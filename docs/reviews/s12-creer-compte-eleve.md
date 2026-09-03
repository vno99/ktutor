# Review — s12-creer-compte-eleve

> Anti-hallucination review of the story diff `git diff d8c990fc..feature/s12-creer-compte-eleve` (commit `77c5091 feat(api): add /api/auth/register endpoint (s12)`, +1254/-1 lines, 14 files).
> The reviewer (fresh context) ran the test suite, neutralised the 3 P0 invariants, and cross-checked the implementation against `docs/plans/s12-creer-compte-eleve.md`, `docs/research/s12-creer-compte-eleve.md`, `AGENTS.md`, and the accepted ADRs in `docs/decisions/`. The design is backend-only (s12 ships no UI); no design-system conformity check is required for this story.
> Date: 2026-09-03.

## Verdict

- **All 7 acceptance criteria are covered by named tests that bite when neutralised.** Each AC has at least one test that would fail if the corresponding code line is removed.
- **All 3 P0 invariants are proven by neutralization**: Pydantic 422 on >72-byte password, SQL `LOWER(pseudo)` unique index, `catch IntegrityError` → 409.
- **No regression on the existing 412 tests.** 442/442 pass in 29.37s (run independently by the reviewer).
- **The declared deviation (UniqueConstraint → Index)** is correct, documented in the plan § "Déviation mineure documentée (D3)" and in `models.py:269-280`. The generated SQL `CREATE UNIQUE INDEX uq_users_pseudo_lower ON users (lower(pseudo))` is valid for both SQLite (tests) and PostgreSQL (prod).
- **No password, hash, or fragment of either** appears in any `logger.*` call.
- **No Alembic migration created** (s12 uses `init_db()` only — convention s01-s10).
- **No frontend file modified** (`git diff --stat d8c990fc..HEAD -- frontend/` returns empty).
- **bcrypt cost = 12 hardcoded**, no `Settings` knob.
- **Endpoint is public** (no `Depends(get_current_user)`, JWT in s13).
- **Conventional commit** `feat(api): add /api/auth/register endpoint (s12)`.

The single **major** finding is a real gap the plan itself acknowledged: the `db.rollback()` calls in the two `except` blocks are not covered by an explicit test. A regression that swapped `rollback()` for `flush()` (or removed it) would pass all 15 register tests. Classified as a follow-up rather than a blocker — the rest of the story is solid enough to ship, and the `test_register_race_condition_with_bypassed_precheck_returns_409` already exercises the `IntegrityError` path end-to-end and asserts that no second row was inserted.

## Plan compliance

| Item | Verdict |
|---|---|
| Phases T1.1 → T5.5 all present in the diff | ✅ |
| `chat/*` and `documents/*` not touched | ✅ (diff stat clean) |
| `models.py` only adds `User` + `UserRole` + Index; no FKs materialised; no other models altered | ✅ |
| No Alembic migration in `backend/alembic/versions/` | ✅ (only pre-existing migration present) |
| `passlib` NOT added; `bcrypt>=4.0` added in a new "Auth" section | ✅ (`requirements.txt:36`) |
| `bcrypt` cost hardcoded to 12 | ✅ (`passwords.py:34`) |
| No login/refresh/JWT/middleware/admin-bootstrap code | ✅ |
| No frontend files modified | ✅ |
| No `scripts/bootstrap_admin.py` | ✅ |
| Conventional commit | ✅ `feat(api): add /api/auth/register endpoint (s12)` |

## Anti-hallucination

- [x] **No invented imports**: `Index` from `sqlalchemy`, `IntegrityError` from `sqlalchemy.exc`, `loguru.logger`, `bcrypt.hashpw/gensalt/checkpw` — all verified used and present.
- [x] **No plausible-but-wrong values**: Pydantic validator actually counts UTF-8 bytes (not chars); bcrypt cost = 12; pseudo PK `String(32)` matches Pydantic `MAX_PSEUDO_CHARS`; `password_hash` `String(255)` is sufficient.
- [x] **No silent try/except**: every `except` block logs at the right level and re-raises as `HTTPException` with a stable code.
- [x] **Code matches its docstrings**: pre-check + `catch IntegrityError` race handling works as advertised (verified end-to-end with monkeypatch on the bypassed-precheck test).

## Rules compliance

- [x] **AGENTS.md** — backend Python conventions respected (snake_case, PascalCase, kebab-case URL `/api/auth/register`); `from __future__ import annotations`; FastAPI router convention; Pydantic schemas; `loguru` positional `.format()` style; `HTTPException` on errors; no `try/except` muets.
- [x] **ADR 005** — `register` is public and creates only `eleve`; no `get_current_user`/`Depends(auth)`; no `parent`/`admin` paths in router; JWT deferred to s13.
- [x] **ADR 011** — pseudo regex `^[a-zA-Z0-9_]{3,32}$` aligned with the backend regex and the documented client-side pattern.

## Tests — coverage of the 7 ACs

