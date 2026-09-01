---
story: s10-api-upload
reviewer: reviewer (anti-hallucination, fresh context)
date: 2026-09-01
worktree: C:/Workspace/ktutor/.worktrees/s10-api-upload
branch: feature/s10-api-upload
commit: 9d5cbc3 feat(api): add /api/documents/upload endpoint (s10)
default_branch_at_review: c5f6163 (s09 squash, s08 included)
---

# Review — s10-api-upload

**Diff reviewed** : `git diff origin/main...feature/s10-api-upload` (single commit `9d5cbc3` on top of s09-squashed `c5f6163`).

**Tests run by reviewer** : `pytest` (412 passed) + `pytest tests/api/test_documents.py` (15 passed). `ruff check` passes sur le scope s10.

## Plan compliance

- [x] Code does what the plan specifies. Every T0–T5 task is implemented.
- [x] **Run interdicts respected** — vérifié via `git show 9d5cbc3 -- <file>` :
  - `backend/app/services/rag/upload_service.py` — inchangé (AC4 contract preserved)
  - `backend/app/services/rag/ingestion.py`, `chroma_store.py`, `ocr.py`, `embeddings.py` — inchangés
  - `backend/app/services/storage/minio_client.py` — inchangé
  - `backend/app/cli.py` — inchangé dans le commit s10 (le diff cli.py plus large vs main est le s08 progressive-correction rewire qui a atterri avant que s10 ne rebase)
  - `backend/app/core/database/models.py` — inchangé
  - `backend/app/core/database/session.py` — inchangé dans s10 (T0.4 no-op confirmé : `Depends` est déjà dans `if TYPE_CHECKING:` à la ligne 15)
- [x] T0.4 vérifié comme un vrai no-op : le `from fastapi import Depends` a été déplacé dans `TYPE_CHECKING` par s09, le commit s10 ne touche pas session.py.

## Anti-hallucination

- [x] Pas d'API/fonction/import inventé. Tous les imports dans `router.py`, `factory.py`, `schemas.py` résolvent vers des symboles existants (`UploadError`, `UploadErrorKind`, `UploadService`, `DocumentStatus`, `MinioClient`, `ChromaStore`, `MultimodalOcr`, `DocumentIngestor`, `get_settings`).
- [x] `Settings.cors_allow_origins`, `Settings.cors_allow_origins_list`, `Settings.max_upload_size_mb` — tous confirmés présents dans `app/core/config.py`.
- [x] `FakeS3` dans `tests/services/storage/test_s3_client.py` — confirmé.
- [x] `chromadb.EphemeralClient()` — confirmé.
- [x] `UploadResult`, `UploadError`, `UploadErrorKind` shapes matchent le dataclass/enum dans `upload_service.py`.
- [x] `app.include_router(documents_router)` dans `main.py` — confirmé (s10 ajoute seulement les 2 lignes attendues ; CORSMiddleware intact, hérité de s09).

## Rules compliance

- [x] Conventions repo respectées : snake_case fichiers, PascalCase classes, kebab-case URLs, schémas Pydantic, loguru pour le logging, `Depends(get_settings)` injection.
- [x] ADR 004 (ChromaDB isolation by collection) — respecté : test cross-tenant confirme l'isolation `rag_<subject>_<pseudo>`.
- [x] ADR 005 (JWT/RBAC) — s10 utilise `pseudo` dans le body, auth stub acceptable per story scope (migration JWT = s15).
- [x] ADR 009 (SeaweedFS) — inchangé dans s10.
- [x] ADR 010 (FastAPI streaming) — s10 réutilise le lifespan et le middleware CORS introduits par s09.

## Tests

