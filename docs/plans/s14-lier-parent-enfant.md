---
validated: yes
---
# Plan — Story s14-lier-parent-enfant

Branch: `feature/s14-lier-parent-enfant`
Research: `docs/research/s14-lier-parent-enfant.md` — read it first; this plan does not repeat it.

## Target story

Lier un compte parent à un compte enfant via une relation many-to-many (un parent peut avoir N enfants, un enfant peut avoir N parents — familles recomposées / garde partagée). Pattern d'autorisation **owner-or-admin** (différent de role-only) : `current_user.pseudo == parent.pseudo` OU `current_user.role is UserRole.ADMIN`.

| Endpoint | Body in | Body out | Codes |
|---|---|---|---|
| `POST /api/users/{parent_pseudo}/children` | `{child_pseudo}` | 201 `{parent_pseudo, child_pseudo}` (ou 200 si déjà lié, idempotence) | 200, 201, 401, 403, 404, 422, 500 |
| `GET /api/users/{parent_pseudo}/children` | — | 200 `[{child_pseudo, role}, ...]` | 200, 401, 403, 404, 500 |

**Acceptance criteria** (7, tous dans le scope) — AC1-AC4 comportement, AC5-AC7 tests.

## Tasks (ordered)

1. [x] **Ajouter `class ParentChildLink(Base)` dans `backend/app/core/database/models.py`** (après la classe `User`, avant la déclaration de l'index `uq_users_pseudo_lower` à la fin du fichier) :
   - `__tablename__ = "parent_child_links"`.
   - `parent_pseudo: Mapped[str] = mapped_column(String(32), ForeignKey("users.pseudo", ondelete="CASCADE"), primary_key=True, nullable=False)`.
   - `child_pseudo: Mapped[str] = mapped_column(String(32), ForeignKey("users.pseudo", ondelete="CASCADE"), primary_key=True, nullable=False)`.
   - `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())`.
   - Docstring rappelant : pas de `cycle detection` (suivi s15+), pas de contrainte de rôle sur `child_pseudo` (un parent peut être lié à un autre parent — cas des fratries aîné-parent), `init_db()` crée la table automatiquement (cf. `models.py:165-166`).
   - **Vérification** : `python -c "from app.core.database.models import ParentChildLink; print(ParentChildLink.__tablename__)"` imprime `parent_child_links` ; `Base.metadata.tables` contient `parent_child_links` après import.

2. [x] **Étendre `backend/app/api/users/schemas.py`** avec les nouveaux schémas pour les endpoints parent-child :
   - `AddChildRequest` : `child_pseudo: str = Field(..., min_length=MIN_PSEUDO_CHARS, max_length=MAX_PSEUDO_CHARS, pattern=PSEUDO_PATTERN)` (réutilisation des constantes `auth/schemas.py`).
   - `ChildLinkResponse` : `{parent_pseudo: str, child_pseudo: str}` (200 + 201).
   - `ChildResponse` : `{child_pseudo: str, role: UserRoleString}` où `UserRoleString = Literal["eleve", "parent", "admin"]` (réutilisable — équivaut à `UpdateUserRole`).
   - `ChildrenListResponse` : `list[ChildResponse]` (200 GET, peut être vide `[]`).
   - **Pas de nouveau `*ErrorCode`** : on **étend** `UserErrorCode` (Literal existant) avec `"user_not_found"` (déjà présent) et on **réutilise** `UserErrorResponse` (déjà exporté). Cf. research §3 — `user_not_found` est déjà dans `UserErrorCode:44-52`. Pas de duplication, pas de nouveau `ParentChildErrorCode`.
   - **Vérification** : `python -c "from app.api.users.schemas import AddChildRequest, ChildLinkResponse, ChildResponse, ChildrenListResponse"` passe sans erreur.

3. [x] **Étendre `backend/app/api/users/router.py`** avec les deux nouveaux endpoints :
   - **`POST /{parent_pseudo}/children`** (`def add_child(parent_pseudo, body, current_user, db)`) :
     - **`current_user: User = Depends(get_current_user)`** (PAS `require_role` — cf. research fait 1).
     - **Étape 1** : fetch le parent par `func.lower(User.pseudo) == parent_pseudo.lower()` (404 `user_not_found` si absent — anti-leak, on ne distingue pas "n'existe pas" de "existe mais pas le bon" via le 403 ensuite, cf. research trap 5).
     - **Étape 2** : check `current_user.pseudo == parent.pseudo` OU `current_user.role is UserRole.ADMIN` (403 `forbidden` sinon, log `users.children.forbidden caller={caller} parent={parent}`).
     - **Étape 3** : fetch le child par `func.lower(User.pseudo) == body.child_pseudo.lower()` (404 `user_not_found` si absent).
     - **Étape 4** : pré-check `SELECT * FROM parent_child_links WHERE parent_pseudo=? AND child_pseudo=?` (case-insensitive sur les deux colonnes — `func.lower()`). Si déjà lié → 200 + `ChildLinkResponse(parent.pseudo, child.pseudo)`, log `users.children.duplicate parent={parent} child={child} actor={current_user}`.
     - **Étape 5** : insert `ParentChildLink(parent_pseudo=parent.pseudo, child_pseudo=child.pseudo)` + `db.commit()`. `catch IntegrityError` → 200 (race) ; `catch Exception` → 500. Retour 201 + `ChildLinkResponse(parent.pseudo, child.pseudo)`, log `users.children.created parent={parent} child={child} actor={current_user}`.
   - **`GET /{parent_pseudo}/children`** (`def list_children(parent_pseudo, current_user, db)`) :
     - Mêmes étapes 1-2 (fetch parent + check owner-or-admin, 404 → 403).
     - **Étape 3** : `db.query(User).join(ParentChildLink, ParentChildLink.child_pseudo == User.pseudo).filter(func.lower(ParentChildLink.parent_pseudo) == parent.pseudo.lower()).all()`.
     - Retour 200 + `ChildrenListResponse([ChildResponse(pseudo=u.pseudo, role=u.role.value) for u in users])`. Liste vide `[]` si pas d'enfant lié (PAS 404 — l'absence d'enfant n'est pas une erreur). Log `users.children.listed parent={parent} count={n} actor={current_user}`.
   - **Helpers privés** :
     - `_fetch_user_or_404(db, pseudo, *, field_name: str) -> User` (réutilise la pattern `func.lower` ; 404 `user_not_found`).
     - `_assert_owner_or_admin(*, current_user, parent, action: str) -> None` (403 `forbidden` si ni owner ni admin ; log structuré `users.children.forbidden`).
   - **Import à ajouter** : `from app.core.auth.middleware import get_current_user` ; `from app.core.database.models import ParentChildLink, User, UserRole`.
   - **Vérification** : `python -c "from app.api.users.router import router; print([r.path for r in router.routes])"` liste les 4 paths (les 2 s13b + les 2 s14).

