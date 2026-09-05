# Research — Story s17-dashboard-parent

## The five structuring facts

1. **`ParentChildLink` est un modèle SQLAlchemy composite (PK `(parent_pseudo, child_pseudo)`)** dans `backend/app/core/database/models.py:269-317`, avec FK `ondelete=CASCADE` sur `users.pseudo`. Pas de contrainte sur le rôle de `child_pseudo` (un parent peut être lié à un autre parent ou un admin — choix explicite du s14, voir docstring du modèle). Pas de détection de cycle (POC).
2. **Le helper `assert_jwt_pseudo_matches_or_403(user, claimed, route=...)`** est livré par s15 dans `backend/app/core/auth/middleware.py:149-211`. Il implémente déjà la garde cross-tenant : `None` = no-op, match = no-op, admin = bypass avec `auth.middleware.admin_bypass` DEBUG, autre = 403 + log `security.cross_tenant_attempt` (caller, claimed, role, route). **Mais ce helper n'est pas directement utilisable pour s17** : il vérifie que le `pseudo` demandé matche le JWT, alors que s17 doit vérifier que le `child_pseudo` demandé est lié au parent du JWT. **Prémisse à challenger** : s17 a besoin d'un helper différent (`assert_parent_linked_to_child_or_403`).
3. **`aggregate_eleve_dashboard(db, pseudo)` est une fonction pure** dans `backend/app/services/dashboard/aggregator.py`. Elle prend un `pseudo` et retourne `EleveDashboardResponse`. **Déjà réutilisable tel quel** par le parent endpoint : il suffit d'appeler `aggregate_eleve_dashboard(db, child_pseudo)` pour chaque enfant lié. Le cache `dashboard:eleve:{pseudo}` est par-`pseudo` de l'élève, donc réutilisable côté parent (l'invalidation est par `pseudo` enfant).
4. **`DashboardClient.tsx` (609 lignes) n'a PAS de prop `readOnly`** et contient 3 boutons d'action (Refresh l. 278, Retry l. 370, Empty CTA l. 593). L'AC #6 exige « the same component as the eleve dashboard, but with no edit/action buttons ». **Prémisse invalide** : la story dit « reuse with readOnly prop », mais le composant n'a pas cette prop. Mitigation de l'agentic note : « extract the read-only view into its own component first, then re-integrate the write-only parts in the eleve view » — c'est un refactor transversal de s16, à acter dans la story.
5. **Le route group `(dashboard)/[locale]/` est en place depuis s16** avec `AuthGuard` qui hydrate `useAuthStore` et redirige `/login?next=...` si non authentifié. Le `AuthGuard` actuel ne distingue pas le rôle — il authentifie, point. **S17 doit passer le rôle `parent` ou échouer avec 403 côté backend**. Le frontend peut afficher un message « accès parent uniquement » si un eleve ou un admin atteint `/dashboard/parent`. Le route group accepte n'importe quel rôle authentifié pour l'instant.

## Target story

`docs/stories.md:833-863` — **As a parent I want** voir la progression de chacun de mes enfants **so that** je suive leur travail sans pouvoir le modifier.

**6 acceptance criteria** (verbatim) :
- AC1 — `GET /api/dashboard/parent` (JWT auth) retourne les dashboards de tous les enfants liés au parent.
- AC2 — `/dashboard/parent` liste chaque enfant sous forme de card, chaque card linkant vers une child-detail view.
- AC3 — La child-detail view est le même composant que le dashboard eleve, sans boutons d'édition/action.
- AC4 — Test : parent ne voit que ses enfants liés.
- AC5 — Test : parent ne peut pas accéder aux données d'un enfant non lié (multi-tenant isolation).
- AC6 — Test : tous les boutons « edit » du composant réutilisé sont cachés ou désactivés en vue parent.

**Dependencies** : s14 (parent-child link, **shipped**), s15 (auth + multi-tenant, **shipped**), s16 (eleve dashboard, **shipped**).

**Files involved** (per agentic note) :
- `backend/app/api/dashboard/parent.py` (NEW, à côté de `eleve.py`)
- `frontend/app/(dashboard)/[locale]/parent/page.tsx` (NEW)
- `frontend/app/(dashboard)/[locale]/parent/[child_pseudo]/page.tsx` (NEW)
- Refactor transversal de `frontend/app/(dashboard)/[locale]/dashboard/eleve/DashboardClient.tsx` (ajout `readOnly` prop, OU extraction d'un `<DashboardView>` partagé)

## Current state of the code

**Backend (s16 livré)** :
- `backend/app/api/dashboard/eleve.py` — endpoint `GET /api/dashboard/eleve` (utilise `assert_jwt_pseudo_matches_or_403` + `aggregate_eleve_dashboard` + cache `dashboard:eleve:{pseudo}`).
- `backend/app/api/dashboard/schemas.py` — `SubjectSummary`, `GlobalSummary`, `EleveDashboardResponse`.
- `backend/app/services/dashboard/aggregator.py` — 2 SQL queries (per-subject + global) avec `CAST(is_success AS FLOAT)` (test pinné par `test_aggregator_compiles_cast_is_success_as_float`).
- `backend/app/services/dashboard/cache.py` — dict TTL 5 min, lock, `now_fn` injectable.

**Backend (s14 livré)** :
- `backend/app/core/database/models.py:269-317` — `ParentChildLink` (composite PK, FK CASCADE).
- `backend/app/api/users/router.py:559` — `list_children(parent_pseudo, current_user, db)` retourne `ChildrenListResponse` (liste de `ChildResponse`). Implémente déjà owner-or-admin : un parent ne peut lister que SES enfants, un admin peut lister pour n'importe quel parent.

**Backend (s15 livré)** :
- `backend/app/core/auth/middleware.py:149-211` — `assert_jwt_pseudo_matches_or_403`. **Pas directement applicable à s17** (vérifie pseudo == JWT, pas parent lié à child). S17 a besoin d'un nouveau helper `assert_parent_linked_to_child_or_403`.

**Frontend (s16 livré)** :
- `frontend/app/(dashboard)/[locale]/layout.tsx` + `AuthGuard.tsx` — auth gate, `useAuthStore`, redirect `/login?next=...` avec locale.
- `frontend/app/(dashboard)/[locale]/dashboard/eleve/page.tsx` — server component, fetch client-side via `apiClient` (JWT en `localStorage`).
- `frontend/app/(dashboard)/[locale]/dashboard/eleve/DashboardClient.tsx` — **609 lignes**, **PAS de prop `readOnly`**, contient 3 boutons d'action (Refresh, Retry, Empty CTA).
- `frontend/app/(dashboard)/[locale]/AuthGuard.tsx` — utilise `useLocale()` pour redirect.

## Anchor points

- **Backend** : `backend/app/api/dashboard/eleve.py:80` (utilise `assert_jwt_pseudo_matches_or_403`) → nouveau fichier `backend/app/api/dashboard/parent.py` à côté.
- **Backend** : `backend/app/services/dashboard/aggregator.py:58, 84` (queries avec `student_pseudo` filter) → réutilisable tel quel.
- **Backend** : `backend/app/services/dashboard/cache.py` (cache `dashboard:eleve:{pseudo}` TTL 5 min) → réutilisable (cache key par `pseudo` enfant).
- **Backend** : `backend/app/api/users/router.py:559` (`list_children`) → pattern à répliquer pour l'agrégation parent.
- **Backend** : `backend/app/core/auth/middleware.py:149-211` → modèle pour un nouveau helper `assert_parent_linked_to_child_or_403`.
- **Frontend** : `frontend/app/(dashboard)/[locale]/dashboard/eleve/DashboardClient.tsx:278, 370, 593` (3 `<Button>`) → candidats au wrapping `readOnly`.
- **Frontend** : `frontend/app/(dashboard)/[locale]/AuthGuard.tsx` → à étendre pour supporter un `requireRole` prop (optionnel, RBAC côté UI).

## Verified APIs / functions

| Symbol | Path | Behavior |
| --- | --- | --- |
| `ParentChildLink` model | `backend/app/core/database/models.py:269` | Composite PK `(parent_pseudo, child_pseudo)`, FK CASCADE. |
| `list_children(parent_pseudo, current_user, db)` | `backend/app/api/users/router.py:559` | Returns list of linked children. Owner-or-admin. 404 if parent doesn't exist. |
| `assert_jwt_pseudo_matches_or_403(user, claimed, route=...)` | `backend/app/core/auth/middleware.py:149` | Verifies `claimed == user.pseudo`, admin bypass. **Not applicable to s17** (parent-child, not pseudo). |
| `aggregate_eleve_dashboard(db, pseudo)` | `backend/app/services/dashboard/aggregator.py` | Returns `EleveDashboardResponse`. Pure, reusable by parent. |
| `get_dashboard(pseudo)` / `set_dashboard(pseudo, data, ttl)` / `invalidate_dashboard(pseudo)` | `backend/app/services/dashboard/cache.py` | Per-`pseudo` cache, TTL 5 min. Reusable for child. |
| `DashboardClient` (React component) | `frontend/app/(dashboard)/[locale]/dashboard/eleve/DashboardClient.tsx` | **No `readOnly` prop.** Contains 3 action buttons. |

## Traps & constraints

1. **Prémisse « reuse eleve dashboard component with readOnly prop » est fausse** : `DashboardClient` n'a pas cette prop. Deux options : (a) ajouter la prop, (b) extraire un `<DashboardView>` partagé. L'option (a) est plus chirurgicale (refactor s16 dans s17, scope creep). L'option (b) est plus propre mais plus large. **À arbitrer en planning**.
2. **Pas de cycle detection** dans `ParentChildLink` (s14 docstring le dit explicitement) : un parent peut être lié à un autre parent ou un admin. Pour s17, ça reste cohérent — un parent lié à un admin pourrait théoriquement demander le dashboard de cet admin. **Le helper `assert_parent_linked_to_child_or_403` doit filtrer par `ParentChildLink.parent_pseudo == user.pseudo` ET `child_pseudo == claimed`**, sans contrainte de rôle. Si un parent demande le dashboard d'un autre parent auquel il est lié, on renvoie le dashboard (qui peut être vide pour un parent sans attempts). C'est OK.
3. **Cache partage eleve/parent** : si l'eleve alice hit `/api/dashboard/eleve`, le cache key est `dashboard:eleve:alice`. Si le parent hit `GET /api/dashboard/parent` qui itère sur ses enfants et appelle `aggregate_eleve_dashboard(db, alice)`, le **même cache key** est utilisé. **C'est intentionnel** (cf. s16 review) — l'invalidation est par `pseudo` enfant, donc l'eleve qui soumet un Attempt invalide son cache, et le parent en bénéficie.
4. **Le parent lit l'Attempt.history de l'enfant** : `aggregate_eleve_dashboard` filtre par `Attempt.student_pseudo == pseudo`. C'est OK pour le parent (lecture), mais le frontend doit **ne pas exposer** les actions « submit attempt » (donc pas d'`/exercises/generate` link, pas de « soumets ta réponse » button). L'AC #6 le dit.
5. **`list_children` est un endpoint distinct** (`GET /api/users/{parent_pseudo}/children`). S17 peut l'utiliser pour récupérer la liste des enfants, puis appeler `GET /api/dashboard/parent` (un nouvel endpoint qui agrège les dashboards). **Deux choix architecturaux** : (a) `GET /api/dashboard/parent` retourne `{children: [{pseudo, dashboard: EleveDashboardResponse}]}` en une seule requête, (b) le frontend appelle `list_children` puis boucle sur `GET /api/dashboard/eleve?pseudo=<child>`. Le (a) est préférable (1 requête vs N+1, cache hit côté parent). **Recommandation : (a)**.
6. **Tests d'isolation cross-tenant existants (s14/s15)** : `test_eleve.py:9 tests` incluent déjà cross-tenant 403. S17 doit ajouter 3 tests minimum (AC4-AC6) : parent voit ses enfants, parent ne voit pas un enfant non lié, refresh button absent en vue parent.
7. **RBAC au niveau endpoint** : s15 a livré `require_role(["eleve", "parent", "admin"])`. S17 doit utiliser `require_role(["parent", "admin"])` sur `/api/dashboard/parent` (un eleve qui hit cet endpoint doit recevoir 403, pas juste un empty list).
8. **i18n** : s16 a ajouté le namespace `dashboard.eleve` dans `fr.json` + `en.json`. S17 doit ajouter un namespace `dashboard.parent` (~10 clés : title, childCount, noChild, linkedAt, etc.) + réutiliser certaines clés `dashboard.eleve` (tauxReussite, lastActivity, etc.).
9. **Frontend route conflict** : `/dashboard/eleve` (s16) et `/dashboard/parent` (s17) sont sous le même route group `(dashboard)/[locale]/`. Next.js gère les routes distinctes sans conflit. Mais `/dashboard/parent/[child_pseudo]` est une route dynamique imbriquée — Next.js la gère nativement.
10. **URL plan vs story** : l'agentic note dit `/dashboard/parent/{child_pseudo}` (sans `[locale]`). Mais le route group `(dashboard)/[locale]/` est préfixé par `[locale]`, donc l'URL effective est `/<locale>/dashboard/parent` et `/<locale>/dashboard/parent/{child_pseudo}`. Cohérent avec s16.

## Open questions

1. **Refactor s16** : ajouter `readOnly` prop à `DashboardClient` (scope creep) vs extraire un `<DashboardView>` partagé (refactor plus large) ? Recommandation : extraire `<DashboardView>` partagé dans `frontend/components/` (ou `frontend/app/(dashboard)/[locale]/_shared/`), `DashboardClient` eleve le wrap avec boutons d'action, page parent utilise `<DashboardView>` directement. Mais ça ajoute 1-2 composants et un fichier de plus. À arbitrer en planning.
2. **Helper `assert_parent_linked_to_child_or_403`** : nouveau helper dans `backend/app/core/auth/middleware.py` vs inline dans le router `parent.py` ? Recommandation : nouveau helper, aligné avec le pattern s15.
3. **Cache key** : faut-il un cache séparé `dashboard:parent:{parent_pseudo}` pour la liste agrégée ? Ou cache partagé via `dashboard:eleve:{child_pseudo}` (recommandé) ? Recommandation : cache partagé (réutilise le TTL 5 min, évite la duplication).
4. **AuthGuard role check** : faut-il étendre `AuthGuard` pour supporter `requireRole` prop, ou laisser l'API rejeter avec 403 (le frontend affiche un message « accès non autorisé ») ? Recommandation : laisser l'API rejeter, plus simple. Le 403 s'affiche comme un état error réutilisable.
5. **Empty state parent** : un parent sans enfants liés affiche quoi ? Recommandation : empty state « Aucun enfant lié à votre compte. Contactez un administrateur pour lier un enfant » + lien vers la page d'aide.
6. **Le parent voit-il ses propres attempts ?** Non — la story dit « lecture seule de mes enfants ». Le parent n'a pas de dashboard eleve. S'il hit `/api/dashboard/eleve` avec son propre pseudo, il reçoit son dashboard (vide s'il n'a pas d'attempts). S'il hit `?pseudo=<other_parent>`, le helper s15 le bloque (admin bypass OK). C'est **par design**, le parent peut voir sa propre page si jamais il y a un cas où il joue aussi le rôle d'eleve (rare mais pas interdit par s14).

## Real complexity

**Story score in `docs/stories.md` : 3** (relevée de 2 → 3 car la story cumule endpoint + page liste + page child-detail + read-only + tests d'isolation).

**My re-score after reading the code : 3** (agree, but the breakdown is shifted) :
- **Backend** : simple, 1 endpoint qui réutilise l'agrégateur s16. ~1.5 days.
- **Frontend list page** : simple, ~0.5 day. Reuse du composant `SubjectCard` de s16 (à extraire si pas déjà partagé).
- **Frontend child-detail page** : medium, le refactor `readOnly` est le point chaud. ~1 day.
- **Tests** : 3+ tests backend + 2+ e2e. ~0.5 day.
- **i18n** : ~10 clés, ~0.25 day.

**Total : ~3-4 days. Verdict 3 confirmé**, mais le **risque** est sur le refactor `readOnly`. Si l'option « extraire `<DashboardView>` partagé » est choisie, la story monte à 4 (refactor + tests). Si l'option « ajouter `readOnly` prop » est choisie, la story reste à 3 (plus chirurgical).

**Ne pas splitter** : la story est shippable en un cycle. Le refactor est contenu.

## Split proposal

**Optionnel, non recommandé** : si le refactor `readOnly` s'avère trop invasif (s16 livré sans cette prop, tests e2e serrés), on pourrait splitter en :
- **s17a** : backend `GET /api/dashboard/parent` + tests (3 tasks). Le parent accède aux données via API.
- **s17b** : frontend refactor `readOnly` + page liste + page child-detail + e2e (5-6 tasks).

Mais s17a sans frontend ne livre pas de valeur user-visible, donc le split est **théorique**. Mieux vaut garder la story unie et bien cadrer le refactor dans le plan.

## Links to prior stories

- **s14** : `ParentChildLink` model + `list_children` endpoint. Le parent lit ses enfants, le s17 les agrège en dashboard.
- **s15** : `assert_jwt_pseudo_matches_or_403` (pattern) + `get_current_user` + `require_role`. s17 réutilise ces helpers + crée son propre `assert_parent_linked_to_child_or_403`.
- **s16** : `aggregate_eleve_dashboard` (pure function) + `EleveDashboardResponse` schema + cache + `DashboardClient` (refactor cible). Le s17 réutilise 90% de s16 et refactore 10%.