- [x] 15 nouveaux tests s10 ; tous les 412 tests totaux passent.
- [x] **Bite prouvé par neutralization** (technique + restore obligation remplie) :
  - **Tempfile cleanup bite** : changé `if tmp_path is not None:` en `if tmp_path is not None and False:` dans `router.py:186` → `test_upload_does_not_leave_tempfile` rouge. Restauré. `git diff --exit-code` clean.
  - **Cross-tenant bite** : hardcodé `service.upload(tmp_path, "alice", subject)` dans `router.py:162` → `test_pseudo_a_upload_not_visible_to_pseudo_b` rouge (`assert count_a >= 1` failed with 0). Restauré. `git diff --exit-code` clean.
  - **CORS bite** : commenté le bloc `app.add_middleware(CORSMiddleware, ...)` dans `main.py:63-69` → les deux tests CORS rouges (`405` au lieu de `200`/`400`). Restauré. `git diff --exit-code` clean.

## Findings

### critical
Aucun.

### major

1. **major — `backend/tests/api/test_documents.py:441` — `test_upload_uses_same_service_as_cli` est une tautologie.** Le test fait deux imports `from app.services.rag.upload_service import UploadService` (lignes 433 et 439, le second aliasé `US`) puis assert `US is UploadService`. C'est toujours vrai, peu importe ce que la factory retourne. Une régression qui introduirait une sous-classe `UploadService` API-only ou remplacerait le callsite de la factory par une implémentation parallèle ne serait pas attrapée. La vraie protection d'AC4 dans cette suite est `test_pseudo_a_upload_not_visible_to_pseudo_b` (le cross-tenant bite), qui exerce le path runtime `body.pseudo → service.upload(tmp_path, pseudo, subject)`. Le plan a explicitement identifié ce test comme "the point everything turns on" (`docs/plans/s10-api-upload.md:141-148`) ; le shared-service test est décoratif. Fix suggéré : assert `type(get_upload_service_dep()) is UploadService` et `type(cli_build_service()) is UploadService` au runtime, ou assert que `get_upload_service_dep.__module__ == "app.api.documents.factory"` (i.e. non patché/remplacé) et que le cross-tenant test est la preuve load-bearing.

### minor

1. **minor — `backend/tests/conftest.py:28-55` — autouse `_isolated_loguru_sink` est over-scoped.** La fixture est autouse et function-scoped, attachée au `tests/conftest.py` racine. Cela veut dire qu'elle tourne pour chaque test s01-s10, pas seulement s10. La motivation documentée dans la docstring (messages français `UploadError` du router s10 cassant le capture pytest cp1252 stderr) est spécifique au router s10. Un fix plus étroit aurait vécu dans `tests/api/conftest.py` (API tests seulement) ou `tests/api/test_documents.py` (s10 seulement). Vérifié : aucun test s01-s09 ne dépend en pratique du sink loguru production (aucun usage `caplog`/`capsys`/`capfd` ; `configure_logging()` dans `app/core/logging.py` n'est jamais appelé). Donc le scope-creep est inoffensif aujourd'hui, mais (a) touche un fichier sur lequel tous les tests des autres stories s'appuient, et (b) pose un précédent pour que les futures stories élargissent la surface. Classifier : minor, scope-creep pas bug.

2. **minor — `backend/app/api/documents/router.py:75-78` — `_map_invalid_file_to_status` discrimine par substring-matching sur le message d'erreur du service ("extension" vs "Taille").** Cela couple le router au wording interne du service. Un futur changement de message dans `upload_service.py:115-126` (par ex. traduire les messages, ou reworder "Taille" → "Trop gros") retournerait silencieusement 413→415 ou 415→413 sans qu'aucun test ne pète. Le plan l'a signalé comme Piège 11 et l'implémenteur a noté le couplage dans la docstring (lignes 27-31). Un design propre serait une nouvelle sous-classe `UploadError` par kind (par ex. `InvalidFileSizeError`, `InvalidFileExtensionError`) — mais ça demande de toucher `upload_service.py` qui est un run-interdict. Le couplage actuel est acceptable pour s10 mais vaut un ADR de suivi si le service grandit en failure modes.

