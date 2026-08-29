---
validated: yes
---
# Plan — Story s01b-migrate-storage-to-seaweedfs

Branch: `feature/s01b-migrate-storage-to-seaweedfs`
Research: `docs/research/s01b-migrate-storage-to-seaweedfs.md` — read it first; this plan does not repeat it.

## Target story

**Story** : s01b-migrate-storage-to-seaweedfs — Migrer le stockage objet de MinIO vers SeaweedFS
**Complexity** : 2 (changement de runtime, pas de logique métier ; API publique du client inchangée)

### Acceptance criteria (12 ACs, du research)

1. `docker-compose.yml` : service `seaweedfs` (image `chrislusf/seaweedfs:4.44`, S3 port 8333), aucun service `minio`.
2. `backend/.env.example` : `S3_*` (4 vars), `MINIO_*` supprimées.
3. `backend/app/core/config.py` : `s3_*` ; pas d'alias rétrocompat.
4. SDK Python reste `minio` (>=7.2) — compatible S3.
5. Fixture `backend/tests/fixtures/seaweedfs/` référencée par CI et tests.
6. Tests `backend/tests/services/storage/` passent contre SeaweedFS.
7. Préfixe `students/<pseudo>/<document_id>` conservé ; test d'isolation cross-tenant reste vert.
8. Colonne `documents.minio_key` → `documents.s3_key` (migration incluse).
9. Doc : `CLAUDE.md` (l.36 + l.521), `docs/prd.md`, `docs/architecture.md`, ADR 002, ADR 004.
10. ADR 009 existe (✅ déjà fait).
11. ADR 007 `Status: superseded by 009` (✅ déjà fait).
12. Aucun impact sur stories aval (s02+).

## Tasks (ordered)

> **Décisions tranchées au planning** (issues de la research § Open questions) :
>
> - **Q1 (Alembic)** : on initialise Alembic dans cette story si non déjà fait. Cohérent avec `docs/architecture.md` (mentionne `alembic/` dans la structure cible). Sinon, on documente un `ALTER TABLE` manuel dans le PR description.
> - **Q2 (volume `minio_data`)** : renommé en `seaweedfs_data`. Pas de données à migrer.
> - **Q3 (`garage.toml`)** : hors-scope, ticket de cleanup séparé.
> - **Q4 (renommer `test_minio_client.py`)** : oui, en `test_s3_client.py`. Cohérence avec le contenu testé.
> - **Q5 (champ privé `_minio` → `_s3`)** : oui, par cohérence.

### Étape 0 — Outillage

1. [x] **Initialiser Alembic** (si non déjà fait) : `cd backend && alembic init alembic`. Configurer `alembic.ini` + `env.py` pour pointer sur `app.core.config.get_settings().database_url` et `app.core.database.models.Base.metadata`. Si Alembic est déjà initialisé, sauter cette tâche.

### Étape 1 — Runtime (docker-compose + env)

2. [x] **Modifier `docker-compose.yml`** : remplacer le service `minio` (l. 32-48) par un service `seaweedfs` (image `chrislusf/seaweedfs:4.44`, port 8333, volume `seaweedfs_data`). Le volume nommé `minio_data` devient `seaweedfs_data` (l. 70). **Vérification** : `docker compose config --services` liste `postgres, redis, seaweedfs, chroma` (pas `minio`).

3. [x] **Modifier `backend/.env.example`** (l. 28-32) : remplacer les 4 lignes `MINIO_*` par `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`. Mettre à jour le commentaire de section. **Vérification** : `grep -c "MINIO" backend/.env.example` retourne `0`.

### Étape 2 — Config Python

4. [x] **Modifier `backend/app/core/config.py`** (l. 39-43) : renommer les 4 champs `minio_*` en `s3_*` (et le commentaire "File Storage"). Aucune valeur par défaut relative à MinIO ; les valeurs par défaut pointent vers SeaweedFS local : `s3_endpoint: str = "localhost:8333"`, `s3_access_key: str = "ktutorci"`, `s3_secret_key: str = "ktutorci_secret"`, `s3_bucket: str = "assistant-documents"`. **Vérification** : `grep -c "minio" backend/app/core/config.py` retourne `0` (sensible à la casse).

