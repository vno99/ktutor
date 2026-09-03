---
name: research-s14-lier-parent-enfant
description: Research pour la story s14 — endpoints parent-child POST /api/users/{parent_pseudo}/children et GET /api/users/{parent_pseudo}/children, vérifiée contre l'état réel post-s12/s13/s13b.
metadata:
  type: research
  story: s14-lier-parent-enfant
  generated: 2026-09-03
---

# Research — Story s14-lier-parent-enfant

## The five structuring facts

1. **`require_role(*UserRole)` n'est PAS la bonne dépendance pour s14** — la story autorise *à la fois* un admin et le parent lui-même (`JWT sub == parent_pseudo`). Le helper `get_current_user` (déjà dans `app.core.auth.middleware:58`) résout l'utilisateur, puis la logique handler compare `current_user.pseudo == parent_pseudo_in_url` OU `current_user.role is UserRole.ADMIN`. C'est le pattern "owner-or-admin", pas "admin-only". Utiliser `require_role(UserRole.ADMIN)` rejetterait à tort tous les parents.

2. **Aucun `ParentChildLink` n'existe** dans `backend/app/core/database/models.py` (vérifié : `git show origin/main:.../models.py | grep -E "ParentChildLink|parent_pseudo|child_pseudo"` retourne vide). Le modèle est greenfield, à créer sur le pattern des autres tables (`__tablename__`, `Mapped`, `mapped_column`, `__table_args__` pour l'unicité composite). Pas d'Alembic (cf. fait 4).

3. **`User.pseudo` est une `String(32)` PK** (`models.py` post-s12) — donc les FKs vers `parent_pseudo` et `child_pseudo` sont des `String(32) ForeignKey("users.pseudo")`. Pas d'UUID pour cette relation, contrairement à `Document`/`Exercise`/`Attempt` qui utilisent `student_pseudo: String(64)`. Cohérence avec la PK du `User` : `parent_pseudo` et `child_pseudo` partagent le même type.

4. **L'autorisation s'applique à `parent_pseudo` dans l'URL, pas à `child_pseudo`** — l'URL est `/api/users/{parent_pseudo}/children`. Le piège est explicite dans la story : "the `parent_pseudo` in the URL must match the authenticated user (or the user must be an admin). Do not trust the URL value." Donc on fetch le parent par son pseudo (case-insensitive, comme partout), puis on vérifie `current_user.pseudo == parent.pseudo OR current_user.role is ADMIN`. Si non, 403 `forbidden`. Le `child_pseudo` n'est *pas* comparé à l'appelant — c'est juste une donnée.

5. **Pas d'Alembic pour cette story** — `init_db()` (`backend/app/core/database/session.py:56`) est l'outil canonique en dev/CI, comme l'a établi s12 (et confirmé par `models.py:165-166` : "no Alembic migration is needed because init_db() applies the full Base metadata in dev/CI"). Le `Base.metadata.create_all` ajoutera la nouvelle table `parent_child_links` au démarrage. Tous les tests utilisent SQLite in-memory + `Base.metadata.create_all`, donc la table apparaîtra automatiquement.

## Target story

Lier un compte parent à un compte enfant via une relation many-to-many (un parent peut avoir N enfants, un enfant peut avoir N parents — familles recomposées / garde partagée).

| Endpoint | Body in | Body out | Codes |
|---|---|---|---|
| `POST /api/users/{parent_pseudo}/children` | `{child_pseudo}` | 201 `{parent_pseudo, child_pseudo}` ou 200 si déjà lié | 200/201, 401, 403, 404, 422, 500 |
| `GET /api/users/{parent_pseudo}/children` | — | 200 `[{child_pseudo, role}, ...]` | 200, 401, 403, 404, 500 |

**Acceptance criteria** (7) — AC1-AC4 comportement, AC5-AC7 tests.

## Current state of the code

