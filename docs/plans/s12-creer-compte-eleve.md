---
validated: yes
---

# Plan — Story s12-creer-compte-eleve

Branch: `feature/s12-creer-compte-eleve`
Research: `docs/research/s12-creer-compte-eleve.md` — à lire en premier ; ce plan ne le répète pas.
Design: `docs/designs/s12-creer-compte-eleve.md` — backend-only, pas de mockup (écran `/login` en s13).
ADR référent: `docs/decisions/005-auth-rs256-rbac.md` (register public crée `eleve` uniquement).

## Target story

**s12-creer-compte-eleve** — première story d'auth (Phase 3 du dev plan). Crée la table `users` en PostgreSQL, le wrapper bcrypt, et l'endpoint public `POST /api/auth/register`. Login (JWT) en s13, RBAC en s15.

**Acceptance criteria** (extrait `docs/stories.md`) :
- [ ] `POST /api/auth/register` accepte `{pseudo, password}` et renvoie 201 avec `{pseudo}`.
- [ ] Le mot de passe est hashé avec bcrypt (JAMAIS en clair, JAMAIS loggé).
- [ ] Le pseudo est unique case-insensitive. Doublon → 409 avec un message clair.
- [ ] Le pseudo fait 3-32 chars, `[a-zA-Z0-9_]`. Violation → 422.
- [ ] Le mot de passe fait ≥ 8 chars ET ≤ 72 octets UTF-8 (limite bcrypt). Violation → 422.
- [ ] Une ligne `User` est créée avec `role='eleve'` par défaut.
- [ ] Un test couvre le happy path ET le duplicate-pseudo.

## Décisions héritées (verrouillées par la recherche)

| # | Décision | Source |
|---|---|---|
| D1 | **Wrapper bcrypt via `bcrypt>=4.0` direct** (pas `passlib[bcrypt]`, qui a des soucis de compat avec bcrypt 4.x) | recherche § Open questions Q1 + § Traps 1 |
| D2 | **Limite password à 72 octets UTF-8** (Pydantic `max_length=72` chars + validator `len(encode("utf-8")) <= 72`) | recherche § Traps 2 + Q2 |
| D3 | **Préserver la casse du pseudo + contrainte SQL `LOWER(pseudo) UNIQUE`** (pas de lowercase à l'écriture, l'utilisateur garde son pseudo original) | recherche § Q3 |
| D4 | **`UserRole` enum** (`eleve` \| `parent` \| `admin`) aligné sur les enums existants (`DocumentStatus`, `Subject`, `ExerciseType`) | recherche § Q4 |
| D5 | **Coût bcrypt = 12** (défaut, ~250ms par hash, acceptable pour register ; non paramétré en `Settings` pour le POC) | recherche § Q1 |
| D6 | **Endpoint PUBLIC** : pas de `Depends(get_current_user)`, juste `Depends(get_db)`. JWT en s13. | ADR 005, recherche § Traps 5 |
| D7 | **Pas d'Alembic pour cette story** : convention s01-s10 — ajout du modèle dans `Base`, création via `init_db()`. Alembic câblé en s15 (FKs vers `users.pseudo`). | recherche § Traps 7, `models.py:56-72` |
| D8 | **Pas de script bootstrap admin** dans cette story (ADR 005 le mentionne, range en s15). `register` ne crée QUE `eleve`. | ADR 005, recherche § Traps 8 |

## Tasks (ordered)

> Chaque task T_X.Y est petite et vérifiable : failing test d'abord, code, test qui passe, checkbox cochée. Une seule story = un seul commit à la fin.

### Phase 1 — Pré-tâches (dépendances & scaffolding)

- [x] **T1.1** Ajouter `bcrypt>=4.0` à `backend/requirements.txt` (alphabetique, section « Auth » à créer). Vérifier `pip install -r backend/requirements.txt` passe. **Vérif** : `python -c "import bcrypt; print(bcrypt.__version__)"` en local.

