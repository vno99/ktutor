# Research — Story s01-uploader-document

> Date : 2026-08-28
> Workspace : `.worktrees/s01-uploader-document` (branche `feature/s01-uploader-document`, HEAD `2401dfd`)
> Verdict stories : `Stories ready: yes` (review précédente OK, max severity: minor)

## The five structuring facts

1. **L'ADR 002 a acté la réécriture from-scratch du POC Python.** `main` ne contient **aucun** code backend/frontend — ni `src/`, ni `requirements.txt`, ni `docker-compose.yml` tracké (vérifié par `git ls-files` dans le worktree). Le POC initial a été supprimé du tracking mais pas re-créé. Conséquence : s01 doit créer le monorepo `backend/`/`frontend/` de zéro. Le code POC n'est plus une hypothèse de départ, c'est un souvenir de référence.
2. **Le worktree a un `.env` non tracké** avec `LLM_PROVIDER=mistral`, `MISTRAL_API_KEY=…`. Mais l'architecture (ADR 002, `CLAUDE.md`, `AGENTS.md` § Technical conventions) impose `LLM_PROVIDER=minimax` (Minimax-M3, gratuit) comme défaut. **Tension documentée** : le `.env` est soit hérité de l'époque POC, soit laissé tel quel par défaut. À trancher en planification : quel provider LLM par défaut, et quel embedding (FastEmbed local vs Mistral embed vs OpenAI).
3. **Pas de `.gitignore` à la racine.** `.env` apparaît comme fichier non-tracké. Le `worktree-manager` l'a confirmé : `git check-ignore .env` retourne exit 1. Conséquence sécurité : un commit accidentel du `.env` révélerait la clé Mistral. **Pré-tâche obligatoire** : créer un `.gitignore` AVANT le premier commit de s01 (inclure `.env`, `__pycache__/`, `chroma_data/`, `node_modules/`, `keys/`, etc.).
4. **ChromaDB n'est pas dans le `docker-compose.yml` du POC d'origine** (qui n'est plus tracké) et n'est pas non plus dans le `main` actuel. Mais `docs/architecture.md` § Integration points liste ChromaDB comme service docker-compose. Donc s01 doit l'ajouter. Cohérence à vérifier : `docker-compose.yml` n'existe plus en tracké non plus (`git ls-files` ne le montre pas).
5. **Pas de pré-tâche « FastAPI » dans les dépendances de s01.** La story s01 livre un CLI (`python -m ktutor.cli upload …`). L'API arrive en s09. Donc s01 n'a pas besoin de FastAPI — uniquement : `chromadb`, `pymupdf`, `langchain` (text splitter + loaders), `pydantic`, `python-dotenv`, `psycopg` (pour la row `Document`), `sqlalchemy`, `alembic` (init du schéma), `typer` (CLI propre), et le provider d'embedding (FastEmbed par défaut).

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

## Current state of the code

État du worktree (vérifié sur `2401dfd`) :

- `git ls-files` retourne **uniquement** : `AGENTS.md`, `README.md`, `docs/architecture.md`, `docs/decisions/*`, `docs/design-system.md`, `docs/prd.md`, `docs/reviews/stories.md`, `docs/roadmap.md`, `docs/stories.md`. Soit 14 fichiers. Tout le reste (POC, `docker-compose.yml`, `requirements.txt`, `src/`, `test_quick.py`, `DeepSeek-OCR-2/`, `deepseek-ocr-python/`) n'est pas tracké.
- Aucun `backend/`, aucun `frontend/`, aucun `tests/`, aucun `requirements.txt`, aucun `docker-compose.yml`, aucun `pyproject.toml` tracké.
- Le seul code Python exécutable référencé est dans `templates/` (juste des `.md`) et le skill `.claude/skills/agentic-stories/SKILL.md` (markdown, pas du code de prod).
- Le `.env` non-tracké est la seule configuration présente.

**Conclusion factuelle :** la prémisse de s01 (créer un CLI d'upload qui parle à ChromaDB et PostgreSQL) est valide puisque le code sera créé par s01. **Aucun code existant à modifier** pour s01 — uniquement à créer. C'est une story greenfield.

## Anchor points (où s01 branche)

| Cible | Fichier à créer | Justification |
|---|---|---|
| Point d'entrée CLI | `backend/app/cli.py` (puis `backend/app/__main__.py` pour `python -m ktutor`) | Convention imposée par `docs/architecture.md` § Repo structure |
| Configuration | `backend/app/core/config.py` (Pydantic Settings) | Convention `docs/architecture.md` § Patterns |
| Modèle `Document` | `backend/app/core/database/models.py` (SQLAlchemy) | Schéma décrit dans `docs/architecture.md` § Data model |
| Init schéma DB | `backend/alembic/`, `backend/alembic.ini` | Alembic migrations |
| Connexion DB | `backend/app/core/database/session.py` | Engine SQLAlchemy |
| Ingestion PDF | `backend/app/services/rag/ingestion.py` | Agentic notes s01 |
| OCR multimodal | `backend/app/services/rag/ocr.py` (réécrit from scratch, plus simple que l'ancien `multimodal_ocr.py` qui dépendait de GPT-4o) | Agentic notes s01 |
| Embeddings | `backend/app/services/rag/embeddings.py` (wrapper FastEmbed + fallback OpenAI) | ADR 002 + archi § Embeddings |
| Vector store | `backend/app/services/rag/chroma_store.py` (factory `get_chroma_collection(subject, pseudo)`) | ADR 004 + archi § Multi-tenancy |
| Docker services | `docker-compose.yml` (postgres, redis, minio, chroma) | ADR 001 + archi § Infrastructure |
| `.gitignore` | `.gitignore` (racine) | Trouvaille : pas de `.gitignore` à la racine, dette à régler |
| `requirements.txt` | `backend/requirements.txt` | Pré-tâche s01 |
| `.env.example` | `backend/.env.example` | Sécuriser les secrets |
| Tests | `backend/tests/services/rag/test_ingestion.py`, `test_chroma_store.py`, `test_ocr.py` | AGENTS.md § Tests |

## Verified APIs / functions (à utiliser, vérifiées contre l'état du code)

Tout est à installer from scratch. Les choix techniques confirmés par `docs/architecture.md` + ADR + AGENTS.md :

- `chromadb.PersistentClient(path=...)` — confirmé par ADR 004 § Decision.
- `langchain.text_splitter.RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, separators=["\n\n", "\n", " ", ""])` — confirmé par s01 AC1.
- `langchain_community.document_loaders.PyMuPDFLoader(file_path)` — listé dans `requirements.txt` historique (non tracké) et l'ancien POC l'utilisait. À remettre dans `requirements.txt`.
- `fastembed.TextEmbedding` — provider d'embeddings local ONNX, par défaut selon `docs/architecture.md` § Stack.
- `sqlalchemy.create_engine(DATABASE_URL)` + `sessionmaker` + `Base.metadata.create_all()` pour l'init (Alembic pour les migrations futures).
- `typer` (ou `click`) pour le CLI — convention à fixer en planning. `typer` est plus moderne et intégré à Pydantic.
- Provider LLM multimodal pour OCR : `ChatOpenAI` (si Mistral/OpenAI) ou un client HTTP vers le service d'inférence (si Minimax-M3). Le `.env` actuel pointe Mistral, ce qui ne fournit pas de vision (Mistral n'a pas de modèle vision natif aussi accessible). **Tension à trancher** : il faut soit changer `LLM_PROVIDER` pour un provider qui supporte la vision (OpenAI GPT-4o ou Gemini), soit accepter que s01 ne teste pas l'OCR manuscrit pour le POC (et le note explicitement dans le rapport). Voir « Open questions ».

## Traps & constraints

1. **POC abandonné (ADR 002)** : ne pas tenter de réutiliser `src/agents/math_agent.py` (puisqu'il n'est même plus tracké). Le code de l'ancien POC n'est pas dans le worktree. Le seul artefact qui survit est la convention de nommage `rag_<subject>_<pseudo>` (ADR 004).
2. **`.env` non ignoré** : créer un `.gitignore` AVANT tout commit. Inclure au minimum : `.env`, `__pycache__/`, `*.pyc`, `chroma_data/`, `node_modules/`, `.next/`, `keys/`, `.venv/`, `venv/`, `data/chroma_db/`, `data/postgres/`, `data/redis/`, `data/minio/`.
3. **Multi-tenant dès le départ** : `Document.student_pseudo` est une FK (le PRD le mandate), et ChromaDB collection = `rag_<subject>_<pseudo>`. La factory `get_chroma_collection` doit valider le format du pseudo (alphanumeric + underscore, 3-32 chars) pour éviter l'injection dans le nom de collection.
4. **MinIO non démarré en POC** : le PRD/ADR disent que les fichiers vont dans MinIO, mais s01 ne s'occupe QUE de l'indexation RAG (pas du stockage du fichier original). Cependant, AC6 dit « persists nothing » en cas d'échec — il faut décider si on stocke le fichier source dans MinIO dans s01 ou plus tard. Cf. « Open questions ».
5. **Test d'isolation cross-tenant (AC7)** : nécessite un ChromaDB de test (in-memory ou éphémère) avec deux pseudos. Le test peut tourner sans PostgreSQL (uniquement la collection ChromaDB). Utiliser `chromadb.EphemeralClient()` pour ce test afin de ne pas dépendre du docker-compose.
6. **Détection PDF scanné** : l'ancien POC avait un piège (PyMuPDF retourne du texte vide pour les PDF scannés, et il faut un fallback OCR). Ce piège est documenté dans les agentic notes de s01. Le code de l'ancien POC (`multimodal_ocr.py`) ne peut pas être réutilisé — il est dépendant de GPT-4o et n'est plus dans le worktree. Réécrire un `ocr.py` minimal qui : (a) tente d'extraire le texte via PyMuPDF ; (b) si la longueur du texte < N caractères (seuil à fixer, ex. 50), bascule vers l'OCR multimodal ; (c) l'OCR multimodal envoie l'image au LLM vision et récupère le texte transcrit.
7. **Détection d'erreur OCR manuscrit** : les agentic notes disent « if confidence < 0.5, reject ». Mais le LLM ne retourne pas un score de confiance natif — il faut soit le demander explicitement dans le prompt (champ `confidence` JSON), soit vérifier la longueur de la transcription. À fixer en planification.
8. **CLI ergonomique** : la story demande `python -m ktutor.cli upload <file> --pseudo <p> --subject maths`. La convention `python -m <module>` requiert soit `backend/app/cli.py` + `backend/app/__init__.py` + exécution `python -m backend.app.cli`, soit un entry-point dans `pyproject.toml` (`ktutor = "app.cli:app"`). À clarifier en planning.
9. **Pas de FastAPI / pas d'auth en s01** : la story livre un CLI qui prend `--pseudo` en argument. Le JWT arrive en s13. Donc le `pseudo` est trusted côté CLI (pas de RBAC, pas de middleware). À documenter explicitement dans l'AC et le code.

## Open questions

À trancher **avant ou pendant** `/ks-plan s01` :

1. **Provider LLM par défaut (vision) :** le `.env` pointe Mistral, mais Mistral n'a pas de modèle vision natif aussi facile à invoquer que GPT-4o. Options :
   - (a) Garder Mistral pour le LLM texte (chat, génération), utiliser OpenAI GPT-4o (ou Gemini) pour la vision via une variable d'env distincte (`VISION_PROVIDER=openai` + `OPENAI_API_KEY`).
   - (b) Tout passer sur OpenAI (LLM texte + vision) et exiger une clé OpenAI.
   - (c) Garder Minimax-M3 (gratuit, comme dans l'archi) pour le texte et exiger OpenAI/Gemini pour la vision. C'est la voie qui colle à l'archi.
   - **Recommandation par défaut** : (a) ou (c), avec deux envs distincts. À trancher explicitement en planning.

2. **MinIO en s01 ou reporté ?** AC6 parle d'une row `Document` en PostgreSQL mais ne mentionne pas le stockage du fichier source dans MinIO. L'architecture dit « préfixe MinIO `students/<pseudo>/<document_id>` ». Options :
   - (a) Stocker le fichier source dans MinIO dès s01 (cohérent avec l'archi).
   - (b) Stocker uniquement le chemin local (`./uploads/<pseudo>/<document_id>.pdf`) en s01, et migrer vers MinIO dans une story dédiée.
   - (Recommandation par défaut : (a) — MinIO est dans le docker-compose prévu, le code est plus simple à écrire maintenant qu'à migrer plus tard.)

3. **Corpus de test (question ouverte PRD § Questions ouvertes #1) :** Sésamath cycle 4 (open-license) vs uniquement upload élève. **Recommandation :** utiliser des **PDF générés en test** (un PDF de maths synthétique, une image PNG contenant du texte tapé, une image PNG d'un exercice manuscrit manuscrit sur papier scanné). Sésamath est un téléchargement externe et alourdit les tests — mieux vaut un corpus synthétique. **Trancher en planning :** OK par défaut.

4. **Validation du format `pseudo` au niveau du CLI** : faut-il rejeter `--pseudo alice@example.com` avec un message d'erreur ? (Le format est alphanumeric + underscore, 3-32 chars selon s12.) Recommandation : oui, valider tôt pour éviter que des pseudos malformés polluent ChromaDB.

5. **Tests : Postgres de test** : AC6 mentionne PostgreSQL. Pour les tests unitaires de la factory `get_chroma_collection`, ChromaDB éphémère suffit. Pour tester l'insertion de la row `Document`, il faut soit un Postgres jetable (testcontainers), soit mocker le session. Recommandation : mocker le `Session` pour les tests unitaires, ajouter un test d'intégration optionnel avec testcontainers (non bloquant).

## Real complexity

**Score initial dans `docs/stories.md` : 3.**
**Score après lecture du code : 3 (confirmé).**

**Justification du score confirmé :**

- 3 surfaces techniques à intégrer : (1) ingestion multi-format, (2) embeddings (FastEmbed local), (3) persistance ChromaDB + PostgreSQL.
- Mais : (1) le code est **greenfield** (pas de dette à gérer), (2) les conventions sont déjà fixées par l'architecture, (3) la story a 7 AC bien découpés, (4) un seul agent à faire (pas de multi-agent en s01).

**Pourquoi pas 2 ?** Multi-format (PDF + image dactylo + image manuscrite) ajoute un OCR multimodal et un fallback. C'est ce qui justifie le 3.

**Pourquoi pas 4 ?** Pas de risque spécifique (pas de state machine, pas de LLM-as-judge). Le risque principal est l'OCR multimodal et il est borné par l'AC3 (« if text is recognized, the same pipeline runs » — on peut toujours tomber en `manual_review_needed`).

**Verdict : 3 confirmé. Pas de split nécessaire.**

Si la planification révèle que l'OCR multimodal est trop risqué (provider à configurer, JSON parsing à fiabiliser), une découpe naturelle serait : **s01a** (PDF + image dactylo seulement) → **s01b** (OCR manuscrit). Mais c'est une décision de planification, pas de research.

## Split proposal

Pas de split (score 3 confirmé). Une éventuelle coupe s01a/s01b est documentée ci-dessus comme option de repli pour `/ks-plan`.

---

## Note finale

Aucun finding ne contredit les AC de la story. La prémisse est **valide** : on part d'un repo greenfield (presque — il y a la dette `.gitignore` à régler) et on construit l'ossature backend + le premier flux métier (upload RAG). Le seul vrai risque est le **provider LLM pour la vision** — Mistral n'est pas idéal et la décision doit être tranchée en planning. Tous les autres pièges sont documentés et ont une parade connue.
