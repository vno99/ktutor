# Review — s07-repondre-texte-libre

> Revu par : sous-agent `reviewer` (contexte frais).
> Date : 2026-09-01.
> Source : `git diff main...feature/s07-repondre-texte-libre` vs `docs/plans/s07-repondre-texte-libre.md` + `docs/research/s07-repondre-texte-libre.md` + `docs/designs/s07-repondre-texte-libre.md` + ADRs.
> Tests : **327 passed** (run by reviewer) — coverage `text_grader.py` **92%** (target 80%).
> Lint : `ruff check app tests` → **0 errors**.
> Worktree : `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre` (branch `feature/s07-repondre-texte-libre`).

## Test suite + lint

- Ran `cd backend && python -m pytest -x -m "not integration"` myself: **327 passed, 1 warning** (`langchain-community` deprecation, out of scope).
- Ran coverage on `text_grader.py`: 92% (uncovered lines are error paths `invalid_answers` / `storage_failure` no-session / session commit fail / `llm_failure`).
- Ran `cd backend && python -m ruff check app tests` myself: all checks passed.
- Smoke CLI: `python -m ktutor.cli submit-text --help` → exit 0, options `--pseudo`, `--exercise-id`, `--answer`, `--quiet`, `--json` documented.

## Diff vs plan, task by task

| Plan task | Status |
| --- | --- |
| Étape 0 — rebase on main (s05+s06+s06b) | Done. HEAD `17ce736`, base `394d4d4`. |
| Étape 1.1 — extend `config.py` (TEXT_GRADER_*) | Done. Defaults 1, 0.0, 8000. |
| Étape 1.2 — extend `.env.example` | Done. |
| Étape 2 — `text_grader.py` (regex + schemas + prompts + class) | Done. All elements present. |
| Étape 3 — CLI `_build_text_grader_service` + `submit_text` | Done. |
| Étape 4.5 — `test_text_grader.py` (~20 tests) | Done. 21 tests (19 planned + 2 `TestExerciseNotFound`). |
| Étape 4.6 — `test_cli.py::TestSubmitText` (~7 tests) | Done. 10 tests (7 planned + 2 help + `invalid_exercise_type_returns_4`). |
| Étape 5.7 — `test_config.py` (1 test) | Done. 4 tests (1 planned + 3 split per setting). |
| Étape 5.9 — lint clean | Done. |
| Étape 5.10 — smoke CLI | Done. |
| Étape 6.11 — single commit | Done. `17ce736 feat(exercises): add LLM-as-judge text grader (s07)`. |

**Drift identified** (all minor, none breaking):

- Plan § Étape 4.5 says "TestCrossTenant: 2 tests" (`test_cross_tenant_raises_text_grading_error` + `test_cross_tenant_does_not_persist_attempt`). Implementation: **1 test** combining all 3 assertions (`kind`, `llm.calls == []`, `attempts == []`). Consolidates related assertions, bite still bites. **Minor**.
- Plan § Étape 3 says "`invalid_exercise_type` → exit 5". Implementation (aligned with `docs/research/s07...md:81` and `docs/designs/s07...md:96`): exit 4. **Minor** — research and design are the source of truth for this mapping.
- Plan § Étape 4 says "~20 tests" and "≥ 312 tests". Implementation: 35 new tests (327 - 292 main). Floor respected. Extras are targeted and meaningful (TestExerciseNotFound 2, help_works 1, invalid_exercise_type exit 1, 3 config split). **Minor**.

**Run interdicts respected**:
- `qcm_grader.py` / `qcm_generator.py`: untouched.
- `free_generator.py` / `flashcard_generator.py`: untouched.
- `_parsing.py`: untouched.
- `models.py`: untouched (no migration).
- `requirements.txt`: untouched.

## Anti-hallucination

