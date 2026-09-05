---
story: s18b-evaluation-actions-admin
reviewer: reviewer (subagent, fresh context, anti-hallucination)
reviewed_at: 2026-09-05
worktree: C:\Workspace\ktutor\.worktrees\s18b-evaluation-actions-admin
branch: feature/s18b-evaluation-actions-admin
base: main
commit_reviewed: a61cbfb
result: PASSED
---

# Review — s18b-evaluation-actions-admin

## Verdict

**Max severity: minor**
**Ship allowed: yes**

## Verified facts

- **Test suite**: 678/678 tests pass (full backend). 52/52 s18b-scoped tests pass.
- **Single commit** on `feature/s18b-evaluation-actions-admin` (`a61cbfb`), clean working tree.
- **8 files touched**, all within the plan's "Files touched" set:
  - `backend/app/api/evaluations/router.py` (+269 / -3)
  - `backend/app/api/evaluations/schemas.py` (+103)
  - `backend/app/services/ocr/evaluation_extractor.py` (+178)
  - `backend/tests/api/test_evaluations.py` (+666)
  - `backend/tests/services/ocr/test_evaluation_extractor.py` (+314)
  - `docs/decisions/014-evaluation-admin-and-parent-actions.md` (new, 172)
  - `docs/plans/s18b-evaluation-actions-admin.md` (new, 164)
  - `docs/research/s18b-evaluation-actions-admin.md` (new, 445)
- **No changes** to interdicted files: `models.py`, `main.py`, `factory.py`, `app/services/rag/ocr.py`, `app/services/storage/minio_client.py`. Verified via `git diff --stat`.
- **ruff check** on s18b files: clean.

## Plan vs diff

All 7 plan tasks (T1-T7) are present:

- **T1 (Pydantic schemas)**: `ScoreManualRequest` with `Field(ge=0)`, cross-field `score ≤ max_score` validator, `max_length=8192` on `teacher_comments`; `ScoreManualResponse`, `ReprocessResponse` (with `ocr_confidence` and `source`), `EvaluationStateErrorResponse` (with `code: Literal["state_conflict", "not_found"]`).
- **T2 (service)**: `EvaluationStateError(Exception)` class; `EvaluationService.score_manual` and `EvaluationService.reprocess` methods; `EvaluationReprocessResult` dataclass (deviation 2, see below); `__all__` extended.
- **T3 (router)**: both endpoints wired with `Depends(get_db)` and `Depends(get_evaluation_service_dep)`. `reprocess` uses `Depends(require_role(UserRole.ADMIN))`.
- **T4 (RBAC)**: `_require_score_manual_authorized` loads row first, then ADMIN bypass → PARENT link check → 403 default. No `row.student_pseudo == user.pseudo` shortcut (Piège 5 honored).
- **T5 (audit logs)**: `security.evaluation_manual_score` and `evaluation.reprocess_attempted` emit with no PII. Verified by loguru sink test that asserts `SECRET-PII-MUST-NOT-LEAK-12345 not in joined` and `"Note finale" not in joined`.
- **T6 (ADR 014)**: all 4 decisions match the implementation.
- **T7 (single commit)**: one conventional commit, all files in one go.

## Central invariants verified (read-only)

1. **RBAC strict on `score-manual`** (`router.py:300-348`): the helper `assert_parent_linked_to_child_or_403` is called with `row.student_pseudo` (not the URL `evaluation_id` UUID, not `user.pseudo`). The 4-edge truth table is covered: `test_score_manual_eleve_cannot_score_own_evaluation`, `test_score_manual_parent_of_linked_child_succeeds`, `test_score_manual_parent_of_unlinked_child_returns_403`, plus admin path. A regression that flipped the order (e.g. accepted any authenticated user with matching pseudo) would break the eleve test.
2. **409 on SCORED reprocess** (`evaluation_extractor.py:549-553`): the service raises `EvaluationStateError` with a non-"not_found" message. The router's `_state_error_to_status` maps to 409. The HTTP test `test_reprocess_returns_409_when_already_scored` and the service test `test_reprocess_raises_state_error_when_already_scored` pin this.
3. **Audit logs without PII**: `security.evaluation_manual_score` carries only `caller`, `evaluation_id`, `new_score`, `new_max_score`, `student_pseudo` — no body, no token, no `teacher_comments`. `evaluation.reprocess_attempted` adds `previous_status` and `new_status`. The audit-log tests capture via a loguru sink and assert both presence (substring) and absence (`secret_comment not in joined`, `"Note finale" not in joined`).
4. **Cross-tenant bite (AC8)**: `test_score_manual_parent_of_unlinked_child_returns_403` seeds pat (parent) without a `ParentChildLink` to bob, then POSTs with pat's JWT targeting bob's row. The helper does the SQL lookup and 403s. A regression that bypassed the helper would fail this test.

## Documented deviations — judgment

1. **`created_at` vs `updated_at`** in response. Plan said `updated_at`, implementation uses `created_at` with the docstring explaining "S18b n'ajoute pas de colonne d'historique : `created_at` est l'horodatage de dernière mise à jour effective". This is honest (no hidden column was added; the run interdicts forbid it). **Acceptable** as documented.
2. **`EvaluationReprocessResult` dataclass** instead of bare `tuple[Evaluation, ExtractionResult]`. The dataclass carries `previous_status` which the plan's T5 audit log requires. The plan signature `tuple[Evaluation, ExtractionResult]` is therefore inconsistent with T5's spec; the dataclass is the only way to honour both. **Acceptable** as a necessary improvement.
3. **Audit log at router layer** (not service). ADR 014 Decision 4 explicitly records this because the service does not know the JWT identity. **Acceptable** as documented.
4. **Pre-commit lint cleanup** — ruff on s18b files is clean. **Acceptable** (verifiable, no finding).

## Findings

### critical
None.

### major
None.

### minor

1. **`created_at` field in response is not bit-tested** (`schemas.py:139-144`, `router.py:429, 511`). No HTTP test asserts on `body["created_at"]` — the field is exposed in the response but its presence and value are not pinned. A future regression that drops or renames it would not be caught. (Cosmetic; the value is informational.)

2. **Audit log field order/content is partially test-bit-tested** (`router.py:495-504`). `test_reprocess_emits_audit_log` asserts the log line is present, that `evaluation_id` and `caller` are in it, and that OCR text is absent. It does not assert the *value* of `previous_status` in the log line — only that the line exists. A regression that swapped `previous_status` and `new_status` in the format string would not be caught. (Acceptable but the assertion is weak; the service test pins `updated.previous_status` separately.)

## What I could NOT verify

- **Mutation testing of the RBAC, 409, and audit-log invariants** — the tool wrapper rejected code mutations on security guards. I substituted read-only inspection of the test code and router code. The test names map 1:1 to the documented invariants; the assertions on status codes, body codes (`forbidden`, `state_conflict`, `not_found`), and log-line substrings are load-bearing. A direct neutralization would be the standard way to prove these tests bite; the auto-classifier declined it.
- **End-to-end browser/UI** — s18b is backend-only per the plan; no frontend was built. Out of scope.
- **Real OCR transport** — never exercised; correctly stubbed per s18 pattern.
- **Real S3 / PostgreSQL** — correctly stubbed with `FakeS3` and in-memory SQLite per s18 pattern; the test pattern was proven in s18.
- **Production JWT keys** — test session fixture generates a fresh RSA keypair; s15 contract is respected.

## Gate

Max severity: minor
Ship allowed: yes
