---
name: research-s10-api-upload
description: s10-api-upload — recherche de contexte pour /ks-plan
metadata:
  type: project
  story: s10-api-upload
---

# Research — Story s10-api-upload

> Recherche en français. Code identifiers dans leur forme d'origine. Date : 2026-09-01.
> Workspace : `.worktrees/s10-api-upload` (branche `feature/s10-api-upload`, HEAD `473181c` = `main`).

## The five structuring facts

1. **`UploadService.upload(file_path, pseudo, subject)` est la seule fonction métier à exposer.** Toute la pipeline RAG (validation pseudo, validation fichier, push S3/SeaweedFS, extraction texte/OCR, chunking, embedding, indexation ChromaDB, persistance `Document` row, rollback S3 sur échec) est déjà encapsulée dans `backend/app/services/rag/upload_service.py:106-204`. La méthode retourne `UploadResult(document_id, chunks_count, duration_ms, status, collection, s3_key, ocr_confidence)` (l. 57-67). **Pour s10, le travail principal n'est PAS de réécrire cette pipeline — c'est d'exposer ce contrat via HTTP multipart.**
2. **`UploadService.upload` attend un `file_path` (str), pas des bytes.** Le fichier doit être lisible depuis le disque (le service fait `path.read_bytes()` ligne 136). **Pour FastAPI**, `UploadFile` est un stream : il faut soit le matérialiser via `await upload.read()` puis l'écrire dans un `tempfile.NamedTemporaryFile` (et passer le path), soit refactorer `UploadService.upload` pour accepter des bytes + un filename. **Cette décision est structurante** : elle conditionne le contrat de l'endpoint.
3. **Aucun fichier `backend/app/main.py` n'existe.** Le seul entry point est `app/__main__.py` qui invoque le CLI typer (`from app.cli import app` puis `app()`). FastAPI n'est **pas** dans `requirements.txt` (vérifié par `grep` ligne 1-53) — il est installé en environnement conda (`fastapi 0.141.1`, `uvicorn 0.52.1`, `httpx 0.28.1`) mais pas déclaré. **Pré-tâche obligatoire** : ajouter `fastapi>=0.115` et `python-multipart>=0.0.9` à `requirements.txt` (ce dernier pour `UploadFile` + `Form`).
4. **Le `pseudo` n'est PAS authentifié en s10.** La story l'explicite : « The `pseudo` in the body is the source of multi-tenant isolation here. The auth stub (no JWT yet) is acceptable for this story. » (stories.md:406). Le middleware JWT arrive en s13/s15. **Conséquence** : le test d'isolation cross-tenant s10 teste le contrat du service (`UploadService.upload` produit une collection `rag_<subject>_<pseudo>` distincte), pas le contrôle d'accès HTTP. La s15 migrera les endpoints `pseudo-in-body` vers JWT.
5. **327 tests collectés au HEAD `473181c` (avant s10).** Le pipeline CI vert s'appuie sur pytest qui exclut les tests d'intégration. L'extension s10 doit suivre la convention : tests d'endpoint avec `fastapi.testclient.TestClient` (pas `pytest-asyncio` direct), pas d'authentification, mocks sur tous les I/O (S3, ChromaDB, OCR, embeddings). Le pattern de double est déjà présent : `FakeS3` dans `tests/services/storage/test_s3_client.py` (importé par `test_upload_service.py:27`).

## Target story

> **As an** élève **I want** téléverser un document depuis une interface web **so that** il soit indexé dans mon RAG.

**Source** : `docs/stories.md:375-407` (s10 — Phase 2 MVP).

**Complexity (donné par `stories.md:381`)** : 2 — FastAPI multipart + reuse of the s01 ingestion pipeline.

### Acceptance criteria (verbatim, depuis `stories.md:383-391`)

- AC1. L'endpoint `POST /api/documents/upload` accepte `multipart/form-data` avec les champs `pseudo`, `subject`, et `file` (PDF, PNG, JPG).
- AC2. Au succès, retourne `{document_id: uuid, status: "indexed", chunks_count: int}` avec HTTP 201.
- AC3. À l'échec (oversize, format non supporté, échec OCR), retourne 4xx avec `{error: "..."}` et ne persiste rien.
- AC4. La logique d'ingestion est la MÊME que dans s01 — extraire une fonction de service dans s01 si pas déjà fait, et l'appeler depuis le CLI et l'API.
- AC5. Un test uploade un petit PDF valide et vérifie la réponse.
- AC6. Un test uploade un fichier trop gros et vérifie l'erreur 4xx.
- AC7. Un test vérifie l'isolation multi-tenant : `pseudo_a` qui uploade ne rend PAS le document visible à `pseudo_b`.

### Questions ouvertes liées (PRD § Questions ouvertes)

- Aucune question ouverte attachée à s10. La story est verrouillée par s01.

## Current state of the code

État du worktree (vérifié sur `473181c` = `main`).

### Modules présents et réutilisables

