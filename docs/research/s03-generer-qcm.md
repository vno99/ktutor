---
name: research-s03-qcm
description: s03-generer-qcm — research output for /ks-plan
metadata:
  type: project
  story: s03-generer-qcm
---

# Research — Story s03-generer-qcm

## The five structuring facts

1. **Aucun module QCM n'existe.** Pas de `services/exercises/qcm_generator.py`, pas de modèle `Exercise` dans `models.py`, pas de sous-dossier `services/exercises/`. L'architecture cible (`docs/architecture.md:187-197`) prévoit un modèle `exercises` mais avec `statement TEXT` / `expected_answer TEXT` / `grading_criteria JSONB` — **différent du format QCM** (un QCM a N questions, pas une seule). La story AC5 demande `questions JSON` (un champ JSON avec la liste des questions). Le choix entre (a) étendre le modèle `exercises` avec un champ `questions JSONB` ou (b) créer un modèle `qcm_exercises` séparé est ouvert.
2. **Le client LLM de s02 est réutilisable tel quel** (`app/services/llm/client.py`). L'interface `LlmClient.invoke(messages: list[BaseMessage]) -> AIMessage` est exactement ce dont le générateur a besoin. La factory `build_llm_client(settings)` route `minimax`/`openai` (ollama reste `NotImplementedError`). Pour le QCM, on n'a PAS besoin de retriever multi-tenant : le générateur opère sur UN document précis (filtré par `document_id`), pas sur la collection entière de l'élève.
3. **ChromaDB permet de filtrer par metadata `document_id`** — vérifié : `collection.get(where={'document_id': 'd1'}, include=['documents'])` retourne uniquement les chunks du document ciblé. Le retriever existant (`services/rag/retriever.py`) ne supporte PAS ce filtre (il fait une query sémantique par question). s03 a besoin d'un **mécanisme distinct de retrieval par document_id**, soit (a) une nouvelle méthode `Retriever.get_chunks_by_document_id(...)`, soit (b) une query directe à `ChromaStore` depuis le générateur.
4. **Pydantic 2.13.4 fait la coercion automatique `str → int`** pour `correct_index: "1"` (testé ci-dessus). Le piège "LLM may output `correct_index: '2'` (string)" mentionné dans la story est donc neutralisé par Pydantic — mais le test doit verrouiller le comportement.
5. **Le pattern de persistence de s01 est réutilisable** : `UploadService._persist_document` injecte un `session_factory`, ajoute un `Document` via `session.add(...)` et `session.commit()`. Le générateur QCM a besoin du même pattern : un `session_factory` injecté, un modèle `Exercise` ajouté, `commit()`. Le `Exercise` doit porter `student_pseudo` pour le multi-tenancy (filtrage côté query) — l'AC5 demande "pseudo" dans les metadata.

## Target story

**Story** : s03-generer-qcm — Générer un QCM à partir de mon cours.
**Complexity** : 3 (LLM generation + structured output parsing + persistence + CLI ergonomics).

### Acceptance criteria (6 ACs)

1. CLI : `python -m ktutor.cli generate-qcm --pseudo <p> --document-id <id> --n 5` retourne un JSON avec 5 questions, chacune avec `question`, `options` (4 items), `correct_index` (0-3).
2. Sortie JSON valide, parsable sans nettoyage manuel.
3. QCM généré UNIQUEMENT à partir du document spécifié (chunks filtrés par `document_id`).
4. LLM est prompté pour produire exactement la structure demandée ; si output malformé, retry une fois avec prompt plus strict, puis échec clair.
5. QCM persisté (PostgreSQL) avec metadata : `pseudo`, `document_id`, `generation_date`, `questions` JSON.
6. Test vérifie que la structure JSON matche le schéma (4 options, 1 correct_index par question).

## Current state of the code

### Fichiers concernés (vérifiés)

