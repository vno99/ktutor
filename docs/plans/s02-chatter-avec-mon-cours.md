---
validated: yes
---
# Plan — Story s02-chatter-avec-mon-cours

Branch: `feature/s02-chatter-avec-mon-cours`
Research: `docs/research/s02-chatter-avec-mon-cours.md` — read it first; this plan does not repeat it.

## Target story

**Story** : s02-chatter-avec-mon-cours — Poser une question sur mon cours et obtenir une réponse sourcée.
**Complexity** : 3 (Agent LangChain + RAG retrieval + prompt engineering + source citation). Confirmé à la recherche (pas de divergence).

### Acceptance criteria (7 ACs, du research)

1. `python -m ktutor.cli chat --pseudo <p> --subject maths --question "..."` retourne une réponse ancrée dans les documents uploadés.
2. La réponse cite au moins une source au format `[source: <filename>, chunk <n>]`.
3. Si aucun chunk pertinent (collection vide), message de fallback — pas d'hallucination.
4. L'agent utilise le `LLM_PROVIDER` env (défaut `minimax`, routé via OpenRouter).
5. Le CLI imprime la réponse et exit 0.
6. Test cross-tenant : `pseudo_a` ne récupère QUE ses documents.
7. Test "no document" : sans upload, l'agent répond avec le message de fallback.

## Decisions tranchées au planning

Issues de la recherche § Open questions, tranchées en checkpoint avec l'utilisateur :

