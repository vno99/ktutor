---
id: s13-login-eleve
title: Research — Se connecter et obtenir un JWT
date: 2026-09-03
status: ready
---

# Research — Story s13-login-eleve

## The five structuring facts

1. **`User` rows already exist (s12 merged)** — `backend/app/core/database/models.py:269+` (post-merge) declares `User(pseudo PK String(32), password_hash String(255), role UserRole, created_at)` + `UserRole {ELEVE, PARENT, ADMIN}`. `indexes.py` includes `Index("uq_users_pseudo_lower", func.lower(User.__table__.c.pseudo), unique=True)`. No Alembic migration in `backend/alembic/versions/` — `init_db()` is the single source of truth (D7 s12).
2. **`hash_password(plain) -> str` and `verify_password(plain, hashed) -> bool` are ready** in `backend/app/core/auth/passwords.py`. Bcrypt cost = 12 hardcoded. `BCRYPT_MAX_BYTES = 72` enforced inside `hash_password`. The wrapper does NOT log the password or the hash (no `logger.*` call references either).
3. **`POST /api/auth/register` is wired and reachable** — `backend/app/api/auth/router.py` exposes it, `main.py:71-72` mounts the router (`app.include_router(auth_router)`), and the dependency `get_db` is overridable per-test (cf. `tests/api/test_auth_register.py:55-70` for the in-memory SQLite + StaticPool pattern). The endpoint creates only `role=UserRole.ELEVE` (D8 s12, ADR 005).
4. **No JWT infra exists yet** — no `pyjwt` in `requirements.txt`, no `cryptography` explicit dep, no `Settings` knobs for `jwt_*`, no `get_current_user`/`require_role` dependencies, no in-process middleware, no `./keys/` directory, no `scripts/generate_jwt_keys.py`. The frontend has `useAuthStore` (cookie-backed pseudo, ADR 011) but **no token storage** and **no axios interceptor** (`frontend/lib/api.ts` is a plain axios client with no auth).
5. **The frontend has a `(public)/[locale]/` group, not `(auth)/`** — `frontend/app/(public)/[locale]/layout.tsx` wraps pages in `<NextIntlClientProvider>` + `<Header>` and assumes the pseudo is read from a non-HttpOnly cookie `pseudo` (ADR 011). The `(auth)/` group mentioned in the architecture doc is **not created** — the story needs to add it (or use `(public)/[locale]/(authed)/`).

## Target story

**s13-login-eleve — Se connecter et obtenir un JWT**
As an **élève** I want **me connecter avec mon pseudo + mot de passe** so that **je reçoive un JWT à utiliser pour les requêtes authentifiées**.

**Acceptance criteria** (verbatim, `docs/stories.md` lines 658-668) :

- `POST /api/auth/login` accepts `{pseudo, password}` and returns `{access_token, refresh_token, token_type: "bearer", expires_in}`.
- The access token is a JWT signed with RS256 (private key from env, never from the codebase).
- The access token expires in 30 minutes (from `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` env).
- The refresh token expires in 7 days.
- `POST /api/auth/refresh` accepts a refresh token and returns a new access token (and rotates the refresh token).
- A wrong password returns 401 with a generic "invalid credentials" message (do not leak whether the pseudo exists).
- The access token contains the claims: `sub` (pseudo), `role`, `iat`, `exp`.
- A test verifies a valid login returns a JWT decodable to the expected claims.
- A test verifies an expired token is rejected by the middleware.

**Complexity (story)** : 3 — JWT generation (RS256) + refresh tokens + expiration + middleware.

## Current state of the code

### Files that EXIST and are usable for s13 (verified, not assumed)

