# Review — Story s01-uploader-document

> Revu par : sous-agent `reviewer` (contexte frais).
> Date : 2026-08-28
> Source : `git diff main...feature/s01-uploader-document` vs `docs/plans/s01-uploader-document.md` + `docs/research/s01-uploader-document.md` + ADRs.
> Tests : **83 passed, 1 warning** (lancés par le reviewer, pas de confiance dans les résultats rapportés).
> Worktree : `C:\Workspace\ktutor\.worktrees\s01-uploader-document` (branche `feature/s01-uploader-document`).

## Plan compliance

- [x] Le code fait ce que le plan spécifie, rien de plus.
  - Tâches 1-16 présentes : `.gitignore`, init backend, `docker-compose.yml`, `.env.example`, modèle `Document`, `session.py`, client MinIO, embeddings, store ChromaDB, ingestion, OCR, service d'upload, CLI, ADR 007 + 008, tests.
  - Codes de sortie 0/1/2/3/4/5 implémentés et testés.
  - `python -m ktutor.cli upload <file> --pseudo <p> --subject maths` fonctionne (vérifié par `tests/cli/test_cli.py::TestCliSurface`).
  - Tous les AC (AC1-AC7) ont une couverture de test.
- [x] Interdits respectés.
  - `src/`, `test_quick.py`, `DeepSeek-OCR-2/`, `deepseek-ocr-python/` : non touchés.
  - `docs/prd.md`, `docs/stories.md`, `docs/architecture.md`, `docs/design-system.md` : non touchés.
  - `.env` : absent du diff (seul `backend/.env.example` est ajouté).
  - `frontend/` : non touché.
  - `app/api/` : non créé.

## Anti-hallucination

- [x] Aucune API / fonction / import inventé (chaque ouverture vérifiée).
  - `httpx` dans `ocr.py` et `cli.py`.
  - `chromadb.EphemeralClient()` / `chromadb.PersistentClient(path=...)`.
  - `langchain_text_splitters.RecursiveCharacterTextSplitter`.
  - `langchain_community.document_loaders.PyMuPDFLoader` (avec `DeprecationWarning` sur `langchain-community` sunset).
  - `minio.Minio`.
  - `pydantic_settings.BaseSettings`.
  - `typer.Typer` + `rich.console.Console`.
  - `sqlalchemy` 2.x.
- [x] Aucune valeur plausible-mais-fausse.
  - `MAX_UPLOAD_SIZE_MB=20` confirmé dans `config.py:47` et testé.
  - `LOW_CONFIDENCE_THRESHOLD = 0.5` confirmé dans `ocr.py:29` et testé.
  - Regex `^[a-zA-Z0-9_]{3,32}$` dans `chroma_store.py:15` et testée.
  - Convention de nommage ChromaDB `rag_<subject>_<pseudo>` dans `chroma_store.py:37`.
  - Préfixe MinIO `students/<pseudo>/<document_id>` dans `minio_client.py:85` et testé.
- [x] Le code matche ses claims.
  - `_build_service()` instancie MinIO + Chroma + embeddings + OCR + session factory comme documenté.
  - Le rollback dans `upload_service.py:196-198, 199-203` respecte l'AC4 (« Si une étape échoue APRÈS l'upload MinIO, on supprime l'objet MinIO »).

## Rules compliance

- [x] Conventions repo (AGENTS.md) : branche `feature/s01-uploader-document` ✓, worktree dédié ✓, TDD ✓, ADRs 007 + 008 créés ✓.
- [x] Aucun ADR contredit.
  - ADR 001 (monorepo) : respecté (seul `backend/`, pas de `frontend/`).
  - ADR 002 (POC rewrite from scratch) : respecté (greenfield, pas de réutilisation de `src/`).
  - ADR 004 (RAG isolation by collection) : respecté (collection par pseudo).
  - ADR 008 supersede partiel de `docs/architecture.md` § Stack (vision) — explicitement acté dans l'ADR 008.