- `backend/app/services/llm/client.py` : `LlmClient` Protocol, `_LangChainChatWrapper`, `build_llm_client(settings)`. Réutilisable tel quel.
- `backend/app/services/rag/chroma_store.py` : `ChromaStore.get_collection(subject, pseudo)`, `add_chunks(...)`. `list_collections_for_pseudo` existe mais n'est pas sur le hot path. Aucun filtre `document_id` exposé.
- `backend/app/services/rag/retriever.py` : `Retriever.query(subject, pseudo, question, k)` — query sémantique. Ne fait pas de filtre `document_id`. s03 a besoin d'un chemin distinct.
- `backend/app/services/rag/upload_service.py` : pattern de `_persist_document` avec `session_factory` injectable. Référence pour le pattern de persistence.
- `backend/app/core/database/models.py` : `Base`, `DocumentStatus`, `Subject`, `Document`. **Aucun modèle `Exercise`**.
- `backend/app/core/database/session.py` : `init_db()` (`Base.metadata.create_all`).
- `backend/app/cli.py` : `upload` + `chat` (ajouté en s02). Pattern typer réutilisable pour `generate-qcm`.
- `backend/app/core/config.py` : pas de variable `QCM_*`. À ajouter.
- `backend/.env.example` : pas de variable `QCM_*`. À ajouter.
- `backend/alembic/` : initialisé en s01b. La migration pour ajouter la table `exercises` est un follow-up (les FK vers `users.pseudo` arrivent en s15). Pour s03, `init_db()` (qui fait `Base.metadata.create_all`) suffit en dev/CI tant que la migration n'est pas dans le pipeline.
- `docs/architecture.md:187-197` : schéma cible pour `exercises` (statement/expected_answer/grading_criteria). **Divergence** avec la story s03 qui demande `questions` JSON. À trancher au planning.

### Modules absents (à créer)

- `backend/app/services/exercises/__init__.py` (vide).
- `backend/app/services/exercises/qcm_generator.py` : le générateur.
- `backend/app/cli.py` : commande `generate-qcm` ajoutée.
- `backend/app/core/database/models.py` : modèle `Exercise` ajouté.
- `backend/app/core/config.py` : variables `QCM_*` ajoutées.
- `backend/.env.example` : variables `QCM_*` ajoutées.
- `backend/tests/services/exercises/qcm_generator.py` (test).
- `backend/tests/cli/test_cli.py` : extension pour `generate-qcm`.
- `backend/tests/core/test_config.py` : extension pour les settings QCM.

### Conventions du projet (déduites du code, pas inventées)

| Convention | Source vérifiée | Forme attendue pour s03 |
|---|---|---|
| Un sous-dossier par service | `services/{rag,storage,llm,agents}/` | `services/exercises/` |
| Injection par constructeur | `UploadService(s3_client=..., chroma_store=..., embeddings=...)` | `QcmGenerator(llm=..., chroma_store=..., session_factory=..., max_questions=N)` |
| `_XxxLike` Protocol pour les dépendances | `_SessionLike`, `_EmbeddingsLike`, `_OcrLike` | `_LlmLike` (réutilise `LlmClient` de s02) |
| Pydantic pour les schémas de données | `Chunk`, `Document`, `RetrievedChunk` | `QcmQuestion`, `QcmExercise`, `QcmOption` |
| `from __future__ import annotations` | Première ligne de chaque module | Idem |
| snake_case fichiers, PascalCase classes | `chroma_store.py`, `ChromaStore` | `qcm_generator.py`, `QcmGenerator` |
| Erreurs typées | `UploadError`, `UploadErrorKind` | `QcmGenerationError`, `QcmErrorKind` (ou réutiliser `UploadErrorKind.STORAGE_FAILURE` / `INVALID_FILE`) |
| Tests par AC, classes `TestX`, fixtures locales | `test_chroma_store.py`, `test_upload_service.py` | Idem : `test_qcm_generator.py` |
| `EphemeralClient` pour ChromaDB dans les tests | `test_chroma_store.py:30-31` | Idem |
| `FakeListChatModel` pour le LLM | `test_maths_agent.py` (s02) | Idem : réponses contrôlées, asserts sur le prompt envoyé |
| `from app.services.storage.minio_client import MinioClient` reste (run interdict) | s01b | Idem : pas de rename |
| CLI : typer.Typer, `_StubService` pour tests | `test_cli.py:33-74` | Pattern `_StubQcmGenerator` |
| Pas de streaming | run interdict s02 | Idem : CLI one-shot, exit 0 |
| Pas de modèle `Conversation`/`Message` | run interdict s02 | Idem : pas d'historique de QCM en s03 |

## Anchor points

