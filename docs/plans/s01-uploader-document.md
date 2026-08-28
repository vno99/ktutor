---
validated: yes
---
# Plan — Story s01-uploader-document

> Branch: `feature/s01-uploader-document`
> Research: `docs/research/s01-uploader-document.md` — read it first; this plan does not repeat it.
> Design: `docs/designs/s01-uploader-document.md` (mockup CLI + tokens).
> Open questions tranchées : voir section « Décisions verrouillées en planification ».

## Target story

> **As an** élève **I want** téléverser un PDF ou une image (dactylo ou manuscrite) **so that** le système l'indexe dans mon RAG personnel.

**Acceptance criteria (verbatim) :**

- AC1. Uploading a valid PDF (≤ 20MB) extracts its text, chunks it (`RecursiveCharacterTextSplitter`, `chunk_size=1000`, `overlap=200`), embeds it, and stores the vectors in a ChromaDB collection named `rag_maths_<pseudo>` (one collection per student).
- AC2. Uploading a typed image (PNG/JPG) calls the multimodal LLM to OCR the text, then runs the same pipeline.
- AC3. Uploading a handwritten image calls the multimodal LLM with vision capability; if text is recognized, the same pipeline runs.
- AC4. An invalid upload (file > 20MB, unsupported format, corrupted) returns a clear error and persists nothing.
- AC5. The CLI command `python -m ktutor.cli upload <file> --pseudo <p> --subject maths` returns 0 on success and a documented non-zero code with a message on failure.
- AC6. A success upload creates a `Document` row in PostgreSQL (metadata) and a populated ChromaDB collection (vectors).
- AC7. A test using two different pseudos verifies that documents uploaded by `pseudo_a` are NOT retrievable from `pseudo_b`'s collection (multi-tenant isolation).

## Décisions verrouillées en planification

Issues des open questions de la research + une dette pré-existante. Ces choix sont **figés pour ce plan**. Tout écart doit être justifié dans une review.

