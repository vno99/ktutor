---
validated: yes
---

# Plan — Story s10-api-upload

Branch: `feature/s10-api-upload`
Research: `docs/research/s10-api-upload.md` — read it first; this plan does not repeat it.

## Target story

> **s10-api-upload** — Exposer l'upload de documents via FastAPI
>
> As an élève, I want téléverser un document depuis une interface web so that il soit indexé dans mon RAG.
>
> **Complexity (story)** : 2 — **Re-scored complexity** : **2 confirmé** (research § « Real complexity »). Pas de split. PR atomique, ~200-300 lignes.

### Acceptance criteria (verbatim `docs/stories.md:383-391`)

1. L'endpoint `POST /api/documents/upload` accepte `multipart/form-data` avec `pseudo`, `subject`, et `file` (PDF, PNG, JPG, JPEG, TXT — extension confirmée par `ALLOWED_EXTENSIONS` dans `upload_service.py:39`).
2. Au succès, retourne `{document_id: uuid, status: "indexed", chunks_count: int}` avec HTTP 201. (Pour `MANUAL_REVIEW_NEEDED`, `status` change et `chunks_count=0` — cf. piège 7.)
3. À l'échec (oversize, format non supporté, échec OCR), retourne 4xx avec `{error: "..."}` et ne persiste rien (roll-back S3 par `UploadService.upload:197-204`).
4. La logique d'ingestion est la MÊME que dans s01 — `UploadService.upload` est la **même fonction** que le CLI invoque (`cli.py:333`). **AC4 trivialement respecté**.
5. Un test uploade un petit PDF valide et vérifie la réponse.
6. Un test uploade un fichier trop gros et vérifie l'erreur 4xx.
7. Un test vérifie l'isolation multi-tenant au niveau service (collections ChromaDB distinctes par `pseudo`, `Document.student_pseudo` distinct).

### Décisions héritées de la recherche (cf. `docs/research/s10-api-upload.md` § « Open questions »)

| Q | Décision | Justification |
|---|---|---|
| Q1 (CORS) | **`main.py` configure `CORSMiddleware`** une fois pour s09 + s10. `Settings.cors_allowed_origins` ajouté en `s09`, s10 le consomme. | Évite la duplication, s'aligne sur la dépendance s09→s10. |
| Q2 (`UploadFile` stream) | **Option (a)** : `tempfile.NamedTemporaryFile` dans le router, `service.upload(tmp_path, ...)` + `try/finally` cleanup. | AC4 respecté strictement, `UploadService.upload` inchangé. |
| Q3 (`cors_allowed_origins`) | Défini par s09, **s10 hérite**. | s09 plan validé, s09 crée la var. |
| Q4 (taille : re-vérifier ?) | **Oui** : router vérifie `Content-Length` (best effort) ET taille post-read. Trois niveaux : header → router → service. | Piège 2, défense en profondeur. |
| Q5 (validation `subject`) | **Pydantic `Literal["maths", "francais"]`** côté API. CLI reste permissif (dette pré-existante). | Piège 5 — alignement avec `Subject` enum. |
| Q6 (forme 201 MANUAL_REVIEW) | `{document_id, status, chunks_count, ocr_confidence?}` avec `status="manual_review_needed"`. | Piège 7 — succès HTTP, pas une erreur. |
| Q7 (`python-multipart`) | Ajouté à `requirements.txt` (pré-tâche). | Piège 4 — bloquant pour `UploadFile`. |
| Q8 (`lifespan` vs `on_event`) | `lifespan` (async context manager). | Piège 10 — recommandé FastAPI 0.115+, `@on_event` deprecated. |
| Q9 (test cross-tenant) | Au niveau service : `ChromaStore.get_collection` retourne des collections distinctes. | Piège 9 — pas d'auth en s10, l'isolation est au service. |
| Q10 (`TestClient` sync) | `TestClient` sync (pas `httpx.AsyncClient`). | Convention FastAPI standard. |

### Dépendance s09→s10