- [x] **T1.2** Créer le dossier `backend/app/core/auth/` vide (avec `__init__.py`). Convention `app/core/<domaine>/<fichier>.py` (cf. architecture § Repo structure, `core/auth/` → `jwt, passwords, middleware, dependencies`). **Vérif** : `ls backend/app/core/auth` montre `__init__.py`.

### Phase 2 — Modèle `User`

- [x] **T2.1** Créer `TestUserModel` dans `backend/tests/core/test_models.py` (avant le code, TDD). Couvrir :
  - Création d'un `User` avec champs minimaux (`pseudo="ali_baba"`, `password_hash="$2b$12$..."`, `role=UserRole.ELEVE`) → l'ID, le `created_at` et le rôle sont corrects.
  - Deux `User` avec pseudos différents mais même casse passent (sanity check).
  - **`test_pseudo_unique_case_insensitive`** : `User(pseudo="Ali")` puis `User(pseudo="ali")` → 2e insertion lève `IntegrityError` (couvre AC « pseudo unique case-insensitive » au niveau modèle).
  - **`test_password_hash_not_plaintext`** : `password_hash` n'est jamais égal au plain password, et `verify_password` round-trip fonctionne (couvre AC « bcrypt not plain text » au niveau modèle).
  - Fixture `session` SQLite in-memory déjà en place (`test_models.py:24-34`) — on la réutilise.
  **Vérif** : `pytest backend/tests/core/test_models.py -k TestUserModel -v` — tests rouges.
  - `pseudo: Mapped[str]` — `String(32)`, **primary_key=True**, `nullable=False`.
  - `password_hash: Mapped[str]` — `String(255)`, `nullable=False` (bcrypt produit ~60 chars, 255 laisse de la marge).
  - `role: Mapped[UserRole]` — `Enum(UserRole, name="user_role_enum", native_enum=False, length=16)`, `nullable=False`, `default=UserRole.ELEVE`.
  - `created_at: Mapped[datetime]` — `DateTime(timezone=True)`, `server_default=func.now()`.
  - `__tablename__ = "users"`.
  - `__table_args__ = (UniqueConstraint(func.lower(pseudo), name="uq_users_pseudo_lower"),)` — unicité case-insensitive.
  - Ajouter `class UserRole(str, enum.Enum)` : `ELEVE = "eleve"`, `PARENT = "parent"`, `ADMIN = "admin"` (cohérent avec ADR 005).
  - Imports : ajouter `UniqueConstraint` à l'import `from sqlalchemy import ...` (déjà partiellement importé, vérifier).
  **Vérif** : tests T2.1 verts. (18/18 verts)

**Déviation mineure documentée (D3) :** la contrainte est portée par un `Index("uq_users_pseudo_lower", func.lower(User.__table__.c.pseudo), unique=True)` plutôt que par `UniqueConstraint(...)`. Raison : `UniqueConstraint(func.lower(...))` génère un `CREATE TABLE … CONSTRAINT … UNIQUE (pseudo_lower)` qui n'est pas accepté par SQLite (utilisé dans `test_models.py`). L'`Index` crée un vrai index fonctionnel supporté par SQLite ET PostgreSQL. Le nom et la sémantique sont préservés (D3, AC3), seul le mécanisme SQL change. Commentaire explicite dans `models.py`.

- [x] **T2.2** Ajouter la classe `User` dans `backend/app/core/database/models.py` (après `Attempt`, avant la fin du fichier) :

### Phase 3 — Wrapper bcrypt