- **Nouveau module** : `backend/app/services/exercises/qcm_generator.py` — `QcmGenerator` class.
- **Nouveau modèle** : `Exercise` dans `backend/app/core/database/models.py`.
- **Extension ChromaStore** (optionnelle, à trancher au planning) : méthode `get_chunks_by_document_id(subject, pseudo, document_id)` qui filtre par metadata. Alternative : `ChromaStore` expose déjà `get_collection(...)` ; le générateur peut faire `coll.get(where={'document_id': ...}, include=[...])` directement sans nouvelle méthode. Cette dernière option est moins invasive (pas de modification de `ChromaStore`).
- **Extension CLI** : commande `@app.command() def generate_qcm(...)` dans `app/cli.py`.
- **Extension config** : `qcm_max_questions: int = 10` (cap), `qcm_default_questions: int = 5`, `qcm_max_retries: int = 1`, `qcm_temperature: float = 0.0` (cohérent avec `chat_temperature`).
- **Extension `.env.example`** : 4 nouvelles variables.

## Verified APIs / functions

- `chroma.Collection.get(where={'document_id': 'd1'}, include=['documents', 'metadatas'])` — confirmé. Retourne les chunks dont la metadata a `document_id == 'd1'`.
- `langchain_core.messages.SystemMessage`, `HumanMessage`, `AIMessage` — confirmés (déjà utilisés en s02).
- `langchain_core.language_models.fake_chat_models.FakeListChatModel(responses: list[str])` — confirmé (s02 l'utilise).
- `LlmClient.invoke(messages) -> AIMessage` (de s02) — confirmé.
- `ChromaStore.get_collection(subject, pseudo)` — confirmé.
- `pydantic` v2.13.4 — confirmé : coercion `str -> int` automatique, `model_validate(raw)` parse les structures imbriquées, `ValidationError` levée si la structure est invalide.
- `sqlalchemy.dialects.postgresql.JSONB` — non vérifié (pas encore utilisé dans le code). À confirmer au planning.
- `sqlalchemy.JSON` (générique, pas dialect-spécifique) — non vérifié. Alternative portable : utiliser `JSON` (SQLite-compat) plutôt que `JSONB` (Postgres-only). Voir la baseline de `requirements.txt` qui supporte SQLite (les tests utilisent SQLite in-memory).

## Traps & constraints

- **Modèle `Exercise` vs architecture cible** : l'architecture cible a `statement TEXT`, `expected_answer TEXT`, `grading_criteria JSONB`. La story s03 demande un QCM avec `questions JSONB`. Solutions :
  1. **Étendre le modèle `exercises`** : ajouter `questions JSONB` (nullable) à côté de `statement`/`expected_answer`/`grading_criteria`. Cohérent avec l'architecture cible, et s06/s06b pourront réutiliser le modèle en laissant `questions` null.
  2. **Modèle séparé `qcm_exercises`** : ne touche pas à l'architecture cible. Plus pur pour le QCM, mais créé un modèle que les stories futures devront JOIN.
  - **Recommandation** : option 1. Justification : `exercises` est prévu pour porter tous les types d'exercices (QCM, problème, rédaction, flashcards). Le `type` (déjà dans l'architecture cible ligne 192) est le discriminant. `questions` JSONB est nullable : null pour les non-QCM.
