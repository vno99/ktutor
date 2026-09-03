---
name: research-s13b-creer-compte-admin-parent
description: Research pour la story s13b — endpoints admin POST /api/users et PUT /api/users/{pseudo}/role, vérifiée contre l'état réel post-s12/s13.
metadata:
  type: research
  story: s13b-creer-compte-admin-parent
  generated: 2026-09-03
---

# Research — Story s13b-creer-compte-admin-parent

## The five structuring facts

1. **`require_role(UserRole.ADMIN)` existe déjà et est testé** dans `backend/app/core/auth/middleware.py:106` (helper) et `backend/tests/api/test_auth_middleware.py:122,243` (fixture `seeded_admin` + test). La story l'utilise **telle quelle** — pas besoin d'un nouveau module `app/api/auth/dependencies.py` comme la note agentic le suggère. Drift à corriger au planning : importer depuis `app.core.auth.middleware`.

2. **Le modèle `User` + l'enum `UserRole` + l'index unique case-insensitive sont complets** dans `backend/app/core/database/models.py:210-280`. `role` accepte `ELEVE | PARENT | ADMIN` (ligne 219-221). Le `UserRole` docstring (ligne 213) dit encore *"parent and admin are created by an admin-only script (s15)"* — c'est une **fausse prémisse mineure** que s13b va invalider ; le docstring sera mis à jour en même temps que le code (pas un blocker, juste un drift de commentaire).

3. **Aucun fichier `backend/app/api/users/` n'existe** — tout l'auth est dans `app/api/auth/`. La story crée ce sous-domaine (`__init__.py` + `router.py` + `schemas.py`) et inclut le router dans `app/main.py:27-29` selon la convention existante (`app.include_router(auth_router)`). Convention d'inclusion : 1 ligne par router, en bas de `main.py`.

4. **Pas de bootstrap admin** dans `backend/scripts/` (seul `generate_jwt_keys.py` y est). ADR 005 ligne 42 annonce `scripts/bootstrap_admin.py` lisant `ADMIN_PSEUDO`/`ADMIN_PASSWORD` du `.env`, mais le script n'a pas été créé en s12. **Pour s13b** : une fixture pytest `seeded_admin` (déjà présente dans `test_auth_middleware.py:122`) suffit à valider les 10 ACs. Le script de bootstrap est un **follow-up de s15** — hors périmètre de s13b. **Pas de nouveau champ `Settings.admin_*` requis** pour s13b.

5. **Schemas `RegisterRequest` réutilisables partiellement** (`backend/app/api/auth/schemas.py:44-72`) : validation pseudo (3-32 chars, `^[a-zA-Z0-9_]+$`) + password (8+ chars, ≤ 72 octets UTF-8) sont déjà codées. Le nouveau `CreateUserRequest` peut soit hériter de `RegisterRequest` (en ajoutant le champ `role`), soit composer via des champs partagés. L'**AC1** impose `role: "parent" | "admin"` (pas `eleve`) — c'est un `Literal` strict, pas un `UserRole` libre. L'**AC5** impose `role: "eleve" | "parent" | "admin"` pour le PUT (inclut eleve). Les deux sont des `Literal` distincts pour éviter qu'un admin crée un `eleve` par erreur sur `POST /api/users`.

## Target story

Créer deux endpoints admin-only (JWT) :

- `POST /api/users` — body `{pseudo, password, role: "parent" | "admin"}` → 201 `{pseudo, role}`. 403 si l'appelant n'est pas admin, 409 si pseudo pris, 422 si validation échoue.
- `PUT /api/users/{pseudo}/role` — body `{role: "eleve" | "parent" | "admin"}` → 200 `{pseudo, role}`. 403 si non-admin, 404 si user inexistant, 409 si l'admin tente de se démettre lui-même et qu'il est le dernier admin.

Acceptance criteria (10) — tous couvrables par les patterns existants, **aucun nouveau schéma de données** requis. La story n'ajoute aucune table, aucune colonne, aucun index. Elle n'altère ni `User` ni `UserRole`. C'est purement du **router + schemas + RBAC + audit log**.

## Current state of the code

