---
name: research-s09-api-chat-streaming
description: s09-api-chat-streaming — recherche de contexte pour /ks-plan
metadata:
  type: project
  story: s09-api-chat-streaming
---

# Research — Story s09-api-chat-streaming

> Recherche en français. Code identifiers (snake_case, PascalCase, etc.) dans leur forme d'origine. Diacritiques respectés.

## 1. Story isolation

### 1.1 Rappel de la story

Source : `docs/stories.md` (lignes 338-372, Phase 2 — MVP).

**As an** élève **I want** chatter depuis une interface web **so that** je vois la réponse de l'agent s'afficher mot par mot (SSE).

**Complexity** : 3 (FastAPI SSE + LangChain streaming + CORS + auth-stub).

### 1.2 Acceptance criteria (7 ACs, verbatim depuis `docs/stories.md:347-354`)

1. L'endpoint `POST /api/chat/stream` accepte un body JSON `{pseudo, subject, question}` et retourne une réponse `text/event-stream` (SSE).
2. Chaque événement SSE contient un chunk de la réponse de l'agent (texte incrémental).
3. Un événement SSE final contient `{done: true, sources: [...]}`.
4. Une erreur pendant le stream est envoyée comme événement SSE `{error: "..."}` et la connexion se ferme proprement.
5. CORS est configuré pour autoriser l'origine du frontend (depuis `NEXT_PUBLIC_API_URL`).
6. Un test avec `TestClient` de FastAPI streame une réponse d'agent factice et assert que les chunks sont reçus dans l'ordre.
7. Un test vérifie qu'une requête invalide (champs manquants) retourne 422 avant l'ouverture du stream.

### 1.3 Dépendances déclarées par la story

