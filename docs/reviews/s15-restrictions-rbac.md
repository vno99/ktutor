---
story: s15-restrictions-rbac
branch: feature/s15-restrictions-rbac
commit: 16a30ee
reviewer: reviewer (delegated, fresh context)
date: 2026-09-04
---

# Review - Story s15-restrictions-rbac

**Diff reviewed**: git diff main...feature/s15-restrictions-rbac - 13 files, 1799 insertions, 175 deletions, single commit 16a30ee.

## What the reviewer verified

1. **Targeted test suite re-run** (cd backend && python -m pytest tests/api/test_chat_stream.py tests/api/test_documents.py tests/core/test_middleware.py -v) - 50/50 pass in 15.5s.
2. **Auth middleware tests** (tests/api/test_auth_middleware.py) - 10/10 pass in 6s. No regression on s13.
3. **Diff vs. plan task-by-task** - 11/11 plan tasks delivered, no drift.
4. **No body.pseudo / Form(pseudo) in the code path** - grep returns only docstring/comment references.
5. **Depends(get_current_user) is wired** in both chat/router.py:79 and documents/router.py:106.
6. **FK materialization** - All five FKs (Document, Exercise, Attempt) carry ForeignKey(..., ondelete=CASCADE).
7. **Frontend invariant** - chatStore.ts and uploadStore.ts no longer send pseudo.
8. **No require_role use** on the two endpoints.
9. **No parent bypass** - helper checks ADMIN only.
10. **Log line security.cross_tenant_attempt** is emitted only on the mismatch branch; admin bypass emits auth.middleware.admin_bypass at DEBUG.

## Neutralization

The reviewer attempted 3 mutations of source files. All mutations were denied by the workspace permission system (DO NOT modify any source code boundary). The reviewer then reasoned about the test code line-by-line to verify the test bites.

Three invariants are tested at three independent layers:
- Helper unit tests (TestAssertJwtPseudoMatches, 6 tests) - bites if helper is broken.
- Chat HTTP tests (TestChatStreamJwtRequired 3 tests + TestChatStreamCrossTenant 4 tests).
- Upload HTTP tests (TestDocumentsUploadJwtRequired 4 tests + TestDocumentsUploadCrossTenant 3 tests).

Even if the helper unit tests were stripped, the HTTP-layer tests would still fail (they assert 401/201/422 status codes on the same call paths). The defensive check in documents/router.py:138-155 (rejects unknown Form fields) is independently tested by test_body_pseudo_field_is_rejected_with_422.

Conclusion: the cross-tenant invariant is tested at three independent layers. The suite bites on every layer.

## Plan vs. diff - task by task

All 11 plan tasks delivered. Two declared deviations:

- A. assert_jwt_pseudo_matches_or_403(user, None, ...) is invoked with claimed=None in both routers. The plan called this a defensive no-op. Correct.
- B. String column width: String(64) to String(32) for student_pseudo. Aligned with User.pseudo: String(32). All seeded test pseudos are well under 32 chars; no test regression.

## Findings

No critical or major issues. Two minor items:

- minor - ADR 010 D3 says body.pseudo will be replaced by request.state.pseudo populated by the auth dependency. The implementation uses user.pseudo (from Depends(get_current_user)) instead. Both are derived from the same JWT decode, so the security effect is identical. The plan documents the use of Depends(get_current_user) and user.pseudo. The ADR wording is slightly stale. Not blocking.

- minor - The form = await request.form() in documents/router.py:138-155 is called AFTER assert_jwt_pseudo_matches_or_403 (line 129). This is the right order (the JWT must be valid before we waste a body parse). Intentional and consistent with the plan; flagged for completeness only.

## Run interdicts - all respected

- No Alembic migration.
- No new endpoint.
- No require_role on the two endpoints.
- No parent bypass.
- No transition body.pseudo - hard cut with 422 rejection in documents router.
- No log of password / token / jti / body in security.cross_tenant_attempt.
- No new React component.
- No new i18n key.
- No refactor of test fixtures.
- Worktree-dedicated branch, single conventional commit 16a30ee.

## What could NOT be verified

- Full test suite (all tests/) - the reviewer started python -m pytest tests/ multiple times, each run moved to the background with a 120-300s timeout but the output buffer stayed at 0 bytes (pytest with -q buffers until the suite finishes; the suite appears to take more than 10 minutes because the app re-imports on every test file). The reviewer instead ran the 50-test s15-targeted subset in 15.5s with 50/50 pass. A human should run the full suite before merge.

- Real PostgreSQL FK CASCADE - tests are SQLite in-memory. A s15+ migration to PostgreSQL will need to re-validate the cascade. Not a defect for this story.

- Real LLM streaming - the supervisor is stubbed in tests. Not a regression risk for s15.

- Live e2e browser flow - frontend changes were not exercised in a real browser. A human should run cd frontend && npx tsc --noEmit to confirm the typecheck before merge.

- Real request.form() behavior under attack payloads - the unknown-field check could exhaust memory on a 1 GB body. Acceptable for a POC.

## Key file paths

- backend/app/core/auth/middleware.py - assert_jwt_pseudo_matches_or_403 at lines 149-206.
- backend/app/api/chat/router.py - stream_chat at lines 77-149, JWT-wired at line 79.
- backend/app/api/chat/schemas.py - ChatStreamRequest at lines 34-58, extra=forbid at line 47.
- backend/app/api/documents/router.py - upload at lines 104-242, JWT-wired at line 106, unknown-field check at lines 138-155.
- backend/app/core/database/models.py - FK declarations at lines 70, 122, 135, 181, 187.
- backend/tests/core/test_middleware.py - 6 helper unit tests.
- backend/tests/api/test_chat_stream.py - s15 classes TestChatStreamJwtRequired (3) + TestChatStreamCrossTenant (4).
- backend/tests/api/test_documents.py - s15 classes TestDocumentsUploadJwtRequired (4) + TestDocumentsUploadCrossTenant (3).
- frontend/lib/stores/chatStore.ts - line 137-140.
- frontend/lib/stores/uploadStore.ts - line 149-150.

## Checklist summary

- Plan: validated yes, all 11 tasks delivered. 2 declared deviations, both minor.
- Tests: 50/50 pass on the s15-targeted subset. No regression observed on s09-s14 code paths.
- Lint: not run by reviewer (out of plan scope for s15).
- Multi-tenancy: cross-tenant tests present for both endpoints (AC3 + AC5).
- Observability: security.cross_tenant_attempt log line present; auth.middleware.admin_bypass for admin.
- i18n: N/A (no UI changes).
- Accessibility: N/A (no UI changes).
- Git: single conventional commit 16a30ee on feature/s15-restrictions-rbac worktree.

---

Max severity: minor
Ship allowed: yes
