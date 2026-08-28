# ADR 007 — Stocker les fichiers source dans MinIO dès s01

- Status: accepted
- Date: 2026-08-28
- Scope: story s01

## Context

Le PRD et `docs/architecture.md` § Multi-tenancy imposent un préfixe MinIO
`students/<pseudo>/<document_id>`. La question tranchée en planification est :
quand commence-t-on à écrire dans MinIO ? Trois options ont été examinées :

1. **Stocker dans MinIO dès s01** (cette décision).
2. **Stocker en filesystem local** (`./uploads/<pseudo>/<document_id>.pdf`) en s01,
   migrer vers MinIO dans une story dédiée plus tard.
3. **Ne pas stocker le fichier source** (uniquement les chunks vectorisés),
   en partant du principe que le PDF source peut être régénéré.

## Decision

Stocker le fichier source dans MinIO dès s01, avec le préfixe
`students/<pseudo>/<document_id>`. Le bucket est `assistant-documents`, créé
idempotemment au démarrage de la CLI.

L'orchestrateur `UploadService` upload d'abord le fichier dans MinIO, puis
effectue l'ingestion et l'indexation. Si une étape ultérieure échoue,
l'objet MinIO est supprimé (rollback) pour respecter AC4 « persists nothing ».

## Considered options

- **Option 1 — MinIO dès s01 (choix retenu)** : aucun coût de migration
  futur. Le code qui écrit l'objet (avec le bon préfixe et le bon content-type)
  est écrit une seule fois. La story s01 a déjà besoin de configurer MinIO
  dans `docker-compose.yml` (services partagés avec s02+) ; autant l'utiliser.

- **Option 2 — filesystem local en s01, MinIO plus tard** : reporte le coût
  d'écriture, mais crée une dette de migration. La migration devrait
  réécrire tous les chemins (`./uploads/...` → `students/...`), re-uploader
  les fichiers existants (impossible si la s01 n'enregistre que le chemin),
  et adapter le test d'isolation cross-tenant. Risque d'incohérence entre
  les environnements dev et prod.

- **Option 3 — ne pas stocker le fichier source** : le PDF ne peut pas être
  régénéré, et l'OCR sur des images ne peut pas être rejoué sans le
  fichier source. Rejeté car cela rendrait la réindexation impossible
  après un changement de modèle d'embedding ou de chunking.

## Consequences

- **Plus simple à long terme** : le code de stockage est écrit une fois pour
  toutes.
- **Dépendance infra** : la CLI a besoin d'un MinIO accessible (docker-compose
  `minio` service) même en local. Les tests unitaires mockent le client.
- **Rollback obligatoire** : un échec d'indexation après upload MinIO doit
  supprimer l'objet. C'est vérifié par les tests de `test_upload_service.py`
  (AC4).
- **Multi-tenant strict** : le `pseudo` du JWT (ou de l'argument CLI en s01)
  est utilisé pour construire la clé. Le test d'isolation cross-tenant
  s'applique aussi à MinIO (le préfixe `<pseudo>` garantit le cloisonnement).
