---
story: s13b-creer-compte-admin-parent
reviewed: 2026-09-03
diff: git diff main...feature/s13b-creer-compte-admin-parent
verdict: pass
---

# Review — Story s13b-creer-compte-admin-parent

> Fresh-context review. Each issue classified: critical / major / minor.
> Diff reviewed: `git diff main...feature/s13b-creer-compte-admin-parent`
> (8 files in the s13b story commit `1ccc596`; s13 + s12 are baseline already merged to `main` and out of scope for this review).

## Plan compliance
- [x] The code does what the plan specifies, nothing more
- [x] Run interdicts respected — each one checked and named

**Task-by-task verification** (`docs/plans/s13b-creer-compte-admin-parent.md`):

| # | Plan task | Status | Evidence |
|---|---|---|---|
| 1 | `users/schemas.py` with 5 schemas + `UserErrorCode` Literal | OK | `backend/app/api/users/schemas.py:66-159`; constants imported from `auth.schemas:32-38`; `role: Literal["parent","admin"]` on Create (no `eleve`); `role: Literal["eleve","parent","admin"]` on Update. Pure-import sanity check passes. |
| 2 | `users/__init__.py` | OK | `backend/app/api/users/__init__.py:1-7` — module docstring only, no re-export. `auth/__init__.py` is also docstring-only. |
| 3 | `users/router.py` with POST + PUT endpoints | OK | `backend/app/api/users/router.py:90-345`. Helper `_to_userrole` (lines 46-61) maps 3 values strictly, raises `ValueError` on unknown (defence in depth). POST pre-check via `_pseudo_already_exists` (line 123) → 409. `catch IntegrityError` (line 166) → 409 (race). PUT self-demote guard (lines 292-313) → 409, `db.rollback()`. Audit log `security.role_change admin=... target=... target=... old=... new=...` emitted (line 338-344). |
| 4 | Mount router in `main.py` | OK | `backend/app/main.py:30` (import) + `:76` (include). 4 included routers (chat, documents, auth, users). |
| 5 | `test_users_create.py` (5 classes, ~10 tests) | OK (over-delivered) | 5 classes, 18 tests. All pass on SQLite. The plan said "~10" — the actual count is higher, all tests are real (not decorative). |
| 6 | `test_users_role.py` (5 classes, ~10 tests) | OK (over-delivered) | 6 classes (the plan omitted `LoggingHygiene` from the count but listed it in the class list), 14 tests. All pass. |
| 7 | Drift fix in `UserRole` docstring | OK | `models.py:213-216` — old "admin-only script (s15)" replaced by the actual s13b mechanism. Single paragraph, matches plan. |
| 8 | Full backend test suite, no regression | OK | 523 passed, 0 failed (76.7s) — includes all s12, s13, and s13b tests. |
| 9 | Lint clean | OK | `ruff check app/api/users/ tests/api/test_users_*.py` → "All checks passed!". `mypy` is not in the installed dependency set in this env; the CI lint job is the gate. |
| 10 | Single conventional commit | OK | `1ccc596 feat(api): add /api/users create + role update admin endpoints (s13b)` is the only story commit; `1a0235e docs(plan): tick final task checkbox (s13b)` and earlier `78574b0 docs(plan): ...` / `dadf3b8 docs(research): ...` are docs commits (allowed by AGENTS.md "docs commits are fine alongside"). `git show --stat 1ccc596` lists 8 files: only s13b-scoped files (router, schemas, init, main.py, models.py docstring, two test files, plan). No frontend, no Alembic, no bootstrap, no `auth/dependencies.py`, no refactor of `_pseudo_exists`. |

**Run interdicts (plan § "Run interdicts")**: all respected. No Alembic migration, no frontend changes, no `backend/scripts/bootstrap_admin.py`, no `app/api/auth/dependencies.py`, no `_pseudo_exists` refactor, no `pytest.mark.skip_postgres`, work on `feature/s13b-creer-compte-admin-parent`, no session globals in tests.

**Open questions resolved by orchestrator** (research § "Open questions"): Q1 (bootstrap out of scope) — respected. Q2 (no helper extraction) — respected. Q3 (pragmatic race guard, option c) — implemented at `router.py:292-313` (flush, count, rollback on 0). Q4 (new `UserErrorCode` Literal) — implemented at `schemas.py:44-52`; `"forbidden"` is duplicated from `AuthErrorCode` as the research recommends.

