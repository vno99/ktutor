# Research — Story s01b-migrate-storage-to-seaweedfs

## The five structuring facts

1. **Le runtime applicatif référence encore MinIO partout**, mais la **CI a déjà basculé sur SeaweedFS** (job `build-seaweedfs`, service `seaweedfs:8333`, image `ghcr.io/.../seaweedfs-ci:4.44`) — l'écart entre CI et code applicatif est le cœur de la story. (`backend/app/services/storage/minio_client.py:16`, `.github/workflows/ci.yml:22-98`)

2. **La CI utilise encore les noms d'env `MINIO_*`** alors qu'elle parle à SeaweedFS sur le port 8333. Le mapping env-var→service est trompeur : l'endpoint pointe vers SeaweedFS, le préfixe dit `MINIO`. La casse doit être nette. (`.github/workflows/ci.yml:70-73`)

3. **Le SDK `minio` Python (>=7.2) parle S3 nativement** et est compatible avec la passerelle S3 de SeaweedFS sans changement de code applicatif. Seul l'`endpoint` change. (`backend/requirements.txt:24`, `backend/app/services/storage/minio_client.py:12-13`)

4. **La fixture SeaweedFS est déjà en place** (`backend/tests/fixtures/seaweedfs/Dockerfile` + `s3config.json`), avec credentials baked-in (`ktutorci` / `ktutorci_secret`) sur le port 8333. La migration runtime est techniquement un port swap. (`backend/tests/fixtures/seaweedfs/Dockerfile:24`)

5. **Le nommage "minio" est immuable dans le code applicatif** (classe `MinioClient`, fichier `minio_client.py`, colonne `documents.minio_key`, champ `minio_key` dans `UploadResult`). La story garde ces noms pour limiter le diff — un rename complet est reporté. (`backend/app/core/database/models.py:57`, `backend/app/services/storage/minio_client.py:16`)

## Target story

**Story** : s01b-migrate-storage-to-seaweedfs — Migrer le stockage objet de MinIO vers SeaweedFS
**Complexity (declared)** : 2

### Acceptance criteria (recap, 12 ACs)

1. `docker-compose.yml` expose un service `seaweedfs` (image `chrislusf/seaweedfs:4.44`) avec S3 sur port 8333 ; aucun service `minio` n'est présent.
2. `backend/.env.example` expose `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET` ; les variables `MINIO_*` sont supprimées.
3. `backend/app/core/config.py` charge les nouvelles variables `s3_*` ; **pas d'alias rétrocompat** (casse nette).
4. SDK Python reste `minio` (>=7.2) — compatible S3.
5. La fixture `backend/tests/fixtures/seaweedfs/` est référencée par le test runner et la CI.
6. Les tests `backend/tests/services/storage/` passent contre SeaweedFS.
7. Le préfixe `students/<pseudo>/<document_id>` est conservé ; test d'isolation cross-tenant de s01 reste vert.
8. La colonne `documents.minio_key` est renommée en `documents.s3_key` (migration SQLAlchemy/Alembic incluse).
9. `CLAUDE.md` (l.36 + l.521), `docs/prd.md`, `docs/architecture.md`, ADR 002 et ADR 004 sont mis à jour.
10. `docs/decisions/009-seaweedfs-replaces-minio.md` existe (déjà créé ce jour) au format MADR.
11. ADR 007 a son frontmatter mis à jour : `Status: superseded by 009` (déjà fait ce jour).
12. Aucune story en aval (s02+) ne change de comportement observable.

## Current state of the code

### Inventaire des références MinIO (par couche)

