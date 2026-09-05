# ADR 013 — Dedicated `EvaluationStatus` enum (not reuse of `DocumentStatus`)

- Status: accepted
- Date: 2026-09-05
- Scope: story s18

## Context

The `Evaluation` model (s18) needs a status column. The natural
question is "should we reuse `DocumentStatus` (which already has
`indexed`, `error`, `manual_review_needed`) or define a new
`EvaluationStatus` enum?"

The two domains look similar — both pipeline to OCR, both can fail,
both can land in manual review — but the *meaning* of "error" is
materially different:

* A `Document` with `status=ERROR` means the document is **not
  usable** (OCR failure, embedding failure, ChromaDB write
  failure). The file is persisted for forensics but the user is
  told to retry.
* An `Evaluation` copy with no score is **still a successful
  upload** — the file is on disk, the user can see the row, and a
  parent / admin can enter the score manually (s18b). The
  underlying observation (the image is on the page) is fine; only
  the score extraction failed.

Reusing `DocumentStatus` would force a three-state design (scored /
manual_review_needed / error) where "error" is unreachable: the
extractor already short-circuits to `source='none'` (and therefore
`MANUAL_REVIEW_NEEDED`) when the OCR returns low confidence. A
dedicated two-state enum matches the actual user-visible outcomes
and keeps the s18b manual-review workflow aligned with the model.

## Decision

Introduce a new `EvaluationStatus` enum with the two values
`SCORED` and `MANUAL_REVIEW_NEEDED`. The mapping at the service
layer is:

* `EvaluationExtractor.source == "regex"` or `"llm"` →
  `EvaluationStatus.SCORED` (with `score` and `max_score` filled).
* `EvaluationExtractor.source == "none"` →
  `EvaluationStatus.MANUAL_REVIEW_NEEDED` (with `score=None` and
  `max_score=None`).
* OCR transport raises → service maps to
  `EvaluationError(EXTRACTION_FAILURE)` → 422 (no row written).

The enum lives in `app.core.database.models.EvaluationStatus`. s18b
will reuse it (manual score entry transitions
`MANUAL_REVIEW_NEEDED` → `SCORED`).

## Considered options

- **Option 1 — reuse `DocumentStatus` (rejected)** : the
  three-value enum (``indexed``, ``error``, ``manual_review_needed``)
  carries states that don't apply to evaluations (``indexed`` is
  meaningless, ``error`` is unreachable). Aliasing the enum would
  push the conceptual mismatch into every check (``is
  EvaluationStatus.INDEXED`` — what does that mean for an
  evaluation copy?).
- **Option 2 — dedicated `EvaluationStatus` (chosen)** : two
  values, both reachable, both semantically meaningful. The enum
  surface is locked by
  `tests/core/test_models.py::test_evaluation_status_enum_has_two_values`
  so a future addition is a deliberate decision, not an accident.

## Consequences

- **Easier** : the s18b manual-review workflow has a stable state
  machine to drive (no spurious ``error`` branch to handle).
- **Easier** : the router maps `MANUAL_REVIEW_NEEDED` to HTTP 201
  (a successful outcome) without consulting a "is this a real
  error" table — the enum value alone tells the story.
- **Harder** : a future dashboard that wants to surface "uploads
  that need attention" must aggregate two enums
  (``DocumentStatus.MANUAL_REVIEW_NEEDED`` and
  ``EvaluationStatus.MANUAL_REVIEW_NEEDED``). The dashboard
  story (s20+) is the right place to centralise this — out of
  scope for s18.
- **Watch** : s18b must not introduce a third ``EvaluationStatus``
  value without revisiting this ADR. The enum-locking test will
  fail if a value is added by accident.