| Fichier | État | Rôle pour s13b |
|---|---|---|
| `backend/app/core/database/models.py:210-280` | Complet | `User`, `UserRole`, index unique case-insensitive — réutilisés tels quels. Mettre à jour le docstring `UserRole` ligne 213. |
| `backend/app/core/auth/middleware.py:58,106` | Complet | `get_current_user` + `require_role` — réutilisés tels quels. |
| `backend/app/core/auth/jwt.py` | Complet | `create_access_token(pseudo, role)` — utilisé dans les fixtures tests. |
| `backend/app/core/auth/passwords.py` | Complet | `hash_password` — réutilisé pour hasher le password du nouveau user. |
| `backend/app/api/auth/router.py` | Complet (s12 + s13) | Référence de structure (router, error payloads, logger.info hygiene). |
| `backend/app/api/auth/schemas.py` | Complet (s12 + s13) | Constantes à importer (`MIN_PSEUDO_CHARS`, `MAX_PSEUDO_CHARS`, `PSEUDO_PATTERN`, `MIN_PASSWORD_CHARS`, `MAX_PASSWORD_BYTES`, `AuthErrorCode` pour `forbidden`). |
| `backend/app/main.py:27,74` | Complet | Ajouter `from app.api.users.router import router as users_router` + `app.include_router(users_router)`. |
| `backend/app/api/users/` | **N'existe pas** | À créer : `__init__.py` + `router.py` + `schemas.py`. |
| `backend/scripts/` | Contient `generate_jwt_keys.py` | Pas de bootstrap à ajouter (cf. fait 4). |
| `backend/tests/api/test_auth_middleware.py:107,122` | Complet | Pattern reproductible : `seeded_user` (eleve) + `seeded_admin` existent — fournir aussi `seeded_parent`. |
| `backend/tests/conftest.py` | Complet | `db_engine` + `session_factory` + `client` disponibles. Pas de helper commun "forge token for role" — à extraire dans s13b pour réutilisation s14+. |

## Anchor points

- **Nouveaux fichiers** :
  - `backend/app/api/users/__init__.py` (vide ou exporte `router`)
  - `backend/app/api/users/router.py` (~150 lignes attendues : deux endpoints + helpers)
  - `backend/app/api/users/schemas.py` (~50 lignes : `CreateUserRequest`, `CreateUserResponse`, `UpdateRoleRequest`, `UserResponse`, `UserErrorResponse`, `UserErrorCode`)
  - `backend/tests/api/test_users_create.py` (~150 lignes : 4-5 tests)
  - `backend/tests/api/test_users_role.py` (~200 lignes : 6-8 tests)
- **Fichiers modifiés** :
  - `backend/app/main.py` — ajouter `import users_router` + `app.include_router(users_router)`
  - `backend/app/core/database/models.py` — mettre à jour le docstring `UserRole` (drift)
- **Fichiers réutilisés sans modification** : `models.py` (User, UserRole), `auth/middleware.py` (require_role, get_current_user), `auth/passwords.py` (hash_password), `auth/schemas.py` (constantes pseudo/password, AuthErrorCode).

## Verified APIs / functions

| Nom | Signature | Localisation | Comportement vérifié |
|---|---|---|---|
| `require_role` | `(*allowed: UserRole) -> Callable` | `app/core/auth/middleware.py:106` | Reçoit 1+ `UserRole`, retourne une dependency FastAPI. Élève 403 `forbidden` si le rôle du `User` résolu n'est pas dans l'allow-list. 401 `invalid_token` si le JWT est invalide (filtré par `get_current_user` en interne). |
| `get_current_user` | `(authorization: str \| None, db: Session) -> User` | `app/core/auth/middleware.py:58` | Lit `Authorization: Bearer <token>`, décode via `decode_token`, fetch le `User` par `sub`. Élève 401 sur tout échec. |
| `hash_password` | `(plain: str) -> str` | `app/core/auth/passwords.py:37` | Bcrypt cost 12, refuse > 72 octets UTF-8 (lève `ValueError`). |
| `User.pseudo` | `Mapped[str]` PK | `app/core/database/models.py:243` | PK, `String(32)`. |
| `User.role` | `Mapped[UserRole]` | `app/core/database/models.py:252` | Enum, default `ELEVE`. |
| `UserRole.ELEVE` / `.PARENT` / `.ADMIN` | enum | `app/core/database/models.py:219-221` | Valeurs `"eleve"`, `"parent"`, `"admin"`. |
| `create_access_token` | `(pseudo: str, role: UserRole, expires_delta: timedelta \| None) -> str` | `app/core/auth/jwt.py:136` | Signe un JWT RS256 avec claims `{sub, role, iat, exp, jti, type: "access"}`. |
| Index `uq_users_pseudo_lower` | `Index(func.lower(User.pseudo), unique=True)` | `app/core/database/models.py:276-280` | Case-insensitive uniqueness au niveau DB. Couvre la race condition sur la création. |
| `MIN_PSEUDO_CHARS` / `MAX_PSEUDO_CHARS` / `PSEUDO_PATTERN` | constantes | `app/api/auth/schemas.py:24-26` | 3, 32, `^[a-zA-Z0-9_]+$`. À importer dans `users/schemas.py` (DRY). |
| `MIN_PASSWORD_CHARS` / `MAX_PASSWORD_BYTES` | constantes | `app/api/auth/schemas.py:29-30` | 8 chars, 72 octets. À importer. |
| `AuthErrorCode` | `Literal[...]` | `app/api/auth/schemas.py:100-106` | Inclut `"forbidden"`. À réutiliser dans `UserErrorCode` (élargi avec les nouveaux codes). |

