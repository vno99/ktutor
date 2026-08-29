---
name: research-s02-chatter
description: s02-chatter-avec-mon-cours — research output for /ks-plan
metadata:
  type: project
  story: s02-chatter-avec-mon-cours
---

# Research — Story s02-chatter-avec-mon-cours

## The five structuring facts

1. **Aucun LLM client n'est instancié dans le code applicatif actuel.** Le `Settings.llm_provider` accepte `"minimax" | "openai" | "mistral" | "ollama"` (config.py:49) et `openai_api_key` (config.py:50), mais aucun module ne consomme ces valeurs pour invoquer un LLM. Le seul client LLM-shaped est `MultimodalOcr` (HTTP direct via `httpx` vers `DEEPSEEK_OCR_URL`). — `backend/app/services/rag/ocr.py:1`.
2. **Le retriever ChromaDB n'existe pas en tant que module.** `ChromaStore` (`backend/app/services/rag/chroma_store.py:47`) expose `get_collection`, `add_chunks`, `list_collections_for_pseudo`, mais pas de méthode de query. La story s02 doit introduire un nouveau module `services/rag/retriever.py` (annoncé dans la story `Files involved`) ou ajouter `query(...)` à `ChromaStore` — convention du projet : un service = un sous-dossier, méthodes cohésives ; la query sémantique est conceptuellement un retriever distinct.
3. **Stub LLM disponible immédiatement.** `langchain_core.language_models.fake.FakeListLLM` (LLM string) et `langchain_core.language_models.fake_chat_models.FakeListChatModel` (chat, retourne `AIMessage`) sont installés (v1.3.15). `FakeListChatModel` est le bon choix pour un agent RAG qui prend une liste de messages. Pas dans `requirements.txt` (langchain-core est tiré par langchain-text-splitters), mais `pip install` confirme la disponibilité.
4. **ChromaDB query API confirmée** : `collection.query(query_embeddings=[[...]], n_results=k, include=["documents", "metadatas", "distances"])` (testé contre 1.5.9). L'embedeur de la question est `FastEmbedProvider` ou `OpenAIEmbeddingProvider` (déjà en place dans `services/rag/embeddings.py`).
5. **`langgraph 1.2.11` est installé** mais non utilisé. Pour s02 (single agent maths, pas de superviseur), pas besoin de `langgraph` — un agent RAG est un appel LLM structuré. Le superviseur arrive en s05 (sujet français). Le piège de scope : ne pas introduire langgraph maintenant.

## Target story

**Story** : s02-chatter-avec-mon-cours — Poser une question sur mon cours et obtenir une réponse sourcée.
**Complexity** : 3 (Agent LangChain + RAG retrieval + prompt engineering + source citation).

### Acceptance criteria (7 ACs)

1. `python -m ktutor.cli chat --pseudo <p> --subject maths --question "..."` retourne une réponse ancrée dans les documents uploadés.
2. La réponse cite au moins une source (filename + page ou chunk index).
3. Si aucun chunk pertinent (similarité sous seuil), message "je n'ai pas trouvé d'information sur ce sujet dans tes documents" — pas d'hallucination.
4. L'agent utilise le `LLM_PROVIDER` env (défaut `minimax`).
5. Le CLI imprime la réponse et exit 0.
6. Test cross-tenant : `pseudo_a` ne récupère QUE ses documents.
7. Test "no document" : sans upload, l'agent répond avec le message de fallback.

## Current state of the code

### Fichiers concernés (vérifiés)