- `from sqlalchemy import func` (text_grader.py:45): top-level import, **fixes** s04 review finding minor #1.
- `from app.services.exercises.text_grader import TextGrader, TextGradingError` (cli.py:65): real import verified.
- `from app.core.database.models import Attempt, Exercise, ExerciseType` (text_grader.py:43): all present in `models.py`.
- `from app.services.llm.client import LlmClient` (text_grader.py:44): Protocol in `client.py:27-34` verified.
- `build_llm_client(settings)` (cli.py:871): function in `client.py:51-79` verified.
- `db_session.init_db()` / `db_session.get_session_factory()` (cli.py:872-873): in `app/core/database/session.py:39, 56`.
- `InvalidPseudoError` (cli.py:67): in `app/services/rag/chroma_store.py:23`.
- `SystemMessage`, `HumanMessage`, `AIMessage` from `langchain_core.messages`: standard.
- Pydantic `Field(min_length=1, max_length=8000)`: correct usage.
- `re.IGNORECASE` on `VERDICT_RE`: confirmed by `test_verdict_extraction_is_case_insensitive`.
- `_next_attempt_number` filters by `Attempt.exercise_id == exercise_uuid` AND `Attempt.student_pseudo == pseudo` (text_grader.py:462-464): confirmed.

## Acceptance criteria verification

| AC | Test | Result |
| --- | --- | --- |
| AC1 (CLI returns is_success/feedback/attempt_number) | `TestSubmitText::test_submit_text_returns_zero_with_success` + `test_submit_text_json_output_is_valid` | Verified |
| AC2 (prompt compare + verdict + feedback) | `TestGrade::test_verdict_reussite_returns_is_success_true` + `test_verdict_echec_returns_is_success_false` + `test_feedback_extracted_before_verdict_line` | Verified |
| AC3 (strict regex, retry 1×) | `TestGrade::test_no_verdict_retries_then_fails` + `test_strict_prompt_used_on_retry` | Verified — bite |
| AC4 (Attempt persisted with answer_text) | `TestGrade::test_attempt_persisted_with_answer_text` + `test_attempt_raw_answers_is_empty_list` | Verified |
| AC5 (stub REUSSITE → true) | `TestGrade::test_verdict_reussite_returns_is_success_true` | Verified |
| AC6 (stub no VERDICT → retry then fail) | `TestGrade::test_no_verdict_retries_then_fails` | Verified — bite |
| AC7 (multi-tenant) | `TestCrossTenant::test_cross_tenant_raises_text_grading_error` | Verified — bite |

## Multi-tenancy invariant

- Ownership check in `TextGrader.grade` (text_grader.py:275) is **before** any LLM call. Bite confirmed: removing the branch makes 1 test go red.
- `Attempt.student_pseudo` is set from the `pseudo` parameter (never from the body/URL).
- `_next_attempt_number` filters by `(exercise_id, student_pseudo)`.
- CLI: `cross_tenant` and `exercise_not_found` produce the same user-facing message (no leak).

## Design conformity

- `TextGradingResult` matches design doc § "Format JSON" (is_success, feedback, attempt_number, attempt_id).
- `kind` → exit code mapping matches design doc § "Erreurs typées" lines 88-97 (the only divergence is the plan line 104 typo, which contradicts the design and the implementation).

## Bite tests neutralized (by reviewer)

1. **Cross-tenant check before LLM** (text_grader.py:275 → `pass`): 1 red (`TestCrossTenant::test_cross_tenant_raises_text_grading_error` fails on `pytest.raises` because no exception is raised, and `llm.calls == []` + `attempts == []` would not have held). Restored, `git diff --exit-code` clean.
2. **Type validation `PROBLEME|REDACTION`** (text_grader.py:285 → `pass`): 2 red symmetric tests (`test_qcm_exercise_raises_invalid_exercise_type` AND `test_flashcards_exercise_raises_invalid_exercise_type`, both fail on `DID NOT RAISE`). Restored, clean.
3. **Different prompt on retry** (text_grader.py:391 → `user = user_soft` always): 1 red (`test_strict_prompt_used_on_retry` — `str(llm.calls[0]) != str(llm.calls[1])` fails because representations are identical). Restored, clean.
4. **`answer_too_long` before LLM** (text_grader.py:235-244, branch removed): 1 red (`test_answer_too_long_raises_before_llm_call` — `exc_info.value.kind == "answer_too_long"` fails, kind becomes `invalid_answers`). Restored, clean.

All 4 central invariants (cross-tenant, type whitelist, retry prompt differentiation, length) are sensitive to their respective guards. Zero red on a neutralized invariant would have been a finding.