| Couche | Fichier | Lignes | Nature |
|---|---|---|---|
| **Runtime** | `docker-compose.yml` | 32-48, 70 | service `minio:9000`, volume `minio_data` |
| **Config** | `backend/.env.example` | 28-32 | `MINIO_*` x4 |
| **Config** | `backend/app/core/config.py` | 40-43 | `minio_endpoint`, `minio_access_key`, `minio_secret_key`, `minio_bucket` |
| **Client** | `backend/app/services/storage/minio_client.py` | 1-99 | classe `MinioClient`, wrapper `minio.Minio` |
| **Schema** | `backend/app/core/database/models.py` | 57 | `minio_key: Mapped[str]` colonne |
| **Service** | `backend/app/services/rag/upload_service.py` | 29, 66, 90, 98, 132, 153, 164, 183, 194, 198, 203, 254, 272 | imports + champ `minio_key` partout |
| **CLI** | `backend/app/cli.py` | 40, 55-61, 73, 92 | instanciation `MinioClient`, sortie JSON `minio_key` |
| **Tests** | `backend/tests/services/storage/test_minio_client.py` | 1-145 | nom de fichier, commentaires, classe `FakeMinio` |
| **Tests** | `backend/tests/services/rag/test_upload_service.py` | 26-27, 72-76, 113, 121, 163, 170, 215, 236, 241, 246, 248, 267, 272, 278 | imports + commentaires `minio_object_removed_on_chromadb_failure` |
| **Tests** | `backend/tests/cli/test_cli.py` | 52, 61 | champ `minio_key=f"students/{pseudo}/stub"` |
| **Tests** | `backend/tests/core/test_models.py` | 35, 56, 64, 85, 102 | champ `minio_key="..."` dans la construction de `Document` |
| **CI** | `.github/workflows/ci.yml` | 22-98, 70-73 | job `build-seaweedfs` + service `seaweedfs:8333` **MAIS** env `MINIO_*` |
| **CI** | `backend/tests/fixtures/seaweedfs/` | Dockerfile + s3config.json | fixture SeaweedFS opérationnelle |
| **CI** | `backend/tests/fixtures/garage.toml` | — | vestige d'un précédent testbench, **inutile à la story** |

### État de la CI (`.github/workflows/ci.yml`)

- **Job `build-seaweedfs`** (l. 22-53) : build & push GHCR de l'image `chrislusf/seaweedfs:4.44` avec credentials baked-in.
- **Job `backend`** (l. 58-203) :
  - service `seaweedfs` sur port 8333 (l. 91-98)
  - env vars pointent vers SeaweedFS mais s'appellent encore `MINIO_*` (l. 70-73) :
    ```yaml
    MINIO_ENDPOINT: localhost:8333
    MINIO_ACCESS_KEY: ktutorci
    MINIO_SECRET_KEY: ktutorci_secret
    MINIO_BUCKET: ktutor-test
    ```
  - check readiness inclut `localhost:8333` (l. 185)

→ **Constat important** : le service est déjà SeaweedFS, l'env aussi fonctionnellement, mais les noms mentent. La story doit aligner le naming (AC2, AC3).

### État du code applicatif

- `MinioClient` (`backend/app/services/storage/minio_client.py:16-99`) :
  - constructeur prend `endpoint, access_key, secret_key, bucket, secure=False`
  - `put_object(pseudo, document_id, filename, data)` → `students/<pseudo>/<document_id>`
  - `get_object(minio_key)` → bytes
  - `remove_object(minio_key)` → idempotent (ignore `NoSuchKey`, `NoSuchObject`)
  - **API publique stable** : ne change pas.
- `Document.minio_key` (`backend/app/core/database/models.py:57`) : `Mapped[str]` `String(512)`, non-nullable.
- `UploadService` (`backend/app/services/rag/upload_service.py`) : orchestre l'upload. Appelle `self._minio.put_object(...)` puis `self._minio.remove_object(...)` sur rollback (AC4 de s01).

### État de la doc

- **MinIO** mentionné dans : `CLAUDE.md` (l.36, l.521), `docs/prd.md`, `docs/architecture.md` (l.23, l.153, l.275), `docs/stories.md` (s01, lignes diverses), ADR 002, 004, 007 (superseded), `docs/research/s01-…`, `docs/plans/s01-…`, `docs/reviews/s01-…`, `docs/reviews/stories.md`.
- **ADR 009** créé ce jour (supersede de 007). Frontmatter ADR 007 mis à jour (`Status: superseded by 009`).
- **Story s01b** insérée dans `docs/stories.md` (Phase 1, après s01).

## Anchor points

Où la migration s'ancre :

### Code

