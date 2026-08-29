# ADR 009 — Remplacer MinIO par SeaweedFS (S3-compatible) pour le stockage objet

- Status: accepted
- Date: 2026-08-29
- Supersedes: ADR 007

## Context

ADR 007 acte l'usage de MinIO pour le stockage objet dès s01, sous le préfixe
`students/<pseudo>/<document_id>`. En pratique, le testbench CI a montré
deux points de friction avec MinIO :

1. Problèmes de permissions au montage du volume (`EACCES`) qui cassent
   l'étape `actions/checkout` au run suivant.
2. Empreinte Docker plus lourde que nécessaire pour un POC local.

SeaweedFS expose une API S3 complète via son binaire `server -s3`. Le SDK
`minio` Python est compatible S3 et fonctionne tel quel contre SeaweedFS :
on change uniquement l'endpoint et le port. La fixture
`backend/tests/fixtures/seaweedfs/Dockerfile` valide déjà ce montage.

Le préfixe multi-tenant `students/<pseudo>/<document_id>` reste
identique. Aucune story en aval ne change de comportement observable.

## Decision

Remplacer le service MinIO (`minio/minio:latest`) par un service SeaweedFS
(`chrislusf/seaweedfs:4.44`) avec la passerelle S3 activée sur le port 8333.
Le SDK Python `minio` est conservé tel quel (il parle S3, pas MinIO).

- Endpoint par défaut : `localhost:8333`
- Bucket inchangé : `assistant-documents`
- Préfixe de clé inchangé : `students/<pseudo>/<document_id>`
- Variables d'environnement renommées : `MINIO_*` → `S3_*` (endpoint,
  access_key, secret_key, bucket). Pas d'alias de rétrocompatibilité :
  la migration est une casse nette (cf. story s01b).
- Le nom du service docker-compose passe de `minio` à `seaweedfs`.
- Le volume nommé associé passe de `minio_data` à `seaweedfs_data`.
- Le code applicatif (`MinioClient`, `documents.minio_key` colonne) garde
  son nom pour limiter le diff ; un rename complet est reporté à un
  passage futur pour ne pas grossir la PR de migration.

## Considered options

- **Option A — Conserver MinIO** : rejeté, le testbench est déjà cassé
  par les problèmes de volume. Garder MinIO impliquerait un contournement
  CI séparé et ne règle pas l'empreinte Docker.
- **Option B — Bascule sur Garage (S3)** : le fichier `garage.toml` est
  déjà présent dans les fixtures, mais Garage a un modèle de
  configuration (cluster, credentials, layout) plus lourd pour un POC
  mono-utilisateur. Rejeté.
- **Option C — Filesystem local (cf. option 2 d'ADR 007)** : rejeté,
  l'ADR 007 a déjà documenté la dette de migration.
- **Option D — SeaweedFS (retenu)** : S3 natif, binaire unique, image
  multi-arch, configuration credentials minimale. Compatible avec le SDK
  `minio` Python. Fixture de tests déjà disponible.

## Consequences

- **Doc à mettre à jour** : `CLAUDE.md` (l.36 + l.521), `docs/prd.md`,
  `docs/architecture.md`, ADR 002 et ADR 004 (qui mentionnent MinIO).
  Les artifacts s01 (research/plan/review) ne sont pas modifiés par
  cette migration — l'API publique du client est inchangée.
- **Code à modifier** : `docker-compose.yml`, `backend/.env.example`,
  `backend/app/core/config.py`, `backend/app/core/database/models.py`
  (renommer `minio_key` → `s3_key`), `backend/app/services/storage/`
  (commentaires et libellés uniquement), `backend/tests/services/storage/`
  (commentaires uniquement). Le testbench SeaweedFS existant devient le
  testbench de référence.
- **Tests d'isolation cross-tenant** : inchangés — le préfixe
  `students/<pseudo>/` est conservé.
- **ADR 007** : marqué `superseded by 009`.
- **Migration de données** : aucune, le POC n'a pas de volume MinIO
  persistant à migrer. Le volume nommé `minio_data` peut rester
  orphelin ou être supprimé manuellement.
- **Casse nette sur les variables d'environnement** : pas d'alias
  `minio_*` acceptés temporairement. Tout `.env` existant doit être
  régénéré. C'est un coût assumé pour éviter de la dette de
  rétrocompatibilité.
