# Review — s04-repondre-qcm

> Revu par : sous-agent `reviewer` (contexte frais).
> Date : 2026-08-30
> Source : `git diff origin/main...feature/s04-repondre-qcm` (équivalent `git show 80c427a`) vs `docs/plans/s04-repondre-qcm.md` + `docs/research/s04-repondre-qcm.md` + ADRs 001/002/003/004/005/006/008/009.
> Tests : **189 passés** (lancés par le reviewer) — couverture **86,54%** (seuil 80%).
> Lint : `ruff check app tests` → **0 erreur**.
> Worktree : `C:\Workspace\ktutor\.worktrees\s04-repondre-qcm` (branche `feature/s04-repondre-qcm`).

## Test suite + lint

- Ran `cd backend && pytest --cov=app --cov-fail-under=80 -m "not integration"` myself: 189 passed, coverage 86.54% (well above 80%).
- Ran `cd backend && ruff check app tests` myself: all checks passed.

## Diff vs plan, task by task

| Plan task | Status |
| --- | --- |
| Étape 0 — `Attempt` model | Done. `id` (UUID PK), `exercise_id` (UUID, FK deferred), `student_pseudo` (String(64) indexed), `attempt_number` (int, ge=1), `is_success` (bool), `raw_answers` (list[int] via sqlalchemy.JSON), `submitted_at` (DateTime server_default=now), `answer_text` (String(8192) nullable), `correction_level` (String(32) nullable), `__repr__` for debug. |
| Étape 1 — `QcmGrader` | Done. `QcmGradingError(kind, message)`, `GradingResult(is_success, correct_count, total, feedback, attempt_id)`, `SubmittedAnswers` with `field_validator` (per-element) + `model_validator(mode="after")` (length cross-check), multi-tenant guard via `Exercise.student_pseudo == pseudo`, Pydantic re-validation of `Exercise.questions` via `QcmQuestion.model_validate`, `MAX(attempt_number)` per `(pseudo, exercise_id)`, persistence with try/except + rollback. |
| Étape 2 — CLI `submit_qcm` | Done. `_build_grader_service` factory, JSON parsing with `json.loads`, exit codes 0/1/4/5, `--json` and `--quiet` flags. |
| Étape 3 — `docs/architecture.md` | Done. Confirmed `attempts` schema with portable `sqlalchemy.JSON` and nullable `answer_text`/`correction_level`. |
| Étape 4 — Run, Lint, Manual | Run + Lint done. Manual verification deferred to human (per plan § Task 7). |

**No drift** — the diff stays inside the plan's scope. Run interdicts respected:

- `services/exercises/qcm_generator.py` (s03) untouched.
- `services/rag/retriever.py` (s02/s03) untouched.
- `services/llm/client.py` (s02) untouched.
- `services/agents/maths_agent.py` (s02) untouched.
- `services/rag/chroma_store.py` (s01) untouched.
- `services/rag/upload_service.py` (s01) untouched.
- `MinioClient` and `ChromaStore` names preserved.
- No LLM wired into `QcmGrader`.
- `sqlalchemy.JSON` used (not `JSONB`).
- No Alembic migration created.
- `init_db()` called by `_build_grader_service` (consistent with s03 pattern).

## Acceptance criteria verification