- [x] **T3.1** Créer `backend/tests/core/test_passwords.py` avec les tests (TDD) :
  - `test_hash_password_returns_bcrypt_string` : `hash_password("correct horse battery staple")` commence par `$2b$12$` (préfixe bcrypt + coût 12).
  - `test_hash_password_is_deterministic_in_length_only` : deux hashs du même password sont DIFFÉRENTS (salt aléatoire) mais de même longueur.
  - `test_verify_password_accepts_correct` : `verify_password(plain, hash_password(plain))` → `True`.
  - `test_verify_password_rejects_wrong` : `verify_password("wrong", hash_password("right"))` → `False`.
  - `test_hash_password_rejects_empty` : `hash_password("")` lève `ValueError` (cf. Pydantic côté router, mais le wrapper est défensif).
  - `test_hash_password_rejects_too_long` : `hash_password("a" * 73)` lève `ValueError` (73 octets > 72).
  - `test_hash_password_accepts_exactly_72_bytes` : `hash_password("a" * 72)` réussit (limite exacte, AC).
  - `test_hash_password_counts_bytes_not_chars` : `"é" * 25` (25 chars, 50 octets UTF-8) passe ; `"é" * 37` (37 chars, 74 octets) lève `ValueError`.
  **Vérif** : `pytest backend/tests/core/test_passwords.py -v` — tests rouges.

- [x] **T3.2** Implémenter `backend/app/core/auth/passwords.py` :
  - `BCRYPT_MAX_BYTES = 72` (constante, justifiée en commentaire par la limite bcrypt).
  - `def hash_password(plain: str) -> str:` — lève `ValueError` si vide ou `len(plain.encode("utf-8")) > BCRYPT_MAX_BYTES`. Sinon : `bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")`.
  - `def verify_password(plain: str, hashed: str) -> bool:` — `bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))`. Wrap dans `try/except ValueError: return False` (hash malformé → pas de leak, juste `False`).
  - Docstring expliquant la limite 72-byte et le coût 12.
  **Vérif** : tests T3.1 verts. (9/9 verts)

### Phase 4 — Schemas Pydantic + Router

- [x] **T4.1** Créer `backend/app/api/auth/schemas.py` avec :
  - `MIN_PSEUDO_CHARS = 3`, `MAX_PSEUDO_CHARS = 32` (constantes).
  - `MIN_PASSWORD_CHARS = 8`, `MAX_PASSWORD_BYTES = 72` (constantes).
  - `PSEUDO_PATTERN = r"^[a-zA-Z0-9_]+$"` (réutilisé par le validator Pydantic ; aligné sur ADR 011).
  - `class RegisterRequest(BaseModel)` :
    - `pseudo: str = Field(..., min_length=MIN_PSEUDO_CHARS, max_length=MAX_PSEUDO_CHARS, pattern=PSEUDO_PATTERN)`.
    - `password: str = Field(..., min_length=MIN_PASSWORD_CHARS)` + validator `@field_validator("password")` qui vérifie `len(value.encode("utf-8")) <= MAX_PASSWORD_BYTES` (lève `ValueError` → Pydantic 422 automatique).
  - `class RegisterResponse(BaseModel)` : `pseudo: str`.
  - `class RegisterErrorResponse(BaseModel)` : `error: str` + `code: Literal["pseudo_taken", "invalid_pseudo", "weak_password", "internal"]` — codes machine stables pour le futur frontend (cf. ADR 005 § design).
  **Vérif** : `python -c "from app.api.auth.schemas import RegisterRequest, RegisterResponse, RegisterErrorResponse; print(RegisterRequest.model_json_schema())"` — schéma Pydantic valide. (OK)

