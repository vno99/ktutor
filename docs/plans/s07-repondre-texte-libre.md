---
validated: yes
---
# Plan — Story s07-repondre-texte-libre

Branch: `feature/s07-repondre-texte-libre`
Research: `docs/research/s07-repondre-texte-libre.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s07-repondre-texte-libre.md` — story purement backend, aucun écran à produire. Le design doc fige le contrat de sortie JSON du grader et les comportements UI attendus des futures stories (s11, s16, s19). Ce plan n'invente rien côté UI.

## Target story

**Story** : s07-repondre-texte-libre — Soumettre ma réponse (texte) à un exercice de type problème ou rédaction et recevoir une appréciation qualitative (positive ou échec) du LLM.

**Complexity** : 3 (LLM-as-judge + prompt engineering + parsing + persistence). Confirmé à la recherche § 1, aucune divergence.

### Acceptance criteria (6 ACs, du research)

1. CLI `python -m ktutor.cli submit-text --exercise-id <id> --answer "..."` retourne `{is_success: bool, feedback: string, attempt_number: int}`.
2. Le grading utilise un prompt LLM qui compare la réponse de l'élève à `expected_answer` et produit un verdict (`REUSSITE` ou `ECHEC`) plus un feedback d'une phrase.
3. Le parsing du verdict est strict (regex sur la ligne `VERDICT:`) ; si absente, le système retente une fois avec un prompt plus strict, puis échoue avec une erreur claire.
4. L'attempt est persisté (même modèle `Attempt` que s04, avec `answer_text` au lieu de `raw_answers`).
5. Un test avec un LLM stub qui retourne `VERDICT: REUSSITE` vérifie que `is_success` est `true`.
6. Un test avec un LLM stub qui ne retourne aucune ligne `VERDICT:` vérifie que le système retente puis échoue.
7. Un test vérifie l'isolation multi-tenant (pseudo_a ne peut pas soumettre à un exercise de pseudo_b).

## Decisions tranchées au planning

Issues de la recherche § 6, **toutes adoptées telles quelles** (D1-D7) :