| Fichier | Ce qui change | Justification |
|---|---|---|
| `docker-compose.yml` | `minio` → `seaweedfs` (image `chrislusf/seaweedfs:4.44`, port 8333, volume `seaweedfs_data`) | AC1 |
| `backend/.env.example` | `MINIO_*` → `S3_*` (4 lignes) | AC2 |
| `backend/app/core/config.py` | `minio_*` → `s3_*` (4 champs) ; **pas d'alias** | AC3 |
| `backend/app/core/database/models.py` | `minio_key` → `s3_key` colonne | AC8 |
| `backend/app/services/rag/upload_service.py` | champ `minio_key` → `s3_key` dans `UploadResult`, `_persist_document`, etc. | cohérence AC8 |
| `backend/app/cli.py` | lecture des `settings.s3_*` ; champ de sortie JSON `s3_key` | cohérence AC8 |
| `backend/tests/services/storage/test_minio_client.py` | nom de fichier → `test_s3_client.py` ; commentaires ; nom de classe `FakeMinio` → `FakeS3` (cohérence) | cohérence |
| `backend/tests/services/rag/test_upload_service.py` | import + commentaires | cohérence |
| `backend/tests/cli/test_cli.py` | champ `minio_key` → `s3_key` dans `_StubService` | cohérence |
| `backend/tests/core/test_models.py` | champ `minio_key` → `s3_key` | cohérence |
| `.github/workflows/ci.yml` | env vars `MINIO_*` → `S3_*` (l. 70-73) | AC2 cohérence runtime |

### Doc

| Fichier | Ce qui change |
|---|---|
| `CLAUDE.md` | l.36 (`MinIO / S3` → `S3 (SeaweedFS)`), l.521 (`MinIO` → `SeaweedFS`) |
| `docs/prd.md` | toutes références à MinIO |
| `docs/architecture.md` | l.23, l.153, l.275 (et autres mentions) |
| `docs/decisions/002-poc-rewrite-from-scratch.md` | références MinIO |
| `docs/decisions/004-rag-isolation-by-collection.md` | références MinIO |

**Note** : `docs/research/s01-uploader-document.md`, `docs/plans/s01-uploader-document.md`, `docs/reviews/s01-uploader-document.md` **ne sont pas modifiés** par cette story — ils décrivent l'état livré de s01, qui est figé.

### Pas à modifier

- `backend/app/services/storage/minio_client.py` : **commentaires uniquement** (le nom de fichier et de classe restent). Le SDK `minio` Python reste utilisé.
- `backend/tests/fixtures/garage.toml` : **vestige**. Hors-scope. À supprimer dans un passage futur.
- `backend/tests/fixtures/seaweedfs/` : **déjà conforme**, utilisé tel quel.
- `requirements.txt` : `minio>=7.2` reste, il parle S3.

## Verified APIs / functions

Vérifié par lecture du code (pas mémoire) :

| Élément | Localisation | Signature / état |
|---|---|---|
| `MinioClient.__init__` | `backend/app/services/storage/minio_client.py:19-33` | `(endpoint, access_key, secret_key, bucket, secure=False)`. **Stable**. |
| `MinioClient.ensure_bucket` | id. 35-38 | idempotent. **Stable**. |
| `MinioClient.put_object` | id. 40-60 | `(pseudo, document_id, filename, data) -> str` (key). **Stable**. |
| `MinioClient.get_object` | id. 62-71 | `(minio_key) -> bytes`. **Stable**. |
| `MinioClient.remove_object` | id. 73-80 | `(minio_key) -> None`, idempotent. **Stable**. |
| `Document.minio_key` | `backend/app/core/database/models.py:57` | `Mapped[str] String(512) NOT NULL`. **À renommer**. |
| `UploadResult.minio_key` | `backend/app/services/rag/upload_service.py:66` | champ dataclass. **À renommer**. |
| `UploadService._minio` | id. 98 | champ privé. **À renommer** en `_s3` (cohérence). |
| `UploadService._persist_document(..., minio_key: str, ...)` | id. 254 | paramètre. **À renommer**. |
| `app.cli._build_service` | `backend/app/cli.py:53-80` | lit `settings.minio_*`. **À migrer vers `settings.s3_*`**. |
| Fixture `seaweedfs/Dockerfile` | `backend/tests/fixtures/seaweedfs/Dockerfile:24` | `CMD ["server", "-dir=/data", "-s3", "-s3.port=8333", ...]` — **vérifié**. |
| Fixture `s3config.json` | `backend/tests/fixtures/seaweedfs/s3config.json` | identité `ktutorci` / `ktutorci_secret`, actions `Read, Write, List, Tagging, Admin`. **Vérifié**. |
| Job CI `build-seaweedfs` | `.github/workflows/ci.yml:22-53` | image tag `ghcr.io/.../ktutor/seaweedfs-ci:4.44`. **Vérifié**. |
| Service CI `seaweedfs` | id. 91-98 | port `8333:8333`, image GHCR. **Vérifié**. |
| Env CI `MINIO_*` | id. 70-73 | `MINIO_ENDPOINT: localhost:8333` (pointe vers SeaweedFS malgré le nom). **Vérifié**. |