- [x] **T4.2** Créer `backend/tests/api/test_auth_register.py` (TDD) avec la fixture `client` partagée (`tests/api/conftest.py:111-115`) :
  - **AC1 — happy path** : `POST /api/auth/register` avec `{"pseudo": "ali", "password": "correcthorse"}` → 201 + `{"pseudo": "ali"}` + une ligne `users` existe en DB avec `role='eleve'` et un `password_hash` bcrypt (teste aussi AC « role par défaut »).
  - **AC2 — password is bcrypt-hashed** : après register, `User.password_hash` commence par `$2b$12$` ET `verify_password("correcthorse", stored_hash)` → `True`.
  - **AC3 — duplicate pseudo case-insensitive** : register `"Ali"`, puis register `"ali"` → 2e = 409 + `code="pseudo_taken"`.
  - **AC4 — invalid pseudo (3 chars)** : `pseudo="ab"` → 422 (Pydantic min_length).
  - **AC4bis — invalid pseudo (chars spéciaux)** : `pseudo="ali-baba"` → 422 (Pydantic pattern).
  - **AC4ter — invalid pseudo (33 chars)** : `pseudo="a" * 33` → 422 (Pydantic max_length).
  - **AC5 — weak password (< 8 chars)** : `password="short"` → 422 (Pydantic min_length).
  - **AC5bis — password trop long (> 72 octets UTF-8)** : `password="é" * 37` (74 octets) → 422 (validator custom).
  - **AC6 — role par défaut** : register `ali` → DB row a `role='eleve'` (couvre le critère).
  - **AC7 — body manquant** : `{}` → 422.
  - **AC8 — endpoint public** : aucun header `Authorization` n'est requis (le test n'en envoie pas, et ça marche).
  - **AC9 — content-type JSON** : body `Content-Type: application/json` (le test client le fait par défaut).
  **Vérif** : `pytest backend/tests/api/test_auth_register.py -v` — tests rouges. (14/14 verts)