- [x] Design system respecté (story CLI).
  - Pas d'UI ; uniquement sortie terminal.
  - `rich.console.Console` avec `success=green`, `error=red`, `warning=yellow`, `info=blue` — convention terminal, intent (success→green, error→red, warning→yellow) préservé. Le design dit « À ne pas copier dans la prod : la vraie sortie sera générée par `rich` » — comportement documenté.

## Tests

- [x] Suite de tests lancée par le reviewer, **83 passed, 1 warning**.
- [x] Assertions épinglent les acceptance criteria.
  - AC1 (PDF, chunks 1000/200, ChromaDB `rag_maths_<pseudo>`) : `test_ingestion.py::TestIngestTextPdf`, `test_chroma_store.py::TestGetCollection`, `test_upload_service.py::TestHappyPath::test_text_pdf_indexed_and_persisted`.
  - AC2 (image dactylo → OCR) : `test_upload_service.py::TestHappyPath::test_typed_image_uses_ocr_then_persists`.
  - AC3 (image manuscrite → OCR) : même pipeline OCR, chemin `manual_review_needed` testé.
  - AC4 (rollback) : `test_upload_service.py::TestRollback::test_minio_object_removed_on_chromadb_failure` et `TestSessionFailure::test_postgres_failure_rolls_back_minio`.
  - AC5 (codes de sortie CLI 0, 2, 3, 4, 5) : `test_cli.py::TestExitCodes`.
  - AC6 (row PostgreSQL + collection ChromaDB) : `test_upload_service.py::TestHappyPath::test_text_pdf_indexed_and_persisted`.
  - AC7 (isolation multi-tenant) : `test_chroma_store.py::TestMultiTenantIsolation::test_pseudo_a_cannot_see_pseudo_b_chunks`.
- [x] **Bite prouvé par neutralisation** (3 invariants cassés, restaurés, worktree clean).
  - **Invariant 1 — validation regex pseudo** : remplacement de `validate_pseudo` par un no-op → 7 tests rouges (`TestPseudoValidation::test_invalid_pseudo_rejected[*]`), 6 verts. Restauré.
  - **Invariant 2 — rollback AC4** : remplacement d'`UploadService.upload` par une version qui skip `self._minio.remove_object(minio_key)` → 3 tests rouges (`TestRollback::test_minio_object_removed_on_chromadb_failure`, `TestSessionFailure::test_postgres_failure_rolls_back_minio`, `TestManualReviewNeeded::test_ocr_http_error_raises_ocr_failure`). Restauré.
  - **Invariant 3 — isolation multi-tenant AC7** : remplacement de `ChromaStore.add_chunks` pour écrire dans une collection unique → 1 test rouge (`TestMultiTenantIsolation::test_pseudo_a_cannot_see_pseudo_b_chunks`). Restauré.
  - Aucun invariant n'est resté vert après neutralisation. Les invariants centraux sont réellement exercés.
- [x] Tests rendus redondants par la story : aucun (greenfield).

## Régressions

- [x] Aucun impact sur le code existant.
  - Repo greenfield — rien à régresser.
  - `langchain-community` est en sunset (`DeprecationWarning` pendant les tests). Dette tech pour s01+ mais pas une régression. Une story future devra migrer vers `langchain-pymupdf` ou un appel `pymupdf` direct.

## Findings

### minor — `backend/app/services/rag/upload_service.py:228-230` — accès aux attributs privés de `DocumentIngestor`

Le service accède à `self._ingestor._splitter._chunk_size`, `_chunk_overlap`, `_separators` (3 `# type: ignore[attr-defined]`). Couple `UploadService` à la structure interne de `DocumentIngestor`. Une méthode publique `DocumentIngestor.split_text(text, document_id) -> list[Chunk]` serait plus propre. **Code smell, pas un bug.**

### minor — `backend/app/services/rag/ingestion.py:41-48` — duplication de `OcrResult`

`OcrResult` est dupliqué en forward declaration pour éviter un import circulaire. Le vrai vit dans `ocr.py`. Les deux ont les mêmes champs mais la copie dans `ingestion.py` n'a pas `ocr_type` et `has_math`. Fonctionne parce que la coercion Pydantic accepte un sous-ensemble, mais un changement de schéma futur pourrait désynchroniser silencieusement les deux. **À déplacer vers un `app/services/rag/types.py` partagé, ou import paresseux.**