| Fichier | État | Rôle pour s14 |
|---|---|---|
| `backend/app/core/database/models.py` | `User`/`UserRole` complets (s12) | Ajouter `ParentChildLink` (nouveau) |
| `backend/app/core/auth/middleware.py` | `get_current_user` + `require_role` (s13) | `get_current_user` est la dépendance (pas `require_role`) |
| `backend/app/core/auth/passwords.py` | `hash_password` | Pas utilisé par s14 (pas de hash) |
| `backend/app/api/users/__init__.py` | Docstring seul (s13b) | Pas de changement |
| `backend/app/api/users/router.py` | `POST /api/users` + `PUT /api/users/{pseudo}/role` (s13b) | Ajouter les 2 endpoints `parent-child` |
| `backend/app/api/users/schemas.py` | `CreateUserRequest/Response`, `UpdateRoleRequest`, `UserResponse`, `UserErrorCode/Response` (s13b) | Ajouter `AddChildRequest`, `ChildResponse`, `ChildrenListResponse`. Réutiliser `UserErrorCode` (étendu avec `"user_not_found"`) — ou nouveau `ParentChildErrorCode` |
| `backend/app/main.py` | `auth_router` + `users_router` montés | Pas de changement (les nouveaux endpoints sont sur `users_router`) |
| `backend/tests/api/test_users_create.py` | 18 tests (s13b) | Pattern à dupliquer |
| `backend/tests/api/test_users_role.py` | 14 tests (s13b) | Pattern à dupliquer pour `test_users_parent_child.py` |
| `backend/app/api/auth/schemas.py` | Constantes `MIN_PSEUDO_CHARS`/`MAX_PSEUDO_CHARS`/`PSEUDO_PATTERN` | Réutiliser pour valider `child_pseudo` |

## Anchor points

- **Nouveau fichier** : `backend/app/api/users/parent_child.py` — OU ajouter à `backend/app/api/users/router.py`. La convention du projet est "un `router.py` par sous-domaine dans `app/api/`" (AGENTS.md § Backend) ; un seul `users/router.py` est conservé (s13b) donc l'ajout s'y fait. Pas de split en `parent_child.py` (le sous-domaine reste `users`). Cf. ADR 005 — `users` couvre tout ce qui touche les comptes.
- **Fichiers modifiés** :
  - `backend/app/core/database/models.py` — ajouter `class ParentChildLink(Base)`.
  - `backend/app/api/users/schemas.py` — ajouter `AddChildRequest`, `ChildLinkResponse`, `ChildrenListResponse` (ou réutiliser `UserResponse`).
  - `backend/app/api/users/router.py` — ajouter `POST /{parent_pseudo}/children` + `GET /{parent_pseudo}/children`.
- **Nouveau fichier de test** : `backend/tests/api/test_users_parent_child.py` (~6-8 tests).

## Verified APIs / functions

| Nom | Signature | Localisation | Comportement vérifié |
|---|---|---|---|
| `get_current_user` | `(authorization, db) -> User` | `app/core/auth/middleware.py:58` | Lit `Authorization: Bearer`, décode via `decode_token`, fetch le `User` par `sub`. 401 sur tout échec. **Retourne le `User` complet** — c'est exactement ce dont s14 a besoin. |
| `require_role(*allowed)` | factory → `Callable` | `app/core/auth/middleware.py:106` | Wrapper de `get_current_user` qui rejette 403 si rôle non autorisé. **Ne convient PAS pour s14** (story autorise parent ou admin, pas un seul rôle). |
| `User.pseudo` | `Mapped[str]` PK | `app/core/database/models.py` (post-s12) | `String(32)`, primary_key. |
| `UserRole.PARENT`, `UserRole.ADMIN`, `UserRole.ELEVE` | enum | `app/core/database/models.py` (post-s12) | Valeurs `"parent"`, `"admin"`, `"eleve"`. |
| `func.lower(User.pseudo)` | SQL func | SQLAlchemy standard | Pattern de comparaison case-insensitive utilisé partout (`register`, `users/router.py:108, 230`). |
| `db.query(User).filter(func.lower(User.pseudo) == pseudo.lower()).one_or_none()` | lookup case-insensitive | `app/api/users/router.py:230` (exemple PUT role) | Pattern canonique pour fetch par pseudo. À réutiliser pour `parent_pseudo` et `child_pseudo`. |
| `MIN_PSEUDO_CHARS`/`MAX_PSEUDO_CHARS`/`PSEUDO_PATTERN` | constantes | `app/api/auth/schemas.py:24-26` | 3, 32, `^[a-zA-Z0-9_]+$`. À importer dans `users/schemas.py` pour valider `child_pseudo`. |
| `UserErrorCode` | `Literal[...]` | `app/api/users/schemas.py:44-52` | 7 codes dont `"user_not_found"`, `"forbidden"`. À réutiliser. |
| `IntegrityError` | SQLAlchemy exception | `sqlalchemy.exc.IntegrityError` | Capture le `UNIQUE` violation sur la PK composite `(parent_pseudo, child_pseudo)`. |

## Traps & constraints