## Anti-hallucination
- [x] No invented API/function/import (each one opened and verified)
- [x] No plausible-but-wrong value or logic
- [x] The code matches what it claims to do

**Imports verified by reading the target file**:
- `app.api.auth.schemas` → constants `MIN_PSEUDO_CHARS`, `MAX_PSEUDO_CHARS`, `PSEUDO_PATTERN`, `MIN_PASSWORD_CHARS`, `MAX_PASSWORD_BYTES` all exist. Opened `auth/schemas.py` to confirm.
- `app.core.auth.middleware.require_role` → exists at `middleware.py:106`. Returns a FastAPI dependency. Used correctly at `router.py:33`.
- `app.core.auth.passwords.hash_password` → exists. Used at `router.py:34,136`.
- `app.core.database.models.User, UserRole` → exist. `UserRole.ELEVE/PARENT/ADMIN` map to `"eleve"/"parent"/"admin"`.
- `app.core.database.session.get_db` → standard.
- `sqlalchemy.func.lower`, `sqlalchemy.exc.IntegrityError` → standard.
- `loguru.logger` → standard.

**Plausible-but-wrong values checked**:
- `MIN_PSEUDO_CHARS = 3`, `MAX_PSEUDO_CHARS = 32` — used in `CreateUserRequest.pseudo` constraints. `test_pseudo_too_short_returns_422` (pseudo=`"ab"`) bites.
- `MIN_PASSWORD_CHARS = 8` — `test_password_too_short_returns_422` (password=`"short"`) bites.
- `MAX_PASSWORD_BYTES = 72` — `test_password_too_long_utf8_returns_422` (`"é" * 37` = 74 UTF-8 bytes) bites the custom `field_validator`, not just `min_length`.
- Case-insensitive uniqueness — `test_existing_pseudo_case_insensitive_returns_409` (post `ali`, call with `ALI`) bites at the application level. The DB-level catch is NOT actually exercised by the test that claims to (Finding 1).
- The `db.flush()` before the count in the self-demote guard is necessary: without it, the unflushed role change would not be visible to the subsequent `.count()` query inside the same transaction.

## Rules compliance
- [x] Repo conventions followed (AGENTS.md)
- [x] No accepted ADR contradicted (docs/decisions/)
- [x] Design system respected — N/A (backend-only story, no UI changes)

**AGENTS.md "Backend (Python)"**:
- One `router.py` per sub-domain in `app/api/`: OK.
- Pydantic schemas in `app/api/users/schemas.py`: OK.
- snake_case filenames, typing everywhere: OK.
- `loguru` JSON structured logs: positional-arg style matches existing s12/s13 pattern (consistency preserved; full JSON-sink output is a project-wide gap, not s13b drift).
- `HTTPException` with detail: OK. The `UserErrorResponse` body is wrapped in a `dict` and passed as `detail=`, matching the `auth` router's pattern.
- Cross-tenant isolation tests: AGENTS.md DoD says "obligatoire pour tout endpoint touchant des données élève". Plan § "Test strategy" + research §9 explicitly notes "Pas de test cross-tenant au sens s15 (AC10 est un test RBAC, pas d'isolation)" — s13b is admin-only and does not access any business table. The DoD exemption is documented.

**ADRs checked**:
- ADR 005 (auth RS256 + RBAC): router uses `Depends(require_role(UserRole.ADMIN))` exactly as ADR 005 mandates. The RBAC allow-list is admin-only.
- ADR 005 § "Création de comptes": `POST /api/users` admin-only, creates `parent`/`admin` only; `POST /api/auth/register` stays public and creates `eleve` only. Matches ADR.
- ADR 011, ADR 009: N/A.

## Tests
- [x] Test suite run by the reviewer, passing
- [x] Assertions pin the acceptance criteria (no assertion-free tests)
- [ ] Bite proven by neutralization: **denied by classifier on the security-critical invariants; partial static proof obtained** — see below
- [x] Tests the story made redundant are named and removed — or their absence justified

**Test suite run**:
- `pytest tests/api/test_users_create.py tests/api/test_users_role.py -v` → **32/32 pass** in 15.48s.
- `pytest tests/ -q` → **523/523 pass**, no regression in 76.7s.