### minor — `docs/research/s01-uploader-document.md` dans le diff

Le plan dit que `docs/research/` est « non touchés », mais la research est un livrable de la story (Research → Plan → Execute → Review sur la même branche par `AGENTS.md`). Le plan texte est inconsistant avec le modèle pipeline documenté. **Mineur — incohérence de plan, pas un bug de code.**

### minor — `backend/app/cli.py:170-171` — spinner vide pour l'init

Le premier `with with_status.status("Initialisation…")` est un spinner vide (`pass`). UX un peu maladroite (deux spinners consécutifs pour une opération). **Fonctionnel et l'utilisateur voit un seul spinner visible. À replier dans le spinner principal de push MinIO + indexation.**

### minor — `backend/requirements.txt:28` — `langchain-community` sunset

`langchain-community>=0.3` est en sunset (DeprecationWarning à l'import). `PyMuPDFLoader` y vit encore. Une story future devra migrer vers `langchain-pymupdf` ou un appel `pymupdf` direct. **Dette documentée, à transformer en ADR de suivi quand la migration arrivera.**

## Non vérifié (vérification humaine recommandée)

- **Vrai serveur MinIO** : le plan dit « pas de test d'intégration avec MinIO ». Humain doit lancer `docker-compose up -d minio` et exercer `python -m ktutor.cli upload tests/fixtures/sample_cours.pdf --pseudo ali --subject maths` end-to-end. Vérifier la clé `students/ali/<uuid>` dans la console MinIO (`:9001`) et la collection `rag_maths_ali` peuplée dans ChromaDB.
- **Vrai service DeepSeek-OCR-2** : jamais contacté. `httpx.MockTransport` le simule. Humain doit lancer le service DeepSeek-OCR-2 (cf. `install_deepseek_ocr.bat` dans le worktree) et soumettre 3-5 images variées (dactylo, manuscrite, PDF scanné) pour confirmer parsing JSON, retry, seuil `confidence < 0.5`. Le « The point everything turns on » du plan le pointe explicitement.
- **Vrai PostgreSQL** : la row `Document` est testée sur `sqlite:///:memory:` dans `test_models.py` et via `FakeSession` dans `test_upload_service.py`. Le `Enum(..., native_enum=False, length=32)` Postgres-spécifique n'est pas exercé contre une vraie DB. Humain doit lancer `docker-compose up -d postgres` et confirmer que `init_db()` crée la table `documents` avec le bon schéma.
- **Multi-tenant sur la row SQL** : `test_filter_by_pseudo_returns_only_matching_rows` prouve le filtre fonctionne en SQLite, mais la FK vers `users.pseudo` n'est PAS ajoutée dans cette story (documenté dans `models.py:52` et plan tâche 5). Le différé FK sera ajouté en s15. Pour l'instant, rien n'empêche d'insérer `Document(student_pseudo="ghost")`. Acceptable pour s01 (AC6 ne demande que la création de la row), mais la garde réelle viendra en s13 (JWT-RBAC) + s15 (migration FK).
- **UX de `manual_review_needed`** : le design dit « Code de sortie : 0 (succès partiel, document NON persisté) » dans l'état 5, mais l'implémentation crée une row `Document` avec `status=manual_review_needed`. L'intent de l'AC4 (« persists nothing ») est débattable : le fichier source est dans MinIO et une row de métadonnées existe. À clarifier avec le produit : « aucun document persisté » signifie « aucun chunk indexé » (comportement actuel) ou « aucune row du tout » (lecture littérale du design).

## Verdict

Max severity: minor
Ship allowed: yes

---

## Suite

Review passée. Next step: /ks-ship s01-uploader-document

Note opérationnelle : 5 findings minor (code smells, dette doc, dépréciation à suivre). Aucun ne bloque le ship. Les 4 points « non vérifié » sont des vérifications humaines recommandées (MinIO, DeepSeek-OCR-2, PostgreSQL réel) — elles ne sont pas bloquantes pour le merge, mais une story de hardening pourrait les intégrer (testcontainers + service DeepSeek-OCR-2 de test).