- `backend/app/services/rag/chroma_store.py` — `ChromaStore.get_collection`, `add_chunks`, `list_collections_for_pseudo`. **Pas de query**. Convention `rag_<subject>_<pseudo>` verrouillée (test `TestCollectionName::test_format`).
- `backend/app/services/rag/embeddings.py` — `EmbeddingProvider` (Protocol), `FastEmbedProvider` (BAAI/bge-small-en-v1.5, 384-dim), `OpenAIEmbeddingProvider` (text-embedding-3-small, 1536-dim). Factory `build_embedding_provider(llm_provider, openai_api_key)`.
- `backend/app/services/rag/ingestion.py` — chunking `RecursiveCharacterTextSplitter(chunk_size=1000, overlap=200)`. Chunk metadata : `{chunk_index, document_id}`. `Chunk` Pydantic.
- `backend/app/cli.py` — CLI typer. Le module expose `app` (typer.Typer) et un `_build_service()`. Le pattern de stub pour les tests est `monkeypatch.setattr("app.cli._build_service", lambda: stub)`.
- `backend/app/services/rag/upload_service.py` — le pipeline d'indexation qui a déjà inséré les chunks dans ChromaDB. Le s02 RETRÈVE ces chunks.
- `backend/app/core/database/models.py` — `Document` (id UUID, student_pseudo, subject, filename, s3_key, chunks_count, status, error_reason, created_at). **Aucun modèle `Conversation` ou `Message` n'existe** — l'architecture cible les mentionne (l.224-240) mais s02 ne les utilise pas (chat est one-shot via CLI).
- `backend/app/core/config.py` — `Settings.llm_provider: Literal["minimax", "openai", "mistral", "ollama"]`, `openai_api_key: str = ""`. **Manque** : URL/clé pour minimax/mistral/ollama, modèle par défaut, temperature. À ajouter dans s02.

### Modules absents

- `backend/app/services/rag/retriever.py` — n'existe pas. À créer.
- `backend/app/services/agents/` — le sous-dossier n'existe pas (mentionné dans l'architecture cible l.69 mais vide).
- `backend/app/services/agents/maths_agent.py` — à créer.
- `backend/app/services/llm/` ou équivalent — pas de client LLM. La convention du projet suggère `services/llm/client.py` (pas dans l'architecture cible) ou un module dans `services/agents/llm_client.py` (couplé à l'agent, pas idéal).
- `backend/app/core/llm/` — alternative : client LLM au niveau core (logique transverse). À trancher.

### Conventions du projet (déduites du code, pas inventées)

| Convention | Source vérifiée | Forme attendue pour s02 |
|---|---|---|
| Un sous-dossier par service | `app/services/rag/{chroma_store,ingestion,ocr,upload_service}.py` | `app/services/agents/maths_agent.py` (sous-dossier `agents/`) |
| Injection par constructeur | `UploadService(s3_client=..., chroma_store=..., embeddings=..., ingestor=..., ocr=...)` | `MathsAgent(llm=..., retriever=..., embeddings=...)` |
| `_XxxLike` Protocol pour les dépendances | `_SessionLike`, `_EmbeddingsLike`, `_OcrLike` dans `upload_service.py:70,76,38` | `_LlmLike` (Protocol) et `_RetrieverLike` (Protocol) |
| `Protocol` classes via `typing.Protocol` | Partout | Idem |
| `from __future__ import annotations` | Première ligne de chaque module | Idem |
| snake_case fichiers et fonctions, PascalCase classes | `chroma_store.py`, `ChromaStore` | `maths_agent.py`, `MathsAgent` |
| Exit codes nommés (`EXIT_OK = 0`, `EXIT_GENERIC_ERROR = 1`...) | `upload_service.py:32-37` | `EXIT_OK = 0`, `EXIT_NO_DOCUMENT = 10` ? — à trancher |
| Erreurs typées (`UploadError`, `UploadErrorKind`) | `upload_service.py:42-54` | `ChatError`, `ChatErrorKind` |
| Tests par AC, classes `TestX`, fixtures locales | `test_chroma_store.py`, `test_upload_service.py` | Idem : `test_maths_agent.py`, `test_chat_cli.py` |
| `EphemeralClient` pour ChromaDB dans les tests | `test_chroma_store.py:30-31`, `test_upload_service.py:78` | Idem |
| Cross-tenant : test `test_pseudo_a_cannot_see_pseudo_b_chunks` | `test_chroma_store.py:127` | Réutiliser ce test au niveau agent |
| Stub pattern CLI : `_StubService` avec `behavior` paramétrable | `test_cli.py:33-74` | Idem pour `chat` |
| Source citation : `[source: <filename>, chunk <n>]` | Stories : ligne 82 | Format à verrouiller dans une constante |