## Traps & constraints

### Pièges techniques

1. **Le nom de service CI diffère du nom de variable env** : `services.seaweedfs` mais env `MINIO_ENDPOINT`. Si on ne renomme que les variables, on introduit un moment où le code ne trouve plus l'env. La migration doit être **atomique** dans la PR.

2. **Le test `test_models.py` charge `Document` via SQLite in-memory** : renommer `minio_key` → `s3_key` côté modèle cassera les tests qui passent `minio_key=` en kwarg. À mettre à jour en cohérence (AC8).

3. **Le test `test_cli.py` expose le champ `minio_key` dans le JSON de sortie** : `result.minio_key` est sérialisé. Si on renomme le champ de `UploadResult`, le test stub doit suivre.

4. **`UploadResult` est un dataclass** : renommer le champ `minio_key` → `s3_key` est une breaking change pour les callers. Les callers internes (CLI, `_persist_document`) sont dans le scope. Pas de caller externe en s01 (story seule).

5. **Le nom de fichier `minio_client.py` est conservé** par décision explicite (story AC : "le code applicatif garde son nom pour limiter le diff"). Le fichier n'est PAS renommé. Seuls les commentaires internes sont mis à jour.

6. **`minio_data` (volume nommé)** : pas de données à migrer (POC). Le volume peut rester orphelin. Pas d'action requise.

7. **`backend/tests/fixtures/garage.toml`** : vestige d'un précédent testbench (commentaire interne parle de "Region set to us-east-1 so the minio>=7.2 Python client"). **Hors-scope de cette story**, mais à supprimer dans un passage futur.

### Dépendances entre modules

- `app.cli` → `app.services.storage.minio_client` (import)
- `app.services.rag.upload_service` → `app.services.storage.minio_client` (import + type hint)
- `app.services.rag.upload_service` → `app.core.database.models` (utilise `Document.minio_key`)
- `app.cli` → `app.core.config` (lit `settings.minio_*`)
- `backend/tests/services/rag/test_upload_service` → `app.services.storage.minio_client` + `tests.services.storage.test_minio_client.FakeMinio`

→ Le rename est **transverse** mais **mécanique** : grep-and-replace, pas de refonte.

### Tests existants à valider

- `backend/tests/services/storage/test_minio_client.py` (renommer en `test_s3_client.py`)
- `backend/tests/services/rag/test_upload_service.py` (mise à jour imports + commentaires)
- `backend/tests/cli/test_cli.py` (mise à jour champ `minio_key`)
- `backend/tests/core/test_models.py` (mise à jour champ `minio_key`)
- **Test d'isolation cross-tenant** : `test_upload_service.py:171` vérifie que `pseudo_a` ne peut pas écrire dans la collection de `pseudo_b`. **Le préfixe `students/<pseudo>/` est conservé**, donc le test reste valide. **Vérifié par lecture du code** : la clé est construite par `_build_key(pseudo, document_id) = f"students/{pseudo}/{document_id}"` (l. 83-84) et le rollback vérifie `k.startswith(f"students/{pseudo}/")` (l. 171, 242, 268, 284).

### Couverture AC de s01b