- **Q1 (Provider LLM)** : `minimax` est routé via **OpenRouter** (API OpenAI-compatible). Le client utilisé est `langchain_openai.ChatOpenAI(base_url=...)`. Tous les providers (`minimax`, `openai`, `ollama`) sont implémentés via la même factory qui route selon `llm_provider`. Le modèle est stocké en config (`llm_model`).
- **Q2 (Filename citation)** : modifier `upload_service._to_chroma_dict` pour ajouter `metadata.filename`. Coût : 1 ligne de diff sur s01. Migration acceptable : les chunks indexés avant s02 n'auront pas le filename ; le retriever fallback sur "unknown" si la metadata est absente.
- **Q3 (Emplacement client LLM)** : `backend/app/services/llm/client.py` (sous-dossier `services/llm/`, cohérent avec `services/rag/`, `services/storage/`).
- **Q4 (Seuil similarité)** : **collection vide uniquement**. Pas de seuil numérique. Le prompt système force le LLM à dire "je ne sais pas" si les chunks ne répondent pas à la question.
- **Q5 (Persistance chat)** : pas de persistance. Le chat est one-shot (l'historique arrive en s09-s19).
- **Q6 (Streaming)** : pas de streaming en s02. CLI one-shot, exit 0.
- **Q7 (LangChain vs openai natif)** : on garde `langchain_openai.ChatOpenAI` pour la cohérence avec `OpenAIEmbeddings` déjà utilisé dans `services/rag/embeddings.py`.

## Tasks (ordered)

### Étape 0 — Outillage (config + extension s01)

1. [x] **Étendre `backend/app/core/config.py`** avec les paramètres LLM (l.48-50) :
   - `llm_api_key: str = ""` (env `LLM_API_KEY`)
   - `llm_base_url: str = "https://openrouter.ai/api/v1"` (env `LLM_BASE_URL`)
   - `llm_model: str = "minimax/minimax-m3:free"` (env `LLM_MODEL`)
   - `chat_temperature: float = 0.0` (env `CHAT_TEMPERATURE`)
   - `chat_top_k: int = 4` (env `CHAT_TOP_K`)
   - `chat_no_document_message: str = "Je n'ai pas trouvé d'information sur ce sujet dans tes documents."` (env `CHAT_NO_DOCUMENT_MESSAGE`)
   - **Vérification** : `python -c "from app.core.config import Settings; s = Settings(); assert s.chat_top_k == 4"` (test dans `tests/core/test_config.py`).
2. [x] **Étendre `backend/.env.example`** : ajouter les 6 nouvelles variables LLM (commentées pour la plupart, valeurs par défaut cohérentes avec la factory).
3. [x] **Étendre `backend/app/services/rag/upload_service.py:288`** : `_to_chroma_dict` ajoute `"filename": filename` au metadata. Le `filename` est disponible via le scope de `_persist_document` ; il faut le passer en argument à `_to_chroma_dict` (signature étendue à `(chunk, document_id, filename)`). **Vérification** : test unitaire qui indexe un PDF, query Chroma et assert `metadata["filename"] == "sample_cours.pdf"`.
4. [x] **Étendre `backend/tests/services/rag/test_upload_service.py`** : ajouter un test `TestMetadata::test_filename_included_in_chroma_metadata` qui vérifie que le `filename` apparaît dans la metadata des chunks indexés.

### Étape 1 — Client LLM (transverse)

5. [x] **Créer `backend/app/services/llm/__init__.py`** (vide) + `backend/app/services/llm/client.py` avec :
   - `LlmClient` Protocol : `def invoke(self, messages: list[BaseMessage]) -> AIMessage`.
   - `_LangChainChatWrapper` : encapsule un `BaseChatModel` (LangChain) pour exposer l'interface `LlmClient`. C'est l'adaptateur unique — tous les providers passent par là.
   - `build_llm_client(settings: Settings) -> LlmClient` : factory qui :
     - lit `settings.llm_provider` (`"minimax"`, `"openai"`, `"ollama"`),
     - lit `settings.llm_api_key` et `settings.llm_base_url`,
     - instancie `ChatOpenAI(model=settings.llm_model, base_url=..., api_key=..., temperature=settings.chat_temperature)` pour `minimax` et `openai`,
     - pour `ollama` : utilise `ChatOllama(model=..., base_url=...)` (import lazy — `langchain_ollama` n'est PAS dans requirements.txt, on note dans ADR 010 que le support ollama nécessite un ajout de dépendance ; **pour s02, on NE CÂBLE PAS ollama** : il lève `NotImplementedError`).
   - **Vérification** : test unitaire qui vérifie que `build_llm_client(Settings(llm_provider="openai", llm_api_key="x", llm_model="gpt-4o", llm_base_url="https://api.openai.com/v1"))` retourne un wrapper non-None, et que le provider `"ollama"` lève `NotImplementedError`.

### Étape 2 — Retriever (encapsulation query ChromaDB)

6. [x] **Créer `backend/app/services/rag/retriever.py`** avec :
   - `_RetrieverLike` Protocol : `def query(self, subject: str, pseudo: str, question: str, k: int = 4) -> list[RetrievedChunk]`.
   - `RetrievedChunk` Pydantic : `content: str`, `metadata: dict`, `distance: float | None`.
   - `Retriever` classe : constructeur `__init__(self, *, chroma_store: ChromaStore, embeddings: EmbeddingProvider)`. Méthode `query(...)` qui :
     1. valide le pseudo (`chroma_store.validate_pseudo(pseudo)`),
     2. embed la question via `self._embeddings.embed_documents([question])[0]`,
     3. récupère la collection `self._chroma.get_collection(subject, pseudo)` (multi-tenant by construction),
     4. appelle `collection.query(query_embeddings=[query_emb], n_results=k, include=["documents", "metadatas", "distances"])`,
     5. retourne une `list[RetrievedChunk]` (vide si la collection est vide, ChromaDB renvoie `{"ids": [[]], ...}`).
   - **Vérification** : tests dans `tests/services/rag/test_retriever.py` :
     - `test_query_returns_top_k_chunks_in_distance_order` (k=4, 6 chunks indexés → 4 retournés, distances croissantes).
     - `test_query_with_empty_collection_returns_empty_list` (AC7 : pas de document).
     - `test_query_cross_tenant_isolation` (AC6 : `pseudo_a` ne voit que les chunks de `rag_maths_alice`, jamais `rag_maths_bob`).
     - `test_query_invalid_pseudo_raises` (re-utilise `validate_pseudo`).
     - `test_query_passes_top_k_to_chromadb` (k=2 → Chroma reçoit n_results=2).

### Étape 3 — Agent (orchestration retrieve + prompt + LLM)

7. [x] **Créer `backend/app/services/agents/__init__.py`** (vide) + `backend/app/services/agents/maths_agent.py` avec :
   - Constante `CITATION_FORMAT = "[source: {filename}, chunk {chunk_index}]"` (verrouille le format de l'AC2).
   - Constante `NO_DOCUMENT_MESSAGE` importée depuis `config` (ou ré-importée depuis `app.core.config.get_settings().chat_no_document_message` au runtime).
   - `SYSTEM_PROMPT` constant : prompt système interdisant les connaissances générales et exigeant (a) une réponse ancrée dans les chunks fournis, (b) au moins une citation par source utilisée, (c) un refus poli si les chunks ne permettent pas de répondre.
   - `MathsAgent` classe : constructeur `__init__(self, *, llm: LlmClient, retriever: Retriever, top_k: int = 4, no_document_message: str = ...)`. Méthode `ask(self, subject: str, pseudo: str, question: str) -> ChatResult` :
     1. `chunks = self._retriever.query(subject, pseudo, question, k=self._top_k)`.
     2. Si `chunks` vide : retourne `ChatResult(answer=self._no_document_message, sources=[])`.
     3. Sinon : construit le prompt user (template qui injecte les chunks avec leur index et filename), invoque `self._llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)])`, post-traite la réponse (regex léger pour vérifier qu'au moins une citation est présente — si absente, le LLM a oublié, on retourne la réponse telle quelle + warning log, sans la modifier ; l'AC2 dit "cite at least one source" mais ne sanctionne pas).
     4. Retourne `ChatResult(answer=..., sources=[SourceCitation(filename=..., chunk_index=...) for c in chunks if c.metadata has filename and chunk_index])`.
   - `SourceCitation` Pydantic : `filename: str`, `chunk_index: int`.
   - `ChatResult` Pydantic : `answer: str`, `sources: list[SourceCitation]`.
   - `ChatError` exception (optionnelle — s02 reste simple, le `ask` n'a pas de mode d'erreur à part retriever failure ; on laisse remonter).
   - **Vérification** : tests dans `tests/services/agents/test_maths_agent.py` :
     - `test_ask_returns_answer_citing_sources` (FakeListChatModel répond avec "Voici la réponse : [source: foo.pdf, chunk 1]", assert `result.answer` contient la chaîne et `result.sources` non-vide).
     - `test_ask_with_empty_collection_returns_no_document_message` (AC3, AC7).
     - `test_ask_uses_retriever_with_correct_subject_pseudo` (assert retriever.query appelé avec les bons args ; spy).
     - `test_system_prompt_forbids_general_knowledge` (assert la constante contient les mots-clés "uniquement" et "tes documents").
     - `test_citation_format_locked` (assert la regex `\[source: [^,]+, chunk \d+\]` matche le format).
     - `test_cross_tenant_isolation_at_agent_level` (AC6 : 2 pseudos, query par un seul, l'agent n'a accès qu'à la collection du sien ; reproduit le pattern `test_chroma_store.py::TestMultiTenantIsolation`).
     - `test_temperature_zero_passed_to_llm` (assert wrapper capture temperature=0 — peut nécessiter inspection du wrapper ou de l'instance `ChatOpenAI`).

### Étape 4 — Commande CLI `chat`

8. [x] **Étendre `backend/app/cli.py`** :
   - Constantes `EXIT_OK = 0`, `EXIT_GENERIC_ERROR = 1`, `EXIT_INVALID_PSEUDO = 5` (ré-exporter depuis upload_service, ou redéclarer ; **préférer redéclarer** dans `cli.py` ou un module `cli_constants.py`).
   - `_build_chat_service()` : instancie `ChromaStore`, `build_embedding_provider`, `build_llm_client`, `Retriever`, `MathsAgent`. Pas besoin de S3 / DB / OCR pour le chat.
   - `@app.command() def chat(pseudo: str = typer.Option(...), subject: str = typer.Option(...), question: str = typer.Option(...), quiet: bool = False, json_output: bool = False) -> None` :
     - Appelle `service.ask(subject, pseudo, question)`.
     - Affiche la réponse (panel rich en mode normal, JSON en mode `--json`).
     - Exit 0 en cas de succès ou "no document". Exit 5 si pseudo invalide. Exit 1 si autre erreur.
   - **Vérification** : `test_cli.py` étendu :
     - `test_chat_returns_zero_with_answer` (stub agent retourne une réponse non-vide).
     - `test_chat_returns_zero_with_no_document` (stub agent retourne `no_document_message`, exit 0, output contient le message).
     - `test_chat_json_output_is_valid` (--json parseable, contient `answer` et `sources`).
     - `test_chat_invalid_pseudo_returns_5` (utilise la validation via retriever → raise → exit 5).
     - `test_chat_help_works` (sous-commande listée dans `--help`).

### Étape 5 — Doc & polish

9. [x] **Étendre `docs/architecture.md:69`** : la ligne `agents/ supervisor, maths_agent, francais_agent` reste correcte (maths_agent arrive en s02, francais_agent en s05, supervisor en s05). Ajouter une ligne dans la section "Integration points" (l.270) pour le LLM provider OpenRouter si pertinent (optionnel — le tableau liste déjà "LLM provider"). Pas d'ADR nouveau pour s02 (les décisions s'inscrivent dans l'ADR 003 existant qui acte LangGraph pour le superviseur futur, et ADR 002 pour le POC rewrite qui acte l'usage de minimax).
10. [ ] **Étendre `docs/prd.md` § Stack** : confirmer la mention de OpenRouter comme routeur pour minimax (si la section existe déjà). Si la section n'existe pas, **skip** — pas dans le scope.

### Étape 6 — Vérification finale

11. [x] **Run global** : `cd backend && pytest --cov=app --cov-fail-under=80 -m "not integration"` (mêmes options que `.github/workflows/ci.yml:195`). **Vérification** : tous les tests passent, couverture ≥ 80%.
12. [x] **Lint** : `cd backend && ruff check app tests` (mêmes options que `.github/workflows/ci.yml:156`). **Vérification** : 0 erreur.
13. [ ] **Vérification manuelle** (à faire par un humain) :
    - `docker compose up -d seaweedfs postgres chroma` (SeaweedFS + Postgres + ChromaDB).
    - `python -m ktutor.cli upload tests/fixtures/sample_cours.pdf --pseudo ali --subject maths`.
    - `python -m ktutor.cli chat --pseudo ali --subject maths --question "Qu'est-ce qu'une dérivée ?"` → réponse + citation.
    - `python -m ktutor.cli chat --pseudo bob --subject maths --question "Qu'est-ce qu'une dérivée ?"` → "no document" (bob n'a rien uploadé).
    - `python -m ktutor.cli chat --pseudo ali --subject francais --question "Qu'est-ce qu'une dérivée ?"` → "no document" (ali n'a rien uploadé en français).

## Run interdicts

- **Ne PAS créer** de modèle SQLAlchemy `Conversation` ou `Message` (l'architecture cible les mentionne mais s09-s19 les créent). s02 est one-shot.
- **Ne PAS introduire** de streaming (SSE arrive en s09). s02 fait un print one-shot.
- **Ne PAS toucher** au superviseur LangGraph (s05). Le maths_agent est un appel LLM structuré, pas un state machine.
- **Ne PAS modifier** `backend/app/services/rag/ocr.py` (s01 intact).
- **Ne PAS modifier** `backend/app/services/rag/embeddings.py` au-delà de l'extension naturelle si nécessaire (préférer réutiliser le `build_embedding_provider` existant).
- **Ne PAS renommer** `ChromaStore` ou `MinioClient` (s01b les a figés).
- **Ne PAS ajouter** de client LLM minimax natif : on route via OpenRouter, point. Si l'utilisateur veut un client custom, c'est une autre story.
- **Ne PAS câbler** `ollama` : le support ollama nécessite `langchain-ollama` qui n'est pas dans requirements.txt. On lève `NotImplementedError` ; un ticket de suivi sera créé.
- **Ne PAS commit** depuis la base du repo. Tout le travail se fait dans `.worktrees/s02-chatter-avec-mon-cours/`.
- **Ne PAS push** vers `main` directement. PR obligatoire.
- **Ne PAS créer** d'ADR nouveau : les décisions LLM/Minimax/OpenRouter s'inscrivent dans l'ADR 002 (POC rewrite) qui acte déjà le provider minimax. Une mention dans cet ADR sera faite si nécessaire (en appendice).

## The point everything turns on

**Le retriever doit prendre `(subject, pseudo, question)` et JAMAIS `(collection_name, question)`**. C'est l'invariant multi-tenant. Si on accepte un nom de collection, on contourne la validation de pseudo et on permet un lookup cross-tenant.

**Trois endroits où ce plan peut se tromper** :

1. **Le câblage OpenRouter** : le modèle `minimax/minimax-m3:free` est gratuit sur OpenRouter au moment de la recherche, mais peut changer. La factory doit accepter un `llm_model` configurable, et un test runtime (non bloquant) vérifie que l'API répond. Si OpenRouter ne marche pas, le fallback est `openai` direct.
2. **Le `filename` dans la metadata** : la modification de `_to_chroma_dict` touche s01. Si les tests de s01 régressent, c'est un blocker. Le test `TestMetadata::test_filename_included_in_chroma_metadata` doit être ajouté dans la même tâche que la modif.
3. **Le prompt "no general knowledge"** : sans un prompt système strict, le LLM peut halluciner même avec des chunks pertinents. Le test `test_system_prompt_forbids_general_knowledge` doit verrouiller la formulation. Si le LLM ne respecte pas le prompt (cas réel avec certains modèles), c'est un signal d'ajuster le prompt, pas d'assouplir le test.

## Files touched

**Code (5 fichiers modifiés, 4 nouveaux)** :
- `backend/app/core/config.py` (modifié, +6 lignes)
- `backend/.env.example` (modifié, +6 lignes)
- `backend/app/services/rag/upload_service.py` (modifié, 1-2 lignes)
- `backend/app/cli.py` (modifié, +50 lignes pour la commande `chat`)
- `backend/app/services/llm/__init__.py` (nouveau)
- `backend/app/services/llm/client.py` (nouveau, ~50 lignes)
- `backend/app/services/rag/retriever.py` (nouveau, ~60 lignes)
- `backend/app/services/agents/__init__.py` (nouveau)
- `backend/app/services/agents/maths_agent.py` (nouveau, ~80 lignes)

**Test (4 nouveaux, 1 étendu)** :
- `backend/tests/services/rag/test_retriever.py` (nouveau, 5 tests)
- `backend/tests/services/agents/test_maths_agent.py` (nouveau, 7 tests)
- `backend/tests/services/llm/test_client.py` (nouveau, 3 tests)
- `backend/tests/services/rag/test_upload_service.py` (étendu, +1 test metadata)
- `backend/tests/cli/test_cli.py` (étendu, +5 tests chat)
- `backend/tests/core/test_config.py` (étendu, +2 tests config)

**Doc (1 fichier mineur)** :
- `docs/architecture.md` (modifié, 1 ligne : confirmer l'emplacement de `services/llm/`)

**Non touchés** :
- `backend/app/services/storage/minio_client.py` (s01, intact)
- `backend/app/services/rag/ocr.py` (s01, intact)
- `backend/app/services/rag/embeddings.py` (s01, intact — réutilisé tel quel)
- `backend/app/services/storage/__init__.py` (s01b, intact)
- `backend/app/core/database/models.py` (s01, intact — pas de modèle `Conversation`/`Message` en s02)
- `backend/tests/fixtures/seaweedfs/` (s01b, intact)
- `backend/app/services/agents/supervisor.py` (n'existe pas, s05)
- `backend/app/services/agents/francais_agent.py` (n'existe pas, s05)
- Tous les docs/plans/research/reviews des stories s01 et s01b (figés)

## Test strategy

### Tests automatisés (un par AC)

| AC | Test | Couche |
|---|---|---|
| AC1 (CLI retourne réponse ancrée) | `test_cli.py::TestChat::test_chat_returns_zero_with_answer` | CLI |
| AC2 (réponse cite au moins une source) | `test_maths_agent.py::TestAsk::test_ask_returns_answer_citing_sources` + `test_citation_format_locked` | Agent |
| AC3 (no document si pas de chunks) | `test_maths_agent.py::TestAsk::test_ask_with_empty_collection_returns_no_document_message` | Agent |
| AC4 (LLM provider env) | `test_client.py::TestFactory::test_factory_picks_provider_from_settings` | Client |
| AC5 (CLI exit 0) | `test_cli.py::TestChat::test_chat_returns_zero_with_answer` | CLI |
| AC6 (cross-tenant) | `test_retriever.py::TestQuery::test_query_cross_tenant_isolation` + `test_maths_agent.py::TestAsk::test_cross_tenant_isolation_at_agent_level` | Retriever + Agent |
| AC7 (no document sans upload) | `test_retriever.py::TestQuery::test_query_with_empty_collection_returns_empty_list` | Retriever |

### Vérification de la cohérence d'API

- Tests de l'embedder : vérifier que `Retriever.query` appelle `embeddings.embed_documents` une fois avec une liste d'un élément (la question).
- Tests du retriever : vérifier que `Retriever.query` appelle `chroma_store.get_collection(subject, pseudo)` (pas `list_collections_for_pseudo`).
- Tests de l'agent : vérifier que le prompt système contient les instructions de citation.
- Tests du client LLM : vérifier que `build_llm_client` lève `NotImplementedError` pour `ollama`, retourne un wrapper pour `minimax` et `openai`.

### Bites de régression (à faire en fin d'implémentation)

- Muter `Retriever.query` pour ne pas appeler `get_collection` (mais `list_collections_for_pseudo`) → test cross-tenant rouge. Restaurer.
- Muter `MathsAgent.ask` pour ne pas injecter les chunks dans le prompt → test `test_system_prompt_forbids_general_knowledge` rouge (vérifier que les chunks sont bien dans le user prompt, pas seulement le system prompt). Restaurer.
- Muter le format de citation pour utiliser `page` au lieu de `chunk` → test `test_citation_format_locked` rouge. Restaurer.

### Vérification manuelle (humain)

- Uploader un PDF puis chatter — vérifier la réponse et la citation.
- Chatter sans upload — vérifier le fallback.
- Chatter avec un autre pseudo — vérifier l'isolation.
- Avec `LLM_PROVIDER=openai OPENAI_API_KEY=<key>` : vérifier que le client openai est bien utilisé (changer le modèle en `gpt-4o-mini` temporairement).

### Pas de test d'intégration avec vrai LLM (best-effort)

L'intégration avec un vrai LLM via OpenRouter ou OpenAI est best-effort, marqué `@pytest.mark.integration`, non bloquant pour la PR.

## Definition of Done

(Reprend la DoD du repo, spécialisée pour s02)

- [ ] Toutes les tâches cochées.
- [ ] `pytest --cov=app --cov-fail-under=80 -m "not integration"` passe (≥ 80% de couverture).
- [ ] `ruff check app tests` passe (0 erreur).
- [ ] AC1-AC7 tous couverts par des tests.
- [ ] Test cross-tenant (`test_maths_agent.py::test_cross_tenant_isolation_at_agent_level`) vert.
- [ ] Test "no document" (`test_maths_agent.py::test_ask_with_empty_collection_returns_no_document_message`) vert.
- [ ] Format de citation `[source: filename, chunk N]` verrouillé par constante et test regex.
- [ ] Prompt système contient l'instruction d'ancrage strict.
- [ ] Temperature 0 par défaut (test vérifie).
- [ ] CLI `chat` exit 0 en cas de succès ou "no document" ; exit 5 si pseudo invalide.
- [ ] Multi-tenancy : le retriever n'accepte jamais un `collection_name` (seulement `(subject, pseudo)`).
- [ ] PR unique, description structurée : résumé, AC cochées, points d'attention (notamment la modif de s01 pour `filename` et la non-câblure d'ollama).
- [ ] `git diff main...feature/s02-chatter-avec-mon-cours` est lisible.
- [ ] Review passée (`docs/reviews/s02-chatter-avec-mon-cours.md` avec `Ship allowed: yes`).

<< IP Mike: task granularity, what a good plan contains/avoids. >>
