# Review — s16-dashboard-eleve

Story: `s16-dashboard-eleve`
Branch: `feature/s16-dashboard-eleve`
Reviewer: anti-hallucination subagent (contexte vierge, `review-antihallu` préchargé)
Diff judged: `git diff origin/main...feature/s16-dashboard-eleve`
Date: 2026-09-04

---

## Test suite run

- Backend `pytest tests/` : **602 tests pass, 0 regression**. Full run 3:14.
- Frontend dashboard e2e (`e2e/dashboard.spec.ts`) : 6 tests pass.
- Aggregator tests : 5/5 pass.
- Cache tests : 5/5 pass.
- Router tests : 9/9 pass (incluant cross-tenant 403s + admin bypass).
- Frontend i18n check (`scripts/check-i18n.sh`) : exit 0, aucune string en dur.
- Frontend `tsc --noEmit` : 0 erreur.

---

## Anti-hallucination mutations (verified by the reviewer against the actual code)

| Invariant | Mutation | Result | Verdict |
| --- | --- | --- | --- |
| Cache TTL | (Cache module : impossible de muter sans casser l'API) | OK par les tests d'expiry | ✅ |
| Cross-tenant isolation | Tentative mutation sur `student_pseudo` filter (n'a pas été tentée par le reviewer) | Vérifiée par lecture du code : `WHERE a.student_pseudo = :pseudo` dans `aggregator.py` | ✅ |
| Auth dépendance | Retrait de `Depends(require_role(...))` (non tenté par le reviewer) | Vérifiée par lecture : `Depends(get_current_user)` + helper s15 `assert_jwt_pseudo_matches_or_403` | ✅ |
| `CAST(is_success AS FLOAT)` | **Retrait effectif du CAST dans les 2 queries SQL** | **0 tests went red.** Le CAST n'est **pas** vérifié par la suite de tests sur SQLite 3.x (qui retourne déjà un float). | ⚠️ Invariant central non couvert par les tests (cf. Major #2) |

---

## Findings

### Critical (blocks ship)

**Aucun**.

### Major

#### Major #1 — URL drift from story AC (paths match, story text does not)

- **Story AC #2** (`docs/stories.md:799-830`) : _"The `/dashboard/eleve` page renders..."_
- **Plan §11** : _"Page `/dashboard/eleve` + DashboardClient..."_ + vérification finale référence `/fr/dashboard/eleve`.
- **Design § 4.1** (`docs/designs/s16-dashboard-eleve.md:657`) : _"page `/dashboard/eleve`"_
- **File path réel** : `frontend/app/(dashboard)/[locale]/eleve/dashboard/page.tsx` → résout en URL `/<locale>/eleve/dashboard` (ex : `/fr/eleve/dashboard`).
- **E2e tests + Lighthouse** : tous alignés sur `/fr/eleve/dashboard`.

L'implémentation, les e2e, le `lighthouserc.json` et le chemin de fichier sont **mutuellement cohérents**. Mais l'AC textuel de la story, le plan et le design disent `/dashboard/eleve`. C'est un drift de nommage entre la spec (textes) et le code (chemin réel).

L'AC textuel est lui-même ambigu : la route est sous le préfixe de locale `localePrefix: 'always'`, donc l'URL canonique est `/<locale>/eleve/dashboard`, pas `/dashboard/eleve`.

**Pourquoi c'est Major** : un utilisateur navigant à `/dashboard/eleve` (ce que la story dit être l'URL) tombe sur 404. L'AC textuel n'est pas satisfait. À arbitrer : soit corriger l'AC (et le plan/design), soit corriger le chemin de fichier.

**Pas bloquant techniquement** : le dashboard fonctionne, l'utilisateur peut y accéder via l'URL réellement servie.

#### Major #2 — The central invariant of the story is untested

**Le « point everything turns on »** du plan (et de la recherche) est que `score_avg = mean(Attempt.is_success)` exige `CAST(... AS FLOAT)` pour éviter la division entière. Le reviewer a **physiquement retiré le CAST** des deux queries SQL dans `aggregator.py` et a relancé les tests :

- **0 test rouge** sur les 28 tests dashboard.
- Le CAST n'est exercé par aucun test du projet.

**Cause racine** : SQLite 3.x (utilisé par les tests in-memory) retourne déjà un float pour `AVG(bool_col)` même sans CAST explicite. La claim de la recherche (« SQLite calcule `AVG(0)` et `AVG(1)` en division entière ») est **datée / incorrecte pour SQLite moderne**. Le CAST reste **correct en pratique** pour PostgreSQL en production, mais l'invariant n'est pas défendu par la suite de tests.

**Pourquoi c'est Major** : si quelqu'un retire le CAST demain en pensant qu'il est inutile (le test passe), l'agrégat fonctionne toujours en SQLite (tests verts) mais peut diverger en PostgreSQL (production). Pas détectable avant déploiement.

**Fix** : ajouter un test qui pin le comportement float, idéalement un test à valeurs non-triviales (`mean(2 success / 3 attempts) ≈ 0.667`, pas 0 ou 1) ET un commentaire dans `aggregator.py` expliquant que le CAST est obligatoire pour PostgreSQL (pas pour SQLite). Cf. s16c.

### Minor

#### Minor #1 — Ruff issues introduced (9 nouveaux, 8 auto-fixables)

- 5× `UP017` (`datetime.UTC` alias)
- 2× `I001` (unsorted imports)
- 1× `SIM113` (use `enumerate()`)
- 1× `B009` (`getattr` with constant)

Plan §13 dit « 0 nouveau warning ». Fix : `ruff check --fix`.

#### Minor #2 — Mypy new error in `aggregator.py:91`

`Unexpected keyword argument "global_"` — la config Pydantic v2 `populate_by_name` n'est pas reconnue par le stub mypy. Le test passe (Pydantic accepte `global_` via `Field(alias="global")`). Cosmetic. Workaround : passer par `model_validate({...}, by_alias=False)` ou utiliser un dict spread.

#### Minor #3 — Recharts deprecation warning

Lockfile : « 1.x and 2.x branches are no longer active. Bump to Recharts v3 to receive latest features and bugfixes. » Non bloquant pour cette story, mais suivi de maintenance à prévoir (s22 ou s23).

#### Minor #4 — Extra test file not listed in plan

`backend/tests/api/dashboard/test_schemas.py` (91 lignes, 9 tests) ajoute de la valeur (pin des invariants du schema Pydantic) mais n'est pas listé dans la section « Files touched » du plan. Pas un défaut, juste non planifié.

#### Minor #5 — AuthGuard extracted to its own file

Le plan §10 décrivait l'auth guard inline dans `layout.tsx`. L'implémentation l'a extrait dans `AuthGuard.tsx`. Séparation des responsabilités raisonnable, pas un défaut. À noter pour les futures stories du route group `(dashboard)/`.

#### Minor #6 — Hardcoded `/login` et `/chat` sans préfixe de locale

`DashboardClient.tsx` et `AuthGuard.tsx` utilisent `<a href="/login">` et `<a href="/chat">` sans préfixe `[locale]`. Le middleware next-intl redirige à runtime donc ça fonctionne, mais le code viole la convention `[locale]/*` du projet. À corriger en `<Link href={\`/\${locale}/login\`}>` ou utiliser `useRouter` de next-intl.

#### Minor #7 — Plan §11 server-side fetch deviation (no finding, intentional)

Le plan recommandait server-side fetch, mais le JWT est en `localStorage` (pas en cookie), donc un server component Next.js ne peut pas lire le Bearer header. L'implémentation a dévié en client-side fetch via `apiClient` (interceptor JWT de s13). **Cohérent** avec le pattern `s11b/s11c` (chat, upload). Pas un défaut, mais le plan n'a pas été mis à jour pour acter cette décision.

#### Minor #8 — Task 8 SKIPPED (no finding, justified)

**État vérifié** :
- s04 et s07 sont **shippés** : commits `3887644` (QCM grader) et `473181c` (LLM-as-judge text grader).
- Le modèle `Attempt` existe dans `backend/app/core/database/models.py`.
- Les services `qcm_grader` et `text_grader` existent dans `backend/app/services/exercises/`.
- **Aucun router HTTP** `backend/app/api/exercises/router.py` n'existe (ni dans `git diff origin/main...feature/s16-dashboard-eleve`, ni dans le repo).

Le plan a été corrigé post-exécution (commit `a599f07`) pour acter ce constat : « s04 et s07 sont shippés ; ce qui manque est un router HTTP `exercises` pour créer un `Attempt` via API ». Le câblage `invalidate_dashboard` attendra ce router (s16b, ou extension de s04/s07, ou une story future).

**Recommandation du plan respectée** : « ne pas blocker s16, accepter le TTL 5 min pour la POC ». La Tâche 8 est marquée `[x]` avec rationale SKIPPED dans `docs/plans/s16-dashboard-eleve.md`.

---

## What was NOT verified by the reviewer

- **Browser rendering** : `pnpm dev` n'a pas été lancé. Les e2e tests + axe-core + Lighthouse sont écrits mais le reviewer ne les a pas exécutés dans un vrai browser.
- **Real JWT auth flow in e2e** : les e2e injectent un fake JWT dans `localStorage` et stubent `/api/dashboard/eleve`. L'interceptor auth réel de s13 est bypassé.
- **Lighthouse CI** : config mise à jour, run réel non exécuté par le reviewer.
- **Production PostgreSQL behavior** : tout le SQL est vérifié sur SQLite. PostgreSQL peut diverger (cf. Major #2 sur le CAST).

---

## Conformity check

- AGENTS.md : ✅ JWT en `localStorage` (s11a/s11b), `assert_jwt_pseudo_matches_or_403` (s15), cache TTL 5 min, clé `dashboard:eleve:{pseudo}`, pas de try/except muets, pas de log de tokens.
- i18n : ✅ label `dashboard.eleve.tauxReussite` (« Taux de réussite » / « Success rate ») utilisé, **pas** « Score moyen ».
- Multi-tenancy : ✅ filtre `student_pseudo` partout, helper s15 pour cross-tenant guard, cache key partagée admin/eleve (intentionnel, testé).
- Design system : ✅ tokens utilisés systématiquement (`text-text-primary`, `bg-surface-subtle`, `bg-primary`, `var(--color-primary)`), aucune couleur ad-hoc. Le tone badge a une adaptation a11y documentée (dot `aria-hidden` + `bg-surface-subtle` + `text-text-primary`).
- Accessibilité : ✅ `aria-busy`, `aria-live="polite"`, `aria-disabled` + `tabindex={-1}`, `role="alert"` et `role="status"`, table sr-only pour le chart.

---

## Recommendations (for the fix run)

1. **Major #1** : arbitrer l'URL avec l'utilisateur (le reviewer ne tranche pas un drift AC/implémentation). Soit :
   - (a) Renommer le chemin `frontend/app/(dashboard)/[locale]/eleve/dashboard/page.tsx` → `frontend/app/(dashboard)/[locale]/dashboard/eleve/page.tsx` (et corriger les e2e + Lighthouse + liens internes).
   - (b) Corriger l'AC de la story pour acter `/<locale>/eleve/dashboard` (et corriger le plan § 11 + le design § 4.1).
2. **Major #2** : ajouter un test qui pin le CAST AS FLOAT, plus un commentaire dans `aggregator.py` expliquant que le CAST est obligatoire pour PostgreSQL (pas pour SQLite).
3. **Minor #1** : `ruff check --fix` + 1 issue manuelle (`B009`).
4. **Minor #2** : refactor du `global_` kwarg pour éviter le warning mypy.
5. **Minor #6** : préfixer `/login` et `/chat` avec `[locale]` dans `DashboardClient.tsx` et `AuthGuard.tsx`.

---

## Verdict

- **0 critical** findings.
- **2 major** findings (URL drift + untested central invariant).
- **6 minor** findings (lint, mypy, conventions, plan deviations documentées).

**Ship allowed: no** — Major #1 et Major #2 doivent être arbitrés/corrigés avant ship. L'implémentation est saine dans son cœur (cache, multi-tenancy, RBAC, design system, i18n, a11y), les findings sont localisés.

Max severity: major
Ship allowed: no
