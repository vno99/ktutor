# User Stories — ktutor

> Une story = un slice shippable de bout en bout, exécutable par un agent.
> Id format : `s<number>-<short-slug>` — réutilisé dans tous les fichiers pipeline et dans la branche.
> Source de vérité : `docs/prd.md`. Spec technique : `CLAUDE.md`. Règles pipeline : `AGENTS.md`.

---

## Phase 1 — POC (Maths, script CLI, mono-utilisateur local)

### Story s01-uploader-document — Téléverser un document pédagogique

**As an** élève **I want** téléverser un PDF ou une image (dactylo ou manuscrite) **so that** le système l'indexe dans mon RAG personnel.

### Complexity
**3** — Ingestion multi-format (PDF, image dactylo, image manuscrite via OCR LLM), chunking, embeddings, persistance ChromaDB.

### Acceptance criteria
- [ ] Uploading a valid PDF (≤ 20MB) extracts its text, chunks it (RecursiveCharacterTextSplitter, chunk_size=1000, overlap=200), embeds it, and stores the vectors in a ChromaDB collection named `rag_maths_<pseudo>` (one collection per student).
- [ ] Uploading a typed image (PNG/JPG) calls the multimodal LLM to OCR the text, then runs the same pipeline.
- [ ] Uploading a handwritten image calls the multimodal LLM with vision capability; if text is recognized, the same pipeline runs.
- [ ] An invalid upload (file > 20MB, unsupported format, corrupted) returns a clear error and persists nothing.
- [ ] The CLI command `python -m ktutor.cli upload <file> --pseudo <p> --subject maths` returns 0 on success and a documented non-zero code with a message on failure.
- [ ] A success upload creates a `Document` row in PostgreSQL (metadata) and a populated ChromaDB collection (vectors).
- [ ] A test using two different pseudos verifies that documents uploaded by `pseudo_a` are NOT retrievable from `pseudo_b`'s collection (multi-tenant isolation).

### Dependencies
- Monorepo initialized (pré-tâche technique dans le worktree de cette story : `backend/`, `requirements.txt`, `docker-compose.yml`).
- PostgreSQL + ChromaDB running locally (docker-compose up).
- LLM provider configured and reachable (pré-tâche : `MINIMAX_API_KEY` in `.env`, client wrapper tested).

### Agentic notes
- **Files involved** : `backend/app/services/rag/ingestion.py`, `backend/app/services/rag/ocr.py`, `backend/app/services/rag/embeddings.py`, `backend/app/services/rag/chroma_store.py`, `backend/app/cli.py`, `backend/app/core/database/models.py`.
- **Constraints** : One ChromaDB collection per (subject × pseudo) — convention `rag_<subject>_<pseudo>`. Enforce in the store factory, not in callers.
- **Traps** :
  - MinIO bucket prefix `students/<pseudo>/<document_id>` — the document_id must be a UUID, not a path-derived name.
  - PDF scanned vs text PDF: PyMuPDF returns empty text for scanned PDFs. Detect by text length and fall back to OCR.
  - Handwritten image OCR has a non-zero error rate — if confidence < 0.5, reject the upload with a clear message and persist nothing.
  - ChromaDB persistence: use `chromadb.PersistentClient` with `path` from env, not in-memory.
- **Test data** : the agent should generate or fetch one sample PDF, one typed image, one handwritten image (e.g. a scanned math exercise from sesamath). Avoid hardcoding the corpus in the story.
- **Open question (PRD § Questions ouvertes)** : for the POC corpus, use open-license college math manuals (e.g. Sésamath cycle 4) or only student-uploaded documents. Decision to make in Research.

---

### Story s02-chatter-avec-mon-cours — Poser une question sur mon cours et obtenir une réponse sourcée

**As an** élève **I want** poser une question en français sur mon cours de maths **so that** j'obtiens une réponse cohérente qui s'appuie sur mes documents.

### Complexity
**3** — Agent LangChain + RAG retrieval + prompt engineering + source citation.

### Acceptance criteria
- [ ] The CLI command `python -m ktutor.cli chat --pseudo <p> --subject maths --question "..."` returns an answer grounded in the uploaded documents.
- [ ] The answer cites at least one source chunk (filename + page or chunk index).
- [ ] If no relevant chunk is found (similarity below threshold), the agent responds with a clear "je n'ai pas trouvé d'information sur ce sujet dans tes documents" message, not a hallucinated answer.
- [ ] The agent uses the LLM provider from `LLM_PROVIDER` env (default `minimax`).
- [ ] The CLI prints the answer and exits 0.
- [ ] A test verifies that a question for `pseudo_a` retrieves ONLY `pseudo_a`'s documents (no leakage from `pseudo_b`).
- [ ] A test verifies that without any document uploaded, the chat responds with the "no document" message.

### Dependencies
- s01 (documents uploaded exist in the RAG).
- s01 (LLM provider configured).

### Agentic notes
- **Files involved** : `backend/app/services/agents/maths_agent.py` (LangChain agent), `backend/app/services/rag/retriever.py`, `backend/app/cli.py` (extend).
- **Constraints** :
  - For POC, single agent (maths), no supervisor yet — supervisor comes in a later story when French is added.
  - The agent MUST be told in its system prompt to refuse answering from general knowledge and only use retrieved chunks. Verify this in the prompt and in tests.
  - Temperature = 0 for reproducibility in tests.
- **Traps** :
  - ChromaDB returns chunks ordered by similarity. The agent must use the top-k (k=4 default) and cite the source in the answer.
  - "I don't know" must be the default behavior when retrieval returns nothing relevant — not an LLM-fabricated answer.
  - Source citation format: `[source: <filename>, chunk <n>]` — keep it parseable.