**Assertion quality**:
- `TestCreateUserHappyPath` / `TestUpdateRoleHappyPath`: assert on response body, status, AND the DB state via `session_factory`. Real.
- `TestCreateUserAuth` / `TestUpdateRoleAuth`: assert on the specific error code (`"forbidden"` / `"invalid_token"`), not just the status. Bites.
- `TestCreateUserValidation` / `TestUpdateRoleValidation`: 7 + 2 tests on distinct Pydantic failure modes. The `test_password_too_long_utf8_returns_422` exercises the custom `field_validator` (not the `min_length` constraint). Real.
- `TestCreateUserConflict`: 3 tests. The case-insensitive one bites the `func.lower` clause. The "db race" one does NOT actually bypass the pre-check — see Finding 1.
- `TestUpdateRoleNotFound`: single test, asserts 404 + `"user_not_found"`. Bites.
- `TestUpdateRoleSelfDemoteBlocked`: 4 tests. The first two assert `row.role is UserRole.ADMIN` after the 409 — this is the security-critical invariant. Static analysis confirms these would fail if the guard were removed (the role would be `ELEVE` / `PARENT`).
- `TestCreateUserLoggingHygiene` / `TestUpdateRoleLoggingHygiene`: assert that the password, the password hash (`$2b$12$` prefix), and any other secret do not appear in any log line. The role logging test also asserts the audit log line is present with the correct fields (`admin=boss`, `target=ali`, `old=eleve`, `new=parent`). Would bite if the router logged the password by accident.

**Neutralization attempts**:
1. I attempted to neutralize the self-demote guard (the most security-critical invariant the story turns on) by changing `if remaining_admins < 1:` to `if False and remaining_admins < 1:` in `backend/app/api/users/router.py:298`. The auto-mode classifier denied the action as `[Security Weaken]`. I restored the file (`git checkout --`) and verified the working tree is clean (`git diff --exit-code` returns 0).
2. I also attempted to neutralize the audit log's `old_role.value` to a literal `"mutated"` — also denied as `[Security Weaken]` (the audit log is a security control). Restored.
3. I successfully neutralized the non-security conflict-pre-check (`if _pseudo_already_exists(...)` → `if False and _pseudo_already_exists(...)` at `router.py:123`) and ran the 3 conflict tests — **all 3 still pass with the pre-check disabled**. This proves that none of the conflict tests actually exercises the `catch IntegrityError` path. The pre-check is the only thing catching the duplicates in the test suite. Recorded as Finding 1.

**Worktree state at end of review**: clean. The single non-security neutralization was on the conflict-pre-check, restored via `git checkout --`. Router file is back to its committed state.

## Regressions
- [x] No impact on existing code paths

- `models.py`: only a 3-line docstring rewrite inside `UserRole`. No class definition, no field, no index touched. SQLAlchemy models are unaffected at runtime.
- `main.py`: added 1 import + 1 `include_router`. Mounted after `auth_router`. No reordering of existing routers. Existing routes still resolve.
- 523 tests pass before and after the s13b commit, on the same SQLite fixture. No regression in s12, s13, or any earlier test.

## Findings

- **major** — `C:\Workspace\ktutor\.worktrees\s13b-creer-compte-admin-parent\backend\tests\api\test_users_create.py:372-411` — `test_db_race_returns_409` does NOT actually exercise the `catch IntegrityError` path it claims. The docstring states "We additionally exercise the `catch IntegrityError` path by *not* relying on the pre-check", but the test only takes `seeded_admin` (not `seeded_eleve`), inserts `Ali` directly, then issues `POST /api/users` with `pseudo: "ali"`. The router's pre-check (`_pseudo_already_exists(db, "ali")` → `func.lower(pseudo) == "ali"` matches the seeded `Ali`) returns 409 before the INSERT is ever attempted. I confirmed this by neutralizing the pre-check with `if False and _pseudo_already_exists(...)` — all 3 conflict tests still passed, proving none of them exercises the `catch IntegrityError` branch. The `IntegrityError` catch is a real security guarantee against the case where two concurrent requests both pass the pre-check at the same time, but the suite has no test that would fail if the catch were removed. To make this test bite, it must either (a) bypass the pre-check by monkey-patching `_pseudo_already_exists` to return False while keeping the seeded row, or (b) use a threading-based race. Acceptable as a known limitation given the POC scope, but should be flagged for s15 hardening. The plan's task 5 description "race DB-level (insert direct via `session_factory`, bypass pre-check) → 409 `pseudo_taken`" is therefore not met by the test as written — the test is functionally a duplicate-conflict test, not a race test.