| AC | Test | Result |
| --- | --- | --- |
| AC1 (CLI returns is_success/correct_count/total/feedback) | `test_cli.py::TestSubmitQcm::test_submit_qcm_returns_zero_with_success` | Verified. |
| AC2 (is_success all-or-nothing) | `test_qcm_grader.py::TestGrade::test_perfect_score_returns_is_success_true` + `test_one_wrong_answer_returns_is_success_false` | Verified — bite confirmed. |
| AC3 (attempt persisted with 6 fields) | `test_qcm_grader.py::TestPersistence::test_attempt_persisted_with_all_fields` + `TestAttemptModel::test_create_attempt_with_raw_answers` (covers `submitted_at` directly) | Verified. |
| AC4 (perfect → true, one wrong → false) | Idem AC2 | Verified — bite confirmed. |
| AC5 (attempt_number increments per (pseudo, exercise_id)) | `test_qcm_grader.py::TestAttemptNumber::test_attempt_number_increments_across_submissions` + `test_attempt_number_is_per_pseudo` | Verified — bite confirmed. |
| AC6 (pseudo_a cannot submit pseudo_b's QCM) | `test_qcm_grader.py::TestCrossTenant::test_cross_tenant_raises_grading_error` | Verified — bite confirmed. |

## Multi-tenancy invariant

- `QcmGrader.grade` calls `session.get(Exercise, exercise_uuid)` and then checks `exercise.student_pseudo != pseudo`. Cross-tenant requests raise `QcmGradingError("cross_tenant", ...)` with the same message as not_found (no leak).
- `attempt_number` is per `(pseudo, exercise_id)` via `SELECT MAX(attempt_number) FROM attempts WHERE exercise_id = ? AND student_pseudo = ?`. A separate test (`test_attempt_number_is_per_pseudo`) confirms two pseudos submitting to the same exercise do not share counter.

## Pydantic schema

- `SubmittedAnswers.root: list[int] = Field(min_length=1)` plus per-element `field_validator` for `0 <= x <= 3`.
- `model_validator(mode="after")` cross-checks `len(answers) == len(Exercise.questions)`. The choice of `model_validator` over a second `field_validator` is correct: in Pydantic v2 the order of multiple `field_validator`s on the same field is not guaranteed, and `expected_length` may not be populated when a sibling field validator runs.
- `Exercise.questions` is re-validated via `QcmQuestion.model_validate(d)` for each dict — defense-in-depth per Q2.

## Persistence

- `session.add(Attempt(id=uuid.uuid4(), exercise_id=exercise_uuid, student_pseudo=pseudo, attempt_number=N, is_success=is_success, raw_answers=raw_answers))` followed by `session.commit()`. Wrapped in try/except with rollback. Verified via `_TrackingSession` wrapper.

## Mutation testing (bites I neutralized)

1. **AC2/AC4 (is_success all-or-nothing)** — neutralized to `is_success = True` in `QcmGrader.grade`. 2 tests went red: `test_one_wrong_answer_returns_is_success_false` (the named bite) and `test_feedback_differs_per_outcome` (related assertion). Restored clean.
2. **AC5 (attempt_number via MAX)** — neutralized to `attempt_number = 1` (in-memory counter). 2 tests went red: `test_attempt_number_increments_across_submissions` and `test_attempt_number_is_per_pseudo`. Restored clean.
3. **AC6 (cross-tenant)** — removed the `if exercise.student_pseudo != pseudo` check. 1 test went red: `test_cross_tenant_raises_grading_error`. Restored clean.

All three central invariants are test-protected and the bites bite. The cross-tenant test at the agent layer is meaningful (it uses a real `_TrackingSession` + a real `Exercise` row seeded with a different `student_pseudo`).

## Test quality

The tests are not decorative. They:

- Use real SQLite in-memory (via `Base.metadata.create_all` and `_TrackingSession`) to verify the model persists and the grader's `session.add(Attempt(...))` is called.
- Use `QcmQuestion.model_validate` in the grader (defense-in-depth) to ensure malformed data in the DB triggers a clean error rather than a crash.
- Script cross-tenant at the agent layer with a real session, asserting the LLM is never invoked.
- `test_attempt_number_is_per_pseudo` adds a second witness for the AC5 invariant (per-pseudo counter) at no extra cost.

## Findings

#### critical

None.

#### major

None.

#### minor

1. **`from sqlalchemy import func` is inside `_next_attempt_number`** (lazy import). Convention would put it at top of file. Not a defect.

2. **The grader test `test_attempt_persisted_with_all_fields` does not directly assert `submitted_at`**. AC3's 6th field (`submitted_at`) is covered by `TestAttemptModel::test_create_attempt_with_raw_answers` (model test) but not directly by the grader test. Minor coverage gap.

3. **The CLI catches `Exception` broadly** in `_build_grader_service` and the final fallback (`except Exception as exc:`). Same pattern as s03, not new. Cosmetic.

## What I could NOT verify

- **Manual end-to-end flow** — s03 generate → s04 submit twice → s04 submit with bad pseudo. A human should run this to confirm exit codes and persistence.
- **No browser/UI evidence** — this is a backend story, no UI to render.
- **No Postgres verification** — the model is exercised on SQLite in-memory. `init_db()` is called in `_build_grader_service`, but no test confirms the table is created in a real Postgres. The plan acknowledges this and defers to s15 (Alembic migration).
- **Real LLM in `QcmGrader`** — forbidden by run-interdict, so nothing to verify. The implementation is 100% deterministic (no `LlmClient` import in `qcm_grader.py`).

## Final

The story is ready to ship. The implementation is clean, the multi-tenant invariant is locked, the all-or-nothing grading is enforced, the attempt_number is per-(pseudo, exercise_id) via MAX, the run interdicts are respected, the tests bite where they need to bite, and the coverage threshold is met.

Max severity: minor
Ship allowed: yes
