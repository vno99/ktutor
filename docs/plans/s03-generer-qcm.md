---
validated: yes
---
# Plan — Story s03-generer-qcm

Branch: `feature/s03-generer-qcm`
Research: `docs/research/s03-generer-qcm.md` — read it first; this plan does not repeat it.

## Target story

**Story** : s03-generer-qcm — Générer un QCM à partir de mon cours.
**Complexity** : 3 (LLM generation + structured output parsing + persistence + CLI ergonomics). Confirmé à la recherche (pas de divergence).

### Acceptance criteria (6 ACs, du research)

1. `python -m ktutor.cli generate-qcm --pseudo <p> --document-id <id> --n 5` retourne un JSON avec 5 questions, chacune `question`, `options` (4 items), `correct_index` (0-3).
2. Sortie JSON valide, parsable sans nettoyage manuel.
3. QCM généré UNIQUEMENT à partir du document spécifié (chunks filtrés par `document_id`).
4. LLM prompté pour la structure exacte ; si output malformé, retry une fois avec prompt strict, puis échec clair.
5. QCM persisté (PostgreSQL) avec metadata : `pseudo`, `document_id`, `generation_date`, `questions` JSON.
6. Test : structure JSON matche le schéma (4 options, 1 `correct_index` par question).

## Decisions tranchées au planning

Issues de la recherche § Open questions, tranchées en checkpoint avec l'utilisateur :