## Anchor points

- **Nouveau module** : `backend/app/services/rag/retriever.py` — encapsulation de la query ChromaDB (embed question → top-k chunks → retour). Reçoit l'embedder et le `ChromaStore` par injection.
- **Nouveau module** : `backend/app/services/agents/maths_agent.py` — orchestration (retrieve + prompt + LLM). Reçoit retriever, embedder, llm.
- **Nouveau module** : `backend/app/services/llm/client.py` (ou `app/core/llm/`) — client LLM abstrait. Probablement le bon endroit car transverse. Décision à confirmer au planning.
- **Extension `cli.py`** : nouvelle commande `@app.command() def chat(...)`. Exit code propre, `--json` output cohérent avec `upload`.
- **Extension `config.py`** : `llm_api_key: str = ""`, `llm_base_url: str = ""` (pour openai, le client lit `OPENAI_API_KEY` ou `OPENAI_BASE_URL` ; pour minimax on a besoin d'un endpoint custom). Modèle et temperature.
- **Nouveau test** : `backend/tests/services/rag/test_retriever.py`, `backend/tests/services/agents/test_maths_agent.py`, `backend/tests/cli/test_cli.py` (extension pour la commande `chat`).

## Verified APIs / functions

- `chromadb.Collection.query(query_embeddings: list[list[float]], n_results: int, include: list[str]) -> dict` — confirmé par tests existants et la version 1.5.9 installée. Retourne `{"ids": [[...]], "documents": [[...]], "metadatas": [[...]], "distances": [[...]]}`.
- `langchain_core.language_models.fake_chat_models.FakeListChatModel(responses: list[str])` — installé (v1.3.15). `invoke([SystemMessage, HumanMessage]) -> AIMessage(content=str)`. Testé ci-dessus : `from langchain_core.language_models.fake_chat_models import FakeListChatModel; llm = FakeListChatModel(responses=['A']); llm.invoke([...]).content == 'A'`.
- `langchain_core.language_models.fake.FakeListLLM` — idem pour un LLM string-based.
- `langchain.chat_models.init_chat_model(...)` — pas testé. C'est l'API recommandée LangChain 1.x pour instancier un ChatModel depuis un provider string ("openai", "anthropic"...). N'inclut pas "minimax" nativement.
- `langchain_openai.ChatOpenAI(model=..., api_key=..., base_url=...)` — confirmé installé. `base_url` permet de pointer vers n'importe quel endpoint OpenAI-compatible (donc compatible avec minimax si le provider expose une API OpenAI).
- `EmbeddingProvider.embed_documents(texts: list[str]) -> list[list[float]]` (Protocol) — déjà défini dans `services/rag/embeddings.py:25`.

## Traps & constraints

- **Provider "minimax"** : aucun client LLM n'est câblé. La story dit "LLM (par défaut) : Minimax-M3 (gratuit, local)". Mais `pip show langchain` ne montre pas d'intégration native minimax. Hypothèse : Minimax expose une API OpenAI-compatible → utiliser `ChatOpenAI(base_url=<minimax_endpoint>, api_key=<key>)`. **À vérifier** : le `LLM_PROVIDER=minimax` n'a pas de signification technique dans le code actuel, juste un littéral. s02 doit choisir un fallback : ou bien câbler minimax via OpenAI-compat, ou bien retombber sur openai pour le POC. **Décision tranchable au planning**.
- **Multi-tenancy test cross-tenant** : la story s02 AC6 demande que `pseudo_a` ne récupère QUE ses documents. La garantie vient de l'isolation par collection (ADR 004) — `rag_maths_alice` ≠ `rag_maths_bob`. Le retriever doit recevoir le `pseudo` en argument explicite et appeler `chroma_store.get_collection(subject, pseudo)` — JAMAIS de lister toutes les collections ou d'accepter le pseudo en body sans validation. Le piège : si le retriever prend un `collection_name` directement, on contourne la convention. **Le retriever DOIT prendre `(subject, pseudo, question)`**.
- **Format de citation** : la story impose `[source: <filename>, chunk <n>]`. Mais les chunks ChromaDB ont `metadata.document_id` (UUID) et `metadata.chunk_index` (int). Le `filename` n'est PAS dans les chunks indexés. Il faut soit :
  1. Joindre `Document.filename` via PostgreSQL (lookup `documents.id == metadata.document_id`).
  2. Inclure `filename` dans `chunk.metadata` à l'indexation (s01 ne l'a pas fait — vérifier `chroma_store.add_chunks` et `upload_service._to_chroma_dict`).
  Vérifié : `upload_service.py:288-293`, `_to_chroma_dict` n'inclut que `{**chunk.metadata, "document_id": str(document_id)}`. Pas de `filename`. **Donc la story s02 doit soit modifier s01 pour inclure le filename, soit faire un lookup DB**. Le lookup DB est lourd (1 chunk → 1 query). **Modifier s01 pour ajouter le filename dans les metadata est le bon choix** — mais ça touche l'AC1 de s01 ("indexed, chunks in collection"). À trancher au planning.