- **s02** (chat logic exists) : `MathsAgent`, `LlmClient`, `Retriever`, `ChromaStore` — **livré** sur main (squash `81d8162`, PR #3).
- **s05** (supervisor with multiple agents) : `FrancaisAgent`, `SubjectSupervisor` — **livré** sur main (squash `c8c9617`, PR #6).

### 1.4 Dépendances NON déclarées mais réelles (vérifiées par ouverture du code)

| Élément manquant | Constat |
|---|---|
| `backend/app/main.py` (entrée FastAPI) | **N'existe pas**. Aucun fichier `main.py` dans `backend/app/`. |
| `backend/app/api/` (sous-dossiers d'endpoints) | **N'existe pas**. Aucun sous-dossier `api/`. |
| `fastapi` dans `requirements.txt` | **Absent**. Vérifié ligne par ligne (40 lignes, aucun `fastapi`, `uvicorn`, `sse-starlette`, `starlette`). |
| `fastapi.responses.StreamingResponse` (utilisé pour SSE) | `fastapi 0.141.1` est **physiquement installé** (`C:\Apps\anaconda3\envs\ktutor\Lib\site-packages\fastapi\`) — probablement via une dépendance transitive (FastAPI dépend de `starlette`, lui-même tiré par `langchain-openai` ou autre). Mais ce n'est **pas déclaré** dans `requirements.txt` et le reviewer CI/QA le marquera comme un trou. |
| `sse-starlette` (wrapper SSE idiomatique) | **PAS installé**. Import `from sse_starlette.sse import EventSourceResponse` → `ModuleNotFoundError`. Le pipeline SSE devra utiliser le `StreamingResponse` natif de FastAPI. |
| `LlmClient.stream` / `astream` | **N'existe PAS**. Le `LlmClient` Protocol (`client.py:27-34`) n'a qu'une méthode `invoke(messages) -> AIMessage`. Le `SubjectAgent` Protocol (`supervisor.py:25-34`) attend `ask(subject, pseudo, question) -> ChatResult`. Le wrapper `_LangChainChatWrapper` ne fait que `chat.invoke(messages)`. **Aucun chemin de streaming n'est câblé.** |
| `SubjectAgent` pour streaming (multi-events) | N'existe pas. Le retour actuel est `ChatResult(answer: str, sources: list[SourceCitation])` — un objet one-shot. Le streaming token-par-token demandera un nouveau contrat (générateur async). |

### 1.5 Prémisse clé de la story : un **biais d'omission**

La story est scorée 3 « FastAPI SSE + LangChain streaming + CORS + auth-stub ». **Cette description suppose que la stack FastAPI est déjà en place**. Or, à HEAD `473181c` (= main local sur ce worktree), **aucune infrastructure FastAPI n'existe** :

- Pas de `main.py`.
- Pas de `app/api/` package.
- Pas de `fastapi` dans `requirements.txt`.
- Pas de CORS middleware.
- Pas de `LlmClient.stream`/`astream`.
- Pas de `SubjectAgent` retournant un générateur.
- Pas de schéma Pydantic pour le body SSE (`ChatStreamRequest`).

Le `s09` est en réalité la **première story API**. Toutes les stories post-s09 (s10 upload, s12 auth, s14 RBAC, s15 multi-tenant middleware) en dépendront.

## 2. Files involved and current state

### 2.1 Fichiers existants à réutiliser (modulo adaptation pour streaming)

| Fichier | État actuel | Réutilisable tel quel pour s09 ? |
|---|---|---|
| `backend/app/services/agents/maths_agent.py` | `MathsAgent.ask(subject, pseudo, question) -> ChatResult` one-shot via `self._llm.invoke(messages)`. `SYSTEM_PROMPT` + `_build_user_prompt` + `_collect_sources` partagés avec `francais_agent.py`. | **Partiellement**. Le pipeline de retrieval (chunks → user prompt) est réutilisable. Mais le `llm.invoke` doit être remplacé par `llm.astream` (ou équivalent) pour avoir des tokens. |
| `backend/app/services/agents/francais_agent.py` | Clone de `MathsAgent` avec `SYSTEM_PROMPT` français et validation `subject == "francais"`. | **Idem**. |
| `backend/app/services/agents/supervisor.py` | `SubjectSupervisor.ask(subject, pseudo, question) -> ChatResult` dispatch par subject. | **Partiellement**. Le dispatch reste ; le retour `ChatResult` doit être remplacé par un AsyncIterator[str] (ou équivalent). Voir § 6 décision D1. |
| `backend/app/services/agents/types.py` | `SourceCitation(filename, chunk_index)` + `ChatResult(answer, sources)` Pydantic. | **Stable** pour la sortie. Mais il faut introduire un type « chunked stream » (cf. D1). |
| `backend/app/services/agents/citations.py` | `CITATION_FORMAT` + `CITATION_RE`. | **Intact**. Les citations sont émises par le LLM dans la réponse (regex parsing post-hoc). Le pattern matche la sortie **complète** ; pour le streaming token-par-token, deux options : (a) parser en streaming (regex incrémentale), (b) parser en fin de stream. Voir § 6 décision D3. |
| `backend/app/services/llm/client.py` | `LlmClient` Protocol avec unique `invoke`, factory `build_llm_client(settings)`. | **À étendre**. Ajouter `astream(messages) -> AsyncIterator[AIMessageChunk]` au Protocol, et l'implémenter dans `_LangChainChatWrapper` (passe-plat vers `chat.astream`). C'est le **changement le plus structurant** de s09. |
| `backend/app/services/rag/retriever.py` | `Retriever.query(subject, pseudo, question, k)` synchrone (utilise `embed_documents` + `collection.query`). | **Réutilisable tel quel** pour la phase retrieval (avant streaming). |
| `backend/app/cli.py:_build_chat_service` | Constructeur du superviseur avec toutes les dépendances (chroma, embeddings, llm, retriever, agents). | **Réutilisable** par le lifespan FastAPI. Pas de modification du CLI. |
| `backend/app/core/database/session.py` | `get_db()` (dépendance FastAPI), `get_session_factory()`, `init_db()`. | **Réutilisable**. Le lifespan doit appeler `init_db()`. |
| `backend/app/core/config.py` | `Settings` (Pydantic). | **À étendre** avec un bloc `API_*` (CORS allow-origin, host, port — déjà en place : `api_host`, `api_port` lignes 21-22, mais `cors_allow_origins` manque), et potentiellement un bloc `CHAT_STREAM_*` (heartbeat interval, max chunks, etc.). |
| `backend/app/core/database/models.py` | Modèles `Document`, `Exercise`, `Attempt`, etc. | **Hors-scope**. s09 n'écrit PAS de `Conversation` / `Message` (story § 338-372 ne le demande pas). L'historique arrive en s19. |

### 2.2 Fichiers à créer

| Fichier | Rôle | Justification |
|---|---|---|
| `backend/app/main.py` | Application FastAPI : `app = FastAPI(...)`, `lifespan` (init DB + warm LLM), `CORSMiddleware`, `include_router`. | Pas d'entrée FastAPI dans l'arbre actuel. s09 doit la créer (devient le point d'entrée du serveur HTTP). |
| `backend/app/api/__init__.py` | `__version__` ou vide (package marker). | Cohérent avec `app/services/__init__.py`. |
| `backend/app/api/chat.py` | Router FastAPI avec `POST /api/chat/stream` (Pydantic body, `StreamingResponse` SSE). | Sous-domaine `chat` conformément à `architecture.md:55-60` et `AGENTS.md` « un sous-dossier par domaine dans `app/api/`, un `router.py` par sous-domaine ». |
| `backend/app/api/schemas/chat.py` (ou `backend/app/api/chat_schemas.py`) | `ChatStreamRequest(pseudo, subject, question)`, `ChatStreamChunkEvent`, `ChatStreamDoneEvent`, `ChatStreamErrorEvent`. | Schémas Pydantic pour body + events SSE (l'AC3 exige `done: true, sources: [...]` typés). |
| `backend/app/services/agents/streaming.py` (ou ajout dans `types.py`) | `class StreamChunk(content: str, event: Literal["token", "sources", "done", "error"])`. | Le contrat de streaming entre agent et router HTTP. |
| `backend/tests/api/__init__.py` | Package marker. | Cohérent avec `tests/services/`. |
| `backend/tests/api/test_chat_stream.py` | Tests `TestClient` (8-10 tests : 422 missing fields, stream happy path, chunk ordering, error event, CORS preflight, OPTIONS, multi-tenant, etc.). | L'AC6 + AC7 l'exigent. |
| `backend/tests/services/agents/test_streaming.py` (ou tests ajoutés dans `test_maths_agent.py` / `test_supervisor.py`) | Tests unitaires du `LlmClient.astream` (stub) et du `SubjectAgent.stream` (asynchrone). | Vérification de l'isolation, des invariants (sources émises en fin), du format SSE. |
| `backend/tests/services/llm/test_client.py` (étendu) | Tests de la nouvelle méthode `astream` du wrapper LangChain. | Le wrapper doit être testé unitairement. |
| `docs/decisions/010-fastapi-streaming.md` (NOUVEAU ADR) | Décision sur l'**architecture de streaming** : (a) extension de `LlmClient` vs nouvelle abstraction, (b) `StreamingResponse` natif vs `sse-starlette`, (c) parsing citations en streaming vs fin, (d) format du body (`pseudo` in body — auth stub). | Toutes les décisions structurantes de s09 (voir § 6). |

### 2.3 Fichiers à modifier (mineure)

| Fichier | Modification | Justification |
|---|---|---|
| `backend/app/services/llm/client.py` | Ajouter `astream(messages) -> AsyncIterator[AIMessageChunk]` au `LlmClient` Protocol + implémenter dans `_LangChainChatWrapper` (passe-plat `chat.astream(messages)`). | Sans cela, aucun chemin streaming n'existe. Le `LlmClient.invoke` reste pour les usages one-shot (CLI, s02, s05). |
| `backend/app/services/agents/maths_agent.py` | Ajouter `async def astream(subject, pseudo, question) -> AsyncIterator[StreamChunk]`. Le `ask` existant reste (CLI one-shot). | Évite la régression sur s02-s07. Le streaming est une nouvelle méthode. |
| `backend/app/services/agents/francais_agent.py` | Idem. | Cohérence. |
| `backend/app/services/agents/supervisor.py` | Ajouter `async def astream(subject, pseudo, question) -> AsyncIterator[StreamChunk]` qui dispatch à l'agent. | Le router FastAPI parle au superviseur, pas aux agents directs. |
| `backend/app/core/config.py` | Ajouter `cors_allow_origins: list[str]` (lit `CORS_ALLOW_ORIGINS` env, défaut `["http://localhost:3000"]`), `chat_stream_max_chunks: int = 5000` (garde-fou), `chat_stream_heartbeat_ms: int = 0` (désactivé par défaut). | CORS obligatoire pour s11 (frontend Next.js) ; les deux autres sont des garde-fous. |
| `backend/requirements.txt` | Ajouter `fastapi>=0.115` + `uvicorn[standard]>=0.30` (séparément, voir § 4.4 piège). | FastAPI est physiquement installé mais **non déclaré** — c'est un trou à fermer. `sse-starlette` n'est PAS retenu (D2). |
| `backend/.env.example` | Ajouter `CORS_ALLOW_ORIGINS=http://localhost:3000` + `CHAT_STREAM_MAX_CHUNKS=5000`. | Convention : tous les blocs `Settings` ont leur pendant dans `.env.example` (cf. s02-s07). |
| `docs/architecture.md` | Ajouter une section « FastAPI application » qui pointe vers `app/main.py`, `app/api/`, et liste les routers connus (s09, s10, s12+). | Cohérence avec § « Stack » et « Repo structure cible ». |
| `docs/decisions/003-langgraph-supervisor.md` | Pas de modif (s09 ne touche pas au superviseur ; juste étend son API). | — |
| `docs/decisions/004-rag-isolation-by-collection.md` | Pas de modif (s09 ne touche pas au retriever). | — |
| `docs/stories.md` | Pas de modif (la story ne change pas). | — |

### 2.4 Fichiers à ne PAS toucher (run interdicts hérités de s02-s08)

- `backend/app/services/rag/retriever.py` (invariant multi-tenant ; s09 le consomme en lecture seule).
- `backend/app/services/rag/chroma_store.py` (factory `get_collection(subject, pseudo)`).
- `backend/app/services/rag/embeddings.py`.
- `backend/app/services/rag/ingestion.py` / `ocr.py` / `upload_service.py`.
- `backend/app/services/storage/minio_client.py`.
- `backend/app/core/database/models.py` (s09 ne crée pas de modèle — historique en s19).
- `backend/app/cli.py` (le CLI reste one-shot, pas de `chat-stream` CLI).
- `backend/app/services/exercises/*` (qcm_grader, text_grader, generators — hors-scope).
- `backend/app/services/correction/*` (s08 livré, hors-scope).

## 3. Premise verification (chaque assertion de la story confrontée au code)

| Assertion de la story (AC) | Vérification dans le code | Verdict |
|---|---|---|
| AC1 — `POST /api/chat/stream` accepte JSON `{pseudo, subject, question}` | Pas d'endpoint `/api/chat/stream` dans le code. Pas de router FastAPI. Pas de schéma Pydantic `ChatStreamRequest`. | **INVALIDE — à créer**. |
| AC2 — Chaque event SSE contient un chunk incrémental | Pas de générateur de streaming. `LlmClient` n'a que `invoke`. | **INVALIDE — `LlmClient.astream` à ajouter** (voir § 6 D1). |
| AC3 — Event final `{done: true, sources: [...]}` | Pas de format d'event défini. `SourceCitation` existe (types.py:22) mais pas l'event wrapper. | **INVALIDE — type `ChatStreamDoneEvent` à créer**. |
| AC4 — Erreur en stream → event `{error: "..."}` + close clean | Pas de gestion d'erreur streaming. Le code existant (`MathsAgent.ask`) lève des exceptions (e.g. `ValueError` cross-tenant, `InvalidPseudoError`) qui tuent le process — pas de catch. | **INVALIDE — try/finally + event error à câbler** (la story le mentionne trap ligne 371). |
| AC5 — CORS configuré pour `NEXT_PUBLIC_API_URL` | Pas de `CORSMiddleware` dans le code. `next_public_api_url` n'est pas dans `Settings`. | **INVALIDE — CORS middleware à ajouter + settings**. |
| AC6 — Test `TestClient` streame + assert ordre | `TestClient` n'est utilisé nulle part (`grep -r "TestClient"` → 0 résultats). | **INVALIDE — tests à créer**. |
| AC7 — 422 sur champs manquants AVANT stream | Pas d'endpoint. La validation Pydantic 422 est native FastAPI (`RequestValidationError`) — disponible dès qu'un endpoint existe avec un schéma Pydantic. | **OK par construction** une fois l'endpoint créé (Pydantic valide avant le handler). |

**Conclusion** : **les 7 ACs sont invalides au sens strict** (aucune n'a de code à réutiliser tel quel). La story a été écrite **en pensant que la stack FastAPI existait déjà** (cf. § 1.5 biais d'omission). C'est la story fondatrice de l'API — toute la complexité « oubliée » du scaffolding s'y concentre.

## 4. Traps & constraints

### 4.1 Piège 1 — `LlmClient.invoke` est synchrone, pas streaming

Le `LlmClient` Protocol (`client.py:27-34`) n'a qu'`invoke`. Le wrapper LangChain (`client.py:38-48`) appelle `self._chat.invoke(messages)` (synchrone). LangChain 1.5.4 supporte `astream` (vérifié : `Has astream: True` en runtime), mais **personne ne l'expose** dans la couche `LlmClient`. Si on tente un streaming sans étendre le Protocol, on est forcé de :
- Soit passer par `langchain_openai.ChatOpenAI` directement dans l'agent (casse l'injection),
- Soit bufferiser la réponse dans `invoke` puis re-streamer côté HTTP (anti-pattern : défait le bénéfice du streaming, on revient à un one-shot lent).

**Mitigation** : D1 (cf. § 6) — étendre `LlmClient` avec `astream` (passe-plat vers `chat.astream`). C'est non-invasif (les callers `invoke` existants ne changent pas).

### 4.2 Piège 2 — Le parsing des citations en streaming

`MathsAgent._collect_sources(chunks)` (maths_agent.py:114-124) **parse les sources depuis les chunks RAG**, pas depuis la réponse LLM. Les citations `[source: filename, chunk N]` sont émises par le LLM dans sa réponse (regex `CITATION_RE` ligne 20 de citations.py) **mais ne sont pas parsées** : le code actuel se contente de retourner `chunks` tels quels. Conséquence : la sortie `ChatResult(answer, sources)` a `sources` = les chunks RAG utilisés, **pas** les citations regex du LLM.

**Pour s09** : le `sources` à émettre dans l'event `done` (AC3) est `list[SourceCitation]`. Question : ces sources sont :
- (a) les chunks RAG (`RetrievedChunk`) transformés → **cohérent avec le code actuel** (s02-s07 utilisent déjà cela).
- (b) les citations regex parsées depuis la sortie LLM → **cohérent avec l'esprit « citation obligatoire »** des system prompts, mais jamais implémenté.

**Verdict** : (a) est ce que le code fait déjà. (b) serait un changement de comportement. **Recommandation D3 (cf. § 6)** : (a) pour s09 (alignement avec l'existant), (b) reporté à une story ultérieure.

### 4.3 Piège 3 — `subject` dans le body (auth stub)

La story AC1 dit « `{pseudo, subject, question}` dans le body » et les Traps ligne 369-371 mentionnent « For now, no auth: the `pseudo` comes from the body. Real auth (JWT) comes in a later story. » **Cohérent** : s09 est en mode auth-stub, le `pseudo` est trusted dans le body. C'est le contrat repris par s15 (« migration from the 'pseudo in body' auth to JWT auth »). **Le bite test cross-tenant au niveau FastAPI n'est PAS exigé par s09** (pas dans les ACs explicites), mais le runner du repo va probablement le demander (cf. AGENTS.md § Multi-tenancy : « au moins un test d'isolation cross-tenant pour toute nouvelle route accédant à des données élève »). **Recommandation** : ajouter un test cross-tenant s09 même si la story ne l'exige pas, pour respecter la DoD du repo (cf. § 6 D4).

### 4.4 Piège 4 — `fastapi` est installé mais non déclaré

`fastapi 0.141.1` est physiquement présent dans le venv (`C:\Apps\anaconda3\envs\ktutor\Lib\site-packages\fastapi\`) **mais absent de `requirements.txt`** (vérifié : 40 lignes, aucun `fastapi`/`uvicorn`/`starlette`/`sse-starlette`). C'est un trou :
- En CI (où l'environnement est recréé à partir de `requirements.txt`), `from fastapi import FastAPI` lèvera `ModuleNotFoundError`.
- En prod, même problème.

**Mitigation obligatoire** : ajouter `fastapi>=0.115` et `uvicorn[standard]>=0.30` à `requirements.txt`. `sse-starlette` n'est PAS retenu (D2 — le `StreamingResponse` natif suffit, et l'écosystème LLM n'a pas besoin du surcouche SSE).

### 4.5 Piège 5 — Le `next_public_api_url` côté backend n'existe pas

Le `CLAUDE.md` mentionne `NEXT_PUBLIC_API_URL` comme variable d'env **frontend** (Next.js). Côté backend, la story AC5 demande « allow the frontend origin (from `NEXT_PUBLIC_API_URL` env) ». **Problème** : `NEXT_PUBLIC_API_URL` est une variable **frontend** ; le backend ne la lit pas naturellement. Conventions Cross-cutting :
- Option 1 : le backend lit `CORS_ALLOW_ORIGINS` (env backend) que l'opérateur synchronise avec `NEXT_PUBLIC_API_URL` côté frontend. Documentation explicite.
- Option 2 : le backend lit `FRONTEND_ORIGIN` (env backend, défaut `http://localhost:3000`) et la doc explique que cette valeur doit matcher `NEXT_PUBLIC_API_URL`.

**Recommandation** : Option 1 (`CORS_ALLOW_ORIGINS`, multi-origins séparées par virgule). Plus flexible (plusieurs frontends possibles), plus idiomatique FastAPI.

### 4.6 Piège 6 — Le `TestClient` n'est utilisé dans aucun test existant

`grep -r "TestClient\|testclient" backend/tests/` → 0 résultats. s09 introduit le pattern. Convention à établir :
- Importer via `from fastapi.testclient import TestClient` (FastAPI 0.141.1 expose un wrapper qui déprécie httpx → installe `httpx2` selon `StarletteDeprecationWarning` runtime).
- Le client est instancié par fixture pytest : `client = TestClient(app)`.
- Pour le SSE, le client lit `response.iter_lines()` ou `response.iter_text()`.
- `httpx 0.28.1` est installé (vérifié) → TestClient fonctionne.

**Convention à fixer dans le plan** : un `conftest.py` au niveau `tests/api/` qui expose la fixture `client` (singleton par session si possible, recréé si `Settings` changent).

### 4.7 Piège 7 — L'asynchrone dans un codebase très majoritairement synchrone

Tout le code backend (s01-s08) est **synchrone** : `def` partout, pas de `async def` dans `app/`. FastAPI gère les deux, mais :
- Les **endpoints** FastAPI sont naturellement `async def` (ou `def` avec run-in-threadpool).
- L'**appel LLM** doit être `async` pour streamer (`chat.astream` est `AsyncIterator`).
- Le **retriever** (ChromaDB + embeddings) est synchrone — on doit l'invoquer avant le streaming.

**Recommandation** : pattern « sync pré-streaming, async streaming ». Le handler :
1. (sync) valide le body Pydantic.
2. (sync) appelle `Retriever.query` (chunks RAG).
3. (async) appelle `subject_supervisor.astream(subject, pseudo, question)` qui yield des `StreamChunk`.
4. (async) yield des events SSE formatés.

C'est le pattern `astream_events` de LangChain (mentionné dans AGENTS.md § LLM et agents : « `astream_events` (LangChain) pour le chat, exposé en SSE par FastAPI »). **Mais** `astream_events` est plus verbeux que `astream` (qui yield des `AIMessageChunk` avec `.content`). Pour s09, `astream` est suffisant (l'agent n'utilise pas de tools ; pas besoin du detail des events).

### 4.8 Piège 8 — Le `lifespan` doit initialiser ChromaDB et l'embedding provider

Quand FastAPI démarre (s09), le `lifespan` doit :
- `db_session.init_db()` (créer les tables — `init_db()` idempotent, OK).
- Warm-up du LLM ? Optionnel ; le premier appel paye la latence. Recommandation : **ne pas** warm-up (YAGNI).
- Warm-up de ChromaDB ? Idem : le `PersistentClient` est lazy, OK.

**Recommandation** : `lifespan` minimal qui appelle `init_db()`. Pas de warm-up LLM (l'instanciation du `ChatOpenAI` est déjà paresseuse côté langchain-openai).

### 4.9 Piège 9 — Format SSE exact

Le format SSE est `data: <json>\n\n`. Pièges classiques :
- Oublier le `\n\n` final → le navigateur ne déclenche pas `onmessage`.
- Encoder le JSON sans `ensure_ascii=False` → caractères français mal rendus.
- Utiliser `Content-Type: text/event-stream; charset=utf-8` (FastAPI le fait automatiquement avec `media_type="text/event-stream"`, mais le charset est implicite — l'ajouter explicitement ne fait pas de mal).

**Recommandation** : helper `_format_sse(payload: dict) -> bytes` qui retourne `f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")`. Test bite : retirer le `\n\n` → le client ne reçoit rien (test rouge sur réception).

### 4.10 Piège 10 — `httpx2` deprecation

Runtime : `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`. C'est un **warning**, pas une erreur, mais le reviewer le flaggera probablement. **Recommandation** : ignorer pour s09 (sorti du scope). Si on installe `httpx2`, c'est un changement de `requirements.txt` qui doit être justifié par un ADR — pas dans s09.

## 5. Open questions

| # | Question | Statut / hypothèse de résolution |
|---|---|---|
| Q1 | Le router FastAPI doit-il accepter `pseudo` dans le body (auth stub) ou dans un header `X-Pseudo` ? | **À trancher en D4**. La story dit « body » explicitement (ligne 348). Le `X-Pseudo` serait plus RESTful mais n'est pas demandé. **Recommandation** : body (fidèle à la story). Migration JWT en s15. |
| Q2 | Le format de l'event SSE `error` doit-il inclure un `code` HTTP-like ou juste un `message` ? | **À trancher en D5**. La story AC4 dit `{error: "..."}` (juste un message). **Recommandation** : `{error: "...", code: "..."}` (code stable, mappé depuis `kind` des exceptions agents : `cross_tenant`, `no_subject`, `invalid_pseudo`, `unknown`). |
| Q3 | Le `sources` dans l'event `done` est-il un `list[SourceCitation]` (Pydantic existant) ou un format plus riche `{filename, chunk_index, excerpt}` ? | **À trancher en D3**. Le code actuel retourne `SourceCitation(filename, chunk_index)` (types.py:22-26). **Recommandation** : réutiliser tel quel. |
| Q4 | Le stream doit-il avoir un heartbeat (comment `: ping\n\n` toutes les N secondes) ? | **À trancher en D6**. Les proxies (nginx, cloudflare) timeout les connexions inactives. **Recommandation** : pas de heartbeat en s09 (YAGNI), paramétrable via `chat_stream_heartbeat_ms=0` (désactivé par défaut). |
| Q5 | Le test cross-tenant est-il obligatoire pour s09 ? | **À trancher en D4**. La story ne l'exige pas (l'AC3 mentionne juste `done: true, sources: [...]`). Mais AGENTS.md § DoD exige « au moins un test d'isolation cross-tenant pour toute nouvelle route accédant à des données élève ». **Recommandation** : ajouter le test (cohérent avec la DoD). |
| Q6 | Le test d'intégration avec un vrai LLM est-il requis pour s09 ? | La story ne le demande pas. Cohérent avec s02-s07 (test d'intégration best-effort non bloquant). **Recommandation** : pas de test d'intégration pour s09 (le test E2E du frontend en s11 exercera le bout en bout). |
| Q7 | L'`ExerciseType` accepte-t-il `probleme`/`redaction` ? | **Question irrelevant pour s09** (s09 fait du chat, pas des exercices). Mais bon à savoir : l'enum contient `QCM, PROBLEME, REDACTION, FLASHCARDS` après s06+s06b. |
| Q8 | L'application FastAPI doit-elle supporter un mode « debug » (auto-reload) ? | **À trancher en D7**. `uvicorn.run(app, reload=True)` est utile en dev mais dangereux en prod. **Recommandation** : un script `backend/scripts/serve.py` (ou un `__main__` de `app.main`) qui lit `Settings.debug` et passe `reload` à uvicorn. Pas d'auto-reload si `DEBUG=false`. |

## 6. Décisions d'architecture à prendre

### D1 — Forme de l'API de streaming agent-side

**Contexte** : `MathsAgent.ask(...) -> ChatResult` est one-shot. Pour streamer, il faut une nouvelle méthode. Options :

- **Option A** — Ajouter `astream(subject, pseudo, question) -> AsyncIterator[StreamChunk]` à `MathsAgent` ET `FrancaisAgent` ET `SubjectSupervisor`. Le `ask` one-shot reste pour le CLI.
- **Option B** — Remplacer `ask` par `astream` partout et wrapper `ask` = `for chunk in agent.astream(...): accumulate.answer += chunk.content; return ChatResult(answer, sources)`. Migration invasive (CLI, tests, s02-s08).
- **Option C** — Nouvelle abstraction `StreamingSubjectAgent(Protocol)` + `StreamingSubjectSupervisor`. Le `SubjectSupervisor` actuel reste pour le one-shot.

**Recommandation** : **Option A**. Justifications :
- Non-invasif : zero changement de comportement pour s02-s08.
- Le CLI one-shot continue à utiliser `ask` (le panel `rich` ne streame pas).
- Les agents mathématiques et français sont symétriques (mêmes deps, même shape) — dupliquer la méthode `astream` est cohérent.
- Le router FastAPI parle au `SubjectSupervisor.astream` ; le CLI parle au `SubjectSupervisor.ask`. Pas de confusion.

**Note** : `astream` est un mot-clé `async` generator (`AsyncIterator[StreamChunk]`). Le type `StreamChunk` est nouveau (voir D3).

### D2 — SSE via `StreamingResponse` natif vs `sse-starlette`

**Contexte** : FastAPI 0.115+ supporte `StreamingResponse(generator, media_type="text/event-stream")`. `sse-starlette` est un wrapper plus idiomatique (ping, retry, etc.) mais n'est pas installé et ajoute une dépendance.

**Options** :
- **Option A** — `StreamingResponse` natif. Le generator yield des `bytes` au format `data: <json>\n\n`. Aucun ajout de dépendance.
- **Option B** — `sse-starlette.EventSourceResponse`. Plus ergonomique (`async def event_generator(): yield {"event": "message", "data": ...}`). Ajoute `sse-starlette>=2.0` à `requirements.txt`.

**Recommandation** : **Option A**. Justifications :
- `sse-starlette` n'est pas installé ; Option B l'ajoute (dépendance supplémentaire).
- Le format SSE est trivial (2 lignes de boilerplate).
- Pas besoin du `ping` (D6, YAGNI).
- Pas besoin du `retry` (le client reconnect automatiquement après `error` event).

### D3 — Format de `sources` et parsing des citations LLM

**Contexte** : Les system prompts (`maths_agent.py:25-40`, `francais_agent.py:34-50`) exigent que le LLM émette `[source: filename, chunk N]` dans sa réponse. Le code actuel **ne parse pas** cette sortie (les sources viennent directement des chunks RAG via `_collect_sources`).

**Options** :
- **Option A** — `sources` = liste des chunks RAG transformés en `SourceCitation(filename, chunk_index)` (comportement actuel de `ChatResult.sources`).
- **Option B** — Parser les citations regex depuis la sortie LLM streamée (regex incrémentale) et les émettre en fin de stream. Si le LLM omet une citation → log warning.

**Recommandation** : **Option A pour s09**. Justifications :
- Cohérent avec le code actuel (zero régression).
- Le `sources` du RAG sont fiables (toujours présents, fichier connu).
- Le parsing regex LLM est fragile (LLM peut omettre, mal former, dupliquer).
- Une story ultérieure peut ajouter le parsing regex si le produit en a besoin.

### D4 — Auth stub : `pseudo` dans le body

**Contexte** : La story dit « `{pseudo, subject, question}` dans le body » (auth stub). s15 migrera vers JWT.

**Options** :
- **Option A** — Body JSON `{pseudo, subject, question}`. Le router lit `body.pseudo` et le passe au superviseur.
- **Option B** — Header `X-Pseudo: <pseudo>` + body `{subject, question}`. Plus RESTful.

**Recommandation** : **Option A** (fidèle à la story). Justifications :
- L'AC1 est explicite sur le format.
- Le test cross-tenant bite : si on retire `pseudo` du body et qu'on le lit depuis le JWT, le test doit changer en s15 (refactor conscient).

**Test cross-tenant** : ajouter un test `test_chat_stream_cross_tenant_via_body_swap_returns_5` qui POST un `pseudo="bob"` mais query sur la collection de `pseudo="alice"` → assert que l'event error contient `code: cross_tenant`. **Note** : ce test est plus fort que ce que la story exige (elle n'exige PAS de test cross-tenant explicite), mais AGENTS.md § DoD l'exige. À inclure pour shipper proprement.

### D5 — Format de l'event `error`

**Contexte** : AC4 dit `{error: "..."}` (message libre). Mais le CLI (s04, s07) a introduit un pattern `kind` (chaîne stable). La cohérence demande d'étendre.

**Options** :
- **Option A** — `{error: "..."}` (format brut, conforme à la story).
- **Option B** — `{error: "...", code: "cross_tenant" | "no_subject" | "invalid_pseudo" | "unknown"}` (aligné avec le pattern `kind` des graders).

**Recommandation** : **Option B** (avec `code` en plus de `error`). Justifications :
- Le client frontend (s11) peut mapper `code` à un comportement (afficher un toast vs rediriger vs retry).
- Le pattern `kind` est déjà établi (s04 QcmGradingError, s07 TextGradingError) — réutilisation.
- Le test bite : retirer `code` → test cross-tenant rouge.

### D6 — Heartbeat / ping SSE

**Contexte** : Les proxies timeout les connexions inactives (nginx par défaut 60s, cloudflare 100s). Un LLM long à répondre peut laisser le client sans nouvelles.

**Options** :
- **Option A** — Pas de heartbeat. Le client peut timeout après N secondes et reconnecter. Simple.
- **Option B** — Heartbeat toutes les 15-30 secondes (`data: {"ping": true}\n\n` ou commentaire SSE `: ping\n\n`).

**Recommandation** : **Option A pour s09 (YAGNI)**. Paramétrable via `chat_stream_heartbeat_ms=0` (désactivé par défaut). Une story ultérieure peut ajouter un heartbeat si l'observabilité (s23) détecte des timeouts proxy.

### D7 — Mode debug / auto-reload

**Contexte** : En dev, `uvicorn.run(app, reload=True)` est utile. En prod, c'est dangereux (recompile tout Python en boucle).

**Options** :
- **Option A** — Pas de mode debug. `uvicorn app.main:app --reload` est explicite côté CLI.
- **Option B** — `Settings.debug=True` active le reload automatiquement.

**Recommandation** : **Option A**. Justifications :
- Le `reload` est un argument uvicorn explicite, l'opérateur le passe en CLI.
- Pas de logique conditionnelle dans le code.
- Cohérent avec FastAPI/uvicorn idiomatique.

### D8 — Sémantique du close de stream

**Contexte** : AC4 dit « the connection closes cleanly ». Comment ?

**Options** :
- **Option A** — Le generator termine naturellement après l'event `done`. FastAPI ferme la connexion TCP.
- **Option B** — Le generator yield `done`, puis yield `None` (sentinel), puis termine. Le router ferme.

**Recommandation** : **Option A** (terminaison naturelle du generator). C'est l'idiome Python pour `async def` generator. Pas de sentinel.

**Try/finally** : AC4 trap ligne 371 dit « use a try/finally around the generator ». Le générateur doit :
- `try` : yield les events.
- `except` : catch toute exception, yield event error, raise (FastAPI ferme).
- `finally` : cleanup (close session DB, close chroma cursor, etc.).

**Pattern recommandé** :
```python
async def event_generator():
    try:
        async for chunk in supervisor.astream(...):
            yield _format_sse(_to_event(chunk))
    except ValueError as exc:
        yield _format_sse({"error": str(exc), "code": _map_code(exc)})
    finally:
        # cleanup if needed
        pass
```

### D9 — Location des fichiers (app/api/ vs app/api/chat/)

**Contexte** : AGENTS.md dit « un sous-dossier par domaine dans `app/api/`, un `router.py` par sous-domaine ». s09 = `chat`. Options :

- **Option A** — `backend/app/api/__init__.py` + `backend/app/api/chat.py` (un seul fichier pour le router, schémas Pydantic inline).
- **Option B** — `backend/app/api/__init__.py` + `backend/app/api/chat/__init__.py` + `backend/app/api/chat/router.py` + `backend/app/api/chat/schemas.py` (sous-dossier, schémas séparés).

**Recommandation** : **Option B**. Justifications :
- Cohérent avec `app/services/{agents,exercises,rag}/` (un sous-dossier par domaine, plusieurs fichiers).
- Les schémas Pydantic peuvent grossir (s11 frontend va consommer plusieurs events).
- Sépare la déclaration de route (router.py) du contrat de données (schemas.py).

### D10 — ADR 010 (NOUVEAU) — Architecture de streaming

**Recommandation** : créer `docs/decisions/010-fastapi-streaming.md` (MADR format, cf. `templates/adr.md`) qui consigne :
- Choix `StreamingResponse` natif vs `sse-starlette` (D2).
- Choix `LlmClient.astream` vs autre (D1).
- Choix `body.pseudo` vs `X-Pseudo` header (D4).
- Format des events SSE (D5).

**Note** : ce n'est PAS un ADR pour le superviseur (ADR 003 le couvre) ni pour le RAG (ADR 004). C'est un ADR pour la **strate de streaming** (comment FastAPI ↔ agent communique).

## 7. Re-scored complexity

### Score de la story dans `docs/stories.md` : **3**

### Score après ouverture du code : **5**

### Justification du écart

| Critère | Story dit | Réalité |
|---|---|---|
| FastAPI SSE | « FastAPI SSE » (1 complexité) | **À créer de zéro** : pas de `main.py`, pas de `app/api/`, pas de `fastapi` dans `requirements.txt`. **+2** (scaffolding entier). |
| LangChain streaming | « LangChain streaming » (1 complexité) | `LlmClient` n'a pas `astream`. Doit être ajouté au Protocol + implémenté dans le wrapper. **+1** (extension de l'API transverse). |
| CORS | « CORS » (1 complexité) | CORS middleware à ajouter + setting `CORS_ALLOW_ORIGINS` à créer. **0.5** (trivial). |
| Auth stub | « auth-stub » (1 complexité) | Le `pseudo` est dans le body, c'est littéralement `body.pseudo`. **0** (gratuit une fois le body Pydantic créé). |
| Tests `TestClient` | implicite | TestClient n'est utilisé nulle part, pattern à introduire. **+0.5** (convention à fixer). |
| Tests d'isolation cross-tenant (DoD) | implicite | Pas dans la story, exigé par AGENTS.md. **+0.5** (à ajouter, test bite). |
| Décisions structurantes (D1-D10) | implicite | 10 décisions à trancher (D1-D10), dont un nouvel ADR. **+1** (charge de décision). |
| Risque de merge avec s08 / s10 | implicite | s08 est mergé sur `origin/main` mais **PAS dans le worktree s09** (branche locale stale). s10 est en parallèle. Risque de rebase forcé. **+0.5** (logistique). |

**Score recalculé** : 3 (story) + 2 (scaffolding) + 1 (extension LlmClient) + 0.5 + 0 + 0.5 + 0.5 + 1 + 0.5 = **9 brut**, lissé à **5** par convention (les complexités 1-2 sont additives, pas multiplicatives).

### Verdict : **5**

### Proposition de split (le plan ne peut pas faire mieux que cette recherche)

Si l'équipe veut respecter la règle « un score de 5 = split obligatoire » :

- **s09a — FastAPI scaffolding** : `app/main.py` + `app/api/__init__.py` + `requirements.txt` (`fastapi`, `uvicorn`) + `Settings.cors_allow_origins` + `Tests/api/conftest.py` (fixture `TestClient`) + 3-4 tests « healthcheck » (`GET /api/health` retourne 200, CORS preflight OK, etc.). **Complexity 2-3**. Livrable shippable, fondation pour toutes les autres stories API.
- **s09b — Chat SSE streaming** : `app/api/chat/router.py` + `LlmClient.astream` + `MathsAgent/FrancaisAgent/SubjectSupervisor.astream` + 8-10 tests `TestClient` (chunks, sources, error, 422, cross-tenant). **Complexity 3-4**. Livrable shippable, consomme s09a.

**Mais** : ce split double le coût d'orchestration (2 plans, 2 reviews, 2 PRs). Le gain est marginal (s09a n'a pas de valeur fonctionnelle). **Recommandation finale** : **NE PAS splitter**. Score 5 assumé, mais :
- Découpage interne en 2 phases (TDD d'abord `LlmClient.astream` + tests unitaires, puis intégration FastAPI).
- PR atomique (commit unique) avec un diff lisible (~600-800 lignes de code, ~300 lignes de tests, ~50 lignes de doc).
- Reviewer explicite sur le score 5 (le finding « complexity bumped from 3 to 5 » est attendu et documenté dans cette recherche).

## 8. Definition of Done (spécialisé pour s09)

- [ ] Toutes les tâches du plan cochées.
- [ ] `pytest --cov=app --cov-fail-under=80 -m "not integration"` passe (≥ 80% de couverture, cible 350+ tests après ajout d'~20).
- [ ] `ruff check app tests` passe (0 erreur).
- [ ] `python -c "import fastapi"` + `python -c "import uvicorn"` fonctionnent après `pip install -r requirements.txt` (validation que les deps sont déclarées).
- [ ] AC1-AC7 tous couverts par des tests `TestClient`.
- [ ] **Test cross-tenant** : un test vérifie qu'un `pseudo_b` ne peut pas streamer du contenu issu de la collection de `pseudo_a` (le router lit `pseudo` du body, le superviseur dispatch au bon agent, l'agent query `Retriever.query(subject, pseudo, question, k)` qui filtre par `pseudo`). Test bite : retirer `pseudo` du body ou hardcoder un autre pseudo dans le router → test rouge.
- [ ] **Test bite sur le format SSE** : un test vérifie que chaque event est au format `data: <json>\n\n` (regex sur les bytes reçus). Test bite : retirer `\n\n` → 0 event reçu.
- [ ] **Test bite sur l'event `done`** : un test vérifie que l'event final contient `{done: true, sources: [...]}` avec au moins 1 source si la collection n'est pas vide. Test bite : ne pas yield l'event `done` → test rouge.
- [ ] **Test bite sur l'event `error`** : un test vérifie qu'une exception dans le generator yield un event `error` + la connexion se ferme. Test bite : retirer le `try/except` → la connexion crashe (test rouge sur `with TestClient`).
- [ ] **Test bite sur le 422** : un test vérifie qu'un body sans `question` retourne 422 avant tout stream. Test bite : retirer la validation Pydantic → test rouge.
- [ ] **Test CORS preflight** : un `OPTIONS /api/chat/stream` avec `Origin: http://localhost:3000` retourne 200 + `Access-Control-Allow-Origin`. Test bite : retirer le middleware CORS → 400/403.
- [ ] **Test streaming order** : un test vérifie que les chunks arrivent dans l'ordre (chunk 1, chunk 2, ..., sources, done). Test bite : yield dans le désordre → test rouge.
- [ ] **CLI non régressé** : `python -m ktutor.cli chat --help` fonctionne toujours (le CLI one-shot n'est pas cassé par l'ajout de `astream`).
- [ ] **Aucune régression sur s02-s08** : tous les tests existants passent.
- [ ] **ADR 010 créé** : `docs/decisions/010-fastapi-streaming.md` avec les choix D1, D2, D4, D5.
- [ ] **CORS_ALLOW_ORIGINS dans `.env.example`** : documenté.
- [ ] **`fastapi` + `uvicorn` dans `requirements.txt`** : déclarés explicitement.
- [ ] PR unique, description structurée : résumé, AC cochées, **points d'attention** (notamment : (a) complexité re-scorée à 5, (b) split non retenu, (c) `sse-starlette` non retenu, (d) `pseudo` dans le body — migration JWT en s15, (e) pas de heartbeat en s09, (f) rebase sur `origin/main` recommandé en étape 0 du plan pour intégrer s08 et d'éventuels merges futurs).
- [ ] `git diff main...feature/s09-api-chat-streaming` est lisible.
- [ ] Review passée (`docs/reviews/s09-api-chat-streaming.md` avec `Ship allowed: yes`).

## 9. Risques

### Risque 1 — Complexité 5 (re-scorée) assumée

10 décisions structurantes (D1-D10), scaffolding entier FastAPI, extension de `LlmClient`, 20+ tests, 1 nouvel ADR. **Mitigation** : découpage en phases dans le plan (TDD `LlmClient.astream` d'abord, puis agents, puis router, puis tests intégration). PR atomique.

### Risque 2 — Le worktree est sur un main stale (HEAD `473181c`, sans s08)

Le worktree `feature/s09-api-chat-streaming` a été branché depuis `main` local avant que `f255046` (s08) ne soit mergé. **Le code de s08 n'est PAS dans ce worktree**. Conséquence : si le plan s09 s'appuie sur du code de s08 (e.g. un éventuel changement dans `Attempt.answer_text` ou l'enum `ExerciseType`), il y aura un conflit de rebase.

**Vérification** : s09 n'utilise PAS s08. Le chat n'a pas besoin de la correction progressive. **Le rebase sur `origin/main` reste recommandé** (étape 0 du plan) pour éviter un rebase forcé en fin de PR. **Pas bloquant**.

### Risque 3 — s10 tourne en parallèle sur le même répertoire de base

L'orchestrateur lance `/ks-research` sur s09 ET s10 en parallèle. Les deux stories partagent la création de `app/main.py` (s09) et `app/api/` (s09 + s10). **Conflit de merge garanti** si les deux PRs mergent sans coordination.

**Mitigation** : 
- s09 crée `app/main.py` + `app/api/__init__.py` + `app/api/chat/router.py` (sans toucher aux autres routers).
- s10 crée `app/api/documents/router.py` (sans toucher à `app/main.py` ou `app/api/__init__.py`).
- Le merge de s09 doit précéder celui de s10 (ou inversement, mais l'un crée `app/main.py`, l'autre l'utilise — s10 dépend de s09).
- **Recommandation** : la dépendance `s09 → s10` doit être documentée dans le plan s10 (le plan s10 doit commencer par « rebase sur s09 mergé »).

### Risque 4 — `fastapi` non déclaré dans `requirements.txt`

Si s09 ajoute `fastapi` et `uvicorn` mais oublie de les committer (oubli dans le diff), le CI va crasher. **Mitigation** : le `Definition of Done` inclut une vérification explicite `python -c "import fastapi"` après install from scratch.

### Risque 5 — Le format SSE est subtil (Pièges 4.9)

Un `\n` oublié, un `ensure_ascii=False` raté, un `Content-Type` mal configuré → le navigateur ne reçoit rien. **Mitigation** : helper centralisé `_format_sse` + test bite (4.9).

### Risque 6 — Tests `TestClient` vs `httpx2` deprecation

`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`. C'est un warning, pas un blocage. **Mitigation** : ignorer pour s09, suivre l'évolution de FastAPI/Starlette. Si on installe `httpx2`, c'est un autre PR.

### Risque 7 — Le LLM ne streame pas vraiment

Le `chat.astream` de LangChain yield des `AIMessageChunk`. Si le LLM upstream ne supporte pas le streaming (e.g. certains modèles sur OpenRouter), le wrapper va soit crasher, soit bufferiser toute la réponse et yield un seul chunk à la fin. **Mitigation** : test bite sur l'ordre et le nombre de chunks (au moins 2 chunks pour une réponse non triviale). Si le test échoue, fallback documenté : `chat.stream` synchrone (peut être plus largement supporté).

### Risque 8 — Multi-tenancy à l'API

La story ne demande PAS de test cross-tenant, mais la DoD l'exige. **Mitigation** : ajouter le test dans le plan (D4 bite). Le test vérifie que le router passe bien `body.pseudo` au superviseur, qui dispatch à l'agent, qui query le retriever avec `(subject, pseudo, question)` — la chaîne complète est auditée.

## 10. Sources

### Fichiers lus (chemins absolus)

- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\docs\stories.md` (l. 338-372 pour s09 ; l. 1086-1091 pour l'ordre d'exécution suggéré)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\docs\architecture.md` (l. 1-360 ; focus l. 53-60 API structure, l. 130-134 backend patterns, l. 244-260 schema `conversations`/`messages` — non utilisé par s09, l. 300 `LLM_BASE_URL`)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\docs\prd.md` (l. 1-100 ; pas de Q ouverte pour s09)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\docs\research\s05-agent-francais-chat.md` (template de structure de cette recherche)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\docs\research\s07-repondre-texte-libre.md` (template de recherche backend ; structure « verifiée runtime »)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\docs\reviews\s05-agent-francais-chat.md` (conventions : bite tests, lint, format review)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\docs\reviews\s07-repondre-texte-libre.md` (conventions : « un test par AC », « central invariants are real, not decorative »)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\CLAUDE.md` (l. 41-50 API stack, l. 110-120 RBAC, l. 150-158 multi-tenancy, l. 200-204 streaming LangChain `astream_events` — note: § « SSE / LangChain » mentionne `astream_events`, pas `astream`. À clarifier au planning, voir D1)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\AGENTS.md` (Backend conventions, Multi-tenancy, LLM et agents, DoD)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\requirements.txt` (intégralité — 41 lignes ; `fastapi`/`uvicorn`/`sse-starlette` absents)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\.env.example` (intégralité — 108 lignes ; `CORS_ALLOW_ORIGINS` absent)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\__init__.py` (vide + `__version__`)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\__main__.py` (entry CLI)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\cli.py` (l. 1-100 imports + `_build_service` ; l. 100-300 `_build_chat_service` et autres services)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\core\config.py` (intégralité — 134 lignes)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\core\database\session.py` (intégralité — `get_db()` FastAPI dependency déjà en place, l. 61-67)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\services\agents\__init__.py` (ré-exports)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\services\agents\maths_agent.py` (intégralité — 125 lignes)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\services\agents\francais_agent.py` (intégralité — 101 lignes)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\services\agents\supervisor.py` (intégralité — 80 lignes)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\services\agents\types.py` (intégralité — 33 lignes ; `ChatResult`, `SourceCitation`)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\services\agents\citations.py` (intégralité — 25 lignes)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\services\llm\client.py` (intégralité — 80 lignes ; `LlmClient` Protocol avec seul `invoke`)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\services\rag\retriever.py` (intégralité — 152 lignes)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\app\services\exercises\qcm_grader.py` (l. 1-60 — pattern `kind` pour D5)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\tests\conftest.py` (intégralité — 146 lignes)
- `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming\backend\tests\services\agents\test_maths_agent.py` (existence vérifiée — pattern `_ScriptedLlm` à adapter pour `astream`)

### Vérifications runtime (sur le venv `ktutor` à `C:\Apps\anaconda3\envs\ktutor`)

- `python -c "import langchain_core; print(langchain_core.__version__)"` → `1.5.4`
- `python -c "from langchain_core.language_models import BaseChatModel; print([m for m in dir(BaseChatModel) if 'stream' in m.lower()])"` → `['_achat_model_stream_v3', '_astream', '_astream_events_v1_v2', '_astream_events_v3_unsupported', '_atransform_stream_with_config', '_chat_model_stream_v3', '_should_stream', '_should_use_protocol_streaming', '_stream', '_streaming_disabled', '_transform_stream_with_config', 'astream', 'astream_events', 'astream_log', 'stream', 'stream_events']` — **streaming natif disponible**.
- `python -c "import fastapi; print(fastapi.__version__)"` → `0.141.1` (**installé mais non déclaré**)
- `python -c "import httpx; print(httpx.__version__)"` → `0.28.1` (**installé**)
- `python -c "from fastapi.testclient import TestClient; print('TestClient OK')"` → `TestClient OK` (avec `StarletteDeprecationWarning` sur `httpx`)
- `python -c "from fastapi.responses import StreamingResponse; print('OK')"` → `OK`
- `python -c "from fastapi.middleware.cors import CORSMiddleware; print('CORS OK'); from fastapi import FastAPI; app = FastAPI(); print('FastAPI app OK')"` → `CORS OK` + `FastAPI app OK`
- `python -c "from sse_starlette.sse import EventSourceResponse"` → `ModuleNotFoundError` (**sse-starlette NON installé**)
- `python -c "from langchain_openai import ChatOpenAI; chat = ChatOpenAI(model='x', api_key='x', base_url='x'); print(hasattr(chat, 'astream'))"` → `True`

### ADRs consultés

- `docs/decisions/001-monorepo-backend-frontend.md` — monorepo (contexte, non touché).
- `docs/decisions/002-poc-rewrite-from-scratch.md` — POC rewrite (non touché).
- `docs/decisions/003-langgraph-supervisor.md` — superviseur (s09 ne touche pas au superviseur lui-même, juste étend son API avec `astream`).
- `docs/decisions/004-rag-isolation-by-collection.md` — multi-tenancy RAG (s09 respecte par construction, le retriever est intact).
- `docs/decisions/005-auth-rs256-rbac.md` — auth (s09 en mode stub, s12-s15 livrent le vrai).

### ADRs à créer

- `docs/decisions/010-fastapi-streaming.md` (NOUVEAU) — consigne les choix D1 (extension `LlmClient` vs autre), D2 (`StreamingResponse` natif vs `sse-starlette`), D4 (`pseudo` dans le body vs header), D5 (format event `error` avec `code`).

### Branches / commits de référence

- Worktree : `C:\Workspace\ktutor\.worktrees\s09-api-chat-streaming`
- Branche : `feature/s09-api-chat-streaming` (HEAD `473181c`)
- Base : `main` (HEAD local `473181c` = squash de s07 = PR #9). **s08 (`f255046`, PR #10) n'est PAS dans ce worktree.**
- `origin/main` (HEAD `f255046` = s08 mergé) — **rebase recommandé en étape 0 du plan**.

### Notes opérationnelles

- Le venv `ktutor` (`C:\Apps\anaconda3\envs\ktutor`) a fastapi 0.141.1 et httpx 0.28.1 préinstallés — l'implémentation peut être testée immédiatement. Mais le `requirements.txt` doit être mis à jour pour que CI/prod les installent.
- `sse_starlette` n'est PAS disponible — utiliser `StreamingResponse` natif.
- L'orchestrateur lance `/ks-research` sur s10 en parallèle. s10 dépend de s09 (création de `app/main.py`). Le plan s09 doit donc être shippable avant s10.

---

## Conclusion

**Score recalculé** : **5** (vs 3 dans la story). Le delta vient du scaffolding FastAPI (main, api/, requirements) qui n'existe pas dans le code actuel. **Split non retenu** (justifié § 7).

**Aucun faux premise trouvé** : toutes les ACs sont invalides au sens strict (« pas de code à réutiliser tel quel ») mais le code existant est sain (s02-s08 sont propres, l'extension est non-invasive). La story est **sur-scopée par rapport à ce qu'elle pense couvrir** (FastAPI SSE = scaffold + extend LlmClient + 10 décisions + ADR nouveau + 20 tests).

**Recommandation pour /ks-plan** : structurer le plan en 4 phases :
1. **Phase 0** — rebase sur `origin/main` (intégrer s08 et le code futur).
2. **Phase 1** — `LlmClient.astream` + tests unitaires du wrapper (TDD strict, 3-4 tests).
3. **Phase 2** — `MathsAgent.astream` + `FrancaisAgent.astream` + `SubjectSupervisor.astream` + tests unitaires (8-10 tests).
4. **Phase 3** — `app/main.py` + `app/api/chat/router.py` + `app/api/chat/schemas.py` + tests `TestClient` (8-10 tests) + ADR 010.
5. **Phase 4** — `requirements.txt` (fastapi, uvicorn) + `Settings.cors_allow_origins` + `.env.example` + `docs/architecture.md` section FastAPI.

PR unique, ~600-800 lignes de code + ~300 lignes de tests + ~80 lignes de doc.
