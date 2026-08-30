---
validated: yes
---
# Plan — Story s04-repondre-qcm

Branch: `feature/s04-repondre-qcm`
Research: `docs/research/s04-repondre-qcm.md` — read it first; this plan does not repeat it.

## Target story

**Story** : s04-repondre-qcm — Soumettre une réponse à un QCM et obtenir un verdict binaire.
**Complexity** : 2 (Persistence + comparison + JSON in/out. No LLM call for QCM scoring). Confirmé à la recherche (pas de divergence).

### Acceptance criteria (6 ACs, du research)

1. `python -m ktutor.cli submit-qcm --exercise-id <id> --answers '[0,2,1,3,0]'` retourne `{is_success: true|false, correct_count: int, total: int, feedback: string}`.
2. `is_success` est `true` si et seulement si TOUTES les réponses matchent `correct_index` pour TOUTES les questions.
3. L'attempt est persisté en PostgreSQL avec : `pseudo`, `exercise_id`, `attempt_number`, `is_success`, `submitted_at`, `raw_answers`.
4. Test : un score parfait retourne `is_success: true` et un score avec une seule mauvaise réponse retourne `is_success: false`.
5. Test : `attempt_number` est incrémenté correctement à travers plusieurs soumissions sur le même exercise.
6. Test : `pseudo_a` ne peut pas soumettre un QCM généré par `pseudo_b` (isolation multi-tenant).

## Decisions tranchées au planning

Issues de la recherche § Open questions, tranchées en checkpoint avec l'utilisateur :