4. [x] **Tests `POST /api/users/{parent_pseudo}/children`** dans `backend/tests/api/test_users_parent_child.py` (5 classes, ≥ 7 tests) :
   - **Fixtures à dupliquer** depuis `test_users_create.py:79-162` (cf. research trap 9) : `rsa_keypair` (session), `_point_settings` (autouse), `db_engine`, `session_factory`, `client`. **Ajouter** : `seeded_another_parent` (un 2e parent pour les tests d'isolation) et `seeded_another_eleve` (un 2e élève pour la même raison). Tous les fixtures s'inspirent ligne-à-ligne de `test_users_role.py:40-120` — duplication assumée (cf. AGENTS.md "Pas de refactor transverse" + research §10).
   - **Helpers** : `_bearer(user)` (équivalent de `_admin_bearer` ligne 165, mais générique : `f"Bearer {create_access_token(user.pseudo, user.role)}"`).
   - **`TestAddChildHappyPath`** : (a) admin linke un parent A à un eleve E → 201 `{parent_pseudo: A, child_pseudo: E}`, ligne `parent_child_links` présente en DB ; (b) parent A s'auto-linke à un eleve E (owner) → 201 ; (c) re-post (idempotence) → 200, **même body**, **DB toujours 1 ligne** (pas d'INSERT supplémentaire).
   - **`TestAddChildAuth`** : (a) eleve caller essaie de lier un parent A à un eleve E → 403 `forbidden` ; (b) parent B essaie de lier un parent A à un eleve E → 403 `forbidden` ; (c) no-token → 401 `invalid_token` ; (d) junk-token → 401 `invalid_token`.
   - **`TestAddChildNotFound`** : (a) `parent_pseudo` URL inexistant → 404 `user_not_found` ; (b) `child_pseudo` body inexistant → 404 `user_not_found`.
   - **`TestAddChildValidation`** : (a) `child_pseudo` trop court (2 chars) → 422 ; (b) `child_pseudo` avec `-` → 422 ; (c) `child_pseudo` 33 chars → 422 ; (d) body vide → 422.
   - **`TestAddChildIdempotence`** : (a) double-link par le même admin → 1er 201, 2e 200, **DB contient 1 ligne** ; (b) link puis link par le parent lui-même → 1er 201, 2e 200, DB contient 1 ligne.
   - **`TestAddChildLoggingHygiene`** : aucune log line ne contient de mot de passe, hash, token, jti. Vérifier les 3 topics : `users.children.created`, `users.children.duplicate`, `users.children.forbidden`.
   - **Vérification** : `pytest backend/tests/api/test_users_parent_child.py -v -k "TestAddChild"` → 7+/7+ pass.