1. **Idempotence de `POST /api/users/{parent_pseudo}/children`** — la story dit "The same child cannot be linked twice to the same parent (idempotency: returns 200 on duplicate, 201 on new)." Donc le router doit :
   - Vérifier si la relation existe déjà (`SELECT ... WHERE parent_pseudo=? AND child_pseudo=?`).
   - Si oui : 200 + body (idempotent).
   - Si non : INSERT, commit, 201 + body.
   - **Attention** : la PK composite `(parent_pseudo, child_pseudo)` rejette le double-INSERT au niveau DB, mais lever `IntegrityError` ferait un 409 au lieu de 200. Il faut pré-check (comme pour `register` et `create_user`) et retourner 200 si déjà là.

2. **L'URL `/api/users/{parent_pseudo}/children` est un sous-router de `users`** — l'APIRouter existant dans `users/router.py` a `prefix="/api/users"`, donc l'endpoint sera `POST /{parent_pseudo}/children` (relatif au préfixe). Le path param `parent_pseudo` est validé par FastAPI (string non vide) mais pas par les contraintes `MIN_PSEUDO_CHARS`/pattern — c'est OK car on fetch par `func.lower(parent_pseudo) == pseudo.lower()` qui matche tout pseudo valide ou non, et on retourne 404 si pas trouvé.

3. **Cycle detection** — la story dit "in theory, a parent-child link could be cyclic (A is parent of B, B is parent of A). For the POC, no cycle prevention — note as a follow-up." Donc s14 ne bloque PAS les cycles. Le piège est qu'à terme (s15+ ou s18b) il faudra peut-être ajouter un check (`child_pseudo` ne doit pas déjà être `parent_pseudo` d'un autre parent qui serait lui-même `child_pseudo`...). Pour s14, **pas de check**.

4. **L'autorisation sur `GET /api/users/{parent_pseudo}/children`** — la story dit "Authorization: admin or the parent themselves." Donc :
   - Si `current_user.role is ADMIN` → accès libre.
   - Si `current_user.pseudo == parent.pseudo` (après fetch du parent par URL) → accès.
   - Sinon → 403 `forbidden`.
   - **Attention** : le `parent.pseudo` retourné par la DB peut différer en case de `parent_pseudo` URL (ex: URL a `Ali`, DB a `ali`). La comparaison doit être `current_user.pseudo.lower() == parent.pseudo.lower()` ou utiliser le `parent.pseudo` canonique de la DB partout. **Recommandation** : comparer `current_user.pseudo == parent.pseudo` après le fetch (les deux sont case-preserved), ou `lower()` sur les deux.

5. **404 vs 403** — si `parent_pseudo` URL n'existe pas en DB, on retourne 404 `user_not_found` (comme le fait `PUT /api/users/{pseudo}/role` ligne 240-251). Mais attention : un attaquant qui essaie d'accéder à `/api/users/victim/children` avec un parent inexistant doit recevoir 404, pas 403 — sinon il peut distinguer "ce parent existe" (403) de "ce parent n'existe pas" (404), ce qui leak de l'info. **Cohérent avec le pattern `PUT /api/users/{pseudo}/role` ligne 240-251** : 404 d'abord, puis 403 si le parent existe mais que l'appelant n'est pas autorisé.

6. **Pas de log des pseudos dans les log lines `auth.middleware.forbidden`** — le middleware logge déjà `current_user.pseudo` pour le 403. Le handler router doit éviter de logger `parent.pseudo` ou `child.pseudo` dans des contextes sensibles (pas de password/hash/token bien sûr, mais pseudos sont OK — ils sont dans le `sub` du JWT de toute façon).

7. **Tests d'isolation cross-tenant obligatoires** — la story dit "A test verifies a parent cannot list another parent's children (multi-tenant isolation)." C'est AC6 explicite. AGENTS.md § DoD confirme : "obligatoire pour tout endpoint touchant des données élève". Le test vérifie qu'un parent `A` qui appelle `GET /api/users/B/children` (où `B` est un autre parent) reçoit 403, et qu'aucune ligne n'est lue.

8. **Pas de Alembic migration** — `init_db()` ajoute la table. Tous les tests fonctionnent en SQLite in-memory + `Base.metadata.create_all(engine)`, donc la table sera créée à chaque `db_engine` fixture. Pas de migration, pas d'`alembic revision --autogenerate`.

9. **Fixture `seeded_parent` existe** dans `test_users_create.py:135-147` — pas dans `conftest.py` (le `conftest.py` n'a pas de `seeded_parent`). Chaque fichier de test du s13b duplique les fixtures (cf. `test_users_create.py:120-162` vs `test_users_role.py`). Pour s14, on duplique le pattern : `seeded_admin` + `seeded_parent` + `seeded_eleve` + `seeded_another_parent` + `seeded_another_eleve` (pour les tests d'isolation).