- **Test strategy** : use a stub LLM (LangChain's FakeListLLM) for unit tests. End-to-end test with real LLM only in integration suite (not blocking for the PR).

---

### Story s03-generer-qcm — Générer un QCM à partir de mon cours

**As an** élève **I want** générer un QCM (4 propositions, 1 bonne réponse) à partir d'un de mes documents **so that** je puisse m'auto-évaluer.

### Complexity
**3** — LLM generation + structured output parsing + persistence + CLI ergonomics.

### Acceptance criteria
- [ ] The CLI command `python -m ktutor.cli generate-qcm --pseudo <p> --document-id <id> --n 5` returns a JSON with 5 questions, each having `question`, `options` (4 items), `correct_index` (0-3).
- [ ] The output is valid JSON, parseable without manual cleanup.
- [ ] The QCM is generated ONLY from the specified document (chunks filtered by `document_id`).
- [ ] The LLM is prompted to produce exactly the requested structure; if the LLM output is malformed, the system retries once with a stricter prompt, then fails with a clear error.
- [ ] The generated QCM is persisted (PostgreSQL) with metadata: pseudo, document_id, generation_date, questions JSON.
- [ ] A test verifies that the JSON structure matches the schema (4 options, 1 correct index per question).

### Dependencies
- s01 (documents uploaded exist).
- s02 (LLM provider working).

### Agentic notes
- **Files involved** : `backend/app/services/exercises/qcm_generator.py`, `backend/app/core/database/models.py` (add `Exercise` model), `backend/app/cli.py`.
- **Constraints** : Use Pydantic models for the QCM structure; the LLM output MUST be validated against the schema before persistence.
- **Traps** :
  - LLM may output `correct_index: "2"` (string) instead of int — coerce in the parser, don't trust raw LLM output.
  - LLM may produce fewer than 4 options or duplicate options — reject and retry.
  - LLM may leak the answer in the question text (e.g. "Which is NOT correct: 2+2=4") — the prompt must forbid this explicitly and a test must catch a sample case.
- **Prompting tip** : use a JSON-mode or function-calling approach if the LLM supports it; otherwise wrap the prompt in delimiters (`=== JSON START ===`) and parse strictly.

---

### Story s04-repondre-qcm — Soumettre une réponse à un QCM et obtenir un verdict binaire

**As an** élève **I want** soumettre mes réponses à un QCM **so that** je sache si j'ai tout bon ou pas (tout-ou-rien).

### Complexity
**2** — Persistence + comparison + JSON in/out. No LLM call for QCM scoring.

### Acceptance criteria
- [ ] The CLI command `python -m ktutor.cli submit-qcm --exercise-id <id> --answers '[0,2,1,3,0]'` returns `{is_success: true|false, correct_count: int, total: int, feedback: string}`.
- [ ] `is_success` is `true` if and only if ALL answers match `correct_index` for ALL questions.
- [ ] The attempt is persisted in PostgreSQL with: pseudo, exercise_id, attempt_number, is_success, submitted_at, raw_answers.
- [ ] A test verifies that a perfect score returns `is_success: true` and a single-wrong-answer score returns `is_success: false`.
- [ ] A test verifies that attempt_number is incremented correctly across multiple submissions on the same exercise.
- [ ] A test verifies that pseudo_a cannot submit a QCM generated by pseudo_b (multi-tenant isolation).

### Dependencies
- s03 (QCM can be generated).

### Agentic notes
- **Files involved** : `backend/app/services/exercises/qcm_grader.py`, `backend/app/core/database/models.py` (add `Attempt` model), `backend/app/cli.py`.
- **Constraints** : QCM scoring is DETERMINISTIC — no LLM call. Resist the temptation to "improve" with an LLM.
- **Traps** :
  - The submitted answers array MUST have the same length as the QCM questions; reject otherwise.
  - `attempt_number` should be per (pseudo, exercise_id), not global — an attempt on exercise_X doesn't increment the count of exercise_Y.
  - For now, just persist the attempt; the progressive correction logic comes in a later story (this is just the QCM submission mechanism).

---

## Phase 2 — MVP (multi-agents, API + frontend, multi-tenancy)

### Story s05-agent-francais-chat — Chatter avec l'agent Français

**As an** élève **I want** poser une question sur un cours de français **so that** j'obtiens une réponse qui s'appuie sur mes documents de français.

### Complexity
**3** — Second agent + supervisor + separate RAG collection.

### Acceptance criteria
- [ ] A French subject is selectable: `--subject francais` works in the chat CLI.
- [ ] The French agent uses a dedicated ChromaDB collection `rag_francais_<pseudo>`.
- [ ] A LangGraph supervisor routes the question to the maths or French agent based on the `--subject` flag (or, in a follow-up, by question content).
- [ ] The answer cites sources from the French documents.
- [ ] A test verifies that asking a French question with NO French documents uploaded returns the "no document" message (no fallback to maths).
- [ ] A test verifies that documents of `pseudo_a` in `rag_francais_a` are NOT retrievable from `rag_francais_b`.

### Dependencies
- s01 (RAG pipeline supports any subject).
- s02 (maths agent pattern to replicate).

### Agentic notes
- **Files involved** : `backend/app/services/agents/francais_agent.py`, `backend/app/services/agents/supervisor.py` (new), `backend/app/services/agents/__init__.py` (registry).
- **Constraints** :
  - Reuse the existing RAG infrastructure; the subject parameter is the only differentiator.
  - The supervisor starts as a simple switch (subject flag → agent). Routing by content is a later iteration.
- **Traps** :
  - ChromaDB collection naming MUST follow the convention `rag_<subject>_<pseudo>`. Centralize in a factory function.
  - The supervisor's system prompt should make it clear it MUST delegate, not answer directly.
- **Open question (PRD § Questions ouvertes)** : the specifics of the French agent's prompt (level: collège, register: neutre, length: concis) are to be refined in Research.

---

### Story s06-generer-probleme-redaction — Générer un problème de maths ou une rédaction de français

**As an** élève **I want** générer un exercice de type problème (maths) ou rédaction (français) **so that** je puisse m'entraîner sur un exercice libre.

### Complexity
**3** — LLM generation + structured output + persistence.

### Acceptance criteria
- [ ] The CLI command `python -m ktutor.cli generate-exercise --pseudo <p> --subject <s> --type probleme|redaction --topic "..." --difficulty facile|moyen|difficile` returns a JSON with `statement`, `expected_answer` (full solution, for later grading), and `grading_criteria` (list of strings for LLM grading).
- [ ] For `probleme` (maths), the statement is a multi-step problem with explicit numerical data.
- [ ] For `redaction` (français), the statement is a writing prompt (sujet de rédaction) with a target length and register.
- [ ] The exercise is persisted with the same metadata as QCM (pseudo, subject, type, generation_date, statement, expected_answer, grading_criteria).
- [ ] A test verifies the JSON schema is valid for both types.

### Dependencies
- s01 (RAG works for any subject).
- s02 (LLM provider).

### Agentic notes
- **Files involved** : `backend/app/services/exercises/free_generator.py`, `backend/app/core/database/models.py` (extend `Exercise` model).
- **Constraints** : For collège level, the problems and prompts must be age-appropriate — the prompt must explicitly mention the level.
- **Traps** :
  - LLM may produce a "correction" instead of a "statement" — the prompt must forbid this and a test must catch it.
  - The `expected_answer` is the FULL solution used later for grading. It must be richer than the statement.
  - LLM may produce a "redaction" without specifying the length/format — coerce or reject.
- **Open question (PRD § Questions ouvertes)** : the level of detail in math problem statements is to be refined in Research (question ouverte n°2 du PRD, à traiter dans la phase Research de cette story).

---

### Story s06b-generer-flashcards — Générer des flashcards à partir d'un document

**As an** élève **I want** générer des flashcards (recto : question, verso : réponse) à partir d'un de mes documents **so that** je puisse réviser par rappel actif.

### Complexity
**3** — LLM generation + structured output + persistence. Split de l'ancien s06 pour respecter le périmètre PRD (les flashcards sont un type d'exercice à part entière, pas une option de `probleme|redaction`).

### Acceptance criteria
- [ ] The CLI command `python -m ktutor.cli generate-flashcards --pseudo <p> --document-id <id> --n 10` returns a JSON with 10 cards, each having `front` (question/prompt), `back` (answer/explanation), `topic` (string, optional).
- [ ] The output is valid JSON, parseable without manual cleanup.
- [ ] The flashcards are generated ONLY from the specified document (chunks filtered by `document_id`).
- [ ] Each card's `front` is a self-contained question (not a fragment that requires context) and `back` is a concise answer.
- [ ] The generated deck is persisted in PostgreSQL with metadata: pseudo, document_id, generation_date, cards JSON.
- [ ] A test verifies the JSON schema is valid (front, back, topic fields present and non-empty).
- [ ] A test verifies multi-tenant isolation: pseudo_a cannot read the deck of pseudo_b.

### Dependencies
- s01 (RAG works for any subject).
- s02 (LLM provider).
- s03 (the `Exercise` model exists — the flashcard deck reuses it with `type='flashcards'`).

### Agentic notes
- **Files involved** : `backend/app/services/exercises/flashcard_generator.py`, `backend/app/core/database/models.py` (extend `Exercise` model with `type='flashcards'` discriminator if not already present), `backend/app/cli.py` (extend).
- **Constraints** :
  - Use the same Pydantic validation discipline as s03 — the LLM output MUST be validated before persistence.
  - For the POC, flashcards are NOT graded via the progressive correction flow (s08) — they are a study aid, not an evaluated exercise. Mark them as such in the model.
  - Number of cards per generation: configurable, default 10, max 30.
- **Traps** :
  - LLM may produce a `back` that simply repeats the `front` — the prompt must explicitly require the back to BE the answer, not a restatement.
  - LLM may produce cards too long for a real flashcard (multiple sentences) — enforce a max length (e.g. 200 chars per side) and reject or truncate.
  - LLM may generate cards that don't come from the source document — the prompt must say "ONLY from the provided chunks".
- **Test data** : a small math PDF or French text already indexed via s01 is enough — the test asserts schema, not factual correctness.

---

### Story s07-repondre-texte-libre — Soumettre une réponse libre et recevoir une appréciation LLM

**As an** élève **I want** soumettre ma réponse (texte) à un exercice de type problème ou rédaction **so that** je reçoive une appréciation qualitative (positive ou échec) du LLM.

### Complexity
**3** — LLM-as-judge + prompt engineering + parsing + persistence.

