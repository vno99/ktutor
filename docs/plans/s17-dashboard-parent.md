---
validated: yes
---

# Plan — Story s17-dashboard-parent

Branch: `feature/s17-dashboard-parent`
Research: `docs/research/s17-dashboard-parent.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s17-dashboard-parent.md` + `.html` — UI reference, not code to copy.
Complexity (re-scored): **3** (story declared 3, confirmed after reading the code — point chaud: the `readOnly` refactor of `DashboardClient`, but option a is 5 lines of diff vs 80 for option b, so the story stays bounded at ~11 tasks).

## Target story

Vue parent lecture seule du dashboard eleve : `GET /api/dashboard/parent` (JWT auth, agrège les dashboards des enfants liés) + page `/dashboard/parent` (liste) + page `/dashboard/parent/[child_pseudo]` (child-detail en read-only) + helper cross-tenant `assert_parent_linked_to_child_or_403` + refactor de `DashboardClient` avec prop `readOnly` + tests d'isolation.

| Endpoint | Body in | Body out | Codes |
| --- | --- | --- | --- |
| `GET /api/dashboard/parent` | — (JWT header only) | `ParentDashboardResponse { children: [ChildDashboardEntry] }` où `ChildDashboardEntry { pseudo: str, linked_at: datetime, dashboard: EleveDashboardResponse }` | 200, 401, 403, 500 |

**Acceptance criteria** (6, all in scope) — AC1 endpoint + contract, AC2-AC3 page rendering + readOnly, AC4-AC5 tests d'isolation cross-tenant, AC6 test du masquage des boutons d'édition.

## Arbitrages (must be enacted in the plan, from research + design)