| AC | Test (file) |
|---|---|
| AC1 — happy path 201 | `test_register_happy_path_returns_201_with_pseudo` (test_auth_register.py) |
| AC2 — bcrypt not plain text | `test_register_hashes_password_with_bcrypt` + `test_password_hash_not_plaintext` (test_passwords.py) |
| AC3 — case-insensitive duplicate → 409 | `test_register_duplicate_pseudo_returns_409` + `test_register_duplicate_pseudo_case_insensitive_returns_409` (test_auth_register.py) + `test_pseudo_unique_case_insensitive` (test_models.py) |
| AC4 — invalid pseudo 422 | `test_register_invalid_pseudo_too_short_returns_422` + `..._special_chars_...` + `..._too_long_...` |
| AC5 — password ≥ 8 chars AND ≤ 72 octets | `test_register_weak_password_too_short_returns_422` + `test_register_password_too_long_bytes_returns_422` |
| AC6 — default role 'eleve' | `test_register_default_role_is_eleve` + `test_default_role_is_eleve` |
| AC7 — happy + duplicate test | both above |

## P0 invariants — proven by neutralization

1. **Pydantic 422 on >72-byte password (UTF-8)** — removed the `@field_validator` UTF-8 byte check in `schemas.py` → `test_register_password_too_long_bytes_returns_422` went **RED** (1 test affected). Restored, full suite green again.
2. **SQL `LOWER(pseudo)` unique Index** — commented out the `Index("uq_users_pseudo_lower", func.lower(...), unique=True)` in `models.py:276-280` → `test_pseudo_unique_case_insensitive` and `test_register_race_condition_with_bypassed_precheck_returns_409` went **RED** (2 tests affected). Restored, full suite green again.
3. **`catch IntegrityError` → 409 + `db.rollback()`** — replaced the `except IntegrityError` block in `router.py:101-114` with `raise` → `test_register_race_condition_with_bypassed_precheck_returns_409` went **RED** (1 test affected). Restored, full suite green again.

`git diff --stat` confirmed clean (no diff) at the end of all neutralizations.

## Findings

| # | Severity | File | Issue |
|---|---|---|---|
| 1 | **major** | `backend/app/api/auth/router.py:106` and `:116` | **`db.rollback()` is not covered by any test.** Neutralised both `db.rollback()` calls (in the `except IntegrityError` and the broad `except Exception` paths) and **all 15 register tests still pass** (15/15). The plan § "Trois points où le plan peut se planter" #3 flagged this risk explicitly ("il faut un test explicite qui simule la race"). The bypassed-precheck test verifies the 409 status, the `code` discriminator, and that no second row was inserted — but does not assert the session is still usable after the rollback. **Follow-up cycle**: add an assertion after the 409 that the session can still be used for a follow-up query (e.g. `db.query(User).count()`). |
| 2 | **minor** | `backend/tests/api/test_auth_register.py:165-195` | The first race-condition test (`test_register_race_condition_raises_integrityerror_returns_409`) is **misnamed**. It seeds a row and calls the endpoint with a case-different pseudo, but the request never reaches the `catch IntegrityError` path: the pre-check (`func.lower(User.pseudo) == body.pseudo.lower()`) finds the seeded `"Ali"` and returns 409 before `db.commit()`. The test is functionally a duplicate of `test_register_duplicate_pseudo_case_insensitive_returns_409`. The actual race path is covered by the *next* test (`..._with_bypassed_precheck_...`). Suggest renaming or removing the first one. |
| 3 | **minor** | `backend/app/api/auth/router.py:115-128` | The `except Exception` block catches everything, including `ValueError` from `hash_password` (defensive case in the wrapper). The plan § Run interdicts and § "Run" do not require this broad catch (Pydantic already rejects >72-byte passwords, so `hash_password` cannot raise in normal flow). It is defensive, but a future maintainer may not realise the order of `except` blocks matters — putting the broad catch first would mask `IntegrityError`. No bug today; style. |

## Not verified (manual follow-ups, low priority)

- **No real PostgreSQL run**: the test suite uses SQLite in-memory. The plan declares D3 deviation (Index over UniqueConstraint) is accepted by both SQLite and PostgreSQL, and the generated SQL is valid. A human should boot the dev environment (`docker-compose up -d postgres`) and let `init_db()` create the table, then `psql` and `\d users` to confirm the index.
- **No end-to-end curl smoke**: the plan § T5.4 marks the manual curl as optional. A human should run `uvicorn app.main:app --reload` and `curl -X POST http://localhost:8000/api/auth/register -H 'Content-Type: application/json' -d '{"pseudo":"ali","password":"correcthorse"}'` to confirm 201 in a real server.
- **No concurrent race verification**: the bypassed-precheck test simulates the race via monkeypatch. A human could verify with `concurrent.futures.ThreadPoolExecutor` submitting 2 requests with the same pseudo and asserting 201 + 409 (not 201 + 500). Low value vs the unit test.
- **bcrypt cost timing**: 12 rounds is claimed to be ~250ms. A human could benchmark on the target hardware.

## Checkpoint questions for the next story (s13)

- The major finding (missing rollback test) is a natural follow-up: add it to s13 in `test_auth_register.py` (or split as a follow-up quick fix). It's not blocking the ship.
- The minor finding #2 (misnamed test) is a clean-up that can happen in s13 or in a quick fix.

Max severity: major
Ship allowed: yes