### Acceptance criteria
- [ ] The CLI command `python -m ktutor.cli submit-text --exercise-id <id> --answer "..."` returns `{is_success: bool, feedback: string, attempt_number: int}`.
- [ ] The grading uses an LLM prompt that compares the student's answer to the `expected_answer` and outputs a verdict (`REUSSITE` or `ECHEC`) plus a one-sentence feedback.
- [ ] The verdict parsing is strict (regex on `VERDICT:` line); if absent, the system retries once with a stricter prompt, then fails with a clear error.
- [ ] The attempt is persisted (same `Attempt` model as s04, with `answer_text` instead of `answers`).
- [ ] A test with a stub LLM that returns `VERDICT: REUSSITE` verifies that `is_success` is `true`.
- [ ] A test with a stub LLM that returns no `VERDICT:` line verifies that the system retries then fails.
- [ ] A test verifies multi-tenant isolation (pseudo_a cannot submit to an exercise of pseudo_b).

### Dependencies
- s06 (free-form exercises can be generated).

### Agentic notes
- **Files involved** : `backend/app/services/exercises/text_grader.py`, `backend/app/cli.py`.
- **Constraints** :
  - LLM-as-judge is NON-DETERMINISTIC. Tests use a stub. The integration test with the real LLM is best-effort.
  - The grading prompt MUST include: the statement, the expected answer, the student's answer, and the grading criteria. No more, no less.
- **Traps** :
  - The LLM may return verbose prose without the `VERDICT:` line — use a strict regex `/VERDICT:\s*(REUSSITE|ECHEC)/i`.
  - The LLM may hallucinate a good grade for a clearly wrong answer — the prompt must explicitly require strict comparison.
  - A very long student answer may exceed the LLM context — truncate with a warning if it does, but do not silently lose content.

---

### Story s08-correction-progressive — Découvrir la correction par étapes (1 à 3 tentatives)