5. [x] **Modifier `.github/workflows/ci.yml`** (l. 70-73) : renommer l'env block en `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`. Le service et le port (8333) restent inchangés. **Vérification** : `grep -c "MINIO_" .github/workflows/ci.yml` retourne `0`.

### Étape 3 — Schéma BDD

6. [x] **Renommer la colonne `documents.minio_key` → `documents.s3_key`** dans `backend/app/core/database/models.py` (l. 57). Mettre à jour le `__repr__` (l. 71-76) en cohérence. **Vérification** : `grep -c "minio_key" backend/app/core/database/models.py` retourne `0`.

7. [x] **Créer la migration Alembic** `alembic/versions/<hash>_rename_minio_key_to_s3_key.py` avec `op.alter_column("documents", "minio_key", new_column_name="s3_key")`. **Vérification** : `alembic upgrade head` puis `alembic downgrade -1` fonctionnent (sur une base jetable locale, pas en CI).

### Étape 4 — Code applicatif

8. [x] **Modifier `backend/app/services/rag/upload_service.py`** :
   - Imports : aucun changement (le client reste `MinioClient`).
   - Champ dataclass `UploadResult.minio_key` → `s3_key` (l. 66).
   - Champ privé `self._minio` → `self._s3` (l. 98) ; le type hint `minio_client: MinioClient` reste.
   - Paramètre `minio_client=` du constructeur → `s3_client=` (l. 90). Idem dans `cli.py` et `test_upload_service.py`.
   - Variables locales `minio_key = ...` → `s3_key = ...` (l. 132, 153, 164, 183, 194, 198, 203).
   - Paramètre `minio_key: str` de `_persist_document` → `s3_key: str` (l. 254, 272).
   - Champ passé au modèle : `Document(..., s3_key=s3_key, ...)` (l. 272).
   - **Vérification** : `grep -c "minio_key" backend/app/services/rag/upload_service.py` retourne `0`.

9. [x] **Modifier `backend/app/cli.py`** :
   - Instanciation `MinioClient(...)` reste (l. 55), mais lit `settings.s3_endpoint`, `settings.s3_access_key`, `settings.s3_secret_key`, `settings.s3_bucket` (l. 56-59).
   - Sortie JSON : `"minio_key": result.minio_key` → `"s3_key": result.s3_key` (l. 92).
   - Variable locale `minio_client = ...` → `s3_client = ...` (l. 55, 73).
   - **Vérification** : `grep -c "minio" backend/app/cli.py` retourne `0` (sensible à la casse).

10. [x] **Renommer le fichier de test `backend/tests/services/storage/test_minio_client.py` → `test_s3_client.py`** (Q4 tranchée : oui). À l'intérieur : renommer la classe `FakeMinio` → `FakeS3` (et tous ses `self.fake_minio` → `self.fake_s3`). Mettre à jour le docstring d'en-tête. Le contrat testé (key multi-tenant, content-type inféré, idempotence du `remove_object`) est **inchangé**. **Vérification** : `pytest backend/tests/services/storage/test_s3_client.py` passe.

11. [x] **Modifier `backend/tests/services/rag/test_upload_service.py`** :
    - Import `from app.services.storage.minio_client import MinioClient` reste (l. 26).
    - Import `from tests.services.storage.test_minio_client import FakeMinio` → `from tests.services.storage.test_s3_client import FakeS3` (l. 27).
    - Variables `fake_minio = FakeMinio()` → `fake_s3 = FakeS3()` (l. 72, 215, 236, 248, 278).
    - Paramètre `minio_client=...` du constructeur `UploadService` → `s3_client=...` (l. 113).
    - Commentaire méthode `test_minio_object_removed_on_chromadb_failure` → `test_s3_object_removed_on_chromadb_failure` (l. 246).
    - Commentaire `test_postgres_failure_rolls_back_minio` → `test_postgres_failure_rolls_back_s3` (l. 272).
    - **Vérification** : `pytest backend/tests/services/rag/test_upload_service.py` passe.