- **Q1 (Modèle `Exercise`)** : étendre le modèle `exercises` (architecture cible) avec un champ `questions` JSON nullable. Le `type='qcm'` discrimine QCM vs futurs types. Champs : `id` (UUID PK), `student_pseudo`, `subject`, `type` (enum), `document_id` (UUID FK vers `Document`), `statement`/`expected_answer`/`grading_criteria` (nullable, pour les futurs types), `questions` (JSON, nullable, pour QCM), `created_at`.
- **Q2 (Retrieval)** : extension de `Retriever` avec `get_chunks_for_document(subject, pseudo, document_id, k) -> list[RetrievedChunk]`. Méthode appelle `chroma.get_collection(subject, pseudo)` (multi-tenant) puis `collection.get(where={'document_id': str(document_id)}, include=['documents', 'metadatas'], limit=k)`.
- **Q3 (Parsing LLM)** : pattern pre-extract + Pydantic + retry strict. Première tentative : prompt "soft" (autorise markdown autour), regex extrait le premier bloc `{...}`, Pydantic valide. Si échec : retry avec prompt strict "JSON only, no markdown". Si retry échoue : `QcmGenerationError("malformed_output")`.
- **Q4 (Date + validation)** : champ `created_at` (cohérent avec `Document.created_at`). Validation explicite : le `qcm_generator` valide `uuid.UUID(document_id)`, fait `session.get(Document, uuid)` pour vérifier existence + appartenance au pseudo, lève `QcmGenerationError("document_not_found")` si pas trouvé ou mauvais pseudo (même erreur, pas de leak).
- **Q5 (Cap/défaut)** : `qcm_default_questions: int = 5`, `qcm_max_questions: int = 20` (cap au-delà duquel l'input est rejeté). N configuré à `--n` ou au défaut.
- **Q6 (Stockage JSON)** : `sqlalchemy.JSON` (portable SQLite/Postgres). Pas de `JSONB` (Postgres-only) pour rester compatible avec les tests sur SQLite.

## Tasks (ordered)

### Étape 0 — Outillage (config + modèle + extension Retriever)

1. [x] **Étendre `backend/app/core/config.py`** avec les paramètres QCM :
   - `qcm_default_questions: int = 5` (env `QCM_DEFAULT_QUESTIONS`)
   - `qcm_max_questions: int = 20` (env `QCM_MAX_QUESTIONS`)
   - `qcm_max_retries: int = 1` (env `QCM_MAX_RETRIES`)
   - `qcm_temperature: float = 0.0` (env `QCM_TEMPERATURE`)
   - **Vérification** : test dans `tests/core/test_config.py` (ajouter `TestQcmSettings::test_default_qcm_settings`).
2. [x] **Étendre `backend/.env.example`** : 4 nouvelles variables QCM (commentées pour la plupart, valeurs par défaut cohérentes avec la factory).
3. [x] **Étendre `backend/app/core/database/models.py`** : ajouter
   - `ExerciseType` enum (`QCM = "qcm"`, extensible)
   - Modèle `Exercise` (champs listés dans Q1 ci-dessus). `questions` est `Mapped[dict | None]` (JSON), `statement`/`expected_answer`/`grading_criteria` sont `Mapped[str | None]` (nullable, pour les futurs types). `document_id` est `Mapped[uuid.UUID]` avec FK logique (string, pas de constraint SQL tant que `users` n'existe pas en s15).
   - **Vérification** : test dans `tests/core/test_models.py` (`TestExercise::test_exercise_creation_with_qcm_questions`).
4. [x] **Étendre `backend/app/services/rag/retriever.py`** avec `get_chunks_for_document(subject, pseudo, document_id, k=20)` :
   - Valide le pseudo (`validate_pseudo`).
   - Valide que `document_id` est un UUID (`uuid.UUID(document_id)`).
   - Appelle `self._chroma.get_collection(subject, pseudo)` (multi-tenant invariant).
   - `collection.get(where={"document_id": str(document_id)}, include=["documents", "metadatas"], limit=k)`.
   - Retourne `list[RetrievedChunk]` (vide si pas de match).
   - **Vérification** : 2-3 tests dans `tests/services/rag/test_retriever.py` :
     - `test_get_chunks_for_document_returns_only_target_document` (AC3).
     - `test_get_chunks_for_document_cross_tenant_isolation` (inject 2 pseudos, query par un seul, ne voir que les chunks du sien).
     - `test_get_chunks_for_document_invalid_uuid_raises`.

### Étape 1 — Générateur QCM (Pydantic + LLM + persistence)

5. [x] **Créer `backend/app/services/exercises/__init__.py`** (vide) + `backend/app/services/exercises/qcm_generator.py` avec :
   - `QcmQuestion` Pydantic : `question: str`, `options: list[str]` (validé longueur=4 via `Field(min_length=4, max_length=4)`), `correct_index: int = Field(ge=0, le=3)`.
   - `QcmExercise` Pydantic : `questions: list[QcmQuestion]` (validé `min_length=1`).
   - `QcmGenerationError(Exception)` : exception typée. Constructeur `(kind: str, message: str)`. `kind` ∈ `{"document_not_found", "malformed_output", "no_chunks", "storage_failure"}`.
   - `_SYSTEM_PROMPT` constant : prompt qui interdit les connaissances générales, exige le format JSON strict, interdit de leak la réponse dans la question.
   - `_USER_PROMPT_TEMPLATE` constant : template qui injecte les chunks et le nombre de questions.
   - `_STRICT_USER_PROMPT_TEMPLATE` constant : pour le retry, ajoute "Réponds UNIQUEMENT avec un objet JSON valide, sans markdown ni prose autour."
   - `_extract_json_block(text: str) -> str | None` : helper qui strip les balises markdown ```json ... ``` puis cherche le premier bloc `{...}`. Réutilise le pattern de `services/rag/ocr.py::_try_parse_json`.
   - `QcmGenerator` classe : constructeur `__init__(self, *, llm: LlmClient, retriever: Retriever, session_factory: Callable[[], _SessionLike] | None = None, default_questions: int = 5, max_questions: int = 20, max_retries: int = 1, temperature: float = 0.0)`. Méthode publique :
     - `generate(pseudo: str, subject: str, document_id: str, n: int | None = None) -> QcmGenerationResult` :
       1. Valide `n` (1 ≤ n ≤ `max_questions`).
       2. Valide `uuid.UUID(document_id)`, lève `QcmGenerationError("document_not_found", ...)` si format invalide.
       3. Si `session_factory` non None : récupère le document en session, vérifie `document.student_pseudo == pseudo`, lève `document_not_found` si absent ou mauvais pseudo.
       4. `chunks = self._retriever.get_chunks_for_document(subject, pseudo, document_id, k=20)`. Si vide : `QcmGenerationError("no_chunks", ...)`.
       5. Construit le user prompt avec les chunks (tronqués si nécessaire) et `n`.
       6. Appelle `self._llm.invoke([SystemMessage, HumanMessage])`. Tente Pydantic validation. Si échec : retry avec prompt strict. Si retry échoue : `QcmGenerationError("malformed_output", ...)`.
       7. Si `session_factory` non None : `session.add(Exercise(student_pseudo=pseudo, subject=Subject(subject), type=ExerciseType.QCM, document_id=doc_uuid, questions=qcm.model_dump(), ...))` + `session.commit()`.
       8. Retourne `QcmGenerationResult(exercise_id=..., questions=qcm.questions, raw=qcm.model_dump_json())`.
   - `QcmGenerationResult` Pydantic : `exercise_id: uuid.UUID`, `questions: list[QcmQuestion]`, `raw: str`.
   - **Vérification** : 7-9 tests dans `tests/services/exercises/qcm_generator.py` :
     - `test_generate_returns_n_questions` (AC1, AC2).
     - `test_generate_filters_chunks_by_document_id` (AC3, bite #1).
     - `test_generate_retries_once_on_malformed_output` (AC4 — 1ère réponse malformée, 2ème correcte).
     - `test_generate_fails_after_max_retries` (AC4 — 2 réponses malformées).
     - `test_generate_persists_exercise_in_session` (AC5, bite #2).
     - `test_generate_raises_document_not_found_for_unknown_uuid` (AC5 — validation DB).
     - `test_generate_raises_document_not_found_for_cross_tenant` (cross-tenant — bite #3).
     - `test_generate_raises_no_chunks_when_document_empty` (AC3).
     - `test_qcm_question_schema_validates_4_options_and_correct_index_range` (AC6).

### Étape 2 — Commande CLI

6. [x] **Étendre `backend/app/cli.py`** :
   - `_build_qcm_service() -> QcmGenerator` : instancie `build_llm_client(settings)`, `ChromaStore`, `build_embedding_provider`, `Retriever`, `QcmGenerator`. **Note** : les embeddings sont instanciés car `Retriever` les attend dans son constructeur, mais la méthode `get_chunks_for_document` n'a pas besoin d'embeddings. C'est un coût négligeable.
   - `@app.command() def generate_qcm(pseudo: str = typer.Option(...), document_id: str = typer.Option(...), n: int = typer.Option(None, "--n", help="Nombre de questions (défaut: qcm_default_questions)"), subject: str = typer.Option("maths", "--subject"), quiet: bool = typer.Option(False, "--quiet"), json_output: bool = typer.Option(False, "--json"))` :
     - Appelle `service.generate(pseudo, subject, document_id, n=n)`.
     - Affiche un panel rich en mode normal, JSON en mode `--json`.
     - Exit 0 sur succès, exit 5 sur `QcmGenerationError("document_not_found", ...)`, exit 4 sur `storage_failure`, exit 1 sur autre erreur.
   - **Vérification** : 4-5 tests dans `tests/cli/test_cli.py` (`TestGenerateQcm`):
     - `test_generate_qcm_returns_zero_with_n_questions`.
     - `test_generate_qcm_json_output_is_valid`.
     - `test_generate_qcm_returns_5_for_document_not_found`.
     - `test_generate_qcm_help_works`.

### Étape 3 — Doc

7. [x] **Étendre `docs/architecture.md:187-197`** : remplacer la description du modèle `exercises` (statement/expected_answer/grading_criteria) par la version réelle (avec `questions` JSON, `type` enum, `document_id`). Le `type` discriminator est explicité. Pas d'ADR nouveau : la décision est documentée inline dans l'architecture (cohérent avec les ADR existants).

### Étape 4 — Vérification finale

8. [x] **Run global** : `cd backend && pytest --cov=app --cov-fail-under=80 -m "not integration"` (mêmes options que CI). Cible : 140+ tests passent, couverture ≥ 80%.
9. [x] **Lint** : `cd backend && ruff check app tests`. 0 erreur.
10. [x] **Vérification manuelle** (humain) :
    - `python -m ktutor.cli upload tests/fixtures/sample_cours.pdf --pseudo ali --subject maths` (depuis s01).
    - Noter le `document_id` retourné.
    - `python -m ktutor.cli generate-qcm --pseudo ali --document-id <id> --n 5` → JSON avec 5 questions, 4 options chacune, `correct_index` ∈ [0,3].
    - `python -m ktutor.cli generate-qcm --pseudo bob --document-id <id d'ali>` → "document_not_found", exit 5.
    - `python -m ktutor.cli generate-qcm --pseudo ali --document-id 00000000-0000-0000-0000-000000000000` → "document_not_found", exit 5.

## Run interdicts

- **Ne PAS modifier** `backend/app/services/llm/client.py` (s02 intact).
- **Ne PAS modifier** `backend/app/services/agents/maths_agent.py` (s02 intact).
- **Ne PAS modifier** `backend/app/services/rag/chroma_store.py` (s01 intact — on étend `Retriever`, pas `ChromaStore`).
- **Ne PAS modifier** `backend/app/services/rag/upload_service.py` (s01/s01b intact).
- **Ne PAS renommer** `MinioClient` ou `ChromaStore` (s01b les a figés).
- **Ne PAS créer** de migration Alembic pour `exercises` (s15 viendra avec `users` et consolidéra). `init_db()` (qui fait `Base.metadata.create_all`) suffit en dev/CI. La story documente ce follow-up dans la PR.
- **Ne PAS utiliser** `JSONB` (Postgres-only). Utiliser `sqlalchemy.JSON` (portable).
- **Ne PAS câbler** un autre provider LLM. Réutiliser `build_llm_client(settings)` de s02. Ollama reste `NotImplementedError`.
- **Ne PAS créer** d'ADR. Les décisions s'inscrivent dans l'architecture cible existante et dans le plan.
- **Ne PAS commit** depuis la base du repo. Tout le travail se fait dans `.worktrees/s03-generer-qcm/`.
- **Ne PAS push** vers `main` directement. PR obligatoire.

## The point everything turns on

**Le générateur DOIT valider l'existence + appartenance du document via la session DB avant d'invoquer le LLM.** C'est l'invariant multi-tenant : sans cette vérification, un attaquant (ou un bug) qui devine un UUID de document d'un autre pseudo peut générer un QCM sur des chunks qui ne sont pas les siens.

**Trois endroits où ce plan peut se tromper** :

1. **Le champ `questions` JSON vs le schéma Pydantic** : si Pydantic strict rejette trop de réponses LLM, on tombe dans le retry. Si Pydantic est trop laxiste, des QCM malformés passent. Le test `test_qcm_question_schema_validates_4_options_and_correct_index_range` doit verrouiller le schéma strict (4 options, `correct_index ∈ [0,3]`).
2. **La regex d'extraction JSON** : trop permissive (capture du texte autour), elle laisse passer du bruit. Trop stricte (exige un bloc `{...}` complet), elle rejette des réponses valides mais avec un préambule. Le pattern de `services/rag/ocr.py::_try_parse_json` est la référence.
3. **Le retry "une fois"** : le plan dit "retry une fois" (AC4), mais le LLM peut être en panne totale (erreur réseau). Le retry va aussi échouer. Le `QcmGenerationError("malformed_output")` est levé après 2 tentatives, mais en cas d'`Exception` non-JSON, on doit lever `QcmGenerationError("storage_failure")` (ou similaire) plutôt que boucler. Le test `test_generate_fails_after_max_retries` couvre ce cas.

## Files touched

**Code (5 fichiers modifiés, 3 nouveaux)** :
- `backend/app/core/config.py` (modifié, +4 lignes)
- `backend/.env.example` (modifié, +4 lignes)
- `backend/app/core/database/models.py` (modifié, +30 lignes pour `Exercise` + `ExerciseType`)
- `backend/app/services/rag/retriever.py` (modifié, +20 lignes pour `get_chunks_for_document`)
- `backend/app/cli.py` (modifié, +commande `generate-qcm`)
- `backend/app/services/exercises/__init__.py` (nouveau)
- `backend/app/services/exercises/qcm_generator.py` (nouveau, ~120 lignes)
- `docs/architecture.md` (modifié, ~10 lignes)

**Test (3 nouveaux, 4 étendus)** :
- `backend/tests/services/exercises/qcm_generator.py` (nouveau, 8-9 tests)
- `backend/tests/services/rag/test_retriever.py` (étendu, +2-3 tests)
- `backend/tests/cli/test_cli.py` (étendu, +4-5 tests)
- `backend/tests/core/test_config.py` (étendu, +1-2 tests)
- `backend/tests/core/test_models.py` (étendu, +1-2 tests)

**Non touchés** :
- `backend/app/services/llm/client.py` (s02, intact)
- `backend/app/services/agents/maths_agent.py` (s02, intact)
- `backend/app/services/rag/chroma_store.py` (s01, intact)
- `backend/app/services/rag/upload_service.py` (s01/s01b, intact)
- `backend/app/services/storage/minio_client.py` (s01b, intact)
- `backend/app/services/rag/ocr.py` (s01, intact)
- `backend/app/services/rag/ingestion.py` (s01, intact)
- `backend/app/services/rag/embeddings.py` (s01, intact)
- Tous les docs/plans/research/reviews de s01, s01b, s02 (figés)

## Test strategy

### Tests automatisés (un par AC)

| AC | Test | Couche |
|---|---|---|
| AC1 (CLI retourne n questions) | `test_cli.py::TestGenerateQcm::test_generate_qcm_returns_n_questions` | CLI |
| AC2 (JSON valide parsable) | `test_qcm_generator.py::TestSchema::test_generate_returns_valid_json` | Generator |
| AC3 (filtre par document_id) | `test_qcm_generator.py::TestDocumentFilter::test_generate_filters_chunks_by_document_id` | Generator |
| AC4 (retry sur output malformé) | `test_qcm_generator.py::TestRetry::test_generate_retries_once_on_malformed_output` | Generator |
| AC5 (persistence PostgreSQL) | `test_qcm_generator.py::TestPersistence::test_generate_persists_exercise_in_session` | Generator |
| AC6 (structure JSON) | `test_qcm_generator.py::TestSchema::test_qcm_question_schema_validates_4_options_and_correct_index_range` | Generator |

### Bites de régression (à faire en fin d'implémentation)

1. **Filtre document_id** : muter `QcmGenerator.generate` pour ne PAS filtrer (utiliser `get_chunks_for_document(subject, pseudo, "ALL", k)` au lieu de passer `document_id`) → AC3 rouge.
2. **Persistence** : muter `QcmGenerator.generate` pour ne PAS appeler `session.add(Exercise(...))` → AC5 rouge (le test vérifie `session.added`).
3. **Cross-tenant** : muter `QcmGenerator.generate` pour ne PAS vérifier `document.student_pseudo == pseudo` (skip la validation) → cross-tenant test rouge.

### Vérification manuelle (humain)

- Uploader un PDF, noter le `document_id`, générer un QCM, vérifier la structure.
- Tester le cross-tenant (un autre pseudo demande le même `document_id`).
- Tester le `document_not_found` (UUID bidon).
- Vérifier la persistance en PostgreSQL (l'`Exercise` apparaît avec le bon `student_pseudo`, `type='qcm'`, `questions` JSON valide).

### Pas de test d'intégration avec vrai LLM

L'intégration avec un vrai LLM (minimax via OpenRouter, ou openai) est best-effort, marqué `@pytest.mark.integration`, non bloquant. Les tests unitaires utilisent `FakeListChatModel` de langchain.

## Definition of Done

- Toutes les tâches cochées.
- `pytest --cov=app --cov-fail-under=80 -m "not integration"` passe (≥ 80% de couverture, cible 140+ tests).
- `ruff check app tests` passe (0 erreur).
- AC1-AC6 tous couverts par des tests.
- Cross-tenant : un test vérifie qu'un pseudo ne peut pas générer un QCM sur le document d'un autre.
- Retry : un test couvre le cas "première réponse malformée, deuxième correcte".
- Persist : un test vérifie que `Exercise` est commit en session avec tous les champs.
- CLI : exit 0 sur succès, exit 5 sur `document_not_found`, exit 4 sur `storage_failure`, exit 1 sur autre erreur.
- `qcm_generator` documente les 3 cas de parsing : valid direct, valid après extraction, invalid après retry.
- `init_db()` crée la table `exercises` (vérifié par un test qui appelle `init_db()` puis interroge la table).
- PR unique, description structurée : résumé, AC cochées, points d'attention (notamment le choix `sqlalchemy.JSON` vs `JSONB`, le nommage `created_at`, le follow-up Alembic pour s15).
- `git diff main...feature/s03-generer-qcm` est lisible.
- Review passée (`docs/reviews/s03-generer-qcm.md` avec `Ship allowed: yes`).

<< IP Mike: task granularity, what a good plan contains/avoids. >>