- **Cohérence nommage** : l'AC5 dit "generation_date", l'architecture cible dit "generated_at". Le projet a déjà `Document.created_at`. Cohérence : utiliser `created_at` (pas `generation_date`, pas `generated_at`). Mettre à jour la story s03 dans `docs/stories.md` est hors scope (figé) ; juste utiliser `created_at` dans le code.
- **`document_id` UUID vs string** : `Document.id` est `uuid.UUID`. Le `metadata.document_id` est stocké comme `str(document_id)` (cf. `chroma_store.add_chunks` → `metadatas=[{"document_id": str(document_id)}]`). L'API de s03 attend `str` (CLI `--document-id`).
- **Validation UUID** : le CLI prend `--document-id` en string. Le générateur doit soit (a) accepter n'importe quel string et échouer si le document n'existe pas, soit (b) valider le format UUID. Le pattern s01 a déjà `Document` accessible via session ; on peut faire `session.get(Document, uuid.UUID(document_id))` pour valider. Coût : 1 query par génération (acceptable).
- **Cross-tenant : `pseudo_a` ne génère pas un QCM sur un document de `pseudo_b`** : la query ChromaDB doit être filtrée par (subject, pseudo, document_id) — pas seulement par document_id. Sinon, un attaquant pourrait deviner un UUID et générer un QCM sur le document d'un autre. **Le générateur DOIT passer `pseudo` à la query ChromaDB**.
- **Validation LLM** : le LLM peut sortir du JSON malformé (texte autour, JSON dans un bloc markdown, etc.). Le `qcm_generator` doit (a) extraire le JSON de la réponse (regex ou parsing tolérant), (b) valider avec Pydantic, (c) si invalide, retry une fois avec prompt strict, (d) si retry échoue, lever une `QcmGenerationError` claire. Le test doit couvrir les 4 cas.
- **Pydantic `Field(ge=0, le=3)`** : pour `correct_index`. Pydantic 2 le supporte nativement. Rejette automatiquement les valeurs hors borne.
- **Retry sur le mauvais provider** : si `LLM_PROVIDER=minimax` et OpenRouter est down, le retry va aussi échouer. C'est un échec permanent, pas transient. Le `qcm_generator` doit distinguer les deux et lever une erreur claire (pas boucler à l'infini).
- **Stub LLM pour les tests** : `FakeListChatModel(responses=[<bad>, <good>])` permet de tester le retry : première réponse malformée, deuxième correcte. Le test assert que le résultat final est la deuxième réponse parsée.
- **Persist après validation** : le générateur ne persiste QUE si la validation Pydantic passe. Sinon, aucun `Exercise` n'est créé (pas de half-persisted state).
- **Alembic** : s01b a initialisé Alembic. Pour s03, soit (a) on ajoute une migration Alembic `add_exercises_table` (propre mais hors scope si la story ne le demande pas), soit (b) on s'appuie sur `init_db()` (qui fait `Base.metadata.create_all`) en dev/test. Le pattern s01 utilise `init_db()` dans le CLI, pas Alembic. Cohérent : utiliser `init_db()` pour s03, et noter dans le PR que la migration Alembic sera ajoutée quand la table `users` arrivera (s12-s15).
- **JSONB vs JSON (SQLite compat)** : les tests unitaires tournent sur SQLite (cf. `conftest.py` et les tests d'upload). SQLite ne supporte pas JSONB nativement. Options :
  1. Utiliser `sqlalchemy.JSON` (générique, marche sur SQLite et Postgres).
  2. Utiliser `JSONB` et mocker/convertir en tests.
  - **Recommandation** : option 1. Pydantic dump le JSON, SQLite le stocke en TEXT, Postgres le stocke en JSON. Plus portable.
- **`type` du modèle `Exercise`** : l'architecture cible l.192 inclut `type` comme discriminator ("qcm" | "probleme" | "redaction" | "flashcards"). Le code s03 doit utiliser `type="qcm"` (string literal ou enum). Pour s03, juste un string suffit (les autres types ne sont pas encore en base). À trancher au planning : enum Python (comme `DocumentStatus`, `Subject`) ou string libre.

## Open questions

1. **Modèle `Exercise`** : étend-on `exercises` (architecture cible) avec un champ `questions` JSONB nullable, ou crée-t-on un modèle séparé `qcm_exercises` ? Proposition : étendre `exercises`, type discriminator `qcm`.
2. **Stockage JSON** : `sqlalchemy.JSON` (portable) ou `JSONB` (Postgres-only) ? Proposition : `JSON` pour la portabilité.
3. **Retrieval des chunks par document_id** : (a) nouvelle méthode `ChromaStore.get_chunks_by_document_id`, (b) appel direct à `coll.get(where=...)` depuis le générateur, (c) nouvelle méthode `Retriever.get_chunks_for_document(subject, pseudo, document_id, k)`. Proposition : (b) pour ne pas étendre `ChromaStore` (run interdict implicite), et (c) si on veut un test propre. Le pattern injection-double dans `Retriever` est déjà là.
4. **Validation UUID en entrée** : le CLI prend `--document-id` en string. Faut-il rejeter les non-UUIDs avant la query ? Proposition : oui, lever une `UploadErrorKind.INVALID_FILE` (réutilisation de la nomenclature s01) ou créer un nouveau code.
5. **Nommage du champ date** : `generation_date` (AC5), `generated_at` (architecture cible), ou `created_at` (cohérent avec `Document.created_at`) ? Proposition : `created_at` pour cohérence avec s01. AC5 noté comme non-contraignant (le mot "date" est générique).
6. **Retry sur mauvais output** : le `qcm_generator` doit-il retry TOUJOURS, ou seulement si la réponse est "presque" du JSON (e.g. balises markdown autour) ? Proposition : regex de pré-extraction (`{...}` block), puis Pydantic strict. Si regex échoue ou Pydantic échoue → retry une fois avec prompt strict "JSON only, no markdown".
7. **Le `type` du modèle `Exercise`** : string libre (`"qcm"`, `"probleme"`, etc.) ou enum Python ? Proposition : enum Python `ExerciseType` avec `QCM = "qcm"`, extensible (PROBLEME, REDACTION, FLASHCARDS) pour les stories futures.
8. **N questions par défaut / cap** : l'AC1 fixe `n=5` (l'exemple de commande). Le plan doit définir le cap max (10 ? 20 ?) et le défaut (5 ?). Proposition : défaut 5, cap 20.
9. **Validation de l'existence du document** : avant de query ChromaDB, faire `session.get(Document, uuid.UUID(document_id))` pour vérifier que le document existe ET appartient au pseudo ? Proposition : oui, lève une erreur explicite "Document not found" si pas trouvé, "Document not found for this pseudo" si trouvé pour un autre pseudo. C'est aussi un test cross-tenant.