## Regressions verified

- `qcm_grader.py` (32 tests): pass. No regression.
- `qcm_generator.py` (16 tests): pass. No regression.
- `free_generator.py` (19 tests): pass. No regression.
- `flashcard_generator.py` (23 tests): pass. No regression.
- `_parsing.py` (mutualized by s06, s06b): untouched, 0 regression.
- Total 327 = 292 (main) + 35 (s07) — clean, no accidental test deletion.

## Conventions repo

- AGENTS.md § Backend: snake_case, PascalCase, kebab-case URLs, typing, Pydantic, structured logging (loguru not used in this module — consistent with qcm_grader.py which also doesn't use loguru). Typed errors with `kind` (cf. QcmGradingError pattern).
- AGENTS.md § Tests: `pytest`, one test per AC, `_ScriptedLlm` stub (no real LLM). `FakeListChatModel` not used, consistent with s04 convention.
- AGENTS.md § Git: single commit `feat(exercises): add LLM-as-judge text grader (s07)`, scope in parentheses respected.
- AGENTS.md § ADR: no new structural decision, no new ADR required. ADR 004 (ChromaDB isolation) and ADR 009 (SeaweedFS) untouched.

## Findings

- **minor** — `docs/plans/s07-repondre-texte-libre.md` line 104 says "`invalid_exercise_type` → exit 5" but the research (line 81) and design (line 96) say 4. The implementation and test follow research/design. No bug, but the validated plan contains an internal inconsistency.
- **minor** — `TestCrossTenant` consolidated to 1 test (instead of 2 planned) combining `kind` + `llm.calls == []` + `attempts == []`. The bite still bites; this is a test design choice. Plan could be updated to reflect the consolidation.
- **minor** — `test_attempt_number_is_per_pseudo`: the test creates a separate exercise for Bob, so Bob doesn't actually submit to Alice's exercise. The test name suggests "per-pseudo" but the invariant exercised is "per-(pseudo, exercise_id)" with distinct exercises. To actually test "per-pseudo on the SAME exercise" would require either mutating `student_pseudo` in DB or crossing tenants (which raises `cross_tenant` before `_next_attempt_number`). The test is valid but the name is slightly misleading.

## Not verified

- **Real LLM end-to-end**: no integration test with a real LLM (consistent with plan, marked `non bloquant` in research § 8.5). A human with `OPENAI_API_KEY` can run `pytest -m integration` to confirm.
- **CLI multi-tenant end-to-end**: CLI tested via `_StubTextGrader`. The real multi-tenant flow is exercised by service tests. A human can smoke: `python -m ktutor.cli submit-text --pseudo bob --exercise-id <ali_exercise_id> --answer "x"` should return exit 5.
- **End-to-end `generate-exercise` (s06) + `submit-text` (s07)**: combined s06 + s07 not tested in integration (out of scope for s07). To exercise manually in dev after both merged.
- **Coverage of uncovered error lines** (245, 258, 356-358, 413-414): error paths `invalid_answers`, `storage_failure` (no session), session commit fail, `llm_failure`. Not tested by convention (s04 also doesn't test these). 92% > 80% threshold.

Max severity: minor
Ship allowed: yes

Fichiers clés (chemins absolus) :
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\services\exercises\text_grader.py`
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\services\exercises\qcm_grader.py` (non modifié, régression évitée)
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\services\exercises\free_generator.py` (non modifié, régression évitée)
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\services\exercises\flashcard_generator.py` (non modifié, régression évitée)
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\core\database\models.py` (non modifié, `Attempt` déjà complet)
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\core\config.py` (settings TEXT_GRADER_*)
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\.env.example` (3 vars TEXT_GRADER_*)
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\app\cli.py` (submit-text + _build_text_grader_service)
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\tests\services\exercises\test_text_grader.py` (21 tests)
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\backend\tests\cli\test_cli.py` (TestSubmitText, 10 tests)
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\docs\plans\s07-repondre-texte-libre.md`
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\docs\research\s07-repondre-texte-libre.md`
- `C:\Workspace\ktutor\.worktrees\s07-repondre-texte-libre\docs\designs\s07-repondre-texte-libre.md`