- `backend/app/services/rag/upload_service.py` (294 lignes) — `UploadService.upload(file_path, pseudo, subject) -> UploadResult`. **Service principal à exposer**. Toutes les constantes d'extension et de limite sont déjà définies (`ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}` l. 39, `max_upload_size_mb=20` l. 96). Les types d'erreurs sont déjà là : `UploadErrorKind ∈ {INVALID_PSEUDO, INVALID_FILE, OCR_FAILURE, STORAGE_FAILURE}` (l. 42-46), `UploadError(kind, message)` (l. 49-54).
- `backend/app/services/rag/ingestion.py` — `DocumentIngestor` et `Chunk`. **Aucun changement requis** (la pipeline d'ingestion est stable depuis s01, cf. `app/cli.py:69`).
- `backend/app/services/rag/chroma_store.py` — `ChromaStore.get_collection(subject, pseudo)` (utilisé par `UploadService` l. 171). Le préfixe `rag_<subject>_<pseudo>` est appliqué ici (cf. ADR 004).
- `backend/app/services/rag/ocr.py` — `MultimodalOcr.transcribe_image(path) -> OcrResult`. Utilisé par `UploadService._extract_text` (l. 217) pour les images et PDF scannés.
- `backend/app/services/storage/minio_client.py` — `MinioClient` (en réalité parle SeaweedFS depuis ADR 009, le nom du SDK est conservé). `put_object(pseudo, document_id, filename, data) -> s3_key` (l. 132 du service). `remove_object(s3_key)` (l. 198 du service).
- `backend/app/services/rag/embeddings.py` — `build_embedding_provider(llm_provider, openai_api_key)`. Pattern d'injection stable.
- `backend/app/core/database/models.py` (207 lignes) — `Document` (l. 53-97), `DocumentStatus` (l. 18-23), `Subject` (l. 26-30). **Aucun ajout de colonne n'est nécessaire pour s10**. Le modèle est stable.
- `backend/app/core/database/session.py` — `init_db()` (appelé par le CLI l. 114) et `get_session_factory() -> Callable[[], Session]`.
- `backend/app/core/config.py` (133 lignes) — `Settings.max_upload_size_mb: int = 20` (l. 46), `Settings.s3_*` (l. 40-43), `Settings.chroma_persist_directory` (l. 31). **Aucun nouveau setting n'est requis pour s10** — `max_upload_size_mb` est déjà partagé avec le CLI.
- `backend/app/cli.py` — `app.command("upload")` (l. 298-385), `_build_service() -> UploadService` (l. 96-123). Le wire-up du CLI est la **référence exacte** pour le wire-up FastAPI : même injection de `MinioClient`, `ChromaStore`, `build_embedding_provider`, `MultimodalOcr`, `DocumentIngestor`, `db_session.get_session_factory()`.

### Modules absents (à créer pour s10)

- `backend/app/main.py` — entry point FastAPI. **N'existe pas**. Le seul `main.py` historique est dans le POC non tracké. s10 doit le créer.
- `backend/app/api/__init__.py` et `backend/app/api/documents.py` — router FastAPI pour l'upload. **Aucun sous-dossier `api/` n'existe encore** (vérifié par `ls` du worktree). s10 doit le créer from scratch.
- `backend/tests/api/__init__.py` et `backend/tests/api/test_documents.py` — tests d'endpoint via `TestClient`.

### Modules partiellement présents (à étendre)

- `backend/requirements.txt` — ajouter `fastapi>=0.115` et `python-multipart>=0.0.9` (déjà installé en conda mais non déclaré, bloquant pour la reproductibilité CI).
- `backend/.env.example` — aucune extension requise (les settings existants suffisent).
- `backend/app/cli.py` — **AUCUNE modification requise** pour s10. La pipeline CLI est stable. Le AC4 dit « la logique d'ingestion est la MÊME que dans s01 — extraire une fonction de service dans s01 si pas déjà fait » : la fonction est **déjà extraite** (`UploadService.upload`). Le CLI et l'API appellent la même fonction. Aucune duplication.

### Constat critique : `backend/app/core/database/session.py:15` importe `from fastapi import Depends`

```python
# backend/app/core/database/session.py:15 (extrait vérifié)
from fastapi import Depends  # noqa: F401  - re-export for callers
```

**Ce `import` ne fonctionne PAS** : `fastapi` n'est pas dans `requirements.txt`. Soit il faut l'ajouter, soit cet import est mort. **Action pour le plan** : ajouter `fastapi` à `requirements.txt` (pré-tâche s10) — cet import deviendra valide et s10 pourra l'utiliser si besoin (par exemple pour des `Depends` plus tard). Si l'import n'est pas utilisé, le supprimer en passant. **Vérification au planning**.

## Anchor points (où s10 branche)

| Cible | Fichier à créer / étendre | Justification |
|---|---|---|
| Entry point HTTP | `backend/app/main.py` (nouveau) | Convention FastAPI. Doit exposer `app = FastAPI(...)` et `include_router(documents.router)`. |
| Router upload | `backend/app/api/documents.py` (nouveau) | Convention `docs/architecture.md` § Repo structure : `backend/app/api/<domaine>/router.py`. s10 utilise `backend/app/api/documents.py` (domaine = documents, fichier unique). |
| Service réutilisé | `backend/app/services/rag/upload_service.py:106` (`UploadService.upload`) | **Aucun changement** : c'est le point d'entrée métier. |
| Wire-up | `_build_service()` dans `cli.py:96-123` (référence à dupliquer dans `api/documents.py`) | Pattern d'injection de dépendances. s10 crée une variante `_build_upload_service()` (ou réutilise l'export). |
| Schémas Pydantic | `backend/app/api/documents.py` (dans le même fichier, lignes du dessus) | `UploadResponse`, `UploadErrorResponse`, `UploadForm` (form model). Convention `docs/architecture.md` § Patterns : Pydantic pour les schémas. |
| Tests endpoint | `backend/tests/api/test_documents.py` (nouveau) | Convention s03/s04/s07 : un test par AC + bites d'anti-régression. |
| Test doubles | `tests/services/storage/test_s3_client.py::FakeS3` (déjà exporté) | Réutilisé par `test_upload_service.py:27` — pattern stable. |
| Settings | `backend/app/core/config.py` (étendre avec 1-2 vars) | Ajout potentiel de `api_cors_origins: list[str] = ["http://localhost:3000"]` pour le CORS (cf. s09). **À trancher en planning** : s10 a-t-il besoin du CORS, ou est-ce partagé avec s09 ? |
| Requirements | `backend/requirements.txt` (étendre) | `fastapi>=0.115` + `python-multipart>=0.0.9`. **Pré-tâche obligatoire**. |
| Test client fixture | `backend/tests/conftest.py` (étendre avec un client HTTP) | `from fastapi.testclient import TestClient; client = TestClient(app)`. Pattern à standardiser. |

## Verified APIs / functions (à utiliser, vérifiées contre l'état du code)

- `UploadService.upload(file_path: str, pseudo: str, subject: str) -> UploadResult` — `backend/app/services/rag/upload_service.py:106-204`. **Contrat stable depuis s01, livré par merge commit `a593fc8`+s05-s07**. Garantit :
  - Validation `pseudo` (regex `^[a-zA-Z0-9_]{3,32}$`) via `validate_pseudo()` (l. 110, importé de `chroma_store.py`).
  - Validation extension (l. 115) + taille (l. 120) avant tout I/O.
  - Push S3 (l. 132), rollback S3 sur tout `UploadError` ou `Exception` (l. 197-204).
  - Persistance `Document` row en PostgreSQL (l. 247-281) si `session_factory` est fourni.
  - Retourne `UploadResult` avec `status: DocumentStatus.INDEXED` ou `MANUAL_REVIEW_NEEDED`.