## Real complexity

**Score donné dans `docs/stories.md` : 3.** Score confirmé après lecture du code : **3**.

Pas de divergence. Les pièces sont en place :

- LLM client réutilisable (s02).
- ChromaDB queryable par `document_id` metadata.
- Pattern de persistence injectable.
- Pydantic pour les schémas.

Le nouveau code :

- 1 modèle SQLAlchemy (`Exercise`).
- 1 sous-dossier `services/exercises/` avec le générateur.
- 1 méthode sur `Retriever` (ou query directe à ChromaDB) pour filtrer par document_id.
- 1 commande CLI.
- Tests : générateur (5-7 tests), CLI (3-4 tests), modèle (1-2 tests), config (2-3 tests).

C'est bien découpé, sans combinatorial surface. Le piège principal est le parsing JSON du LLM (3 cas : valide direct, valide après extraction, invalide même après retry) — mais c'est borné et testable.

Si on devait splitter, le cut naturel serait :

- **s03a** : modèle `Exercise` + retrieval par `document_id` (shippable seul, testable).
- **s03b** : générateur QCM + LLM + CLI (dépend de s03a pour la persistence).

Mais s03a seul n'a pas de valeur visible (pas de "QCM"). Donc on garde s03 en un seul. **Verdict : 3, ne pas splitter.**

## Split proposal

Pas de split (verdict 3).

## Files touched (anticipated)

**Code (5 fichiers nouveaux ou modifiés)** :

- `backend/app/core/database/models.py` (modifié) : modèle `Exercise` ajouté.
- `backend/app/core/config.py` (modifié) : `qcm_default_questions`, `qcm_max_questions`, `qcm_max_retries`, `qcm_temperature`.
- `backend/.env.example` (modifié) : 4 nouvelles variables.
- `backend/app/services/exercises/__init__.py` (nouveau) : vide.
- `backend/app/services/exercises/qcm_generator.py` (nouveau) : `QcmGenerator` class + `QcmQuestion` Pydantic + `QcmGenerationError` exception.
- `backend/app/services/rag/retriever.py` (modifié, ~10 lignes) : ajout de `get_chunks_for_document(subject, pseudo, document_id, k) -> list[RetrievedChunk]`.
- `backend/app/cli.py` (modifié) : commande `generate-qcm` + `_build_qcm_service()`.

**Test (3 nouveaux, 3 étendus)** :

- `backend/tests/services/exercises/qcm_generator.py` (nouveau, 7-10 tests).
- `backend/tests/cli/test_cli.py` (étendu, +4-5 tests).
- `backend/tests/core/test_config.py` (étendu, +3-4 tests).
- `backend/tests/core/test_models.py` (étendu, +1-2 tests pour `Exercise`).
- `backend/tests/services/rag/test_retriever.py` (étendu, +2 tests pour `get_chunks_for_document`).

**Doc** :

- `docs/architecture.md` (modifié, mineure) : confirmer la forme du modèle `Exercise` (questions JSON).
- Pas d'ADR nouveau (les décisions s'inscrivent dans l'architecture cible existante).

**Non touchés** :