## Traps & constraints

1. **Fausse prémisse dans la story** : la note agentic dit "extend `app/api/auth/dependencies.py` (RBAC helper for 'admin only')". Ce fichier **n'existe pas** — le helper est dans `app/core/auth/middleware.py`. Le plan doit importer depuis le bon module. **Pas un blocker** : le helper existe, c'est juste le chemin d'import qui est différent.

2. **Drift dans le docstring `UserRole`** (`models.py:213`) : dit que `parent`/`admin` sont créés par un "admin-only script (s15)". s13b invalide cette assertion. Le plan doit inclure une mise à jour du docstring (1 ligne, scope minimal).

3. **Race condition "last admin"** (AC6) : un admin qui se démet doit être bloqué s'il est le dernier. Trois approches :
   - **(a)** Lock pessimiste : `SELECT ... FOR UPDATE` sur la row de l'admin, count, update. SQLite ne supporte pas `FOR UPDATE` (no-op silencieux), PostgreSQL oui. → **ne marche pas en CI** qui tourne sur SQLite.
   - **(b)** Transaction sérialisable : `db.begin()` + count + update + commit. SQLite : `BEGIN IMMEDIATE` verrouille en écriture. PostgreSQL : `SERIALIZABLE` isolation. → **marche partout** mais alourdit.
   - **(c)** Count + check + update dans une seule transaction avec `SELECT ... FOR UPDATE` seulement sur PostgreSQL, et un check défensif sur SQLite. → **recommandé** : portable, le test SQLite prouve le cas nominal, le test PostgreSQL (manual, non bloquant) prouve le lock. Pour le POC, **(c) avec une variante pragmatique** suffit : un `db.query(User).filter(role=ADMIN).count() >= 1` après l'update, et si 0 on raise 409 + rollback. C'est une course tolérable (POC local, peu d'admins simultanés).

4. **`POST /api/users` ne doit pas émettre de JWT** (story ligne 723) — l'admin créé doit se logger via `POST /api/auth/login` (s13). Donc `CreateUserResponse` n'expose que `{pseudo, role}` — pas de token.

5. **Pseudo uniqueness span tous rôles** (story ligne 722) : si un eleve `"alice"` existe, l'admin ne peut pas créer un parent `"Alice"` (case-insensitive). L'index `uq_users_pseudo_lower` (models.py:276) couvre déjà ce cas. Le router doit faire le même pre-check que `register()` (auth/router.py:103) puis `catch IntegrityError` (auth/router.py:127). **Code copy-paste-friendly** : extraire un helper `_pseudo_exists(db, pseudo) -> bool` serait bien mais **pas obligatoire** pour s13b — le plan peut dupliquer le pattern.

6. **Le role dans le JWT d'un user qui change de rôle** : si un admin promeut un eleve en parent, ses access tokens existants portent encore `role: "eleve"` (le rôle est dans le payload signé). Au prochain refresh, `decode_token` lira `sub`, fetchera le user (avec son nouveau rôle), et créera un nouveau token avec le rôle frais (cf. `auth/router.py:303`). Donc un changement de rôle prend effet au prochain refresh, pas immédiatement. C'est le comportement attendu (et c'est dans le docstring `refresh` ligne 257). **Pas un piège pour s13b**, juste un fait à connaître pour les tests.

7. **Audit log** (AC9) : "role update is logged (audit trail entry)". Le pattern est déjà `logger.info("security.role_change ...", ...)` (aligné sur le `register.conflict`, `login.failed`, etc. dans `auth/router.py`). **Une ligne par endpoint** suffit, pas de table `AuditLog` (story ligne 719 dit "simple log line"). Format suggéré : `security.role_change admin={admin} target={pseudo} old={old} new={new}`. Le `admin.pseudo` vient du `user: User = Depends(require_role(UserRole.ADMIN))`.

8. **Test fixtures "admin / parent / eleve"** : `test_auth_middleware.py:107,122` fournit `seeded_user` (eleve) et `seeded_admin`. Il faut ajouter `seeded_parent` dans le même fichier (ou dans `conftest.py` si on extrait). **Recommandation** : laisser dans `test_auth_middleware.py` pour rester proche, et créer un helper `make_access_token(user)` dans `conftest.py` (utilisé 3+ fois par les tests s13b, et sera réutilisé par s14+).

9. **Pas de test cross-tenant s13b** : AC10 dit "a `parent` user (not admin) gets 403 on these endpoints". C'est un test **RBAC**, pas un test cross-tenant au sens s15. Le piège serait de le ranger dans un test d'isolation alors que c'est un test d'autorisation. → test dans `test_users_create.py::TestCreateUserAuthorization::test_parent_caller_gets_403` (et pareil pour `test_users_role.py`).

10. **Pas de migration Alembic à créer** : `init_db()` (database/session.py:56) est utilisé en dev/CI. La story ne touche pas au schéma, donc aucun migration. (Conforme au note des models s12 "no Alembic migration is needed because init_db() applies the full Base metadata in dev/CI", models.py:165-166.)

11. **Le piège ADR 011 (s15)** : "le pseudo du body est spoofable avant s15". **Hors périmètre de s13b** : s13b ne s'occupe que d'admin, et l'admin ne peut pas se faire passer pour un autre (il a un JWT signé). La story est safe **by virtue of using JWT auth exclusively** — pas de `pseudo` dans le body pour ces endpoints. À expliciter dans le plan pour qu'un futur lecteur ne tente pas d'ajouter `pseudo_from_body` par commodité.

12. **Préfixe router** : `auth/router.py:46` utilise `router = APIRouter(prefix="/api/auth", tags=["auth"])`. Convention : `users/router.py` doit être `APIRouter(prefix="/api/users", tags=["users"])`. Les endpoints dans le router sont alors `/` (pour `POST /api/users`) et `/{pseudo}/role` (pour `PUT /api/users/{pseudo}/role`).

## Open questions

1. **Le script `bootstrap_admin.py` (ADR 005 ligne 42) est-il dans le périmètre de s13b ou repoussé à s15 ?** Mon avis : **hors périmètre s13b**. Les 10 ACs sont satisfaits par des fixtures pytest. Le script bootstrap n'est nécessaire que pour le tout premier démarrage en prod, et s15 (RBAC + multi-tenancy) traitera l'admin global. À confirmer avec l'utilisateur au planning. Si "oui, dans s13b" → ajouter une tâche pour le script + champs `Settings.admin_pseudo` / `Settings.admin_password` + variables `.env.example`.

2. **Faut-il factoriser un helper `_pseudo_exists(db, pseudo) -> bool` partagé entre `auth/router.py::register` et `users/router.py::create_user` ?** Mon avis : **non pour s13b**, duplication tolérée (2 endroits, 4 lignes). Refactor transverse = s15+. Si l'utilisateur veut DRY stricte, extraire dans `app/services/users/lookup.py` — mais c'est un service sans logique métier, donc borderline.

3. **La race condition "last admin"** : option (c) pragmatique (count + check + rollback en cas de 0) suffit-elle, ou faut-il un lock pessimiste ? Mon avis : option (c) pour le POC. Le test SQLite couvre le cas nominal ; un test manuel PostgreSQL peut être ajouté en commentaire `pytest.mark.skip_postgres` pour suivre la progression. À trancher au planning.

4. **`UserErrorCode` réutilise-t-il `AuthErrorCode` ou est-il un nouveau `Literal` ?** Mon avis : **nouveau** `UserErrorCode = Literal["invalid_pseudo", "weak_password", "pseudo_taken", "user_not_found", "self_demote_blocked", "forbidden", "internal"]`. Le code `"forbidden"` est dupliqué entre `AuthErrorCode` et `UserErrorCode` — c'est OK, le router sérialise dans le bon schéma (`UserErrorResponse`). Pas de hiérarchie de codes dans Pydantic, donc duplication assumée.

## Real complexity

**Verdict : 3** (identique à `docs/stories.md`).

Pourquoi 3 et pas 2 :
- 2 endpoints avec 4-5 tests d'autorisation croisés chacun (admin/parent/eleve/unauthenticated)
- 1 piège non-trivial (race condition "last admin")
- 1 helper à extraire (make_access_token) réutilisé 3+ fois dans les tests
- 1 drift à corriger en passant (docstring `UserRole`)

Pourquoi pas 4 :
- Le RBAC est déjà codé (1 ligne d'usage)
- Le modèle est déjà complet
- L'index unique couvre déjà la race sur la création
- L'audit log = 1 ligne par write
- ~12-15 tests au total, pas 25+

Pas de split proposé.

## Split proposal

N/A — complexité 3, plan estimée < 10 tâches, shippable en un cycle.

<< IP Mike: exploration method, what a good research always verifies. >>