3. **minor — `backend/app/api/documents/router.py:1-32` — la module docstring documente le mapping `INVALID_FILE` pour taille et extension, mais la fonction `_map_invalid_file_to_status` n'a pas de test inline pour le edge case message vide.** Si le service levait jamais `UploadError(INVALID_FILE, "")`, la fonction retournerait 413 (default branch). Pas déclenchable actuellement, mais un `raise ValueError` défensif ou un `logger.error` serait plus sûr.

## Not verified

- **Vrai wire-up HTTP contre uvicorn qui tourne + vrai S3 + vrai ChromaDB** : pas exercé dans cette review. Le test cross-tenant utilise `chromadb.EphemeralClient()` et `FakeS3`, qui exercent l'intégration API/service mais pas la vraie SeaweedFS ni ChromaDB persistant. Un humain devrait : `docker-compose up -d postgres redis seaweedfs chroma`, puis `uvicorn app.main:app --reload`, puis `curl -F "pseudo=alice" -F "subject=maths" -F "file=@sample_cours.pdf" http://localhost:8000/api/documents/upload` et vérifier 201 + que le document apparaît dans `chroma list` et dans PostgreSQL `SELECT * FROM documents`.
- **Vrai PDF avec texte body non-ASCII passant par le pipeline OCR** : pas exercé. Le test cross-tenant utilise un `httpx.MockTransport` in-memory qui retourne du JSON canned. Un humain devrait : uploader un PDF français avec caractères accentués et vérifier les chunks ChromaDB.
- **Frontend (s11) consommant réellement l'endpoint** : hors-scope. Un humain devrait : lancer le Next.js dev server et vérifier que le form poste un vrai PDF et rend la réponse succès/erreur.
- **Le vrai bénéfice de la fixture autouse `_isolated_loguru_sink` sur Windows** : confirmé conceptuellement (Python rapporte `sys.stderr.encoding='cp1252'`) mais la suite de tests a été lancée dans l'env conda qui a déjà le mode `UTF-8`. La fixture peut être superflue dans cet env exact. Un humain devrait : lancer la suite dans un Python Windows vanilla (sans hack conda UTF-8) et confirmer que le message français déclenche vraiment une teardown failure sans la fixture.
- **Comportement de la branche `OSError` dans le cleanup `finally` (router.py:189-196)** : je n'ai pas construit de test qui force `os.unlink` à échouer. Le code path est un logger.warning fallback, pas un invariant testable.

## Files reviewed (absolute paths)

- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/app/api/documents/router.py`
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/app/api/documents/schemas.py`
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/app/api/documents/factory.py`
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/app/api/documents/__init__.py`
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/app/main.py`
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/tests/api/test_documents.py`
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/tests/api/conftest.py`
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/tests/conftest.py`
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/app/services/rag/upload_service.py` (run-interdict, vérifié inchangé)
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/app/cli.py` (run-interdict, vérifié inchangé dans le commit s10)
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/app/core/database/session.py` (T0.4 verify, inchangé)
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/backend/app/core/config.py` (Settings.cors_allow_origins + max_upload_size_mb)
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/docs/plans/s10-api-upload.md`
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/docs/research/s10-api-upload.md`
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/docs/decisions/004-rag-isolation-by-collection.md` (cross-tenant convention)
- `C:/Workspace/ktutor/.worktrees/s10-api-upload/docs/decisions/010-fastapi-streaming.md` (CORS inheritance)

## Summary for the gate

- Tous les ACs sont couverts par des tests nommés.
- 412 tests verts, ruff clean.
- 3 mutations red→green sur les invariants centraux (tempfile cleanup, cross-tenant `body.pseudo`, CORS allow-list).
- 0 critical, 1 major, 3 minor.
- **Major** : `test_upload_uses_same_service_as_cli` est tautologique — l'invariant AC4 réel est porté par le cross-tenant bite (et confirmé par la mutation). C'est décoratif, pas un trou de couverture, mais c'est un signal que le test ne fait pas ce que son nom prétend.
- Le ship n'est pas bloqué. Le major est documenté pour backlog — la protection runtime d'AC4 est ailleurs.

Max severity: major
Ship allowed: yes
