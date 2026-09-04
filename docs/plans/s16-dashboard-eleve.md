---
validated: yes
---

# Plan — Story s16-dashboard-eleve

Branch: `feature/s16-dashboard-eleve`
Research: `docs/research/s16-dashboard-eleve.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s16-dashboard-eleve.md` + `.html` — UI reference, not code to copy.
Complexity (re-scored): **4** (story declared 3, raised after reading the code — three greenfield families: `app/api/dashboard/`, route group `(dashboard)/`, `recharts` dep). Plan bounded to **12 tasks** (vs ≤ 10 idéal), split deferred — research says optional, prefer one PR.

## Target story

Élève dashboard : `GET /api/dashboard/eleve` (JWT auth) + page `/dashboard/eleve` + cache 5 min + tests cross-tenant.

| Endpoint | Body in | Body out | Codes |
| --- | --- | --- | --- |
| `GET /api/dashboard/eleve` | — (JWT header only) | `EleveDashboardResponse {subjects: [SubjectSummary], global: GlobalSummary}` | 200, 401, 403, 500 |
| `GET /api/dashboard/eleve?pseudo=<x>` | — | idem, for `pseudo=<x>` | 200 (admin only), 403 (else) |

**Acceptance criteria** (6, all in scope) — AC1 endpoint + contract, AC2-AC3 page rendering + responsive, AC4 cache, AC5-AC6 tests.

## Arbitrages (must be enacted in the plan, from research)

1. **`score_avg` = `mean(Attempt.is_success)` per subject** (proxy ; `Attempt` only stores a bool, no numeric score). UI label: **« Taux de réussite »**, never « Score moyen » (the proxy would mislead). Tasks 4 + 7.
2. **`last_activity_at` = `MAX(attempts.submitted_at)`** joined to `exercises` filtered by `subject` and `student_pseudo`. Tasks 4 + 5.
3. **`exercises_count` = `COUNT(attempts.id)`** (= number of attempts, not distinct exercises). Tasks 4 + 5.
4. **Cache in-process** TTL 5 min **+ explicit invalidation** on each new `Attempt` inserted in `app/api/exercises/router.py`. Tests cover both paths. Tasks 2 + 6 + 10.
5. **Admin bypass** via `?pseudo=...` : use s15 helper `assert_jwt_pseudo_matches_or_403`. Task 3.
6. **Recharts** for the chart (architecture.md:36, design-system gap l.236). `pnpm add recharts@^2.13.0`. Task 7.

## Tasks (ordered)

