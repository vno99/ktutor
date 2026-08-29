# Review — Story s01b-migrate-storage-to-seaweedfs

> Revu par : sous-agent `reviewer` (contexte frais).
> Date : 2026-08-29
> Source : `git diff main...feature/s01b-migrate-storage-to-seaweedfs` vs `docs/plans/s01b-migrate-storage-to-seaweedfs.md` + `docs/research/s01b-migrate-storage-to-seaweedfs.md` + ADRs 001/002/003/004/005/006/007/008/009.
> Tests : **86 passed** (lancés par le reviewer, pas de confiance dans les résultats rapportés) — couverture **86.12%** (seuil 80%).
> Lint : `ruff check app tests` → **All checks passed**.
> Worktree : `C:\Workspace\ktutor\.worktrees\s01b-migrate-storage-to-seaweedfs` (branche `feature/s01b-migrate-storage-to-seaweedfs`).

## Plan compliance

- [x] Le code fait ce que le plan spécifie, rien de plus.
  - Tâches 1-21 toutes cochées. Vérifié par `git diff --stat` + lecture du diff.
  - **Tâche 1 — Alembic init** : `backend/alembic.ini` (149 lignes), `backend/alembic/env.py` (72 lignes), `backend/alembic/script.py.mako`, `backend/alembic/__init__.py`, `backend/alembic/versions/__init__.py`, `backend/alembic/README` ajoutés. `env.py` charge `get_settings().database_url` et `Base.metadata` comme spécifié. `prepend_sys_path = .` dans `alembic.ini` rend `app` importable. **OK**.
  - **Tâche 2 — docker-compose seaweedfs** : `chrislusf/seaweedfs:4.44`, `command: server -dir=/data -s3 -s3.port=8333`, port 8333, volume `seaweedfs_data`. Healthcheck `curl -f http://localhost:8333/`. Aucun service `minio` ne subsiste. **OK**.
  - **Tâche 3 — env.example S3_*** : 4 vars `S3_*` présentes, `MINIO_*` totalement supprimées (commentaire sur le SDK `minio` acceptable, AC2 demande la suppression des vars). `grep -c "MINIO"` → 0. **OK**.
  - **Tâche 4 — config s3_*** : 4 champs `s3_*` présents, defaults alignés sur les credentials de la fixture SeaweedFS (`ktutorci` / `ktutorci_secret`). `grep -ic "minio"` → 0. **OK**.
  - **Tâche 5 — CI yml S3_*** : 4 envs `S3_*` présentes, `MINIO_*` totalement supprimées. **OK**.
  - **Tâche 6 — colonne s3_key** : `models.py:57` porte `s3_key: Mapped[str]`. `__repr__` ne référence pas la colonne (juste `id, pseudo, subject, status, chunks`). `grep -c "minio_key"` → 0. **OK**.
  - **Tâche 7 — migration Alembic** : `f6211a490dce_rename_minio_key_to_s3_key.py` avec `op.alter_column("documents", "minio_key", new_column_name="s3_key")` (upgrade) + inverse (downgrade). **Réversible, vérifié par `test_rename_minio_key.py` et exécution manuelle** (`alembic upgrade head` puis `alembic downgrade -1` sur SQLite jetable, données préservées — round-trip `('x', 'students/ali/x')` OK).
  - **Tâche 8 — upload_service** : `UploadResult.minio_key` → `s3_key`, `_minio` → `_s3`, paramètre `minio_client` → `s3_client`, `minio_key` local → `s3_key`, `Document(..., s3_key=...)`. `grep -c "minio_key"` → 0. **OK**.
  - **Tâche 9 — cli.py** : `settings.s3_*`, `s3_client = MinioClient(...)`, sortie JSON `"s3_key"`. `grep -c "minio"` → 1 (l'import `from app.services.storage.minio_client import MinioClient` à la ligne 40, inévitable car le run interdit défend le rename du fichier et de la classe — voir Findings). **Acceptable**.
  - **Tâche 10 — test_s3_client.py** : `git mv` (similarity 67% confirme le rename) + classe `FakeMinio` → `FakeS3`. 7 tests passent. **OK**.
  - **Tâche 11 — test_upload_service.py** : `FakeS3`, `fake_s3`, `s3_client=...`, commentaires mis à jour. **OK**.
  - **Tâche 12 — test_cli.py** : `_StubService` retourne `s3_key=...` au lieu de `minio_key=...`. **OK**.
  - **Tâche 13 — test_models.py** : 5 occurrences `s3_key` au lieu de `minio_key`. **OK**.
  - **Tâches 14-18 — Doc** : `CLAUDE.md` (l.36 + l.521 + l.595-598 + l.634), `docs/prd.md`, `docs/architecture.md` (3 MinIO → SeaweedFS, plus `minio_key` → `s3_key` et `source_image_minio_key` → `source_image_s3_key` dans le schéma forward-looking), ADR 002, ADR 004. **OK**, à noter que la modification de `CLAUDE.md` au-delà des 2 lignes initialement spécifiées est signalée comme déviation par l'implémenteur.
  - **Tâches 19-21 — Vérification finale** : pytest 86 OK (86.12% cov ≥ 80%), ruff clean, grep global laisse uniquement les références attendues (SDK dans `requirements.txt`, imports dans `minio_client.py`, ADR 007 supersédé, ADR 009 nouvelle, recherche/plan/review figés de s01). **OK**.

- [x] Interdits respectés.
  - `backend/app/services/storage/minio_client.py` et la classe `MinioClient` non renommés (vérifié : `ls backend/app/services/storage/` et `grep "class MinioClient"`). Le SDK `minio>=7.2` reste en `requirements.txt:24`.
  - `backend/tests/fixtures/garage.toml` non supprimé (vérifié : `ls backend/tests/fixtures/`).
  - `docs/research/s01-uploader-document.md`, `docs/plans/s01-uploader-document.md`, `docs/reviews/s01-uploader-document.md` non modifiés (`git diff` vide).
  - `docs/decisions/007-minio-from-s01.md` modifié **uniquement** au frontmatter (Status, note de supersession) — le contenu historique reste intact. **OK**.
  - Aucun alias rétrocompat `minio_*` dans `config.py` (vérifié par lecture complète).
  - `docs/decisions/001-monorepo-backend-frontend.md`, `003-langgraph-supervisor.md`, `005-auth-rs256-rbac.md`, `006-frontend-nextjs-app-router.md`, `008-deepseek-ocr-2-for-vision.md` non touchés (`git diff` vide).
  - Un seul commit sur la branche (`48cb6c1`), pas de commit sur la branche par défaut.

## Anti-hallucination

- [x] Aucune API / fonction / import inventé (chaque ouverture vérifiée).
  - `minio.Minio`, `minio.error.S3Error` : confirmés dans `backend/app/services/storage/minio_client.py:12-13`. SDK déjà installé (`requirements.txt:24`, `minio>=7.2`).
  - `alembic.op.alter_column(..., new_column_name=...)` : API documentée Alembic 1.13+. Version installée : 1.19.1 (vérifié). La migration appelle `op.alter_column("documents", "minio_key", new_column_name="s3_key")` qui est l'API standard.
  - `alembic.context.config.set_main_option`, `context.run_migrations`, `engine_from_config`, `pool.NullPool` : API standard Alembic, présente dans `env.py`.
  - `pydantic_settings.BaseSettings` : confirmé dans `config.py:11`.
  - `subprocess.run([..., "alembic", ...])` : API Python stdlib. Le test `test_rename_minio_key.py` l'utilise pour invoquer alembic en sous-processus avec un `DATABASE_URL` jetable.
  - `sqlalchemy.create_engine`, `text(...)`, `PRAGMA table_info(...)` : API SQLAlchemy 2.0 + SQLite standard, utilisée dans le test de migration.
  - `chrislusf/seaweedfs:4.44` : image DockerHub officielle, déjà référencée par `backend/tests/fixtures/seaweedfs/Dockerfile` (fixture préexistante, non touchée par cette story).

- [x] Aucune valeur plausible-mais-fausse.
  - `s3_endpoint: str = "localhost:8333"` : aligné sur le port exposé par `docker-compose.yml` (8333:8333) et par la CI (`S3_ENDPOINT: localhost:8333`), et par la fixture `seaweedfs/Dockerfile` (`-s3.port=8333`).
  - `s3_access_key: str = "ktutorci"`, `s3_secret_key: str = "ktutorci_secret"` : baked-in dans `backend/tests/fixtures/seaweedfs/s3config.json` (`accessKey: ktutorci, secretKey: ktutorci_secret`). Cohérent.
  - `s3_bucket: str = "assistant-documents"` : préservé de s01 (était `minio_bucket`).
  - Volume `seaweedfs_data` : cohérent avec le `-dir=/data` du `command` SeaweedFS.
  - Healthcheck `curl -f http://localhost:8333/` : SeaweedFS expose un endpoint HTTP sur le port S3 (le binaire `server -s3` répond sur ce port). Acceptable comme readiness probe.

- [x] Le code matche ses claims.
  - `MinioClient.put_object(pseudo, document_id, filename, data)` construit `f"students/{pseudo}/{document_id}"` via `_build_key` (vérifié l.83-84) — invariant multi-tenant conservé.
  - `UploadService._s3.put_object(...)` est appelé en step 1, `self._s3.remove_object(s3_key)` en rollback (UploadError + Exception) — pattern identique à s01.
  - `alembic/versions/f6211a490dce_rename_minio_key_to_s3_key.py` fait exactement `op.alter_column("documents", "minio_key", new_column_name="s3_key")` (upgrade) et l'inverse (downgrade) — pas d'invention.
  - `env.py:32` `config.set_main_option("sqlalchemy.url", get_settings().database_url)` — l'URL de l'env prend le pas sur l'ini placeholder, comme documenté.

## Rules compliance

- [x] Conventions repo (AGENTS.md) : branche `feature/s01b-migrate-storage-to-seaweedfs` ✓, worktree dédié ✓, TDD ✓, ADR 009 créé ✓, ADR 007 marqué superseded ✓, un seul commit sur la branche ✓.
- [x] Aucun ADR contredit.
  - **ADR 001 (monorepo)** : respecté (uniquement `backend/` modifié).
  - **ADR 002 (POC rewrite)** : `docs/decisions/002-poc-rewrite-from-scratch.md` mis à jour : MinIO → SeaweedFS dans la mention contexte. Cohérent.
  - **ADR 003 (LangGraph supervisor)** : non touché.
  - **ADR 004 (RAG isolation)** : `docs/decisions/004-rag-isolation-by-collection.md` mis à jour : MinIO → SeaweedFS (S3). Le préfixe `students/<pseudo>/<document_id>` est explicitement préservé. Cohérent avec la décision d'ADR 009.
  - **ADR 005 (auth RS256)** : non touché.
  - **ADR 006 (frontend Next.js)** : non touché.
  - **ADR 007 (MinIO dès s01)** : `Status: superseded by 009` + note d'avertissement en tête. Le contenu historique est intact (run interdict respecté). **OK**.
  - **ADR 008 (DeepSeek-OCR-2)** : non touché.
  - **ADR 009 (SeaweedFS remplace MinIO)** : créé au format MADR, `Status: accepted`, `Supersedes: ADR 007`. Context mentionne EACCES sur le volume MinIO, decision acte SeaweedFS, considered options explorées, consequences documentées. **OK**.
- [x] Design system / UI : N/A (story backend/runtime, pas d'UI).
- [x] **Multi-tenancy** : le préfixe `students/<pseudo>/<document_id>` est conservé tel quel. `MinioClient._build_key` (l.83-84) construit toujours `f"students/{pseudo}/{document_id}"`. Test `test_upload_service.py::TestHappyPath::test_text_pdf_indexed_and_persisted` (l.171) asserte `any(k.startswith(f"students/{pseudo}/") for k in keys)`. Le test d'isolation cross-tenant ChromaDB (`test_chroma_store.py::TestMultiTenantIsolation::test_pseudo_a_cannot_see_pseudo_b_chunks`) est toujours vert.

## Tests

- [x] Suite de tests lancée par le reviewer (`cd backend && pytest --cov=app --cov-fail-under=80 -m "not integration"`) → **86 passed, 1 warning, coverage 86.12%**. La warning concerne `langchain-community` sunset (`ingestion.py:20`), dette préexistante à s01, non bloquante.
- [x] Assertions épinglent les acceptance criteria.
  - **AC1 (service seaweedfs dans docker-compose)** : vérifié par lecture du YAML.
  - __AC2 (S3__ dans .env.example, MINIO__ supprimées)** : vérifié par grep + lecture.
  - __AC3 (s3__ dans config.py, pas d'alias)_* : vérifié par lecture.
  - **AC4 (SDK minio>=7.2 conservé)** : `requirements.txt:24` intact.
  - **AC5 (fixture SeaweedFS référencée)** : `backend/tests/fixtures/seaweedfs/{Dockerfile,s3config.json}` (déjà conforme, non touché). CI `.github/workflows/ci.yml:22-98` build l'image GHCR.
  - **AC6 (tests `services/storage` passent)** : `test_s3_client.py` (7 tests) tous verts.
  - **AC7 (préfixe multi-tenant + isolation cross-tenant vert)** : `test_s3_client.py::TestPutObject::test_key_follows_students_pseudo_document_id_convention` (l.101-104) asserte `key == f"students/ali/{document_id}"`. `test_upload_service.py::TestHappyPath::test_text_pdf_indexed_and_persisted` (l.161-181) asserte que la clé uploadée a le préfixe. Test d'isolation ChromaDB inchangé.
  - **AC8 (colonne s3_key, migration incluse)** : `test_models.py` (5 assertions `s3_key=...`), `test_rename_minio_key.py` (3 tests : script existe, upgrade rename + data preserved, downgrade revert + data preserved).
  - **AC9 (doc à jour)** : vérifié par grep (`MinIO` → 0 dans tous les fichiers attendus).
  - **AC10/AC11 (ADR 009 + ADR 007 superseded)** : fichiers présents et frontmatter conforme.
  - **AC12 (aucun impact sur s02+)** : aucune story aval n'existe encore (greenfield). La CI job `build-seaweedfs` était déjà SeaweedFS, donc les stories futures seront S3-compatible dès le départ.
- [x] **Bite prouvé par neutralisation** : 1 invariant cassé, restauré, worktree clean.
  - **Invariant central — préfixe multi-tenant** : remplacement de `_build_key` pour retourner `f"OTHER/{pseudo}/{document_id}"` au lieu de `f"students/{pseudo}/{document_id}"` → **3 tests rouges** : `test_s3_client.py::TestPutObject::test_key_follows_students_pseudo_document_id_convention`, `test_s3_client.py::TestGetObject::test_returns_bytes_for_existing_key`, `test_upload_service.py::TestHappyPath::test_text_pdf_indexed_and_persisted`. Restauré. `git diff --exit-code` clean sur `minio_client.py`. **L'invariant central est réellement exercé.**
- [x] Tests non redondants : les tests existants lockent le contrat ; le nouveau test Alembic (`test_rename_minio_key.py`) verrouille la réversibilité de la migration (justifié par l'AC8 et la procédure de vérification manuelle du plan, qui dit « alembic upgrade head puis alembic downgrade -1 »).

## Régressions

- [x] Aucun impact sur les chemins de code existants au-delà du scope.
  - `MinioClient` API publique inchangée (`__init__`, `ensure_bucket`, `put_object`, `get_object`, `remove_object` — toutes les signatures préservées).
  - Préfixe `students/<pseudo>/<document_id>` inchangé.
  - `Document` schéma : seul `minio_key` → `s3_key` (1 colonne, type `String(512) NOT NULL`).
  - Aucune story en aval n'existe encore (greenfield en s01b, après s01).

## Findings

### minor — `backend/app/services/storage/minio_client.py:50` — docstring obsolète

Le docstring de `put_object` dit encore : `The returned key has the form \`\`students/<pseudo>/<document_id>\`\` and is the value persisted in the \`\`documents.minio_key\`\` column.` La colonne est désormais `documents.s3_key` (AC8). L'implémenteur a gardé le fichier intact par respect du run interdit (« **Ne PAS renommer** le fichier `backend/app/services/storage/minio_client.py` ni la classe `MinioClient`. … Le SDK Python`minio` reste utilisé. ») — la modification aurait été légitime uniquement dans un commentaire. **Code smell, pas un bug.** À fixer dans une story de cleanup post-migration.

### minor — `backend/app/services/storage/minio_client.py:62, 73` — paramètres `minio_key` non renommés

Les méthodes `get_object(self, minio_key: str)` et `remove_object(self, minio_key: str)` exposent encore un paramètre nommé `minio_key`. Cohérent avec le contenu (la valeur passée est bien une clé S3) mais le nom est trompeur post-migration. Le plan AC8 + le champ `UploadResult.s3_key` ont renommé la donnée mais pas le nom de paramètre. **Cosmétique, pas un bug.** Les tests utilisent des kwargs positionnels ou des f-strings, donc rien ne casse au call-site.

### minor — `backend/app/cli.py:40` — `grep -c "minio"` retourne 1 au lieu de 0

Le plan AC9 / Tâche 9 spécifiait `grep -c "minio" backend/app/cli.py` → 0 (sensible à la casse). L'import `from app.services.storage.minio_client import MinioClient` à la ligne 40 est **inévitable** : le run interdit défend le rename de `minio_client.py` et `MinioClient`. Le test `grep -c "minio"` retourne donc 1 (l.40 seule). L'implémenteur a signalé cette déviation (Déviation #3). **Accepté par la force des interdits.**

### minor — `backend/app/services/storage/minio_client.py:1, 17, 88` — commentaires internes « MinIO » non mis à jour

Le module docstring (l.1) dit encore `"""MinIO / S3 client for storing uploaded source files."""`. Le docstring de classe (l.17) dit `"""Thin wrapper around \`\`minio.Minio\`\` enforcing our key convention."""`. Le commentaire de`_guess_content_type` (l.88) dit `"""Best-effort MIME guess from the file extension (MinIO needs one)."""`. Le plan § Run interdits autorisait explicitement les « commentaires internes seulement si pertinent » — l'implémenteur n'a pas mis à jour ces commentaires. **Cosmétique.** Aucun impact sur le comportement, mais crée une incohérence de surface : le runtime et la doc sont SeaweedFS, les commentaires sont MinIO.

### minor — `backend/.env.example:29` — commentaire SDK `minio`

La ligne `# S3-compatible object store. The Python SDK is the \`minio\` package` est conservée. Justifiée par AC4 (SDK `minio` préservé). Le `grep -c "MINIO"` retourne 0 (variable `MINIO_*` n'existe plus), seul un commentaire mentionne le nom du package. **OK au sens de l'AC2.**

### minor — `.github/workflows/ci.yml:64` — commentaire obsolète `minio`

Le commentaire `# Service containers: without a job-level \`container:\`, services are accessed via the published ports on localhost. The service labels (postgres, minio, chroma) are NOT resolvable as DNS in this mode` mentionne encore `minio` au lieu de `seaweedfs`. La section env`S3_*` est correcte. **Drift cosmétique de commentaire.** Le job `backend` continue de fonctionner (les services sont en fait `postgres`,`seaweedfs`,`chroma`), mais le commentaire est trompeur pour un futur lecteur.

### minor — Plan violation : tests nouveaux (Déviation acceptée)

Le plan § Test strategy dit « **Pas de test nouveau (scope respecté). Cette story est une migration, pas une refonte.** » L'implémenteur a créé `backend/tests/migrations/test_rename_minio_key.py` (166 lignes, 3 tests). **Cependant**, le plan § Tâche 7 / § Définition of Done dit aussi « alembic upgrade head puis alembic downgrade -1 fonctionnent » — la procédure de vérification manuelle du plan demandait précisément cette garantie, que le test automatise. La déviation est **justifiée par la procédure de vérification du plan lui-même**, et le test est solide (il bite, neutralisé plus haut). **Accepté.**

### minor — Plan deviation : `CLAUDE.md` modifié au-delà des 2 lignes spécifiées (Déviation acceptée)

Le plan § Tâche 14 spécifiait les lignes 36 et 521 uniquement. L'implémenteur a aussi mis à jour :

- l.595-598 : `MINIO_ENDPOINT=minio:9000` etc. → `S3_ENDPOINT=localhost:8333` etc. (l'exemple `.env` reproduit dans CLAUDE.md)
- l.634 : `docker-compose up -d postgres redis minio chroma` → `… seaweedfs chroma`

Ces modifications sont **internement cohérentes** : le bloc env dans CLAUDE.md (l.595-598) doit suivre la même migration que `.env.example` (Tâche 3), et la commande docker-compose dans CLAUDE.md (l.634) doit suivre la même migration que `docker-compose.yml` (Tâche 2). Sans ces changements, CLAUDE.md mentirait aux lecteurs qui suivent ses instructions. **Déviation raisonnable, justifiée par cohérence interne.**

### minor — `docs/architecture.md:214` — renommage schema `source_image_minio_key` → `source_image_s3_key`

Hors scope strict de la story (la table `evaluations` n'est pas encore implémentée — elle sera créée en s15 ou une story future), mais le renommage garde la cohérence du schéma documenté. Le plan § Tâche 16 dit « remplacer les 3 occurrences "MinIO" par "SeaweedFS" (ou "SeaweedFS (S3)") ». Le renommage de colonne dans un schéma forward-looking est un bonus de cohérence. **OK, justifiable.**

## Non vérifié (vérification humaine recommandée)

- **Vrai service SeaweedFS via docker-compose** : le reviewer n'a pas lancé `docker-compose up -d seaweedfs postgres redis chroma`. Humain doit :
  1. Tirer l'image `chrislusf/seaweedfs:4.44` (l'image custom GHCR est buildée en CI, mais l'image officielle DockerHub suffit en local).
  2. Lancer `docker compose up -d seaweedfs`.
  3. Exercer `python -m ktutor.cli upload tests/fixtures/sample_cours.pdf --pseudo ali --subject maths` end-to-end.
  4. Vérifier que la clé `students/ali/<uuid>` apparaît dans SeaweedFS (via `mc alias set local http://localhost:8333 ktutorci ktutorci_secret` + `mc ls local/assistant-documents/students/ali/`).
  5. Vérifier que la collection `rag_maths_ali` est peuplée dans ChromaDB.
  6. Tester le rollback : uploader un PDF corrompu, vérifier que la clé S3 est bien supprimée.

- **Vrai PostgreSQL** : `init_db()` n'a pas été exécuté contre une vraie DB Postgres dans cette story (les tests utilisent SQLite in-memory ou FakeSession). Humain doit lancer `docker compose up -d postgres` et confirmer que `init_db()` crée la table `documents` avec la colonne `s3_key` (et pas `minio_key`). Puisque la migration Alembic ne **crée pas** la table (seulement `alter_column`), `init_db()` (`Base.metadata.create_all`) doit avoir été appelée **avant** la migration. C'est cohérent avec le state pré-migration (s01 a déjà `Base.metadata.create_all` quelque part dans le CLI), mais l'ordre `init_db()` → `alembic upgrade head` doit être vérifié contre un vrai Postgres.

- **Migration Alembic sur PostgreSQL** : testée sur SQLite (transactionnel, types permissifs). Le `op.alter_column("documents", "minio_key", new_column_name="s3_key")` doit aussi fonctionner sur Postgres (qui supporte `ALTER TABLE ... RENAME COLUMN`). Le test SQLite est une bonne heuristique mais pas une preuve formelle sur Postgres. Humain doit appliquer la migration sur une instance Postgres jetable (locale ou via le service CI `postgres`).

- **Vrai CI run** : le job `build-seaweedfs` et le job `backend` doivent passer en CI. Le reviewer n'a pas push la branche ni déclenché le workflow. La modification de `.github/workflows/ci.yml` (env `S3_*`) ne peut être validée que par un run CI réel.

- **Test cross-tenant S3 strict** : la story introduit un test d'isolation S3 partiel (`test_s3_object_removed_on_chromadb_failure` vérifie que la clé du pseudo courant est retirée sur rollback) mais ne teste pas explicitement qu'un élève A ne peut pas uploader/lire les données d'un élève B. C'est cohérent avec le scope (l'isolation S3 est garantie par construction — la clé contient le pseudo), mais un test « pseudo_a ne peut pas écrire dans le bucket de pseudo_b » serait un renforcement futur (déjà couvert pour ChromaDB par `TestMultiTenantIsolation`).

- **`garage.toml` fixture** : vestige d'un précédent testbench (commentaire interne parle de « Region set to us-east-1 so the minio>=7.2 Python client »). Conservé par run interdict, à supprimer dans une story de cleanup dédiée. Aucun impact fonctionnel.

Max severity: minor
Ship allowed: yes