**s10 dépend de s09 mergé**. Les deux stories modifient `backend/app/main.py`, `backend/app/api/`, et `backend/requirements.txt`. **Sans coordination, conflit de merge garanti.** Le plan s10 inclut **T0.1** (rebase sur `origin/main` qui doit contenir s09) et **T0.2** (validation de la présence des artefacts s09 dans le rebase).

**Note de l'orchestrateur** : s09 est planifié en parallèle et shippera en premier. Si l'ordre de merge change, s10 doit s'adapter — le plan reste valide tant que s09 est sur `main` au moment de l'exécution s10.

## Tasks (ordered)

> Ordre TDD strict : test rouge → code minimal → test vert. **Commit unique en fin de story** (AGENTS.md).

### Phase 0 — Rebase & pré-tâches (obligatoire)

- [x] **T0.1** — `git fetch origin && git rebase origin/main` dans le worktree. HEAD doit intégrer `f255046` (s08) **et** la squash de s09. **Note** : le squash s09 n'est pas encore sur `main` au moment de la planification. Si s09 n'est pas mergé, l'exécution s10 doit **attendre** que s09 soit mergé (ou faire un rebase --onto une fois s09 sur main). **Décision au moment de l'exécution** : si s09 n'est pas mergé, s10 NE DÉMARRE PAS — le reviewer le bloquera.
- [x] **T0.2** — Vérifier que les artefacts s09 sont présents : `backend/app/main.py` existe, `backend/app/api/chat/router.py` existe, `Settings.cors_allowed_origins` existe. Si l'un manque → STOP, demander à l'orchestrateur.
- [x] **T0.3** — Vérifier que `fastapi>=0.115` et `python-multipart>=0.0.9` sont **déjà** dans `requirements.txt` (s09 les a ajoutés). Si l'un manque → l'ajouter (pré-tâche partagée, s10 ne fait pas cavalier seul).
- [x] **T0.4** — Vérifier que l'import `from fastapi import Depends` dans `app/core/database/session.py:15` fonctionne (s09 a ajouté fastapi). Si l'import est cassé → le retirer (c'est un re-export mort — `Depends` n'est pas utilisé).

### Phase 1 — Wire-up de l'application (extensions sur l'existant s09)

- [x] **T1.1** — Vérifier que `Settings.subject_choices` (ou équivalent) est défini. Si non, l'ajouter comme `Literal["maths", "francais"]` — **décision** : importer `from app.core.database.models import Subject` et utiliser `Subject` enum comme type. **Ou** : créer un `Literal` dans `schemas.py`. Recommandation : `Literal` local au router (couplage minimal).
- [x] **T1.2** — Modifier `backend/app/main.py` pour ajouter `from app.api.documents.router import router as documents_router` (le fichier n'existe pas encore — c'est une faute de frappe de planification ; sera créé en T2). **Décision finale** : `app/main.py` est créé par s09, s10 ne fait qu'`include_router(documents_router)`. Le rebase en T0.1 intègre cette modification.
- [x] **T1.3** — Vérifier que `Settings.cors_allowed_origins` est consommé dans `main.py` (`app.add_middleware(CORSMiddleware, allow_origins=settings.cors_allowed_origins_list, ...)`). S09 l'a fait ; s10 ne touche pas.

### Phase 2 — Router FastAPI `documents`

- [x] **T2.1** — **Test bite** dans `backend/tests/api/test_documents.py` (nouveau) : `test_upload_accepts_multipart_with_pdf` — POST un PDF valide via `TestClient` avec un `UploadService` stubbé. Test bite : si le router n'est pas câblé → 404.
- [x] **T2.2** — **Schémas Pydantic** dans `backend/app/api/documents/schemas.py` (nouveau) :
  - `class UploadResponse(BaseModel)` : `document_id: UUID`, `status: str` (`"indexed"` | `"manual_review_needed"` | `"error"`), `chunks_count: int`, `ocr_confidence: float | None = None`.
  - `class UploadErrorResponse(BaseModel)` : `error: str`, `code: str` (`"invalid_pseudo"` | `"invalid_file"` | `"ocr_failure"` | `"storage_failure"`).
  - Note : pas de schéma pour le body — FastAPI `Form` field-by-field suffit (cf. T2.4).