| # | Question | Décision | Justification |
|---|---|---|---|
| D1 | Provider LLM pour la vision OCR (Mistral n'a pas de vision native) | **`VISION_PROVIDER=deepseek-ocr-2` par défaut**. | Modele libre, gratuit, hébergé en local dans un premier temps |
| D2 | Stockage du fichier source (MinIO en s01 ou reporté) | **MinIO dès s01**, préfixe `students/<pseudo>/<document_id>`. | Cohérent avec ADR 001, archi § Multi-tenancy, AGENTS.md § Multi-tenancy. Migrer plus tard = dette. Fait l'objet d'un ADR (cf. § ADR à créer). |
| D3 | Corpus de test (Sésamath vs synthétique) | **Synthétique** : un PDF généré (3 pages de maths), une image PNG avec du texte tapé, une image PNG « manuscrit simulé » (texte rendu en Comic Sans sur fond papier). Pas de téléchargement externe. | Tests déterministes, offline, hermétiques. Sésamath est un téléchargement externe et alourdit la CI. |
| D4 | Validation du format `--pseudo` au niveau CLI | **Rejet strict** : `^[a-zA-Z0-9_]{3,32}$`. Code retour 5 si invalide, avec message qui affiche la regex attendue. | Évite la pollution des noms de collection ChromaDB. Cohérent avec s12 (story future qui revalidera côté API). |
| D5 | Tests PostgreSQL (testcontainers vs mock) | **Mock du `Session` SQLAlchemy pour les tests unitaires**. Test d'intégration Postgres dans une story future (pas bloquant pour s01). | Les tests d'isolation cross-tenant (AC7) ciblent ChromaDB, pas Postgres. AC6 teste la **création** d'une row, pas une requête complexe — mockable trivialement. |
| D6 | CLI framework (`typer` vs `click` vs `argparse`) | **`typer`**. | Plus moderne, intégration Pydantic, autocomplétion shell, docstring auto-générée (`--help`). `click` est plus mature mais verbeux. `argparse` est trop bas niveau. |
| D7 | Bibliothèque de sortie terminal (`rich` vs ANSI brut) | **`rich`**. | Requis pour respecter les tokens du design system (couleurs, mono, spinner). Cf. design. |
| D8 | Dette `.gitignore` racine | **Créer `.gitignore` en pré-tâche** (avant tout commit). Inclut : `.env`, `__pycache__/`, `*.pyc`, `chroma_data/`, `node_modules/`, `.next/`, `keys/`, `.venv/`, `venv/`, `data/postgres/`, `data/redis/`, `data/minio/`, `.pytest_cache/`, `*.egg-info/`, `dist/`, `build/`. | Le `worktree-manager` a confirmé l'absence de `.gitignore`. `.env` est exposé. Bloque le premier commit. |

## ADR à créer pendant l'exécution

- **ADR 007 — Stockage MinIO dès s01 vs reporté** (`docs/decisions/007-minio-from-s01.md`) — formalise la décision D2. Tracé ici car le plan le déclenche et le commit de l'ADR voyage avec la branche feature.
- **ADR 008 — Provider vision DeepSeek-OCR-2 vs GPT-4o / Gemini** (`docs/decisions/008-deepseek-ocr-2-for-vision.md`) — formalise la décision D1. ⚠️ Cet ADR **supersede** partiellement `docs/architecture.md` § Stack qui mentionnait « Vision LLM : GPT-4o / Gemini ». Le PRD ne tranche pas entre les providers vision ; ce plan diverge de l'archi pour des raisons de coût (gratuit vs payant) et de localité. L'ADR expose les options (DeepSeek-OCR-2 vs OpenAI GPT-4o vs Gemini) et justifie le choix. La conséquence pratique : la couche OCR de s01 utilise `httpx` vers `http://localhost:8500`, pas `ChatOpenAI(model="gpt-4o")`. Si une future story veut GPT-4o, elle créera un ADR qui supersede ADR 008.

## Tasks (ordered)

1. [x] **Créer `.gitignore` à la racine** avec le contenu défini en D8. Vérifier que `git check-ignore .env` retourne exit 0 après création. _AC couverts : dette pré-existante, blocage du commit._
2. [x] **Initialiser le backend Python** : créer `backend/pyproject.toml` (ou `backend/requirements.txt` + `backend/setup.py` minimal), `backend/Dockerfile`, `backend/app/__init__.py`, `backend/app/core/__init__.py`, `backend/app/core/config.py` (Pydantic Settings), `backend/app/core/logging.py` (loguru JSON structuré), `backend/app/core/database/__init__.py`. _AC couverts : pré-tâche technique, fondation config._
3. [x] **Ajouter `docker-compose.yml` à la racine** avec les services `postgres`, `redis`, `minio`, `chroma` (image `chromadb/chroma:latest` ou Chroma en mode server), avec volumes nommés et ports. Healthchecks sur postgres et chroma. Variables d'env alignées sur `backend/app/core/config.py`. _AC couverts : pré-tâche « PostgreSQL + ChromaDB running locally »._
4. [x] **Ajouter `backend/.env.example`** (committé, sans secret) listant toutes les variables lues par `config.py` : `DATABASE_URL`, `CHROMA_PERSIST_DIRECTORY`, `CHROMA_SERVER_URL`, `VISION_PROVIDER=deepseek-ocr-2`, `DEEPSEEK_OCR_URL=http://localhost:8500`, `DEEPSEEK_OCR_TIMEOUT=60`, `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MAX_UPLOAD_SIZE_MB=20`, `LLM_PROVIDER`, `OPENAI_API_KEY` (uniquement pour les embeddings en fallback, pas la vision). Documenter en commentaire chaque variable. _AC couverts : onboarding dev, pas de secret commité, D1._
5. [x] **Modèle SQLAlchemy `Document`** dans `backend/app/core/database/models.py` : `id: UUID` (PK, default `uuid4`), `student_pseudo: str` (FK vers `users.pseudo`, indexé), `subject: str` (enum `maths|francais`), `filename: str`, `minio_key: str`, `chunks_count: int`, `status: str` (enum `indexed|error|manual_review_needed`), `error_reason: str | None`, `created_at: datetime`. Modèle `Base` partagé. La table `users` n'existe pas encore (s12), donc on documente la FK en string et on crée la contrainte en commentaire (la contrainte sera ajoutée en s15 par Alembic). _AC couverts : AC6, préparation de la FK pour s12/s15._
6. [x] **Session DB et init du schéma** dans `backend/app/core/database/session.py` : `engine = create_engine(DATABASE_URL, pool_size=20)`, `SessionLocal = sessionmaker(...)`, `get_db()` FastAPI dependency (préparée mais inutilisée en s01), `init_db()` qui appelle `Base.metadata.create_all(engine)` au démarrage de la CLI. _AC couverts : AC6._
7. [x] **MinIO client** dans `backend/app/services/storage/minio_client.py` : `class MinioClient` avec `__init__(endpoint, access_key, secret_key, bucket)`, méthode `ensure_bucket()`, méthode `put_object(pseudo: str, document_id: UUID, filename: str, data: bytes) -> str` (retourne la clé `students/<pseudo>/<document_id>`), méthode `get_object(minio_key: str) -> bytes`. Le bucket est créé au démarrage de la CLI. _AC couverts : AC6, D2._
8. [x] **Embeddings wrapper** dans `backend/app/services/rag/embeddings.py` : `class EmbeddingProvider` qui abstrait FastEmbed (par défaut, via `fastembed.TextEmbedding(model="BAAI/bge-small-en-v1.5", dim=384)`) et OpenAI (fallback si `LLM_PROVIDER=openai` + `OPENAI_API_KEY` défini, via `langchain_openai.OpenAIEmbeddings`). Méthode `embed_documents(texts: list[str]) -> list[list[float]]` synchrone. _AC couverts : AC1, D1 (vision séparée)._
9. [x] **ChromaDB store avec isolation multi-tenant** dans `backend/app/services/rag/chroma_store.py` : `class ChromaStore` qui wrap `chromadb.PersistentClient(path=...)`. Méthode `get_collection(subject: str, pseudo: str) -> Collection` qui (a) valide le pseudo via la regex `^[a-zA-Z0-9_]{3,32}$` (lève `ValueError` sinon, mappé vers code 5), (b) construit le nom `rag_<subject>_<pseudo>`, (c) appelle `get_or_create_collection(name=..., embedding_function=...)` en passant l'`EmbeddingProvider` (mais on n'utilise pas l'embedding côté ChromaDB car on embed déjà — `embedding_function=None` et on stocke les vecteurs pré-calculés). Méthode `add_chunks(collection, chunks: list[dict])` qui itère et appelle `collection.add(ids=..., embeddings=..., documents=..., metadatas=...)`. _AC couverts : AC1, AC6, AC7, D4._
10. [x] **Ingestion PDF** dans `backend/app/services/rag/ingestion.py` : `class DocumentIngestor` avec méthode `ingest(file_path: str) -> list[Document]` qui (a) ouvre le PDF via `PyMuPDFLoader`, (b) vérifie la longueur du texte extrait (si < 50 chars → bascule vers OCR), (c) split via `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, separators=["\n\n", "\n", " ", ""])`, (b) ajoute les métadonnées `chunk_index` et `document_id` à chaque chunk. Retourne des objets Pydantic `Chunk(content, metadata)` typés. _AC couverts : AC1, trap « PDF scanné »._
11. [x] **OCR multimodal** dans `backend/app/services/rag/ocr.py` : `class MultimodalOcr` avec méthode `transcribe_image(image_path: str) -> OcrResult`. Construit un client HTTP (`httpx`) vers le service DeepSeek-OCR-2 local (`DEEPSEEK_OCR_URL` env, défaut `http://localhost:8500`), envoie l'image encodée base64 + un prompt d'instructions strict exigeant un JSON `{"transcription": str, "type": "texte|mathematique|mixte", "confidence": float, "has_math": bool}`. Parsing strict avec regex `\{.*\}` (retry une fois avec prompt plus strict si pas de JSON, puis `OcrError`). Si `confidence < 0.5` ou `transcription` vide → retourne `OcrResult(ok=False, reason="low_confidence", confidence=...)`. _AC couverts : AC2, AC3, D1, trap « manuscrit à faible confiance »._
12. [x] **Service d'upload orchestré** dans `backend/app/services/rag/upload_service.py` : `class UploadService` qui orchestre les 4 services. Méthode `upload(file_path: str, pseudo: str, subject: str) -> UploadResult` : (1) valide le pseudo (regex) → code 5 si KO, (2) vérifie la taille du fichier (≤ 20 Mo) → code 2 si KO, (3) vérifie le format (`.pdf`, `.png`, `.jpg`, `.jpeg`) → code 2 si KO, (4) upload le fichier dans MinIO (`MinioClient.put_object`), (5) ingère via `DocumentIngestor` (PDF) ou `MultimodalOcr.transcribe_image` puis `DocumentIngestor.ingest` (image), (6) embed via `EmbeddingProvider`, (7) ajoute à la collection ChromaDB via `ChromaStore.add_chunks`, (8) crée la row `Document` en PostgreSQL (status=`indexed` ou `manual_review_needed`), (9) retourne `UploadResult(document_id, chunks_count, duration_ms, status)`. **Si une étape échoue APRÈS l'upload MinIO, on supprime l'objet MinIO** (rollback) pour respecter AC4 « persists nothing ». _AC couverts : AC1, AC2, AC3, AC4, AC6._
13. [x] **CLI avec `typer` et sortie `rich`** dans `backend/app/cli.py` : application `typer.Typer()`. Commande `upload(file: Path, pseudo: str, subject: str, quiet: bool = False, json_output: bool = False)`. Sortie via `rich.console.Console` : spinner ligne par ligne (états 1→2 du design), puis bloc de paires `clé : valeur` alignées (état 3). Mode `--json` : retourne `{"status": "indexed", "document_id": "...", "chunks_count": 87, "duration_ms": 4200}`. Code retour `0` sur succès et `manual_review_needed` ; `1` erreur générique ; `2` fichier invalide ; `3` OCR échec ; `4` erreur ChromaDB/PostgreSQL ; `5` pseudo invalide. `python -m ktutor.cli` doit fonctionner → ajouter `backend/app/__main__.py` qui importe `cli:app`. _AC couverts : AC4, AC5, design § Tech mapping, design § States 1-5._
14. [x] **ADR 007 et ADR 008** : (a) **ADR 007 — MinIO dès s01** dans `docs/decisions/007-minio-from-s01.md` (MADR, options « local filesystem » vs « MinIO dès s01 » vs « reporter à s10 »), tracer la décision D2. (b) **ADR 008 — DeepSeek-OCR-2 pour la vision** dans `docs/decisions/008-deepseek-ocr-2-for-vision.md` (MADR, options « OpenAI GPT-4o » vs « Gemini » vs « DeepSeek-OCR-2 »), tracer la décision D1 et le supersede partiel de `docs/architecture.md` § Stack. _AC couverts : traçabilité décisions, divergence archi actée._
15. [x] **Tests unitaires** :
    - `backend/tests/core/test_config.py` — vérifie que les variables d'env sont lues et validées au démarrage.
    - `backend/tests/services/rag/test_chroma_store.py` — vérifie que `get_collection("maths", "ali")` retourne bien la collection `rag_maths_ali` ; **AC7 vérifié ici** : un `client_a` ne peut pas voir les chunks du `client_b` car ce sont deux collections distinctes (test avec `chromadb.EphemeralClient()`).
    - `backend/tests/services/rag/test_ocr.py` — stub du service DeepSeek-OCR-2 (via `httpx.AsyncClient` mocké par `respx` ou `httpx.MockTransport`), vérifie le parsing strict du JSON, le retry, et le seuil `confidence < 0.5` → `OcrResult(ok=False)`.
    - `backend/tests/services/rag/test_ingestion.py` — vérifie le split (`chunk_size=1000`, `overlap=200`), la détection PDF scanné (texte court → bascule OCR, mocké).
    - `backend/tests/services/rag/test_upload_service.py` — mock de `MinioClient`, `EmbeddingProvider`, `ChromaStore`, mock du `Session` SQLAlchemy (D5). Vérifie AC4 : un échec en milieu de pipeline supprime l'objet MinIO (rollback testé). Vérifie AC6 : succès crée la row `Document` en PostgreSQL. Vérifie les codes retour 0, 2, 3, 4, 5.
    - `backend/tests/cli/test_cli.py` — invocation de `python -m ktutor.cli upload …` via `subprocess` ou `typer.testing.CliRunner`, vérifie les codes retour, vérifie la sortie JSON avec `--json`.
    - Fixture `conftest.py` : PDF synthétique de 3 pages (maths : dérivées), PNG avec texte tapé, PNG « manuscrit simulé », fichier trop gros (25 Mo généré en `tmp_path`), fichier invalide (`.exe`). _AC couverts : tous (1 par test)._
16. [x] **Validation finale** : `pytest` depuis `backend/` doit être vert ; `python -m ktutor.cli upload --help` doit afficher l'aide ; `python -m ktutor.cli upload <pdf_test> --pseudo ali --subject maths` doit retourner 0 et indexer dans ChromaDB (test d'intégration manuel rapide, docker-compose pas obligatoire pour s01 — un test isolé ChromaDB éphémère suffit). Vérifier que `git status` ne liste pas `.env` après l'ajout du `.gitignore`.