12. [x] **Modifier `backend/tests/cli/test_cli.py`** (l. 52, 61) : `minio_key=f"students/{pseudo}/stub"` → `s3_key=f"students/{pseudo}/stub"`. **Vérification** : `pytest backend/tests/cli/test_cli.py` passe.

13. [x] **Modifier `backend/tests/core/test_models.py`** (l. 35, 56, 64, 85, 102) : `minio_key="..."` → `s3_key="..."` dans la construction des `Document` de test. **Vérification** : `pytest backend/tests/core/test_models.py` passe.

### Étape 5 — Doc

14. [x] **Modifier `CLAUDE.md`** :
    - l. 36 : `- **File Storage**: MinIO / S3` → `- **File Storage**: S3 (SeaweedFS, S3-compatible)`
    - l. 521 : `- **MinIO** : préfixe de clé \`students/<student_pseudo>/<document_id>\`.` → `- **SeaweedFS (S3)** : préfixe de clé \`students/<student_pseudo>/<document_id>\`. Le SDK Python \`minio>=7.2\` est utilisé (compatible S3).`
    - **Vérification** : `grep -c "MinIO" CLAUDE.md` retourne `0` (sensible à la casse).

15. [x] **Modifier `docs/prd.md`** : remplacer toutes les mentions "MinIO" par "SeaweedFS" (en préservant le contexte S3-compatible). **Vérification** : `grep -c "MinIO" docs/prd.md` retourne `0`.

16. [x] **Modifier `docs/architecture.md`** (l. 23, l. 153, l. 275) : remplacer les 3 occurrences "MinIO" par "SeaweedFS" (ou "SeaweedFS (S3)"). Ajouter une note d'intégration dans le tableau "Integration points" (l. 275) si pertinent. **Vérification** : `grep -c "MinIO" docs/architecture.md` retourne `0`.

17. [x] **Modifier `docs/decisions/002-poc-rewrite-from-scratch.md`** : remplacer "MinIO" par "SeaweedFS" partout où la mention porte sur le runtime (pas sur les ADR superseded). **Vérification** : `grep -c "MinIO" docs/decisions/002-poc-rewrite-from-scratch.md` retourne `0`.

18. [x] **Modifier `docs/decisions/004-rag-isolation-by-collection.md`** : remplacer "MinIO" par "SeaweedFS" (la convention de préfixe `students/<pseudo>/<document_id>` est conservée). **Vérification** : `grep -c "MinIO" docs/decisions/004-rag-isolation-by-collection.md` retourne `0`.

### Étape 6 — Vérification finale

19. [x] **Run global** : `cd backend && pytest --cov=app --cov-fail-under=80 -m "not integration"` (mêmes options que `.github/workflows/ci.yml` l. 195). **Vérification** : tous les tests passent, couverture ≥ 80%.

20. [x] **Lint** : `cd backend && ruff check app tests` (mêmes options que `.github/workflows/ci.yml` l. 156). **Vérification** : 0 erreur.

