# Review — s08-correction-progressive (FIX RUN)

> Revu par : sous-agent `reviewer` (contexte frais).
> Date : 2026-09-01.
> Source : commit `89a2535` (fix) sur top de `6c73641` (feat) + `de63b18` (doc tick). Story diff = `git diff main...feature/s08-correction-progressive`.
> Previous review : `docs/reviews/s08-correction-progressive.md` (version précédente, jugée `Ship allowed: no` à cause d'un critical).
> Tests : **368 passed** (run by reviewer, +1 vs baseline 367).
> Lint : `ruff check app/services/correction tests/services/correction tests/cli/test_cli.py` → **0 errors**.
> Worktree : `C:\Workspace\ktutor\.worktrees\s08-correction-progressive` (branch `feature/s08-correction-progressive`).

## Verdict

**Ship allowed.** Le critical finding de la review précédente est résolu : le service appelle maintenant `HintGenerator.generate_hints(context)` avec un unique `HintContext` construit à partir de l'exercice (statement, exercise_type, attempt_number, feedback, grading_criteria, questions). Le nouveau test `TestRealHintGeneratorIntegration::test_real_hint_generator_returns_hints_for_partial` instancie le vrai `HintGenerator` dans le vrai service et échoue avec `TypeError: ... takes 2 positional arguments but 4 were given` si on restaure l'ancienne signature — la régression est mordante. Les trois minor findings (UUID leak, bare except, double session_factory) sont aussi résolus.

## Test suite + lint

- Ran `cd backend && python -m pytest` myself: **368 passed, 1 warning** (deprecation `langchain-community`, hors-scope).
- Sub-suite counts (post-fix) :
  - `tests/services/correction/test_progressive.py` — 25 tests (+1 vs 24).
  - `tests/services/correction/test_hints.py` — 6 tests.
  - `tests/cli/test_cli.py::TestSubmitQcmProgressive` + `TestSubmitTextProgressive` — 8 tests.
  - `tests/core/test_config.py::TestProgressiveCorrectionSettings` — 2 tests.
  - Total new s08 tests: **41** (40 baseline + 1 new integration test).
- Re-ran `qcm_grader` + `text_grader` (s04 + s07 surface) : **37 passed**, aucune régression.

## CRITICAL finding — fixed

**Old critical** : `ProgressiveCorrectionService.evaluate()` appelait `self._hint_generator.generate_hints(exercise, attempt_number, feedback)` (3 args positionnels) mais la vraie signature de `HintGenerator.generate_hints` est `generate_hints(self, context: HintContext)` (1 arg). Production crashait sur tout `submit-qcm` / `submit-text` réel qui aboutissait à `partial` ou `partial_attempt_2`.

**Fix (commit `89a2535`, `progressive.py:299-326`)** : le service construit désormais un `HintContext` à partir de l'exercice et appelle `self._hint_generator.generate_hints(context)` avec un unique argument. Le mapping est :
- `statement` ← `exercise.statement or ""`
- `exercise_type` ← `exercise.type` (un `ExerciseType`)
- `attempt_number` ← `attempt_number` local
- `feedback` ← `feedback` du grade_callback
- `grading_criteria` ← liste normalisée (list → list[str], dict → list[str] des valeurs, sinon `None`)
- `questions` ← `[dict(q) for q in exercise.questions]` ou `None` si vide

Le `from app.services.correction.hints import HintContext` est local à la branche `if correction_level in ("partial", "partial_attempt_2")` : pas d'import inutile sur le chemin `full` / `full_after_attempts`.

**Bite test (commit `89a2535`, `test_progressive.py:707-759`)** : la nouvelle classe `TestRealHintGeneratorIntegration::test_real_hint_generator_returns_hints_for_partial` instancie un vrai `HintGenerator` (avec un stub `_ScriptedLlm` qui renvoie du JSON bien formé) et le passe au vrai `ProgressiveCorrectionService`. Elle vérifie `result.correction_level == "partial"`, `result.hints == ["relis la definition de la derivee"]`, `result.next_steps == "consulte la section 3.2 du cours"` et `len(llm.calls) == 1`.

J'ai **vérifié moi-même** que la bite mord : en restaurant temporairement le code buggy (3 args positionnels), ce test tombe en rouge exactement avec :
```
TypeError: HintGenerator.generate_hints() takes 2 positional arguments but 4 were given
```
Après restauration du fix, le test repasse. `git diff --exit-code` est propre sur le fichier.

**Stub de test mis à jour** : `_RecordingHintGenerator` dans `test_progressive.py:196-208` utilise maintenant la bonne signature `generate_hints(self, context: HintContext)`. Les assertions correspondantes (lignes 338-340 et 367-369) vérifient que `hints.calls[0].attempt_number` et `hints.calls[0].feedback` portent les bons champs — une régression sur la construction du `HintContext` casserait ces assertions.

## 3 minor findings — all fixed

| Finding | Fix | Verification |
| --- | --- | --- |
| UUID leak (malformed path echoait l'input) | `progressive.py:215-221` : message générique `f"Exercise {pseudo!r} introuvable."` pour malformed-UUID **et** not-found. Le raw input `exercise_id` n'apparaît plus. | Test `test_malformed_uuid_raises_not_found` passe. Vérification manuelle : `service.evaluate('ali', 'not-a-uuid-secret-input', grader)` → `msg: "Exercise 'ali' introuvable."` (pas d'écho de `'not-a-uuid-secret-input'`). |
| Bare `except` dans `hints.py` | `hints.py:153-167` : `logger.warning("hint_generator.llm_failure attempt={} error={!r}", i + 1, exc)` avant `continue`. Plus de `_ = exc`. | Vérification manuelle : injection d'une `ConnectionError` dans le LLM stub → log structuré `hint_generator.llm_failure attempt=1 error=ConnectionError('boom from upstream')` + retour du fallback déterministe `('Relis le cours lie a cet exercice et reessaye.', 'Consulte tes notes et reessaye demain.')`. |
| Double `session_factory()` call | `progressive.py:231-233` capture `session` une fois. `progressive.py:339` réutilise ce `session` au lieu de rappeler `self._session_factory()`. | Code review confirme : `session` est alloué à la ligne 233, et la branche persistance lit `if session is not None:` sans rappeler la factory. La lecture et l'écriture sont maintenant dans une même transaction. |

## Re-verify 5 previous bite mutations (post-fix)

J'ai relancé les 5 mutations de la review précédente et toutes mordent toujours après le fix. Chaque mutation a été neutralisée, les tests cibles observés en rouge, puis la mutation a été restaurée et `git diff --exit-code` était propre.

| Mutation | Test(s) qui devraient passer au rouge | Rouge observé | Bite |
| --- | --- | --- | --- |
| Remove cross-tenant guard (`if False and exercise.student_pseudo != pseudo`) | `TestCrossTenant::test_foreign_exercise_raises_cross_tenant` | 1 red (`Failed: DID NOT RAISE ProgressiveCorrectionError`) | yes |
| Remove closed gate (`if False:`) | `test_service_does_not_call_grade_callback_when_closed` | 1 red (`grader.calls` non vide) | yes |
| `partial_attempt_2` → `partial` | `test_valid_transition[2-False-partial_attempt_2]` + `test_partial_attempt_2_is_distinct_from_partial` + `test_service_evaluates_second_attempt_failure_with_partial_attempt_2` | 3 red | yes |
| Drop `attempt_number == 1` from `bonus_points` (D6) | `test_service_evaluates_late_success_with_full_no_bonus` | 1 red (`assert 2 == 0`) | yes |
| Add `FLASHCARDS` to `_PROGRESSIVE_TYPES` (D10) | `test_flashcards_exercise_raises_invalid_exercise` | 1 red (`Failed: DID NOT RAISE ProgressiveCorrectionError`) | yes |

J'ai aussi re-muté `self._hint_generator.generate_hints(exercise, attempt_number, feedback)` en restaurant la signature buggée, et la nouvelle bite `TestRealHintGeneratorIntegration::test_real_hint_generator_returns_hints_for_partial` est tombée en rouge avec le `TypeError` exact. Le filet est tendu.

## Anti-hallucination

- `HintContext(statement, exercise_type, attempt_number, feedback, grading_criteria, questions)` — vérifié dans `hints.py:104-113`. Tous les 6 champs sont bien alimentés.
- `HintGenerator.generate_hints(self, context: HintContext) -> tuple[list[str], str]` — vérifié dans `hints.py:138-140`. Le service appelle bien cette signature (et **seulement** celle-ci) post-fix.
- `_PROGRESSIVE_TYPES` exclut toujours `FLASHCARDS` (D10) — `progressive.py:150-152`.
- `bonus_points = 2 if is_success and attempt_number == 1 else 0` (D6) — `progressive.py:293`.
- `next_correction_level(attempt_number, is_success, max_attempts=3)` reste une fonction pure — table de vérité AC inchangée.
- Le service **n'écrit toujours pas** dans `reward_ledger` — s20 consommera `bonus_points` plus tard.
- `CorrectionResult` Pydantic avec les champs planifiés — `progressive.py:75-88`.
- `_SessionLike` Protocol inchangé.
- Le message `closed` reste le même ; le message `cross_tenant` reste le même ; le message `invalid_exercise` reste le même ; le message `exercise_not_found` (not_found) reste le même — seul le message de la branche malformed-UUID a été nettoyé.

## Plan compliance

- Étape 0 : rebase sur main (s05+s06+s06b+s07) — déjà fait en feat commit.
- Étape 1.1-1.2 : `max_correction_attempts` Settings + `.env.example` — déjà fait.
- Étape 2 : state machine, service, schemas, hint generator — fait. La seule dérive de la version précédente (signature de `generate_hints`) est corrigée.
- Étape 3 : CLI `_build_progressive_service` + `submit_qcm` + `submit_text` + `EXIT_PROGRESSIVE_CLOSED = 6` — fait.
- Étape 4 : tests progressifs (25 dans `test_progressive.py`, 6 dans `test_hints.py`, 8 CLI, 2 config) — **41 tests**, +1 vs baseline 40.
- Étape 5 : `pytest` clean, `ruff` clean.
- Étape 6 : commit unique feat (avec un trivial doc-tick pour la checkbox). Le fix commit `89a2535` est séparé, formaté `fix(correction): ...` — conforme à `AGENTS.md` § Git et PR.

Note : le plan lui-même, ligne 92, documentait la mauvaise signature `(exercise, attempt_number, feedback)`. La recherche (ligne 295) et le design donnaient la bonne `generate_hints(context)`. Le fix commit s'aligne sur la recherche/le design, ce qui est la bonne décision. Pas d'ADR nécessaire (cohérent avec D2 et la recherche déjà validée).

## Git conventions

- Conventional commit : `fix(correction): wire ProgressiveCorrectionService to HintGenerator via HintContext` — scope entre parenthèses, verbe à l'infinitif, message technique clair.
- Commit sur `feature/s08-correction-progressive` (pas sur la branche par défaut).
- Pas de scope inventé (`fix(correction)` est le bon domaine).
- Body du commit documente le bug, le fix, et les 3 minor findings (3 fichiers touchés, 3 problèmes résolus).

## Tests

- Test suite run par le reviewer : **368/368 passed**.
- Tous les 25 tests de `test_progressive.py` passent.
- La bite `TestRealHintGeneratorIntegration` mord quand on restaure la signature buggée (vérifié 2 fois : avant et après la mutation).
- 5 mutations de la review précédente mordent toujours (cross-tenant, closed, partial_attempt_2, bonus_points, FLASHCARDS).
- Aucun test décoratif / dupliqué ajouté. Le nouveau test fait un bout-en-bout réel (vrai `HintGenerator`, vrai service, vrai `CorrectionResult`).

## Regressions

- `qcm_grader.py`, `text_grader.py`, `qcm_generator.py`, `free_generator.py`, `flashcard_generator.py`, `_parsing.py`, `models.py`, `llm/client.py`, `agents/*`, `rag/*`, `storage/*` — tous **inchangés** (le diff story ne montre que 14 fichiers, aucun dans la liste s04/s07).
- Les 37 tests s04+s07 passent toujours.
- `cli.py` diff ne touche que les zones s08 (extension de `submit-qcm` / `submit-text` + `_build_progressive_service`).

## Findings

Aucun finding nouveau. Le fix commit `89a2535` est propre.

| Sev | File | Issue |
| --- | --- | --- |
| — | — | Aucun — la review précédente a été intégralement résolue. |

## Not verified

- **Manual smoke test** (plan § Étape 5 task 12) : je n'ai pas lancé le vrai `python -m ktutor.cli submit-qcm` avec un vrai LLM. **Mais** : (1) j'ai exécuté un smoke test programmatique équivalent (vrai `HintGenerator` + vrai `ProgressiveCorrectionService` + stub LLM renvoyant du JSON) et il retourne `correction_level=partial`, `hints=['hint1']`, `next_steps='step1'`, `llm_calls=1`. (2) Le nouveau test bite-mordant couvre exactement ce chemin. Un humain peut faire le test CLI final, mais le risque résiduel est marginal.
- **Coverage threshold** : le plan demande `pytest --cov=app --cov-fail-under=80`. Je n'ai pas lancé avec coverage. À vérifier localement.
- **Real OpenRouter call** : le fallback LLM n'a pas été testé avec un vrai provider. Le test bite-mordant utilise un stub JSON bien formé. Un humain devrait lancer avec `LLM_PROVIDER=minimax` et confirmer que la chaîne bout-en-bout renvoie des hints non-vides pour un QCM raté.

## Verdict final

Le critical de la review précédente est **mordant-empêché** par le nouveau test d'intégration. Les 3 minors sont nettoyés. Les 5 bites précédentes tiennent toujours. Lint clean. 368/368 tests verts. Pas de régression sur le code s04/s07 ou la production-grade shipped. Conventional commit. Ship.

Max severity: none
Ship allowed: yes

Fichiers clés (chemins absolus) :
- `C:\Workspace\ktutor\.worktrees\s08-correction-progressive\backend\app\services\correction\progressive.py` (fix lignes 215-221, 231-233, 299-326, 339)
- `C:\Workspace\ktutor\.worktrees\s08-correction-progressive\backend\app\services\correction\hints.py` (fix lignes 30, 153-167)
- `C:\Workspace\ktutor\.worktrees\s08-correction-progressive\backend\tests\services\correction\test_progressive.py` (fix stub lignes 196-208, bite test lignes 707-759)
- `C:\Workspace\ktutor\.worktrees\s08-correction-progressive\docs\plans\s08-correction-progressive.md` (note : le plan lui-même, ligne 92, documentait la mauvaise signature)
- `C:\Workspace\ktutor\.worktrees\s08-correction-progressive\docs\research\s08-correction-progressive.md`
- `C:\Workspace\ktutor\.worktrees\s08-correction-progressive\docs\designs\s08-correction-progressive.md`