| File | What it provides | Used by s13? |
|---|---|---|
| `backend/app/core/auth/passwords.py` | `hash_password`, `verify_password`, `BCRYPT_MAX_BYTES = 72` | yes (login) |
| `backend/app/core/database/models.py` | `User`, `UserRole` (ELEVE/PARENT/ADMIN) | yes (login) |
| `backend/app/core/database/session.py` | `get_db`, `init_db`, `get_engine` | yes |
| `backend/app/api/auth/router.py` | `register` endpoint (POST /api/auth/register) | reference pattern |
| `backend/app/api/auth/schemas.py` | `RegisterRequest`, `RegisterResponse`, `RegisterErrorResponse` | reference pattern |
| `backend/app/main.py` | mounts auth_router | yes (add login/refresh routers) |
| `backend/tests/api/conftest.py` | `client` + supervisor stub fixtures | yes (extend with auth fixtures) |
| `backend/tests/api/test_auth_register.py` | SQLite in-memory + StaticPool + `app.dependency_overrides[get_db]` pattern | yes (replicate verbatim for login) |
| `frontend/lib/api.ts` | `apiClient` (axios, baseURL = NEXT_PUBLIC_API_URL) | yes (add JWT interceptor) |
| `frontend/lib/stores/authStore.ts` | `useAuthStore` (pseudo, hydrated, setPseudo, clearPseudo) | yes (extend with tokens) |
| `frontend/app/(public)/[locale]/layout.tsx` | `<Header>` + `<NextIntlClientProvider>` | yes (use as layout base for the new /login page) |
| `frontend/messages/fr.json` and `en.json` | i18n catalogs | yes (add `auth` namespace) |
| `frontend/components/Input.tsx`, `Label.tsx`, `Button.tsx`, `Card.tsx` | design system | yes (login form) |
| `backend/requirements.txt` | adds `bcrypt>=4.0` (s12) | yes (add `pyjwt`, `cryptography`) |

### Files that DO NOT EXIST (must be created)

| Path | Purpose | From ADR / Story |
|---|---|---|
| `backend/app/core/auth/jwt.py` | `create_access_token`, `create_refresh_token`, `decode_token` (RS256), `hash_token_for_blacklist` | ADR 005, s13 AC |
| `backend/app/core/auth/middleware.py` | `get_current_user`, `require_role` (decorator) | ADR 005 |
| `backend/app/core/auth/token_blacklist.py` | in-memory set, `add(jti)`, `is_revoked(jti)` | ADR 005 (POC: in-memory, prod: Redis) |
| `backend/app/api/auth/login.py` (or `router.py` extension) | `POST /api/auth/login` | s13 AC1 |
| `backend/app/api/auth/refresh.py` (or `router.py` extension) | `POST /api/auth/refresh` | s13 AC5 |
| `backend/app/api/auth/schemas.py` (extend) | `LoginRequest`, `LoginResponse`, `RefreshRequest`, `RefreshResponse`, `AuthErrorResponse` | new |
| `backend/scripts/generate_jwt_keys.py` | generates `./keys/jwt_private.pem` + `./keys/jwt_public.pem` (RSA 2048, idempotent) | ADR 005 § Bootstrap, **NOT in s13 AC** |
| `./keys/jwt_private.pem` (gitignored) + `./keys/jwt_public.pem` (gitignored) | RS256 keys | ADR 005 |
| `backend/tests/api/test_auth_login.py` | login + refresh + middleware + expired-token tests | s13 AC9 |
| `backend/tests/core/test_jwt.py` | `create_access_token` shape, RS256 signature, decode, blacklist | new |
| `frontend/app/(public)/[locale]/login/page.tsx` | login form (pseudo + password, link to /register) | story intent |
| `frontend/lib/api.ts` (modify) | add `Authorization: Bearer <access_token>` interceptor + 401-refresh-on-retry | ADR 005 |

### Settings to add (s13)

The current `backend/app/core/config.py` has no `jwt_*` knobs. Required additions (per ADR 005 + AC2/AC3/AC4) :

```python
# Auth — JWT (s13)
jwt_private_key_path: str = "./keys/jwt_private.pem"  # gitignored
jwt_public_key_path: str = "./keys/jwt_public.pem"     # gitignored
jwt_algorithm: str = "RS256"                            # pinned, never None
jwt_access_token_expire_minutes: int = 30              # AC3
jwt_refresh_token_expire_days: int = 7                 # AC4
```

> **Note** : AC2 says "private key from env, never from the codebase". The convention (ADR 005) is "path to a file on disk, generated at first launch by `scripts/generate_jwt_keys.py`". The path is read from `.env`. In production, the key would come from a secret manager. For the POC, the path-based loader is acceptable.

### Env vars to add to `.env.example` (and `frontend/.env.example` if needed)

```
# Auth (s13)
JWT_PRIVATE_KEY_PATH=./keys/jwt_private.pem
JWT_PUBLIC_KEY_PATH=./keys/jwt_public.pem
JWT_ALGORITHM=RS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
```