- [x] **T2.3** — **Helper factory** dans `backend/app/api/documents/factory.py` (nouveau) : `def build_upload_service(settings: Settings) -> UploadService`. Réutilise le pattern de `cli.py:96-123` (`_build_service`). **Note** : duplication partielle avec le CLI est acceptable (s10 garde la cohérence ; un refactor commun est une dette hors-scope).
- [x] **T2.4** — **Router** dans `backend/app/api/documents/router.py` (nouveau) :
  - `router = APIRouter(prefix="/api/documents", tags=["documents"])`
  - `@router.post("/upload", status_code=201, response_model=UploadResponse)` :
    - `async def upload(pseudo: str = Form(...), subject: Literal["maths", "francais"] = Form(...), file: UploadFile = File(...), settings: Settings = Depends(get_settings))` :
      - Vérification `Content-Length` header (best effort) : `if request.headers.get("content-length") and int(...) > settings.max_upload_size_mb * 1024 * 1024: raise HTTPException(413, detail={"error": "Fichier trop volumineux", "code": "invalid_file"})`.
      - `data = await file.read()` ; `if len(data) > max_bytes: raise HTTPException(413, ...)` (Piège 2 — double check).
      - **Validation `subject`** (T1.1) : `Literal` Pydantic → 422 automatique si invalide.
      - **Validation `pseudo`** : ne PAS valider ici (laisser le service trancher, Piège 6, single source of truth). Mappage en 422 si `UploadError(INVALID_PSEUDO)`.
      - **Tempfile** : `tmp = tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False) ; tmp.write(data) ; tmp.close() ; tmp_path = tmp.name`. **try/finally** : `os.unlink(tmp_path)` en sortie, **même en cas d'exception**.
      - **Appel service** : `result = service.upload(tmp_path, pseudo, subject)`.
      - **Réponse 201** : `UploadResponse(document_id=result.document_id, status=result.status.value, chunks_count=result.chunks_count, ocr_confidence=result.ocr_confidence)`.
      - **Mapping `UploadError`** : dans un `except UploadError as exc` autour de l'appel service :
        - `INVALID_PSEUDO` → 422 + `UploadErrorResponse(error=exc.message, code="invalid_pseudo")`
        - `INVALID_FILE` → 413 (taille) ou 415 (extension) — discriminer via le message (contient "extension" → 415, contient "Taille" → 413)
        - `OCR_FAILURE` → 422
        - `STORAGE_FAILURE` → 500
- [x] **T2.5** — **Câblage du router dans `main.py`** : ajouter `app.include_router(documents_router)` dans `backend/app/main.py` (s09 a créé `main.py`, s10 ajoute la ligne). **Si rebase OK en T0.1**, ce changement est minime. **Si s09 a divergé**, résoudre le conflit en gardant les deux `include_router` (chat + documents).

### Phase 3 — Tests d'endpoint

