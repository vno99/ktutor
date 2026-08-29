# Review — s02-chatter-avec-mon-cours

> Revu par : sous-agent `reviewer` (contexte frais).
> Date : 2026-08-29
> Source : `git diff main...feature/s02-chatter-avec-mon-cours` vs `docs/plans/s02-chatter-avec-mon-cours.md` + `docs/research/s02-chatter-avec-mon-cours.md` + ADRs 001/002/003/004/005/006/008/009.
> Tests : **126 passés** (lancés par le reviewer, pas de confiance dans les résultats rapportés) — couverture **87,56%** (seuil 80%).
> Lint : `ruff check app tests` → **0 erreur**.
> Worktree : `C:\Workspace\ktutor\.worktrees\s02-chatter-avec-mon-cours` (branche `feature/s02-chatter-avec-mon-cours`).

## Verifications run

- `pytest --cov=app --cov-fail-under=80 -m "not integration"` — 126 tests passed, 87.56% coverage (well above 80%). Coverage on every s02 file is 100% (maths_agent, retriever, client).
- `ruff check app tests` — 0 errors.
- Read every diff hunk: `backend/.env.example`, `backend/app/cli.py`, `backend/app/core/config.py`, `backend/app/services/agents/__init__.py`, `backend/app/services/agents/maths_agent.py`, `backend/app/services/llm/{__init__,client}.py`, `backend/app/services/rag/retriever.py`, `backend/app/services/rag/upload_service.py`, all test files, `docs/architecture.md`.
- For every import / function call referenced by the new code I opened the target and confirmed it exists with the expected signature: `ChromaStore.get_collection` (chroma_store.py:63), `ChromaStore.list_collections_for_pseudo` (chroma_store.py:94), `validate_pseudo` (chroma_store.py:27), `EmbeddingProvider.embed_documents` (embeddings.py), `chat_models.BaseChatModel` and `AIMessage/HumanMessage/SystemMessage` (langchain_core), `build_llm_client` factory, `Settings` (config.py:10). All real.
- `git status` is clean on `feature/s02-chatter-avec-mon-cours`. Working tree was restored after every neutralization mutation, confirmed by `git diff --exit-code` returning 0.

## Plan → diff check (13 tasks)

All 13 plan tasks are present:
- Étape 0 (config + filename metadata) — done (`config.py` 6 new fields; `_to_chroma_dict` extended to take `filename`).
- Étape 1 (LLM client) — `services/llm/client.py` with `LlmClient` Protocol, `_LangChainChatWrapper`, `build_llm_client`.
- Étape 2 (Retriever) — `services/rag/retriever.py` with `RetrievedChunk`, `Retriever`. Multi-tenant invariant respected: only `query(subject, pseudo, question, k)`, no `collection_name` path.
- Étape 3 (Maths agent) — `services/agents/maths_agent.py` with `CITATION_FORMAT`, `SYSTEM_PROMPT`, `SourceCitation`, `ChatResult`, `MathsAgent`. `ask(subject, pseudo, question)` → `ChatResult`.
- Étape 4 (CLI chat) — `chat` command with `--pseudo`, `--subject`, `--question`, `--json`. Exit codes follow the documented matrix: 0 success / 1 generic / 5 invalid pseudo.
- Étape 5 (Doc) — `docs/architecture.md` updated (services/llm/ in the tree; LLM provider line in the table mentions OpenRouter).
- Étape 6 (Verification) — pytest, ruff, 80% coverage. All green.

## AC verification (7 ACs)

| AC | Test | Status |
|---|---|---|
| AC1 CLI returns grounded answer | `test_cli.py::TestChat::test_chat_returns_zero_with_answer` | green |
| AC2 Citation `[source: filename, chunk N]` | `test_maths_agent.py::TestCitationFormat::*` + `TestAskHappyPath::test_ask_returns_answer_citing_sources` | green |
| AC3 No-document fallback (no hallucination) | `test_maths_agent.py::TestAskEmpty::test_ask_with_empty_collection_returns_no_document_message` | green |
| AC4 LLM provider from env | `test_client.py::TestFactoryProvider::test_openai_returns_wrapper`, `test_minimax_routes_via_openrouter`, `test_ollama_raises_not_implemented` | green |
| AC5 CLI exit 0 | `test_cli.py::TestChat::test_chat_returns_zero_with_answer`, `test_chat_returns_zero_with_no_document` | green |
| AC6 Cross-tenant | `test_retriever.py::TestCrossTenant::test_query_cross_tenant_isolation` + `test_maths_agent.py::TestCrossTenant::test_cross_tenant_isolation_at_agent_level` | green |
| AC7 No document test | `test_retriever.py::TestQueryEmpty::test_query_with_empty_collection_returns_empty_list` | green |

## Run interdicts

- No `Conversation` / `Message` model added (diff is empty in `app/core/database/`).
- No streaming — `ask` returns a single `ChatResult`; CLI prints a single Panel.
- No LangGraph supervisor (no `supervisor.py`, no `langgraph` imports in `app/`).
- `ocr.py`, `embeddings.py`, `minio_client.py` untouched (`git diff` returns 0 lines).
- `ChromaStore`, `MinioClient` not renamed.
- ollama raises `NotImplementedError` (verified at runtime and locked by `test_ollama_raises_not_implemented`).
- Retriever signature is `query(subject, pseudo, question, k=4)` — never `collection_name`. `grep collection_name backend/app/services/rag/retriever.py` returns nothing.
- All work on `feature/s02-chatter-avec-mon-cours`; no commit on `main`.
- No new ADR (decisions absorbed into existing ADR 002/003/004).