## Anchor points

| File | Hook | What s13 plugs in |
|---|---|---|
| `backend/app/main.py:71-72` | `app.include_router(auth_router)` | extend router or add separate `login_router` + `refresh_router` |
| `backend/app/core/config.py:10-162` | `class Settings(BaseSettings)` | add 5 `jwt_*` fields |
| `backend/app/core/auth/passwords.py:6-37` | `hash_password`, `verify_password` | `login` endpoint uses `verify_password` |
| `backend/app/core/database/models.py:269+` | `User` model | `login` queries by `LOWER(pseudo)` |
| `backend/app/core/database/session.py:61-67` | `get_db` | `login`/`refresh` endpoints depend on it |
| `backend/tests/api/conftest.py:101-108` | `app.dependency_overrides[...]` pattern | override `get_current_user` for tests of protected endpoints |
| `backend/tests/api/test_auth_register.py:32-70` | `db_engine` + `session_factory` + `client` fixtures | copy verbatim for `test_auth_login.py` |
| `frontend/lib/api.ts:13-19` | `apiClient` | add JWT request interceptor + 401-refresh response interceptor |
| `frontend/lib/stores/authStore.ts:44-70` | `useAuthStore` | add `accessToken`, `refreshToken`, `setTokens`, `clearTokens` |
| `frontend/app/(public)/[locale]/layout.tsx:38` | `<Header />` | add logout button (when hydrated + tokens present) |
| `frontend/messages/fr.json` + `en.json` | i18n catalogs | add `auth.*` namespace |
| `frontend/components/Input.tsx`, `Label.tsx`, `Button.tsx`, `Card.tsx` | design system | login form |

## Verified APIs / functions

I read each of these in the current `origin/main` (post-merge) before writing the report. Names, signatures, locations are real, not assumed.

- `app.core.auth.passwords.hash_password(plain: str) -> str` — `passwords.py:6-22`. Encodes to UTF-8, raises `ValueError` if empty or > 72 bytes, returns `bcrypt.hashpw(...).decode("utf-8")`.
- `app.core.auth.passwords.verify_password(plain: str, hashed: str) -> bool` — `passwords.py:25-37`. Wraps `bcrypt.checkpw`, returns `False` on `ValueError` (e.g. malformed hash).
- `app.core.database.models.User` — `models.py:269-307`. PK = `pseudo: String(32)`, has `password_hash`, `role: UserRole`, `created_at`.
- `app.core.database.models.UserRole` — `models.py:255-260`. `ELEVE="eleve"`, `PARENT="parent"`, `ADMIN="admin"`.
- `app.core.database.models.Index("uq_users_pseudo_lower", ...)` — `models.py:312-322` (D3 s12). SQLite + PostgreSQL compatible functional index on `LOWER(pseudo)`.
- `app.core.database.session.get_db()` — `session.py:61-67`. `Generator[Session, None, None]`, FastAPI dependency. Used by every endpoint that touches the DB.
- `app.core.config.Settings` — `config.py:10-162`. 25+ knobs, no `jwt_*` yet.
- `app.api.auth.router` — `api/auth/router.py:21-138`. `APIRouter(prefix="/api/auth", tags=["auth"])`, has `register` (POST) only.
- `app.api.auth.schemas.RegisterRequest` / `RegisterResponse` / `RegisterErrorResponse` — `api/auth/schemas.py:13-79`. Reference pattern for the new `LoginRequest` / `LoginResponse` / etc.
- `app.main.app` — `main.py:57-72`. `FastAPI(...)` with `CORSMiddleware` (origins = `settings.cors_allow_origins_list`), `app.include_router(auth_router)`.
- `frontend.lib.stores.useAuthStore` — `frontend/lib/stores/authStore.ts:52-70`. Zustand store, `pseudo`/`hydrated`/`setPseudo`/`clearPseudo`, cookie-backed.
- `frontend.lib.api.apiClient` — `frontend/lib/api.ts:13-19`. `axios.create({ baseURL, headers: { Accept: 'application/json' } })`. No interceptors.

## Traps & constraints

