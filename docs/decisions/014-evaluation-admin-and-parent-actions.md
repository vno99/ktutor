# ADR 014 — Evaluation admin and parent actions (s18b)

- Status: accepted
- Date: 2026-09-05
- Scope: story s18b

## Context

The `Evaluation` model (s18) lands in `MANUAL_REVIEW_NEEDED` when
the LLM vision extractor cannot produce a score. Two new endpoints
(`POST /api/evaluations/{id}/score-manual` and
`POST /api/evaluations/{id}/reprocess`) let an operator unblock
those rows. The story says "admin (ou un parent lié)" — open
questions in the research (s18b § Open questions) ask:

* who can call `score-manual`?
* who can call `reprocess`?
* what happens when a `SCORED` row is reprocessed?
* where do the audit log lines live?
* do we add a history column or not?

The `Evaluation` model has no `updated_at` and no
`previous_status` column (s18b does not introduce one — the
run interdicts forbid it).

## Decision

### Decision 1 — `score-manual` RBAC is admin-OR-linked-parent

The router for `POST /api/evaluations/{id}/score-manual` does
NOT use `require_role`. The flow is:

1. Load the row by id (404 if missing — anti-leak).
2. If the user is `ADMIN`, proceed.
3. If the user is `PARENT`, call
   `assert_parent_linked_to_child_or_403(user, row.student_pseudo,
   route=..., db=db)`. The helper short-circuits on `ADMIN` (so
   no bypass duplication is needed).
4. Any other role (`ELEVE` and any future role) → 403
   `forbidden`. **No** `row.student_pseudo == user.pseudo`
   shortcut — an eleve cannot score her own copy (Piège 5).

The state transition `MANUAL_REVIEW_NEEDED → SCORED` lives in
the service (`EvaluationService.score_manual`), not in the
router. The router delegates the entire business rule.

### Decision 2 — `EvaluationStateError` is a separate class

A new `EvaluationStateError` exception class is added to
`app.services.ocr.evaluation_extractor`. The existing
`EvaluationErrorKind` enum stays upload-only
(`INVALID_FILE` / `EXTRACTION_FAILURE` / `STORAGE_FAILURE`).
The router maps the new error by message-substring:

* `"not_found"` in the message → 404
* anything else → 409 `state_conflict`

The discriminator is the message, not a 4th enum value — the
enum stays semantically focused on upload failures, and the new
error class carries a single bit of metadata ("this is a
state-transition refusal") that a future discriminator could
formalise.

### Decision 3 — `reprocess` returns 409 on a `SCORED` row

`POST /api/evaluations/{id}/reprocess` is admin-only
(`Depends(require_role(UserRole.ADMIN))`). A row in
`SCORED` is rejected with 409 `state_conflict`. The
reasoning:

* Re-extracting a scored copy opens the door to score drift
  (the LLM returns a different number, the student contests
  it). The s18b workflow is "the LLM failed the first time,
  force a retry" — not "the LLM got it right, let's see if it
  can get it right again."
* Future "reprocess after model upgrade" workflows are out of
  s18b scope. They can be added in a later story (s23+) that
  revises this decision.

The 409 is enforced at the service layer
(`EvaluationService.reprocess` raises `EvaluationStateError`
on `SCORED`), not just at the router — the same row cannot
be reprocessed via any future caller of the service.

### Decision 4 — No history column; audit logs in loguru only

The `Evaluation` model keeps its `created_at` column and gains
no `updated_at` / `previous_status` / `previous_score`
columns. The audit trail for `score-manual` and `reprocess`
lives in loguru only:

* `security.evaluation_manual_score` (INFO) on a successful
  `score-manual` with `caller` (the JWT pseudo), `evaluation_id`,
  `new_score`, `new_max_score`, `student_pseudo` (the row's
  tenant). No `teacher_comments`, no token, no body.
* `evaluation.reprocess_attempted` (INFO) on every `reprocess`
  (success or no-score) with `caller`, `evaluation_id`,
  `previous_status`, `new_status`, `new_score`,
  `student_pseudo`. No `ocr_text`, no image bytes, no
  `teacher_comments`.

The audit logs are emitted at the **router** layer because the
service does not know the JWT identity. The service's internal
errors (state conflicts, exceptions) are logged at the router
too (the router catches `EvaluationStateError` and logs a
warning with the caller).

## Considered options

For **Decision 1**:

* **Option A — admin only** (rejected): would force a parent
  to call an admin to score a child's copy. Operationally
  costly for the family workflow.
* **Option B — admin or any parent (no link check)** (rejected):
  turns the manual review into a cross-tenant attack vector —
  any parent can score any child's copy. Rejected by AC3 and
  Piège 2.
* **Option C — admin or linked parent** (chosen): the helper
  `assert_parent_linked_to_child_or_403` is the only check
  the parent branch runs. Admin short-circuits at the helper
  boundary. Eleve → 403 strict.

For **Decision 2**:

* **Option A — add a 4th value `STATE_CONFLICT` to
  `EvaluationErrorKind`** (rejected): the enum is upload-only.
  Mixing state-transition errors into an upload-error enum
  pollutes its semantics.
* **Option B — separate `EvaluationStateError` class** (chosen):
  orthogonal to the upload error family; the router has a
  small mapping table to convert.

For **Decision 3**:

* **Option A — re-extract a `SCORED` row (200, the new score
  replaces the old one)** (rejected): opens the door to score
  drift. The student could contest the new number against the
  one the teacher saw on the paper.
* **Option B — 409 on `SCORED`** (chosen): the s18b
  "re-extract because the LLM missed" workflow ends at the
  `MANUAL_REVIEW_NEEDED` row.

For **Decision 4**:

* **Option A — add a `previous_status` / `previous_score`
  column** (rejected): schema migration, alembic revision, and
  the row would carry stale data after the second reprocess.
  Out of scope for s18b.
* **Option B — audit logs in loguru only** (chosen): the audit
  trail is operational metadata, not part of the model's
  state. The log line carries everything an operator needs
  to reconstruct what happened.

## Consequences

* **Easier** : the s18b manual-review workflow has a stable
  state machine to drive (no spurious error branch to handle).
* **Easier** : the router maps `MANUAL_REVIEW_NEEDED` to
  HTTP 200 / 201 (a successful outcome) without consulting a
  "is this a real error" table — the enum value alone tells
  the story.
* **Harder** : a future dashboard that wants to surface
  "uploads that need attention" must aggregate two enums.
  The dashboard story (s20+) is the right place to centralise
  this — out of scope for s18b.
* **Watch** : a future story that wants to allow reprocess on
  `SCORED` rows must supersede this ADR (cf. AGENTS.md §
  "Décision immuable"). The 409 is on the service layer, so
  the flip is a service change + a router change + a new test
  bite (`test_reprocess_raises_state_error_when_already_scored`
  becomes a positive case).