- `backend/app/services/llm/client.py` (s02, intact, réutilisé).
- `backend/app/services/agents/maths_agent.py` (s02, intact).
- `backend/app/services/rag/chroma_store.py` (s01, intact — le générateur peut faire `coll.get(where=...)` directement, ou via `Retriever.get_chunks_for_document` qui appelle `get_collection`).
- `backend/app/services/rag/upload_service.py` (s01, intact).
- `backend/app/services/storage/minio_client.py` (s01b, intact).
- `backend/app/services/rag/ocr.py` (s01, intact).
- `backend/app/services/rag/ingestion.py` (s01, intact).
- `backend/app/services/rag/embeddings.py` (s01, intact).
- Modèles existants (`Document`, `DocumentStatus`, `Subject`).
- Migration Alembic (s01b a initialisé Alembic, la migration pour `exercises` est un follow-up à coordonner avec s15).

## Test strategy

### Tests automatisés (un par AC)

| AC | Test | Couche |
|---|---|---|
| AC1 (CLI retourne 5 questions) | `test_cli.py::TestGenerateQcm::test_generate_qcm_returns_n_questions_in_json` | CLI |
| AC2 (JSON valide parsable) | `test_qcm_generator.py::TestParse::test_valid_json_parsed` | Generator |
| AC3 (filtre par document_id) | `test_qcm_generator.py::TestDocumentFilter::test_only_chunks_of_target_document_used` | Generator |
| AC4 (retry sur output malformé) | `test_qcm_generator.py::TestRetry::test_retries_once_on_malformed_output` + `test_fails_after_max_retries` | Generator |
| AC5 (persistence PostgreSQL) | `test_qcm_generator.py::TestPersistence::test_persists_exercise_in_session` + `test_persists_with_metadata_pseudo_document_id_created_at_questions` | Generator |
| AC6 (structure JSON matche schéma) | `test_qcm_generator.py::TestSchema::test_validates_4_options_per_question` + `test_validates_correct_index_in_range` | Generator |

### Bites de régression (à faire en fin d'implémentation)

- Muter `QcmGenerator` pour ne pas filtrer par `document_id` → AC3 rouge.
- Muter `QcmGenerator` pour ne pas retry → AC4 rouge.
- Muter `QcmGenerator` pour persister avant validation → AC5 rouge (ou plutôt : test rouge car la session n'est pas commit si l'assertion post-validation manque).
- Muter le parsing JSON pour ne pas strip les balises markdown → AC4 rouge (test du retry).

### Vérification manuelle

- `python -m ktutor.cli upload tests/fixtures/sample_cours.pdf --pseudo ali --subject maths` (depuis s01).
- `python -m ktutor.cli generate-qcm --pseudo ali --document-id <id> --n 5` → JSON avec 5 questions.
- Vérifier que chaque question a 4 options, 1 `correct_index` ∈ [0,3].
- `python -m ktutor.cli generate-qcm --pseudo bob --document-id <id d'ali>` → erreur "Document not found" (cross-tenant).
- `python -m ktutor.cli generate-qcm --pseudo ali --document-id <uuid-non-existant>` → erreur "Document not found".

### Pas de test d'intégration avec vrai LLM

L'intégration avec un vrai LLM (minimax via OpenRouter, ou openai) est best-effort, marqué `@pytest.mark.integration`, non bloquant pour la PR. Les tests unitaires utilisent `FakeListChatModel` de langchain (déjà disponible, s02 l'a prouvé).

## Definition of Done (candidat)

- Toutes les tâches cochées.
- `pytest -m "not integration"` passe (cible : 140+ tests).
- `ruff check app tests` clean.
- AC1-AC6 tous couverts par des tests.
- Cross-tenant : un test vérifie qu'un pseudo ne peut pas générer un QCM sur le document d'un autre.
- Retry : un test couvre le cas "première réponse malformée, deuxième correcte".
- Persist : un test vérifie que `Exercise` est commit en session avec tous les champs.
- CLI : exit 0 sur succès, exit non-zéro sur document inexistant.
- `qcm_generator` documente les 3 cas de parsing : valid direct, valid après extraction, invalid après retry.
- PR unique, description structurée : résumé, AC cochées, points d'attention (notamment le choix `sqlalchemy.JSON` vs `JSONB` et le nommage `created_at`).
- Review passée (gate `Ship allowed: yes`).

<< IP Mike: what a research always verifies — premise, traps, anchor points, complexity. >>