1. **`JWT_ALGORITHM=none` attack** (Piège 4) — the JWT library accepts a `algorithms=["RS256"]` whitelist on decode. If the verifier passes `algorithms=None` (or relies on the token's `alg` header), an attacker can forge a token with `alg: none`. **Piège** : pin `algorithms=["RS256"]` explicitly in every `jwt.decode(...)` call. The plan must enforce this in a single helper (`decode_token(...)` in `core/auth/jwt.py`) so a single function enforces the whitelist.
2. **Wrong-password timing leak** (Piège 6) — AC6 says "do not leak whether the pseudo exists". The natural implementation does `if not user: raise 401` (fast) and `if not verify_password(...): raise 401` (slow). An attacker can time-attack the existence. Mitigation : always call `verify_password(plain, DUMMY_HASH)` when the user does not exist, to align timing. `verify_password` is constant-time (bcrypt). The plan must include a test that asserts the response time is similar for "user not found" vs "wrong password".
3. **Refresh token rotation vs access token reuse** (Piège 7) — `POST /api/auth/refresh` must reject an access token (and vice versa). Solution : a `type: "access" | "refresh"` claim in the JWT. The plan must add this claim to AC7 (the AC says `sub`, `role`, `iat`, `exp` only — the `type` claim is required for safety and is a non-breaking addition).
4. **Refresh token blacklist is in-memory** (ADR 005, Piège 5) — fine for `uvicorn` with `--workers 1` (dev), but breaks under multi-worker. The plan must document the limitation as a s15+ follow-up. **Alternative** : use the `jti` claim and check it in a `set[str]` in `app.core.auth.token_blacklist`. The set is per-process, which is acceptable for the POC. The plan must add `jti` to the access and refresh tokens, even if the AC doesn't list it (justification : enables the blacklist in s15+ and supports `POST /api/auth/logout` if s13 includes it — see Q4).
5. **`(auth)/` group does not exist in the frontend** — the architecture doc and the story assume it (s12 design says "écran `/login` mockupé en s13"), but only `(public)/[locale]/` exists. The plan must decide between (a) creating `frontend/app/(public)/[locale]/(authed)/login/page.tsx` or (b) creating `frontend/app/(auth)/[locale]/login/page.tsx` at the root. **(a)** is closer to the current code (the `(public)/[locale]/layout.tsx` already wraps `<Header />` and `<NextIntlClientProvider />` — perfect for the login page). **(b)** is the long-term plan (the `(auth)/` group is for login/register only, no header). **Recommendation** : (a) for s13 (minimal change), (b) in s15+ when the JWT migration is complete.
6. **Cookie `pseudo` vs JWT `sub`** — the frontend currently stores `pseudo` in a non-HttpOnly cookie. After s13, the source of truth for `pseudo` becomes the JWT (`/api/auth/me` decodes the token, or the authStore decodes locally). The cookie stays (ADR 011 § Migration) for backwards compatibility, but the `pseudo` field of the authStore is **redundant** with the JWT. The plan must decide: (a) keep both (cookie + JWT), (b) remove the cookie. **(a)** is less invasive and matches ADR 011's "transitional" wording. **Recommendation** : (a), document the cookie as deprecated.
7. **Token storage in the frontend** (Q1) — s13 cannot use HttpOnly cookies (the backend doesn't `Set-Cookie` yet — that's a s15+ concern). Tokens are in `localStorage` or in-memory. ADR 005 says "localStorage acceptable pour POC, à passer en cookie HttpOnly pour la prod". **Recommendation** : `localStorage` with a clear "POC only, XSS-risky" comment. The Zustand `authStore` should `hydrate()` from `localStorage` on mount and clear on `clearTokens()`. This is a documented debt for s15+.
8. **CORS with credentials** — `main.py:65-67` already has `allow_credentials=True`. The `cors_allow_origins` env is a single origin by default (`http://localhost:3000`). For s13 (no cookies), `allow_credentials=True` is a no-op (axios `withCredentials: false` is the default). For s15+ (cookies), this config is already aligned. **No action needed** in s13.
9. **`scripts/generate_jwt_keys.py` is not in s13's AC** (Q3) — but without it, the app cannot start in production-like mode (the keys are loaded from disk by `Settings.jwt_private_key_path`). The plan must include the script as a **supporting task** (not an AC). It's idempotent (skip if files exist), runs at first launch via a one-shot CLI, and is gitignored (the keys).
10. **`POST /api/auth/logout` is not in s13's AC** (Q4) — but the user-visible "se déconnecter" affordance is part of the login flow (otherwise the user cannot log out). Two options : (a) add a `POST /api/auth/logout` endpoint that blacklists the access token's `jti`, or (b) skip it and just `clearTokens()` on the frontend (no server-side revocation). **(a)** is more robust (an attacker with the access token cannot reuse it after logout), **(b)** is simpler. The plan must decide.
11. **Tests must be hermetic on RS256 keys** — generating RSA 2048 keys at every test is slow (~200ms each). The plan must either (a) generate keys once per session (pytest fixture with `scope="session"`), or (b) hardcode a pair of test keys in `tests/fixtures/jwt_test_*.pem` (committed, **safe because they are test-only**). **(a)** is simpler. **Recommendation** : (a) via a pytest fixture.
12. **Test for "expired token rejected"** (AC9) — must not sleep 31 minutes. The plan must construct a JWT with `exp = now - 1` directly (via `create_access_token` with an explicit `expires_delta`) and assert 401.
13. **The `pseudo` case is preserved in the JWT** — `User.pseudo` is stored case-preserved, the SQL `LOWER()` index is only for uniqueness. The JWT `sub` claim is the case-preserved pseudo. The login flow does NOT lowercase the input — it queries `LOWER(pseudo) == body.pseudo.lower()` and returns the case-preserved `User.pseudo` in the JWT. This matches s12's pattern (`User.pseudo` is the PK, no lowercasing on insert).
14. **`pytest-asyncio` for the FastAPI `TestClient`?** — `TestClient` is sync, no async needed. The existing tests use `TestClient(app)` synchronously. `pytest-asyncio` is in `requirements.txt` but not required for s13.
15. **Alembic** — s12 didn't create a migration (D7 s12). s13 must NOT create one either. `init_db()` creates the schema, including the (already-existing) `users` table. The plan must not introduce an Alembic migration.
16. **No password, hash, or token in any log** — `passwords.py` and the new `jwt.py` must follow the AGENTS.md § Backend logging rule. A grep for `logger\.(info|warning|error|debug).*(password|token|hash|jwt)` across the new files should return zero matches. The plan must include this as an explicit check.
17. **The `register` router coexists with the new login/refresh** — the existing `app/api/auth/router.py` has the register endpoint. The plan can either (a) extend the same router (clean, one file) or (b) split into `register.py` + `login.py` + `refresh.py` (matches the s09/s10 pattern of one file per endpoint family). **Recommendation** : (a) for s13, split in s15+ if the file grows. Or (b) split now to match the convention. The architecture doc and AGENTS.md say "un `router.py` par sous-domaine" — so (a). The plan should extend the existing file, not split.
18. **`/api/auth/logout` is a frontend-only operation in s13 if we pick (b) for Piège 10** — but the user clicks "Se déconnecter" somewhere. The plan must decide where (in the `<Header />`? as a separate page?). The convention is `<Header />` (the existing pseudo input becomes a logout button when tokens are present).

## Open questions

- **Q1 — Token storage in the frontend** : `localStorage` (XSS-vulnerable, persistent) or in-memory (lost on refresh, XSS-safer) ? ADR 005 says localStorage is acceptable for POC. **Recommendation** : localStorage, document the debt.
- **Q2 — authStore refacto** : keep both `pseudo` (cookie) and `tokens` (localStorage), or split into two stores, or migrate `pseudo` to be derived from the JWT ? **Recommendation** : one store, add `tokens`, keep `pseudo` as a cached copy (read from JWT decode on `hydrate()`).
- **Q3 — `scripts/generate_jwt_keys.py`** : in scope or out ? Not in s13's AC but required to run the app. **Recommendation** : include as a supporting task (idempotent, ~30 lines, no tests beyond "the script runs and produces two files").
- **Q4 — `POST /api/auth/logout`** : in scope or out ? Not in s13's AC but a real UX concern. **Recommendation** : include (small, ~10 lines + 1 test), with a `jti` blacklist.
- **Q5 — `jti` claim** : add to access and refresh tokens, even though the AC only lists `sub`/`role`/`iat`/`exp` ? **Recommendation** : yes, add `jti` (UUID) + `type` (`access` or `refresh`). Justification : enables the blacklist, enables logout, prevents access-vs-refresh swap (Piège 3). The AC "contains the claims X" doesn't forbid additional claims.
- **Q6 — CORS for credentials in s13 vs s15** — `allow_credentials=True` is already set. In s13, no cookies are exchanged (tokens in localStorage). In s15, cookies will be set by the backend. **No code change needed in s13** — the config is already aligned.

## Real complexity

**Score : 3, identical to the story. No split needed.**

Why 3, not 4 : the story is well-decomposed (3 endpoints + 1 middleware + 1 store refacto + 1 interceptor + ~6 test files). The conventions are in place (`router.py`, `schemas.py`, `dependency_overrides` test pattern, `useAuthStore` extension pattern). The dependencies are clear (s12's `User` + `passwords` + `register` are merged). The 9 ACs map 1-to-1 to tests.

Why not lower (2) : the RS256 key bootstrap (`generate_jwt_keys.py`) + the JWT blacklist + the in-memory vs Redis choice + the frontend store refacto + the i18n namespace add up to more than a "single endpoint + DB insert". The 3 score reflects that the story is **multi-layer** (backend + frontend + i18n + config) without being **multi-actor** (no new agent, no new RAG, no new model).

Why not higher (4-5) : no architectural choice is open. The ADR 005 has settled the algorithm, the claims, the rotation, the RBAC. The plan is mostly mechanical translation of ADR 005 + s13's AC.

**Split proposal** : **N/A.** The story is shippable in one cycle. Splitting would only make sense if the frontend and backend were decoupled (separate PRs), which the pipeline doesn't support (one story = one branch = one commit).

## Split proposal

N/A — score 3, one shippable cycle.

---

## Files that will be touched (preview for the Plan)

**Backend — new (4 files)** :
- `backend/app/core/auth/jwt.py` — `create_access_token`, `create_refresh_token`, `decode_token` (RS256, `jti` + `type` claims, blacklist check)
- `backend/app/core/auth/middleware.py` — `get_current_user` (Depends), `require_role` (decorator)
- `backend/app/core/auth/token_blacklist.py` — in-memory `set[str]` of revoked `jti`
- `backend/scripts/generate_jwt_keys.py` — idempotent RSA 2048 key generator
- `backend/tests/core/test_jwt.py` — token shape, RS256 signature, blacklist
- `backend/tests/api/test_auth_login.py` — login + refresh + logout + expired-token + wrong-password timing
- `backend/tests/api/test_auth_middleware.py` — `get_current_user`, `require_role`, expired, missing, malformed

**Backend — modified (3 files)** :
- `backend/app/core/config.py` — add 5 `jwt_*` knobs
- `backend/app/api/auth/schemas.py` — add `LoginRequest`, `LoginResponse`, `RefreshRequest`, `RefreshResponse`, `AuthErrorResponse`
- `backend/app/api/auth/router.py` — add `login`, `refresh`, `logout` endpoints
- `backend/app/main.py` — no change (router is already included)
- `backend/requirements.txt` — add `pyjwt[crypto]>=2.8` (pulls `cryptography` transitively)
- `backend/.env.example` + `.env.example` — add 5 `JWT_*` env vars

**Frontend — new (2 files)** :
- `frontend/app/(public)/[locale]/login/page.tsx` — login form (pseudo + password, link to /register)
- `frontend/app/(public)/[locale]/register/page.tsx` — registration form (was always announced in s12 but never built; s13 is the right time)

**Frontend — modified (3 files)** :
- `frontend/lib/api.ts` — JWT request interceptor + 401-refresh-on-retry response interceptor
- `frontend/lib/stores/authStore.ts` — add `accessToken`, `refreshToken`, `role`, `setTokens`, `clearTokens`, `decodeTokens` (or split)
- `frontend/components/Header.tsx` — when hydrated + tokens present, show "Se déconnecter" instead of the pseudo input
- `frontend/messages/fr.json` + `frontend/messages/en.json` — add `auth.*` namespace (login, logout, errors)

**Generated, gitignored (2 files)** :
- `./keys/jwt_private.pem` (RSA 2048, produced by `generate_jwt_keys.py`)
- `./keys/jwt_public.pem` (RSA 2048, produced by `generate_jwt_keys.py`)

**Total : 7 new + 7 modified + 2 generated.** This matches the typical s09/s10/s11 stories.