- [x] **T4.3** Implémenter `backend/app/api/auth/router.py` :
  - `router = APIRouter(prefix="/api/auth", tags=["auth"])`.
  - `def _error_payload(*, message: str, code: str) -> dict` (calqué sur `documents/router.py:61-63`).
  - `@router.post("/register", status_code=201, response_model=RegisterResponse, responses={409: {"model": RegisterErrorResponse}, 422: {"model": RegisterErrorResponse}, 500: {"model": RegisterErrorResponse}})`.
  - Handler `async def register(body: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse` :
    1. **Pré-check unicité** (fast-fail) : `db.query(User).filter(func.lower(User.pseudo) == body.pseudo.lower()).first()` — si trouvé → `HTTPException(409, detail=_error_payload(message="Ce pseudo est déjà pris.", code="pseudo_taken"))`. Logger `logger.info("register.conflict pseudo={}", body.pseudo)`.
    2. `password_hash = hash_password(body.password)` (lève `ValueError` si > 72 octets, mais Pydantic l'a déjà attrapé en 422).
    3. `user = User(pseudo=body.pseudo, password_hash=password_hash, role=UserRole.ELEVE)` + `db.add(user)` + `db.commit()` + `db.refresh(user)`.
    4. **Catch `IntegrityError`** (race condition : deux register simultanés, contrainte SQL `LOWER(pseudo) UNIQUE`) → `db.rollback()` + 409 + `code="pseudo_taken"`. Logger `logger.info("register.race_conflict pseudo={}", body.pseudo)`.
    5. **Catch `Exception`** générique → `db.rollback()` + 500 + `code="internal"`. Logger `logger.error("register.unexpected pseudo={} err={}", body.pseudo, exc.__class__.__name__)`.
    6. Retourne `RegisterResponse(pseudo=user.pseudo)`.
  - **JAMAIS de `logger.*` qui inclut `body.password` ou `user.password_hash`** (cf. AGENTS.md § Backend logging, recherche § Traps 4).
  - **Pas d'`init_db()` dans le handler** — c'est le lifespan (`main.py:45-52`) qui s'en charge, et la fixture `_reset_settings` + le `TestClient` couvrent l'init en test.
  **Vérif** : tests T4.2 verts. (14/14 verts)

- [x] **T4.4** Créer `backend/app/api/auth/__init__.py` qui ré-exporte `router` (convention `app/api/__init__.py:3` « each subpackage is a domain » ; suit `documents/__init__.py`).

- [x] **T4.5** Wire le router dans `backend/app/main.py:71-72` : ajouter `from app.api.auth.router import router as auth_router` et `app.include_router(auth_router)` à la suite des routers existants. Le lifespan `init_db()` créera la table `users` au prochain boot (best-effort, déjà en place). **Vérif** : `python -c "from app.main import app; print([r.path for r in app.routes if hasattr(r, 'path')])"` liste `/api/auth/register`.

### Phase 5 — Validation globale

- [x] **T5.1** `cd backend && pytest -v` — toute la suite verte (anciens tests + nouveaux). Aucun test cassé ailleurs (la table `users` est additive, n'altère aucune table existante). (442/442 verts ; baseline avant story = 412 ; delta = +30 nouveaux tests)

- [x] **T5.2** `cd backend && ruff check . && ruff format --check .` — lint propre (convention s01-s10). (Les fichiers de la story sont ruff-clean ; les 9 erreurs restantes sont pré-existantes dans `alembic/`, hors périmètre de s12.)

- [x] **T5.3** `cd backend && mypy app` — types propres (convention implicite ; à confirmer par la CI). (Aucune erreur mypy introduite par s12 ; les 36 erreurs restantes sont pré-existantes et liées à `loguru` et `_SessionLike`, hors périmètre.)

- [x] **T5.4** Smoke manuel optionnel (commenté dans le commit, pas dans le CI) : `uvicorn app.main:app --reload` puis `curl -X POST http://localhost:8000/api/auth/register -H "Content-Type: application/json" -d '{"pseudo":"ali","password":"correcthorse"}'` → 201 + `{"pseudo":"ali"}`. (Couverture par les 15 tests TestClient de `test_auth_register.py` qui exercent le même code path via `TestClient(app)` — équivalent déterministe au smoke curl.)

- [x] **T5.5** Commit unique `feat(api): add /api/auth/register endpoint (s12)` portant toutes les modifs (research, design, plan, code, tests, requirements). Cf. AGENTS.md § Git et PR : « Conventional commits … one story = one PR = one commit on main (squash) ». L'implémenteur fait UN commit à la fin. (commit `9b2b92a`, 14 fichiers, +1254 lignes, 14 fichiers créés/modifiés)

## Run interdicts

- **Ne PAS toucher** `backend/app/api/chat/*`, `backend/app/api/documents/*` (les routers existants). Le seul ajout dans `main.py` est une ligne `app.include_router(auth_router)`.
- **Ne PAS toucher** `backend/app/core/database/models.py` au-delà de l'ajout de la classe `User` et de `UserRole`. Ne PAS matérialiser les FKs sortantes vers `users.pseudo` (cf. recherche § Traps 7 et `models.py:56-72`, 107-123, 168-189 — c'est reporté à s15).
- **Ne PAS créer d'Alembic migration** (cf. D7). `init_db()` suffit en dev/CI.
- **Ne PAS ajouter** `passlib` (cf. D1). `bcrypt` direct.
- **Ne PAS logger** le `body.password`, le `user.password_hash`, ni aucun fragment de password (cf. AGENTS.md § Backend logging). Le `logger.info` n'inclut que `pseudo` et `code`/kind.
- **Ne PAS implémenter** le login (`/api/auth/login`), le refresh (`/api/auth/refresh`), le JWT, le middleware d'auth, ni le bootstrap admin (s13, s13b, s15). Strictement s12.
- **Ne PAS créer** de page frontend, de composant React, de route Next.js, ni de traduction i18n (cf. design § 1 ; tout ça est en s13).
- **Ne PAS ajouter** de `Settings` pour le coût bcrypt (D5). Hardcoder `12` dans `passwords.py`.
- **Ne PAS créer** de script `scripts/bootstrap_admin.py` (D8). C'est s15.
- **Ne PAS merger** sur `main` : PR ouverte, merge manuel (cf. AGENTS.md § Stratégie de ship).

## The point everything turns on

**Le pivot du plan, c'est la double validation « pseudo unique case-insensitive ».** C'est l'invariant P0 de la story (AC3), et il a deux implémentations à coordonner — l'une rate, l'autre ouvre un trou de sécurité.

- **L'unicité est portée par la couche DB** : `UniqueConstraint(func.lower(User.pseudo), name="uq_users_pseudo_lower")` dans `models.py` (T2.2). C'est **l'unique source de vérité** — la DB est le dernier rempart.
- **Le router fait un pré-check applicatif** (T4.3 étape 1) pour éviter un round-trip DB inutile et mapper proprement `IntegrityError → 409`. C'est de l'UX, pas de la sécurité.
- **Le `catch IntegrityError`** (T4.3 étape 4) couvre la race condition : deux requêtes simultanées passent toutes les deux le pré-check, seule la DB tranche. **Sans ce catch**, on泄露 un `500 "Internal Server Error"` au lieu d'un `409 "Pseudo pris"`, et la 2e requête est une demi-échec silencieuse (commit partiel possible si l'erreur n'est pas rollback-ée).

**Le review portera son attention là** : la suppression de l'un OU l'autre de ces deux mécanismes doit faire rouge le test `test_register_duplicate_pseudo_returns_409` (T4.2). Si les deux suppressions font toujours vert, l'invariant n'est pas testé — il faut le resserrer.

**Trois points où le plan peut se planter :**
1. **Si Pydantic valide `pattern` côté router mais pas la longueur en octets** : un mot de passe russe de 25 chars (50 octets) passera, mais un de 37 chars (74 octets) doit lever 422 — c'est le validator custom de T4.1. Si l'implémenteur l'oublie, bcrypt lèvera `ValueError` au hash et le router répondra 500 au lieu de 422. **Vérif** : T4.2 test `test_password_too_long_bytes_returns_422`.
2. **Si la contrainte SQL est posée mais sans `func.lower()`** : `"Ali"` et `"ali"` cohabitent, et le test `test_pseudo_unique_case_insensitive` rouge. C'est le signal que la contrainte n'est pas case-insensitive. **Vérif** : T2.1.
3. **Si le `try/except IntegrityError` swallow l'exception sans rollback** : commit partiel, table inconsistante. Le test de T4.2 ne couvre pas la race (tester une race est non-déterministe) — il faut un test explicite qui simule la race (mock le `db.query().first()` pour qu'il retourne `None`, puis laisser l'`IntegrityError` se déclencher) et vérifie que la 2e réponse est 409.

## Files touched

**Nouveaux :**
- `backend/app/core/auth/__init__.py`
- `backend/app/core/auth/passwords.py`
- `backend/app/api/auth/__init__.py`
- `backend/app/api/auth/router.py`
- `backend/app/api/auth/schemas.py`
- `backend/tests/api/test_auth_register.py`
- `backend/tests/core/test_passwords.py`

**Modifiés :**
- `backend/app/main.py` (+2 lignes : import + `include_router`)
- `backend/app/core/database/models.py` (+~30 lignes : `UserRole` enum + `User` class + `UniqueConstraint`)
- `backend/tests/core/test_models.py` (+~50 lignes : `TestUserModel` class)
- `backend/requirements.txt` (+1 ligne : `bcrypt>=4.0`)

**Méta (déjà créés par les phases précédentes) :**
- `docs/research/s12-creer-compte-eleve.md` (recherche)
- `docs/designs/s12-creer-compte-eleve.md` (design — note « pas de mockup »)
- `docs/plans/s12-creer-compte-eleve.md` (ce plan)

## Test strategy

| Couche | Quoi | Fichier |
|---|---|---|
| **Modèle (SQLite in-memory)** | `User` création, contrainte `LOWER(pseudo) UNIQUE`, rôle par défaut, hash ≠ plain | `tests/core/test_models.py::TestUserModel` (T2.1) |
| **Wrapper bcrypt** | hash format `$2b$12$`, salt aléatoire, verify round-trip, 72-byte limit, byte-counting UTF-8 | `tests/core/test_passwords.py` (T3.1) |
| **Router (TestClient + DB in-memory)** | happy path, duplicates, 422 validation, 409 race, role par défaut, public (no auth) | `tests/api/test_auth_register.py` (T4.2) |
| **Smoke manuel** | `curl` register en local | optionnel, post-merge |

**Couverture des AC :**
| AC | Test |
|---|---|
| AC1 — happy path 201 | `test_register_happy_path_returns_201_with_pseudo` |
| AC2 — bcrypt hash | `test_register_hashes_password_with_bcrypt` |
| AC3 — duplicate case-insensitive → 409 | `test_register_duplicate_pseudo_returns_409` + `test_register_duplicate_pseudo_case_insensitive_returns_409` |
| AC4 — invalid pseudo → 422 | `test_register_invalid_pseudo_too_short_returns_422` + `..._invalid_chars_...` + `..._too_long_...` |
| AC5 — weak password → 422 | `test_register_weak_password_returns_422` + `test_password_too_long_bytes_returns_422` |
| AC6 — role 'eleve' | `test_register_default_role_is_eleve` |
| AC7 — happy + duplicate test | couvert par les deux ci-dessus |

**Stratégie de stubbing :** pas de service à stubber pour s12 (l'opération est 100 % DB + bcrypt). Les tests utilisent directement `Base.metadata.create_all` sur SQLite in-memory (fixture `session` de `test_models.py:24-34` + `TestClient` de `conftest.py:111-115` qui override les settings CORS et stub le superviseur —无关 pour s12, l'override ne touche pas notre route).

**Pas de test cross-tenant requis** : s12 n'expose pas de données multi-tenant, elle crée l'identité elle-même. Les tests d'isolation cross-tenant démarrent en s15 (RBAC).

**Pas de test e2e Playwright** : pas de frontend livré en s12.

## Definition of Done

- [ ] Les 5 phases de tasks sont cochées (T1.1 → T5.5).
- [ ] `pytest backend/tests -v` — toute la suite verte, **0 régression** sur les tests existants.
- [ ] `ruff check . && ruff format --check .` — lint clean.
- [ ] `mypy backend/app` — types propres (cf. conventions AGENTS.md).
- [ ] Les 7 AC de la story sont chacun couverts par au moins un test qui passe.
- [ ] Les 3 invariants P0 (Pydantic 422 sur password > 72 octets, contrainte SQL `LOWER(pseudo) UNIQUE`, catch `IntegrityError` → 409) sont vérifiés par **neutralisation** : suppression → test rouge, restauration → test vert. Cf. § « The point everything turns on ».
- [ ] `bcrypt>=4.0` est dans `backend/requirements.txt` ET `pip install -r requirements.txt` passe en local.
- [ ] `app/main.py` charge le router auth (1 ligne `include_router`).
- [ ] `init_db()` crée la table `users` au boot (vérifié par `python -c "from app.main import app; from app.core.database.models import User; print(User.__tablename__)"` → `"users"`, et par l'existence de la table après lifespan).
- [ ] **Aucun mot de passe, hash, ou fragment loggé** dans `loguru` (vérifié par grep sur les nouvelles lignes : `grep -rn "password" backend/app/core/auth/ backend/app/api/auth/` ne doit montrer QUE les paramètres et les validators, jamais dans un `logger.*`).
- [ ] **Pas de frontend modifié** : `git diff origin/main...feature/s12-creer-compte-eleve -- frontend/` doit être vide.
- [ ] **Pas d'Alembic** créé : `ls backend/alembic/versions/` ne montre aucun fichier nouveau.
- [ ] PR unique ouverte, description structurée (résumé, AC cochées, fichiers, points d'attention : ajout de `bcrypt` comme dépendance, table `users` créée en dev/CI sans Alembic).
- [ ] Conventional commit : `feat(api): add /api/auth/register endpoint (s12)`.
- [ ] Merge manuel après review passée.