- [x] **T3.1** — **Test bite AC1+AC2** : `test_upload_returns_201_with_id_status_chunks` — POST un PDF valide, assert 201 + `document_id` est un UUID + `status="indexed"` + `chunks_count > 0`. Test bite : router ne retourne pas `result.status.value` (mute en `"ok"`) → test rouge.
- [x] **T3.2** — **Test bite AC2 bis (MANUAL_REVIEW)** : `test_upload_returns_201_for_manual_review_needed` — stub le service pour retourner `UploadResult(status=MANUAL_REVIEW_NEEDED, chunks_count=0)`. Assert 201 + `status="manual_review_needed"`. Test bite : router mappe MANUAL_REVIEW sur 4xx → test rouge.
- [x] **T3.3** — **Test bite AC3 (oversize)** : `test_upload_oversize_returns_413` — POST un fichier de 25 MB (fixture `make_oversized_file` existe dans `conftest.py`). Assert 413 + `code="invalid_file"`. Test bite : retirer la vérif `Content-Length` ET la vérif post-read → test rouge.
- [x] **T3.4** — **Test bite AC3 (extension)** : `test_upload_unsupported_extension_returns_415` — POST un `.exe`. Assert 415 + `code="invalid_file"`. Test bite : router mappe `INVALID_FILE` toujours en 413 → test rouge.
- [x] **T3.5** — **Test bite AC3 (pseudo invalide)** : `test_upload_invalid_pseudo_returns_422` — POST `pseudo="ali ce"`. Assert 422 + `code="invalid_pseudo"`. Test bite : router n'attrape pas `UploadError(INVALID_PSEUDO)` → 500.
- [x] **T3.6** — **Test bite AC3 (OCR failure)** : `test_upload_ocr_failure_returns_422` — stub le service pour lever `UploadError(OCR_FAILURE, "low confidence")`. Assert 422 + `code="ocr_failure"`.
- [x] **T3.7** — **Test bite AC3 (storage failure)** : `test_upload_storage_failure_returns_500` — stub le service pour lever `UploadError(STORAGE_FAILURE, "S3 down")`. Assert 500 + `code="storage_failure"`.
- [x] **T3.8** — **Test bite (champ manquant)** : `test_upload_missing_file_field_returns_422` — POST sans `file`. Assert 422 (Pydantic auto).
- [x] **T3.9** — **Test bite (`subject` invalide)** : `test_upload_invalid_subject_returns_422` — POST `subject="physique"`. Assert 422 (Pydantic `Literal`).
- [x] **T3.10** — **Test bite AC4 (même service que CLI)** : `test_upload_uses_same_service_as_cli` — importer `cli._build_service()` et `api.documents.factory.build_upload_service()` et vérifier qu'ils retournent le même type d'instance (ou que les deux passent le même `UploadService` à un test d'intégration léger). Test bite : router utilise un service ad-hoc qui ne fait pas le pipeline complet → test rouge.
- [x] **T3.11** — **Test bite (cleanup tempfile)** : `test_upload_does_not_leave_tempfile` — après une requête valide **et** après une requête invalide, vérifier que `tempfile.gettempdir()` ne contient pas de fichier résiduel. Test bite : retirer `os.unlink` du `finally` → test rouge.
- [x] **T3.12** — **Test bite AC7 (cross-tenant)** : `test_pseudo_a_upload_not_visible_to_pseudo_b` — uploader en tant que `pseudo_a`, uploader en tant que `pseudo_b`, vérifier que `ChromaStore.get_collection("maths", "alice")` contient 1 doc et `ChromaStore.get_collection("maths", "bob")` contient 1 doc **différent**. Test bite : `UploadService.upload` ignore `pseudo` → les deux collections contiennent le même doc → test rouge.
- [x] **T3.13** — **Test bite CORS (preflight)** : `test_cors_preflight_succeeds_for_allowed_origin` — `OPTIONS /api/documents/upload` avec `Origin: http://localhost:3000` → 200 + `Access-Control-Allow-Origin: http://localhost:3000`. Test bite : middleware retiré → 400.
- [x] **T3.14** — **Test bite CORS (origine refusée)** : `test_cors_preflight_fails_for_disallowed_origin` — `OPTIONS` avec `Origin: http://evil.com` → 400. Test bite : `allow_origins=["*"]` → 200.
- [x] **T3.15** — **Fixture `client`** dans `backend/tests/api/conftest.py` (nouveau ou extension de `backend/tests/conftest.py`) : `client = TestClient(app)` + `upload_service_stub` (un `UploadService` avec `FakeS3`, `FakeEmbeddings`, `FakeSession`, `_build_service` pattern depuis `tests/services/rag/test_upload_service.py:27`).

### Phase 4 — Configuration & documentation

- [x] **T4.1** — Vérifier que `CORS_ALLOWED_ORIGINS` est documenté dans `backend/.env.example` (s09 l'a fait). Si non, l'ajouter.
- [x] **T4.2** — Étendre `docs/architecture.md` § Repo structure : confirmer `backend/app/api/documents/router.py` (vs `documents.py` plat). **Note** : la convention `docs/architecture.md:52-60` liste `app/api/<domaine>/` (sous-dossier). **Décision** : s10 utilise un sous-dossier `app/api/documents/` (avec `router.py`, `schemas.py`, `factory.py`) — **cohérent** avec la convention.
- [x] **T4.3** — Étendre `docs/architecture.md` § API Endpoints : ajouter le bloc « Documents » avec `POST /api/documents/upload`, body, response, errors.

### Phase 5 — Definition of Done

- [x] **T5.1** — `pytest -x -m "not integration"` passe. Tous les tests existants (s01-s07 + s08 mergé sur main) + 14 nouveaux tests s10.
- [x] **T5.2** — `ruff check backend/app backend/tests` passe (0 erreur).
- [x] **T5.3** — Vérification manuelle : `uvicorn app.main:app` démarre sans erreur, `POST /api/documents/upload` accepte multipart et retourne 201 sur succès. Note le résultat dans la PR description.
- [x] **T5.4** — Tous les tests bite du plan passent (cf. liste T3).
- [x] **T5.5** — PR unique, commit unique (`feat(api): add /api/documents/upload endpoint (s10)`), description structurée : résumé, AC cochées, **points d'attention** (dépendance s09 mergé, tempfile cleanup, CORS hérité de s09, AC4 trivialement respecté par `UploadService.upload` partagé).
- [x] **T5.6** — Pas de régression sur s01-s08 (le CLI `python -m ktutor.cli upload` continue de fonctionner).

## Run interdicts

- **NE PAS** modifier `backend/app/services/rag/upload_service.py`. La fonction `upload` est le contrat partagé. AC4 en dépend.
- **NE PAS** modifier `backend/app/services/rag/ingestion.py`, `chroma_store.py`, `ocr.py`, `embeddings.py`, `storage/minio_client.py`. Run interdicts hérités de s01-s07.
- **NE PAS** modifier `backend/app/cli.py`. La commande `upload` reste intacte. Le CLI et l'API appellent la même `UploadService.upload`.
- **NE PAS** créer de nouveau modèle SQLAlchemy. `Document` (models.py:53-97) couvre tous les champs. `init_db()` est idempotent.
- **NE PAS** ajouter d'auth JWT. Auth stub via `body.pseudo`. Migration JWT = s15.
- **NE PAS** merger dans `main` localement. PR ouverte, merge manuel.
- **NE PAS** commit par tâche. **Commit unique en fin de story**.
- **NE PAS** utiliser `git worktree remove` ou `git checkout` sur la branche `main`.
- **NE PAS** installer `sse-starlette`. (Hors-scope — s09 l'a exclu.)
- **NE PAS** ajouter de `try/except` muets. Toutes les exceptions doivent logger via `loguru` ou être explicitement mappées vers une réponse HTTP.
- **NE PAS** démarrer l'exécution s10 si s09 n'est pas mergé sur `main`. STOP et notifier l'orchestrateur.

## The point everything turns on

**Le router FastAPI doit appeler `UploadService.upload(tmp_path, body.pseudo, body.subject)` avec le `pseudo` du body — sans le réécrire.** C'est le seul invariant que AC7 (cross-tenant) protège : si une régression future remplace `body.pseudo` par un pseudo hardcodé (e.g. pour les tests), l'upload atterrit dans la collection ChromaDB d'un autre élève, et l'isolation multi-tenant casse en silence.

**Trois endroits où ça peut péter** :
1. **T2.4** (router) — `pseudo = body.pseudo` (via `Form(...)`) doit être préservé jusqu'à l'appel `service.upload(tmp_path, pseudo, subject)`. Le test bite `test_pseudo_a_upload_not_visible_to_pseudo_b` (T3.12) le vérifie directement.
2. **T2.4** (router) — `subject` doit être passé tel quel à `service.upload`. La validation `Literal["maths", "francais"]` filtre les valeurs aberrantes (T3.9), mais ne réécrit pas la valeur.
3. **T1.3** (rebase) — `main.py` doit contenir `app.include_router(documents_router)` **ET** `app.include_router(chat_router)`. Si le rebase s09→main drop l'un des deux, la régression n'est détectée qu'au runtime.

**La review doit s'attarder sur ces trois points** — ce sont les seuls où une régression silencieuse peut passer les tests unitaires et ne péter qu'en production multi-tenant.

## Files touched

### Created

| Fichier | Rôle |
|---|---|
| `backend/app/api/__init__.py` | Package marker (s09 ne le crée pas explicitement, vérifié). |
| `backend/app/api/documents/__init__.py` | Package marker. |
| `backend/app/api/documents/router.py` | `POST /api/documents/upload` + `UploadFile` + `Form` + tempfile + mapping `UploadError`. |
| `backend/app/api/documents/schemas.py` | `UploadResponse`, `UploadErrorResponse`. |
| `backend/app/api/documents/factory.py` | `build_upload_service(settings)` (réutilise le pattern `cli._build_service`). |
| `backend/tests/api/__init__.py` | Package marker (s09 le crée peut-être — vérifier). |
| `backend/tests/api/test_documents.py` | 14 tests `TestClient` (cf. T3). |
| `backend/tests/api/conftest.py` | Fixture `client` + `upload_service_stub` (si pas déjà créé par s09). |

### Modified

| Fichier | Modification |
|---|---|
| `backend/app/main.py` | Ajouter `from app.api.documents.router import router as documents_router` + `app.include_router(documents_router)`. **Modif minimale** si s09 a créé `main.py` (rebase T0.1). |
| `docs/architecture.md` | Étendre § API Endpoints avec le bloc « Documents » (T4.3). |
| `backend/.env.example` | Vérifier `CORS_ALLOWED_ORIGINS` documenté (T4.1). |

### NOT touched (run interdicts)

- `backend/app/services/rag/upload_service.py` (AC4 — service partagé CLI+API)
- `backend/app/services/rag/ingestion.py`, `chroma_store.py`, `ocr.py`, `embeddings.py`
- `backend/app/services/storage/minio_client.py`
- `backend/app/cli.py` (commande `upload` intacte)
- `backend/app/core/database/models.py` (s10 n'ajoute pas de colonne)
- `backend/app/services/agents/*`, `backend/app/services/exercises/*`, `backend/app/services/correction/*` (hors-scope)

## Test strategy

### Tests automatisés (un par AC + bites)

| AC | Test | Couche | Fichier |
|---|---|---|---|
| AC1 (multipart) | `test_upload_accepts_multipart_with_pdf` | HTTP | `test_documents.py::TestUploadEndpoint` |
| AC2 (201 + payload) | `test_upload_returns_201_with_id_status_chunks` | HTTP | idem |
| AC2 (MANUAL_REVIEW) | `test_upload_returns_201_for_manual_review_needed` | HTTP | idem |
| AC3 (oversize) | `test_upload_oversize_returns_413` | HTTP | idem |
| AC3 (extension) | `test_upload_unsupported_extension_returns_415` | HTTP | idem |
| AC3 (pseudo) | `test_upload_invalid_pseudo_returns_422` | HTTP | idem |
| AC3 (OCR) | `test_upload_ocr_failure_returns_422` | HTTP | idem |
| AC3 (storage) | `test_upload_storage_failure_returns_500` | HTTP | idem |
| AC4 (même service) | `test_upload_uses_same_service_as_cli` | Service | idem |
| AC5 (PDF valide) | Couvert par AC1+AC2 | — | — |
| AC6 (trop gros) | `test_upload_oversize_returns_413` | HTTP | idem |
| AC7 (cross-tenant) | `test_pseudo_a_upload_not_visible_to_pseudo_b` | HTTP + service | `test_documents.py::TestCrossTenant` |

### Tests bite (à valider par le reviewer)

| Test bite | Prouve que | Test rouge si |
|---|---|---|
| `test_upload_returns_201_with_id_status_chunks` | `status` retourné = `result.status.value` | Hardcodé `"ok"` |
| `test_upload_returns_201_for_manual_review_needed` | `MANUAL_REVIEW_NEEDED` est un succès HTTP (201) | Mapper en 4xx |
| `test_upload_oversize_returns_413` | Double check taille (Content-Length + post-read) | L'un des deux retiré |
| `test_upload_unsupported_extension_returns_415` | Mapping discriminant taille/extension | Tout en 413 |
| `test_upload_invalid_pseudo_returns_422` | Mapping `UploadError(INVALID_PSEUDO)` → 422 | `except` retiré |
| `test_upload_does_not_leave_tempfile` | `os.unlink` dans `finally` | `unlink` retiré |
| `test_pseudo_a_upload_not_visible_to_pseudo_b` | `body.pseudo` propagé jusqu'au retriever | Hardcodé dans le router |
| `test_cors_preflight_succeeds_for_allowed_origin` | Middleware CORS actif | Middleware retiré |
| `test_cors_preflight_fails_for_disallowed_origin` | CORS refuse les origines non listées | `allow_origins=["*"]` |
| `test_upload_invalid_subject_returns_422` | Pydantic `Literal` sur `subject` | Validation retirée |
| `test_upload_missing_file_field_returns_422` | FastAPI 422 auto sur champ manquant | Schéma retiré |
| `test_upload_uses_same_service_as_cli` | Router appelle `UploadService.upload` (pas une variante) | Service ad-hoc dans le router |

### Vérifications manuelles (smoke)

| Action | Critère de succès |
|---|---|
| `uvicorn app.main:app --reload` | Démarre sans erreur, lifespan `init_db()` silencieux. |
| `curl -F "pseudo=alice" -F "subject=maths" -F "file=@sample.pdf" http://localhost:8000/api/documents/upload` | 201 + `{"document_id": "...", "status": "indexed", "chunks_count": N}`. |
| `curl -F "pseudo=alice" -F "subject=maths" -F "file=@big.pdf" http://localhost:8000/api/documents/upload` (25 MB) | 413 + `{"error": "...", "code": "invalid_file"}`. |
| `python -m ktutor.cli upload --help` | CLI intact, `upload` toujours fonctionnel. |
| `pytest -x -m "not integration"` | Tous les tests passent. |

## Definition of Done

- [ ] **Tâches** : toutes les cases T0.1 → T5.6 cochées.
- [ ] **Tests** : `pytest -x -m "not integration"` passe. ≥ 95% des tests existants + 14 nouveaux.
- [ ] **Lint** : `ruff check backend/app backend/tests` passe.
- [ ] **AC1-AC7** : tous couverts par des tests `TestClient` ou service.
- [ ] **Tests bite** : les 12 tests bite listés dans `Test strategy` passent.
- [ ] **CLI non régressé** : `python -m ktutor.cli upload --help` fonctionne, `python -m ktutor.cli upload <file> --pseudo <p> --subject maths` retourne 0 sur succès.
- [ ] **Aucune régression s01-s08** : tous les tests existants passent.
- [ ] **Pas de duplication de logique** : le router appelle `UploadService.upload` (AC4 strict).
- [ ] **Tempfile cleanup** : aucun fichier résiduel après une requête valide ou invalide.
- [ ] **CORS** : un preflight depuis `http://localhost:3000` passe, depuis une autre origine échoue.
- [ ] **Commit unique** : un seul commit sur la branche.
- [ ] **PR ouverte** : description structurée (résumé, AC cochées, **points d'attention** : dépendance s09 mergé, `UploadService.upload` partagé CLI+API, CORS hérité de s09, tempfile cleanup).
- [ ] **Review passée** : `docs/reviews/s10-api-upload.md` avec `Max severity: <...>` et `Ship allowed: yes`.

### Notes pour la review

- **Score 2 confirmé** : pas de LLM, pas de state machine, pas de migration DB, pipeline métier déjà factorisée. Le seul vrai travail est l'exposition HTTP.
- **AC4 trivialement respecté** : `UploadService.upload` est appelée à la fois par `cli.py:333` et par le router s10. **Aucun risque de divergence** (vérifié par `test_upload_uses_same_service_as_cli`).
- **Dépendance s09→s10** : s10 doit rebase sur `origin/main` qui contient s09. Si s09 n'est pas mergé au moment de l'exécution, s10 NE DÉMARRE PAS.
- **CORS** : hérité de s09, pas de modification de `main.py` côté CORS.
- **Pas de Conversation/Message** : s19 (hors-scope).
- **Pas d'auth JWT** : `pseudo` dans le body, migration en s15.