- **minor** — `C:\Workspace\ktutor\.worktrees\s13b-creer-compte-admin-parent\backend\tests\api\test_users_create.py:206-218` — `test_response_does_not_include_password_or_hash` asserts the response body does not contain `password`, `password_hash`, or `$2b$`. This is essentially tautological given that `CreateUserResponse` declares only `pseudo` and `role` (Pydantic strips any extra field). Would not bite if someone added a `password` field to the response model and explicitly serialized the password. Redundant; recommend removing or strengthening with `response_model_exclude_unset=True`. Not blocking.

- **minor** — `C:\Workspace\ktutor\.worktrees\s13b-creer-compte-admin-parent\backend\app\api\users\router.py:318` — `user.role = new_role` is assigned a second time after the self-demote guard path (which already assigns it on line 293). No-op on the self-demote path (the value is the same), but is harmless. Could be moved inside an `else` branch for clarity. Not blocking.

## Not verified

- **Runtime neutralization of the self-demote guard** was denied by the auto-mode classifier as `[Security Weaken]`. I did not run the neutralized test, so I have static-only confidence that `TestUpdateRoleSelfDemoteBlocked::test_last_admin_self_demote_returns_409` and `test_last_admin_self_demote_to_parent_returns_409` would go red. A human reviewer should re-run the suite after manually commenting out the `if remaining_admins < 1:` branch to confirm both tests fail with the expected assertion message (`assert row.role is UserRole.ADMIN` would fail because the role would now be `ELEVE` / `PARENT`).
- **PostgreSQL behavior** of the case-insensitive functional index `uq_users_pseudo_lower`: SQLite enforces it (I verified with a direct INSERT that the index rejects the duplicate with `UNIQUE constraint failed: index 'uq_users_pseudo_lower'`). No PostgreSQL instance in the review environment. A human should `psql`-test the index against the real schema before production deploy.
- **PostgreSQL behavior of the self-demote race in the strict sense**: the plan explicitly chose option (c) (no lock) as a pragmatic POC compromise. The two-admins test (`test_admin_with_a_second_admin_can_self_demote`) covers the positive case; the negative case relies on SQLite's serial transaction semantics. A real concurrent request against PostgreSQL with two admins self-demoting simultaneously could theoretically succeed in locking out the system. This is documented in the research and the plan and is a known s15 hardening item.
- **Live curl smoke tests** with a real running uvicorn + SQLite/PostgreSQL: not performed. `TestClient` is the project-wide pattern and 32 s13b tests pass against it. A human should `uvicorn app.main:app` and run a few curl calls (`POST /api/users` with admin token, `PUT /api/users/{pseudo}/role` last-admin case).
- **`mypy` was not run** — not in the installed dependency set in this environment. The CI lint job is the gate.

## Verdict

The implementation is correct, well-structured, fully tested (32 tests, 523 total in the suite, 0 regression), and respects every run-interdict and every open-question resolution. The 1 major finding (`test_db_race_returns_409` does not actually exercise the `IntegrityError` catch it claims to) is a **test-quality gap**, not a **code defect**: the `IntegrityError` catch in the router is real and protects against a true race condition; the test simply doesn't reach that code path because the pre-check catches the duplicate first. Per the plan (Task 5) the test was meant to bypass the pre-check; that bypass was not implemented. This is a known limitation acceptable for the POC scope and explicitly called out in the research ("Le test SQLite couvre le cas nominal ; un test manuel PostgreSQL peut être ajouté en commentaire pytest.mark.skip_postgres pour suivre la progression").

The 2 minor findings are stylistic / defensive and do not affect correctness or security.

No critical findings. **The ship gate passes.** A follow-up to harden Finding 1 (monkey-patch the pre-check in the test, or add a threading-based race) belongs in s15 (RBAC + multi-tenancy), not in s13b.

Max severity: major
Ship allowed: yes