- **D1** — **Option D1.a** : `Attempt` partagé. QCM laisse `answer_text=NULL` et `raw_answers=[...]`. Texte laisse `raw_answers=[]` et `answer_text="..."`. **Aucune migration** : `answer_text` est déjà en place depuis s04 (ligne 182 du modèle).
- **D2** — **Option D2.a étendue** : `if exercise.type not in {ExerciseType.PROBLEME, ExerciseType.REDACTION}: raise TextGradingError("invalid_exercise_type")`. **Extension post-s06b** : la liste des types rejetés inclut désormais `QCM` et `FLASHCARDS` (en plus de ce qui n'existe pas encore). Le test bite mord pour les 2 types rejetés (cf. D2.b ci-dessous).
- **D3** — **Option D3.a** : `TextGradingResult = {is_success: bool, feedback: str, attempt_id: UUID, attempt_number: int}`. Aligné sur l'AC1, minimal, sans bruit. Le `raw_verdict` est loggué (loguru) mais pas retourné à l'élève.
- **D4** — **Option D4.a (refuser)** : `TextGradingError("answer_too_long", ...)` retournée au CLI, exit 2. **Pas d'appel LLM** sur réponse trop longue. D4.b (troncature silencieuse) est risquée (l'élève ne sait pas que sa fin a été coupée).
- **D5** — **Option D5.a (texte avant verdict)** : prendre tout le texte **avant** la ligne `VERDICT:`, nettoyer les espaces, retourner comme feedback. Tolérant à la prose.
- **D6** — **Option D6.a (faire confiance au verdict)** : pas de second passage LLM. Le verdict structuré prime sur la cohérence du feedback.
- **D7** — **Gate obsolète** : s06 a déjà été squash-merge sur `main` (f928d65, PR #7) avant le début de s07. Le rebase en étape 0 du plan suffit pour intégrer le code de s06. **D7 est satisfaite d'office** (pas besoin de check supplémentaire).

### Décision complémentaire D2.b — Symétrie du bite test pour `FLASHCARDS`

La recherche D2.a recommande un bite test `test_qcm_exercise_raises_invalid_exercise_type`. **Après merge de s06b** (squash 394d4d4, PR #8), l'enum `ExerciseType` contient 4 valeurs : `QCM`, `PROBLEME`, `REDACTION`, `FLASHCARDS`. La validation D2.a doit rejeter **2** types (`QCM` et `FLASHCARDS`), pas seulement `QCM`. Le plan doit donc inclure **deux** bite tests symétriques :

- `test_qcm_exercise_raises_invalid_exercise_type` (QCM rejeté)
- `test_flashcards_exercise_raises_invalid_exercise_type` (FLASHCARDS rejeté — cohérent avec la note design s06b : « study aid, not an evaluated exercise »)

### Décision complémentaire D8 — Patterns de test réutilisés

- **`_ScriptedLlm`** : import depuis `tests/services/exercises/test_qcm_grader.py` (s'il existe) ou `test_qcm_generator.py:47-62`. Pas de duplication : **extraction** vers `tests/services/exercises/_test_doubles.py` (nouveau module de test privé) qui exporte `_ScriptedLlm`, `_TrackingSession`, `memory_db`, `_SessionFactory`. Imports depuis les 3 générateurs + les 2 graders.

  **Recommandation** : **(a) dupliquer localement** dans `test_text_grader.py` (cohérent avec ce que s04 a fait pour le QCM grader — il a ses propres `_ScriptedLlm`/`_TrackingSession` dans `test_qcm_grader.py:40-90` sans factoriser). C'est plus simple et le helper est petit (~30 lignes). **(b) factoriser** maintenant pour 3 générateurs + 2 graders est une décision d'outillage de test qui sort du périmètre de s07. **Recommandation (a)** : duplication locale, alignée sur la convention s04.

- **`FakeListChatModel`** (LangChain) : alternative au `_ScriptedLlm`. s04 ne l'utilise pas. s07 reproduit le pattern s04 par cohérence.

### Décision complémentaire D9 — Réutilisation de `_next_attempt_number` du QCM grader

Le pattern `SELECT MAX(attempt_number) FROM attempts WHERE exercise_id = ? AND student_pseudo = ?` (qcm_grader.py:259-281) est **réutilisable tel quel** par s07. Le plan doit soit (a) dupliquer la méthode, soit (b) l'extraire vers un helper partagé (s07 + s04 + futur s08 correction). **Recommandation (a)** par parallélisme avec s04 : duplication locale. Une factorisation interviendrait idéalement en s08, mais ce n'est pas le scope de s07.

## Tasks (ordered)

### Étape 0 — Préparation du worktree

0. [x] **Rebase sur main pour intégrer s05, s06, s06b** : `git fetch origin && git rebase origin/main`. Main est à `394d4d4` (= s05 c8c9617 + s06 f928d65 + s06b 394d4d4 squashés). Conflits attendus : aucun sur le code référencé par s07 (s05 additif, s06 et s06b modifient des fichiers que s07 ne touche pas : `models.py` enum étendue, `free_generator.py` nouveau, `flashcard_generator.py` nouveau, `cli.py` ajout de commandes). **Vérification** : `git log --oneline -4` montre les 3 commits squashés.

### Étape 1 — Outillage (config + settings)

1. [x] **Étendre `backend/app/core/config.py`** : bloc `TEXT_GRADER_*` après le bloc `FLASHCARDS_*` (ajouté par s06b), avec :
   - `text_grader_max_retries: int = 1` (env `TEXT_GRADER_MAX_RETRIES`, cohérent avec `qcm_max_retries=1`)
   - `text_grader_temperature: float = 0.0` (env `TEXT_GRADER_TEMPERATURE`, défaut tests/prod)
   - `text_grader_max_answer_chars: int = 8000` (env `TEXT_GRADER_MAX_ANSWER_CHARS`, filet de sécurité avant la limite 8192 de la colonne `String(8192)` de `Attempt.answer_text`, cf. recherche § 4.6)
   - **Vérification** : test dans `tests/core/test_config.py` (ajouter `TestTextGraderSettings::test_default_text_grader_settings` qui assert les 3 valeurs par défaut).
2. [x] **Étendre `backend/.env.example`** : 3 variables `TEXT_GRADER_*` commentées après le bloc `FLASHCARDS_*` (lignes ajoutées par s06b), avec un commentaire expliquant le rôle de `text_grader_max_answer_chars` (garde-fou avant la limite de la colonne).

### Étape 2 — Text Grader (Pydantic + LLM + parsing + persistence)

3. [x] **Créer `backend/app/services/exercises/text_grader.py`** avec :
   - **Regex de parsing** : `VERDICT_RE = re.compile(r"VERDICT:\s*(REUSSITE|ECHEC)", re.IGNORECASE)` (cf. recherche § 4.2). Matche `VERDICT: REUSSITE` ou `VERDICT: ECHEC` en casse mixte.
   - **Schémas Pydantic** :
     - `TextSubmission(answer: str = Field(min_length=1, max_length=8000))` — `max_length=8000` correspond à `text_grader_max_answer_chars` (validation à la frontière).
     - `TextGradingResult(is_success: bool, feedback: str, attempt_id: uuid.UUID, attempt_number: int)`.
   - **Exceptions** : `TextGradingError(Exception)` avec `kind: str` ∈ `{"exercise_not_found", "cross_tenant", "invalid_exercise_type", "answer_too_long", "verdict_missing", "llm_failure", "storage_failure"}` (cohérent avec `QcmGradingError` + extensions s07).
   - **Prompts** :
     - `_TEXT_GRADER_SYSTEM_PROMPT` : explique les invariants (« tu es un évaluateur, pas un générateur ; tu réponds UNIQUEMENT en français ; tu termines par une ligne `VERDICT: REUSSITE` ou `VERDICT: ECHEC` ; tu compares la réponse de l'élève à `expected_answer` en t'appuyant sur `grading_criteria` ; tu es STRICT : pas de REUSSITE si la réponse est hors sujet ou incomplète »).
     - `_USER_PROMPT_TEMPLATE` (soft) : injecte `statement`, `expected_answer`, `grading_criteria`, `answer`. Termine par l'instruction de format.
     - `_STRICT_USER_PROMPT_TEMPLATE` (retry) : encore plus impératif, exige UNIQUEMENT la ligne `VERDICT:`.
   - **`TextGrader` classe** : constructeur `__init__(self, *, llm: LlmClient, session_factory: Callable[[], _SessionLike] | None = None, max_retries: int = 1, temperature: float = 0.0, max_answer_chars: int = 8000)`. Méthode publique :
     - `grade(pseudo: str, exercise_id: str, answer: str) -> TextGradingResult` :
       1. Valide `len(answer) <= max_answer_chars` → sinon `TextGradingError("answer_too_long", ...)`. **Bite test critique** : le LLM n'est PAS appelé sur réponse trop longue.
       2. Valide `uuid.UUID(exercise_id)`. Si `session_factory` non None : récupère l'`Exercise`, vérifie `exercise.student_pseudo == pseudo`. Échec ou mauvais pseudo : `TextGradingError("cross_tenant", ...)` (même message, pas de leak). **Bite test critique** : le LLM n'est PAS appelé sur requête cross-tenant, et aucun `Attempt` n'est persisté.
       3. Vérifie `exercise.type ∈ {PROBLEME, REDACTION}` → sinon `TextGradingError("invalid_exercise_type", ...)`. **Bite test critique** : QCM et FLASHCARDS sont rejetés.
       4. Valide que `exercise.statement`, `exercise.expected_answer`, `exercise.grading_criteria` sont non-NULL → sinon `TextGradingError("invalid_exercise", ...)` (defense-in-depth, en pratique s06 garantit ces champs).
       5. Construit le user prompt avec les 4 champs. Boucle retry `for i in range(max_retries + 1)` : 1ère itération prompt soft, 2ème prompt strict. Chaque appel : `self._llm.invoke([SystemMessage, HumanMessage])`. Parse la sortie avec `VERDICT_RE.search(output)`. Si match : extrait verdict (lowercased) et feedback (texte avant la ligne `VERDICT:`, stripé). Si pas de match : retry, puis `TextGradingError("verdict_missing", ...)` après `max_retries + 1` tentatives.
       6. Calcule `attempt_number = self._next_attempt_number(exercise_id, pseudo) + 1` (réutilise le pattern s04 qcm_grader.py:259-281).
       7. Si `session_factory` non None : `session.add(Attempt(exercise_id=..., student_pseudo=pseudo, attempt_number=..., is_success=..., answer_text=answer, raw_answers=[]))` + `session.commit()`.
       8. Retourne `TextGradingResult(is_success, feedback, attempt_id, attempt_number)`.
   - **Vérification** : tests dans `tests/services/exercises/test_text_grader.py` (cf. § Tests).

### Étape 3 — CLI

4. [x] **Étendre `backend/app/cli.py`** :
   - Ajouter `_build_text_grader_service() -> TextGrader` à côté de `_build_flashcard_service()` (ajouté par s06b). Wire-up : `db_session.init_db()`, `build_llm_client(settings)`, `TextGrader(session_factory=..., max_retries=settings.text_grader_max_retries, temperature=settings.text_grader_temperature, max_answer_chars=settings.text_grader_max_answer_chars)`.
   - Ajouter la commande typer `submit_text(...)` à côté de `submit_qcm` (l. 471). Options :
     - `--exercise-id` (required, UUID)
     - `--answer` (required, string)
   - Mapping d'exceptions vers exit codes (cohérent avec conventions `docs/designs/s01-uploader-document.md`) :
     - `cross_tenant`, `exercise_not_found`, `invalid_exercise_type` → exit 5.
     - `verdict_missing`, `llm_failure`, `storage_failure`, `invalid_exercise` → exit 4.
     - `answer_too_long` → exit 2.
   - Helpers d'affichage `_print_text_result(result)` et `_print_text_error(error: TextGradingError)` à côté de `_print_qcm_result` et `_print_qcm_error`.
   - **Vérification** : tests dans `tests/cli/test_cli.py::TestSubmitText` (cf. § Tests).

### Étape 4 — Tests

5. [x] **Créer `backend/tests/services/exercises/test_text_grader.py`** avec ~16 tests :
   - Pattern réutilisé : `_ScriptedLlm` et `_TrackingSession` dupliqués localement (D8.a) depuis `test_qcm_grader.py:40-90` (~30 lignes). Fixtures `memory_db`, `_SessionFactory` réutilisées.
   - **TestSchema (2 tests)** :
     - `test_text_submission_rejects_empty_answer` : `answer=""` → Pydantic rejette (`min_length=1`).
     - `test_text_submission_rejects_too_long_answer` : `answer="x" * 8001` → Pydantic rejette (`max_length=8000`). Bite : si `max_length` retiré, le test mord.
   - **TestGrade (8 tests)** :
     - `test_verdict_reussite_returns_is_success_true` (AC1, AC2, AC5) : LLM stub retourne `"Bonne réponse.\nVERDICT: REUSSITE"` → `is_success=True`, feedback="Bonne réponse.".
     - `test_verdict_echec_returns_is_success_false` (AC1, AC2) : LLM stub retourne `"Réponse incomplète.\nVERDICT: ECHEC"` → `is_success=False`, feedback="Réponse incomplète.".
     - `test_verdict_extraction_is_case_insensitive` (D5) : LLM stub retourne `"verdict: reussite"` (casse mixte) → `is_success=True`. Bite : sans `re.IGNORECASE`, le test mord.
     - `test_feedback_extracted_before_verdict_line` (AC2) : LLM stub retourne `"La démarche est correcte, mais le résultat est faux.\nVERDICT: ECHEC"` → feedback contient « La démarche est correcte, mais le résultat est faux. ».
     - `test_no_verdict_retries_then_fails` (AC3, AC6) : LLM stub retourne d'abord un texte sans `VERDICT:`, puis encore un texte sans `VERDICT:` au retry. → `TextGradingError("verdict_missing")`. Assert `len(llm.calls) == 2` (1ère tentative + retry).
     - `test_strict_prompt_used_on_retry` (AC3, AC6) : LLM stub retourne d'abord sans verdict, puis avec verdict au retry. Assert `llm.calls[1].messages` diffère de `llm.calls[0].messages` (le prompt change). Bite : si la 1ère tentative et le retry utilisent le même prompt, le test mord.
     - `test_llm_anglais_verdict_does_not_match` (Piège 5) : LLM stub retourne `"Good answer.\nVERDICT: SUCCESS"` (anglais) → `TextGradingError("verdict_missing")` après retry.
     - `test_attempt_persisted_with_answer_text` (AC4) : LLM stub `VERDICT: REUSSITE` → `session.add(Attempt(...))` appelé avec `answer_text=<réponse>`, `is_success=True`, `raw_answers=[]`.
     - `test_attempt_raw_answers_is_empty_list` (AC4) : assert `attempt.raw_answers == []`.
   - **TestAttemptNumber (3 tests)** :
     - `test_attempt_number_increments_across_submissions` (AC4) : 3 soumissions successives au même exercise → `attempt_number` 1, 2, 3.
     - `test_attempt_number_is_per_pseudo` (AC4) : 2 élèves soumettent au même exercise → `attempt_number` 1 pour chacun (per-pseudo).
     - `test_attempt_number_is_per_exercise` : 2 exercises différents, 1 élève → `attempt_number` 1 pour chacun (per-exercise).
   - **TestCrossTenant (2 tests, obligatoires)** :
     - `test_cross_tenant_raises_text_grading_error` (AC7) : Alice possède l'exercise, Bob soumet, `TextGradingError("cross_tenant")` levée, `assert llm.calls == []`. Bite critique.
     - `test_cross_tenant_does_not_persist_attempt` (AC7) : idem, `assert added == []` (aucun `Attempt` ajouté en session).
   - **TestInvalidExercise (3 tests)** :
     - `test_qcm_exercise_raises_invalid_exercise_type` (D2.a) : exercise.type=QCM → `TextGradingError("invalid_exercise_type")`, `assert llm.calls == []`. Bite critique.
     - `test_flashcards_exercise_raises_invalid_exercise_type` (D2.b) : exercise.type=FLASHCARDS → `TextGradingError("invalid_exercise_type")`, `assert llm.calls == []`. Bite symétrique.
     - `test_missing_expected_answer_raises_invalid_exercise` (defense-in-depth) : exercise.expected_answer=None → `TextGradingError("invalid_exercise")`.
   - **TestAnswerLength (1 test)** :
     - `test_answer_too_long_raises_before_llm_call` (Piège 3) : `answer="x" * 9000` (> max_answer_chars) → `TextGradingError("answer_too_long")`, `assert llm.calls == []`.
6. [x] **Étendre `backend/tests/cli/test_cli.py`** avec une nouvelle classe `TestSubmitText` (~7 tests) :
   - `_StubTextGrader` (drop-in pour `TextGrader`) + `stubbed_text_grader_service` (monkeypatch de `_build_text_grader_service`).
   - `test_submit_text_returns_zero_with_success` (AC1, AC5) : `is_success=True` → exit 0, sortie JSON `{is_success: true, feedback: "...", attempt_number: 1}`.
   - `test_submit_text_echec_returns_zero_with_is_success_false` (AC1, AC2).
   - `test_submit_text_json_output_is_valid` (AC1).
   - `test_submit_text_cross_tenant_returns_5` (AC7, multi-tenant).
   - `test_submit_text_exercise_not_found_returns_5`.
   - `test_submit_text_verdict_missing_returns_4` (AC3, AC6).
   - `test_submit_text_answer_too_long_returns_2` (D4.a).
   - `test_help_lists_submit_text_command` : sanity check que la commande apparaît dans `--help`.

### Étape 5 — Vérification finale

7. [x] **Lancer la suite de tests complète** : `cd backend && python -m pytest -x -m "not integration"`. Tous les tests existants (≥ 292 après s06b) + ~25 nouveaux doivent passer.
8. [x] **Vérifier la couverture** : `pytest --cov=app --cov-fail-under=80`. Le nouveau module `text_grader.py` doit être couvert ≥ 80%.
9. [x] **Lint** : `ruff check app tests` clean.
10. [x] **Smoke test CLI manuel** (sanity, hors pytest) : `python -m ktutor.cli submit-text --help` affiche la commande et ses options. Le chemin complet de bout en bout (génération + soumission) requiert un vrai LLM et un exercice `probleme`/`redaction` créé via `generate-exercise` (s06) ; il est exercé par les 21 tests unitaires + 10 tests CLI qui mockent le LLM.

### Étape 6 — Commit unique

11. [x] **Un seul commit sur `feature/s07-repondre-texte-libre`** (cf. convention s05, s06, s06b) : `feat(exercises): add LLM-as-judge text grader (s07)`. Le commit inclut :
   - Tous les changements de code (étapes 1-5).
   - Note dans le commit message : « Cette PR complète la boucle de génération-correction pour les exercices libres (s06 produit → s07 grade), sans toucher aux QCM (s03/s04) ni aux flashcards (s06b). Le LLM-as-judge est non-déterministe par nature (cf. `docs/stories.md:288`) ; tous les tests utilisent un stub. Le grader rejette explicitement les exercices de type QCM et FLASHCARDS (D2.a étendue) : les QCM ont leur propre grader binaire, les flashcards sont un outil d'étude non noté. »

## Run interdicts

- **Ne pas modifier `qcm_grader.py` ou `qcm_generator.py`**. Tout le code de s07 est nouveau (`text_grader.py`) ou dans des fichiers étensibles (config, cli, tests). `qcm_grader.py:259-281` est référencé comme **pattern** à dupliquer localement (D9.a), pas à importer.
- **Ne pas modifier `free_generator.py` ou `flashcard_generator.py`**. Aucun rapport avec s07.
- **Ne pas dupliquer `extract_json_block`** : s07 n'utilise pas ce helper (parsing regex direct). Si jamais un import émerge, importer depuis `app.services.exercises._parsing` (mutualisé par s06).
- **Ne pas étendre `Attempt` avec de nouvelles colonnes** : `answer_text` et `correction_level` sont déjà là (s04 et s08). Aucune migration.
- **Ne pas ajouter de dépendance** (`requirements.txt`). Tout le code utilise la stack existante.
- **Ne pas toucher au design system** : la story est purement backend.
- **Ne pas implémenter la correction progressive (s08)**. s07 grade binaire ; s08 orchestrera la progressivité.
- **Ne pas merger dans `main`** : c'est le job de `/ks-ship`. Un commit sur la branche suffit.
- **Ne pas importer `_ScriptedLlm` / `_TrackingSession`** depuis `test_qcm_grader.py` (D8.a : duplication locale, alignée sur la convention s04). Si on importe, le test bite d'isolement devient ambigu.
- **Ne pas accepter un exercise de type QCM** : c'est le travail de `submit_qcm` (s04), pas `submit_text` (s07). Le test bite mord.
- **Ne pas accepter un exercise de type FLASHCARDS** : c'est un outil d'étude, pas un exercice noté (cf. design s06b). Le test bite mord.
- **Ne pas faire de second passage LLM pour valider la cohérence verdict-feedback** (D6.a) : on fait confiance au verdict structuré.
- **Ne pas tronquer silencieusement une réponse trop longue** (D4.a) : on refuse et on explique.

## The point everything turns on

**Le point central** est l'**alignement strict entre la sortie LLM et le verdict parsé** (parsing regex sur `VERDICT:\s*(REUSSITE|ECHEC)`). Trois endroits où cela peut casser :

1. **Le bite test cross-tenant** : si la vérification d'ownership est déplacée **après** l'appel LLM (au lieu d'avant), le test `test_cross_tenant_raises_text_grading_error` devient rouge sur `assert llm.calls == []`. **Comparaison** : le diff de `text_grader.py` doit montrer la vérification d'ownership dans `grade(...)` **avant** tout appel à `self._llm`.

2. **Le bite test invalid_exercise_type** : si la validation `type ∈ {PROBLEME, REDACTION}` est retirée, le test `test_qcm_exercise_raises_invalid_exercise_type` passe au vert alors qu'il devrait lever `invalid_exercise_type`. Le test symétrique `test_flashcards_exercise_raises_invalid_exercise_type` mord si on retire la validation **et** étend la liste acceptée. **Comparaison** : le diff de `text_grader.py` doit montrer une validation explicite `if exercise.type not in {ExerciseType.PROBLEME, ExerciseType.REDACTION}`.

3. **Le bite test retry prompt** : si la 1ère tentative et le retry utilisent le même prompt, le test `test_strict_prompt_used_on_retry` devient rouge sur l'assertion d'inégalité des messages. **Comparaison** : le diff de `text_grader.py` doit montrer deux templates distincts (`_USER_PROMPT_TEMPLATE` vs `_STRICT_USER_PROMPT_TEMPLATE`) et leur utilisation respective dans la boucle retry.

## Files touched

| Fichier | Action | Rôle |
|---|---|---|
| `backend/app/core/config.py` | Étendre (3 lignes) | Bloc `TEXT_GRADER_*` après `FLASHCARDS_*`. |
| `backend/.env.example` | Étendre (3 lignes) | 3 variables `TEXT_GRADER_*` commentées. |
| `backend/app/services/exercises/text_grader.py` | Créer (~250 lignes) | `TextGrader` + regex + prompts + exception typée. |
| `backend/app/cli.py` | Étendre (~80 lignes) | `_build_text_grader_service`, `submit_text`, helpers d'affichage. |
| `backend/tests/services/exercises/test_text_grader.py` | Créer (~500 lignes) | ~20 tests (cf. étape 4). |
| `backend/tests/cli/test_cli.py` | Étendre (~150 lignes) | `TestSubmitText` + `_StubTextGrader` + `stubbed_text_grader_service`. |
| `backend/tests/core/test_config.py` | Étendre (~30 lignes) | `TestTextGraderSettings::test_default_text_grader_settings`. |

**Aucun changement** dans `models.py` (`Attempt` déjà complet), `qcm_grader.py`, `qcm_generator.py`, `free_generator.py`, `flashcard_generator.py`, `_parsing.py`, ou les autres stories.

## Test strategy

**Niveau unitaire** (couche service) : `test_text_grader.py` — 20 tests couvrent toutes les ACs, tous les pièges, et les 7 décisions D1-D9. Les bites d'anti-régression sont explicites : retirer la validation ownership fait passer `llm.calls` de 0 à 1 ; retirer la validation type fait passer `test_qcm_exercise_raises_invalid_exercise_type` au vert ; utiliser le même prompt au retry fait passer `test_strict_prompt_used_on_retry` au rouge.

**Niveau CLI** (couche présentation) : `test_cli.py::TestSubmitText` — 7 tests vérifient que le mapping d'exceptions → exit codes fonctionne (0/2/4/5), et que la sortie JSON contient les 3 champs attendus (AC1, AC5). Pas de duplication des invariants déjà testés en unitaire.

**Niveau settings** : `test_config.py::TestTextGraderSettings` — 1 test assert les 3 valeurs par défaut. Évite qu'un changement de settings casse silencieusement la CLI.

**Pas de test a11y/Lighthouse** (story backend pur).

**Pas de test d'intégration LLM réel** : le LLM-as-judge est non-déterministe par nature (recherche § 4.1). Tous les tests utilisent `_ScriptedLlm`. Un test `@pytest.mark.integration` est best-effort, non bloquant (cf. recherche § 8.5).

**Smoke test manuel** (étape 5.4) : sanity check de bout en bout, hors pytest. Documenté dans le commit message.

## Definition of Done

- Toutes les tâches du plan cochées (11/11).
- `pytest -m "not integration"` passe (≥ 312 tests attendus après ajout de ~25 nouveaux).
- `pytest --cov=app --cov-fail-under=80` passe.
- `ruff check app tests` clean.
- AC1-AC7 tous couverts par des tests unitaires ET des tests CLI.
- **Multi-tenancy** : `test_cross_tenant_raises_text_grading_error` passe, bite vérifié.
- **Bite tests symétriques** : `test_qcm_exercise_raises_invalid_exercise_type` ET `test_flashcards_exercise_raises_invalid_exercise_type` mordent si la validation type est retirée.
- **Bite test retry** : `test_strict_prompt_used_on_retry` mord si le prompt ne change pas au retry.
- **Bite test troncature** : `test_answer_too_long_raises_before_llm_call` mord si la validation n'est pas en amont.
- Smoke test CLI manuel OK (sortie JSON avec les 3 champs).
- Commit unique sur `feature/s07-repondre-texte-libre`, message conventional commit avec note sur le périmètre (s06 produit → s07 grade, pas de QCM ni FLASHCARDS) et la non-déterminisme.
- Review passée (gate `Ship allowed: yes`).
