---
validated: yes
---
# Plan — Story s08-correction-progressive

Branch: `feature/s08-correction-progressive`
Research: `docs/research/s08-correction-progressive.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s08-correction-progressive.md` — story purement backend, aucun écran à produire. Le design doc fige le contrat de sortie de la state machine 4 états × 2 types d'exercice. Ce plan n'invente rien côté UI.

## Target story

**Story** : s08-correction-progressive — Découvrir la correction par étapes (1 à 3 tentatives).

**Complexity** : 4 (state machine sur 4 états × 2 types d'exercice + génération d'indices LLM + couplage avec un verdict externe non-déterministe + fermeture de l'exercice après 3 échecs). Confirmé à la recherche § Cible, aucune divergence.

### Acceptance criteria (9 ACs)

1. Après un 1er échec (QCM ou texte), la réponse contient `correction_level: "partial"`, `hints: [str, ...]` (1-3 indices), `next_steps: str`.
2. Après un 2e échec sur le même exercice, `correction_level: "partial_attempt_2"` avec des indices plus spécifiques.
3. Après un 3e échec, `correction_level: "full_after_attempts"` avec la solution complète.
4. Si la 1re tentative réussit, `correction_level: "full"` avec solution + bonus.
5. State machine déterministe : succès à la tentative N (1 ≤ N ≤ 3) → `full` ; échec 1 ou 2 → `partial`/`partial_attempt_2` ; échec 3 → `full_after_attempts`. `attempt_number > 3` → fermé (409 / exit 6).
6. Tests couvrent les 4 états + le cas « réussite du premier coup » (5 transitions + 1 closed = 8 cas).
7. Test vérifie que les indices tentative 2 ≠ indices tentative 1.
8. Test vérifie l'isolation multi-tenant.
9. Test vérifie que `attempt_number > 3` retourne 409 (exit 6 en CLI).

## Decisions tranchées au planning

Issues de la recherche § Décisions, **toutes adoptées telles quelles** (D1-D8) :

- **D1** — **Option A** : state machine comme **fonction pure** `next_correction_level(attempt_number, is_success, max_attempts) -> Literal[...]`. Test trivial avec `@pytest.mark.parametrize` sur 8 transitions. La classe `ProgressiveCorrection` du CLAUDE.md est incomplète (un seul état `partial`) et remplacée par une fonction + un orchestrateur de service. La fonction pure est aussi référençable depuis s09+ (API REST).
- **D2** — **Option B** : **4 prompts versionnés** (`HINT_PROMPT_V1_QCM`, `HINT_PROMPT_V2_QCM`, `HINT_PROMPT_V1_TEXT`, `HINT_PROMPT_V2_TEXT`). Aligne sur AC7 (hints v1 ≠ v2) et la distinction QCM/texte.
- **D3** — **Option A** : `full_after_attempts` est marqué `is_success=False` dans l'`Attempt`. Cohérent avec l'AC3 (« la solution complète est dévoilée » ne dit pas « l'exercice est réussi »). s16 (dashboard) agrégera. **À confirmer au checkpoint**.
- **D4** — **Option A** : le **service** (pas le CLI) lève `ProgressiveCorrectionError("closed")` si `attempt_number > max_correction_attempts`. Le CLI mappe en exit 6. Cohérent avec le pattern s04 (le service lève `cross_tenant`, le CLI mappe en exit 5).
- **D5** — **Option A** : 1 retry avec prompt strict + fallback déterministe (hint générique « Relisez le cours lié à cet exercice et réessayez. »). Pattern aligné sur s03.
- **D6** — **Option B** : bonus points = 2 **seulement au first-try** (lecture stricte de s20 `docs/stories.md:826`). `bonus_points: int` exposé dans `CorrectionResult` ; s20 le consommera.
- **D7** — **Refactor minimal** : `submit-qcm` (s04) et `submit-text` (s07) restent **séparés** et chacun **étend** sa commande pour appeler la state machine après grading. **Pas de commande unifiée `submit-attempt`** dans cette story (refactor non-trivial, hors-scope). **Note** : la recherche recommandait l'unification ; je l'écarte pour rester aligné sur le pattern s04/s07 (commandes séparées, orchestration commune via le service).
- **D8** — **Option A** : pas de `CHECK constraint` en s08 (cohérent avec s04 qui ne crée pas de migration). `correction_level: String(32) nullable` est déjà en place. La CHECK est du ressort de s15 (Alembic).

### Décision complémentaire D9 — Refactor minimal de s04 et s07

Pour intégrer la state machine sans refactor majeur, le plan introduit un **service partagé** `ProgressiveCorrectionService` dans `backend/app/services/correction/progressive.py` qui :
- Prend en constructeur : `session_factory`, `max_attempts=3`, `hint_generator: HintGenerator`.
- Expose une méthode `evaluate(pseudo, exercise_id, grade_callback)` où `grade_callback` est un **callable** `(exercise, pseudo) -> tuple[bool, str]` (le verdict déjà calculé). `QcmGrader.grade` et `TextGrader.grade` sont wrappés dans ce callable par le CLI.
- Applique : ownership check, state machine, hint generation, persistance `Attempt` avec `correction_level`.

Cela permet de **garder s04 et s07 intacts** : le CLI de chaque commande wrap son grader dans un callable et appelle le service. Le service est la **seule source de vérité** pour la state machine et l'écriture de `correction_level`.

### Décision complémentaire D10 — Rejet explicite de `FLASHCARDS`

L'enum `ExerciseType` contient désormais 4 valeurs (`QCM`, `PROBLEME`, `REDACTION`, `FLASHCARDS`) après les merges s06 et s06b. La validation s08 :
- Accepte `QCM`, `PROBLEME`, `REDACTION` (les 3 types notés).
- Rejette `FLASHCARDS` (outil d'étude, pas noté, cf. design s06b) → `ProgressiveCorrectionError("invalid_exercise")`, exit 4.

Le bite test `test_flashcards_exercise_raises_invalid_exercise` mord si la liste des types acceptés est élargie par erreur.

## Tasks (ordered)

### Étape 0 — Préparation du worktree

0. [x] **Rebase sur main pour intégrer s05, s06, s06b, s07** : `git fetch origin && git rebase origin/main`. Main est à `473181c` (= s05 c8c9617 + s06 f928d65 + s06b 394d4d4 + s07 473181c squashés). Conflits attendus : aucun sur le code référencé par s08 (s07 a ajouté `text_grader.py` que s08 ne touche pas). **Vérification** : `git log --oneline -5` montre les 4 commits squashés.

### Étape 1 — Outillage (settings + service squelette)

1. [x] **Étendre `backend/app/core/config.py`** : ajouter `max_correction_attempts: int = 3` (env `MAX_CORRECTION_ATTEMPTS`, cohérent avec `CLAUDE.md:609`) dans `Settings`. **Vérification** : test dans `tests/core/test_config.py` (ajouter `TestProgressiveCorrectionSettings::test_default_max_correction_attempts_is_3` + `test_max_correction_attempts_override_via_env`).
2. [x] **Étendre `backend/.env.example`** : ajouter `MAX_CORRECTION_ATTEMPTS=3` commenté à la fin, avec un commentaire « nombre max de tentatives avant `full_after_attempts` ; ne pas confondre avec `QCM_MAX_*` (limites du générateur) ».

### Étape 2 — State machine + Hint generator (cœur s08)

3. [x] **Créer `backend/app/services/correction/__init__.py`** (vide, barrel) + `backend/app/services/correction/progressive.py` avec :
   - **Schémas Pydantic** :
     - `CorrectionResult(is_success: bool, feedback: str, correction_level: Literal["partial", "partial_attempt_2", "full", "full_after_attempts"], attempt_number: int, attempt_id: uuid.UUID, hints: list[str], next_steps: str | None, solution: str | None, detailed_correction: str | None, common_mistakes: str | None, bonus_points: int)`.
     - `ProgressiveCorrectionError(Exception)` : `kind: str` ∈ `{"exercise_not_found", "cross_tenant", "closed", "invalid_exercise", "storage_failure", "llm_failure", "no_chunks"}`. Pour AC9, le `kind="closed"` est levé quand `attempt_number > max_attempts`.
   - **Fonction pure** `next_correction_level(attempt_number: int, is_success: bool, max_attempts: int = 3) -> Literal[...]` (D1). Lève `ProgressiveCorrectionError("closed")` si `attempt_number > max_attempts`. Table de vérité (8 transitions parametrize) :
     | attempt | is_success | correction_level |
     |---|---|---|
     | 1 | true | `"full"` |
     | 1 | false | `"partial"` |
     | 2 | true | `"full"` |
     | 2 | false | `"partial_attempt_2"` |
     | 3 | true | `"full"` |
     | 3 | false | `"full_after_attempts"` |
     | 4+ | true ou false | `closed` (exception) |
   - **Classe `ProgressiveCorrectionService`** : constructeur `__init__(self, *, session_factory: Callable[[], _SessionLike] | None, hint_generator: HintGenerator | None = None, max_attempts: int = 3)`. Méthode publique :
     - `evaluate(pseudo: str, exercise_id: str, grade_callback: Callable[[Exercise, str], tuple[bool, str]]) -> CorrectionResult` :
       1. Valide `uuid.UUID(exercise_id)`. Si `session_factory` non None : récupère l'`Exercise`, vérifie `exercise.student_pseudo == pseudo`. Échec ou mauvais pseudo : `ProgressiveCorrectionError("cross_tenant", ...)` (même message que `exercise_not_found`, pas de leak). **Bite test critique** : le LLM (hint) et le grade_callback ne sont PAS appelés sur requête cross-tenant.
       2. Valide `exercise.type ∈ {QCM, PROBLEME, REDACTION}` (D10) → sinon `ProgressiveCorrectionError("invalid_exercise", ...)`. Bite test symétrique `FLASHCARDS` rejeté.
       3. Calcule `attempt_number = self._next_attempt_number(exercise_id, pseudo) + 1` (pattern qcm_grader.py:260-281). Si `attempt_number > self._max_attempts` : `ProgressiveCorrectionError("closed", ...)` **AVANT** d'appeler `grade_callback` ou les hints. **Bite test critique** (Piège n°11) : `grade_callback` et `hint_generator` ne sont PAS appelés.
       4. Appelle `is_success, feedback = grade_callback(exercise, pseudo)`. C'est la seule logique de scoring (déléguée à s04 ou s07).
       5. `correction_level = next_correction_level(attempt_number, is_success, self._max_attempts)`. **Pure function**.
       6. Si `correction_level in {"partial", "partial_attempt_2"}` : `hints, next_steps = self._hint_generator.generate_hints(exercise, attempt_number, feedback)`. Le hint_generator est None-safe (un test avec `hint_generator=None` doit fonctionner pour les cas `full` / `full_after_attempts`).
       7. Si `correction_level in {"full", "full_after_attempts"}` : `solution = exercise.expected_answer`, `detailed_correction = exercise.expected_answer`, `common_mistakes = None`. (Pour QCM, reconstruction depuis `questions` JSON ; pour texte, `expected_answer` direct.)
       8. Calcule `bonus_points = 2 if is_success and attempt_number == 1 else 0` (D6).
       9. Si `session_factory` non None : `session.add(Attempt(exercise_id=..., student_pseudo=pseudo, attempt_number=..., is_success=is_success, answer_text=None, raw_answers=[], correction_level=correction_level))` + `session.commit()`.
       10. Retourne `CorrectionResult(...)`.
   - **Vérification** : tests dans `tests/services/correction/test_progressive.py` (cf. § Tests).
4. [x] **Créer `backend/app/services/correction/hints.py`** avec :
   - **Dataclass** `HintContext(statement: str, exercise_type: ExerciseType, attempt_number: int, feedback: str, grading_criteria: list[str] | None, questions: list[dict] | None)`.
   - **4 prompts** constants :
     - `HINT_PROMPT_V1_QCM` : « L'élève a échoué à un QCM. Donne 1-3 indices sur le **concept** testé. Réponds UNIQUEMENT en JSON : `{"hints": ["..."], "next_steps": "..."}`. ».
     - `HINT_PROMPT_V2_QCM` : comme V1 + « L'élève a déjà vu les indices précédents (V1). Sois plus précis : identifie le type d'erreur (mauvaise compréhension vs distraction). ».
     - `HINT_PROMPT_V1_TEXT` : « L'élève a soumis une réponse libre à un problème/rédaction. Donne 1-3 indices sur les **critères de grading non remplis** (cf. grading_criteria). Réponds en JSON. ».
     - `HINT_PROMPT_V2_TEXT` : comme V1 + historique des indices + type d'erreur.
   - **Classe `HintGenerator`** : constructeur `__init__(self, *, llm: LlmClient, max_retries: int = 1)`. Méthode publique :
     - `generate_hints(context: HintContext) -> tuple[list[str], str]` :
       1. Construit le prompt selon `(context.exercise_type, context.attempt_number)`.
       2. Boucle retry : 1ère tentative prompt, retry avec un prompt « strict » exigeant UNIQUEMENT le JSON. Si retry échoue : fallback `(["Relisez le cours lié à cet exercice et réessayez."], "Consultez vos notes et réessayez demain.")`.
       3. Parse la sortie LLM avec un regex JSON simple (pas besoin de `_parsing.extract_json_block` ici, on est en texte pur). Si parse échoue : retry ; si retry échoue : fallback.
       4. Retourne `(hints, next_steps)`.
   - **Vérification** : tests dans `tests/services/correction/test_hints.py` (cf. § Tests).

### Étape 3 — CLI : extension de `submit-qcm` et `submit-text`

5. [x] **Étendre `backend/app/cli.py`** :
   - Ajouter `_build_progressive_service() -> ProgressiveCorrectionService` qui wire `db_session.init_db()`, `HintGenerator(llm=build_llm_client(settings), max_retries=settings.text_grader_max_retries)` (réutilise le setting s07), `max_attempts=settings.max_correction_attempts`. Le service s08 n'a pas son propre setting pour les retries de hints — on réutilise le setting de retry de s07.
   - **Étendre `submit_qcm` (s04)** : après `result = qcm_grader.grade(...)`, appeler `progressive.evaluate(pseudo, exercise_id, grade_callback=lambda ex, ps: (result.is_success, result.feedback))`. Le résultat affiché est la `CorrectionResult` du service s08 (avec `correction_level`, `hints`, etc.), pas le `GradingResult` brut de s04.
   - **Étendre `submit_text` (s07)** : même pattern. Après `result = text_grader.grade(...)`, appeler `progressive.evaluate(...)` avec un lambda wrappant le verdict texte.
   - **Mapping d'exceptions vers exit codes** (cohérent avec s04 + s07) :
     - `cross_tenant`, `exercise_not_found` → exit 5.
     - `invalid_exercise`, `invalid_exercise_type`, `invalid_answers` → exit 4.
     - `closed` → **exit 6** (nouveau, pour AC9).
     - `storage_failure`, `llm_failure` → exit 4.
   - **Helpers d'affichage** `_print_progressive_result(result)` qui affiche le `correction_level`, les `hints`, le `feedback` du grader sous-jacent. Réutilisé par les deux commandes.
   - **Vérification** : tests dans `tests/cli/test_cli.py::TestSubmitQcm` (étendu) + `TestSubmitText` (étendu) pour les nouveaux exit codes et le `correction_level` dans la sortie.

### Étape 4 — Tests

6. [x] **Créer `backend/tests/services/correction/test_progressive.py`** avec ~15 tests :
   - **`TestNextCorrectionLevel` (8 cas parametrize)** : les 8 transitions de la table de vérité (D1). Bite : neutraliser la branche `partial_attempt_2` → le test rouge (AC2).
   - **`TestProgressiveCorrectionService` (8 tests)** :
     - `test_service_evaluates_first_attempt_failure_with_partial` (AC1)
     - `test_service_evaluates_second_attempt_failure_with_partial_attempt_2` (AC2)
     - `test_service_evaluates_third_attempt_failure_with_full_after_attempts` (AC3)
     - `test_service_evaluates_first_try_success_with_full` (AC4, Piège n°6)
     - `test_service_evaluates_late_success_with_full` (AC5)
     - `test_service_persists_attempt_with_correction_level` (AC5)
     - `test_service_raises_closed_on_attempt_4` (AC9, Piège n°11)
     - `test_service_does_not_call_grade_callback_when_closed` (AC9, Piège n°11)
   - **`TestCrossTenant` (2 tests)** :
     - `test_foreign_exercise_raises_cross_tenant` (AC8, bite)
     - `test_cross_tenant_does_not_call_grade_callback_or_hint_generator` (AC8, Piège n°5)
   - **`TestInvalidExercise` (1 test)** :
     - `test_flashcards_exercise_raises_invalid_exercise` (D10)
7. [x] **Créer `backend/tests/services/correction/test_hints.py`** avec ~5 tests :
   - `test_generate_hints_v1_qcm_returns_list_of_strings` (AC1)
   - `test_generate_hints_v2_text_includes_grading_criteria_context` (AC2)
   - `test_generate_hints_v1_differ_from_v2_for_same_input` (AC7, bite : si on retire la diff, le test rouge)
   - `test_generate_hints_retries_on_malformed_output` (Piège n°7)
   - `test_generate_hints_falls_back_to_generic_when_llm_fails_twice` (Piège n°7)
8. [x] **Étendre `backend/tests/cli/test_cli.py`** avec ~6 tests pour la state machine intégrée :
   - `test_submit_qcm_first_try_failure_returns_partial_and_hints` (AC1) — utilise `_StubQcmGrader` + `_StubProgressiveService` ou stub LLM pour les hints.
   - `test_submit_qcm_first_try_success_returns_full` (AC4)
   - `test_submit_qcm_third_try_failure_returns_full_after_attempts` (AC3)
   - `test_submit_qcm_fourth_try_returns_six` (AC9, exit 6)
   - `test_submit_text_first_try_failure_returns_partial` (AC1)
   - `test_submit_text_fourth_try_returns_six` (AC9)

### Étape 5 — Vérification finale

9. [x] **Lancer la suite de tests complète** : `cd backend && python -m pytest -x -m "not integration"`. Tous les tests existants (≥ 327 après s07) + ~30 nouveaux doivent passer.
10. [x] **Vérifier la couverture** : `pytest --cov=app --cov-fail-under=80`. Les nouveaux modules `progressive.py` et `hints.py` doivent être couverts ≥ 80%.
11. [x] **Lint** : `ruff check app tests` clean.
12. [x] **Smoke test CLI manuel** (sanity, hors pytest) : créer un exercise factice via `generate-exercise` (s06), puis soumettre 3 fois avec des réponses volontairement fausses via `submit-text`, vérifier que les exit codes progressent 0 → 0 → 0 (avec `correction_level` qui change) → 6 (closed).

### Étape 6 — Commit unique

13. [x] **Un seul commit sur `feature/s08-correction-progressive`** (cf. convention s05, s06, s06b, s07) : `feat(correction): add progressive correction state machine (s08)`. Le commit inclut :
   - Tous les changements de code (étapes 1-5).
   - Note explicite dans le commit message : « Cette PR implémente la state machine 4 états de la correction progressive (partial / partial_attempt_2 / full / full_after_attempts). Le `partial_attempt_3` listé dans `CLAUDE.md:307` n'est PAS implémenté (3 max attempts rend cet état inutile) — la story prime (AC5). Le service s08 s'interface sur s04 (QCM) et s07 (texte) via un callable `grade_callback`, sans modifier ni l'un ni l'autre. `MAX_CORRECTION_ATTEMPTS=3` est ajouté à `Settings`. »

## Run interdicts

- **Ne pas modifier `qcm_grader.py` (s04) ni `text_grader.py` (s07)** : le service s08 les wrappe via un `grade_callback`. Le seul changement autorisé est dans `cli.py` (extension des commandes `submit_qcm` et `submit_text` pour appeler le service après le grading).
- **Ne pas créer de commande unifiée `submit-attempt`** (D7 alternative écartée) : c'est un refactor non-trivial, hors-scope. Chaque commande reste séparée.
- **Ne pas modifier `models.py`** : `Attempt.correction_level: String(32) nullable` est déjà en place (s04). Aucune migration Alembic.
- **Ne pas ajouter de CHECK constraint sur `correction_level`** (D8) : c'est le rôle de s15. s08 valide côté service.
- **Ne pas implémenter `partial_attempt_3`** : la story n'en retient que 4 états. Documenter dans le commit message.
- **Ne pas accepter `FLASHCARDS`** (D10) : c'est un outil d'étude, pas noté. Le bite test mord.
- **Ne pas persister de points dans `reward_ledger`** : c'est le rôle de s20. s08 expose `bonus_points: int` dans `CorrectionResult`.
- **Ne pas merger dans `main`** : c'est le job de `/ks-ship`. Un commit sur la branche suffit.
- **Ne pas utiliser `_parsing.extract_json_block` dans le hint generator** : les hints LLM sont du texte simple (regex JSON maison, fallback déterministe). Cohérent avec s07 (parsing regex direct).
- **Ne pas dupliquer `_next_attempt_number`** : importer le pattern ou le ré-implémenter localement (s04 l'a en privé, s08 le fait en privé). Une factorisation interviendrait idéalement en s15 ou s20, mais ce n'est pas le scope de s08.

## The point everything turns on

**Le point central** est l'**ordre strict des gardes** dans `ProgressiveCorrectionService.evaluate(...)` : cross-tenant AVANT grade_callback, attempt_number AVANT grade_callback, type validation AVANT grade_callback. Trois endroits où cela peut casser :

1. **La garde cross-tenant** : si elle est déplacée **après** `grade_callback(...)` ou `hint_generator.generate_hints(...)`, le test `test_foreign_exercise_raises_cross_tenant` rouge sur `assert grade_callback.calls == []` (et `assert hint_generator.calls == []`). **Comparaison** : le diff de `progressive.py` doit montrer la vérification d'ownership dans `evaluate(...)` **avant** tout appel à `grade_callback`.

2. **La garde `attempt_number > max_attempts`** : si elle est déplacée **après** `grade_callback`, le test `test_service_raises_closed_on_attempt_4` rouge sur `assert grade_callback.calls == []` (Piège n°11). **Comparaison** : le diff doit montrer le check `closed` **avant** `grade_callback`.

3. **La bite du `partial_attempt_2`** : si on omet cette branche dans `next_correction_level`, le test parametrize `attempt=2, is_success=False → "partial_attempt_2"` rouge (AC2). **Comparaison** : la table de vérité dans le code doit contenir explicitement la branche `elif attempt_number == 2: return "partial_attempt_2"`.

## Files touched

| Fichier | Action | Rôle |
|---|---|---|
| `backend/app/core/config.py` | Étendre (1 ligne) | `max_correction_attempts: int = 3`. |
| `backend/.env.example` | Étendre (1 ligne) | `MAX_CORRECTION_ATTEMPTS=3` commenté. |
| `backend/app/services/correction/__init__.py` | Créer (vide) | Barrel. |
| `backend/app/services/correction/progressive.py` | Créer (~200 lignes) | `next_correction_level` (pure) + `ProgressiveCorrectionService` + `CorrectionResult` + `ProgressiveCorrectionError`. |
| `backend/app/services/correction/hints.py` | Créer (~150 lignes) | `HintGenerator` + 4 prompts + `HintContext`. |
| `backend/app/cli.py` | Étendre (~80 lignes) | `_build_progressive_service` + extension de `submit_qcm` et `submit_text` + mapping d'exceptions + helpers d'affichage. |
| `backend/tests/services/correction/test_progressive.py` | Créer (~400 lignes) | 19 tests (8 parametrize + 8 service + 2 cross-tenant + 1 invalid). |
| `backend/tests/services/correction/test_hints.py` | Créer (~150 lignes) | 5 tests. |
| `backend/tests/cli/test_cli.py` | Étendre (~200 lignes) | 6 tests pour la state machine intégrée. |
| `backend/tests/core/test_config.py` | Étendre (~30 lignes) | `TestProgressiveCorrectionSettings`. |

**Aucun changement** dans `qcm_grader.py`, `text_grader.py`, `qcm_generator.py`, `free_generator.py`, `flashcard_generator.py`, `_parsing.py`, `models.py`, ou les autres stories.

## Test strategy

**Niveau unitaire** (couche service) : `test_progressive.py` — 19 tests couvrent toutes les ACs, tous les pièges, et les 6 décisions D1-D6 + D9-D10. La fonction pure `next_correction_level` est testée par `@pytest.mark.parametrize` sur 8 transitions, garantissant l'exhaustivité. Le bite test critique (cross-tenant + closed avant grade_callback) est obligatoire.

**Niveau unitaire** (couche hints) : `test_hints.py` — 5 tests avec stub LLM, couvrent les 4 prompts (QCM V1/V2, texte V1/V2), le retry, le fallback, et l'AC7 (v1 ≠ v2).

**Niveau CLI** (couche présentation) : `test_cli.py` — 6 tests vérifient que les commandes `submit_qcm` et `submit_text` retournent le `correction_level` dans la sortie JSON, et que exit code 6 = closed (AC9).

**Niveau settings** : `test_config.py` — 1 test assert `max_correction_attempts=3` par défaut, surchargeable via env.

**Pas de tests a11y/Lighthouse** (story backend pur).

**Pas de test d'intégration LLM réel** : la génération de hints est non-déterministe par nature. Tous les tests utilisent `_ScriptedLlm`. Test `@pytest.mark.integration` best-effort hors-scope.

**Smoke test manuel** (étape 5.4) : sanity check de bout en bout via CLI, hors pytest. Documenté dans le commit message.

## Definition of Done

- Toutes les tâches du plan cochées (13/13).
- `pytest -m "not integration"` passe (≥ 357 tests attendus après ajout de ~30 nouveaux).
- `pytest --cov=app --cov-fail-under=80` passe.
- `ruff check app tests` clean.
- AC1-AC9 tous couverts par des tests unitaires ET des tests CLI.
- **Multi-tenancy** : `test_foreign_exercise_raises_cross_tenant` passe, bite vérifié.
- **Closed (AC9)** : `test_service_raises_closed_on_attempt_4` ET `test_submit_qcm_fourth_try_returns_six` passent. Le grade_callback n'est PAS appelé après 3 échecs.
- **State machine exhaustive** : 8 transitions parametrize couvrent la table de vérité.
- **Hints V1 ≠ V2 (AC7)** : `test_generate_hints_v1_differ_from_v2_for_same_input` mord.
- **Bite test `partial_attempt_2` (AC2)** : le test parametrize `attempt=2, is_success=False` mord si on retire la branche.
- **Rejet `FLASHCARDS` (D10)** : `test_flashcards_exercise_raises_invalid_exercise` mord.
- Smoke test CLI manuel OK.
- Commit unique sur `feature/s08-correction-progressive`, message conventional commit avec note sur l'écart `partial_attempt_3` (CLAUDE.md vs story) et le couplage via `grade_callback`.
- Review passée (gate `Ship allowed: yes`).