| AC | État actuel | Action |
|---|---|---|
| AC1 service `seaweedfs` | ❌ `docker-compose.yml` référence `minio/minio:latest` | Modifier le fichier |
| AC2 env `S3_*` | ❌ `backend/.env.example` a `MINIO_*` | Modifier le fichier |
| AC3 config `s3_*` | ❌ `config.py` a `minio_*` | Modifier le fichier |
| AC4 SDK `minio` conservé | ✅ `requirements.txt` ligne 24 | Aucune action |
| AC5 fixture référencée | ✅ `backend/tests/fixtures/seaweedfs/` existe et CI l'utilise | Aucune action |
| AC6 tests `services/storage` passent | ⚠️ Tests existants utilisent `MinioClient` ; devront passer contre SeaweedFS | Run pytest après renommage |
| AC7 préfixe multi-tenant conservé | ✅ Code inchangé | Aucune action, vérification dans test run |
| AC8 colonne `s3_key` | ❌ `minio_key` partout | Renommer dans `models.py` + callers |
| AC9 doc à jour | ⚠️ `CLAUDE.md`, `prd.md`, `architecture.md`, ADR 002, 004 mentionnent MinIO | Modifier |
| AC10 ADR 009 existe | ✅ Créé ce jour | Aucune action |
| AC11 ADR 007 supersédé | ✅ Fait ce jour | Aucune action |
| AC12 aucun impact aval | ✅ s02+ pas encore développées | Vérifier à l'exécution |

## Open questions

1. **Alembic ou `Base.metadata.create_all` ?** : `models.py` n'a pas de version Alembic visible (juste `Base` de SQLAlchemy 2.0). Pour le POC, un simple `rename_column` via Alembic est surdimensionné. **Décision à prendre au planning** : Alembic (plus rigoureux) vs `ALTER TABLE` manuel documenté dans le PR description vs `Base.metadata.create_all` qui re-crée la table (perte de données, inacceptable en prod, acceptable en POC car pas de données à migrer).
   - **Recommandation** : utiliser Alembic car c'est la convention du projet (`docs/architecture.md` mentionne `alembic/` dans la structure cible). Si Alembic n'est pas encore initialisé, l'initialiser dans cette story est cohérent avec "Phase 3 Rôles et Sécurité" qui arrive plus tard.

2. **Le volume `minio_data` doit-il être supprimé de docker-compose ?** : la migration supprime le service `minio` mais le volume nommé reste orphelin. **Décision** : le renommer en `seaweedfs_data` est OK (équivalent, plus de données à migrer). Le supprimer complètement force les utilisateurs à re-tirer l'image.

3. **Le test `garage.toml` est-il supprimé dans cette PR ?** : c'est un vestige. **Décision recommandée** : hors-scope. Une story de cleanup séparée serait plus propre.

4. **Le nom de fichier `test_minio_client.py` doit-il être renommé en `test_s3_client.py` ?** : la story dit "commentaires uniquement" pour `minio_client.py`, mais ne parle pas du fichier de test. **Décision recommandée** : renommer aussi, pour cohérence (le fichier de test teste le même client). Mais c'est un cas limite. À trancher au planning.

5. **Le champ `_minio` interne de `UploadService` doit-il être renommé en `_s3` ?** : la story dit "champ `minio_key` → `s3_key`" mais pas le champ privé `_minio`. **Décision recommandée** : oui, par cohérence, le préfixe `_s3` est plus juste. Mais c'est cosmétique.

## Real complexity

**Déclaré** : 2 (changement de runtime, pas de logique métier).
**Après lecture du code** : **2** — confirmé.

**Justification** :
- L'API publique du client est **inchangée** (signatures, comportements, exceptions). Le SDK `minio` Python continue de fonctionner contre SeaweedFS.
- Le test d'isolation cross-tenant repose sur le préfixe de clé, pas sur l'implémentation du client.
- Le travail est **mécanique** : renommer `minio_key` → `s3_key` (modèle + dataclass + callers), renommer `minio_*` → `s3_*` (config + env), remplacer le service dans docker-compose.yml, mettre à jour la doc.
- La CI est **déjà à moitié migrée** (service SeaweedFS existe, env pointe vers SeaweedFS). La story aligne le naming, c'est tout.

**Pas de verdict 5** : la story ne mérite pas d'être splittée. Une seule PR, un seul diff, un seul merge.

**Différentiel avec la déclaration** : aucun. Le score 2 tient.

## Split proposal

**Non requis** (verdict 2, pas 5).

Si un split devenait utile (par exemple si on découvrait que la migration Alembic est plus lourde que prévu), la coupe naturelle serait :
- **s01b-1-data-migration** : renommage colonne + Alembic + tests modèles
- **s01b-2-runtime** : docker-compose + config + env + CI env vars
- **s01b-3-doc** : CLAUDE.md + prd.md + architecture.md + ADR 002/004

Mais aucune raison de splitter a priori. **Recommandation** : rester sur une seule story.

<< IP Mike: exploration method, what a good research always verifies. >>