- **Threshold de similarité** : AC3 parle d'un seuil de similarité. ChromaDB retourne des `distances` (cosine ou L2 selon configuration). Le seuil de fallback "no document" est non spécifié dans la story. **À trancher au planning** (proposition : cosine distance > 0.5, ou top-k tous au-dessus d'un seuil). Le test AC7 "no document" est trivial : collection vide → directement le fallback.
- **Top-k** : la story dit "k=4 default". À verrouiller comme constante.
- **Temperature = 0** : mentionné dans la story (l.78). Important pour la reproductibilité des tests. À passer en config ou en argument.
- **Architecture cible vs réalité** : `docs/architecture.md:69` mentionne `services/agents/supervisor.py` et `services/agents/maths_agent.py`. Le sous-dossier n'existe pas encore. Le superviseur arrive en s05 ; s02 ne le crée pas, mais crée `maths_agent.py` directement (single agent par matière).
- **CLI existant** : `app/cli.py` n'a qu'une commande `upload`. L'ajout de `chat` étend `app` (le `typer.Typer` racine). Pattern cohérent.
- **Modèles SQLAlchemy** : la story s02 n'introduit pas de nouveau modèle (pas de `Conversation` / `Message` en s02 — l'architecture cible les mentionne mais les stories s09-s19 les créent). L'AC "historique" n'est pas dans s02.
- **Tests d'isolation** : le test cross-tenant est obligatoire (DoD AGENTS.md). Le test "no document" est aussi dans l'AC7. Ces deux tests sont déjà partiellement couverts par les tests `test_chroma_store.py::TestMultiTenantIsolation` (au niveau store) — s02 doit les re-tester au niveau agent/CLI.
- **Loguru** : `app/core/logging.py` existe (non lu) — s02 doit logger les appels LLM (durée, prompt length, response length) conformément à l'observabilité.
- **LangChain warnings** : `langchain-community` est sunset. Les `from langchain_community.document_loaders import PyMuPDFLoader` (ingestion.py:20) et `from langchain_community.llms.fake import FakeListLLM` sont concernés. Pour s02, on n'utilise pas community — uniquement `langchain_core` (déjà en place) et éventuellement `langchain_openai` pour le client LLM.

## Open questions