21. [x] **Vérification grep globale** : `grep -rni "minio" backend/ docs/ CLAUDE.md docker-compose.yml 2>/dev/null | grep -v ".pyc"` ne retourne que :
    - les fichiers/classes qui restent par décision explicite (le SDK `minio` Python dans `requirements.txt` l. 24 et les imports `from minio import Minio` dans `backend/app/services/storage/minio_client.py` l. 12-13)
    - les références historiques dans ADR 002, 004 (commentaire "avant cette migration" éventuel)
    - `docs/decisions/007-minio-from-s01.md` (l'ADR superseded, volontairement intacte)
    - `docs/decisions/009-seaweedfs-replaces-minio.md` (la nouvelle ADR qui mentionne MinIO dans le Context et Considered Options)
    - **Tous les autres résultats sont des échecs** : la migration n'est pas complète.

## Run interdicts

- **Ne PAS renommer** le fichier `backend/app/services/storage/minio_client.py` ni la classe `MinioClient`. Le SDK Python `minio` reste utilisé (Q4/Q5 ne s'appliquent qu'au fichier de test et au champ privé `_minio` → `_s3`). Décision explicite pour limiter le diff.
- **Ne PAS supprimer** `backend/tests/fixtures/garage.toml` — vestige, hors-scope.
- **Ne PAS modifier** `docs/research/s01-uploader-document.md`, `docs/plans/s01-uploader-document.md`, `docs/reviews/s01-uploader-document.md` — ils décrivent l'état livré de s01, figé.
- **Ne PAS modifier** `docs/decisions/007-minio-from-s01.md` au-delà du frontmatter (déjà fait). Son contenu historique reste.
- **Ne PAS ajouter** d'alias rétrocompat `minio_*` dans `config.py`. Casse nette (AC3).
- **Ne PAS toucher** aux autres ADR (001, 003, 005, 006, 008) qui ne mentionnent pas MinIO.
- **Ne PAS commit** depuis la base du repo. Tout le travail se fait dans `.worktrees/s01b-migrate-storage-to-seaweedfs/`.
- **Ne PAS push** vers `main` directement. PR obligatoire.

## The point everything turns on

**Le renommage doit être atomique dans la PR** : à mi-migration, le code applicatif attend `settings.s3_*` mais l'env peut encore exposer `MINIO_*` (ou inversement). Casse nette, pas d'alias. Si la PR est splittée en commits séparés (un commit par fichier), chaque commit intermédiaire doit être cassé — c'est OK sur une branche de feature non mergée, mais le rebase et la review deviennent pénibles.

**Deux endroits où ce plan peut se tromper** :

1. **L'initialisation Alembic** (étape 0). Si Alembic n'est pas initialisé et qu'on saute cette étape, la migration de colonne se fera "à la main" via `Base.metadata.create_all` qui re-crée la table — perte de données. Si Alembic est déjà initialisé, on saute. **À vérifier en début d'exécution** : `ls backend/alembic/` doit être non-vide.
2. **Le rename de fichier de test** (étape 10). `git mv` est préférable à `Write` + `Delete` pour conserver l'historique. Si l'agent d'exécution oublie, l'historique git perd la trace du rename.

## Files touched

**Code** (11 fichiers) :

- `docker-compose.yml` (modifié)
- `backend/.env.example` (modifié)
- `backend/app/core/config.py` (modifié)
- `backend/app/core/database/models.py` (modifié)
- `backend/app/services/rag/upload_service.py` (modifié)
- `backend/app/cli.py` (modifié)
- `backend/tests/services/storage/test_minio_client.py` (renommé en `test_s3_client.py`)
- `backend/tests/services/rag/test_upload_service.py` (modifié)
- `backend/tests/cli/test_cli.py` (modifié)
- `backend/tests/core/test_models.py` (modifié)
- `.github/workflows/ci.yml` (modifié, env block uniquement)
- `backend/alembic/versions/<hash>_rename_minio_key_to_s3_key.py` (nouveau, si Alembic initialisé)
- `backend/alembic.ini` + `backend/alembic/env.py` (nouveau, si Alembic pas encore initialisé)

**Doc** (5 fichiers) :

- `CLAUDE.md` (modifié)
- `docs/prd.md` (modifié)
- `docs/architecture.md` (modifié)
- `docs/decisions/002-poc-rewrite-from-scratch.md` (modifié)
- `docs/decisions/004-rag-isolation-by-collection.md` (modifié)

**Non touchés** (run interdicts) :

- `backend/app/services/storage/minio_client.py` (commentaires internes seulement si pertinent)
- `backend/requirements.txt`
- `backend/tests/fixtures/seaweedfs/` (déjà conforme)
- `backend/tests/fixtures/garage.toml` (vestige, hors-scope)
- `docs/research/s01-…`, `docs/plans/s01-…`, `docs/reviews/s01-…` (s01 est figée)
- `docs/decisions/007-minio-from-s01.md` (superseded, intact)
- `docs/decisions/001, 003, 005, 006, 008` (pas concernés)

## Test strategy

### Tests automatisés (existants, à faire passer)

- `backend/tests/services/storage/test_s3_client.py` (renommé) : 6 tests existants (ensure_bucket, put_object, get_object, remove_object, content_type). Aucun nouveau test — le contrat est inchangé.
- `backend/tests/services/rag/test_upload_service.py` : ~10 tests existants (validation, happy path, manual review, rollback, session failure). Test d'isolation cross-tenant de s01 reste valide (le préfixe `students/<pseudo>/` est conservé).
- `backend/tests/cli/test_cli.py` : tests CLI existants (stub `_StubService` mis à jour).
- `backend/tests/core/test_models.py` : tests du modèle `Document` (colonne renommée).

### Vérification de la migration Alembic (manuelle, locale)

- Sur une base jetable (SQLite in-memory ou Postgres local) :

  ```
  alembic upgrade head    # doit créer la table avec s3_key
  alembic downgrade -1    # doit revenir à minio_key
  alembic upgrade head    # doit re-appliquer s3_key
  ```

- Vérifier qu'aucune donnée n'est perdue (la colonne est juste renommée).

### Vérification du runtime (manuelle, locale)

- `docker compose config --services` : doit lister `seaweedfs`, pas `minio`.
- `docker compose up -d seaweedfs postgres redis chroma` doit démarrer sans erreur.
- `curl http://localhost:8333/` (healthcheck SeaweedFS, si exposé) ou `mc alias set local http://localhost:8333 ktutorci ktutorci_secret` (test client).

### Vérification CI (à la PR)

- Le job `build-seaweedfs` doit toujours passer (image SeaweedFS inchangée).
- Le job `backend` doit passer avec le nouvel env block `S3_*`.
- Le job `docs` doit passer (markdownlint sur les fichiers modifiés).

### Pas de test nouveau (scope respecté)

Cette story est une **migration**, pas une refonte. L'API publique du client est inchangée, le comportement est inchangé. Les tests existants lockent le contrat. Ajouter de nouveaux tests serait du scope creep.

## Definition of Done

(Reprend la DoD du repo, spécialisée pour s01b)

- [ ] Toutes les tâches cochées.
- [ ] `pytest --cov=app --cov-fail-under=80` passe (≥ 80% de couverture).
- [ ] `ruff check app tests` passe (0 erreur).
- [ ] Le test d'isolation cross-tenant (`test_upload_service.py::TestHappyPath::test_text_pdf_indexed_and_persisted`) reste vert.
- [ ] Le préfixe `students/<pseudo>/<document_id>` est vérifié dans au moins un test.
- [ ] Aucun service `minio` dans `docker-compose.yml`.
- [ ] Aucune variable `MINIO_*` dans `.env.example`, `config.py`, `ci.yml`.
- [ ] Aucun champ `minio_key` dans `models.py`, `upload_service.py`, `cli.py`, `test_*.py`.
- [ ] ADR 009 existe (✅) et ADR 007 a `Status: superseded by 009` (✅).
- [ ] PR unique, description structurée : résumé, AC cochées, points d'attention (notamment la migration Alembic si elle a été initialisée).
- [ ] `git diff main...feature/s01b-migrate-storage-to-seaweedfs` est lisible (un seul sujet, pas de bruit).
- [ ] Review passée (`docs/reviews/s01b-migrate-storage-to-seaweedfs.md` avec `Ship allowed: yes`).

<< IP Mike: task granularity, what a good plan contains/avoids. >>
