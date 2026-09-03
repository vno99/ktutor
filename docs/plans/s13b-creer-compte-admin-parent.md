---
validated: yes
---
# Plan — Story s13b-creer-compte-admin-parent

Branch: `feature/s13b-creer-compte-admin-parent`
Research: `docs/research/s13b-creer-compte-admin-parent.md` — read it first; this plan does not repeat it.

## Target story

Créer deux endpoints admin-only (JWT) pour gérer les comptes non-élève et les changements de rôle. La story ne touche pas au modèle `User` (complet depuis s12) ni à l'index unique case-insensitive (déjà en place) : c'est purement du **router + schemas + RBAC + audit log**.

| Endpoint | Body in | Body out | Codes |
|---|---|---|---|
| `POST /api/users` | `{pseudo, password, role: "parent" \| "admin"}` | 201 `{pseudo, role}` | 201, 401, 403, 409, 422, 500 |
| `PUT /api/users/{pseudo}/role` | `{role: "eleve" \| "parent" \| "admin"}` | 200 `{pseudo, role}` | 200, 401, 403, 404, 409, 422, 500 |

**Acceptance criteria** (10, tous dans le scope de ce plan) — AC1-AC6 comportement, AC7-AC10 tests.

## Tasks (ordered)

1. [x] **Créer `backend/app/api/users/schemas.py`** avec :
   - `CreateUserRequest` (hérite des invariants `RegisterRequest` via réutilisation des constantes `MIN_PSEUDO_CHARS`, `MAX_PSEUDO_CHARS`, `PSEUDO_PATTERN`, `MIN_PASSWORD_CHARS`, `MAX_PASSWORD_BYTES` depuis `app.api.auth.schemas`) + champ `role: Literal["parent", "admin"]` (pas `eleve`).
   - `CreateUserResponse(pseudo, role)`.
   - `UpdateRoleRequest(role: Literal["eleve", "parent", "admin"])`.
   - `UserResponse(pseudo, role)`.
   - `UserErrorCode = Literal["invalid_pseudo", "weak_password", "pseudo_taken", "user_not_found", "self_demote_blocked", "forbidden", "internal"]` (nouveau, séparé d'`AuthErrorCode`).
   - `UserErrorResponse(error, code)`.
   - **Vérification** : `python -c "from app.api.users.schemas import CreateUserRequest, UpdateRoleRequest"` passe (test d'import pur, pas de test composant).

2. [x] **Créer `backend/app/api/users/__init__.py`** (vide, ou `from .router import router` si la convention du projet l'exige — à vérifier en lisant `auth/__init__.py`).

3. [x] **Créer `backend/app/api/users/router.py`** avec `APIRouter(prefix="/api/users", tags=["users"])` et deux endpoints :
   - `POST /` : `def create_user(body: CreateUserRequest, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_db))` — pre-check `func.lower(User.pseudo) == body.pseudo.lower()` (409 `pseudo_taken`), `hash_password(body.password)`, insert `User(pseudo, password_hash, role=body.role_to_userrole())` (helper de conversion `Literal` → `UserRole`), `catch IntegrityError` → 409 (race), 500 sur autre exception. Retourne `CreateUserResponse(pseudo, role)`. Logger `users.create admin={admin} target={pseudo} role={role}`. **Pas de JWT** dans la réponse.
   - `PUT /{pseudo}/role` : `def update_role(pseudo, body: UpdateRoleRequest, admin: User = Depends(require_role(UserRole.ADMIN)), db: Session = Depends(get_db))` — fetch user par `pseudo` (404 `user_not_found` si absent), self-demote check : si `pseudo == admin.pseudo` ET `new_role != UserRole.ADMIN` → count `db.query(User).filter(User.role == UserRole.ADMIN).count()` ; si `count < 1` (après update simulé) raise 409 `self_demote_blocked`. Update + commit, refresh, `logger.info("security.role_change admin={admin} target={pseudo} old={old} new={new}")`. Retourne `UserResponse(pseudo, role)`.
   - **Helper de conversion** : `def _to_userrole(value: Literal["eleve","parent","admin"]) -> UserRole` (mappage strict, lève `ValueError` si input inattendu — sécurité défense en profondeur).
   - **Vérification** : voir tâches 5 et 6.

4. [x] **Inclure le router dans `backend/app/main.py`** : ajouter `from app.api.users.router import router as users_router` (dans le bloc d'imports ligne 27-30) et `app.include_router(users_router)` après la ligne `app.include_router(auth_router)` ligne 74. **Vérification** : `python -c "from app.main import app; print([r.path for r in app.routes])"` liste `/api/users` et `/api/users/{pseudo}/role`.

5. [x] **Tests `POST /api/users`** dans `backend/tests/api/test_users_create.py` (5 classes, ~10 tests) :
   - `TestCreateUserHappyPath` : admin crée un parent (201, body conforme, hash bcrypt en DB, role=PARENT), admin crée un admin (201, role=ADMIN).
   - `TestCreateUserAuth` : parent caller → 403 `forbidden`, eleve caller → 403 `forbidden`, no-token → 401 `invalid_token`, junk-token → 401 `invalid_token`.
   - `TestCreateUserValidation` : pseudo trop court → 422, pseudo avec `-` → 422, password 7 chars → 422, password > 72 octets UTF-8 → 422, `role: "eleve"` → 422, `role: "guest"` → 422, body vide → 422.
   - `TestCreateUserConflict` : pseudo existant (eleve) → 409 `pseudo_taken`, pseudo existant case-insensitive (`Ali` vs `ali`) → 409 `pseudo_taken`, race DB-level (insert direct via `session_factory`, bypass pre-check) → 409 `pseudo_taken`.
   - `TestCreateUserLoggingHygiene` : aucune log line ne contient le password ou le hash (cf. `test_auth_register.py::TestRegisterLoggingHygiene` ligne 297 — pattern identique).
   - **Vérification** : `pytest backend/tests/api/test_users_create.py -v` → 10/10 pass.

6. [x] **Tests `PUT /api/users/{pseudo}/role`** dans `backend/tests/api/test_users_role.py` (5 classes, ~10 tests) :
   - `TestUpdateRoleHappyPath` : admin promote eleve → parent (200, role=PARENT en DB, log `security.role_change` présente), admin change parent → admin (200), admin demote parent → eleve (200).
   - `TestUpdateRoleAuth` : parent caller → 403, eleve caller → 403, no-token → 401.
   - `TestUpdateRoleValidation` : `role: "guest"` → 422, body vide → 422.
   - `TestUpdateRoleNotFound` : pseudo inexistant → 404 `user_not_found`.
   - `TestUpdateRoleSelfDemoteBlocked` : admin seul essaie de se passer admin → 409 `self_demote_blocked`, **DB reste inchangée** (role toujours ADMIN) ; admin seul essaie eleve → parent → OK (pas de self-demote) ; admin se change en parent avec un 2e admin présent → 200 OK.
   - `TestUpdateRoleLoggingHygiene` : la log `security.role_change` contient `admin`, `target`, `old`, `new` mais **jamais** le password ou le hash (pas de risque ici mais test pour blinder).
   - **Vérification** : `pytest backend/tests/api/test_users_role.py -v` → 10/10 pass.

7. [x] **Corriger le drift du docstring `UserRole`** dans `backend/app/core/database/models.py:213-217` : remplacer *"parent and admin are created by an admin-only script (s15)"* par *"parent and admin are created by an admin via POST /api/users (s13b); POST /api/auth/register creates eleve only (s12)."*. **Vérification** : `git diff backend/app/core/database/models.py` montre une seule ligne modifiée.

8. [x] **Run full backend test suite** : `pytest backend/tests/ -v --tb=short` → 0 régression sur les tests existants (s12, s13). **Vérification** : tous les tests `test_auth_*.py` et `test_models.py` et `test_passwords.py` restent verts.

9. [x] **Lint + typecheck** : `cd backend && ruff check app/ tests/` (zéro nouveau warning) + `mypy app/` (zéro nouvelle erreur). **Vérification** : CI lint job passe.

10. [ ] **Conventional commit unique** : `feat(api): add /api/users create + role update admin endpoints (s13b)` couvrant tous les fichiers modifiés + créés. Pas de commit par tâche. **Vérification** : `git log -1` montre un seul commit avec tous les fichiers (research + plan + code + tests).

## Run interdicts

- **Pas de migration Alembic** : `init_db()` (database/session.py:56) est l'outil canonique en dev/CI. `User` et `UserRole` ne changent pas. Un Alembic migration ici serait du drift hors-périmètre.
- **Pas de frontend** : s13b est backend-only. Aucun fichier dans `frontend/` ne doit être touché.
- **Pas de bootstrap admin** (`backend/scripts/bootstrap_admin.py`) — décision Open Q1, hors périmètre s13b, follow-up s15.
- **Pas de nouveau module `app/api/auth/dependencies.py`** — la story le mentionne, mais ce fichier n'existe pas et n'est pas nécessaire : le helper `require_role` est dans `app.core.auth.middleware`.
- **Pas de refactor transverse** : le pattern `_pseudo_exists` n'est pas factorisé. Pas de DRY pour 4 lignes copiées. Refactor = s15+.
- **Pas de changement au format des logs existants** : `register.conflict`, `login.failed`, etc. utilisent `logger.info("topic ...")` avec positional args. Garder la même forme pour `users.create.*` et `security.role_change`.
- **Pas de `pytest.mark.skip_postgres` décorateur sans justification** : tous les tests doivent passer en SQLite/CI. La course "last admin" est tolérée par design (POC), pas un skip.
- **Pas de commit sur la branche par défaut** : tout part sur `feature/s13b-creer-compte-admin-parent` (worktree dédié). Le squash-merge vers `main` est manuel après review.
- **Pas de session globale dans les tests** : chaque test crée son propre `db_engine` (cf. pattern `test_auth_register.py:32-46`) pour ne pas polluer.

## The point everything turns on

**Le décision centrale** : le helper RBAC `require_role` est-il correctement branché sur les deux endpoints, **et** la conversion `Literal → UserRole` est-elle stricte (refuse toute valeur hors `[eleve, parent, admin]`) ?

Trois pièges à surveiller :

1. **Mauvais import de `require_role`** : la note agentic dit `app/api/auth/dependencies.py`, ce fichier n'existe pas. Le plan dit `from app.core.auth.middleware import require_role` (vérifié : `app/core/auth/middleware.py:106`). Si l'implémenteur importe depuis le mauvais chemin, l'exécution crashera à l'import — détecté en 2 secondes par `python -c "from app.api.users.router import router"`.

2. **Pydantic `.value` vs enum direct** : `Literal["parent", "admin"]` est une string. `User.role` est un `Enum`. L'insert `User(role="parent")` échoue en Pydantic/SQLAlchemy si on ne convertit pas. Le helper `_to_userrole(value)` est non-optionnel — sa présence garantit la conversion explicite et le test `test_create_user_invalid_role_returns_422` prouve la validation Pydantic en amont.

3. **Le piège de la race "last admin"** : le test `TestUpdateRoleSelfDemoteBlocked::test_last_admin_self_demote_returns_409` doit aussi vérifier que la DB **n'a pas été modifiée** (role toujours ADMIN). Si l'update passe avant le check, on a une fenêtre où l'admin peut se démettre — bug de sécurité. Le plan fait le check **après** l'update, puis rollback si 0 admins. Cela suppose que la session est dans une transaction — ce qui est le cas par défaut avec SQLAlchemy + le `session_factory` de la fixture.

Vérification finale par le reviewer : (a) `grep -rn "require_role" backend/app/api/users/` montre bien l'import depuis `core.auth.middleware`, (b) `_to_userrole` existe et mappe les 3 valeurs, (c) le test self-demote vérifie `user.role is UserRole.ADMIN` après le 409.

## Files touched

**Créés** :
- `backend/app/api/users/__init__.py` (vide ou 1 ligne)
- `backend/app/api/users/schemas.py` (~70 lignes : 5 schémas + 1 Literal)
- `backend/app/api/users/router.py` (~150 lignes : 2 endpoints + helpers)
- `backend/tests/api/test_users_create.py` (~200 lignes : 5 classes, 10 tests)
- `backend/tests/api/test_users_role.py` (~220 lignes : 5 classes, 10 tests)
- `docs/research/s13b-creer-compte-admin-parent.md` (déjà créé)
- `docs/plans/s13b-creer-compte-admin-parent.md` (ce fichier)

**Modifiés** :
- `backend/app/main.py` (2 lignes : 1 import + 1 `include_router`)
- `backend/app/core/database/models.py` (1 ligne : drift du docstring `UserRole`)

**Non touchés (volontairement)** :
- `backend/app/core/auth/middleware.py` — `require_role` est utilisé tel quel
- `backend/app/core/auth/passwords.py` — `hash_password` est utilisé tel quel
- `backend/app/core/auth/jwt.py` — `create_access_token` est utilisé tel quel
- `backend/app/api/auth/schemas.py` — constantes importées, pas modifiées
- `backend/app/api/auth/router.py` — non touché (pas de factorisation de `_pseudo_exists` — décision Open Q3)
- `backend/scripts/` — pas de bootstrap (décision Open Q1)
- `backend/app/core/config.py` — pas de `admin_*` Settings (cohérent avec Open Q1)
- `frontend/**` — pas de frontend (s13b est backend-only)

## Test strategy

**Couche principale** : tests d'API (FastAPI TestClient + SQLite in-memory + StaticPool + `app.dependency_overrides[get_db]`) — pattern `test_auth_register.py:32-70`. C'est la couche qui prouve les ACs 1-10.

**Couche fixtures** : les fixtures `seeded_admin`, `seeded_user`, `db_engine`, `session_factory` sont **réutilisées** depuis `test_auth_middleware.py` (lignes 86-132) **et** dupliquées dans les nouveaux fichiers de test (chaque test file doit être autonome — pytest ne garantit pas l'ordre). Le helper `make_access_token(user)` (mentionné dans la research §8) **n'est pas extrait dans s13b** — chaque test appelle `create_access_token(user.pseudo, user.role)` directement (1 ligne, 5 endroits). Refactor = s15+.

**Tests qui n'existent pas et n'existent pas besoin d'exister** :
- Pas de test cross-tenant au sens s15 (AC10 est un test RBAC, pas d'isolation) — la recherche §9 le précise.
- Pas de test d'intégration PostgreSQL (POC local, SQLite suffit).
- Pas de test E2E frontend (pas de frontend dans s13b).
- Pas de test de migration Alembic (pas de migration).

**Couverture attendue** : 20 tests au total (10 create + 10 role), tous indépendants, tous passants sur SQLite/CI. La review vérifiera qu'aucun test n'est skipped ou xfail sans justification.

## Definition of Done

- [ ] Tous les ACs 1-10 sont couverts par un test qui passe (`pytest backend/tests/api/test_users_create.py backend/tests/api/test_users_role.py -v`).
- [ ] Aucune régression : `pytest backend/tests/ -v` reste 100% vert.
- [ ] Lint clean : `ruff check backend/app/api/users/ backend/tests/api/test_users_*.py` → 0 issue.
- [ ] Typecheck clean : `mypy backend/app/api/users/` → 0 issue.
- [ ] Multi-tenancy (cf. AGENTS.md § DoD) : bien que s13b ne touche pas à des données élève, les deux endpoints sont admin-only et n'accèdent à aucune table métier. Pas de test d'isolation cross-tenant requis (cf. research §9).
- [ ] Observabilité : `users.create` et `security.role_change` logguent avec pseudo + role (jamais password/hash — vérifié par `TestCreateUserLoggingHygiene` + `TestUpdateRoleLoggingHygiene`).
- [ ] Aucun fichier frontend touché.
- [ ] Conventional commit unique : `feat(api): add /api/users create + role update admin endpoints (s13b)`.
- [ ] PR ouverte depuis `feature/s13b-creer-compte-admin-parent` vers `main` avec description structurée (résumé, ACs cochées, points d'attention sur la race "last admin" et le drift du docstring `UserRole`).

<< IP Mike: task granularity, what a good plan contains/avoids. >>