**As an** élève **I want** que la correction soit dévoilée progressivement (indices d'abord, puis solution) **so that** je sois poussé à réfléchir avant de voir la réponse.

### Complexity
**4** — State machine across attempts + decision logic + persistence + hint generation. Call out the risk below.

### Acceptance criteria
- [ ] After a first failed attempt (QCM or text), the response includes `correction_level: "partial"`, `hints: [str, str, ...]` (1-3 indices), and `next_steps: str`.
- [ ] After a second failed attempt on the same exercise, the response includes `correction_level: "partial_attempt_2"` with more specific hints identifying the error type.
- [ ] After a third failed attempt, the response includes `correction_level: "full_after_attempts"` with the full solution.
- [ ] If the first attempt succeeds, the response includes `correction_level: "full"` with the full solution + bonus points.
- [ ] The state machine is deterministic: success on attempt N (1 ≤ N ≤ 3) → `full`; failure on attempt 1 or 2 → `partial`; failure on attempt 3 → `full_after_attempts` (no 4th attempt; the student cannot submit again on the same exercise).
- [ ] A test covers all 4 correction states: `partial`, `partial_attempt_2`, `full`, `full_after_attempts`, plus the "success on first try" case (5 total).
- [ ] A test verifies that hints on attempt 2 are different from (or richer than) hints on attempt 1.
- [ ] A test verifies multi-tenant isolation.
- [ ] A test verifies that an attempt_number > 3 on the same exercise returns 409 (the exercise is closed after `full_after_attempts`).

### Dependencies
- s04 (QCM submission).
- s07 (text submission).

### Agentic notes
- **Files involved** : `backend/app/services/correction/progressive.py`, `backend/app/services/correction/hints.py`.
- **Risk (complexity 4)** : the state machine has 4+ states × 2 exercise types = a combinatorial surface. The state diagram and the LLM prompts for hints generation are both error-prone. Mitigation: write the state machine as a pure function, unit-test every transition; use a stub LLM for hint generation tests.
- **Constraints** :
  - Hints are LLM-generated, not hard-coded — they must be specific to the student's actual answer and the exercise.
  - The number of attempts is read from `MAX_CORRECTION_ATTEMPTS` env (default 3). After 3 failed attempts, the exercise is CLOSED — a 4th submission returns 409.
  - The correction level is sent to the client; the client decides how to display it.
- **Traps** :
  - The "successful on attempt 1" case must NOT trigger any partial state — verify in the test.
  - A QCM that the student partially gets right (e.g. 4/5) is a FAILURE (QCM is all-or-nothing per PRD). Do not give partial credit.
  - The progressive logic must be the same for QCM and text — but the "hints" content differs (for QCM, hints point to the concept; for text, hints point to the grading criteria not met).
- **Open question (PRD § Questions ouvertes)** : the policy of "failed 3 times = raté vs réussi après aide" is to be decided in Research.

---

### Story s09-api-chat-streaming — Exposer le chat en streaming via FastAPI

**As an** élève **I want** chatter depuis une interface web **so that** je vois la réponse de l'agent s'afficher mot par mot (SSE).

### Complexity
**3** — FastAPI SSE + LangChain streaming + CORS + auth-stub.

### Acceptance criteria
- [ ] The endpoint `POST /api/chat/stream` accepts a JSON body `{pseudo, subject, question}` and returns a `text/event-stream` (SSE) response.
- [ ] Each SSE event contains a chunk of the agent's response (incremental text).
- [ ] A final SSE event contains `{done: true, sources: [...]}`.
- [ ] An error during the stream is sent as an SSE event with `{error: "..."}` and the connection closes cleanly.
- [ ] CORS is configured to allow the frontend origin (from `NEXT_PUBLIC_API_URL` env).
- [ ] A test using FastAPI's TestClient streams a fake agent response and asserts chunks are received in order.
- [ ] A test verifies that an invalid request (missing fields) returns 422 before opening the stream.

### Dependencies
- s02 (chat logic exists).
- s05 (supervisor with multiple agents, if multi-subject is in scope).

### Agentic notes
- **Files involved** : `backend/app/api/chat.py`, `backend/app/main.py` (router include).
- **Constraints** :
  - Use FastAPI's `StreamingResponse` with `media_type="text/event-stream"`.
  - The agent MUST be invoked with `stream=True` (LangChain streaming); do not buffer the full response then stream it.
  - For now, no auth: the `pseudo` comes from the body. Real auth (JWT) comes in a later story.
- **Traps** :
  - CORS preflight (`OPTIONS`) must succeed or the browser will block the stream.
  - The SSE format is `data: <json>\n\n` — missing the trailing newline breaks the client.
  - Closing the stream cleanly on agent error: use a try/finally around the generator.

---

### Story s10-api-upload — Exposer l'upload de documents via FastAPI

**As an** élève **I want** téléverser un document depuis une interface web **so that** il soit indexé dans mon RAG.

### Complexity
**2** — FastAPI multipart + reuse of the s01 ingestion pipeline.

### Acceptance criteria
- [ ] The endpoint `POST /api/documents/upload` accepts `multipart/form-data` with fields `pseudo`, `subject`, and `file` (PDF, PNG, JPG).
- [ ] On success, returns `{document_id: uuid, status: "indexed", chunks_count: int}` with HTTP 201.
- [ ] On failure (oversize, unsupported format, OCR failure), returns 4xx with `{error: "..."}` and persists nothing.
- [ ] The ingestion logic is the SAME as in s01 — extract a service function in s01 if not already, and call it from both the CLI and the API.
- [ ] A test uploads a small valid PDF and verifies the response.
- [ ] A test uploads an oversized file and verifies the 4xx error.
- [ ] A test verifies multi-tenant isolation: pseudo_a uploading does NOT make the document visible to pseudo_b.

### Dependencies
- s01 (ingestion pipeline exists).

### Agentic notes
- **Files involved** : `backend/app/api/documents.py`, refactor `backend/app/services/rag/ingestion.py` to expose a callable function.
- **Constraints** :
  - The size limit (20MB per PRD) is enforced by the API, not just by the CLI.
  - Reuse the CLI ingestion code, do NOT duplicate the logic.
- **Traps** :
  - FastAPI's `UploadFile` is a stream — read it into bytes before passing to the ingestion function (which expects a path or bytes).
  - Multipart parsing may fail on very large files; test with a 20MB+ file to ensure the limit is enforced.
  - The `pseudo` in the body is the source of multi-tenant isolation here. The auth stub (no JWT yet) is acceptable for this story.

---

### Story s11-frontend-upload-chat — Utiliser l'app web pour uploader et chatter

**As an** élève **I want** utiliser une interface web responsive (smartphone + tablette) **so that** je puisse uploader et chatter sans installer quoi que ce soit.

### Complexity
**4** — Next.js 16 + SSE consumption + state management (Zustand) + responsive UI + i18n scaffold. Call out the risk below.

### Acceptance criteria
- [ ] A `/upload` page lets the user select a file, choose a subject, and submit. On success, shows a confirmation. On error, shows a clear error message.
- [ ] A `/chat` page lets the user type a question, choose a subject, and see the agent's response streamed in real time.
- [ ] Both pages are responsive: usable on a 360px-wide screen (smartphone) and on a 768px+ screen (tablet). No horizontal scroll.
- [ ] The chat page reads the SSE stream and appends chunks as they arrive.
- [ ] A footer or header allows switching the UI language between French (default) and English.
- [ ] A test using a headless browser (Playwright) verifies the upload flow end-to-end against a stubbed backend.
- [ ] A test verifies the chat page renders without JavaScript errors and the SSE stream connection is opened.
- [ ] Lighthouse Accessibility score ≥ 90 on both pages.

### Dependencies
- s09 (chat API).
- s10 (upload API).

### Agentic notes
- **Files involved** : `frontend/app/(auth-less)/upload/page.tsx`, `frontend/app/(auth-less)/chat/page.tsx`, `frontend/lib/api.ts` (axios client), `frontend/lib/stores/chatStore.ts` (Zustand), `frontend/messages/fr.json`, `frontend/messages/en.json`, `frontend/middleware.ts` (next-intl).
- **Risk (complexity 4)** : responsive UI, SSE consumption, and i18n are all in the same story — three concerns that can each blow up. Mitigation: each concern in its own commit within the story's branch, and ship a minimal "ugly but works" UI first, polish later in a follow-up story.
- **Constraints** :
  - Use `next-intl` from the start (no hardcoded strings).
  - Use Tailwind for styling; no custom CSS unless strictly necessary.
  - SSE consumption: use `fetch` with `ReadableStream` (the `EventSource` API does not support POST).
- **Traps** :
  - SSE on Next.js: the dev server buffers responses by default. Use a reverse proxy or a Node runtime for the chat route.
  - The chat page must not break if the SSE connection drops — show a "connection lost, retry?" UI.
  - The i18n middleware must be registered in `next.config.js` correctly, or the locale switcher is a no-op.
  - File upload from a smartphone camera requires `accept="image/*" capture="environment"` — without `capture`, the user gets a file picker, not the camera.

---

## Phase 3 — Authentification, RBAC, isolation multi-tenant transverse

### Story s12-creer-compte-eleve — Créer un compte élève (pseudo + mot de passe)

**As a** visiteur **I want** créer un compte élève en choisissant un pseudo et un mot de passe **so that** je puisse m'authentifier et accéder à mon espace.

### Complexity
**2** — Form + PostgreSQL insert + bcrypt hash + uniqueness check.

### Acceptance criteria
- [ ] The endpoint `POST /api/auth/register` accepts `{pseudo, password}` and returns 201 with `{pseudo}` on success.
- [ ] The password is hashed with bcrypt (NOT stored in plain text).
- [ ] The pseudo is unique (case-insensitive). A duplicate returns 409 with a clear error.
- [ ] The pseudo is 3-32 chars, alphanumeric + underscore. A violation returns 422.
- [ ] The password is ≥ 8 chars. A violation returns 422.
- [ ] A `User` row is created in PostgreSQL with `role='eleve'` by default (this story covers ONLY the `eleve` role; creation of `parent` and `admin` is in s12b).
- [ ] A test verifies the happy path and the duplicate-pseudo case.

### Dependencies
- PostgreSQL initialized (s01 pré-tâche).

### Agentic notes
- **Files involved** : `backend/app/api/auth/register.py`, `backend/app/core/database/models.py` (`User` model), `backend/app/core/auth/passwords.py` (bcrypt wrapper).
- **Constraints** :
  - JWT is NOT in this story — this is just account creation. Login (token issuance) is a separate story.
  - The `pseudo` is the only identifier — no email, no real name (per PRD § Hors-scope).
  - This endpoint is public; only `eleve` is creatable via the public path. The `parent` and `admin` roles require a different story (s12b) because they need a different onboarding path.
- **Traps** :
  - Bcrypt has a 72-byte input limit — pre-hash with SHA-256 if the password is long, or just enforce a 72-byte max.
  - The uniqueness check should be case-insensitive (use `LOWER()` in the SQL).
  - Do NOT log the password, even in error messages.

---

### Story s12b-creer-compte-admin-parent — Créer un compte parent ou admin et mettre à jour un rôle

**As an** admin **I want** créer un compte parent (ou admin) et pouvoir changer le rôle d'un utilisateur existant **so that** les comptes non-élève existent et le RBAC soit testable de bout en bout.

### Complexity
**3** — Admin-only endpoints + role update + auditability. Split de l'ancien s12 + s14 pour résoudre la dépendance cyclique : s14 (lier parent ↔ enfant) présuppose qu'un compte `parent` existe, ce qui n'était livré par aucune story. Cette story doit précéder s14.

### Acceptance criteria
- [ ] The endpoint `POST /api/users` (admin only, JWT) accepts `{pseudo, password, role: "parent" | "admin"}` and returns 201 with `{pseudo, role}`.
- [ ] The endpoint enforces: the authenticated user MUST have `role='admin'`. A non-admin caller gets 403.
- [ ] The `pseudo` follows the same rules as s12 (3-32 chars, alphanumeric + underscore, unique case-insensitive).
- [ ] The `User` row is created with the requested role (not forced to `eleve`).
- [ ] The endpoint `PUT /api/users/{pseudo}/role` (admin only) accepts `{role: "eleve" | "parent" | "admin"}` and updates the role. Returns 200 with the updated user.
- [ ] An admin cannot demote themselves (the last admin cannot change their own role to `parent` or `eleve`) — returns 409 if attempted.
- [ ] A test verifies an admin can create a `parent` user.
- [ ] A test verifies a non-admin caller gets 403 on `POST /api/users`.
- [ ] A test verifies role update is logged (audit trail entry).
- [ ] A test verifies multi-tenant behavior: a `parent` user (not admin) gets 403 on these endpoints.

### Dependencies
- s12 (the `User` model exists).
- s13 (JWT middleware exists — to verify the `admin` role).

### Agentic notes
- **Files involved** : `backend/app/api/users/create.py`, `backend/app/api/users/role.py`, `backend/app/core/database/models.py` (extend `User` if needed), `backend/app/api/auth/dependencies.py` (RBAC helper for "admin only").
- **Constraints** :
  - This is a SECURITY-CRITICAL story. The admin endpoints MUST be locked down (no public access, even authenticated non-admin).
  - The password is hashed with bcrypt (reuse s12's wrapper).
  - For the POC, the `audit trail` is a simple log line (`security.role_change`) — a dedicated `AuditLog` table is a future optimization.
- **Traps** :
  - The "last admin" check requires a count query — handle the race condition with a transaction (lock the row, count admins, then update).
  - Do NOT allow an admin to create a `parent` user with the same `pseudo` as an existing `eleve` (or vice versa) — pseudo uniqueness spans all roles.
  - The `POST /api/users` endpoint does NOT issue a JWT — the created user must log in via `POST /api/auth/login` (s13) to get a token.
- **Test strategy** : seed the test database with an `admin` user via a fixture (e.g. environment-driven bootstrap or a migration seed); the test client logs in as that admin to call these endpoints.

---

### Story s13-login-eleve — Se connecter et obtenir un JWT

**As an** élève **I want** me connecter avec mon pseudo + mot de passe **so that** je reçoive un JWT à utiliser pour les requêtes authentifiées.

### Complexity
**3** — JWT generation (RS256) + refresh tokens + expiration + middleware.

### Acceptance criteria
- [ ] The endpoint `POST /api/auth/login` accepts `{pseudo, password}` and returns `{access_token, refresh_token, token_type: "bearer", expires_in}`.
- [ ] The access token is a JWT signed with RS256 (private key from env, never from the codebase).
- [ ] The access token expires in 30 minutes (from `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` env).
- [ ] The refresh token expires in 7 days.
- [ ] The endpoint `POST /api/auth/refresh` accepts a refresh token and returns a new access token (and rotates the refresh token).
- [ ] A wrong password returns 401 with a generic "invalid credentials" message (do not leak whether the pseudo exists).
- [ ] The access token contains the claims: `sub` (pseudo), `role`, `iat`, `exp`.
- [ ] A test verifies a valid login returns a JWT decodable to the expected claims.
- [ ] A test verifies an expired token is rejected by the middleware.

### Dependencies
- s12 (User row exists).

### Agentic notes
- **Files involved** : `backend/app/api/auth/login.py`, `backend/app/api/auth/refresh.py`, `backend/app/core/auth/jwt.py`, `backend/app/core/auth/middleware.py`.
- **Constraints** :
  - RS256 (asymmetric). The private key signs; the public key verifies. For a local POC, both can live on the same machine, but the structure must be ready for the public key to be distributed.
  - Never log the token, even partially.
- **Traps** :
  - The JWT secret must come from env, not from a hardcoded fallback. Crash on missing env in production; warn in dev.
  - The middleware must reject tokens with `alg: none` (a known attack). Pin the algorithm.
  - Token rotation on refresh: invalidate the old refresh token. For a local POC, a simple in-memory blacklist is acceptable; for production, use Redis.

---

### Story s14-lier-parent-enfant — Lier un compte parent à un compte enfant

**As a** parent **I want** que mon compte soit lié au compte de mon enfant **so that** je puisse consulter sa progression.

### Complexity
**2** — Form + PostgreSQL relationship + admin-or-parent-self linking.

### Acceptance criteria
- [ ] The endpoint `POST /api/users/{parent_pseudo}/children` with body `{child_pseudo}` creates a `ParentChildLink` row in PostgreSQL.
- [ ] Only an admin (JWT role='admin') or the parent themselves (JWT sub matches `{parent_pseudo}`) can create the link. Any other caller gets 403.
- [ ] The same child cannot be linked twice to the same parent (idempotency: returns 200 on duplicate, 201 on new).
- [ ] The endpoint `GET /api/users/{parent_pseudo}/children` returns the list of linked children. Authorization: admin or the parent themselves.
- [ ] A test verifies a parent can list their own children.
- [ ] A test verifies a parent cannot list another parent's children (multi-tenant isolation).
- [ ] A test verifies a non-admin, non-parent caller gets 403.

### Dependencies
- s12 (eleve User row exists for the child).
- s12b (parent and admin User rows exist).
- s13 (auth middleware enforces role).

### Agentic notes
- **Files involved** : `backend/app/api/users/parent_child.py`, `backend/app/core/database/models.py` (add `ParentChildLink` model).
- **Constraints** : The link is many-to-many (a parent can have multiple children, a child can have multiple parents — for blended families or shared custody).
- **Traps** :
  - The endpoint URL is `/api/users/{parent_pseudo}/children` — the `parent_pseudo` in the URL must match the authenticated user (or the user must be an admin). Do not trust the URL value.
  - Cycle detection: in theory, a parent-child link could be cyclic (A is parent of B, B is parent of A). For the POC, no cycle prevention — note as a follow-up.
  - This story was previously blocked on the absence of a story creating `parent` accounts. The dependency chain is now: s12 → s12b → s13 → s14.

---

### Story s15-restrictions-rbac — Empêcher un élève d'accéder aux données d'un autre

**As a** système **I want** que chaque requête authentifiée soit restreinte aux données du `pseudo` du JWT **so that** l'isolation multi-tenant soit garantie.

### Complexity
**3** — Middleware + repository-level filters + tests d'isolation pour chaque endpoint.

### Acceptance criteria
- [ ] Every authenticated endpoint extracts the `pseudo` from the JWT and uses it as the tenant key.
- [ ] Any request where a body/URL field contains a `pseudo` different from the JWT's `pseudo` is rejected with 403 (for an élève) or processed (for an admin).
- [ ] Every existing endpoint that returns or mutates data has a corresponding test that verifies cross-tenant access is blocked.
- [ ] The middleware logs a `security.cross_tenant_attempt` event when a block occurs.
- [ ] A test simulates a student JWT trying to access another student's data via URL manipulation and verifies the 403.

### Dependencies
- s13 (JWT middleware exists).
- All prior API endpoints (s09, s10) must be migrated to the JWT-based auth (this story includes the migration as a task).

### Agentic notes
- **Files involved** : `backend/app/core/auth/middleware.py` (extend), all `backend/app/api/**/*.py` (use `Depends(get_current_user)`).
- **Constraints** :
  - This is the security foundation — every API story after this one inherits it.
  - The `admin` role bypasses the tenant check (admins can impersonate for support).
- **Traps** :
  - Do NOT trust the `pseudo` from the URL or body — always derive it from the JWT.
  - The migration from the "pseudo in body" auth (s09, s10) to JWT auth is part of this story. The test suite must cover BOTH the old and the new auth to ensure nothing regresses.
  - The 403 message must be generic ("forbidden") — do not leak which tenant key was attempted.

---

## Phase 4 — Pédagogie (dashboards, historique, évaluations, récompenses)

### Story s16-dashboard-eleve — Voir ma progression (scores, exercices tentés, temps)

**As an** élève **I want** voir un dashboard avec mes scores par matière, mes exercices tentés, et mon temps d'activité **so that** je suive ma progression.

### Complexity
**3** — Aggregated SQL queries + chart rendering + responsive layout.

### Acceptance criteria
- [ ] The endpoint `GET /api/dashboard/eleve` (JWT auth) returns `{subjects: [{name, score_avg, exercises_count, last_activity_at}], global: {...}}`.
- [ ] The `/dashboard/eleve` page renders the data as a chart per subject + a summary card.
- [ ] The chart is readable on a 360px-wide screen (legend below the chart, not next to it).
- [ ] The data is cached for 5 minutes to avoid hammering the database.
- [ ] A test verifies the dashboard returns data for an authenticated student.
- [ ] A test verifies the dashboard returns 403 for another student trying to access it (via JWT swap in the test).

### Dependencies
- s04, s07 (attempts persisted).
- s15 (auth + multi-tenant).

### Agentic notes
- **Files involved** : `backend/app/api/dashboard/eleve.py`, `frontend/app/(dashboard)/eleve/dashboard/page.tsx`.
- **Constraints** :
  - Use a simple charting library (Recharts or Chart.js) — do NOT build a custom SVG chart from scratch.
  - The cache key is per `(pseudo, date)` — invalidated on each new attempt.
- **Traps** :
  - "Time spent" is hard to measure accurately (the user can leave the tab open). For the POC, use a simple metric: sum of session durations (login → logout). Do not over-engineer.
  - The dashboard MUST work offline (cache-first) — see observability story for the offline pattern.

---

### Story s17-dashboard-parent — Voir la progression de mes enfants (lecture seule)

**As a** parent **I want** voir la progression de chacun de mes enfants **so that** je suive leur travail sans pouvoir le modifier.

### Complexity
**3** — Reuse the eleve dashboard with a parent-facing read-only wrapper. La complexité est relevée de 2 à 3 (vs version précédente) car la story cumule : endpoint parent, page liste, page child-detail, vérification read-only, tests d'isolation. Risque explicité ci-dessous.

### Acceptance criteria
- [ ] The endpoint `GET /api/dashboard/parent` (JWT auth) returns the dashboards of all children linked to the parent.
- [ ] The `/dashboard/parent` page lists each child as a card, each card linking to a child-detail view.
- [ ] The child-detail view is the same component as the eleve dashboard, but with no edit/action buttons.
- [ ] A test verifies the parent sees only their linked children.
- [ ] A test verifies a parent cannot access a non-linked child's data (multi-tenant isolation).
- [ ] A test verifies all "edit" buttons in the reused component are hidden or disabled in the parent view.

### Dependencies
- s14 (parent-child link).
- s15 (auth + multi-tenant).
- s16 (eleve dashboard exists).

### Agentic notes
- **Files involved** : `backend/app/api/dashboard/parent.py`, `frontend/app/(dashboard)/parent/page.tsx`, `frontend/app/(dashboard)/parent/[child_pseudo]/page.tsx`.
- **Constraints** : No write actions on the parent view — buttons for "submit answer", "generate exercise", etc. are absent or disabled.
- **Risk (complexity 3)** : the "reuse" of the eleve dashboard component is the most error-prone part. The component must accept a `readOnly` prop and disable/hide write affordances. Mitigation: extract the read-only view into its own component first, then re-integrate the write-only parts in the eleve view.
- **Traps** :
  - The parent JWT must NOT allow accessing `/api/dashboard/eleve/{other_pseudo}` — the URL is `/api/dashboard/parent` and the backend filters by the linked children.
  - The child-detail URL includes the `child_pseudo` for clarity, but the backend MUST verify that the parent is linked to that child before returning data.

---

### Story s18-uploader-copie-extraire-score — Téléverser une copie d'évaluation corrigée et extraire le score

**As an** élève **I want** téléverser une photo de ma copie d'évaluation corrigée par l'enseignant **so that** le système extraie le score et les annotations.

### Complexity
**4** — LLM vision + score extraction (regex + LLM) + structured storage + edge cases (manuscrit illisible, format inattendu). Call out the risk.

### Acceptance criteria
- [ ] The endpoint `POST /api/evaluations/upload` accepts `multipart/form-data` with `pseudo`, `subject`, and `file` (image).
- [ ] The LLM vision extracts: `score` (number or "non précisé"), `max_score` (number or "non précisé"), `annotations` (list of strings), `teacher_comments` (string or null).
- [ ] The extraction uses BOTH a regex (for explicit scores like "12/20") and an LLM call (for unstructured comments).
- [ ] If neither regex nor LLM finds a score, the system returns the upload with `status: "manual_review_needed"` and prompts the user (or an admin) to enter the score manually (the manual entry path is s18b).
- [ ] The extracted data is persisted in a `Evaluation` row in PostgreSQL.
- [ ] A test with a sample image containing "12/20" verifies the regex picks it up.
- [ ] A test with a sample image (no clear score) verifies the LLM is called and a result is returned (or "manual_review_needed").
- [ ] A test verifies multi-tenant isolation.

### Dependencies
- s10 (upload API exists).
- s15 (auth).

### Agentic notes
- **Files involved** : `backend/app/services/ocr/evaluation_extractor.py`, `backend/app/api/evaluations.py`, `backend/app/core/database/models.py` (add `Evaluation` model).
- **Risk (complexity 4)** : LLM vision is non-deterministic and the extraction surface is wide (multiple score formats, languages, handwriting styles). Mitigation: structured prompt with explicit fields, regex as a fast-path, manual review as the fallback.
- **Constraints** :
  - The extraction prompt must ask for the score in a STRICT format (e.g. "If a score is visible, reply `SCORE: <n>/<m>`. If not, reply `SCORE: NONE`.").
  - The "manual_review_needed" state is part of the success flow (HTTP 201 with a flag), not an error.
- **Traps** :
  - The LLM may hallucinate a score when none is visible. The prompt must include "If no score is clearly written, do not guess — reply `SCORE: NONE`."
  - The LLM may extract the wrong number (e.g. "élève noté 12 sur 20" but the actual score is 8 because the 12 is in a different sentence). The regex should anchor on `/<n>\s*\/\s*<m>/` patterns to reduce false positives.
  - A photo with low resolution or bad lighting may yield no text — fall back to "manual_review_needed" without retrying the LLM.
- **Follow-up** : the manual score entry and LLM reprocess endpoints are in s18b.

---

### Story s18b-evaluation-actions-admin — Saisir ou relancer l'extraction du score d'une évaluation

**As an** admin (ou un parent lié) **I want** saisir manuellement le score d'une copie d'évaluation en `manual_review_needed` (ou relancer l'extraction LLM) **so that** les copies sans score détecté puissent tout de même alimenter les dashboards.

### Complexity
**2** — Deux endpoints admin + RBAC + transition d'état `manual_review_needed` → `scored`. Split de l'ancien s18 pour fermer la boucle d'extraction de score (sans ces endpoints, les copies non auto-scorées sont des données mortes).

### Acceptance criteria
- [ ] The endpoint `POST /api/evaluations/{id}/score-manual` (admin or linked parent, JWT) accepts `{score, max_score, teacher_comments?}` and updates the `Evaluation` row. Returns 200 with the updated evaluation.
- [ ] The endpoint validates that the evaluation is in `manual_review_needed` status; otherwise returns 409 (already scored).
- [ ] A non-admin, non-linked-parent caller gets 403.
- [ ] The endpoint `POST /api/evaluations/{id}/reprocess` (admin only, JWT) re-invokes the LLM vision extractor on the original image. Returns 200 with the new extraction result (or `manual_review_needed` if it still fails).
- [ ] Both endpoints update the `Evaluation.status` to `scored` on success, or leave it as `manual_review_needed` on failure.
- [ ] A test verifies an admin can manually score an evaluation in `manual_review_needed`.
- [ ] A test verifies a non-admin, non-parent caller gets 403.
- [ ] A test verifies multi-tenant isolation: a parent cannot score an evaluation of a non-linked child.

### Dependencies
- s18 (the `Evaluation` row exists with `manual_review_needed` status).
- s14 (parent-child link — to authorize the linked parent).
- s15 (auth + multi-tenant).

### Agentic notes
- **Files involved** : `backend/app/api/evaluations/score_manual.py`, `backend/app/api/evaluations/reprocess.py`.
- **Constraints** :
  - These are admin-first endpoints, with a narrow parent exception (only the parent linked to the student can score the child's evaluation).
  - Manual score entry is auditable — log `security.evaluation_manual_score` with the admin/parent pseudo, the evaluation_id, and the new score.
  - The reprocess endpoint reuses the extractor from s18; do not duplicate the LLM call logic.
- **Traps** :
  - The `score` and `max_score` MUST be non-negative numbers; `score` MUST be ≤ `max_score`. Validate before persisting.
  - The reprocess endpoint must NOT delete the previous extraction result — keep the history (or at least a log) for debugging.
  - A parent can score their child's evaluation, but the "linked" check is in the multi-tenant test — do not forget the `parent_child` link lookup in the authorization path.

---

### Story s19-historique-conversations — Consulter l'historique de mes conversations

**As an** élève **I want** consulter l'historique de mes conversations passées **so that** je retrouve une explication que j'ai eue.

### Complexity
**2** — List endpoint + paginated query + frontend history view.

### Acceptance criteria
- [ ] The endpoint `GET /api/chat/history?limit=20&offset=0` (JWT auth) returns the user's past conversations, newest first.
- [ ] Each conversation includes: `id`, `subject`, `first_question`, `last_activity_at`, `message_count`.
- [ ] The endpoint `GET /api/chat/history/{conversation_id}` returns the full message thread.
- [ ] The `/history` page lists the conversations and clicking one opens the detail.
- [ ] Pagination uses `limit` + `offset` (no cursor for the POC).
- [ ] A test verifies a student sees only their own conversations.
- [ ] A test verifies pagination works (limit=2 returns 2, offset=2 returns the next 2).

### Dependencies
- s15 (auth).

### Agentic notes
- **Files involved** : `backend/app/api/chat/history.py`, `frontend/app/(dashboard)/eleve/history/page.tsx`.
- **Constraints** : The conversation storage must be efficient — denormalize `first_question` and `message_count` to avoid scanning all messages on the list endpoint.
- **Traps** :
  - The detail endpoint must verify the conversation belongs to the authenticated user (not just any conversation with the same ID).
  - Storing full message threads in PostgreSQL works for the POC, but the column should be JSONB for flexibility (e.g. later adding tool calls, sources, etc.).

---

### Story s20-systeme-recompenses — Gagner des points en réussissant des exercices

**As an** élève **I want** gagner des points quand je réussis un exercice (et plus si réussite du premier coup) **so that** je sois encouragé à progresser.

### Complexity
**3** — Points ledger + level/threshold logic + frontend badge component.

### Acceptance criteria
- [ ] Submitting a successful QCM or text answer awards 5 base points.
- [ ] A first-try success (attempt_number = 1) awards 5 + 2 = 7 points (bonus).
- [ ] A failed attempt awards 0 points (participation only — but the attempt is still recorded in the `Attempt` table).
- [ ] After 3 failed attempts, the full correction is shown but no points are awarded. The exercise is then CLOSED — a 4th submission returns 409 (see s08).
- [ ] Points are stored in a `RewardLedger` (immutable log) and a `UserPoints` summary.
- [ ] The dashboard shows the current points total and the level (e.g. "Apprenti" 0-99, "Confirmé" 100-499, "Expert" 500+).
- [ ] A test verifies the points awarded for each scenario (1st-try success: 7, later success: 5, failure: 0, 3 failures + closed: 0).
- [ ] A test verifies the ledger is append-only (no UPDATE on existing rows).

### Dependencies
- s04, s07, s08 (attempts + correction logic).
- s16 (dashboard to show the points).

### Agentic notes
- **Files involved** : `backend/app/services/rewards/ledger.py`, `backend/app/services/rewards/levels.py`, `backend/app/core/database/models.py` (add `RewardLedger`, `UserPoints`).
- **Constraints** :
  - The ledger is the source of truth. The `UserPoints` summary is a denormalization, recomputable from the ledger.
  - Levels and thresholds are constants for the POC; if changed, recompute all `UserPoints` from the ledger.
- **Traps** :
  - Concurrency: two parallel submissions must not double-count points. Use a DB transaction with row-level locking on `UserPoints`.
  - The 3-attempt rule means an exercise can have at most 3 attempts (1st failure → 2nd failure → 3rd failure → closed with `full_after_attempts`). Each attempt is recorded in the ledger with its points (always 0 for failed attempts).

---

## Phase 5 — Finalisation (i18n, accessibilité, observabilité, notifications, docs)

### Story s21-i18n-fr-en — Basculer l'interface entre français et anglais

**As a** utilisateur **I want** basculer l'interface entre français et anglais **so that** l'application soit utilisable dans les deux langues.

### Complexity
**3** — next-intl setup + message catalogs + backend Accept-Language. La complexité est relevée de 2 à 3 (vs version précédente) car la story couvre deux surfaces techniques très différentes (frontend next-intl + backend i18n sur les messages d'erreur). Risque explicité.

### Acceptance criteria
- [ ] All UI strings come from `frontend/messages/fr.json` and `frontend/messages/en.json` — no hardcoded strings in components.
- [ ] A language switcher in the header lets the user toggle between FR and EN.
- [ ] The choice persists across page reloads (cookie).
- [ ] Backend API responses respect the `Accept-Language` header for any user-facing string (errors, prompts).
- [ ] A test verifies that switching to EN translates all visible strings on the chat page.
- [ ] A test verifies the backend returns a French error message for a French request and English for an English one.

### Dependencies
- s11 (frontend chat page exists).

### Agentic notes
- **Files involved** : `frontend/middleware.ts` (next-intl), `frontend/messages/fr.json`, `frontend/messages/en.json`, `backend/app/api/*` (i18n on error messages).
- **Constraints** :
  - For the POC, only FR and EN. Other languages are out of scope (per PRD § Hors-scope).
  - The backend error messages are minimal for the POC; if the messages grow, use a Pydantic + gettext approach.
- **Risk (complexity 3)** : the two surfaces (frontend next-intl vs backend Accept-Language) have very different toolchains and runtime contracts. Mitigation: define a small JSON message catalog contract for the backend (error codes → messages) and reuse the same catalog format as the frontend for consistency.
- **Traps** :
  - Do not translate content uploaded by the user (manuscript text, documents) — only UI chrome.
  - Locale routing: the chat page URL can be `/fr/chat` or `/en/chat`, or use a cookie — pick ONE for the POC and stick to it.

---

### Story s22-accessibilite-responsive — Rendre l'interface accessible et responsive (WCAG 2.1 A)

**As a** utilisateur sur smartphone ou tablette **I want** que l'interface soit lisible, navigable au clavier, et conforme aux standards d'accessibilité **so that** je puisse utiliser l'application sur n'importe quel appareil et avec un lecteur d'écran.

### Complexity
**3** — Lighthouse audit + ARIA attributes + keyboard navigation + contrast fixes.

### Acceptance criteria
- [ ] Lighthouse Accessibility score ≥ 90 on the chat, upload, dashboard, and history pages.
- [ ] All interactive elements are reachable via Tab key with a visible focus indicator.
- [ ] All images have an `alt` attribute (or `alt=""` if decorative).
- [ ] The color contrast ratio for text is ≥ 4.5:1 (WCAG AA).
- [ ] All form fields have an associated `<label>`.
- [ ] The layout is usable on 360px, 768px, and 1280px wide screens (no horizontal scroll, no overlapping elements).
- [ ] A test using Playwright + axe-core runs an automated audit on the main pages and asserts no critical violations.

### Dependencies
- s11 (frontend exists).

### Agentic notes
- **Files involved** : all `frontend/app/**/page.tsx` and components, `frontend/tailwind.config.js` (focus styles, contrast tokens).
- **Constraints** : WCAG 2.1 A is the minimum (per CLAUDE.md). AA is a stretch goal.
- **Traps** :
  - Streaming chat output must be announced to screen readers — use `aria-live="polite"` on the message container.
  - Custom dropdowns (subject selector) need ARIA roles; native `<select>` is preferred.
  - The mobile camera capture (`capture="environment"`) is not an accessibility issue per se, but ensure the file picker fallback is labeled.

---

### Story s23-observabilite-logs-metriques — Ajouter logs structurés, traces et métriques

**As a** opérateur **I want** que toutes les requêtes, appels LLM, et tâches soient loguées, tracées, et mesurées **so that** je puisse diagnostiquer les problèmes et suivre les performances.

### Complexity
**3** — Structured logging + OpenTelemetry + Prometheus + dashboard.

### Acceptance criteria
- [ ] All log lines are JSON-structured (timestamp, level, message, request_id, pseudo, route, duration_ms).
- [ ] All HTTP requests emit a log line with the above fields (FastAPI middleware).
- [ ] All LLM calls emit a log line with prompt_tokens, completion_tokens (if available), duration_ms, model.
- [ ] All Celery tasks emit a log line on start, success, and failure.
- [ ] OpenTelemetry traces are exported to the console (local) and to OTLP if `OTEL_EXPORTER=otlp` is set.
- [ ] Prometheus metrics are exposed at `/metrics` (no auth in local) with at least: `http_requests_total`, `http_request_duration_seconds`, `llm_calls_total`, `llm_call_duration_seconds`, `rag_retrievals_total`.
- [ ] A test verifies a sample request produces the expected log lines and metrics.

### Dependencies
- All prior API stories (s09, s10, s12-s20) — this story retrofits them.

### Agentic notes
- **Files involved** : `backend/app/core/observability/logging.py`, `backend/app/core/observability/tracing.py`, `backend/app/core/observability/metrics.py`, `backend/app/main.py` (middleware registration), `backend/app/api/metrics.py` (`/metrics` endpoint).
- **Constraints** :
  - Use `loguru` for Python logging and `pino` for TypeScript (already in CLAUDE.md).
  - The middleware order is critical: logging first, then metrics, then auth. Otherwise unauthenticated requests pollute the metrics.
  - LLM tracing wraps LangChain's callbacks — use `langchain.callbacks.tracers.logging` or a custom callback.
- **Traps** :
  - Logs must NOT contain the password, the JWT, or the document content (PII-ish).
  - The `/metrics` endpoint must be excluded from the request logger to avoid infinite recursion.
  - Tracing adds latency (~5-10ms) — measure and accept, do not optimize prematurely.

---

### Story s24-alerting — Configurer des alertes sur les signaux critiques

**As a** opérateur **I want** être alerté quand le taux d'erreur dépasse 5% ou la latence p95 dépasse 5 secondes **so that** je puisse réagir avant que les utilisateurs ne soient impactés.

### Complexity
**2** — Alert rules in Prometheus + simple Grafana dashboard or local console output.

### Acceptance criteria
- [ ] An alert rule fires when `rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05` for 2 minutes.
- [ ] An alert rule fires when `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 5` for 5 minutes.
- [ ] An alert rule fires when `celery_queue_length > 100`.
- [ ] For the POC, the alerts are displayed in the console (log line with severity ALERT) — no PagerDuty / Slack integration.
- [ ] A test with a synthetic 5xx storm verifies the alert fires within 2 minutes.

### Dependencies
- s23 (observability infrastructure exists).

### Agentic notes
- **Files involved** : `backend/app/core/observability/alerts.py`, `ops/prometheus/alerts.yml` (if using Prometheus rule files), `frontend/app/(admin)/ops/page.tsx` (optional local dashboard).
- **Constraints** : For the POC, console output is acceptable. Production should use Alertmanager + a notification channel.
- **Traps** :
  - Alert thresholds are POC defaults — adjust after observing real traffic.
  - "5xx storm" is hard to simulate in tests. Use a synthetic load generator (e.g. `locust` or a simple `httpx` loop) to trigger the rule.

---

### Story s25-notifications-in-app — Recevoir des notifications in-app (nouvelle évaluation, points gagnés)

**As an** élève **I want** recevoir une notification in-app quand mon évaluation est traitée ou que je gagne des points **so that** je sois informé sans avoir à rafraîchir la page.

### Complexity
**3** — Polling or SSE-based notification feed + unread count + frontend toast.

### Acceptance criteria
- [ ] When an `Evaluation` is processed (s18), a `Notification` row is created.
- [ ] When a `RewardLedger` entry awards points (s20), a `Notification` row is created.
- [ ] The endpoint `GET /api/notifications?unread_only=true` returns the user's notifications.
- [ ] The endpoint `POST /api/notifications/{id}/read` marks a notification as read.
- [ ] The frontend shows a toast for new notifications and an unread count in the header.
- [ ] The notification feed is polled every 30 seconds (no WebSocket for the POC).
- [ ] A test verifies a notification is created on evaluation processing.
- [ ] A test verifies the unread count is correct.

### Dependencies
- s18, s20 (events that trigger notifications).

### Agentic notes
- **Files involved** : `backend/app/api/notifications.py`, `backend/app/core/database/models.py` (add `Notification` model), `frontend/lib/stores/notificationsStore.ts`, `frontend/app/(dashboard)/eleve/layout.tsx` (header).
- **Constraints** : Polling (30s) is acceptable for the POC. WebSocket / SSE for notifications is a later optimization.
- **Traps** :
  - The notification must be created in the SAME transaction as the event (evaluation processed, points awarded). Otherwise, a crash between the two leaves the user uninformed.
  - Marking as read must be idempotent (POST to a read notification is a no-op, not an error).

---

### Story s26-documentation-utilisateur — Rédiger la documentation utilisateur

**As a** utilisateur (élève, parent, admin) **I want** accéder à une documentation claire **so that** je sache comment utiliser l'application.

### Complexity
**1** — Markdown docs + simple static site or `/docs` page.

### Acceptance criteria
- [ ] A `docs/user-guide/` directory contains: `eleve.md`, `parent.md`, `admin.md` (in FR and EN).
- [ ] The `/docs` page in the app renders the user guide as a navigable static site.
- [ ] The user guide covers: account creation, uploading a document, chatting, generating an exercise, submitting an answer, viewing the dashboard (eleve), linking a child and viewing their progress (parent), managing users (admin).
- [ ] Screenshots or short screen recordings illustrate the key flows.
- [ ] A test verifies all links in the user guide resolve to a section (no broken anchors).

### Dependencies
- s11, s16, s17, s18, s20 (the features being documented exist).

### Agentic notes
- **Files involved** : `docs/user-guide/*.md`, `frontend/app/docs/[...slug]/page.tsx`.
- **Constraints** : Keep the guide short (one page per persona). Link to deeper explanations, do not embed them.
- **Traps** :
  - The guide MUST be updated when features change. A test that compares the guide's section count to the route count can catch drift.
  - Avoid screenshots from an outdated UI version — automate with Playwright snapshots.

---

## Notes de fin

### Dépendances interphases (transversales)

- **Multi-tenancy** : toute story API (s09, s10, s14, s15, s16, s17, s18, s18b, s19, s20) inclut un test d'isolation cross-tenant. La story s15 consolide le middleware ; les stories antérieures peuvent l'utiliser partiellement.
- **Observabilité** : les stories s23-s24 retrofitent les stories antérieures. Les stories entre s15 et s22 doivent au minimum logger les requêtes (mais le middleware complet est en s23).
- **i18n** : à partir de s11, les nouvelles chaînes UI passent par `next-intl`. s21 consolide.
- **Accessibilité** : à partir de s11, respecter les bonnes pratiques (label, focus, contrast). s22 consolide et audite.

### Stories candidates non retenues

Les stories candidates `STORY-005` (init monorepo) et `STORY-006` (config LLM) ont été **intégrées comme pré-tâches techniques** dans la première story qui en a besoin (s01). Elles ne sont pas des stories en soi — ce sont des conditions préalables.

### Splits

- `STORY-003` (test OCR manuscrit) → pré-tâche de s01 (test d'ingestion incluant une image manuscrite).
- `STORY-007` (génération QCM) → **s03** (story à part entière, livrée indépendamment).
- `STORY-013` (problèmes maths) + `STORY-014` (flashcards) → splittés en **s06** (problème/rédaction) et **s06b** (flashcards). Le périmètre PRD liste explicitement les flashcards comme type d'exercice à part entière, donc elles ont leur propre story shippable.
- `STORY-019` (correction progressive) → **s08** (complexity 4, risque explicité).
- `STORY-021` (dashboards) → splitté en **s16** (eleve) et **s17** (parent) pour limiter la complexité par story.
- `STORY-022` (historique conversations) → **s19**.
- `STORY-023` (récompenses) → **s20**.
- `STORY-024-028` (i18n, obs, a11y, notifications, docs) → **s21 à s26** (5 stories).

### Corrections issues de la review `docs/reviews/stories.md`

- **Critical (flashcards)** : s06b ajoutée pour livrer les flashcards (sinon drop silencieux du périmètre).
- **Major (comptes non-élève)** : s12b ajoutée pour créer des comptes `parent`/`admin` et mettre à jour un rôle. Sans cette story, s14, s15, s17 n'étaient pas testables. La chaîne de dépendances est maintenant : s12 → s12b → s13 → s14.
- **Major (endpoints évaluation)** : s18b ajoutée pour livrer `POST /evaluations/{id}/score-manual` et `POST /evaluations/{id}/reprocess`. Le fallback `manual_review_needed` de s18 a maintenant un chemin de remédiation.
- **Minor s22** : wording nettoyé (caractère chinois parasite supprimé).
- **Minor s20** : wording clarifié — l'exercice est fermé après 3 tentatives (pas de 4e soumission), chaque tentative est dans le ledger avec ses points (toujours 0 pour les échecs).
- **Minor s08** : ajout d'un AC vérifiant que `attempt_number > 3` retourne 409 (cohérence avec s20).
- **Minor s17** : complexité relevée de 2 à 3, risque explicité.
- **Minor s21** : complexité relevée de 2 à 3, risque explicité.
- **Minor s06** : référence PRD mise à jour (la question ouverte sur le niveau de détail des problèmes maths est dans la phase Research de cette story, plus une référence stale à STORY-016).

### Ordre d'exécution suggéré

Phase 1 (POC) : s01 → s02 → s03 → s04.
Phase 2 (MVP) : s05 → s06 → s06b → s07 → s08 → s09 → s10 → s11.
Phase 3 (Sécurité) : s12 → s12b → s13 → s14 → s15.
Phase 4 (Pédagogie) : s18 → s18b → s20 → s16 → s17 → s19. (s18 et s20 en premier car ils produisent les données que les dashboards affichent.)
Phase 5 (Finalisation) : s21 → s22 → s23 → s24 → s25 → s26.