1. **Refactor `readOnly: boolean` prop** sur `DashboardClient` (option a, 5 lignes de diff). Bouton « Rafraîchir » reste. CTA « Aller au chat » (empty state) et bouton « Voir les détails » (Subject cards) sont **supprimés du DOM** (pas masqués en CSS) en `readOnly={true}`. Tâche 7.
2. **Cache partagé eleve/parent** : `dashboard:eleve:{child_pseudo}` est réutilisé tel quel (l'invalidation est par `pseudo` enfant). Le parent bénéficie du cache populé par l'eleve. Pas de nouveau cache key. Tâche 4.
3. **Endpoint unique `GET /api/dashboard/parent`** qui agrège en 1 requête (1 + N queries batchées, pas N+1). Évite la cascade d'appels frontend. Tâche 4.
4. **Helper `assert_parent_linked_to_child_or_403`** dans `backend/app/core/auth/middleware.py` (pattern répliqué de `assert_jwt_pseudo_matches_or_403` s15). Filtre `ParentChildLink.parent_pseudo == user.pseudo` ET `child_pseudo == claimed`. Admin bypass aligné sur s15. Tâche 1.
5. **RBAC endpoint** : `Depends(require_role(["parent", "admin"]))` sur `/api/dashboard/parent` — un eleve qui hit cet endpoint reçoit **403 `forbidden`**, pas une liste vide (cohérent avec le pattern RBAC strict s15). Tâche 4.
6. **Header post-JWT par rôle** : extension de `Header.tsx` avec prop `activeNav?: "eleve" | "parent" | null`. Le layout `(dashboard)/[locale]/layout.tsx` calcule `activeNav` depuis `useAuthStore.role` après hydration. Le layout reste mutualisé entre s16 et s17. Tâche 9.
7. **`ParentChildLink.created_at`** (modèle s14) est réutilisé comme `linked_at` dans la réponse — pas de nouvelle colonne, pas de migration. Tâche 2 + 4.

## Tasks (ordered)

1. [x] **Helper `assert_parent_linked_to_child_or_403`** dans `backend/app/core/auth/middleware.py` (ajout, ~35 lignes) :
   - Signature : `def assert_parent_linked_to_child_or_403(user: User, claimed: str | None, *, route: str, db: Session) -> None`.
   - Branches (alignées sur `assert_jwt_pseudo_matches_or_403` s15) :
     - `claimed is None` → no-op (pour endpoints où l'URL ne contient pas de child, comme `GET /api/dashboard/parent` qui agrège TOUS les enfants).
     - `claimed.lower() == user.pseudo.lower()` → no-op (le parent peut voir son propre dashboard, edge case rare mais autorisé par s14).
     - `user.role is UserRole.ADMIN` → bypass, log DEBUG `auth.middleware.admin_bypass` (cohérent avec s15).
     - **DB lookup** : `db.query(ParentChildLink).filter(ParentChildLink.parent_pseudo == user.pseudo, ParentChildLink.child_pseudo == claimed).first()`. Si trouvé → no-op. Si absent → log INFO `security.cross_tenant_attempt caller={} claimed={} role={} route={}` et raise `HTTPException(403, "forbidden")`.
   - **Import** : `from app.core.database.models import ParentChildLink, User, UserRole` + `from sqlalchemy.orm import Session`. Le `db: Session` est passé en paramètre (pas importé globalement) pour rester testable.
   - **Note** : le helper s15 (`assert_jwt_pseudo_matches_or_403`) NE nécessite pas de `db`. Le nouveau helper a besoin d'une query SQL (vérifier la liaison), donc `db` est obligatoire. Le pattern est aligné mais l'API diffère.
   - **Vérification** : `python -c "from app.core.auth.middleware import assert_parent_linked_to_child_or_403"` passe ; `ruff check app/core/auth/middleware.py` 0 warning.

2. [x] **Schemas Pydantic** dans `backend/app/api/dashboard/schemas.py` (extension du fichier s16, +20 lignes) :
   - Importer `EleveDashboardResponse` (existant, s16).
   - `ChildDashboardEntry { pseudo: str, linked_at: datetime, dashboard: EleveDashboardResponse }` — `linked_at` correspond à `ParentChildLink.created_at`.
   - `ParentDashboardResponse { children: list[ChildDashboardEntry] }` — liste peut être vide si le parent n'a aucun enfant lié (PAS 404, c'est un état valide).
   - Réutiliser les mêmes contraintes Pydantic que s16 (regex pseudo, ge=0/le=1 sur score_avg, etc.).
   - **Vérification** : `python -c "from app.api.dashboard.schemas import ParentDashboardResponse, ChildDashboardEntry; print(ParentDashboardResponse.model_json_schema())"` affiche le JSON schema.

3. [x] **Tests helper cross-tenant** dans `backend/tests/core/auth/test_assert_parent_linked.py` (nouveau fichier, ≥ 5 tests) :
   - **Fixtures** : `rsa_keypair`, `_point_settings`, `db_engine`, `session_factory` (dupliquées depuis `test_eleve.py:30-50`, AGENTS.md « Pas de refactor transverse »).
   - `_bearer` helper — non requis ici (le helper ne dépend pas de la couche HTTP, c'est un test unitaire).
   - **Factory** : `seeded_user(pseudo, role)` et `seeded_link(parent, child)` (crée un `ParentChildLink`).
   - **`TestAssertParentLinkedToChild`** :
     - `test_claimed_none_is_noop` : `claimed=None` → return None, pas d'exception.
     - `test_claimed_self_is_noop` : `claimed=user.pseudo` (parent linked to self) → return None.
     - `test_claimed_linked_child_passes` : parent Alice linked to child Bob, `assert_parent_linked_to_child_or_403(alice, "bob", route=..., db=...)` → return None.
     - `test_claimed_unlinked_child_raises_403` : parent Alice linked to child Bob, tente `assert_parent_linked_to_child_or_403(alice, "charlie", ...)` → `HTTPException(403, "forbidden")`.
     - `test_admin_bypasses_link_check` : admin (pas dans ParentChildLink) tente `assert_parent_linked_to_child_or_403(admin, "any_child", ...)` → return None (bypass).
     - `test_case_insensitive_match` : parent linked to "bob" tente `assert_parent_linked_to_child_or_403(parent, "BOB", ...)` → return None (aligné sur la `func.lower` du modèle s14).
   - **Vérification** : `pytest backend/tests/core/auth/test_assert_parent_linked.py -v` → 6/6 pass.

4. [x] **Router `GET /api/dashboard/parent`** dans `backend/app/api/dashboard/parent.py` (nouveau fichier, ~70 lignes) :
   - Endpoint `GET /api/dashboard/parent`.
   - Signature : `def get_parent_dashboard(user: User = Depends(require_role(["parent", "admin"])), db: Session = Depends(get_db)) -> ParentDashboardResponse`.
   - **Pas de query param** : la liste des enfants est dérivée du JWT (`user.pseudo`).
   - **Étapes** :
     1. Si `user.role is UserRole.ADMIN` → query tous les `ParentChildLink` (admin peut tout voir). Sinon → query `db.query(ParentChildLink).filter(ParentChildLink.parent_pseudo == user.pseudo).all()`.
     2. Pour chaque `link.child_pseudo` : appeler `aggregate_eleve_dashboard(db, link.child_pseudo)` (réutilisé de s16) et `get_dashboard(link.child_pseudo)` (cache check) avant — si cache hit, on évite la query SQL.
     3. Construire la liste `children: [ChildDashboardEntry(pseudo=link.child_pseudo, linked_at=link.created_at, dashboard=EleveDashboardResponse)]`.
     4. Trier par `linked_at` DESC (les enfants les plus récemment liés en premier) — l'ordre serveur est stable, le frontend ne trie pas.
   - **Performance** : pour 1-3 enfants (cas POC), N queries SQL sont OK. Si on veut scaler, on batch les aggregations en 1 query `GROUP BY student_pseudo` — out of scope POC, gap noté.
   - **Erreurs** : laisser remonter `SQLAlchemyError` en 500 (AGENTS.md § Erreurs). Le `require_role` s15 lève 403 si l'eleve hit.
   - **`__init__.py`** : `backend/app/api/dashboard/__init__.py` existe déjà (s16). Pas de modif.
   - **Montage** dans `backend/app/main.py` : `from app.api.dashboard.parent import router as dashboard_parent_router; app.include_router(dashboard_parent_router, prefix="/api/dashboard", tags=["dashboard"])`.
   - **Vérification** : `python -c "from app.main import app; print([r.path for r in app.routes if 'dashboard' in r.path])"` liste `/api/dashboard/parent`.

5. [x] **Tests router `GET /api/dashboard/parent`** dans `backend/tests/api/dashboard/test_parent.py` (nouveau fichier, ≥ 6 tests) :
   - **Fixtures** : `rsa_keypair`, `_point_settings`, `db_engine`, `session_factory`, `client`, `seeded_parent_alice`, `seeded_parent_paul`, `seeded_eleve_bob`, `seeded_eleve_charlie`, `seeded_eleve_dave`, `seeded_admin`, `_bearer` (dupliquées depuis `test_eleve.py:30-90`).
   - **Helper** : `seed_link(parent, child)` (crée un `ParentChildLink`).
   - **`TestGetParentDashboardAuth`** :
     - `test_no_token_returns_401` : pas de `Authorization` → 401 `{"error": "Token invalide ou expiré.", "code": "invalid_token"}`.
     - `test_eleve_returns_403` : bearer eleve bob → 403 `{"code": "forbidden"}` (via `require_role(["parent", "admin"])`).
   - **`TestGetParentDashboardHappy`** :
     - `test_returns_empty_list_when_parent_has_no_children` : bearer parent alice (0 enfant lié) → 200 avec `children: []`.
     - `test_returns_dashboards_for_all_linked_children` : bearer parent alice linked to bob + charlie (chacun avec 2 attempts) → 200 avec `children.length == 2`, chaque entrée contient `pseudo`, `linked_at`, `dashboard.subjects`. **Note** : réinitialiser le cache avant le test (`invalidate_dashboard` fixture autouse).
   - **`TestGetParentDashboardCache`** :
     - `test_reuses_eleve_cache_for_child_dashboards` : 1er call (cache miss, `set_dashboard` appelé pour bob et charlie). 2ème call (cache hit, `aggregate_eleve_dashboard` appelé 0 fois). Vérifier via `unittest.mock.patch` sur `aggregate_eleve_dashboard`, `assert_not_called` au 2ème call.
   - **`TestGetParentDashboardCrossTenant`** :
     - `test_parent_alice_does_not_see_pauls_children` : bearer parent alice linked to bob ; créer parent paul linked to charlie. Alice hit `/api/dashboard/parent` → 200 avec `children: [{pseudo: "bob", ...}]`, charlie absent.
     - `test_admin_sees_all_links` : bearer admin → 200 avec tous les enfants de tous les parents (2+ enfants dans le résultat).
   - **Vérification** : `pytest backend/tests/api/dashboard/test_parent.py -v` → 6/6 pass.

6. [x] **Refactor `DashboardClient.tsx` avec prop `readOnly`** dans `frontend/app/(dashboard)/[locale]/dashboard/eleve/DashboardClient.tsx` (modification, ~10 lignes de diff) :
   - Importer `Eye` Lucide icon (déjà installé en s11c).
   - Ajouter `readOnly?: boolean` à l'interface props (défaut `false` pour ne pas casser s16).
   - **Bouton « Rafraîchir » (l. 278)** : reste affiché en `readOnly={true}`. Le parent peut rafraîchir.
   - **Bouton « Réessayer » (l. 370)** : reste affiché en `readOnly={true}`. Une erreur réseau, c'est pareil pour l'eleve et le parent.
   - **Empty state CTA « Aller au chat » (l. 395-400)** : wrappé dans `{!readOnly && <a ...>}`. Le parent n'a pas de chat.
   - **Bouton « Voir les détails » dans les Subject cards** : wrappé dans `{!readOnly && <Button ...>}` (si s16 l'a déjà wrappé avec `aria-disabled`, c'est juste un `{!readOnly && ...}` en plus).
   - **Pastille read-only** (optionnel, dans le composant) : `{readOnly && <div className="..."><Eye /> Vue parent — lecture seule</div>}`. Affichée au-dessus du dashboard. Le label est i18n (cf. Tâche 10).
   - **Tests** : s16 a un e2e `dashboard.spec.ts`. Ajouter `test_readOnly_hides_edit_buttons` : naviguer sur la page avec `?readOnly=true` (ou via un query param de debug out-of-scope — **recommandation** : tester via un mock du composant parent, ou via l'inspection DOM des pages `/dashboard/parent/[child_pseudo]` (Tâche 11)). On accepte que le test de masquage soit fait en e2e, pas en unitaire composant.
   - **Vérification** : `cd frontend && npx tsc --noEmit` 0 erreur ; le diff git montre ~10 lignes modifiées (ajout de la prop + 3 conditions `{!readOnly && ...}` + 1 pastille).

7. [x] **Header post-JWT avec nav par rôle** dans `frontend/components/Header.tsx` (extension, ~25 lignes) :
   - Ajouter une prop optionnelle `activeNav?: "eleve" | "parent" | null` à l'interface `HeaderProps`. Défaut `null` (le header public ne montre pas la nav post-JWT).
   - Si `activeNav === "eleve"` : afficher un lien `<Link href="/dashboard/eleve">` avec `text-primary` + `border-b-2 border-primary` si le pathname matche. Label : `dashboard.nav.eleve` (« Tableau de bord » / « Dashboard »).
   - Si `activeNav === "parent"` : afficher un lien `<Link href="/dashboard/parent">` avec le même style si le pathname matche. Label : `dashboard.nav.parent` (« Mes enfants » / « My children »).
   - **i18n** : `dashboard.nav.eleve` et `dashboard.nav.parent` (s17 ajoute ces 2 clés — elles sont aussi utilisées par s16, mais s16 n'a pas livré de nav post-JWT, on les ajoute maintenant en s17 et s16 pourra les réutiliser si elle étend le layout dashboard dans une story future).
   - **Visibilité** : masquer la nav si `activeNav === null` (header public s11a-s11c). Garder l'aria-current="page" sur le lien actif.
   - **Vérification** : `cd frontend && npx tsc --noEmit` 0 erreur ; les pages publiques (s11a-s11c) ne montrent pas la nav post-JWT (prop absente).

8. [x] **Layout `(dashboard)/[locale]/layout.tsx` mutualisé avec nav par rôle** dans `frontend/app/(dashboard)/[locale]/layout.tsx` (modification, ~15 lignes) :
   - Importer `useAuthStore` et `usePathname` (déjà utilisés dans `AuthGuard.tsx`).
   - Dans le composant `DashboardLayout` (qui est **async server component**), on ne peut pas lire le store Zustand directement. **Solution** : extraire un sous-composant client `DashboardShell` qui wrappe les children et lit `useAuthStore` :
     ```tsx
     // DashboardShell.tsx (nouveau, 'use client', ~20 lignes)
     'use client';
     import { useAuthStore } from '@/lib/stores/authStore';
     import { Header } from '@/components/Header';
     export function DashboardShell({ children, locale }: { children: ReactNode; locale: string }) {
       const role = useAuthStore((s) => s.role);
       const activeNav = role === 'eleve' ? 'eleve' : role === 'parent' ? 'parent' : null;
       return (
         <>
           <Header activeNav={activeNav} />
           <main id="main" className="min-h-[calc(100vh-3.5rem)] bg-canvas">{children}</main>
         </>
       );
     }
     ```
   - Le layout dashboard (`layout.tsx`) appelle `<DashboardShell locale={locale}>{children}</DashboardShell>` au lieu de `<main>{children}</main>`. L'`<AuthGuard>` reste en place autour.
   - **Note** : actuellement le layout n'a pas de `<Header>` (s16 a choisi de ne pas en mettre, gap design-system). On en ajoute un maintenant pour s17. C'est un changement marginal : le Header public reste sur `(public)/`, le Header dashboard apparaît sur `(dashboard)/`. s16 n'est pas cassé (le header ne s'affichait pas, maintenant il s'affiche, mais c'est un ajout non-breaking).
   - **Vérification** : `cd frontend && npx tsc --noEmit` 0 erreur ; navigation manuelle sur `/fr/dashboard/eleve` montre le header avec le lien actif.

9. [x] **Page `/dashboard/parent` + ParentListClient** dans `frontend/app/(dashboard)/[locale]/parent/page.tsx` (nouveau, ~30 lignes) + `frontend/app/(dashboard)/[locale]/parent/ParentListClient.tsx` (nouveau, ~200 lignes) :
   - **`page.tsx`** (server component, réplique du pattern `eleve/dashboard/page.tsx`) :
     - `export const dynamic = "force-dynamic"`.
     - Server-side : récupère l'access token via `cookies()` (helper next/headers), appelle `apiClient.get('/api/dashboard/parent', { headers: { Authorization: `Bearer ${token}` } })`, gère 401 (redirect `/login`), passe les données initiales à `<ParentListClient>`.
     - **Note** : pour un admin, l'API retourne TOUS les enfants de TOUS les parents (cf. Tâche 4). C'est intentionnel (admin debug), mais l'UI admin pourrait afficher une vue différente — gap s22.
   - **`ParentListClient.tsx`** (`'use client'`) :
     - 4 états : loading (textuel + spinner), empty (Card centrée avec icône `users` 48px), error (réseau/401/403/500), success (grille de Child cards + bouton Rafraîchir).
     - **Child card** : `<a href={/${locale}/dashboard/parent/${child.pseudo}}>` wrappant un `<Card>`-like layout : avatar (initiale en `bg-primary/10 text-primary`), nom + pseudo + « Lié depuis le {date} », valeur « X % » (ou « — » si pas d'activité), badge indicateur, chevron `arrow-right`. Hover : `border-primary/40`.
     - **Bouton Rafraîchir** : `<Button variant="primary" size="md">` avec icône `refresh-cw` / `loader-2`. Appelle `apiClient.get('/api/dashboard/parent')` (le `Cache-Control: no-cache` est honoré par le frontend mais pas propagé au cache backend, on accepte le TTL 5 min — même décision que s16).
     - **i18n** : `useTranslations('dashboard.parent')` partout (cf. Tâche 10).
     - **Format de date** : `new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(linked_at))`.
   - **Vérification** : `cd frontend && npx tsc --noEmit` 0 erreur ; `cd frontend && npx next build` build OK.

10. [x] **i18n** dans `frontend/messages/fr.json` + `frontend/messages/en.json` (extension namespace `dashboard.parent`, ~22 clés) :
    - `dashboard.parent.listTitle` — « Mes enfants » / « My children »
    - `dashboard.parent.listSubtitle` — « Suis la progression de chacun de tes enfants. » / « Track the progress of each of your children. »
    - `dashboard.parent.readOnly` — « Vue parent — lecture seule » / « Parent view — read-only »
    - `dashboard.parent.readOnlyAria` — « Mode lecture seule : tu peux consulter les données de tes enfants mais pas les modifier. » / « Read-only mode: you can view your children's data but not modify it. »
    - `dashboard.parent.linkedSince` — « Lié depuis le {date} » / « Linked since {date} » (`t.rich` ou interpolation simple)
    - `dashboard.parent.successRate` — « Taux de réussite » / « Success rate » (dupliqué depuis `dashboard.eleve.subjectRate` — recommandation : dupliquer pour autonomie, pas de cross-namespace)
    - `dashboard.parent.noActivity` — « Pas encore d'activité » / « No activity yet »
    - `dashboard.parent.refreshList` — « Rafraîchir la liste » / « Refresh list »
    - `dashboard.parent.refreshingList` — « Rafraîchissement… » / « Refreshing… »
    - `dashboard.parent.emptyTitle` — « Aucun enfant lié à ton compte. » / « No children linked to your account. »
    - `dashboard.parent.emptySubtitle` — « Demande à un administrateur de lier un enfant à ton compte pour suivre sa progression. » / « Ask an administrator to link a child to your account to track their progress. »
    - `dashboard.parent.error403Role` — « Accès refusé. Cette page est réservée aux parents. » / « Access denied. This page is for parents only. »
    - `dashboard.parent.backHome` — « Retour à l'accueil » / « Back to home »
    - `dashboard.parent.backToList` — « Retour à la liste » / « Back to list »
    - `dashboard.parent.detailTitle` — « Progression de {child} » / « Progress of {child} » (`t.rich`)
    - `dashboard.parent.detailReadOnly` — « Vue parent — lecture seule · {child} » / « Parent view — read-only · {child} » (`t.rich`)
    - `dashboard.parent.cardAria` — « Accéder au tableau de bord de {child} » / « Go to {child}'s dashboard » (`t.rich`)
    - `dashboard.parent.detail403` — « Accès refusé. Cet enfant n'est pas lié à ton compte. » / « Access denied. This child is not linked to your account. »
    - `dashboard.parent.loadingList` — « Chargement de tes enfants… » / « Loading your children… »
    - `dashboard.parent.loadingDetail` — « Chargement du tableau de bord de {child}… » / « Loading {child}'s dashboard… » (`t.rich`)
    - `dashboard.parent.refresh` — « Rafraîchir » / « Refresh » (dupliqué depuis `dashboard.eleve.refresh`)
    - `dashboard.parent.refreshing` — « Rafraîchissement… » / « Refreshing… » (dupliqué depuis `dashboard.eleve.refreshing`)
    - `dashboard.parent.retry` — « Réessayer » / « Retry » (dupliqué depuis `dashboard.eleve.retry`)
    - `dashboard.nav.eleve` — « Tableau de bord » / « Dashboard »
    - `dashboard.nav.parent` — « Mes enfants » / « My children »
    - **Pas de hardcoded strings** : `useTranslations('dashboard.parent')` partout. Vérifié par `frontend/scripts/check-i18n.sh` (exit 0 obligatoire en CI).
    - **Vérification** : `cd frontend && bash scripts/check-i18n.sh` exit 0 ; clés présentes dans fr.json ET en.json.

11. [x] **Page `/dashboard/parent/[child_pseudo]` + ParentChildClient** dans `frontend/app/(dashboard)/[locale]/parent/[child_pseudo]/page.tsx` (nouveau, ~30 lignes) + `frontend/app/(dashboard)/[locale]/parent/[child_pseudo]/ParentChildClient.tsx` (nouveau, ~150 lignes) :
    - **`page.tsx`** (server component) :
      - `export const dynamic = "force-dynamic"`.
      - `params: Promise<{ locale: string; child_pseudo: string }>` (Next.js 16 async params).
      - Server-side fetch `apiClient.get('/api/dashboard/eleve', { params: { pseudo: child_pseudo }, headers: { Authorization: `Bearer ${token}` } })`. Note : on utilise l'endpoint s16 eleve avec `?pseudo=` car l'admin bypass + l'extension parent du helper couvrent notre cas. **Vérification** : 401 (redirect login), 403 (afficher le message `forbidden` côté client), 200 (passer les données).
    - **`ParentChildClient.tsx`** (`'use client'`) :
      - États : loading, error (3 sous-types : 401, 403, réseau, 500), success.
      - **Back link** « ← Retour à la liste » (`text-sm text-text-secondary`).
      - **Titre de page** « Progression de {child_pseudo} ».
      - **Pastille read-only** : `bg-primary/10 text-primary` + icône `eye` + « Vue parent — lecture seule · {child_pseudo} ».
      - **DashboardClient wrappé en readOnly** : `<DashboardClient data={data} readOnly={true} />` (Tâche 6). Le DashboardClient gère ses 4 états internes (loading/empty/error/success) ; on lui passe directement les données initiales via la prop `data`.
      - **Note** : pour l'empty state, le `DashboardClient` affichera son empty state s16 « Tu n'as pas encore tenté d'exercice. » SANS le CTA « Aller au chat » (masqué par `readOnly={true}`). C'est cohérent — le parent voit que l'enfant n'a pas d'activité.
      - **Bouton « Rafraîchir »** : reste, géré par DashboardClient.
      - **Erreur 403 custom** : si l'API renvoie 403, on affiche un Card erreur spécifique « Accès refusé. Cet enfant n'est pas lié à ton compte. » + bouton « Retour à la liste ». Le `DashboardClient` a un état 403 générique, mais on l'override ici pour avoir le bon message + le bon bouton.
    - **Vérification** : `cd frontend && npx tsc --noEmit` 0 erreur ; navigation manuelle sur `/fr/dashboard/parent/alice` rend le dashboard sans CTA empty.

12. [x] **Tests e2e + axe-core + Lighthouse a11y** dans `frontend/e2e/dashboard-parent.spec.ts` (nouveau fichier, ≥ 5 tests) + `frontend/lighthouserc.json` (modification) :
    - **`frontend/e2e/dashboard-parent.spec.ts`** (Playwright + @axe-core/playwright) :
      - **Setup** : créer 1 parent (alice_parent), 1 admin, 3 eleves (bob, charlie, dave). Lier alice_parent à bob et charlie via `POST /api/users/alice_parent/children`. Login alice_parent. Seed 2 attempts pour bob et 1 attempt pour charlie (via l'endpoint Attempt à venir, ou via un helper de seed direct DB — **si pas d'endpoint HTTP, skip et tester avec mocks**, cf. research Fait 6).
      - **`TestParentListPage`** :
        - `test_renders_list_of_linked_children` : navigate `/fr/dashboard/parent` → assert 2 Child cards (bob + charlie), chaque card avec valeur % + badge + chevron.
        - `test_empty_state_when_no_children_linked` : login parent (pas d'enfant lié) → assert empty state Card avec icône `users` + message.
        - `test_redirects_to_login_when_unauthenticated` : pas de login, navigate `/fr/dashboard/parent` → assert URL = `/fr/login?next=%2Ffr%2Fdashboard%2Fparent`.
        - `test_eleve_cannot_access_parent_dashboard` : login eleve bob, navigate `/fr/dashboard/parent` → assert page d'erreur 403 avec message « Accès refusé. Cette page est réservée aux parents. ».
        - `test_axe_core_no_critical_or_serious_violations` : `@axe-core/playwright` scan, assert 0 violation `critical` + 0 `serious`.
      - **`TestParentChildDetailPage`** :
        - `test_renders_read_only_dashboard_for_linked_child` : login alice_parent, navigate `/fr/dashboard/parent/bob` → assert DashboardClient rendu, pastille read-only visible, bouton « Aller au chat » absent (CTA empty), bouton « Voir les détails » absent dans Subject cards. **C'est le test AC #6**.
        - `test_403_when_parent_not_linked_to_child` : login alice_parent, navigate `/fr/dashboard/parent/dave` (dave non lié) → assert page d'erreur 403 « Accès refusé. Cet enfant n'est pas lié à ton compte. ».
        - `test_axe_core_no_critical_or_serious_violations_on_child_detail` : idem liste.
    - **`frontend/lighthouserc.json`** : étendre le tableau `collect.url` avec `"http://localhost:3000/fr/dashboard/parent"` et `"http://localhost:3000/fr/dashboard/parent/alice"`. L'assertion `assertions` reste la même.
    - **Vérification** : `pnpm exec playwright test e2e/dashboard-parent.spec.ts --reporter=list` 5/5+ pass ; `pnpm exec lhci collect` score a11y ≥ 90 sur les 2 URLs.

13. [x] **Run full backend + frontend test suite + i18n check** :
    - `cd backend && pytest tests/ -v --tb=short` → 0 régression sur les tests s04, s07, s09, s10, s12, s13, s13b, s14, s15, s16 existants.
    - `cd backend && ruff check app/ tests/` → 0 nouveau warning.
    - `cd backend && mypy app/` → 0 nouvelle erreur.
    - `cd frontend && npx tsc --noEmit` → 0 erreur TypeScript.
    - `cd frontend && bash scripts/check-i18n.sh` → exit 0 (22+ clés `dashboard.parent` + 2 `dashboard.nav` dans fr.json + en.json).
    - `cd frontend && pnpm exec playwright test e2e/ --reporter=list` → 0 régression sur les e2e s11a-s11c, s13, s15, s16 existants + 5+ nouveaux dashboard-parent.
    - **Vérification** : tous les jobs CI restent verts.

14. [x] **Conventional commit unique** : `feat(frontend+api): add parent dashboard with read-only child view (s17)` couvrant tous les fichiers modifiés + créés + le research + le design + le plan.
    - **Vérification** : `git log -1` montre un seul commit avec tous les fichiers.

## Run interdicts

- **Pas de nouveau cache key** (`dashboard:parent:{parent_pseudo}`) : on réutilise `dashboard:eleve:{child_pseudo}` (cf. Arbitrage #2). Une entrée par `pseudo` enfant suffit — l'invalidation est par pseudo enfant, le parent en bénéficie.
- **Pas d'endpoint `/api/dashboard/parent/{child_pseudo}`** : le frontend appelle `/api/dashboard/eleve?pseudo={child_pseudo}` (s16) avec le helper cross-tenant s17 (Tâche 1). Ça évite d'avoir 2 endpoints qui retournent la même structure.
- **Pas de modification d'`Attempt`** : on ne touche pas au modèle. La cache invalidation câblée par s16 (Tâche 8 s16) attend toujours le router HTTP `exercises` à venir — s17 n'a pas de router Attempt à créer.
- **Pas d'extraction `<DashboardView>` partagé** (option b) : on ajoute juste la prop `readOnly` (option a, 5 lignes de diff). Refactor transverse = hors-scope, complexifierait la review.
- **Pas de nouveau shared component** : pas de `<ChildCard>`, pas de `<ReadOnlyBadge>`, pas de `<EmptyParentState>`. Les composants sont inline dans `ParentListClient.tsx` (cf. AGENTS.md « Pas de logique métier dans un composant partagé »). Factorisation à s22 si d'autres stories en ont besoin.
- **Pas de toggle dark/light UI** : le shell supporte `data-theme` mais le toggle arrive en s22.
- **Pas de bottom tab bar mobile** : la nav post-JWT est dans le Header, pas en bottom bar. Gap design-system l.232.
- **Pas de filter/tri des enfants** : ordre serveur (`linked_at DESC`), pas de filtre UI.
- **Pas de notification parent** (« alice a tenté un exercice ») : gap s25.
- **Pas de log du password, hash, token, jti, ou body** : le helper cross-parent s17 log INFO `security.cross_tenant_attempt` (caller, claimed, role, route), pas de pseudo, pas de token, pas de body (cf. AGENTS.md § Backend logging).
- **Pas de refactor transverse des fixtures de test** : duplication assumée. `rsa_keypair`, `_point_settings`, `db_engine`, `session_factory`, `client`, `seeded_*`, `_bearer` sont dupliqués depuis `test_eleve.py:30-90` et `test_users_parent_child.py`.
- **Pas de commit sur la branche par défaut** : tout part sur `feature/s17-dashboard-parent` (worktree dédié).

## The point everything turns on

**La décision centrale** : le `readOnly` prop sur `DashboardClient` (option a, 5 lignes de diff) est **le point chaud** de la story. Le composant est self-contained, ajouter une prop booléenne est le changement minimal pour masquer 2 boutons (CTA empty + Voir détails). Le bouton « Rafraîchir » reste (le parent rafraîchit aussi), le bouton « Réessayer » reste (pareil pour les erreurs réseau).

Trois pièges à surveiller :

1. **Le helper `assert_parent_linked_to_child_or_403` a besoin d'une `db` query**, contrairement à `assert_jwt_pseudo_matches_or_403` s15. C'est un coût DB (1 query `SELECT * FROM parent_child_links WHERE parent_pseudo=? AND child_pseudo=?`). Pour N enfants dans `GET /api/dashboard/parent`, on a **N queries** (1 par agrégation, déjà le cas) **+ 0 query cross-tenant** (le helper n'est pas appelé pour cet endpoint — il est appelé seulement dans la child-detail où le `child_pseudo` est dans l'URL). Le coût est négligeable pour la POC (1-3 enfants par parent).

2. **Cache key collision eleve/parent** : `dashboard:eleve:{child_pseudo}` est partagé. Si l'eleve alice hit `/api/dashboard/eleve` (cache miss → set), puis son parent hit `/api/dashboard/parent` (cache hit via `aggregate_eleve_dashboard` check), le parent bénéficie du cache populé par l'eleve. C'est **intentionnel** (cf. recherche Piège n°3). Test `test_reuses_eleve_cache_for_child_dashboards` (Tâche 5) couvre.

3. **Le `DashboardClient` est wrappé 2 fois** (s16 sans `readOnly`, s17 avec `readOnly={true}`). Le composant doit rester **rétrocompatible** : la prop `readOnly` est optionnelle avec défaut `false`. **Vérification** : `npx tsc --noEmit` 0 erreur, et l'e2e s16 (`e2e/dashboard.spec.ts`) passe sans modification (le `readOnly` n'est jamais passé, donc le comportement s16 est inchangé).

Vérification finale par le reviewer : (a) `grep -rn "assert_parent_linked_to_child_or_403" backend/app/` montre le helper, l'appel et les tests ; (b) `grep -rn "readOnly" frontend/app/\(dashboard\)/[locale]/dashboard/eleve/DashboardClient.tsx` montre les 3 conditions `{!readOnly && ...}` ; (c) `grep -rn "dashboard.parent" frontend/messages/` montre les 22+ clés i18n ; (d) `cd frontend && pnpm exec playwright test e2e/dashboard-parent.spec.ts` 5+ tests pass.

## Files touched

**Créés** :
- `backend/app/api/dashboard/parent.py` (~70 lignes, router)
- `backend/tests/core/auth/__init__.py` (vide, ~1 ligne)
- `backend/tests/core/auth/test_assert_parent_linked.py` (~150 lignes, 6 tests)
- `backend/tests/api/dashboard/test_parent.py` (~250 lignes, ≥ 6 tests)
- `frontend/app/(dashboard)/[locale]/DashboardShell.tsx` (~20 lignes, client wrapper pour Header + nav par rôle)
- `frontend/app/(dashboard)/[locale]/parent/page.tsx` (~30 lignes, server entry)
- `frontend/app/(dashboard)/[locale]/parent/ParentListClient.tsx` (~200 lignes, 4 états + grille Child cards)
- `frontend/app/(dashboard)/[locale]/parent/[child_pseudo]/page.tsx` (~30 lignes, server entry)
- `frontend/app/(dashboard)/[locale]/parent/[child_pseudo]/ParentChildClient.tsx` (~150 lignes, 4 états + DashboardClient readOnly wrappé)
- `frontend/e2e/dashboard-parent.spec.ts` (~200 lignes, 7+ tests)
- `docs/research/s17-dashboard-parent.md` (déjà créé)
- `docs/designs/s17-dashboard-parent.md` (déjà créé)
- `docs/designs/s17-dashboard-parent.html` (déjà créé)
- `docs/plans/s17-dashboard-parent.md` (ce fichier)

**Modifiés** :
- `backend/app/core/auth/middleware.py` (+35 lignes : helper `assert_parent_linked_to_child_or_403` + import)
- `backend/app/api/dashboard/schemas.py` (+20 lignes : `ChildDashboardEntry` + `ParentDashboardResponse`)
- `backend/app/main.py` (+2 lignes : import + `include_router` pour `dashboard_parent_router`)
- `frontend/app/(dashboard)/[locale]/dashboard/eleve/DashboardClient.tsx` (+10 lignes : prop `readOnly` + 3 conditions `{!readOnly && ...}` + pastille read-only)
- `frontend/app/(dashboard)/[locale]/layout.tsx` (+5 lignes : wrappe children dans `<DashboardShell>`)
- `frontend/components/Header.tsx` (+25 lignes : prop `activeNav` + 2 liens conditionnels)
- `frontend/messages/fr.json` (+24 clés : namespace `dashboard.parent.*` + `dashboard.nav.eleve` + `dashboard.nav.parent`)
- `frontend/messages/en.json` (idem)
- `frontend/lighthouserc.json` (+2 entrées dans `collect.url` : `/fr/dashboard/parent` + `/fr/dashboard/parent/<child_pseudo>`)

**Non touchés (volontairement)** :
- `backend/app/core/database/models.py` — `ParentChildLink` reste avec `created_at` (utilisé comme `linked_at`, pas de nouvelle colonne)
- `backend/app/services/dashboard/aggregator.py` — réutilisé tel quel (Tâche 4 appelle `aggregate_eleve_dashboard`)
- `backend/app/services/dashboard/cache.py` — réutilisé tel quel (cache key inchangée, partagée eleve/parent)
- `backend/app/api/dashboard/eleve.py` — pas de modif (s16 livré OK, l'endpoint reste utilisé par le child-detail parent via `?pseudo=`)
- `frontend/app/(public)/[locale]/layout.tsx` — pas de modif (le Header public n'a pas la nav post-JWT)
- `frontend/lib/stores/authStore.ts` — pas de modif (le store est utilisé tel quel, `role` déjà disponible)
- `frontend/lib/api.ts` — pas de modif (l'interceptor JWT suffit, pas d'extension)
- `frontend/components/Card.tsx`, `Button.tsx`, `Input.tsx`, `Label.tsx`, `Select.tsx` — pas de modif (réutilisés tels quels)
- `docs/architecture.md` — pas de nouvelle section (la doc est correcte)
- `docs/design-system.md` — pas d'extension (les 15+ gaps sont notés dans `docs/designs/s17-dashboard-parent.md § 10`)
