---
validated: yes
---
# Plan — Story s18b-evaluation-actions-admin

Branch: `feature/s18b-evaluation-actions-admin`
Research: `docs/research/s18b-evaluation-actions-admin.md` — read it first; this plan does not repeat it.

## Target story

`docs/stories.md:906-942` — **s18b — Saisir ou relancer l'extraction du score d'une évaluation.**

As an admin (ou un parent lié) I want saisir manuellement le score d'une copie en `manual_review_needed` (ou relancer l'extraction LLM) so that les copies sans score détecté alimentent les dashboards.

### Acceptance criteria (verbatim)

- AC1. `POST /api/evaluations/{id}/score-manual` (admin or linked parent, JWT) accepte `{score, max_score, teacher_comments?}` et met à jour la ligne `Evaluation`. Retourne 200 avec l'évaluation mise à jour.
- AC2. L'endpoint valide que l'évaluation est en `manual_review_needed` ; sinon retourne 409.
- AC3. Un appelant non-admin, non-parent lié obtient 403.
- AC4. `POST /api/evaluations/{id}/reprocess` (admin only, JWT) ré-invoque l'extracteur LLM sur l'image originale. Retourne 200 avec le nouveau résultat (ou `manual_review_needed`).
- AC5. Les deux endpoints passent le statut à `scored` en cas de succès, ou laissent `manual_review_needed` en cas d'échec.
- AC6. Test : admin peut scorer manuellement une copie en `manual_review_needed`.
- AC7. Test : non-admin, non-parent obtient 403.
- AC8. Test : parent ne peut pas scorer une évaluation d'un enfant non lié.

## Tasks (ordered)

1. [x] **T1 — Extend `app/api/evaluations/schemas.py` with the request/response shapes.**
   - `ScoreManualRequest` (Pydantic BaseModel) : `score: float = Field(ge=0)`, `max_score: float = Field(ge=0)`, `teacher_comments: str | None = Field(default=None, max_length=8192)`. Cross-field validator `score ≤ max_score` (returns 422 on violation — Piège 1).
   - `ScoreManualResponse` (mirror of `UploadResponse`, minus `ocr_confidence`) : `evaluation_id: UUID`, `status: Literal["scored", "manual_review_needed"]`, `score: float | None`, `max_score: float | None`, `teacher_comments: str | None`, `updated_at: datetime` (read off the row).
   - `ReprocessResponse` (same shape as `ScoreManualResponse` plus `ocr_confidence: float | None` and `source: Literal["regex","llm","none"]` carried from `ExtractionResult`).
   - `EvaluationStateErrorResponse` (Pydantic) : `error: str`, `code: Literal["state_conflict", "not_found"]`.
   - **Failing test first** : `tests/api/test_evaluations.py::test_score_manual_request_rejects_negative_score`, `::test_score_manual_request_rejects_score_greater_than_max`, `::test_score_manual_request_teacher_comments_too_long` (Pydantic-level, no HTTP).