5. [x] **Tests `GET /api/users/{parent_pseudo}/children`** (dans le même fichier, ≥ 5 tests) :
   - **`TestListChildrenHappyPath`** : (a) parent A (owner) liste ses enfants → 200, liste non-vide avec le bon `child_pseudo` et `role` ; (b) admin liste les enfants d'un parent A → 200, même body ; (c) parent A sans enfant lié → 200 `[]` (PAS 404).
   - **`TestListChildrenAuth`** : (a) eleve caller → 403 ; (b) **parent B essaie de lister les enfants du parent A** (test d'isolation cross-tenant obligatoire, AC6) → 403, **DB non lue** (assertion : on peut vérifier que la query retourne 0 lignes, ou que l'endpoint renvoie `[]` au lieu de la liste des enfants de A — pour un parent B qui n'a aucun lien, le résultat EST `[]` ; pour le cas "B essaie d'accéder à A", B n'est pas owner et n'est pas admin → 403) ; (c) no-token → 401.
   - **`TestListChildrenNotFound`** : `parent_pseudo` URL inexistant → 404 (anti-leak : pas de 403 sur parent inexistant).
   - **`TestListChildrenCaseInsensitive`** : (a) parent URL en `Ali` qui correspond à `ali` en DB → 200, enfants listés. Réutilise le pattern case-insensitive de `func.lower()` déjà présent.
   - **`TestListChildrenResponseShape`** : la réponse est bien `[{child_pseudo: str, role: Literal[...]}, ...]` (assertion de schéma sur tous les éléments).
   - **Vérification** : `pytest backend/tests/api/test_users_parent_child.py -v -k "TestListChildren"` → 5+/5+ pass.

6. [x] **Run full backend test suite** : `pytest backend/tests/ -v --tb=short` → 0 régression sur les tests s12/s13/s13b existants. **Vérification** : tous les tests `test_auth_*.py`, `test_users_create.py`, `test_users_role.py`, `test_models.py`, `test_passwords.py` restent verts.

7. [x] **Lint + typecheck** : `cd backend && ruff check app/ tests/` (zéro nouveau warning) + `mypy app/` (zéro nouvelle erreur). **Vérification** : CI lint job passe.

8. [x] **Conventional commit unique** : `feat(api): add /api/users/{pseudo}/children parent-child link endpoints (s14)` couvrant tous les fichiers modifiés + créés + le research + le plan. **Vérification** : `git log -1` montre un seul commit avec tous les fichiers (research + plan + code + tests).

## Run interdicts

- **Pas de migration Alembic** : `init_db()` (database/session.py:56) est l'outil canonique en dev/CI. `ParentChildLink` n'a pas besoin d'Alembic — la table sera créée par `Base.metadata.create_all` au prochain démarrage, et SQLite in-memory la crée au prochain test.
- **Pas de frontend** : s14 est backend-only. Aucun fichier dans `frontend/` ne doit être touché.
- **Pas de `require_role(UserRole.ADMIN)`** : c'est `get_current_user` + check `owner-or-admin` dans le handler (cf. research fait 1). Utiliser `require_role` ici rejetterait à tort les parents.
- **Pas de cycle detection** : la story dit explicitement "For the POC, no cycle prevention — note as a follow-up." Ne pas ajouter de check `child not in parent_of_parent`.
- **Pas de contrainte de rôle sur `child_pseudo`** : un parent peut être lié à un autre parent (cas aîné-parent dans une fratrie). Ne pas ajouter de check `child.role is ELEVE`.
- **Pas de DELETE endpoint** : la story n'en parle pas. Un admin qui veut délier peut le faire via la DB (POC). À ajouter en s15 ou s17 si besoin.
- **Pas de nouveau `*ErrorCode` Literal** : on étend `UserErrorCode` (qui contient déjà `"user_not_found"` et `"forbidden"`). Pas de `ParentChildErrorCode` séparé — duplication inutile, Pydantic ne peut pas modéliser des hiérarchies (commentaire `schemas.py:21-23` l'explicite déjà pour s13b).
- **Pas de refactor transverse** : le pattern `_pseudo_already_exists` de s13b n'est pas factorisé en helper partagé. Idem pour `_fetch_user_or_404` — duplication assumée, refactor = s15+.
- **Pas de commit sur la branche par défaut** : tout part sur `feature/s14-lier-parent-enfant` (worktree dédié). Le squash-merge vers `main` est manuel après review.
- **Pas de session globale dans les tests** : chaque test crée son propre `db_engine` (cf. pattern `test_users_create.py:79-92`) pour ne pas polluer.
- **Pas de log du password, hash, token, jti** dans les nouvelles log lines `users.children.*` (vérifié par `TestAddChildLoggingHygiene`).

## The point everything turns on

**La décision centrale** : le pattern d'autorisation est **owner-or-admin**, pas **admin-only**. C'est différent de s13b.

Trois pièges à surveiller :

1. **Mauvais import de la dépendance** : la note agentic dit `app/api/auth/dependencies.py`, ce fichier n'existe pas. Le plan dit `from app.core.auth.middleware import get_current_user` (vérifié : `app/core/auth/middleware.py:58`). Si l'implémenteur importe `require_role` ici, **tous les parents** (même le bon) seront rejetés avec 403 — c'est exactement le bug de pattern que le research §1 met en garde contre. Test : `TestAddChildAuth::test_parent_self_link_returns_201` prouve que l'owner n'est pas rejeté.

2. **404 avant 403** : si on fetch le parent en DB puis on check l'autorisation, on doit retourner 404 (parent inexistant) **avant** 403 (parent existant mais caller pas autorisé). L'inverse leak l'existence du parent (un attaquant pourrait distinguer "ce parent existe" via 403 vs "n'existe pas" via 404). Test : `TestAddChildNotFound::test_missing_parent_returns_404_not_403` + `TestListChildrenNotFound::test_missing_parent_returns_404`. Cf. research trap 5.

3. **Idempotence vs PK composite** : la PK composite `(parent_pseudo, child_pseudo)` rejette le double-INSERT au niveau DB (`IntegrityError`). Si on ne pré-check pas, on renverrait 409 au lieu de 200 (idempotence). Le plan fait le pré-check en lecture (`SELECT ... WHERE`) avant l'INSERT, donc 200 sur duplicate, 201 sur nouveau. Test : `TestAddChildIdempotence::test_double_link_same_admin_returns_200_on_second` prouve que le 2e appel renvoie 200 (et non 409, et non 500).

Vérification finale par le reviewer : (a) `grep -n "get_current_user" backend/app/api/users/router.py` montre bien l'import depuis `core.auth.middleware` ; (b) `grep -n "require_role" backend/app/api/users/router.py` ne montre qu'un usage ou zéro (pas de régression sur s13b, mais l'idéal est que les 2 endpoints s14 utilisent `get_current_user` et les 2 s13b continuent d'utiliser `require_role`) ; (c) le test `TestAddChildIdempotence` assert `len(rows) == 1` après 2 POSTs.

## Files touched

**Créés** :
- `backend/tests/api/test_users_parent_child.py` (~250 lignes : 10 classes, ≥ 12 tests)
- `docs/research/s14-lier-parent-enfant.md` (déjà créé)
- `docs/plans/s14-lier-parent-enfant.md` (ce fichier)

**Modifiés** :
- `backend/app/core/database/models.py` (~25 lignes ajoutées : classe `ParentChildLink` + docstring)
- `backend/app/api/users/schemas.py` (~50 lignes ajoutées : `AddChildRequest`, `ChildLinkResponse`, `ChildResponse`, `ChildrenListResponse`)
- `backend/app/api/users/router.py` (~120 lignes ajoutées : 2 endpoints + 2 helpers privés + 2 imports)

**Non touchés (volontairement)** :
- `backend/app/core/auth/middleware.py` — `get_current_user` est utilisé tel quel
- `backend/app/core/auth/passwords.py` — pas de hash dans s14
- `backend/app/core/auth/jwt.py` — pas de JWT à émettre (les liens n'auth-entifient rien)
- `backend/app/main.py` — `users_router` est déjà monté (s13b), pas de nouveau router
- `backend/app/api/users/__init__.py` — pas touché (le sous-domaine reste `users`, cf. research anchor points)
- `backend/app/api/auth/schemas.py` — constantes importées, pas modifiées
- `backend/app/api/auth/router.py` — non touché (pas de factorisation de `_pseudo_already_exists` — décision Open Q3)
- `backend/scripts/` — pas de bootstrap
- `frontend/**` — pas de frontend (s14 est backend-only)

## Test strategy

**Couche principale** : tests d'API (FastAPI TestClient + SQLite in-memory + StaticPool + `app.dependency_overrides[get_db]`) — pattern `test_users_create.py:79-117`. C'est la couche qui prouve les ACs 1-7.

**Couche fixtures** : duplication assumée des fixtures `rsa_keypair`, `_point_settings`, `db_engine`, `session_factory`, `client` (cf. research trap 9 + AGENTS.md "Pas de refactor transverse"). `seeded_admin` / `seeded_parent` / `seeded_eleve` sont réutilisés tels quels. `seeded_another_parent` et `seeded_another_eleve` sont ajoutés localement pour les tests d'isolation cross-tenant.

**Tests d'isolation cross-tenant** : `TestListChildrenAuth::test_parent_B_cannot_list_parent_A_children_returns_403` (AC6 explicite). C'est le seul test d'isolation — l'écriture (`POST`) n'a pas de notion de tenant côté caller puisque le caller est owner ou admin (pas de fuite possible).

**Tests qui n'existent pas et n'existent pas besoin d'exister** :
- Pas de test d'intégration PostgreSQL (POC local, SQLite suffit).
- Pas de test E2E frontend (pas de frontend dans s14).
- Pas de test de migration Alembic (pas de migration).
- Pas de test du path `DELETE` (endpoint hors-scope).
- Pas de test de cycle detection (hors-scope, suivi s15+).

**Couverture attendue** : ≥ 12 tests (7 add + 5 list) + 2-3 tests de logging hygiene, tous indépendants, tous passants sur SQLite/CI. La review vérifiera qu'aucun test n'est skipped ou xfail sans justification.

## Definition of Done

- [ ] Tous les ACs 1-7 sont couverts par un test qui passe (`pytest backend/tests/api/test_users_parent_child.py -v`).
- [ ] Aucune régression : `pytest backend/tests/ -v` reste 100% vert.
- [ ] Lint clean : `ruff check backend/app/api/users/ backend/app/core/database/ backend/tests/api/test_users_parent_child.py` → 0 issue.
- [ ] Typecheck clean : `mypy backend/app/api/users/ backend/app/core/database/` → 0 issue.
- [ ] Multi-tenancy (cf. AGENTS.md § DoD) : test d'isolation cross-tenant obligatoire pour AC6 — `TestListChildrenAuth::test_parent_B_cannot_list_parent_A_children_returns_403` passe.
- [ ] Observabilité : `users.children.created`, `users.children.duplicate`, `users.children.forbidden`, `users.children.listed` logguent avec `parent` + `child` + `actor` (jamais password/hash/token — vérifié par `TestAddChildLoggingHygiene`).
- [ ] Aucun fichier frontend touché.
- [ ] Conventional commit unique : `feat(api): add /api/users/{pseudo}/children parent-child link endpoints (s14)`.
- [ ] PR ouverte depuis `feature/s14-lier-parent-enfant` vers `main` avec description structurée (résumé, ACs cochées, points d'attention sur la dépendance `get_current_user` au lieu de `require_role`, le pattern 404-avant-403, et l'idempotence 200/201).

<< IP Mike: task granularity, what a good plan contains/avoids. >>