1. [x] **Schemas Pydantic** dans `backend/app/api/dashboard/schemas.py` (nouveau fichier, ~50 lignes) :
   - `SubjectName = Literal["maths", "francais"]` (réutilise `Subject` enum existant via `Literal[...]`, **pas** de nouvel enum pour éviter le drift).
   - `SubjectSummary { name: SubjectName, score_avg: float, exercises_count: int, last_activity_at: datetime | None }` (Pydantic v2, `Field(..., ge=0, le=1)` sur `score_avg` ; `exercises_count >= 0`).
   - `GlobalSummary { score_avg: float, exercises_count: int, last_activity_at: datetime | None }` (mêmes contraintes).
   - `EleveDashboardResponse { subjects: list[SubjectSummary], global: GlobalSummary }` (liste peut être vide si l'élève n'a jamais tenté d'exercice).
   - **Vérification** : `python -c "from app.api.dashboard.schemas import EleveDashboardResponse; print(EleveDashboardResponse.model_json_schema())"` affiche le JSON schema.

2. [x] **Service aggregator** dans `backend/app/services/dashboard/aggregator.py` (nouveau fichier, ~80 lignes) :
   - `aggregate_eleve_dashboard(db: Session, pseudo: str) -> EleveDashboardResponse` (pure function, takes a session).
   - **Query 1** (per subject) : `SELECT e.subject, AVG(CAST(a.is_success AS FLOAT)) AS score_avg, COUNT(a.id) AS exercises_count, MAX(a.submitted_at) AS last_activity_at FROM attempts a JOIN exercises e ON a.exercise_id = e.id WHERE a.student_pseudo = :pseudo GROUP BY e.subject` → construit la liste `subjects`.
   - **Query 2** (global) : `SELECT AVG(CAST(a.is_success AS FLOAT)) AS score_avg, COUNT(a.id) AS exercises_count, MAX(a.submitted_at) AS last_activity_at FROM attempts a WHERE a.student_pseudo = :pseudo` → construit `global`. **Note** : `AVG` retourne `None` si la table est vide ; mapper à `0.0` + `last_activity_at=None`.
   - **Pas de filtre `COUNT > 0`** : la requête GROUP BY filtre naturellement les matières sans tentative. Si 0 matière → `subjects=[]`, `global.score_avg=0.0`, `global.exercises_count=0`.
   - **Empty edge case** : élève qui n'a jamais tenté d'exercice → `subjects=[]`, `global={score_avg: 0.0, exercises_count: 0, last_activity_at: None}`. Le router retourne 200, l'UI affiche l'empty state.
   - **Vérification** : `python -c "from app.services.dashboard.aggregator import aggregate_eleve_dashboard"` passe. Tests unitaires en Tâche 5.

3. [x] **Cache in-process** dans `backend/app/services/dashboard/cache.py` (nouveau fichier, ~40 lignes) :
   - Module-level `dict[str, tuple[float, EleveDashboardResponse]]` (clé = `f"dashboard:eleve:{pseudo}"`, valeur = `(expires_at_monotonic, data)`).
   - `get_dashboard(pseudo: str) -> EleveDashboardResponse | None` : lit, vérifie TTL, retourne `None` si expiré (pas de `raise`).
   - `set_dashboard(pseudo: str, data: EleveDashboardResponse, ttl_seconds: int = 300) -> None` : écrit avec TTL.
   - `invalidate_dashboard(pseudo: str) -> None` : supprime la clé.
   - **Injectable `now_fn`** : paramètre optionnel `now_fn: Callable[[], float] = time.monotonic` pour la testabilité (le test mock l'horloge).
   - **Thread safety** : `threading.Lock` autour des accès (FastAPI uvicorn workers sont single-threaded async mais pytest fixtures peuvent re-enter). Pas de `asyncio.Lock` (le module est sync).
   - **Vérification** : `python -c "from app.services.dashboard.cache import get_dashboard, set_dashboard, invalidate_dashboard"` passe.

4. [x] **Router `GET /api/dashboard/eleve`** dans `backend/app/api/dashboard/eleve.py` (nouveau fichier, ~80 lignes) :
   - Endpoint `GET /api/dashboard/eleve`.
   - Signature : `def get_eleve_dashboard(pseudo: str | None = Query(default=None, max_length=32, pattern=PSEUDO_REGEX), user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> EleveDashboardResponse`.
   - **Garde cross-tenant** : `assert_jwt_pseudo_matches_or_403(user, pseudo, route="/api/dashboard/eleve")` (importé depuis `app.core.auth.middleware`, livré s15). Si `pseudo is None` (cas par défaut, l'élève demande son propre dashboard) → no-op, on utilise `user.pseudo`. Si `pseudo is not None` (admin demande pour quelqu'un) → helper vérifie que `user.role is UserRole.ADMIN`, sinon 403.
   - **Cache lookup** : `cached = get_dashboard(target_pseudo)` où `target_pseudo = pseudo or user.pseudo`. Si hit non-expiré → return cached. **Note** : la clé cache est par `target_pseudo`, pas par `user.pseudo` — un admin hit avec `?pseudo=alice` cache pour `alice`, pas pour l'admin.
   - **Cache miss** : `data = aggregate_eleve_dashboard(db, target_pseudo)` ; `set_dashboard(target_pseudo, data)` ; return `data`.
   - **Erreurs** : laisser remonter les `SQLAlchemyError` en 500 via le handler FastAPI par défaut (pas de try/except muet, AGENTS.md § Erreurs).
   - **`__init__.py`** : `backend/app/api/dashboard/__init__.py` (vide, marque le sous-domaine).
   - **Montage** dans `backend/app/main.py` : `from app.api.dashboard.eleve import router as dashboard_eleve_router; app.include_router(dashboard_eleve_router, prefix="/api/dashboard", tags=["dashboard"])`. Importer après les routers existants (chat, documents, users).
   - **Vérification** : `python -c "from app.api.dashboard.eleve import router; print([r.path for r in router.routes])"` liste `/eleve` ; `python -c "from app.main import app; print([r.path for r in app.routes if 'dashboard' in r.path])"` liste `/api/dashboard/eleve`.

5. [x] **Tests aggregator** dans `backend/tests/services/dashboard/test_aggregator.py` (nouveau fichier, ≥ 5 tests) :
   - **Fixture** : `in_memory_db` (StaticPool SQLite en mémoire, `Base.metadata.create_all`), `seed_eleve_with_attempts` (crée 1 User + 3 Exercise [2 maths, 1 francais] + 5 Attempt avec `is_success` mixtes).
   - **`TestAggregateEleveDashboard`** :
     - `test_returns_empty_when_eleve_has_no_attempts` : élève alice, 0 Attempt → `subjects=[]`, `global.score_avg=0.0`, `global.exercises_count=0`, `global.last_activity_at=None`.
     - `test_groups_by_subject` : alice, 3 maths attempts (2 success, 1 fail) + 2 francais attempts (1 success, 1 fail) → `subjects=[{name: "maths", score_avg: 2/3, exercises_count: 3, last_activity_at: <max>}, {name: "francais", score_avg: 1/2, exercises_count: 2, last_activity_at: <max>}]`. **Ordre non-garanti** (GROUP BY sans ORDER BY) → on trie par `name` pour stabiliser l'assertion.
     - `test_global_avg_is_overall_not_mean_of_subjects` : si Maths 3 attempts (2/3) et Français 1 attempt (0/1), `global.score_avg = (2+0)/4 = 0.5`, **PAS** `mean(2/3, 0/1) = 1/6` (test du bug classique).
     - `test_filters_by_student_pseudo` : alice (3 attempts) + bob (2 attempts) → aggregator(alice) ne retourne que les attempts d'alice.
     - `test_last_activity_at_is_max_submitted_at` : 3 attempts à 3 timestamps distincts → `last_activity_at = max`. Edge case : 1 seul attempt → `last_activity_at = that.submitted_at`.
   - **Vérification** : `pytest backend/tests/services/dashboard/test_aggregator.py -v` → 5/5 pass.

6. [x] **Tests cache** dans `backend/tests/services/dashboard/test_cache.py` (nouveau fichier, ≥ 4 tests) :
   - **`TestDashboardCache`** :
     - `test_set_then_get_returns_data` : `set_dashboard("alice", data, ttl=300)` ; `clock=monotonic_base` ; `get_dashboard("alice", now_fn=lambda: monotonic_base + 10)` retourne `data`.
     - `test_expired_entry_returns_none` : `set_dashboard("alice", data, ttl=300)` ; `get_dashboard("alice", now_fn=lambda: monotonic_base + 301)` retourne `None`.
     - `test_invalidate_removes_entry` : set puis invalidate puis get → `None`.
     - `test_different_pseudos_have_separate_keys` : set("alice", ...) et set("bob", ...) ; get("alice") retourne alice data, get("bob") retourne bob data.
   - **Vérification** : `pytest backend/tests/services/dashboard/test_cache.py -v` → 4/4 pass.

7. [x] **Tests router `GET /api/dashboard/eleve`** dans `backend/tests/api/dashboard/test_eleve.py` (nouveau fichier, ≥ 6 tests) :
   - **Fixtures** : `rsa_keypair`, `_point_settings`, `db_engine`, `session_factory`, `client` (dupliquées depuis `test_users_create.py:79-166` + `test_documents.py`, AGENTS.md « Pas de refactor transverse »), `seeded_eleve_alice`, `seeded_eleve_bob`, `seeded_admin`, `seed_eleve_with_attempts(pseudo, attempts_data)` helper.
   - `_bearer(user) -> dict[str, str]` helper (réplique de `_admin_bearer`).
   - **`TestGetEleveDashboardAuth`** :
     - `test_no_token_returns_401_invalid_token` : pas de `Authorization` → 401 `{"error": "Token invalide ou expiré.", "code": "invalid_token"}`.
     - `test_expired_token_returns_401_invalid_token` : `create_access_token(alice.pseudo, alice.role, expires_delta=timedelta(seconds=-1))` → 401.
   - **`TestGetEleveDashboardHappy`** :
     - `test_returns_aggregated_data_for_authenticated_eleve` : bearer alice + 3 maths attempts (2 success) + 2 francais attempts (1 success) → 200 avec `subjects=[...]` et `global.score_avg` cohérent. **Note** : réinitialiser le cache avant le test (setUp appelle `invalidate_dashboard("alice")` via un fixture autouse).
     - `test_returns_empty_when_eleve_has_no_attempts` : bearer bob (jamais tenté) → 200 avec `subjects=[]`, `global.exercises_count=0`.
   - **`TestGetEleveDashboardCache`** :
     - `test_second_call_within_ttl_returns_cached_data` : 2 calls consécutifs avec le même bearer → 2ème call a `data == 1er` mais **la query SQL n'est appelée qu'une fois** (vérifier via `unittest.mock.patch` sur `aggregate_eleve_dashboard`, `assert_called_once`).
     - `test_invalidation_clears_cache` : 1er call (cache miss, `set_dashboard` appelé), `invalidate_dashboard("alice")`, 2ème call (cache miss, `set_dashboard` re-appelé) → `aggregate_eleve_dashboard` appelé 2 fois.
   - **`TestGetEleveDashboardCrossTenant`** :
     - `test_eleve_bob_cannot_query_alice_via_query_param` : bearer bob + `?pseudo=alice` → 403 `{"code": "forbidden"}`, log INFO `security.cross_tenant_attempt`. (Bob demande pour Alice, le helper refuse.)
     - `test_admin_can_query_any_eleve_via_query_param` : bearer admin + `?pseudo=alice` → 200 avec les données d'alice. (Admin bypass.)
     - `test_eleve_alice_cannot_query_bob_via_query_param` : bearer alice + `?pseudo=bob` → 403.
   - **Régression** : `test_no_regression_on_existing_endpoints` : sanity check que les autres routes (chat, documents) répondent encore (1 smoke test par route, ou skip si trop couplé).
   - **Vérification** : `pytest backend/tests/api/dashboard/test_eleve.py -v` → 6+ tests pass.

8. [x] **Cache invalidation on new Attempt** dans `backend/app/api/exercises/router.py` (modification, ~5 lignes) : **SKIPPED** — `backend/app/api/exercises/router.py` does not exist on `feature/s16-dashboard-eleve`. **Note factuelle (post-exécution, à l'attention de la review)** : s04 et s07 sont **shippés** (commits `3887644` QCM grader et `473181c` LLM-as-judge text grader, voir `git log --all --oneline --grep="s04\|s07"`), le modèle `Attempt` existe dans `backend/app/core/database/models.py`, et les services `qcm_grader` / `text_grader` existent dans `backend/app/services/exercises/`. Ce qui manque est un **router HTTP** qui crée un `Attempt` via API (les stories s04 / s07 ont livré les **graders** consommés en CLI, pas de endpoint REST). Le câblage `invalidate_dashboard` exige ce router. Per the plan, do NOT create the endpoint here. The dashboard cache will be invalidated by TTL (5 min) until an `exercises` HTTP router is shipped — by a future story, by an s16b, or by extending s04/s07.
   - Localiser l'endpoint qui crée un `Attempt` (router HTTP à venir — s04 / s07 ont livré les services de grading, pas de router REST). **Vérification préalable** : `grep -n "Attempt(" backend/app/api/exercises/router.py` ; si 0 hit, **STOP et reporter** que l'endpoint n'existe pas, l'invalidation sera câblée par la story qui crée le router.
   - Si l'endpoint existe : après le `session.add(Attempt(...))` et avant le `session.commit()`, ajouter `from app.services.dashboard.cache import invalidate_dashboard; invalidate_dashboard(pseudo=user.pseudo)`. (Si s04 utilise un `pseudo` body, utiliser `body.pseudo` ; si s15 a migré vers JWT, utiliser `user.pseudo` — adapter selon l'état du repo au moment de l'implémentation.)
   - **Note** : `set_dashboard` et `invalidate_dashboard` sont sync ; le router est probablement `async def` (FastAPI standard). Appeler `invalidate_dashboard(...)` directement (pas `await`) — c'est sync.
   - **Test régression** : ajouter un test dans `test_eleve.py` (`TestGetEleveDashboardCache::test_new_attempt_invalidates_cache`) qui :
     1. Crée un Attempt pour alice via l'endpoint s04/s07.
     2. Hit `/api/dashboard/eleve` (cache miss, set).
     3. Hit `/api/dashboard/eleve` (cache hit, 2ème call).
     4. Crée un 2ème Attempt pour alice.
     5. Hit `/api/dashboard/eleve` → **cache miss** (invalidation a marché), le `exercises_count` reflète le nouvel attempt.
   - **Si l'endpoint Attempt n'existe pas** : ne pas créer l'endpoint dans cette story (hors-scope — un router HTTP `exercises` n'a pas encore été livré ; les stories s04 / s07 ont livré les graders, pas le router). Câbler `invalidate_dashboard` est conditionnel — vérifier l'état du repo avant d'exécuter.
   - **Vérification** : `pytest backend/tests/api/dashboard/test_eleve.py::TestGetEleveDashboardCache::test_new_attempt_invalidates_cache -v` → 1/1 pass (si l'endpoint Attempt existe).

9. [x] **`pnpm add recharts` + lockfile** dans `frontend/package.json` + `frontend/pnpm-lock.yaml` :
   - Commande : `cd frontend && pnpm add recharts@^2.13.0` (pnpm 10.15, Node ≥ 20).
   - Vérifier le diff : `git diff frontend/package.json` montre `"recharts": "^2.13.0"` ajouté aux `dependencies`. **Ne pas** ajouter aux `devDependencies` (recharts est utilisé en runtime).
   - **Vérification** : `cd frontend && pnpm install --frozen-lockfile` ne casse pas ; `ls frontend/node_modules/recharts/package.json` existe.

10. [x] **Route group `(dashboard)/[locale]/` + auth guard** dans `frontend/app/(dashboard)/[locale]/layout.tsx` (nouveau fichier, ~50 lignes) :
    - Réplique la structure de `frontend/app/(public)/[locale]/layout.tsx` (`<NextIntlClientProvider>` + `<Header>` + `<main>`).
    - **Auth guard** : composant client interne `'use client'` qui :
      1. `useEffect(() => { useAuthStore.getState().hydrate() }, [])` au mount.
      2. Attend l'hydratation : si `!hydrated` (state du store), return un placeholder (`<div className="min-h-screen" />`, pas un spinner plein écran, design-system l.155).
      3. Si `hydrated && !isAuthenticated` → `router.replace('/login?next=' + encodeURIComponent(pathname))`.
      4. Si `hydrated && isAuthenticated` → render `{children}`.
    - **`useAuthStore`** : vérifier que `hydrate()` est idempotent et que `isAuthenticated` est `hydrated && accessToken !== null` (cf. recherche Fait 6).
    - **`<Header>` du layout dashboard** : variante simplifiée (logo + `<LanguageSwitcher>` + avatar), pas de liens desktop (gap design-system l.232, la nav post-JWT arrive en s17). L'avatar affiche `pseudo.charAt(0).toUpperCase()`.
    - **i18n** : ajouter `dashboard.layout.title` (« Mon tableau de bord » / « My dashboard ») dans `messages/fr.json` + `messages/en.json` namespace `dashboard`.
    - **Vérification** : `cd frontend && npx tsc --noEmit` ne montre pas de nouvelle erreur ; `cd frontend && npx next build` ne casse pas (mais on n'a pas encore la page `/dashboard/eleve`).

11. [x] **Page `/dashboard/eleve` + DashboardClient** dans `frontend/app/(dashboard)/[locale]/eleve/dashboard/page.tsx` (nouveau) + `frontend/app/(dashboard)/[locale]/eleve/dashboard/DashboardClient.tsx` (nouveau, ~200 lignes) :
    - **`page.tsx`** (server component, réplique du pattern `chat/page.tsx:34-42`) :
      - `export const dynamic = "force-dynamic"` (le dashboard n'a pas de cache statique).
      - Server-side : récupère l'access token via `cookies()` (helper next/headers), appelle `apiClient.get('/api/dashboard/eleve', { headers: { Authorization: `Bearer ${token}` } })`, gère les erreurs 401 (redirect `/login`), passe les données initiales à `<DashboardClient>`.
      - **Alternative** : laisser le client faire le fetch (le `apiClient` interceptor ajoute le Bearer automatiquement). **Recommandation** : server-side fetch initial pour le SSR-correctness, sinon le dashboard fait un aller-retour inutile (client → serveur → DB → client). **Décision à acter** : server-side fetch initial.
    - **`DashboardClient.tsx`** (`'use client'`) :
      - 4 états : loading (textuel + spinner), empty (CTA vers `/chat`), error (réseau / 401 / 403 / 500 avec bouton Réessayer), success (Summary + Chart + Subject cards + Refresh).
      - **Composants importés** : `<Card>` (existant), `<Button>` (existant), `<BarChart>` de Recharts (nouveau).
      - **Subject cards** : 1 row de 2 sur tablette+ (`grid grid-cols-1 md:grid-cols-2`), stack vertical sur mobile. Pour chaque matière : `SubjectCard` interne (nom + icône `book-open` Lucide + valeur % + badge coloré + méta).
      - **`<BarChart>` Recharts** : `data` = `[{name: "Maths", taux: 75}, {name: "Français", taux: 60}]` ; `<CartesianGrid>`, `<XAxis>`, `<YAxis domain={[0, 100]} tickFormatter={v => v + '%'}>`, `<Tooltip>`, `<Bar dataKey="taux" fill="var(--color-primary)" radius={[4, 4, 0, 0]}>`, **`<Legend verticalAlign="bottom" />`** (AC #3). `<ResponsiveContainer width="100%" height={240}>` (200 sur mobile via `useEffect` + state `isMobile`).
      - **`<table>` sr-only** inline (doublon accessible) : 1 table avec caption + 3 colonnes + 2 lignes, `className="sr-only"`. Cf. design § 4.2 (5).
      - **i18n** : `useTranslations('dashboard.eleve')` partout, 15+ clés (cf. design § 7). **Pas de string en dur**.
      - **Format de date** : `new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(last_activity_at))`. Pour « il y a 3 jours » : `Intl.RelativeTimeFormat(locale, { numeric: 'auto' })` (next-intl a un wrapper, sinon natif).
      - **Format de %** : `new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 0 }).format(score_avg)`.
      - **Bouton Rafraîchir** : state `isRefreshing`, icône `refresh-cw` → `loader-2` pendant le refresh, label `dashboard.eleve.refresh` → `dashboard.eleve.refreshing`. Appelle `apiClient.get('/api/dashboard/eleve', { headers: { 'Cache-Control': 'no-cache' } })` puis `invalidate_dashboard` côté frontend (re-set le state). Note : le `Cache-Control: no-cache` header ne traverse pas jusqu'au backend (l'API backend a son propre cache in-process) ; pour vraiment bypass le cache, on POST un endpoint `/api/dashboard/eleve/invalidate` (admin/eleve self) ou on accepte que le bouton respecte le TTL 5 min. **Décision à acter** : pas d'endpoint invalidate exposé, le bouton Refresh hit l'API qui hit le cache (TTL respecté) — c'est OK pour la POC. Le bouton sert surtout à refresh après une nouvelle tentative (5 min de latence max).
    - **Vérification** : `cd frontend && npx tsc --noEmit` 0 erreur ; `cd frontend && npx next build` build OK ; `pnpm exec playwright test e2e/dashboard.spec.ts` (cf. Tâche 12) 0 violation.

12. [x] **Tests e2e + axe-core + Lighthouse a11y** dans `frontend/e2e/dashboard.spec.ts` (nouveau fichier, ≥ 4 tests) + `frontend/lighthouserc.json` (modification) :
    - **`frontend/e2e/dashboard.spec.ts`** (Playwright + @axe-core/playwright) :
      - **Setup** : créer un user alice, login, seed 3 maths attempts + 2 francais attempts via `request.post('/api/attempts/...')` ou via le helper backend de seed. **Note** : si les endpoints Attempt ne sont pas accessibles en e2e (auth + tests), utiliser un seed direct via `psql` ou via un endpoint de test (`POST /api/test/seed-attempts` non-production). **Recommandation** : créer un fixture helper `seed_attempts_via_api(page, attempts_data)` qui hit les endpoints s04/s07 (ou qui hit directement la DB via un endpoint de test interne — à confirmer avec l'owner s04/s07).
      - **`TestDashboardPage`** :
        - `test_renders_summary_chart_and_subjects_for_logged_in_eleve` : login alice, navigate `/fr/dashboard/eleve`, assert Summary value = "69 %", chart visible, 2 Subject cards (Maths + Français).
        - `test_chart_legend_is_below_chart_at_360px` : set viewport 360×800, login alice, navigate, screenshot du chart, vérifier visuellement que la légende est sous le chart (pixel check via `page.locator('[data-testid="chart-legend"]').boundingBox().y > chart.boundingBox().y + chart.boundingBox().height - 50`).
        - `test_empty_state_when_eleve_has_no_attempts` : login bob (0 attempt), navigate, assert empty state card visible avec CTA « Aller au chat ».
        - `test_redirects_to_login_when_unauthenticated` : pas de login, navigate `/fr/dashboard/eleve`, assert URL = `/fr/login?next=%2Ffr%2Fdashboard%2Feleve`.
        - `test_axe_core_no_critical_or_serious_violations` : `@axe-core/playwright` scan, assert 0 violation `critical` + 0 violation `serious`.
    - **`frontend/lighthouserc.json`** : étendre le tableau `collect.url` avec `"http://localhost:3000/fr/dashboard/eleve"`. L'assertion `assertions` reste la même (categories:a11y ≥ 90).
    - **Vérification** : `pnpm exec playwright test e2e/dashboard.spec.ts --reporter=list` 5/5 pass ; `pnpm exec lhci collect` (Lighthouse CI) score a11y ≥ 90 sur `/fr/dashboard/eleve`.

13. [x] **Run full backend + frontend test suite + i18n check** :
    - `cd backend && pytest tests/ -v --tb=short` → 0 régression sur les tests s04, s07, s09, s10, s12, s13, s13b, s14, s15 existants.
    - `cd backend && ruff check app/ tests/` → 0 nouveau warning.
    - `cd backend && mypy app/` → 0 nouvelle erreur.
    - `cd frontend && npx tsc --noEmit` → 0 erreur TypeScript.
    - `cd frontend && bash scripts/check-i18n.sh` → exit 0 (aucune string en dur, les 15+ clés `dashboard.eleve` sont dans `fr.json` + `en.json`).
    - `cd frontend && pnpm exec playwright test e2e/ --reporter=list` → 0 régression sur les e2e s11b, s11c, s13, s15 existants + les 5 nouveaux dashboard.
    - **Vérification** : tous les jobs CI restent verts.

14. [x] **Conventional commit unique** : `feat(frontend+api): add eleve dashboard with progress metrics (s16)` couvrant tous les fichiers modifiés + créés + le research + le design + le plan.
    - **Vérification** : `git log -1` montre un seul commit avec tous les fichiers.

## Run interdicts

- **Pas de score numérique ajouté à `Attempt`** : le proxy `mean(is_success)` est la seule métrique. Tenter d'ajouter une colonne `score: float` nécessiterait une migration (cf. ADR 010, init_db()) et toucherait s04/s07/s08 — hors-scope s16.
- **Pas de Redis** : cache in-process, module-level dict + `threading.Lock`. Redis arrive quand l'app scale (s23+ ou une story ops).
- **Pas d'admin impersonation via body** : seul `?pseudo=...` query param permet l'admin bypass (via helper s15). Pas de `body.pseudo`.
- **Pas de notification toast** : confirmation succès / erreur reste inline (cf. design-system l.231, gap s25).
- **Pas de bottom tab bar mobile** : gap design-system l.232, la nav post-JWT arrive en s17 ou s22.
- **Pas de toggle dark/light UI** : le shell supporte `data-theme` mais le toggle arrive en s22. Le mockup respecte `prefers-color-scheme` (CSS `@media`).
- **Pas de filtre par matière côté frontend** : la story affiche toutes les matières en même temps (s22 si besoin).
- **Pas de line chart temporel** : gap design (s18 ou s22).
- **Pas de modification d'`Attempt`** : la Tâche 8 câblée sur l'endpoint HTTP `exercises` à venir. s04 et s07 ont livré les services (`qcm_grader`, `text_grader`) et le modèle `Attempt`, mais **pas de router REST** pour créer un `Attempt` via API. La Tâche 8 se réduit à la doc et un test « skipped » ; le câblage réel attendra la story qui livrera ce router (s16b, ou extension de s04/s07, ou une autre story à identifier).
- **Pas de nouveau shared component** : `<BarChart>` est utilisé directement depuis Recharts, pas wrapper dans `frontend/components/`. La `<table>` sr-only est inline dans la page, pas un shared `<Table>`. Factorisation à s22 si d'autres stories en ont besoin.
- **Pas de log du password, hash, token, jti, ou body** : le cache ne loggue rien (silence = succès). La garde cross-tenant log INFO `security.cross_tenant_attempt` (cf. s15, vérifié par le test `test_log_does_not_contain_token_material`).
- **Pas de refactor transverse des fixtures de test** : duplication assumée (cf. AGENTS.md + research trap 9). `rsa_keypair`, `_point_settings`, `db_engine`, `session_factory`, `client`, `seeded_*`, `_bearer` sont dupliqués depuis `test_users_create.py` / `test_documents.py`.
- **Pas de commit sur la branche par défaut** : tout part sur `feature/s16-dashboard-eleve` (worktree dédié). Le squash-merge vers `main` est manuel après review.

## The point everything turns on

**La décision centrale** : `score_avg` est un **proxy** (`mean(is_success)`), pas un score numérique. C'est ce qui rend l'AC #1 (story) implémentable **sans** modifier le modèle `Attempt` (et donc sans migration, sans casser s04 / s07 / s08). Le label UI « Taux de réussite » est ce qui rend le proxy honnête vis-à-vis de l'élève.

Trois pièges à surveiller :

1. **Le `AVG(CAST(is_success AS FLOAT))` SQL** : SQLite (test) et PostgreSQL (prod) ont des sémantiques différentes pour `AVG` sur un entier — SQLite peut retourner 0 ou 1 en division entière. Le `CAST(... AS FLOAT)` est **obligatoire** pour les deux. Test unitaire `test_groups_by_subject` (Tâche 5) couvre le cas `2/3 ≈ 0.667`. Le reviewer vérifiera `grep -n "AVG" backend/app/services/dashboard/aggregator.py` et la query SQL exacte.

2. **Cache key collision admin vs eleve** : un admin qui hit `?pseudo=alice` cache pour `alice`, pas pour l'admin (cf. Tâche 4). Si un eleve alice hit `/api/dashboard/eleve` (pas de `?pseudo=`), le cache key est `dashboard:eleve:alice` — même clé. C'est **intentionnel** (on veut partager le cache entre l'eleve et l'admin qui debug). Test `test_different_pseudos_have_separate_keys` (Tâche 6) + test admin dans `TestGetEleveDashboardCrossTenant` (Tâche 7) couvrent.

3. **Tâche 8 (cache invalidation on new Attempt) peut être bloquante** si aucun router HTTP `exercises` n'existe encore. État vérifié au moment de l'exécution de s16 : s04 et s07 sont **shippés** (graders + modèle `Attempt`), mais **aucun router REST** ne crée d'`Attempt` via API. Le plan **détecte** en Tâche 8 (« STOP et reporter »), ne crée **pas** le router dans cette story (hors-scope, owner = story future). Le câblage `invalidate_dashboard` attendra cette story. **Recommandation** : ne pas blocker s16, accepter le TTL 5 min pour la POC ; créer s16b (ou équivalent) quand le router `exercises` sera livré pour câbler l'invalidation.

Vérification finale par le reviewer : (a) `grep -rn "score_avg" backend/app/` montre la query SQL et le schema Pydantic uniquement ; (b) `grep -rn "Taux de réussite" frontend/messages/` montre la chaîne i18n ; (c) `grep -n "is_success" backend/app/services/dashboard/aggregator.py` montre l'usage dans `AVG(CAST(...))` ; (d) `cd frontend && pnpm exec playwright test e2e/dashboard.spec.ts` 5/5 pass.

## Files touched

**Créés** :
- `backend/app/api/dashboard/__init__.py` (vide, ~1 ligne)
- `backend/app/api/dashboard/eleve.py` (~80 lignes, router)
- `backend/app/api/dashboard/schemas.py` (~50 lignes, Pydantic)
- `backend/app/services/dashboard/__init__.py` (vide, ~1 ligne)
- `backend/app/services/dashboard/aggregator.py` (~80 lignes, query SQL)
- `backend/app/services/dashboard/cache.py` (~40 lignes, TTL dict)
- `backend/tests/api/dashboard/__init__.py` (vide)
- `backend/tests/api/dashboard/test_eleve.py` (~200 lignes, ≥ 6 tests)
- `backend/tests/services/__init__.py` (vide, si manquant)
- `backend/tests/services/dashboard/__init__.py` (vide)
- `backend/tests/services/dashboard/test_aggregator.py` (~150 lignes, 5 tests)
- `backend/tests/services/dashboard/test_cache.py` (~100 lignes, 4 tests)
- `frontend/app/(dashboard)/[locale]/layout.tsx` (~50 lignes, auth guard)
- `frontend/app/(dashboard)/[locale]/eleve/dashboard/page.tsx` (~30 lignes, server entry)
- `frontend/app/(dashboard)/[locale]/eleve/dashboard/DashboardClient.tsx` (~200 lignes, 4 états + chart + subject cards)
- `frontend/e2e/dashboard.spec.ts` (~150 lignes, 5 tests)
- `docs/research/s16-dashboard-eleve.md` (déjà créé)
- `docs/designs/s16-dashboard-eleve.md` (déjà créé)
- `docs/designs/s16-dashboard-eleve.html` (déjà créé)
- `docs/plans/s16-dashboard-eleve.md` (ce fichier)

**Modifiés** :
- `backend/app/main.py` (~5 lignes : import + `include_router` pour `dashboard_eleve_router`)
- `backend/app/api/exercises/router.py` (~5 lignes : `invalidate_dashboard` après `session.add(Attempt)` — **conditionnel**, voir Tâche 8)
- `frontend/package.json` (+1 ligne : `"recharts": "^2.13.0"` aux `dependencies`)
- `frontend/pnpm-lock.yaml` (régénéré par `pnpm add`)
- `frontend/messages/fr.json` (+15 clés namespace `dashboard.eleve` + `dashboard.layout.title`)
- `frontend/messages/en.json` (idem)
- `frontend/lighthouserc.json` (+1 entrée dans `collect.url` : `/fr/dashboard/eleve`)

**Non touchés (volontairement)** :
- `backend/app/core/database/models.py` — `Attempt` reste avec `is_success: bool` (pas de colonne `score: float`)
- `backend/app/api/chat/router.py` — inchangé (s15 a déjà câblé JWT)
- `backend/app/api/documents/router.py` — inchangé (s15 a déjà câblé JWT)
- `backend/app/api/auth/*` — inchangé (s12/s13 inchangés)
- `frontend/components/*` — aucun nouveau shared component (Recharts utilisé directement)
- `frontend/lib/stores/*` — `useAuthStore` est utilisé tel quel (s13 inchangé), pas de nouveau store
- `frontend/lib/api.ts` — l'interceptor JWT (s13) suffit, pas d'extension
- `docs/architecture.md` — pas de nouvelle section (la doc est correcte)
- `docs/design-system.md` — pas d'extension (les gaps sont notés dans `docs/designs/s16-dashboard-eleve.md § 9`)
