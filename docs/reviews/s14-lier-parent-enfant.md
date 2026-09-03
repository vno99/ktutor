---
story: s14-lier-parent-enfant
branch: feature/s14-lier-parent-enfant
commit: 6a59556
reviewer: reviewer (delegated, fresh context)
date: 2026-09-03
---

# Review — Story s14-lier-parent-enfant

**Diff reviewed**: `git diff origin/main...feature/s14-lier-parent-enfant` — 7 files, 1691 insertions, 4 deletions, single commit `6a59556`.

## What the reviewer verified

1. **Test suite re-run** (`cd backend && python -m pytest tests/ -q`) — 556 passed, 0 failed (97s). No regression on s12/s13/s13b.
2. **Lint** — `ruff check app/ tests/` clean. mypy not in deps; 24 pre-existing errors elsewhere, **none** in s14-touched files.
3. **Imports & API targets** — `get_current_user` at `app/core/auth/middleware.py:58`; `require_role` at line 106; pseudo/role constants correctly reused from `auth/schemas.py`.
4. **Scope** — only `backend/*` + `docs/{plans,research}/*` changed. No frontend, no Alembic migration, single conventional commit on the dedicated branch.

## Neutralization (4 mutations, all restored clean)

The reviewer ran 4 mutations against the diff; every one produced failing tests, demonstrating the suite bites:

| # | Mutation | Red tests | Pinned invariant |
|---|---|---|---|
| 1 | Invert 404-before-403 on `add_child` (return 403 even when parent missing) | 2 | Anti-leak (research trap 5) |
| 2 | Same inversion on `list_children` | 4 (1+2 above + 2 GET equivalents) | Anti-leak, both endpoints |
| 3 | Break `IntegrityError` catch + remove pre-check | 3 in `TestAddChildHappyPath`/`TestAddChildIdempotence` | Idempotence 200-on-duplicate (research trap 1) |
| 4 | Owner-or-admin → admin-only (`require_role(UserRole.ADMIN)` instead of `get_current_user`) | 5 (`test_parent_self_link_returns_201` + 3 parent-owned GETs + ...) | Owner-or-admin pattern (research fait 1) |

## Plan vs. diff — task by task

All 8 plan tasks delivered. Two deviations the implementer declared up front:

- **A. `ChildrenListResponse = list[ChildResponse]` is a type alias**, not a Pydantic wrapper class. Wire format identical (top-level JSON array). Pydantic 2 serialises `list[X]` directly; a wrapper would require deprecated `__root__`. Justified.
- **B. 27 tests instead of plan's `≥ 12`** — all 15 extras are real. Mutations 1-2 prove the unauthorised-caller 404 tests directly defend the anti-leak invariant that the plan's authorised-caller tests would not.

## Findings

No critical or major issues. Three minor items:

- **minor** — `ChildrenListResponse` is a type alias, not a wrapper class. Justified (see deviation A). Wire format unchanged.
- **minor** — 27 tests vs. plan's `≥ 12`. Strengthens the suite. AGENTS.md § DoD cross-tenant test is present.
- **minor** — `require_role` is still imported in `router.py:51` because s13b's `create_user` and `update_role` still need it. Not a defect, not a drift.

## Run interdicts — all respected

- No Alembic migration (init_db handles it; `backend/alembic/versions/` unchanged from s01b).
- No frontend files touched.
- No `require_role(UserRole.ADMIN)` on s14 endpoints (correctly uses `get_current_user` + owner-or-admin check in handler).
- No cycle detection (POC scope, per story spec).
- No role constraint on `child_pseudo` (a parent can be linked to another parent, per research §3).
- No DELETE endpoint (out of scope for s14).
- No new `*ErrorCode` Literal — extends the existing `UserErrorCode` which already contains `"user_not_found"` and `"forbidden"`.
- No refactor of `_pseudo_already_exists` (per AGENTS.md "Pas de refactor transverse").
- Worktree-dedicated branch, single conventional commit.

## What could NOT be verified

- **Real PostgreSQL FK CASCADE** on `parent_child_links.parent_pseudo` / `.child_pseudo` — tests are SQLite in-memory. The CASCADE is wired (`ondelete="CASCADE"`), SQLite does not enforce it, and a s15+ migration to PostgreSQL will need to be re-validated.
- **True concurrent-request race** for the idempotence path — TestClient is single-threaded. The `catch IntegrityError` path is exercised by serial tests (mutation 3), but the actual race is not.
- **Cross-tenant test for `add_child`** — only `GET` has one. The auth model excludes the case by construction (a different parent is neither owner nor admin of the URL), so a test would be a tautology. Not a defect, noted for completeness.
- **Real password material in logs** — the test checks the literal `seedpassword1`; a future hash-format regression would not be caught by string-matching. Acceptable for POC.

## Key file paths

- `backend/app/api/users/router.py` — s14 endpoints at lines 423-597
- `backend/app/api/users/schemas.py` — s14 schemas at lines 161-206
- `backend/app/core/database/models.py` — `ParentChildLink` at lines 269-319
- `backend/tests/api/test_users_parent_child.py` — 27 tests
- `backend/tests/core/test_models.py` — 6 model tests at lines 463-580
- `backend/app/core/auth/middleware.py:58` — `get_current_user` (reused as-is)

## Checklist summary

- Plan: validated: yes, all 8 tasks delivered.
- Tests: 556/556 pass, +33 vs. pre-s14 baseline (529). 0 regressions.
- Lint: ruff clean. mypy: no new errors in s14-touched files.
- Multi-tenancy: cross-tenant test present (AC6).
- Observability: log topics `users.children.{created,duplicate,forbidden,listed}`; logging-hygiene test verifies no password/hash/token/jti.
- i18n: N/A (backend-only).
- Accessibility: N/A (backend-only).
- Git: single conventional commit on feature branch.

---

Max severity: minor
Ship allowed: yes