**Nombre de tâches : 16.** Légèrement au-dessus de la guideline « ~10 tâches », justifié par :

- 4 pré-tâches techniques (gitignore, init backend, docker-compose, .env.example) qui sont des fondations mais qui doivent être chacune vérifiables ;
- 1 service par tâche (ingestion, OCR, embeddings, ChromaDB, MinIO, upload orchestré, CLI) — la séparation est nécessaire pour la testabilité ;
- les tests sont consolidés en une seule tâche (15) parce qu'ils partagent la fixture `conftest.py`.

Un découpage plus fin créerait des tâches « créer un fichier vide » qui ne sont pas des incréments livrables. Le plan reste à la limite supérieure de la guideline mais ne la dépasse pas. **Pas de split nécessaire.**

## Run interdicts

- **Ne pas toucher `src/`, `test_quick.py`, `DeepSeek-OCR-2/`, `deepseek-ocr-python/`** : ce sont des dossiers non trackés (hérités de l'époque POC, ADR 002 dit « on réécrit »). Les laisser tranquilles, ils ne sont pas dans le scope de s01 et seront nettoyés par une story de ménage future.
- **Ne pas committer `.env`** : le `.gitignore` créé en tâche 1 l'exclut. Si l'agent d'exécution voit `.env` dans `git status`, c'est un signal d'alarme.
- **Ne pas créer `frontend/`** : hors scope de s01. Le frontend arrive en s11.
- **Ne pas créer `app/api/`** : pas de FastAPI en s01. Le CLI est le seul point d'entrée.
- **Ne pas installer les dépendances globalement** : tout dans `backend/.venv` ou un container. `pip install` depuis la racine du repo est interdit.
- **Ne pas écrire de logique métier dans `cli.py`** : la CLI ne fait que de l'orchestration de présentation. Toute la logique est dans `backend/app/services/`.
- **Ne pas mocker le LLM dans les tests d'intégration** (s'il y en a) : pour les tests d'intégration OCR, marquer `@pytest.mark.integration` et les skipper par défaut (`-m "not integration"`).
- **Ne pas inventer un composant UI** : s01 n'a pas d'UI. Si l'agent pense avoir besoin d'un composant, c'est qu'il sort du scope.