1. **Provider "minimax"** : comment câbler concrètement le LLM Minimax-M3 ? Option A : `ChatOpenAI(base_url="https://api.minimax.com/v1", api_key=...)` (si l'API est OpenAI-compatible). Option B : client custom via `httpx`. Option C : retomber sur openai pour le POC et noter dans la recherche que minimax est une promesse pour plus tard. **À trancher au planning**.
2. **Source citation - filename** : modifier `_to_chroma_dict` dans s01 pour inclure `filename` dans la metadata ? Ou faire un lookup DB à chaque retrieval ? Proposition : modifier s01 (1 ligne de diff) — c'est cohérent avec le fait que le nom de fichier fait partie du document, pas juste de la session d'indexation.
3. **Threshold de similarité** : valeur exacte du seuil "no document" ? Proposition : cosine distance > 0.5 = no document. À tester empiriquement ou hardcoder.
4. **Format de prompt** : le format de citation doit-il être `[source: filename, chunk 3]` (avec virgule) ou `[source: filename, page 3]` (avec page) ? Les chunks n'ont pas de notion de page, juste `chunk_index`. Proposition : `[source: <filename>, chunk <n>]`. Verrouillé dans une constante.
5. **Persistance du chat** : s02 sauvegarde-t-il l'échange question/réponse ? L'architecture cible a `conversations` et `messages` (s09-s19). Pour le POC CLI one-shot, **non** — l'historique est géré par les stories d'API. s02 fait du one-shot.
6. **Module client LLM** : `app/services/llm/client.py` (transverse, suit le pattern "un sous-dossier par service") ou `app/core/llm/client.py` (logique core transverse) ? Proposition : `app/services/llm/` (services ne sont pas que RAG, l'agent n'est qu'un consumer).
7. **Liste de providers LLM supportés en s02** : openai seulement (couvrir le test stub), ou tenter minimax ? Proposition : openai câblé (test runtime), minimax config-only (pas de client instancié, fallback openai si le provider est "minimax" sans base_url). Minimax sera branché dans une story ultérieure.
8. **Streaming** : la story dit "the CLI prints the answer and exits 0". Pas de streaming requis. L'API streaming arrive en s09 (`/chat/stream` SSE). **s02 est one-shot, pas de stream**.

## Real complexity

**Score donné dans `docs/stories.md` : 3.** Score confirmé après lecture du code : **3**.

Pas de divergence. Les pièces sont en place (embeddings, ChromaStore, chunking). Le nouveau code se résume à :
- 1 retriever (méthode `query(subject, pseudo, question, k=4)` qui embed + appelle `chroma.query`).
- 1 client LLM (factory `build_llm(provider, settings)` → ChatModel).
- 1 agent (méthode `ask(subject, pseudo, question)` qui retrieve + prompt + LLM).
- 1 commande CLI `chat`.
- 1 test cross-tenant + 1 test "no document" + tests unitaires de chaque composant.

C'est un slice bien découpé, sans risque de combinatorial explosion (vs s08 qui a un state machine à 4 états × 2 types d'exercices).

Si on devait splitter, le cut naturel serait :
- **s02a** : retriever ChromaDB (embed question + top-k chunks) — shippable, testable seul, sans LLM.
- **s02b** : maths_agent (retriever + LLM + prompt) + CLI `chat`.

Mais s02a seul ne livre pas de valeur visible (pas de "chat"). Donc on garde s02 en un seul. **Verdict : 3, ne pas splitter.**

## Split proposal

Pas de split (verdict 3). Si une complexité inattendue émerge au planning (ex. : intégrer le streaming s09 dans s02 pour éviter 2 commandes CLI différentes), rouvrir le débat.

## Files touched (anticipated)

**Code (5-6 fichiers nouveaux ou modifiés)** :
- `backend/app/core/config.py` (modifié) : ajout `llm_api_key`, `llm_base_url`, `llm_model`, `chat_temperature`, `chat_top_k`, `similarity_threshold_no_doc`.
- `backend/app/services/rag/retriever.py` (nouveau) : `Retriever` class + Protocol `_RetrieverLike`.
- `backend/app/services/llm/client.py` (nouveau) : `LlmClient` Protocol + `build_llm_client(provider, settings)` factory.
- `backend/app/services/agents/maths_agent.py` (nouveau) : `MathsAgent` class avec `ask(subject, pseudo, question) -> ChatResult`.
- `backend/app/services/rag/upload_service.py` (modifié, 1 ligne) : ajouter `filename` dans les metadata des chunks.
- `backend/app/cli.py` (modifié) : commande `chat` + `_build_chat_service()`.
- `backend/app/services/rag/chroma_store.py` (modifié) : ajouter méthode `query(collection, query_embeddings, n_results)` (utilitaire) OU la query se fait directement dans le retriever.

**Test (3-4 nouveaux)** :
- `backend/tests/services/rag/test_retriever.py` (3-4 tests : top-k, cross-tenant, no document, mauvais subject).
- `backend/tests/services/agents/test_maths_agent.py` (5-6 tests : stub LLM, sources citées, fallback no document, cross-tenant, prompt contient les chunks, temperature=0).
- `backend/tests/cli/test_cli.py` (étendu : 3-4 tests : `chat` exit 0, JSON output, `--pseudo` invalide, pas de document).
- `backend/tests/services/llm/test_client.py` (2-3 tests : factory par provider, fallback si provider inconnu).

**Doc** :
- `docs/architecture.md` (modifié, mineure) : confirmer l'emplacement de `services/llm/` (si retenu).
- Pas d'ADR nouveau (les décisions s'inscrivent dans les ADR existants : 002 POC rewrite, 003 LangGraph, 004 RAG isolation).