10. **DRY vs duplication** — AGENTS.md "Pas de refactor transverse : le pattern _pseudo_exists n'est pas factorisé. Pas de DRY pour 4 lignes copiées. Refactor = s15+." Donc on duplique les fixtures et le helper de pre-check, comme s13b l'a fait.

11. **`role` de l'enfant dans la réponse ?** — la story dit "returns the list of linked children" (AC4) sans préciser la forme. Le PRD n'exige pas d'inclure le rôle de l'enfant dans la réponse. **Recommandation** : retourner `[{child_pseudo, role}]` pour donner au frontend assez d'info (s17 dashboard parent en aura besoin). Le rôle de l'enfant est toujours `ELEVE` (seuls les parents et admins sont créés par `POST /api/users`), mais le rendre explicite dans la réponse rend l'API self-describing.

12. **Quel schéma pour `AddChildRequest` ?** — body `{child_pseudo}`. Le champ `child_pseudo` doit valider `MIN_PSEUDO_CHARS`/`MAX_PSEUDO_CHARS`/`PSEUDO_PATTERN` (réutilisation des constantes `auth/schemas.py`). Pas d'autre champ.

## Open questions

1. **Schéma de réponse pour `GET .../children` : `[{child_pseudo}]` ou `[{child_pseudo, role}]` ?** Mon avis : **`[{child_pseudo, role}]`** pour self-describing API et préparer s17 (dashboard parent qui aura besoin du rôle de l'enfant pour adapter l'UI). Trivial à implémenter (un `User.role` JOIN). À confirmer au planning.

2. **Body de `POST .../children` : `{child_pseudo}` ou `{pseudo}` ?** La story dit `body {child_pseudo}`. **Cohérent avec la sémantique de l'URL** (l'URL porte le `parent_pseudo`, le body porte le `child_pseudo`). Mon avis : garder `{child_pseudo}` comme spécifié. Pas de renommage.

3. **Faut-il un endpoint `DELETE .../children/{child_pseudo}` pour délier ?** La story n'en parle pas. Mon avis : **hors périmètre s14** — s15 (RBAC + multi-tenancy) ou s17 (dashboard parent) pourra l'ajouter. Un admin ou un parent qui veut délier peut le faire via la DB (POC). À confirmer au planning (sinon l'ajouter comme AC8 implicite).

4. **Cas où le `child_pseudo` pointe vers un parent** — si on link `parent_pseudo=A` à `child_pseudo=B` où `B.role is PARENT`, est-ce valide ? La story dit "a parent can have multiple children, a child can have multiple parents" — elle ne restreint pas le rôle de l'enfant. **Mon avis : autoriser** (c'est un cas réel pour les fratries où un aîné est lui-même parent). Le test AC1 n'a pas besoin de couvrir ce cas, mais un test additionnel ("link a parent to another parent") est utile.

5. **Idempotence : 200 sur duplicate, mais le body doit-il être identique au 201 ?** La story dit "returns 200 on duplicate, 201 on new." Mon avis : **même body** (`{parent_pseudo, child_pseudo}`) dans les deux cas. Le test AC3 vérifie le code 200 sur duplicate et le 201 sur first create.

6. **Logging de l'audit trail pour création de lien** — la story ne mentionne pas de log line spécifique. Mon avis : **`security.parent_child_link admin={admin_or_parent} parent={parent_pseudo} child={child_pseudo} action=create`** et **`action=duplicate`** pour le 200. Aligné sur le pattern de `security.role_change` (s13b). À confirmer au planning.

## Real complexity

**Verdict : 2** (identique à `docs/stories.md`).

Pourquoi 2 :
- 1 nouveau modèle (10-20 lignes)
- 1 helper de pre-check + 1 helper d'autorisation (10-15 lignes)
- 2 endpoints simples (40-60 lignes au total)
- 6-8 tests d'API (FastAPI TestClient + SQLite in-memory)
- Pas de piège algorithmique (pas de cycle detection, pas de race critique au-delà de la PK composite)
- Réutilisation massive : `get_current_user`, `func.lower`, `UserErrorCode`, les constantes `MIN_PSEUDO_CHARS` etc.

Pourquoi pas 3 :
- Pas d'agent LangGraph ou de LLM
- Pas de multi-step workflow
- L'autorisation "owner-or-admin" est un `if` de 2 lignes

Pas de split proposé.

## Split proposal

N/A — complexité 2, plan estimée < 8 tâches, shippable en un cycle.

<< IP Mike: exploration method, what a good research always verifies. >>