- `UploadError(kind: UploadErrorKind, message: str)` — `upload_service.py:49-54`. **Exception à intercepter dans le router FastAPI** pour mapper en HTTP.
- `UploadErrorKind` enum — 4 valeurs : `INVALID_PSEUDO`, `INVALID_FILE`, `OCR_FAILURE`, `STORAGE_FAILURE` (l. 42-46).
- `DocumentStatus` enum — 3 valeurs : `INDEXED`, `ERROR`, `MANUAL_REVIEW_NEEDED` (`models.py:18-23`).
- `MinioClient.put_object(pseudo, document_id, filename, data)` — `backend/app/services/storage/minio_client.py`. **S3-compatible** (parle SeaweedFS via le SDK minio).
- `ChromaStore.get_collection(subject, pseudo)` — convention `rag_<subject>_<pseudo>` (ADR 004).
- `build_embedding_provider(llm_provider, openai_api_key)` — factory stable, pattern s02-s07.
- `MultimodalOcr(base_url, timeout, transport)` — utilise `httpx` injecté pour les tests. Pattern stable.
- `db_session.init_db()` + `db_session.get_session_factory()` — `backend/app/core/database/session.py`. Appelé une fois au boot de l'app FastAPI (`@app.on_event("startup")`) ou au premier appel du router.
- FastAPI patterns disponibles (lib installés en conda, à déclarer dans `requirements.txt`) :
  - `from fastapi import FastAPI, UploadFile, File, Form, HTTPException, status`
  - `from fastapi.testclient import TestClient` (équivalent httpx pour les tests, basé sur starlette `TestClient`)
  - `from fastapi.responses import JSONResponse`
  - `python-multipart` pour parser `multipart/form-data` (pré-requis pour `UploadFile` + `Form`)

## Traps & constraints

### Piège 1 — `UploadFile` est un stream, `UploadService.upload` veut un `file_path`

**Description** : `UploadService.upload(file_path, pseudo, subject)` lit `path.read_bytes()` (l. 136) et fait `path.stat().st_size` (l. 120). FastAPI `UploadFile` est un objet wrapper autour d'un `SpooledTemporaryFile` qui peut être lu via `await upload.read()` ou `upload.file.read()`. Il faut soit :
- (a) matérialiser les bytes via `await upload.read()` puis écrire dans un `tempfile.NamedTemporaryFile(suffix=...)` et passer le path au service. **Nettoyage** : `os.unlink(tmp_path)` dans un `try/finally`.
- (b) refactorer `UploadService.upload` pour accepter `(filename, data: bytes, pseudo, subject)`. **Impact** : modifie le contrat existant, oblige à mettre à jour `cli.py:333` (l'appel `service.upload(str(file), pseudo, subject)`). **Plus invasif** mais plus propre.

**Mitigation (R : option a)** : matérialiser le fichier via tempfile dans le router FastAPI, passer le path au service, nettoyer dans `finally`. Le service reste inchangé. L'AC4 (« la logique d'ingestion est la MÊME que dans s01 ») est respectée strictement.

### Piège 2 — Limite de taille : enforcement API vs enforcement service

**Description** : l'AC3 dit « On failure (oversize, unsupported format, OCR failure), returns 4xx ». Le service lève `UploadError(INVALID_FILE, ...)` si la taille dépasse `max_upload_size_mb` (l. 120-126). **Mais** : FastAPI `UploadFile` ne lit le fichier qu'à la demande (streaming). Si le client envoie un fichier de 1 GB, FastAPI va bufferiser le tout en mémoire avant que `service.upload` ne voie la taille. **Double mitigation** :
- (a) Limite déclarative : ajouter une vérification de `Content-Length` header (si présent) **avant** `await upload.read()`. Si `Content-Length > max_bytes`, retourner 413 (Payload Too Large) sans lire le body.
- (b) Vérification post-read : `len(data) > max_bytes` → 413.
- (c) Backend : `UploadService.upload` lève déjà `INVALID_FILE` qui mappe en 413 (mapping à fixer).

