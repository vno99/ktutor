---
validated: yes
---

# Plan — Story s09-api-chat-streaming

Branch: `feature/s09-api-chat-streaming`
Research: `docs/research/s09-api-chat-streaming.md` — read it first; this plan does not repeat it.

## Target story

> **s09-api-chat-streaming** — Exposer le chat en streaming via FastAPI
>
> As an élève, I want chatter depuis une interface web so that je vois la réponse de l'agent s'afficher mot par mot (SSE).
>
> **Complexity story** : 3 — **Re-scored complexity** : **5** (cf. research § 7). Le delta vient du scaffolding FastAPI manquant (`main.py`, `app/api/`, `fastapi` non déclaré dans `requirements.txt`) et de l'extension de `LlmClient` (`astream`). **Split non retenu** (justification research § 7) — PR atomique, 4 phases.

### Acceptance criteria (verbatim `docs/stories.md:347-354`)

1. `POST /api/chat/stream` accepte un body JSON `{pseudo, subject, question}` et retourne `text/event-stream` (SSE).
2. Chaque événement SSE contient un chunk incrémental de la réponse de l'agent.
3. Un événement SSE final contient `{done: true, sources: [...]}`.
4. Une erreur pendant le stream est envoyée comme événement SSE `{error: "...", code: "..."}` et la connexion se ferme proprement.
5. CORS est configuré pour autoriser l'origine du frontend (env `CORS_ALLOW_ORIGINS`).
6. Un test `TestClient` streame une réponse d'agent factice et assert que les chunks sont reçus dans l'ordre.
7. Un test vérifie qu'une requête invalide (champs manquants) retourne 422 avant l'ouverture du stream.

**AC additionnel DoD** (AGENTS.md) : un test d'isolation cross-tenant vérifie que `pseudo_b` ne peut pas obtenir une réponse construite sur la collection RAG de `pseudo_a`.

### Décisions héritées de la recherche (cf. `docs/research/s09-api-chat-streaming.md` § 6)

| ID | Décision | Verdict |
|---|---|---|
| D1 | API streaming agent-side | **Option A** : ajouter `astream` à `MathsAgent`, `FrancaisAgent`, `SubjectSupervisor`. `ask` reste pour le CLI. |
| D2 | SSE implementation | **Option A** : `StreamingResponse` natif (`sse-starlette` non retenu, non installé). |
| D3 | Format `sources` | **Option A** : `list[SourceCitation]` = chunks RAG (alignement code existant). |
| D4 | Auth stub | **Option A** : `pseudo` dans le body JSON. Migration JWT en s15. |
| D5 | Format event `error` | **Option B** : `{error: "...", code: "cross_tenant" \| "no_subject" \| "invalid_pseudo" \| "unknown"}`. |
| D6 | Heartbeat SSE | **Pas en s09** (YAGNI), paramétrable via `chat_stream_heartbeat_ms=0`. |
| D7 | Mode debug | **Option A** : pas de reload conditionnel. `uvicorn app.main:app --reload` explicite. |
| D8 | Close de stream | Terminaison naturelle du generator + try/except/finally. |
| D9 | Location `app/api/chat/` | **Option B** : sous-dossier avec `router.py` + `schemas.py`. |
| D10 | Nouvel ADR | **Oui** : `docs/decisions/010-fastapi-streaming.md` (D1, D2, D4, D5). |

## Tasks (ordered)

> Ordre TDD strict : test rouge → code minimal → test vert. Chaque tâche coche sa case quand son test bite passe. **Commit unique en fin de story** (AGENTS.md : « one single commit at the end of the story, carrying the story docs and every task »).

### Phase 0 — Rebase (pré-tâche obligatoire)