- **Q1 (Exit code `invalid_answers`)** : code 4 (storage_failure). Justification : "mauvais input qui ne peut pas être persisté" étend la sémantique actuelle du code 4.
- **Q2 (Re-validation Pydantic)** : oui, defense-in-depth. Le grader passe chaque `dict` de `Exercise.questions` par `QcmQuestion.model_validate(...)` avant d'extraire les `correct_index`. Si invalide : `QcmGradingError("invalid_exercise")`.
- **Q3 (Schéma `Attempt`)** : pré-créer `answer_text` (TEXT, nullable) et `correction_level` (String(32), nullable) pour s07/s08. Cohérent avec l'architecture cible. Pas de migration Alembic (s15 viendra).
- **Q4 (Sortie CLI)** : rich Panel pour mode normal, `console.print_json` pour `--json`. Feedback textuel informatif : "Toutes les réponses sont correctes" (is_success=true) ou "X/Y réponses correctes" (is_success=false).
- **Q5 (Format `--answers`)** : string JSON `'[0,2,1,3,0]'` (cohérent avec l'AC1 et le pattern string-JSON de s02).
- **Q6 (Feedback textuel)** : format court et informatif, pas de moralisation.
- **Q7 (`is_success` = X==Y)** : comportement littéral de l'AC2. Affichage de `correct_count` pour transparence, mais `is_success` reste binaire.
- **Q8 (`attempt_number` 1-based)** : premier submission = 1, deuxième = 2, etc. Standard.
- **Q9 (Validation `raw_answers`)** : Pydantic `SubmittedAnswers(root=list[int])` avec `Field(ge=0, le=3)` par élément + longueur = `len(Exercise.questions)`. Erreur claire si invalide.

## Tasks (ordered)

### Étape 0 — Outillage (modèle `Attempt` + re-validation)

1. [x] **Étendre `backend/app/core/database/models.py`** : ajouter le modèle `Attempt` avec :
   - `id: Mapped[uuid.UUID]` PK (default `uuid.uuid4`)
   - `exercise_id: Mapped[uuid.UUID]` (FK logique vers `exercises.id`, deferred s15)
   - `student_pseudo: Mapped[str]` String(64), nullable=False, indexed
   - `attempt_number: Mapped[int]` Integer, nullable=False, `Field(ge=1)` au niveau Python
   - `is_success: Mapped[bool]`, nullable=False
   - `raw_answers: Mapped[list[int]]` via `JSON`, nullable=False
   - `submitted_at: Mapped[datetime]` DateTime(timezone=True), `server_default=func.now()`, nullable=False
   - `answer_text: Mapped[str | None]` String(8192), nullable=True (pour s07)
   - `correction_level: Mapped[str | None]` String(32), nullable=True (pour s08)
   - `__repr__` pour debug (id, pseudo, exercise_id, attempt_number, is_success)
   - **Vérification** : test dans `tests/core/test_models.py` (`TestAttempt::test_attempt_creation_with_raw_answers`).

### Étape 1 — Service `QcmGrader`

2. [x] **Créer `backend/app/services/exercises/qcm_grader.py`** avec :
   - `QcmGradingError(Exception)` : `kind: str` ∈ `{"exercise_not_found", "cross_tenant", "invalid_answers", "invalid_exercise", "storage_failure"}`, `message: str`.
   - `GradingResult(BaseModel)` : `is_success: bool`, `correct_count: int`, `total: int`, `feedback: str`, `attempt_id: uuid.UUID`.
   - `SubmittedAnswers(BaseModel)` : `root: list[int] = Field(min_length=1)`, validator sur chaque élément (0 ≤ x ≤ 3) et sur la longueur (vs Exercise.questions).
   - `_SessionLike` Protocol : `get`, `add`, `commit`, `rollback`, `query` (pour `MAX(attempt_number)`).
   - `QcmGrader` classe : constructeur `__init__(self, *, session_factory: Callable[[], _SessionLike])`. Méthode publique :
     - `grade(pseudo: str, exercise_id: str, raw_answers: list[int]) -> GradingResult` :
       1. Valide `uuid.UUID(exercise_id)`, lève `QcmGradingError("exercise_not_found", ...)` si invalide.
       2. `session.get(Exercise, exercise_uuid)` ; si `None` : `QcmGradingError("exercise_not_found", ...)`.
       3. **Multi-tenancy** : `if exercise.student_pseudo != pseudo` : `QcmGradingError("cross_tenant", ...)` (même message que not_found, pas de leak).
       4. **Re-validation Pydantic** : pour chaque `dict` dans `exercise.questions`, `QcmQuestion.model_validate(d)` ; si ValidationError : `QcmGradingError("invalid_exercise", ...)`. Construit `list[QcmQuestion]`.
       5. **Validation des `raw_answers`** : `SubmittedAnswers(root=raw_answers, expected_length=len(questions))` ; si invalide (longueur ou valeurs) : `QcmGradingError("invalid_answers", ...)`.
       6. **Grading** : `correct_count = sum(1 for a, q in zip(answers, questions) if a == q.correct_index)`, `is_success = (correct_count == len(questions))`.
       7. **`attempt_number`** : `SELECT MAX(attempt_number) FROM attempts WHERE exercise_id = ? AND student_pseudo = ?` (ou COUNT(*) + 1). Premier = 1.
       8. **Persistance** : `session.add(Attempt(id=uuid.uuid4(), exercise_id=exercise_uuid, student_pseudo=pseudo, attempt_number=N, is_success=is_success, raw_answers=raw_answers))` + `session.commit()`. Try/except + rollback.
       9. **Feedback** : `is_success ? "Toutes les réponses sont correctes." : f"{correct_count}/{total} réponses correctes."`
       10. Retourne `GradingResult(is_success, correct_count, total=len(questions), feedback, attempt_id)`.
   - **Vérification** : 6-7 tests dans `tests/services/exercises/qcm_grader.py` :
     - `TestSchema::test_submitted_answers_rejects_wrong_length` (Q9 — validator).
     - `TestSchema::test_submitted_answers_rejects_out_of_range_value` (Q9).
     - `TestGrade::test_perfect_score_returns_is_success_true` (AC2, AC4 — bite #1).
     - `TestGrade::test_one_wrong_answer_returns_is_success_false` (AC2, AC4 — bite #1).
     - `TestPersistence::test_attempt_persisted_with_all_fields` (AC3).
     - `TestAttemptNumber::test_attempt_number_increments_across_submissions` (AC5 — bite #2).
     - `TestCrossTenant::test_cross_tenant_raises_grading_error` (AC6 — bite #3).
     - `TestInvalidExercise::test_malformed_exercise_questions_raises_grading_error` (defense-in-depth, Q2).
     - `TestExerciseNotFound::test_unknown_exercise_id_raises_grading_error`.

### Étape 2 — Commande CLI

3. [x] **Étendre `backend/app/cli.py`** :
   - `_build_grader_service() -> QcmGrader` : instancie `db_session.init_db()`, retourne `QcmGrader(session_factory=db_session.get_session_factory())`.
   - `@app.command() def submit_qcm(exercise_id: str = typer.Option(..., "--exercise-id"), answers: str = typer.Option(..., "--answers", help="Réponses en JSON, ex: '[0,2,1,3,0]'"), quiet: bool = typer.Option(False, "--quiet"), json_output: bool = typer.Option(False, "--json"))` :
     - Parse `json.loads(answers)` (si JSON invalide : exit 4 avec message).
     - Appelle `service.grade(pseudo, exercise_id, raw_answers)`. **Note** : pas de `--pseudo` dans l'AC1, le CLI prend `--pseudo` partagé ? Vérifier l'AC1 : `python -m ktutor.cli submit-qcm --exercise-id <id> --answers '[0,2,1,3,0]'` → la commande n'a pas `--pseudo` ! Décision : ajouter `--pseudo` quand même (cohérent avec upload/chat/generate-qcm). L'AC1 est probablement sous-spécifiée sur ce point.
     - Exit 0 sur succès, exit 4 sur `invalid_answers` ou `invalid_exercise`, exit 5 sur `cross_tenant` ou `exercise_not_found`, exit 1 sur autre.
   - `_print_grading_result(result, *, json_output)` : rich Panel avec récap (succès/échec + score X/Y + feedback) ou JSON.
   - **Vérification** : 3-4 tests dans `tests/cli/test_cli.py` (`TestSubmitQcm`):
     - `test_submit_qcm_returns_zero_with_success`.
     - `test_submit_qcm_json_output_is_valid`.
     - `test_submit_qcm_invalid_answers_returns_4`.
     - `test_submit_qcm_help_works`.

### Étape 3 — Doc

4. [x] **Étendre `docs/architecture.md:207-217`** : confirmer le modèle `attempts` (les colonnes `answer_text` et `correction_level` sont nullable, `raw_answers` est stocké en `sqlalchemy.JSON` portable, pas `JSONB`). Note inline sur le deferred FK (`users.pseudo` arrive en s15).

### Étape 4 — Vérification finale

5. [x] **Run global** : `cd backend && pytest --cov=app --cov-fail-under=80 -m "not integration"`. Cible : 170+ tests passent, couverture ≥ 80%.
6. [x] **Lint** : `cd backend && ruff check app tests`. 0 erreur.
7. [x] **Vérification manuelle** (humain) :
    - Générer un QCM depuis s03.
    - Soumettre les bonnes réponses → `is_success: true`, `correct_count: 5`, `total: 5`.
    - Soumettre une mauvaise réponse → `is_success: false`, `correct_count: 4`, `total: 5`.
    - Soumettre 2 fois de suite → vérifier `attempt_number: 1` puis `2` en base.
    - Soumettre avec un mauvais `--pseudo` → erreur cross-tenant, exit 5.

## Run interdicts

- **Ne PAS modifier** `backend/app/services/exercises/qcm_generator.py` (s03, intact).
- **Ne PAS modifier** `backend/app/services/rag/retriever.py` (s02/s03, intact).
- **Ne PAS modifier** `backend/app/services/llm/client.py` (s02, intact).
- **Ne PAS modifier** `backend/app/services/agents/maths_agent.py` (s02, intact).
- **Ne PAS modifier** `backend/app/services/rag/chroma_store.py` (s01, intact).
- **Ne PAS modifier** `backend/app/services/rag/upload_service.py` (s01, intact).
- **Ne PAS renommer** `MinioClient` ou `ChromaStore` (s01b les a figés).
- **Ne PAS câbler** de LLM dans `QcmGrader`. Le scoring est 100% déterministe.
- **Ne PAS créer** de migration Alembic pour `attempts` (s15 viendra avec `users`). `init_db()` (déjà appelé par `_build_grader_service`) suffit en dev/CI.
- **Ne PAS utiliser** `JSONB` (Postgres-only). Utiliser `sqlalchemy.JSON` (portable).
- **Ne PAS modifier** `docs/architecture.md` au-delà du modèle `attempts` (l.207-217).
- **Ne PAS commit** depuis la base du repo. Tout le travail se fait dans `.worktrees/s04-repondre-qcm/`.
- **Ne PAS push** vers `main` directement. PR obligatoire.

## The point everything turns on

**L'invariant multi-tenant** : `Exercise.student_pseudo == pseudo`. Sans cette vérification, un élève A peut deviner un UUID d'exercise et soumettre ses réponses (test attack). Le check DOIT être fait après `session.get(Exercise, ...)` mais avant toute logique de grading. **La check se fait en premier sur la session DB (pas via la collection ChromaDB), parce que l'Exercise est persisté en DB**.

**Trois endroits où ce plan peut se tromper** :

1. **L'instruction `MAX(attempt_number)`** : il faut un `session.query(Attempt).filter(...).with_entities(func.max(Attempt.attempt_number))`. Si la table est vide, `MAX` retourne `None` → `attempt_number = 1`. Si la session a déjà flushé l'attempt précédent, `MAX` peut retourner cette valeur + 1. **À tester explicitement** (`TestAttemptNumber::test_attempt_number_increments_across_submissions`).
2. **La re-validation Pydantic** : si `Exercise.questions` contient un dict mal formé (ex. `correct_index: 5`), le test `TestInvalidExercise` doit tourner. Le coût est 1 test et une layer de sécurité.
3. **Le format `--answers`** : l'AC1 spécifie `'[0,2,1,3,0]'` (string JSON). Si le CLI parse via `json.loads` et que la string est `'0,2,1,3,0'` (sans crochets), `json.loads` lève `JSONDecodeError`. Le handler doit capturer et lever une erreur claire.

## Files touched

**Code (3 fichiers modifiés, 1 nouveau)** :
- `backend/app/core/database/models.py` (modifié, +~30 lignes pour `Attempt`).
- `backend/app/services/exercises/qcm_grader.py` (nouveau, ~100 lignes).
- `backend/app/cli.py` (modifié, +commande `submit_qcm`).
- `docs/architecture.md` (modifié, ~5 lignes).

**Test (2 nouveaux, 2 étendus)** :
- `backend/tests/services/exercises/qcm_grader.py` (nouveau, 8-9 tests).
- `backend/tests/cli/test_cli.py` (étendu, +4 tests pour `submit-qcm`).
- `backend/tests/core/test_models.py` (étendu, +1 test pour `Attempt`).

**Non touchés** :
- `backend/app/services/exercises/qcm_generator.py` (s03, intact).
- `backend/app/services/rag/retriever.py` (s02/s03, intact).
- `backend/app/services/llm/client.py` (s02, intact).
- `backend/app/services/agents/maths_agent.py` (s02, intact).
- `backend/app/services/rag/chroma_store.py` (s01, intact).
- `backend/app/services/rag/upload_service.py` (s01, intact).
- `backend/app/services/storage/minio_client.py` (s01b, intact).
- `backend/app/core/config.py` (s02/s03, intact — pas de nouvelle variable).
- `backend/.env.example` (s02/s03, intact).
- Tous les docs de s01, s01b, s02, s03 (figés).

## Test strategy

### Tests automatisés (un par AC)

| AC | Test | Couche |
|---|---|---|
| AC1 (CLI retourne is_success/correct_count/total/feedback) | `test_cli.py::TestSubmitQcm::test_submit_qcm_returns_zero_with_success` | CLI |
| AC2 (is_success = true ssi toutes les réponses matchent) | `test_qcm_grader.py::TestGrade::test_perfect_score_returns_is_success_true` + `test_one_wrong_answer_returns_is_success_false` | Grader |
| AC3 (attempt persisté avec les 6 champs) | `test_qcm_grader.py::TestPersistence::test_attempt_persisted_with_all_fields` | Grader |
| AC4 (perfect → true, one wrong → false) | Idem AC2 | Grader |
| AC5 (attempt_number incrémenté) | `test_qcm_grader.py::TestAttemptNumber::test_attempt_number_increments_across_submissions` | Grader |
| AC6 (cross-tenant) | `test_qcm_grader.py::TestCrossTenant::test_cross_tenant_raises_grading_error` | Grader |

### Bites de régression (à faire en fin d'implémentation)

1. **AC2 / AC4** : muter `QcmGrader.grade` pour retourner `is_success=True` toujours → test rouge.
2. **AC5** : muter le calcul d'`attempt_number` pour toujours retourner 1 (compteur en mémoire) → test rouge.
3. **AC6** : retirer le check `Exercise.student_pseudo != pseudo` → test rouge.

### Vérification manuelle (humain)

- Générer un QCM depuis s03.
- Soumettre les bonnes réponses → succès.
- Soumettre avec une erreur → échec.
- Soumettre 2 fois → vérifier `attempt_number` en base.
- Soumettre avec un mauvais `--pseudo` → cross-tenant.

### Pas de test d'intégration (s04 est déterministe)

Tous les tests sont unitaires (SQLite in-memory + `_TrackingSession`). Pas de marqueur `@pytest.mark.integration` nécessaire.

## Definition of Done

- Toutes les tâches cochées.
- `pytest --cov=app --cov-fail-under=80 -m "not integration"` passe (≥ 80% de couverture, cible 170+ tests).
- `ruff check app tests` passe (0 erreur).
- AC1-AC6 tous couverts par des tests.
- Cross-tenant : un test vérifie qu'un pseudo ne peut pas soumettre un QCM d'un autre.
- `attempt_number` : un test vérifie l'incrément correct après 2+ soumissions sur le même exercise.
- `is_success` : un test pour le cas "tout parfait" et un test pour "une erreur".
- CLI : exit 0 sur succès, exit 4 sur `invalid_answers` ou `invalid_exercise`, exit 5 sur `cross_tenant` ou `exercise_not_found`, exit 1 sur autre.
- `QcmGrader` est 100% déterministe (aucun appel LLM, vérifié par absence d'import `LlmClient`).
- PR unique, description structurée : résumé, AC cochées, points d'attention (notamment le choix exit code 4 pour `invalid_answers`, le pre-création de `answer_text`/`correction_level`, le defense-in-depth Pydantic).
- `git diff main...feature/s04-repondre-qcm` est lisible.
- Review passée (`docs/reviews/s04-repondre-qcm.md` avec `Ship allowed: yes`).

<< IP Mike: task granularity, what a good plan contains/avoids. >>