## Anti-hallucination neutralization (4 mutations, all red, all restored)

I proved the central invariants bite. After each mutation I restored the file and confirmed `git diff --exit-code` is clean.

1. **Cross-tenant routing (AC6)** — Replaced `self._chroma.get_collection(subject, pseudo)` in `retriever.py:75` with a call through `list_collections_for_pseudo` + manual `get_or_create_collection`. Result: `test_query_uses_get_collection_not_list_collections` RED (1 test). Restored clean.
2. **Chunk injection into user prompt (no-hallucination)** — Removed the `for i, chunk in enumerate(chunks)` block in `maths_agent.py:124-129`. Result: `test_ask_injects_chunks_into_user_prompt` AND `test_cross_tenant_isolation_at_agent_level` RED (2 tests). Restored clean.
3. **Empty-collection fallback (AC3/AC7)** — Replaced `return ChatResult(answer=self._no_document_message, sources=[])` with `return ChatResult(answer="", sources=[])`. Result: `test_ask_with_empty_collection_returns_no_document_message` RED (1 test). Restored clean.
4. **Ollama NotImplementedError** — Made `build_llm_client` return a wrapper for `ollama` instead of raising. Result: `test_ollama_raises_not_implemented` RED (1 test). Restored clean.

The central invariants are real, not decorative. The cross-tenant test at the agent level is meaningful (it uses a real `Retriever` + real `EphemeralClient` + an EchoLlm that leaks the user prompt on cross-tenant data).

## Drift and deviations

- `_RetrieverLike` Protocol was placed only in `maths_agent.py:65-69` and removed from `retriever.py` (implementer said "per ruff"). The plan § Étape 2 asked for the Protocol in `retriever.py`. The agent still has the type to constrain its dependency on the retriever interface, so the contract is honored; the duplication is just relocated. This is **minor** — coverage and behavior are unaffected.
- `test_citation_format_locked` from the plan was split into 3 finer-grained tests (`test_citation_format_constant_matches_story`, `test_citation_regex_matches_real_citation`, `test_citation_regex_rejects_wrong_field`). Coverage is strictly stronger. **Minor**, in line with the implementer's report.
- The plan listed `test_temperature_zero_passed_to_llm` in `test_maths_agent.py`, but the invariant is instead locked at the config layer (`tests/core/test_config.py::test_default_chat_temperature_is_zero`) and the factory passes `settings.chat_temperature` to `ChatOpenAI(temperature=...)`. Behavior is right; the test lives at a different layer. **Minor**.
- "Réponds en français, en citant tes sources au format demandé." line added at `maths_agent.py:131` per implementer's deviation #3. The system prompt already says "Tu réponds en français" (point 4), so this is a redundant reinforcement. Harmless. **Minor**.
- `docs/architecture.md` got a small bonus edit: the LLM provider line in the integration table now mentions OpenRouter and the `services/llm/` directory is added to the tree. Both are accurate and consistent with the plan. No issue.
- `cli.py:11` still references `docs/designs/s01-uploader-document.md § Conventions` for exit codes — that doc path was not changed by s02 (the path is in s01 territory). Not a finding for s02.

## What I could NOT verify

- **No real LLM call.** The unit tests use `FakeListChatModel` and `_CapturingLlm`. The integration with OpenRouter / OpenAI is best-effort and explicitly out of scope per the plan. I cannot confirm that `minimax/minimax-m3:free` on OpenRouter still exists or that the API key plumbing works end-to-end. A human must run `python -m ktutor.cli upload ...` then `python -m ktutor.cli chat --pseudo ...` to actually validate a live response and a live citation. The plan's "Vérification manuelle" checklist is honest about this.
- **No browser/UI.** s02 is CLI/backend only; no UI was touched.
- **No multi-tenant via real JWT.** The CLI accepts `--pseudo` directly (no auth layer yet — s12). The retriever's pseudo-isolation test only exercises `(subject, pseudo)`; a JWT-injected pseudo is a downstream story. The plan acknowledged this is a placeholder.
- **The "Réponds en français" line in `_build_user_prompt`** is not asserted by any test. The system prompt alone enforces language. The line is dead weight from a coverage standpoint but is harmless.

## Findings

- **None critical.**
- **None major.**
- **Minor 1**: `_RetrieverLike` Protocol lives in `maths_agent.py` rather than `retriever.py` (plan drift; coverage and contract still hold).
- **Minor 2**: `test_temperature_zero_passed_to_llm` from the plan's test list was not added at the agent layer; the invariant is covered at the config layer only. The factory still passes `settings.chat_temperature` to `ChatOpenAI` — not directly tested.
- **Minor 3**: A redundant "Réponds en français, en citant tes sources au format demandé." line in `_build_user_prompt` (already enforced by the system prompt) — not asserted by any test, harmless.

The diff is clean, the tests are meaningful, the multi-tenant invariant is real and provably protected, the system prompt forbids general knowledge, citations are locked by a regex, and the ollama provider raises `NotImplementedError` as required. Run interdicts are respected. Three plan-level deviations are minor cosmetic/test-renaming, none break the story.

Max severity: minor
Ship allowed: yes