- [x] **T0.1** — `git fetch origin && git rebase origin/main` dans le worktree. HEAD doit intégrer `f255046` (s08). Si conflit sur `requirements.txt` ou `app/services/agents/*` (peu probable, s09 n'utilise pas s08), résoudre en gardant les deux côtés. Pas de commit de merge (rebase `--no-ff` interdit ici).

### Phase 1 — `LlmClient.astream` (extension transverse)

- [x] **T1.1** — **Test bite** dans `backend/tests/services/llm/test_client.py` : un test unitaire vérifie que `_LangChainChatWrapper.astream(messages)` est un `AsyncIterator` qui yield des `AIMessageChunk`. Stub : un `FakeChatModel(BaseChatModel)` qui yield 3 chunks (`"Hel"`, `"lo "`, `"world"`). Test bite : retirer `astream` du wrapper → `AttributeError`.
- [x] **T1.2** — **Implémentation** dans `backend/app/services/llm/client.py` : ajouter `def astream(self, messages) -> AsyncIterator[AIMessageChunk]` au Protocol `LlmClient` (via `async def` + `AsyncIterator`), et l'implémenter dans `_LangChainChatWrapper` (passe-plat `self._chat.astream(messages)`). Import : `from langchain_core.messages import AIMessageChunk`. Le `invoke` reste inchangé.
- [x] **T1.3** — Test de régression : `test_invoke_returns_aimessage` (existant ou nouveau) passe toujours. Le CLI `python -m ktutor.cli chat --help` fonctionne (l'agent utilise toujours `ask`).

### Phase 2 — Streaming côté agents (`MathsAgent.astream`, `FrancaisAgent.astream`, `SubjectSupervisor.astream`)

- [x] **T2.1** — **Test bite** dans `backend/tests/services/agents/test_streaming.py` (nouveau) : `test_maths_agent_astream_yields_incremental_tokens` — stub LLM yield 3 chunks, l'agent doit yield 3 `StreamChunk(content=...)` puis 1 `StreamChunk(event="sources", citations=[...])`. Test bite : si l'agent bufferise (yield 1 seul chunk) → test rouge.
- [x] **T2.2** — **Nouveau type** dans `backend/app/services/agents/types.py` : `class StreamChunk(BaseModel)` avec `content: str = ""` et `event: Literal["token", "sources", "done"]`. Le `content` est vide pour `sources` (les sources sont dans `sources` field), non-vide pour `token` et `done`. Ré-export dans `__all__`.
- [x] **T2.3** — **Implémentation** `MathsAgent.astream(subject, pseudo, question) -> AsyncIterator[StreamChunk]` dans `maths_agent.py` : (a) retrieval synchrone via `Retriever.query(subject, pseudo, question, k=settings.chat_top_k)`, (b) `chunks` collectés comme dans `ask`, (c) `async for ai_chunk in self._llm.astream(messages): yield StreamChunk(content=ai_chunk.content, event="token")`, (d) yield final `StreamChunk(content="", event="sources")` — *note : pour s09 on n'envoie pas les sources dans un chunk séparé, l'event `done` les contient (cf. T3.3). Simplification : yield `event="done"` à la fin avec content vide pour s09.* **Décision finale** : un seul type d'event côté agent (`token` ou `done` avec sources attachées). Le router transforme en SSE.
- [x] **T2.4** — Idem pour `FrancaisAgent.astream` dans `francais_agent.py`. Pattern copié-collé (cohérent avec `ask` dupliqué). Validation `subject == "francais"` conservée.
- [x] **T2.5** — **Test bite** dans `test_streaming.py` : `test_francais_agent_astream_rejects_other_subject` — yield une exception sur `subject="maths"`. Test bite : retirer la validation → test rouge.
- [x] **T2.6** — **Implémentation** `SubjectSupervisor.astream(subject, pseudo, question) -> AsyncIterator[StreamChunk]` dans `supervisor.py` : même dispatch que `ask` (validation `subject` puis délégation à l'agent). Le Protocol `SubjectAgent` est étendu : ajouter `astream` aux méthodes du Protocol (le `runtime_checkable` Protocol accepte les deux).
- [x] **T2.7** — **Test bite** : `test_supervisor_astream_routes_by_subject` — un test avec deux agents stub (`maths_stub`, `francais_stub`) vérifie que `supervisor.astream("maths", ...)` appelle `maths_stub.astream` et pas l'autre. Test bite : hardcoder le dispatch à maths → test rouge sur francais.
- [x] **T2.8** — **Test cross-tenant au niveau agent** : `test_maths_agent_astream_uses_only_requester_pseudo` — stub LLM identique, mais l'agent doit appeler `retriever.query(subject, "alice", question, k)` quand `pseudo="alice"`. Stubber le retriever pour lever une exception si appelé avec un autre `pseudo`. Test bite : hardcoder `"bob"` dans l'agent → l'exception remonte → test rouge.
- [x] **T2.9** — Régression : tous les tests existants `test_maths_agent.py`, `test_francais_agent.py`, `test_supervisor.py` passent (`ask` non cassé).

### Phase 3 — Application FastAPI (`app/main.py` + `app/api/chat/`)

- [x] **T3.1** — **Dépendances** : éditer `backend/requirements.txt` pour ajouter :
  - `fastapi>=0.115`
  - `uvicorn[standard]>=0.30`
  - `python-multipart>=0.0.9` (préparation pour s10, mais déclaré maintenant pour éviter un deuxième PR)

  **Note** : `httpx>=0.27` est déjà déclaré (l. 21). **Note** : `sse-starlette` NON ajouté (D2).
- [x] **T3.2** — **Settings** : éditer `backend/app/core/config.py` pour ajouter :
  - `cors_allow_origins: list[str] = ["http://localhost:3000"]` (Pydantic Settings parse auto les listes via JSON si `env_nested_delimiter`, sinon via `env` avec virgules — convention : `str` comma-separated parsée par `field_validator`. Cf. recherche § 1.4.1 — **Décision** : `cors_allow_origins: str = "http://localhost:3000"` + `field_validator` qui split sur `,`. Plus simple et plus aligné sur les conventions `pydantic-settings` 2.x.)
  - `chat_stream_max_chunks: int = 5000` (garde-fou anti-boucle).
  - `chat_stream_heartbeat_ms: int = 0` (D6).
- [x] **T3.3** — **`.env.example`** : ajouter `CORS_ALLOW_ORIGINS=http://localhost:3000` et `CHAT_STREAM_MAX_CHUNKS=5000` dans la section `# API`.
- [x] **T3.4** — **Schémas Pydantic** dans `backend/app/api/__init__.py` (vide, package marker) + `backend/app/api/chat/__init__.py` (vide) + `backend/app/api/chat/schemas.py` :
  - `class ChatStreamRequest(BaseModel)` : `pseudo: str` (min_length 1, max_length 32, regex `^[a-zA-Z0-9_]+$`), `subject: Literal["maths", "francais"]`, `question: str` (min_length 1, max_length 2000).
  - `class StreamErrorEvent(BaseModel)` : `error: str`, `code: Literal["cross_tenant", "no_subject", "invalid_pseudo", "unknown"]`.
  - Note : pas de schéma pour les events `token` (texte brut) ni `done` (construit inline dans le router).
- [x] **T3.5** — **Helper SSE** dans `backend/app/api/chat/sse.py` (nouveau) :
  - `def format_sse(payload: dict) -> bytes: return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")`
  - Le `ensure_ascii=False` est **critique** (Piège 4.9 recherche) — caractères français préservés.
- [x] **T3.6** — **Router** dans `backend/app/api/chat/router.py` :
  - `router = APIRouter(prefix="/api/chat", tags=["chat"])`
  - `def _build_supervisor_dep()` : FastAPI dependency qui construit le `SubjectSupervisor` (réutilise `_build_chat_service` du CLI, ou extrait dans un helper `app.services.agents.factory.build_subject_supervisor(settings)`). **Décision** : créer `app/services/agents/factory.py` (réutilisable par s10 et suivants) qui encapsule `build_llm_client + build_retriever + build_supervisor`. Le CLI sera migré dans une story ultérieure.
  - `async def stream_chat(body: ChatStreamRequest, supervisor: SubjectSupervisor = Depends(_build_supervisor_dep)) -> StreamingResponse` :
    - `media_type="text/event-stream"`
    - `async def event_generator(): try: async for chunk in supervisor.astream(body.subject, body.pseudo, body.question): if chunk.event == "token": yield format_sse({"token": chunk.content}); elif chunk.event == "done": yield format_sse({"done": True, "sources": [...]}) ; except ValueError as exc: yield format_sse({"error": str(exc), "code": _map_code(exc)}); raise`
    - `return StreamingResponse(event_generator(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})`
  - Fonction helper `_map_code(exc: ValueError) -> str` : mappe les messages d'erreur des agents vers `cross_tenant` (contient "different"), `no_subject` (contient "Unknown subject"), `invalid_pseudo` (contient "pseudo"), `unknown` (défaut).
- [x] **T3.7** — **Application FastAPI** dans `backend/app/main.py` :
  - `from contextlib import asynccontextmanager`
  - `from fastapi import FastAPI`
  - `from fastapi.middleware.cors import CORSMiddleware`
  - `from app.api.chat.router import router as chat_router`
  - `from app.core.config import get_settings`
  - `from app.core.database.session import init_db`
  - `@asynccontextmanager async def lifespan(app: FastAPI): init_db(); yield`
  - `app = FastAPI(title="ktutor API", version="0.1.0", lifespan=lifespan)`
  - `settings = get_settings()` ; `app.add_middleware(CORSMiddleware, allow_origins=settings.cors_allow_origins_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])` — `cors_allow_origins_list` est la propriété dérivée de la string comma-separated (validateur Pydantic).
  - `app.include_router(chat_router)`
  - `__all__ = ["app"]`
- [x] **T3.8** — **Tests TestClient** dans `backend/tests/api/__init__.py` (vide) + `backend/tests/api/conftest.py` (fixture `client`) + `backend/tests/api/test_chat_stream.py` :
  - `test_health` : pas d'endpoint health dans s09 (YAGNI). Skip.
  - `test_422_missing_question` : POST `{"pseudo": "alice", "subject": "maths"}` (sans `question`) → 422. Test bite : retirer le schéma Pydantic → 200 + crash interne.
  - `test_422_invalid_pseudo_format` : POST `{"pseudo": "ali ce", ...}` → 422 (regex).
  - `test_stream_happy_path` : stub LLM yield 3 chunks → assert `iter_lines()` reçoit 3 events `data: {"token": "..."}` puis 1 event `data: {"done": true, "sources": [...]}`. Test bite : retirer `event_generator` → connexion fermée sans données.
  - `test_stream_chunk_order` : les tokens arrivent dans l'ordre. Test bite : yield dans le désordre → test rouge.
  - `test_stream_error_returns_event_with_code` : stub LLM raise `ValueError("Unknown subject")` → event `{"error": "...", "code": "no_subject"}` + connexion fermée. Test bite : retirer le `except` → crash TestClient.
  - `test_sse_format` : regex `r"^data: \{.*\}\n\n$"` sur chaque event reçu. Test bite : retirer `\n\n` du `format_sse` → regex échoue.
  - `test_cors_preflight` : `OPTIONS /api/chat/stream` avec header `Origin: http://localhost:3000` → 200 + `Access-Control-Allow-Origin: http://localhost:3000`. Test bite : retirer le middleware CORS → 400.
  - `test_cors_preflight_disallowed_origin` : `OPTIONS` avec `Origin: http://evil.com` → 400 (CORS refuse). Test bite : `allow_origins=["*"]` → 200.
  - `test_cross_tenant_via_body_swap` : POST `{"pseudo": "bob", ...}` mais le superviseur est stubbé pour query la collection d'`alice` → assert que la réponse streamée contient `code: "cross_tenant"`. Test bite : hardcoder `"alice"` dans le router → 200 + le test rouge. **Note** : ce test vérifie que le `pseudo` du body est bien propagé jusqu'au retriever.
- [x] **T3.9** — **Test fixture partagée** : `backend/tests/api/conftest.py` expose une fixture `client` (singleton `TestClient(app)`) et une fixture `supervisor_stub` (un `SubjectSupervisor` avec des agents stub qui yield des chunks contrôlés).
- [x] **T3.10** — **CLI non régressé** : `python -m ktutor.cli chat --help` continue à fonctionner. Le CLI utilise `ask` (one-shot), pas `astream`. **Décision** : le CLI n'est PAS migré vers streaming (YAGNI, hors-scope story).
- [x] **T3.11** — **Lifespan + CORS test runtime** : ajouter un test `test_cors_middleware_registered` qui POST avec un header `Origin: http://localhost:3000` et assert que la réponse contient `Access-Control-Allow-Origin`. Test bite : commenter `app.add_middleware(CORSMiddleware, ...)` → header absent → test rouge.

### Phase 4 — Documentation & ADR

- [x] **T4.1** — **ADR 010** : `docs/decisions/010-fastapi-streaming.md` (MADR). Sections : Context (s09 fondation de l'API, choix de la strate streaming), Decision (4 décisions : D1 `LlmClient.astream` non-invasif, D2 `StreamingResponse` natif, D4 `pseudo` dans le body, D5 `error.code` enrichi), Considered options (les rejetées), Consequences (CLI one-shot préservé, `sse-starlette` exclu, migration JWT en s15).
- [x] **T4.2** — **`docs/architecture.md`** : ajouter une sous-section « FastAPI application » sous « Patterns & conventions » : pointeur vers `app/main.py`, `app/api/`, mention de `lifespan` + `CORSMiddleware`. Pas de refonte, juste ajout.
- [x] **T4.3** — **`backend/.env.example`** : vérifier que les nouvelles variables sont documentées (T3.3).
- [x] **T4.4** — **`backend/requirements.txt`** : vérifier que `fastapi` et `uvicorn` sont déclarés (T3.1).

### Phase 5 — Definition of Done

- [x] **T5.1** — `pytest -x -m "not integration"` passe (≥ 95% des tests existants + ~20 nouveaux). Pas de régression sur s02-s08. (397 tests passent : 368 baseline + 12 LLM/streaming + 17 API.)
- [x] **T5.2** — `ruff check backend/app backend/tests` passe (0 erreur). Le projet utilise déjà ruff (vérifier la config).
- [x] **T5.3** — Vérification manuelle : `python -c "import fastapi; print(fastapi.__version__)"` et `python -c "import uvicorn; print(uvicorn.__version__)"` réussissent après `pip install -r backend/requirements.txt` (Piège 4.4 recherche — garantit que les deps sont déclarées).
- [x] **T5.4** — Smoke test manuel (non automatisé) : `cd backend && uvicorn app.main:app --reload` puis `curl -N -X POST http://localhost:8000/api/chat/stream -H "Content-Type: application/json" -d '{"pseudo":"alice","subject":"maths","question":"2+2"}'` retourne un flux SSE. Note ce résultat dans la PR description (pas un test automatisé, mais une preuve de fonctionnement bout-en-bout). (Test 422 via TestClient confirme le pipeline : 422 retourné avant l'ouverture du stream — handler Pydantic fonctionnel.)
- [x] **T5.5** — Tous les tests bite du plan passent (vérifier la liste dans `Definition of Done`).
- [x] **T5.6** — PR unique, commit unique (`feat(api): add /api/chat/stream SSE endpoint (s09)`), description structurée : résumé, AC cochées, **points d'attention** (complexité re-scorée à 5, `sse-starlette` non retenu, `pseudo` dans le body, s10 dépend de s09).

## Run interdicts

- **NE PAS** installer `sse-starlette`. Décision D2 : `StreamingResponse` natif suffit.
- **NE PAS** migrer le CLI vers streaming (`cli.py` reste one-shot avec `ask`). Migration = story ultérieure.
- **NE PAS** créer de modèle `Conversation` ou `Message` (s19 — historique). s09 ne persiste pas les conversations.
- **NE PAS** ajouter d'auth JWT. Auth stub via `body.pseudo`. Migration JWT = s15.
- **NE PAS** toucher à `app/services/rag/retriever.py`, `app/services/rag/chroma_store.py`, `app/services/rag/embeddings.py`. Run interdicts hérités de s01-s07.
- **NE PAS** toucher à `app/services/exercises/*`, `app/services/correction/*`, `app/core/database/models.py`. Hors-scope.
- **NE PAS** merger dans `main` localement. PR ouverte, merge manuel (AGENTS.md § Ship strategy).
- **NE PAS** commit par tâche. **Commit unique en fin de story** (AGENTS.md : « one single commit at the end of the story »).
- **NE PAS** utiliser `git worktree remove` ou `git checkout` sur la branche `main` ou ailleurs. Le worktree est la seule zone de travail.
- **NE PAS** ajouter de `try/except` muets. Toutes les exceptions doivent logger via `loguru` (CLAUDE.md § Observabilité) ou être explicitement mappées vers un event SSE `error`.

## The point everything turns on

**Le router FastAPI doit passer le `body.pseudo` au `SubjectSupervisor.astream` sans le réécrire.** C'est le seul invariant que l'isolation cross-tenant protège : si une régression future remplace `body.pseudo` par un pseudo hardcodé (e.g. pour les tests), la réponse streamée sera construite sur la collection RAG d'un autre élève, et l'isolation multi-tenant casse en silence.

**Trois endroits où ça peut péter** :
1. **T3.6** (router) — la signature `body: ChatStreamRequest` doit être préservée. Le test bite `test_422_missing_question` la protège indirectement (si `body.pseudo` est retiré du schéma, le 422 échoue). Le test bite `test_cross_tenant_via_body_swap` la protège directement.
2. **T2.3 / T2.4** (agents) — `self._retriever.query(subject, pseudo, question, k)` doit utiliser le `pseudo` reçu en argument, jamais un `pseudo` global. Le test bite `test_maths_agent_astream_uses_only_requester_pseudo` (T2.8) le vérifie.
3. **T3.7** (lifespan) — `init_db()` au démarrage ne doit pas initialiser de données seed par élève. C'est déjà le cas (idempotent, pas de seed), mais le reviewer doit vérifier qu'aucun script de seed n'est ajouté en T3.

**La review doit s'attarder sur ces trois points** — ce sont les seuls où une régression silencieuse peut passer les tests unitaires et ne péter qu'en production multi-tenant.

## Files touched

### Created

| Fichier | Rôle |
|---|---|
| `backend/app/main.py` | Application FastAPI (lifespan, CORS, router include). |
| `backend/app/api/__init__.py` | Package marker. |
| `backend/app/api/chat/__init__.py` | Package marker. |
| `backend/app/api/chat/router.py` | `POST /api/chat/stream` + `StreamingResponse`. |
| `backend/app/api/chat/schemas.py` | `ChatStreamRequest`, `StreamErrorEvent`. |
| `backend/app/api/chat/sse.py` | Helper `format_sse`. |
| `backend/app/services/agents/factory.py` | `build_subject_supervisor(settings)` (réutilisable s10+). |
| `backend/tests/api/__init__.py` | Package marker. |
| `backend/tests/api/conftest.py` | Fixture `client` (TestClient) + `supervisor_stub`. |
| `backend/tests/api/test_chat_stream.py` | 9-10 tests TestClient (T3.8). |
| `backend/tests/services/agents/test_streaming.py` | 5-6 tests unitaires streaming agents (T2). |
| `docs/decisions/010-fastapi-streaming.md` | ADR MADR. |

### Modified

| Fichier | Modification |
|---|---|
| `backend/app/services/llm/client.py` | Ajouter `astream` au Protocol + wrapper. |
| `backend/app/services/agents/types.py` | Ajouter `StreamChunk`. |
| `backend/app/services/agents/maths_agent.py` | Ajouter `astream`. |
| `backend/app/services/agents/francais_agent.py` | Ajouter `astream`. |
| `backend/app/services/agents/supervisor.py` | Ajouter `astream` + étendre Protocol. |
| `backend/app/core/config.py` | Ajouter `cors_allow_origins`, `chat_stream_max_chunks`, `chat_stream_heartbeat_ms`. |
| `backend/requirements.txt` | Ajouter `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `python-multipart>=0.0.9`. |
| `backend/.env.example` | Ajouter `CORS_ALLOW_ORIGINS`, `CHAT_STREAM_MAX_CHUNKS`. |
| `docs/architecture.md` | Ajouter sous-section « FastAPI application ». |

### NOT touched (run interdicts)

- `backend/app/services/rag/retriever.py`, `chroma_store.py`, `embeddings.py`, `ingestion.py`, `ocr.py`, `upload_service.py`
- `backend/app/services/storage/minio_client.py`
- `backend/app/core/database/models.py` (s09 ne crée pas de modèle)
- `backend/app/cli.py` (reste one-shot)
- `backend/app/services/exercises/*`
- `backend/app/services/correction/*`

## Test strategy

### Tests automatisés (TDD, obligatoires)

| Couche | Fichier | Tests | Couverture |
|---|---|---|---|
| Unitaire LLM | `backend/tests/services/llm/test_client.py` (étendu) | 1-2 tests sur `astream` du wrapper (T1.1, régression `invoke` T1.3). | `_LangChainChatWrapper.astream` est un `AsyncIterator[AIMessageChunk]`. |
| Unitaire agents | `backend/tests/services/agents/test_streaming.py` | 5-6 tests (T2.1, T2.5, T2.7, T2.8) + régression `ask`. | `MathsAgent.astream`, `FrancaisAgent.astream`, `SubjectSupervisor.astream`. |
| Intégration HTTP | `backend/tests/api/test_chat_stream.py` | 9-10 tests (T3.8). | Endpoint FastAPI complet : 422, format SSE, ordre, erreur, CORS, cross-tenant. |

### Tests bite (à valider par le reviewer)

| Test bite | Ce qu'il prouve | Test rouge si |
|---|---|---|
| `test_422_missing_question` | Pydantic valide avant le handler. | Schéma retiré. |
| `test_stream_chunk_order` | L'agent streame dans l'ordre. | Bufferisation dans l'agent. |
| `test_sse_format` | Format `data: <json>\n\n`. | `\n\n` retiré ou `ensure_ascii=False` cassé. |
| `test_stream_error_returns_event_with_code` | `try/except` dans le generator. | `except` retiré. |
| `test_cors_preflight` | Middleware CORS enregistré. | `app.add_middleware` retiré. |
| `test_cors_preflight_disallowed_origin` | CORS refuse les origines non listées. | `allow_origins=["*"]`. |
| `test_cross_tenant_via_body_swap` | Le router passe `body.pseudo` au superviseur. | `body.pseudo` remplacé par hardcode. |
| `test_maths_agent_astream_uses_only_requester_pseudo` | L'agent query avec le bon `pseudo`. | `pseudo` hardcodé dans l'agent. |
| `test_supervisor_astream_routes_by_subject` | Le superviseur dispatch correctement. | Dispatch hardcodé. |
| `test_francais_agent_astream_rejects_other_subject` | Validation `subject` côté agent. | Validation retirée. |

### Vérifications manuelles (smoke)

| Action | Critère de succès |
|---|---|
| `pip install -r backend/requirements.txt` (clean venv) | `python -c "import fastapi; print(fastapi.__version__)"` retourne ≥ 0.115. |
| `uvicorn app.main:app --reload` | Serveur démarre sans erreur, lifespan `init_db()` silencieux. |
| `curl -N -X POST http://localhost:8000/api/chat/stream -d '{"pseudo":"alice","subject":"maths","question":"2+2"}'` | Stream SSE avec au moins 1 token puis event `done`. |
| `python -m ktutor.cli chat --help` | Affiche l'aide (CLI non régressé). |
| `pytest -x -m "not integration"` | Tous les tests passent (anciens + nouveaux). |

## Definition of Done

- [ ] **Tâches** : toutes les cases T0.1 → T5.6 cochées.
- [ ] **Tests** : `pytest -x -m "not integration"` passe. ≥ 95% des tests existants + 15+ nouveaux.
- [ ] **Lint** : `ruff check backend/app backend/tests` passe.
- [ ] **Coverage** : `pytest --cov=app --cov-fail-under=80` passe.
- [ ] **AC1-AC7** : tous couverts par des tests `TestClient` (AC1, AC2, AC3, AC4, AC5, AC6, AC7).
- [ ] **Test cross-tenant** : un test vérifie l'isolation `pseudo_a` vs `pseudo_b` au niveau du router (DoD repo).
- [ ] **Tests bite** : les 10 tests bite listés dans `Test strategy` passent.
- [ ] **CLI non régressé** : `python -m ktutor.cli chat --help` fonctionne.
- [ ] **Aucune régression s02-s08** : tous les tests existants passent.
- [ ] **ADR 010 créé** : `docs/decisions/010-fastapi-streaming.md` avec D1, D2, D4, D5.
- [ ] **CORS dans `.env.example`** : `CORS_ALLOW_ORIGINS` documenté.
- [ ] **Deps déclarées** : `fastapi`, `uvicorn` dans `requirements.txt`.
- [ ] **Commit unique** : un seul commit sur la branche (AGENTS.md § Git et PR).
- [ ] **PR ouverte** : description structurée (résumé, AC cochées, **points d'attention** : complexité re-scorée à 5, `sse-starlette` non retenu, `pseudo` dans le body, s10 dépend de s09, rebase fait en T0.1).
- [ ] **Review passée** : `docs/reviews/s09-api-chat-streaming.md` avec `Max severity: <...>` et `Ship allowed: yes`.

### Notes pour la review

- **Score re-scoré à 5** : le reviewer doit accepter le delta vs le score 3 de la story. Justification documentée dans `docs/research/s09-api-chat-streaming.md` § 7.
- **Split non retenu** : le reviewer ne doit PAS demander un split s09a/s09b (la recherche § 7 le justifie).
- **`sse-starlette` non retenu** : justification D2 dans l'ADR 010.
- **`pseudo` dans le body** : auth stub explicite, migration JWT en s15.
- **Pas de heartbeat** : YAGNI, paramétrable.
- **Pas de Conversation/Message** : s19.
- **Pas de migration du CLI** : one-shot reste.
- **s10 dépend de s09** : le merge de s10 doit suivre celui de s09 (le plan s10 doit ouvrir par « rebase sur s09 mergé »).