**Mitigation (R : a + c)** : la vérification de `Content-Length` est best-effort (les clients peuvent l'omettre). La vérification post-read dans le router est l'autoritative. Le service a déjà la sienne. **Trois niveaux de défense** : header → router → service.

### Piège 3 — CORS : s10 sans auth, mais le frontend Next.js a besoin d'un CORS permissif

**Description** : la story ne mentionne pas le CORS. Mais s11 (frontend) consommera l'API depuis `http://localhost:3000` (ou `NEXT_PUBLIC_API_URL`). Le navigateur bloque les requêtes cross-origin sans header `Access-Control-Allow-Origin`. **Mitigation** : ajouter `CORSMiddleware` dans `main.py` avec `allow_origins=[settings.next_public_api_url]`. **Mais** : `NEXT_PUBLIC_API_URL` n'est pas dans `Settings` (l'API utilise `api_host/api_port`, le frontend utilise `next_public_api_url`). **À trancher en planning** : ajouter un setting `cors_allowed_origins: list[str]` côté backend, ou s'aligner sur l'origin par défaut du dev (`http://localhost:3000`).

**Recommandation (R)** : ajouter `cors_allowed_origins: list[str] = ["http://localhost:3000"]` à `Settings`, configuré via `CORS_ALLOWED_ORIGINS` env (comma-separated string, parsing identique à `free_difficulty_options` dans `cli.py:213-217`). **Cohérent** avec s09 si s09 a le même besoin (le pre-flight OPTIONS doit passer).

### Piège 4 — Multipart parsing : taille du body, gestion des erreurs de parse

**Description** : si le client envoie un `multipart/form-data` malformé (boundary manquant, champ manquant), FastAPI retourne déjà 422 via la validation Pydantic. **Mais** : si le client envoie un body de 100 MB sans boundary correct, `python-multipart` peut bufferiser avant de crasher. **Mitigation** : configurer un middleware ASGI pour rejeter les `Content-Length > 25 MB` (20 MB de marge) avec 413 immédiat. **Plus simple** : utiliser un reverse proxy (nginx, Caddy) en production ; en dev, compter sur `UploadFile.read()` pour échouer naturellement. **Recommandation** : ne pas surdimensionner pour le POC, ajouter un test bite : `Content-Length > max + margin` retourne 413.

### Piège 5 — Validation du `subject`

**Description** : le service `UploadService.upload` accepte `subject: str` (l. 106). Il n'y a **aucune validation** que `subject` est dans `{"maths", "francais"}` (cf. `Subject` enum `models.py:26-30`). Si le client envoie `subject="physique"`, la collection ChromaDB s'appellera `rag_physique_<pseudo>` (création silencieuse, pollution de l'espace de noms). **Mitigation** : Pydantic `Form` field avec `Literal["maths", "francais"]` ou `Subject` enum directement. **Recommandation (R)** : utiliser `Subject` enum pour la validation côté API. **Le CLI accepte déjà `str`** (cf. `cli.py:302`) mais ne valide pas non plus — c'est une dette pré-existante non bloquante pour s10.

### Piège 6 — Le `pseudo` est validé par le service, pas par le router

**Description** : `UploadService.upload` lève `UploadError(INVALID_PSEUDO, ...)` (l. 110-112) si le pseudo ne matche pas `^[a-zA-Z0-9_]{3,32}$`. **Mais** : un élève qui upload via l'API avec `pseudo="alice@evil.com"` ne sera détecté qu'au moment de l'appel service. Le router doit soit valider en amont (Pydantic `Field(regex=...)`), soit laisser le service trancher. **Recommandation (R)** : laisser le service trancher (single source of truth). Le router mappe `UploadError(INVALID_PSEUDO)` → 422 (validation error). **Cohérent** avec le CLI qui retourne exit 5 sur la même condition.

### Piège 7 — `UploadResult.status` peut être `MANUAL_REVIEW_NEEDED` (succès partiel)

**Description** : si l'OCR échoue avec `confidence < 0.5` (cf. `upload_service.py:147-157`), le service retourne `UploadResult(status=MANUAL_REVIEW_NEEDED, chunks_count=0, ocr_confidence=0.2)`. C'est un **succès HTTP** (le document est tracé en base avec `status=manual_review_needed`), pas une erreur. **Le router FastAPI doit retourner 201** dans ce cas (pas 4xx). **Mais** : `chunks_count=0` peut surprendre l'UI qui s'attend à un document indexé. **Recommandation (R)** : retourner 201 avec `{"document_id": ..., "status": "manual_review_needed", "chunks_count": 0, "ocr_confidence": 0.2}`. L'UI décide de l'affichage. **Cohérent** avec le comportement CLI (exit 0 sur `manual_review_needed`, cf. `cli.py:16`).

### Piège 8 — Pas de migration de schéma nécessaire pour s10

**Description** : `Document` (models.py:53-97) couvre tous les champs requis (`student_pseudo`, `subject`, `filename`, `s3_key`, `chunks_count`, `status`, `error_reason`, `created_at`). **Aucun ajout de colonne**. `init_db()` est idempotent (vérifié par s04). **Risque de régression** : si une autre story a ajouté un champ à `Document` (cf. s18 evaluations), c'est leur problème, pas celui de s10.

### Piège 9 — Test d'isolation cross-tenant (AC7)

**Description** : AC7 dit « pseudo_a qui uploade ne rend PAS le document visible à pseudo_b ». **Mais** : l'isolation cross-tenant s10 est au niveau **service** (la collection ChromaDB s'appelle `rag_<subject>_<pseudo_a>`, distincte de `rag_<subject>_<pseudo_b>`), pas au niveau HTTP (pas d'auth en s10). Le test doit :
- (1) Uploader via l'API en tant que `pseudo_a` avec un PDF.
- (2) Uploader via l'API en tant que `pseudo_b` avec un autre PDF.
- (3) Vérifier que la collection `rag_<subject>_<pseudo_a>` contient le doc de `pseudo_a` (via `ChromaStore.get_collection`).
- (4) Vérifier que la collection `rag_<subject>_<pseudo_b>` contient le doc de `pseudo_b` (et **PAS** celui de `pseudo_a`).
- (5) Vérifier qu'aucune row PostgreSQL `Document` n'est partagée (les `Document.student_pseudo` sont distincts).

**Mitigation** : utiliser deux `FakeS3` (ou un seul `FakeS3` partagé) et `chromadb.EphemeralClient()` partagé. Le test mord si quelqu'un retire la convention `rag_<subject>_<pseudo>`.

### Piège 10 — FastAPI lifespan et `init_db()`

**Description** : le CLI appelle `db_session.init_db()` au démarrage de chaque commande (`cli.py:114`). Pour FastAPI, l'équivalent est `@asynccontextmanager async def lifespan(app: FastAPI)` dans `main.py`. **Recommandation (R)** : `init_db()` dans le lifespan, au démarrage, une seule fois. Cohérent avec le CLI. **Pas d'init dans le router** (sinon N requêtes par démarrage).

### Piège 11 — Validation 422 vs 4xx mapping

**Description** : FastAPI retourne 422 pour les erreurs de validation Pydantic (champ manquant, type incorrect). Le service lève `UploadError` qui doit mapper en 4xx. **Convention** :
- Pydantic validation 422 (champ `pseudo` manquant dans le form, etc.) → FastAPI gère, 422 automatique.
- `UploadError(INVALID_PSEUDO)` → 422 (validation error, le pseudo est mal formé).
- `UploadError(INVALID_FILE)` (taille, extension) → 413 (Payload Too Large) ou 415 (Unsupported Media Type). **Recommandation (R)** : 413 pour la taille, 415 pour l'extension.
- `UploadError(OCR_FAILURE)` → 422 (le fichier est valide mais le contenu est inutilisable) ou 400. **Recommandation (R)** : 422.
- `UploadError(STORAGE_FAILURE)` → 500 (S3 ou ChromaDB injoignable, c'est une panne infra).

### Piège 12 — `subject` est un enum SQLAlchemy

**Description** : `Document.subject: Mapped[Subject] = mapped_column(Enum(Subject, ...))` (`models.py:73-76`). Le service convertit via `Subject(subject)` (l. 270). **Mais** : si l'API reçoit `subject="MATHS"` (majuscules), `Subject("MATHS")` lève `ValueError` (l'enum est case-sensitive). **Mitigation (R)** : normaliser `subject.lower()` côté router avant de passer au service. **Ou** : utiliser `Subject` enum Pydantic côté router (qui valide la casse).

### Piège 13 — `from app.core.database.session import Depends` ne fonctionne pas

**Description** : `session.py:15` importe `from fastapi import Depends  # noqa: F401  - re-export for callers`. Si `fastapi` n'est pas dans `requirements.txt`, ce fichier **ne s'importe pas**. Le CLI fonctionne parce qu'il n'importe pas `session.py` directement, ou il a un fallback. **Vérification au planning** : `from app.core.database.session import get_session_factory` doit fonctionner. Si ça échoue à cause de l'import `Depends` mort, il faut soit ajouter `fastapi` à `requirements.txt`, soit retirer l'import mort.

## Open questions

À trancher **avant ou pendant** `/ks-plan s10` :

1. **CORS : s10 le pose-t-il ou s09 le pose-t-il ?** Les deux stories ont besoin du CORS. Option (a) : s10 inclut le CORS, s09 hérite. Option (b) : s10 NE pose PAS le CORS, s09 le fait. Option (c) : CORS est partagé dans `main.py`, chaque story ajoute ses routes. **Recommandation (R : c)** : `main.py` configure le `CORSMiddleware` une fois pour toutes, avec `allow_origins` configurable via `CORS_ALLOWED_ORIGINS` env. s10 ET s09 héritent. **Tension** : s09 est en parallèle, il pourrait avoir la même intention. **Mitigation** : si s09 merge en premier avec CORS, s10 ne le rajoute pas. Si s10 merge en premier, s09 hérite.

2. **`UploadFile` stream vs bytes : refactor ou tempfile ?** Piège 1 ci-dessus. Option (a) : `tempfile.NamedTemporaryFile` dans le router, `service.upload(tmp_path, ...)` puis cleanup. Option (b) : refactor `UploadService.upload(filename, data: bytes, pseudo, subject)`. **Recommandation (R : a)** : zero impact sur la pipeline existante, AC4 strictement respecté. **Mais** : s10 doit tester que le tempfile est bien nettoyé en cas d'erreur (try/finally).

3. **`Settings.cors_allowed_origins` : nouvelle var ou aligner sur l'existant ?** Aucun setting CORS aujourd'hui. **Recommandation (R)** : ajouter `cors_allowed_origins: str = "http://localhost:3000"` à `Settings`, parser comme `free_difficulty_options` (comma-separated string). **Cohérent** avec la convention s06. Le parsing peut être fait dans le lifespan ou dans un helper.

4. **`max_upload_size_mb` : doit-il être re-vérifié dans le router ?** Le service le vérifie déjà. Mais la vérification **post-read** (Piège 2) demande que le router lise le body entièrement pour avoir la taille. **Recommandation (R)** : double check : router vérifie `Content-Length` (best effort) ET taille post-read. Si `Content-Length > 20MB`, 413 immédiat. Si `Content-Length` absent, lire le body et vérifier.

5. **Validation `subject` côté API : Pydantic `Literal` ou service ?** Le service ne valide pas. **Recommandation (R)** : Pydantic `Form` field avec `Literal["maths", "francais"]` (cohérent avec les Settings). **Ou** : passer `Subject` enum Pydantic. **À trancher en planning**.

6. **Format de la réponse 201 : doit-elle inclure `chunks_count=0` quand `MANUAL_REVIEW_NEEDED` ?** L'AC2 dit `{document_id, status: "indexed", chunks_count: int}`. Pour `MANUAL_REVIEW_NEEDED`, `status` change. **Recommandation (R)** : retourner la même forme `{document_id, status, chunks_count, ocr_confidence?}` avec `status="manual_review_needed"` quand c'est le cas. Le frontend (s11) affichera un message spécifique.

7. **`python-multipart` est-il déjà installé ?** Vérifié : `pip list | grep multipart` ne retourne rien. **Pré-tâche obligatoire** : ajouter `python-multipart>=0.0.9` à `requirements.txt`. Sans ça, FastAPI `UploadFile` + `Form` lèvent `RuntimeError: Form data requires "python-multipart" to be installed`.

8. **`@app.on_event("startup")` vs `lifespan` ?** FastAPI 0.115+ recommande `lifespan` (async context manager), `@app.on_event` est deprecated. **Recommandation (R)** : `lifespan` avec `init_db()` dedans. **Cohérent** avec FastAPI 0.141 (déjà installé).

9. **Test bite AC7 : comment tester l'isolation cross-tenant sans auth ?** AC7 dit « pseudo_a qui uploade ne rend PAS le document visible à pseudo_b ». Sans JWT, c'est le service qui isole (par le préfixe `rag_<subject>_<pseudo>`). Le test vérifie que les collections ChromaDB sont distinctes et que les rows `Document` ont des `student_pseudo` distincts. **Recommandation (R)** : tester via `ChromaStore.get_collection` directement (le service est censé l'appeler avec le bon pseudo).

10. **FastAPI TestClient : `TestClient(app)` synchrone ou `httpx.AsyncClient` ?** `fastapi.testclient.TestClient` est un wrapper sync autour de httpx. Il marche avec pytest-asyncio. **Recommandation (R)** : `TestClient` sync, plus simple, suffit pour les tests bite. **Pas besoin de `httpx.AsyncClient`**.

## Real complexity

**Score initial dans `docs/stories.md` : 2.**
**Score après lecture du code : 2 (confirmé).**

**Justification du score confirmé :**

- **1 surface technique principale** : exposer un endpoint FastAPI multipart qui appelle `UploadService.upload`.
- **Pipeline métier déjà factorisée** : `UploadService.upload` est la **même fonction** que le CLI appelle. **Aucun risque de divergence CLI/API**. Le AC4 est respecté sans effort.
- **Pas de LLM** dans la hot path de l'API (l'OCR est appelé par le service, mais c'est asynchrone et déjà géré). L'API elle-même est synchrone et retourne après que le service ait fini.
- **Pas de state machine** (vs s08 correction progressive).
- **Pas de migration DB**.
- **Pas d'auth** (Piège : le `pseudo` est dans le body, c'est un stub).

**Pourquoi pas 1 ?** Multipart parsing a des pièges (Piège 1, 2, 4, 11), et l'écriture des tests d'endpoint (`TestClient`) ajoute un peu de surface. C'est ce qui justifie le 2.

**Pourquoi pas 3 ?** Pas de LLM-as-judge, pas de retry, pas de state machine. Le service fait tout le travail.

**Verdict : 2 confirmé. Pas de split nécessaire.**

Une éventuelle coupe s10a/s10b serait :
- **s10a** (Happy path + 422) : `POST /api/documents/upload` accepte un PDF, retourne 201, lève 422 sur validation. Tests : 3-4.
- **s10b** (Edge cases) : taille, format, OCR failure, isolation cross-tenant, CORS. Tests : 3-4.

Mais c'est une **décision de planification** et le verdict 2 ne la justifie pas. **Recommandation : un seul s10**.

## Split proposal

Pas de split (score 2 confirmé). Le périmètre tient en une story.

## Files touched (anticipated)

**Code (5 fichiers nouveaux, 1 modifié) :**

- `backend/app/main.py` (nouveau, ~30 lignes) — entry point FastAPI, lifespan `init_db()`, `CORSMiddleware`, `include_router(documents.router)`.
- `backend/app/api/__init__.py` (nouveau, vide).
- `backend/app/api/documents.py` (nouveau, ~120-150 lignes) — router FastAPI, schémas Pydantic, wire-up `UploadService`, mappage `UploadError` → HTTPException, gestion tempfile.
- `backend/requirements.txt` (modifié, +2 lignes) — `fastapi>=0.115` et `python-multipart>=0.0.9`.
- `backend/.env.example` (étendu, 1 var) — `CORS_ALLOWED_ORIGINS=http://localhost:3000` (commenté, à activer en dev).
- `backend/app/core/config.py` (étendu, +5 lignes) — `cors_allowed_origins: str = "http://localhost:3000"`.

**Test (2 nouveaux) :**

- `backend/tests/api/__init__.py` (nouveau, vide).
- `backend/tests/api/test_documents.py` (nouveau, ~250-350 lignes) — TestClient + doubles + 8-10 tests.

**Doc :**

- `docs/research/s10-api-upload.md` (créé, ce document).
- `docs/architecture.md` (étendre) — confirmer le repo structure `app/api/documents/`, le format de réponse upload, le mapping CORS.
- `docs/designs/s10-api-upload.md` (créé en parallèle par /ks-design) — la story est backend, peut être minime (cf. s07 design : « aucun écran à produire »).

**Non touchés :**

- `backend/app/services/rag/upload_service.py` (s01, intact — la fonction `upload` est réutilisée telle quelle).
- `backend/app/services/rag/ingestion.py` (s01, intact).
- `backend/app/services/rag/chroma_store.py` (s01, ADR 004, intact).
- `backend/app/services/storage/minio_client.py` (s01b, intact).
- `backend/app/cli.py` (s01-s07, intact — la commande `upload` continue de fonctionner, ne change pas).
- `backend/app/core/database/models.py` (s01-s07, intact — aucun ajout de colonne).
- `backend/app/services/rag/ocr.py` (s01, intact).
- `backend/app/services/rag/embeddings.py` (s02, intact).
- `backend/tests/services/rag/test_upload_service.py` (s01, intact — les tests existants couvrent déjà le service).
- `backend/tests/conftest.py` (s01, intact — les fixtures `sample_pdf_path`, `typed_image_path`, etc. sont réutilisées par les tests d'endpoint).
- `docs/architecture.md` § Data model (intact — `documents` table couvre déjà tout).

## Test strategy

### Tests automatisés (un par AC + bites)

| AC | Test | Couche |
|---|---|---|
| AC1 (endpoint accepte multipart) | `test_documents.py::TestUploadEndpoint::test_upload_accepts_multipart_with_pdf` | HTTP (TestClient) |
| AC2 (retourne 201 + `{document_id, status, chunks_count}`) | `test_documents.py::TestUploadEndpoint::test_upload_returns_201_with_id_status_chunks` | HTTP |
| AC3 (retourne 4xx sur invalid) | `test_documents.py::TestUploadEndpoint::test_upload_returns_4xx_on_oversize` + `test_upload_returns_415_on_unsupported_extension` + `test_upload_returns_422_on_ocr_failure` | HTTP |
| AC4 (logique d'ingestion = CLI) | `test_documents.py::TestUploadEndpoint::test_upload_uses_same_service_as_cli` (par introspection : `_build_upload_service` est la même factory) | Test d'intégration léger |
| AC5 (test PDF valide) | `test_documents.py::TestUploadEndpoint::test_upload_valid_pdf_returns_201` (idempotent avec AC1+AC2, plus complet) | HTTP |
| AC6 (test fichier trop gros) | `test_documents.py::TestUploadEndpoint::test_upload_oversize_returns_413` | HTTP |
| AC7 (cross-tenant) | `test_documents.py::TestCrossTenant::test_pseudo_a_upload_not_visible_to_pseudo_b` | HTTP + service introspection |

### Bites d'anti-régression

1. **AC2 (statut "indexed")** : muter le router pour retourner `status="ok"` (au lieu de `status=result.status.value`) → test `test_upload_returns_201_with_id_status_chunks` rouge.
2. **AC3 (4xx sur invalid)** : muter le router pour swallow `UploadError` et retourner 200 → test rouge.
3. **AC6 (taille)** : retirer la vérification `Content-Length` ET la vérification post-read → test `test_upload_oversize_returns_413` rouge.
4. **AC7 (cross-tenant)** : muter `UploadService.upload` pour ignorer `pseudo` (collection partagée) → test `test_pseudo_a_upload_not_visible_to_pseudo_b` rouge.
5. **Cleanup tempfile** : ne pas appeler `os.unlink` dans le `finally` → test `test_upload_does_not_leave_tempfile` rouge (vérifier `os.listdir(tmpdir)` est vide après la requête).

### Tests `tests/api/test_documents.py` détaillés

| Test | AC couvert | Piège couvert |
|---|---|---|
| `TestUploadEndpoint::test_upload_accepts_multipart_with_pdf` | AC1, AC5 | — |
| `TestUploadEndpoint::test_upload_returns_201_with_id_status_chunks` | AC2 | — |
| `TestUploadEndpoint::test_upload_returns_201_for_manual_review_needed` | AC2 | Piège 7 (succès partiel) |
| `TestUploadEndpoint::test_upload_oversize_returns_413` | AC3, AC6 | Piège 2 (Content-Length + post-read) |
| `TestUploadEndpoint::test_upload_unsupported_extension_returns_415` | AC3 | Piège 11 (mapping) |
| `TestUploadEndpoint::test_upload_invalid_pseudo_returns_422` | AC3 | Piège 6 (validation) |
| `TestUploadEndpoint::test_upload_ocr_failure_returns_422` | AC3 | Piège 11 |
| `TestUploadEndpoint::test_upload_storage_failure_returns_500` | AC3 | Piège 11 |
| `TestUploadEndpoint::test_upload_missing_file_field_returns_422` | AC1 | Pydantic auto |
| `TestUploadEndpoint::test_upload_invalid_subject_returns_422` | AC1 | Piège 5 |
| `TestUploadEndpoint::test_upload_uses_same_service_as_cli` | AC4 | — |
| `TestUploadEndpoint::test_upload_does_not_leave_tempfile` | — | Cleanup tempfile (Piège 1) |
| `TestCrossTenant::test_pseudo_a_upload_not_visible_to_pseudo_b` | AC7 | Piège 9 |
| `TestCors::test_cors_preflight_succeeds_for_allowed_origin` | — | Piège 3 |
| `TestCors::test_cors_preflight_fails_for_disallowed_origin` | — | Piège 3 (test bite) |

### Tests manuels (humain, hors CI)

- Lancer `uvicorn app.main:app --reload` sur `http://localhost:8000`.
- `curl -F "pseudo=alice" -F "subject=maths" -F "file=@sample_cours.pdf" http://localhost:8000/api/documents/upload` → 201.
- `curl -F "pseudo=alice" -F "subject=maths" -F "file=@big_25mb.pdf" http://localhost:8000/api/documents/upload` → 413.
- `curl -F "pseudo=alice" -F "subject=maths" -F "file=@bad.exe" http://localhost:8000/api/documents/upload` → 415.
- Vérifier que le document est dans ChromaDB (`chroma list`) et en PostgreSQL (`SELECT * FROM documents`).

### Pas de test d'intégration LLM (s10 n'appelle pas de LLM directement)

## Risques

### Risque 1 — Le tempfile leak en cas d'exception non gérée

**Description** : si le router FastAPI crash entre `tempfile.NamedTemporaryFile()` et `os.unlink()`, le fichier reste sur disque. **Mitigation** : `try/finally` strict. Test bite dédié.

### Risque 2 — Conflit de merge avec s09 (chat streaming)

**Description** : s09 ajoute `backend/app/api/chat.py` et probablement `main.py`. Si s10 merge en premier, s09 doit s'intégrer dans un `main.py` existant. **Mitigation** : s09 et s10 s'accordent sur le format de `main.py` (lifespan + CORSMiddleware + 2 routers) **avant de merger**. Si s09 merge en premier, s10 ajoute `documents.router` au main existant.

### Risque 3 — CORS manquant bloque le frontend

**Description** : s11 (frontend) appelle l'API. Sans CORS, le navigateur bloque. **Mitigation** : `CORSMiddleware` dans `main.py`, configurable via `CORS_ALLOWED_ORIGINS` env.

### Risque 4 — `python-multipart` non installé silencieusement

**Description** : si la pré-tâche requirements.txt est oubliée, le test bite 422 fonctionne (FastAPI gère), mais l'upload réel crash à l'exécution avec un `RuntimeError` cryptique. **Mitigation** : pré-tâche requirements.txt est gate bloquant. Le plan s10 doit le mentionner explicitement en étape 0.

### Risque 5 — `UploadResult` shape change entre s01 et s10

**Description** : si s01 a un `UploadResult` shape X, et que s10 suppose un autre shape, le router est cassé. **Mitigation** : `UploadResult` est stable depuis s01 (dataclass l. 57-67). Pas de modification prévue. Le test `test_upload_uses_same_service_as_cli` mord si le shape change.

## Definition of Done (spécialisé pour s10)

- [ ] **Pré-tâche 0** : `fastapi>=0.115` et `python-multipart>=0.0.9` ajoutés à `backend/requirements.txt`. `pip install -r requirements.txt` réussit. `from fastapi import FastAPI` fonctionne.
- [ ] **Pré-tâche 0bis** : décision sur l'import mort dans `session.py:15` (ajouter fastapi ou retirer l'import).
- [ ] Toutes les tâches du plan cochées.
- [ ] `pytest --cov=app --cov-fail-under=80 -m "not integration"` passe (≥ 80% de couverture, cible 350+ tests après ajout d'~15).
- [ ] `ruff check app tests` passe (0 erreur).
- [ ] AC1-AC7 tous couverts par des tests automatisés.
- [ ] **Test bite AC2** : le `status` retourné matche `result.status.value` (pas un literal).
- [ ] **Test bite AC6** : la taille est vérifiée à deux niveaux (Content-Length + post-read).
- [ ] **Test bite AC7** : l'isolation cross-tenant est testée au niveau service.
- [ ] **Test bite tempfile** : aucun fichier ne leak en cas d'erreur.
- [ ] **Test bite CORS** : un preflight depuis une origine non autorisée retourne 403.
- [ ] `uvicorn app.main:app` démarre sans erreur, `GET /` retourne 200 (health check).
- [ ] `POST /api/documents/upload` accepte multipart et retourne 201 sur succès, 4xx sur invalid.
- [ ] **Pas de duplication de logique** : le router appelle `UploadService.upload` directement, pas une variante locale.
- [ ] PR unique, description structurée : résumé, AC cochées, points d'attention (CORS, tempfile cleanup, cross-tenant test).
- [ ] `git diff main...feature/s10-api-upload` est lisible.
- [ ] Review passée (`docs/reviews/s10-api-upload.md` avec `Ship allowed: yes`).

## Sources

### Fichiers lus (chemins absolus)

- `C:\Workspace\ktutor\.worktrees\s10-api-upload\docs\stories.md` (l. 375-407 pour s10 ; l. 1085-1091 pour l'ordre d'exécution).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\docs\architecture.md` (l. 50-122 pour le repo structure ; l. 145-157 pour multi-tenancy ; l. 178-200 pour `documents` table).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\docs\prd.md` (référencé indirectement ; pas de Q ouverte pour s10).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\app\services\rag\upload_service.py` (l. 1-294 : service principal, ALLOWED_EXTENSIONS, UploadError, UploadResult, pipeline complète).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\app\services\rag\ingestion.py` (l. 1-122 : DocumentIngestor, Chunk, OCR fallback).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\app\services\rag\chroma_store.py` (référencé pour `validate_pseudo` et `get_collection` ; ADR 004).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\app\cli.py` (l. 96-123 pour `_build_service` ; l. 298-385 pour `upload` command ; l. 213-217 pour le parsing comma-separated).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\app\core\config.py` (l. 1-133 : Settings, max_upload_size_mb, s3_*, chroma_persist_directory).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\app\core\database\models.py` (l. 18-97 : DocumentStatus, Subject, Document ; FK deferred to s15).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\app\core\database\session.py` (l. 1-30 : import `from fastapi import Depends` mort à vérifier).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\tests\services\rag\test_upload_service.py` (l. 1-305 : pattern FakeS3, FakeEmbeddings, FakeSession, _build_service).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\tests\conftest.py` (l. 1-146 : sample_pdf_path, typed_image_path, tmp_upload, fixed_document_id, make_oversized_file).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\app\__main__.py` (l. 1-6 : entry point CLI, pas de main.py).
- `C:\Workspace\ktutor\.worktrees\s10-api-upload\backend\requirements.txt` (l. 1-53 : pas de fastapi, pas de python-multipart).

### ADRs consultés

- `docs/decisions/001-monorepo-backend-frontend.md` — monorepo (contexte).
- `docs/decisions/002-poc-rewrite-from-scratch.md` — réécriture from-scratch (contexte).
- `docs/decisions/004-rag-isolation-by-collection.md` — collection ChromaDB par (matière × élève) (AC7).
- `docs/decisions/005-auth-rs256-rbac.md` — JWT auth (hors-scope s10, en attente de s13).
- `docs/decisions/009-seaweedfs-replaces-minio.md` — SeaweedFS S3-compatible (l'import `minio_client` est conservé).

### CLAUDE.md (extraits pertinents)

- § Stack Technologique — FastAPI mentionné (l. 27-31), backend Python (l. 35-40), S3-compatible (l. 38).
- § Multi-Tenancy — `student_pseudo` partout (l. 145-155 dans architecture.md). ChromaDB collection `rag_<subject>_<pseudo>` (ADR 004).
- § Workflows Clés § 1 (Upload de document) — la pipeline est celle que `UploadService.upload` encapsule.
- § API Endpoints § Documents — `POST /documents/upload` listé (l. 90). **Note** : le CLAUDE.md utilise `/documents/upload`, la story s10 utilise `/api/documents/upload`. **Discrepancy** à clarifier : le préfixe `/api` est-il requis ? Architecture.md n'utilise pas le préfixe `/api`. **Recommandation (R)** : utiliser le préfixe `/api` (convention REST moderne) ; c'est ce que la story demande.
- § Conventions de Code — snake_case fichiers, PascalCase classes, kebab-case URLs (`/documents/upload`), Pydantic pour les schémas, async pour I/O-bound.

### Research antérieurs consultés

- `docs/research/s01-uploader-document.md` — la pipeline RAG d'origine, les conventions de nommage, les pièges OCR.
- `docs/research/s04-repondre-qcm.md` — pattern de recherche, structure (sections 1-12), format des DoD.
- `docs/research/s07-repondre-texte-libre.md` — structure de recherche la plus récente (s08 deferred gate, re-vérification post-merges).

### Pas d'ADR nouveau requis

Les décisions s'inscrivent dans l'architecture cible existante. **Aucun nouvel ADR n'est nécessaire pour s10**. Le seul ADR potentiellement pertinent serait un ADR sur le préfixe `/api/` (vs pas de préfixe), mais la story est explicite et l'architecture ne tranche pas. **À documenter en PR description plutôt qu'en ADR**.

## Re-vérification (2026-09-01)

Cette recherche est livrée alors que :
- `main` est à `473181c` (= `a593fc8` + s05 (c8c9617) + s06 (f928d65) + s06b (394d4d4) + s07 (473181c) squashés).
- La branche `feature/s10-api-upload` est créée depuis `main`, HEAD = `473181c`, working tree clean.
- **Aucun travail précédent sur `app/api/`** (s09 est en parallèle, même situation).
- **Pas de `main.py` FastAPI** : le seul entry point est `__main__.py` qui invoque le CLI typer.
- **FastAPI installé en conda** (0.141.1) mais **pas dans `requirements.txt`** (gate bloquant pour la reproductibilité CI).
- **Pas de merge conflict attendu avec s05-s07** : s10 ne touche que `app/api/`, `app/main.py`, `requirements.txt`, `app/core/config.py` (potentiellement).

**Verdict** : la recherche est **solide**. La prémisse est **valide**. Le AC4 (« la logique d'ingestion est la MÊME que dans s01 ») est trivialement respecté par construction : la pipeline est dans `UploadService.upload`, le CLI et l'API appellent la même fonction. Le seul vrai risque structurel est le **CORS** (Piège 3) et le **tempfile cleanup** (Piège 1), qui ont des parades documentées. Le plan s10 peut être écrit sans modification des prémisses.