2. [x] **T2 — Extend `EvaluationService` with `score_manual` and `reprocess`, plus a new `EvaluationStateError`.**
   - In `backend/app/services/ocr/evaluation_extractor.py` :
     - Add `class EvaluationStateError(Exception)` (no enum — the kind is the 409 itself).
     - Add `EvaluationService.score_manual(*, evaluation_id, score, max_score, teacher_comments) -> Evaluation`. Behavior: load row by id → 404-equivalent (`EvaluationStateError("not_found")`) if absent → 409 if `status is not MANUAL_REVIEW_NEEDED` → apply UPDATE (status=SCORED, score, max_score, teacher_comments) via the existing `session_factory` → return refreshed row.
     - Add `EvaluationService.reprocess(*, evaluation_id) -> tuple[Evaluation, ExtractionResult]`. Behavior: load row → 404 if absent → 409 if `status is SCORED` (re-scorer une copie déjà scorée n'a pas de sens — recherche Piège 4) → download via `self._s3.get_object(s3_key)` → write tempfile (`tempfile.NamedTemporaryFile(delete=False)`, suffix from `row.filename`) → call `self._extractor.extract(tmp_path)` in a try/finally that unlinks the tempfile → build a new `status` (SCORED if new score else MANUAL_REVIEW_NEEDED), update the row, log `evaluation.reprocess_attempted` with `previous_status`, `new_status`, `new_score`, `pseudo` (no body) → return `(row, result)`.
     - Extend `__all__` with the new symbols.
   - **Failing tests first (service-level, no HTTP)** :
     - `tests/services/ocr/test_evaluation_extractor.py::test_score_manual_persists_score_and_status_scored` (TDD: stub session_factory, build an `Evaluation` in MANUAL_REVIEW_NEEDED, call service, assert UPDATE + status flipped).
     - `::test_score_manual_raises_state_error_when_status_not_manual_review_needed` (status=SCORED → EvaluationStateError).
     - `::test_score_manual_raises_state_error_when_evaluation_missing` (404-like).
     - `::test_reprocess_extracts_and_updates_to_scored` (inject `_OcrStub` returning `"12/20"` text; assert row now SCORED with score=12, max_score=20).
     - `::test_reprocess_leaves_manual_review_needed_on_no_score` (stub returns empty text; row stays MANUAL_REVIEW_NEEDED, ocr_text persisted).
     - `::test_reprocess_raises_state_error_when_already_scored` (status=SCORED → EvaluationStateError).

3. [x] **T3 — Extend the router with the two endpoints + RBAC + 409 mapping.**
   - In `backend/app/api/evaluations/router.py` :
     - `POST /api/evaluations/{evaluation_id}/score-manual` (`response_model=ScoreManualResponse`, `responses={403, 404, 409, 422}`). RBAC gate (custom — do NOT call the lax parent helper directly, see T4) : if `user.role is ADMIN` → proceed; elif `user.role is PARENT` → load the row first, then `assert_parent_linked_to_child_or_403(user, row.student_pseudo, route=..., db=db)`; else 403. Calls `service.score_manual(...)` in a try/except, maps `EvaluationStateError` to 409 (status_conflict) or 404 (not_found) based on substring match in the message (mirror of the `documents/router.py` size-vs-extension trick).
     - `POST /api/evaluations/{evaluation_id}/reprocess` (`response_model=ReprocessResponse`, `responses={403, 404, 409, 500, 503}`). RBAC : `Depends(require_role(UserRole.ADMIN))`. Calls `service.reprocess(...)`; same `EvaluationStateError` → 409/404 mapping.
     - Replace `_status_for_evaluation_error` with a single mapping table `{EvaluationErrorKind → int}` plus a sibling for `EvaluationStateError` to keep the function small (Piège 8).
     - Add DB dependency: the existing `get_db` from `app.core.database.session`. Pulled into the router via `Depends(get_db)`.
   - **Failing tests first (HTTP-level, `tests/api/test_evaluations.py`)** :
     - `::test_score_manual_admin_updates_to_scored` (AC1 + AC6) — seed `seeded_admin` + a MANUAL_REVIEW_NEEDED row for alice; POST `{score: 12, max_score: 20}`; assert 200, body shape, and DB row.
     - `::test_score_manual_returns_409_when_already_scored` (AC2) — seed a SCORED row; assert 409 + `code: "state_conflict"`.
     - `::test_reprocess_admin_extracts_and_updates` (AC4) — seed a MANUAL_REVIEW_NEEDED row + S3 fake + `_OcrStub` returning a score; POST; assert 200, row SCORED.
     - `::test_reprocess_leaves_manual_review_needed_on_ocr_failure` (AC5 second branch) — stub returns no score; assert 200 + `status: "manual_review_needed"`.

4. [x] **T4 — RBAC strict + cross-tenant bite (AC3, AC7, AC8 + Piège 2 + Piège 5).**
   - The router's RBAC must reject:
     - `eleve` with 403 (even on its own evaluation) — Piège 5.
     - `parent` calling on an evaluation of a non-linked child — AC8 / Piège 2.
     - `parent` calling on an evaluation of a **linked** child → 200.
     - `admin` → 200.
   - **Failing tests first** :
     - `::test_score_manual_eleve_cannot_score_own_evaluation` (Piège 5, complements AC7) — seed `seeded_eleve_alice` + a MANUAL_REVIEW_NEEDED row for alice; POST with alice's JWT; assert 403, no DB mutation.
     - `::test_score_manual_parent_of_linked_child_succeeds` (Piège 2 success branch) — seed `seeded_parent`, `seeded_eleve_alice`, link them, seed a MANUAL_REVIEW_NEEDED row for alice; POST with parent's JWT; assert 200.
     - `::test_score_manual_parent_of_unlinked_child_returns_403` (AC8) — seed `seeded_parent`, `seeded_eleve_alice` (linked), `seeded_eleve_bob` (not linked), seed a MANUAL_REVIEW_NEEDED row for bob; POST with parent's JWT; assert 403.
     - `::test_reprocess_eleve_returns_403` (AC4's "admin only" baked in) — eleve JWT → 403.
   - All test names are bit-tests : a regression that flips the RBAC order (e.g. lets any authenticated user through) breaks at least one of these.

5. [x] **T5 — Audit logging.**
   - `security.evaluation_manual_score` (info) emitted on a successful `score-manual` with `caller`, `evaluation_id`, `new_score`, `new_max_score` — no body, no token, no `teacher_comments` (Pydantic-serialized value of the new comment is **never** in the log line; per the agentic note about audit and per `AGENTS.md § Backend logging`).
   - `evaluation.reprocess_attempted` (info) emitted on every `reprocess` call (success or no-score) with `caller`, `evaluation_id`, `previous_status`, `new_status`, `new_score`. **No** S3 bytes, no `ocr_text`, no `teacher_comments` in the log line.
   - **Failing tests first** : `tests/api/test_evaluations.py::test_score_manual_emits_audit_log` (use `loguru` test handler or `caplog`-equivalent — verify the `caller` and `evaluation_id` fields, assert the absence of `teacher_comments`), `::test_reprocess_emits_audit_log` (same shape).

6. [x] **T6 — Record ADR 014.**
   - `docs/decisions/014-evaluation-admin-and-parent-actions.md` (MADR format). Records:
     - Decision 1 : RBAC pattern for `score-manual` is **admin-OR-linked-parent** (not "admin OR any parent"). Helper `assert_parent_linked_to_child_or_403` after row load.
     - Decision 2 : `EvaluationStateError` is a **separate exception class**, not a 4th value of `EvaluationErrorKind` (the latter stays upload-specific).
     - Decision 3 : `reprocess` returns 409 on a row already `SCORED` (no re-extraction of an already-scored copy in s18b).
     - Decision 4 : no history column is added; the audit trail lives in `loguru` only (desamorce Piège 3).
   - Considered options for Decision 1 (admin-only, no parent exception / open-to-all-parents / RBAC matrix) — at least 2 rejected with reasons.

7. [x] **T7 — Single commit on the feature branch.**
   - `git add` the changes; one commit `feat(api): add /api/evaluations/{id}/score-manual and /reprocess admin endpoints (s18b)`. Carries the story docs (research + plan + ADR) and every task — never one commit per task.
   - `docs/stories.md` is **not** edited (research already overrode AC1's drift on s18, no new drift here).
   - One final test pass (`pytest backend/tests`) and one `ruff check` from inside the worktree before commit.

## Run interdicts

- **Do NOT add a new Alembic migration.** The `Evaluation` model is unchanged (s18). `init_db()` already creates the table.
- **Do NOT touch `MultimodalOcr` or `OcrResult`.** s18 already extended them with the optional `prompt` and `raw` fields. Reusing them as-is is the whole point of s18b's reprocess.
- **Do NOT extend `EvaluationErrorKind` with a 4th value.** The 409 lives in `EvaluationStateError`. The mapping table in the router handles both.
- **Do NOT add a `previous_*` history column to the `Evaluation` model.** Piège 3 desamored by logs.
- **Do NOT add a `GET /api/evaluations/{id}` endpoint.** Out of scope (s19/s20 territory). The `score-manual` response carries the updated row, so the client doesn't need a follow-up GET.
- **Do NOT allow `eleve` to call `score-manual` on its own evaluation.** Piège 5. RBAC strict — no lax `claimed == user.pseudo` shortcut.
- **Do NOT allow `reprocess` to mutate a `SCORED` row.** Returns 409. The re-extraction workflow is reserved for `MANUAL_REVIEW_NEEDED`.
- **Do NOT log the `teacher_comments` value, the OCR text, the image bytes, the JWT, or any PII in any new log line.** Audit log carries `caller`, `evaluation_id`, score fields only.
- **Do NOT split the router into `score_manual.py` + `reprocess.py`.** The repo convention is one `router.py` per sub-domain (cf. `documents/router.py`, `users/router.py`). The agentic notes' file list was a hint, not a mandate. **This is a planner decision recorded in this plan; the implementer must respect it.**
- **Do NOT edit `docs/stories.md`.** The AC text is preserved as-is; any drift is documented in the research.
- **No Celery, no async streaming, no frontend.** Pure backend CRUD.

## The point everything turns on

The single decision this plan stands on is the **RBAC pattern for `score-manual`** (T4). It is the place the plan hesitated the most. The choice is : route the parent's `score-manual` call through `assert_parent_linked_to_child_or_403` **after loading the row** (so the helper sees the row's `student_pseudo`, not anything from the URL/body). The wrong alternatives, and how to spot them :

- **Loading the row but bypassing the helper** → fails AC8. A regression here breaks `test_score_manual_parent_of_unlinked_child_returns_403`.
- **Calling the helper with the URL path `evaluation_id` as `claimed`** → fails because `evaluation_id` is a UUID, not a pseudo. The helper compares pseudo strings.
- **Letting any authenticated user through because they "own" the evaluation (a paranoid "row.student_pseudo == user.pseudo" shortcut)** → fails Piège 5. `test_score_manual_eleve_cannot_score_own_evaluation` catches it.
- **Admin bypassing the link check by accident** → also correct (ADR 005 § RBAC : admin impersonation is allowed). The helper itself short-circuits on `user.role is UserRole.ADMIN`, so calling it is the right thing — do not duplicate the bypass.

The secondary point is the **`reprocess`-on-`SCORED` returns 409** choice (research open question 3). If the implementer flips this to allow re-extraction, they must also flip the test `::test_reprocess_raises_state_error_when_already_scored` and add the audit log note. A reviewer should ask : "Is there a concrete use case for re-extracting a scored copy today?" If no, 409 is the right answer.

## Files touched

**Modified** :
- `backend/app/api/evaluations/schemas.py` — add `ScoreManualRequest`, `ScoreManualResponse`, `ReprocessResponse`, `EvaluationStateErrorResponse` (T1).
- `backend/app/services/ocr/evaluation_extractor.py` — add `EvaluationStateError`, `EvaluationService.score_manual`, `EvaluationService.reprocess`; extend `__all__` (T2).
- `backend/app/api/evaluations/router.py` — add two endpoints, RBAC gates, 409 mapping, DB dependency, `get_current_user` import is already present (T3 + T4 + T5).
- `tests/api/test_evaluations.py` — extend the s18 suite with T1/T3/T4/T5 tests.
- `tests/services/ocr/test_evaluation_extractor.py` — extend the s18 suite with T2 service-level tests.

**Created** :
- `docs/decisions/014-evaluation-admin-and-parent-actions.md` (T6).

**Unchanged** (verified by `git diff` in T7) :
- `backend/app/core/database/models.py` (no model change, no migration).
- `backend/app/main.py` (no new include_router — both endpoints attach to the existing `evaluations_router`).
- `backend/app/api/evaluations/factory.py` (no new DI: the new service methods reuse `s3_client`, `extractor`, `session_factory` already wired by `build_evaluation_service`).
- `docs/stories.md` (per research override pattern).

## Test strategy

| Layer | Tests | Where | What they prove |
| --- | --- | --- | --- |
| Pydantic schema | 3 (T1) | `tests/api/test_evaluations.py` | `ScoreManualRequest` rejects negative score, score > max_score, oversized comments. |
| Service unit | 6 (T2) | `tests/services/ocr/test_evaluation_extractor.py` | `score_manual` and `reprocess` happy paths + 409 + 404 + no-score leaves MANUAL_REVIEW_NEEDED. |
| API integration | 11 (T3 + T4 + T5) | `tests/api/test_evaluations.py` | End-to-end: status codes, response bodies, RBAC across 4 caller types, audit log shape, AC1-AC8 all bit-tested. |
| Lint / type | 1 | `ruff check backend/ tests/` | No F401 / I001 / RUF022 regressions. |

**Total new tests** : 20 (3 schema + 6 service + 11 API). All named after the AC or Piège they pin.

**Bite-defence tests** (intentionally not in the AC list but called out in the plan) :
- T4's four RBAC tests are the four edges of the truth table : (admin, parent-linked, parent-unlinked, eleve-own). Any regression that flips one row is caught.
- T2's `::test_reprocess_raises_state_error_when_already_scored` is the bite on the "reprocess on SCORED" decision.
- T5's two log tests are the bite on the "no PII in logs" invariant.

**Test independence** : the API tests don't share `Evaluation` rows across tests (each test seeds its own row in its own `session_factory` block). The service tests use the existing `FakeS3` from `tests.services.storage.test_s3_client` plus a hand-rolled `_OcrStub` (s18 already proved the pattern).

**Cross-tenant bite** : `::test_score_manual_parent_of_unlinked_child_returns_403` is the AC8 test. A regression that lets the parent through breaks this test and would, in production, allow a parent to override another family's evaluation — a real breach.

## Definition of Done

- One PR opened from `feature/s18b-evaluation-actions-admin` to `main`. Conventional-commit title `feat(api): add /api/evaluations/{id}/score-manual and /reprocess admin endpoints (s18b)`. Body carries the AC table (AC1-AC8) with each one ticked, the research summary, and the review verdict (placeholder — filled in by the review).
- `pytest backend/tests` green (full suite, no regression on s18's 53+ existing tests, no regression on the 652-test baseline noted in the s18 review).
- `ruff check backend/ tests/` clean.
- `git diff main...feature/s18b-evaluation-actions-admin` shows touches only in the files listed above (`backend/app/api/evaluations/{schemas,router}.py`, `backend/app/services/ocr/evaluation_extractor.py`, the two test files, the new ADR, and the new plan/research). No collateral damage in `models.py`, `main.py`, `factory.py`, `MultimodalOcr`, `MinioClient`.
- A passing review (no critical findings) per AGENTS.md § Gate.
- No code on `main` directly — the PR is the only delivery vehicle (manual ship mode, AGENTS.md § Stratégie de ship).

<< IP Mike: task granularity, what a good plan contains/avoids. >>