**Non touchés** :
- `backend/app/services/storage/minio_client.py` (s01, intact).
- `backend/app/services/rag/ocr.py` (s01, intact).
- `backend/app/services/rag/embeddings.py` (s01, intact, juste consommé par le retriever).
- Modèles SQLAlchemy (pas de modèle `Conversation`/`Message` en s02).
- `docs/research/s01-…`, `docs/plans/s01-…`, `docs/reviews/s01-…` (s01 figé).
- `docs/research/s01b-…`, `docs/plans/s01b-…`, `docs/reviews/s01b-…` (s01b figé).

## Test strategy

### Tests automatisés

- **Retriever** : `chromadb.EphemeralClient`, `FakeEmbeddings` (reprise du pattern `test_upload_service.py:34-42`).
- **MathsAgent** : `FakeListChatModel` pour le LLM (assertion sur le prompt envoyé : contient les chunks, contient la question, contient l'instruction "réponds uniquement à partir des chunks").
- **CLI** : pattern `_StubService` de `test_cli.py:33` étendu à un `_StubAgent`.
- **Cross-tenant** : 2 pseudos, upload pour chacun, query par un seul — l'agent ne doit voir que les chunks du sien.
- **No document** : pseudo sans aucun upload, query → fallback "je n'ai pas trouvé d'information sur ce sujet dans tes documents" + exit 0.
- **Stub LLM** : `FakeListChatModel(responses=["Voici la réponse basée sur ton cours de maths."])` pour les tests unitaires.

### Vérification manuelle locale

- `python -m ktutor.cli upload tests/fixtures/sample_cours.pdf --pseudo ali --subject maths`
- `python -m ktutor.cli chat --pseudo ali --subject maths --question "Qu'est-ce qu'une dérivée ?"`
- Vérifier que la réponse cite `[source: sample_cours.pdf, chunk N]`.
- Lancer la même commande avec un autre pseudo (sans upload) → fallback "no document".
- Lancer avec `pseudo_b` (qui n'a rien uploadé) sur la question → "no document" (pas de leak depuis `ali`).

### Pas de test d'intégration avec vrai LLM (best-effort)

L'intégration avec un vrai LLM (openai ou minimax) est best-effort, marqué `@pytest.mark.integration`, non bloquant pour la PR.

## Definition of Done (candidat)

- Toutes les tâches cochées.
- `pytest -m "not integration"` passe (cible : 90+ tests).
- `ruff check app tests` clean.
- Test cross-tenant au niveau agent/CLI vert.
- Test "no document" vert.
- Format de citation verrouillé (constante, test).
- Prompt système exigeant "réponds uniquement à partir des chunks" + "refuse si pas de contexte".
- Temperature 0 par défaut (test vérifie la valeur).
- CLI `chat` exit 0 en cas de succès ou de "no document" (pas d'erreur).
- CLI `chat` exit non-zéro seulement si `--pseudo` invalide (code 5, comme upload) ou autre erreur.
- PR unique, description structurée, AC cochées.
- Review passée (gate `Ship allowed: yes`).

<< IP Mike: what a research always verifies — premise, traps, anchor points, complexity. >>