## The point everything turns on

**Le pipeline s'effondre si l'OCR multimodal n'est pas testable hermétiquement.**

Ce plan suppose qu'on peut stub le service DeepSeek-OCR-2 (via `httpx` mocké ou via un fake client) pour tester le parsing strict du JSON, le retry, et le seuil de confiance. Si le code de l'OCR s'avère trop couplé au service DeepSeek réel au point de ne pas accepter un fake, les tests AC2/AC3 ne passent pas et on ne peut pas shipper. **Conséquence du choix D1** : on n'utilise plus `FakeListLLM` de LangChain (puisque l'OCR passe par `httpx`, pas par un `ChatModel`). Les tests doivent mocker `httpx.AsyncClient.post`.

**Deux endroits où ça peut casser :**

1. Le parsing JSON de la réponse DeepSeek-OCR-2 (tâche 11) — si la regex `{.*}` rate des cas (service qui préfixe avec prose, qui suffixe avec du markdown), le retry ne suffit pas et on tombe en `OcrError`. **À comparer contre** : la sortie réelle de DeepSeek-OCR-2 sur un échantillon de 3-5 cas de test, enregistrée dans `tests/fixtures/ocr_responses/` (captures réelles ou simulées). Si DeepSeek-OCR-2 ne retourne pas du JSON nativement, il faut ajouter une étape de structuration par un LLM léger (Minimax-M3) — c'est une dette architecturale à acter en review.
2. Le calcul du `confidence` retourné par le service (tâche 11) — si DeepSeek-OCR-2 est incohérent ou ne fournit pas de champ `confidence` nativement, le seuil 0.5 n'est pas stable. **À comparer contre** : un test manuel sur 5 images variées, et un ajustement éventuel du prompt ou un fallback heuristique (longueur de la transcription, présence de blocs LaTeX).

Si ces deux points cassent en planification, le plan propose le split **s01a (PDF + image dactylo)** / **s01b (OCR manuscrit)** comme repli. Mais on tente l'OCR complet d'abord.

## Files touched

**Créés :**

- `.gitignore` (racine)
- `docker-compose.yml` (racine) — services postgres, redis, minio, chroma
- `backend/requirements.txt`
- `backend/pyproject.toml` (optionnel, pour `ktutor = "app.cli:app"` entry-point — peut être reporté si on utilise `python -m backend.app.cli`)
- `backend/Dockerfile`
- `backend/.env.example`
- `backend/app/__init__.py`
- `backend/app/__main__.py` (permet `python -m ktutor.cli`)
- `backend/app/cli.py`
- `backend/app/core/__init__.py`
- `backend/app/core/config.py`
- `backend/app/core/logging.py`
- `backend/app/core/database/__init__.py`
- `backend/app/core/database/models.py`
- `backend/app/core/database/session.py`
- `backend/app/services/__init__.py`
- `backend/app/services/rag/__init__.py`
- `backend/app/services/rag/ingestion.py`
- `backend/app/services/rag/ocr.py`
- `backend/app/services/rag/embeddings.py`
- `backend/app/services/rag/chroma_store.py`
- `backend/app/services/rag/upload_service.py`
- `backend/app/services/storage/__init__.py`
- `backend/app/services/storage/minio_client.py`
- `backend/tests/__init__.py`
- `backend/tests/conftest.py`
- `backend/tests/core/test_config.py`
- `backend/tests/services/rag/test_chroma_store.py`
- `backend/tests/services/rag/test_ocr.py`
- `backend/tests/services/rag/test_ingestion.py`
- `backend/tests/services/rag/test_upload_service.py`
- `backend/tests/cli/test_cli.py`
- `backend/tests/fixtures/sample_cours.pdf` (généré en conftest)
- `backend/tests/fixtures/sample_typed.png` (généré en conftest)
- `backend/tests/fixtures/sample_handwritten.jpg` (généré en conftest)
- `docs/decisions/007-minio-from-s01.md`

**Modifiés :** aucun (le repo est greenfield, pas de code préexistant à modifier).

**Non touchés (interdits) :** `src/`, `test_quick.py`, `DeepSeek-OCR-2/`, `deepseek-ocr-python/`, `docs/prd.md`, `docs/stories.md`, `docs/architecture.md`, `docs/design-system.md`, `docs/research/`, `docs/designs/`.

## Test strategy

| Couche | Quoi | Comment |
|---|---|---|
| **Unitaire — config** | Variables d'env lues, validation Pydantic, défaut de `MAX_UPLOAD_SIZE_MB=20` | `pytest` + `monkeypatch.setenv` |
| **Unitaire — ChromaStore** | Nommage `rag_<subject>_<pseudo>`, isolation cross-tenant, regex de validation du pseudo | `chromadb.EphemeralClient()` + 2 pseudos |
| **Unitaire — OCR** | Parsing JSON strict, retry sur réponse non-JSON, `confidence < 0.5` → `OcrResult(ok=False)` | `httpx.MockTransport` (ou `respx`) avec 3 scénarios : JSON valide, pas de JSON, confidence basse. Le service DeepSeek-OCR-2 est appelé via `httpx.AsyncClient`, pas via LangChain. |
| **Unitaire — Ingestion** | Split `chunk_size=1000`, `overlap=200`, détection PDF scanné (texte court → OCR mocké) | Fixture PDF + mock OCR |
| **Unitaire — UploadService** | Orchestration, rollback MinIO sur échec, codes retour 0/2/3/4/5, création row `Document` | Mocks de tous les services ; mock du `Session` SQLAlchemy (D5) |
| **Unitaire — MinIO** | `put_object` construit la bonne clé, `ensure_bucket` idempotent | `minio.Minio` mocké (pas de MinIO de test en s01) |
| **CLI** | `python -m ktutor.cli upload …` retourne 0, `--json` retourne du JSON, `--help` fonctionne | `typer.testing.CliRunner` |
| **Multi-tenant (AC7)** | `pseudo_a` ne peut pas voir les chunks de `pseudo_b` | Test d'isolation via `EphemeralClient`, déjà couvert dans `test_chroma_store.py` |

**Pas de test d'intégration** avec Postgres, MinIO, Chroma-server, ou vrai LLM en s01 (volontairement, pour rester hermétique et rapide). Les stories ultérieures ajouteront des tests d'intégration.

**Coverage cible** : ≥ 80 % sur `backend/app/services/rag/` (les modules les plus testés). Vérifié par `pytest --cov`.

## Definition of Done

- [ ] Toutes les tâches cochées.
- [ ] `pytest` depuis `backend/` est vert (≥ 80 % coverage sur `services/rag/`).
- [ ] `python -m ktutor.cli --help` et `python -m ktutor.cli upload --help` affichent l'aide correctement.
- [ ] Test manuel rapide : `python -m ktutor.cli upload tests/fixtures/sample_cours.pdf --pseudo ali --subject maths` retourne 0 et crée une collection `rag_maths_ali` (ChromaDB éphémère ou local).
- [ ] `git status` ne liste pas `.env`, `__pycache__/`, `chroma_data/`, etc.
- [ ] ADR 007 et ADR 008 commités dans `docs/decisions/`.
- [ ] Le diff `main..feature/s01-uploader-document` montre : `.gitignore`, `docker-compose.yml`, `backend/` (complet), `docs/decisions/007-*.md`, et **rien d'autre** (pas de modif sur `docs/architecture.md`, `docs/stories.md`, etc.).
- [ ] Au moins un test d'isolation cross-tenant (AC7) dans la suite.
- [ ] Pas de régression sur le code existant (il n'y en a pas, mais c'est documenté).
- [ ] PR ouverte vers `main` (mode manuel par défaut).
