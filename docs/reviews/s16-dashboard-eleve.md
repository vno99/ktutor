# Review — s16-dashboard-eleve

Story: `s16-dashboard-eleve`
Branch: `feature/s16-dashboard-eleve`
Reviewer: anti-hallucination subagent (contexte vierge, `review-antihallu` préchargé)
Date: 2026-09-04

---

## Review history

- **Pass 1** (commit `3e318a6`) : `Max severity: major` / `Ship allowed: no`. 2 Major findings (URL drift + untested central invariant), 6 Minor (ruff, mypy, conventions, plan deviations).
- **Fix run** (commit `9891b93`) : URL renommée + test de garde CAST AS FLOAT + ruff + mypy + locale-prefixed links.
- **Pass 2** (this report) : `Max severity: none` / `Ship allowed: yes`. Tous les findings corrigés, aucune régression.

---

## Test suite run (independent, pass 2)

- Backend `pytest tests/` : **603 tests pass, 0 regression** (was 602, +1 pour le CAST guard).
- Frontend `pnpm exec playwright test` : **35 e2e tests pass** (6 dashboard + 29 existants).
- `mypy app/services/dashboard/ app/api/dashboard/` : dashboard module clean (2 erreurs préexistantes dans `app/core/auth/middleware.py` non liées). Project-wide : 24 erreurs (identique à pre-fix, 0 nouvelle).
- `ruff check app/ tests/` : **0 issues** (was 9 pre-fix).
- `npx tsc --noEmit` : clean.
- `bash scripts/check-i18n.sh` : exit 0.

---

## Verification of the fix run (pass 2)

### Major #1 — URL renommée à `/<locale>/dashboard/eleve`

- `git show --name-status 9891b93` confirme R099/R100 renames depuis `frontend/app/(dashboard)/[locale]/eleve/dashboard/{page,DashboardClient}.tsx` vers `frontend/app/(dashboard)/[locale]/dashboard/eleve/{page,DashboardClient}.tsx`.
- File system check : ancien chemin n'existe plus ; nouveau chemin contient les deux fichiers.
- `frontend/e2e/dashboard.spec.ts` (l. 84, 109, 129, 141, 149, 167) : les 6 tests naviguent vers `/fr/dashboard/eleve` (ou `/en/dashboard/eleve`). Test (d) assert le regex de redirect `/\/fr\/login\?next=%2Ffr%2Fdashboard%2Feleve$/`.
- `frontend/lighthouserc.json` (l. 11-12) : `/fr/dashboard/eleve` et `/en/dashboard/eleve` présents.
- Les 6 tests e2e passent, y compris le test de redirect. **AC #2 de la story satisfaite** (servie à `/<locale>/dashboard/eleve`, locale-prefixed par convention projet).

**Verdict : Major #1 corrigé.**

### Major #2 — CAST AS FLOAT regression-guard test

- `backend/tests/services/dashboard/test_aggregator.py::test_aggregator_compiles_cast_is_success_as_float` (l. 305-372).
- Le test hooke `sqlalchemy.event.listen(db_engine, "before_cursor_execute", _record)` pour capturer le SQL rendu, appelle `aggregate_eleve_dashboard(s, "alice")`, et assert `"CAST(attempts.is_success AS FLOAT)" in per_subject_sql` AND `"CAST(attempts.is_success AS FLOAT)" in global_sql`.
- **Test de neutralisation (vérifié)** : le reviewer a **physiquement retiré** le CAST des deux `func.avg(cast(...))` dans `aggregator.py`, restauré le fichier, lancé `pytest tests/services/dashboard/test_aggregator.py -v` :
  - Avec CAST (production) : 6/6 pass.
  - Sans CAST (muté) : 5/6 pass, **1 rouge** (le nouveau test), les 5 autres passent (confirmant le masquage SQLite diagnostiqué en pass 1).
  - `git diff --exit-code backend/app/services/dashboard/aggregator.py` après restore : clean.
- Le bloc de documentation `CRITICAL` dans `aggregator.py` (l. 36-47) explique le piège SQLite vs PostgreSQL, pointe vers le nouveau test comme garde, et référence la review. Un futur implémenteur qui retire le CAST verra pourquoi et sera tourné rouge par le test.

**Verdict : Major #2 corrigé, le test mord réellement.**

### Minor #1 — Ruff clean

- `ruff check app/ tests/` : **0 issues** (was 9). Les 8 auto-fixables résolus, le B009 dans `test_schemas.py` remplacé par accès direct à l'attribut, le SIM113 dans `test_eleve.py` remplacé par `enumerate`.

**Verdict : Minor #1 corrigé.**

### Minor #2 — Mypy clean sur dashboard module

- `mypy app/services/dashboard/ app/api/dashboard/` : 2 erreurs restantes dans `app/core/auth/middleware.py` (l. 87, 111), préexistantes et non liées. L'erreur `aggregator.py:91` (Unexpected keyword argument "global_") est **partie** — le fix utilise `model_validate({"subjects": ..., "global": ...})` qui exerce l'alias proprement. Le `populate_by_name=True` dans `schemas.py:75` le permet.

**Verdict : Minor #2 corrigé (dashboard module).**

### Minor #6 — Locale-prefixed links

- `frontend/app/(dashboard)/[locale]/AuthGuard.tsx` (l. 3, 30, 46, 47) : import `useLocale`, appel `useLocale()`, construction du redirect `\`/${locale}/login?next=${next}\``.
- `frontend/app/(dashboard)/[locale]/dashboard/eleve/DashboardClient.tsx` (l. 281, 335 reconnect, 360, 367 CTA) : `ErrorState` et `EmptyState` utilisent `useLocale()` et construisent `\`/${locale}/login\`` et `\`/${locale}/chat\``.
- Le test e2e (d) confirme que le redirect finit par `?next=%2Ffr%2Fdashboard%2Feleve` (le nouveau path), passant en browser réel.

**Verdict : Minor #6 corrigé.**

---

## Anti-hallucination mutations (re-run on the fix commit)

| Invariant | Mutation | Résultat | Verdict |
| --- | --- | --- | --- |
| `CAST(is_success AS FLOAT)` | Retrait physique du CAST des deux `func.avg(cast(...))` dans `aggregator.py` | **1 test rouge** (le nouveau `test_aggregator_compiles_cast_is_success_as_float`) ; 5/6 autres tests aggregator passent (confirmant le masquage SQLite) | **Mord confirmé** |
| URL servie à `/<locale>/dashboard/eleve` | (non re-muté ; le rename était le fix lui-même) | Tests e2e (a)-(f) naviguent vers la nouvelle URL et passent ; le regex de redirect en (d) matche | **Corrigé** |
| AuthGuard locale redirect | (non re-muté ; le fix a ajouté `useLocale`) | E2e (d) passe ; `useLocale()` câblé | **Corrigé** |

---

## Findings (pass 2)

### Critical (blocks ship)

**Aucun.**

### Major

**Aucun.**

### Minor

**Aucun nouveau.** Les 6 Minor listés en pass 1 sont soit corrigés (1, 2, 6), soit acceptés comme no-finding (3, 4, 5, 7, 8).

### Re-check des Minor acceptés (no regression)

- Minor #3 (Recharts deprecation) — toujours présent dans pnpm-lock, inchangé. Accepté.
- Minor #4 (test_schemas.py unplanned) — toujours présent et passant. Accepté.
- Minor #5 (AuthGuard extracted) — toujours extrait, utilise maintenant `useLocale()`. Accepté.
- Minor #7 (plan §11 server-side fetch deviation) — page.tsx utilise toujours client-side fetch. Accepté.
- Minor #8 (Task 8 SKIPPED, no exercises HTTP router) — pas de `backend/app/api/exercises/router.py` créé. Plan § 8 corrigé pour marquer SKIPPED. Accepté.

### Cross-tenant / RBAC / cache — regression check (full branch diff)

- `backend/app/api/dashboard/eleve.py:80` — `assert_jwt_pseudo_matches_or_403` (s15 helper) toujours appelé.
- `backend/app/services/dashboard/aggregator.py:58, 84` — `Attempt.student_pseudo == pseudo` filter toujours présent dans les deux queries.
- `backend/app/services/dashboard/cache.py` — clé = `dashboard:eleve:{pseudo}` ; lock-protected ; TTL via `time.monotonic`. Inchangé par le fix.
- `backend/app/main.py:78` — `app.include_router(dashboard_eleve_router)` toujours enregistré.
- 9 router tests passent (3 cross-tenant 403 + admin bypass + happy + empty + cache hit + cache invalidate + 2 auth 401).
- **Aucun drift sur l'architecture core.**

---

## What was NOT verified by the reviewer

- **Browser rendering** de l'URL live `/<locale>/dashboard/eleve` : les tests e2e + axe-core exercent l'URL en headless Chromium (35/35 pass, 2 scans axe-core sur /fr et /en), mais le reviewer n'a pas ouvert manuellement la page dans un vrai browser. Un smoke test humain est recommandé avant ship pour confirmer que le layout visuel matche `docs/designs/s16-dashboard-eleve.html`.
- **Lighthouse CI real run** : la config est à jour et bien formée, mais un vrai `lhci autorun` n'a pas été exécuté par le reviewer. L'assertion a11y ≥ 90 est posée mais non vérifiée à runtime.
- **Production PostgreSQL behavior** : SQLite dans le test backend n'exerce pas la divergence float-vs-integer division que le nouveau test CAST défend. Le nouveau test pin l'émission SQL quel que soit le backend, donc l'invariant est défendu. Mais un vrai run d'intégration PostgreSQL est best-effort (per AGENTS.md).
- **Real JWT auth flow in e2e** : les e2e injectent un fake JWT dans `localStorage` et stubent l'API. Le chemin interceptor complet (refresh on 401, etc.) n'est pas exercé end-to-end. Même caveat que les reviews précédentes.

---

## Conformity check (re-validé après fix)

- **AGENTS.md** : ✅ JWT en `localStorage`, `assert_jwt_pseudo_matches_or_403` (s15), cache TTL 5 min, cache key par pseudo, pas de try/except muets, pas de log de tokens.
- **i18n** : ✅ label `dashboard.eleve.tauxReussite` (« Taux de réussite »), aucune string en dur (check-i18n.sh exit 0).
- **Multi-tenancy** : ✅ `student_pseudo` filter sur les deux queries, helper s15, cache key par pseudo, tests cross-tenant passent.
- **Design system** : ✅ tokens utilisés systématiquement, aucune couleur ad-hoc.
- **Accessibilité** : ✅ scans axe-core passent sur /fr et /en (tests e et f), `aria-live`, `aria-disabled`, `role="alert"`, focus visible.

---

## Verdict

- **0 critical** findings.
- **0 major** findings.
- **0 new minor** findings.

Le fix run a correctement adressé les 2 Major (URL renommée pour matcher l'AC, CAST AS FLOAT pinné par un test qui mord réellement) et les 3 Minor claimés (1 : ruff clean, 2 : dashboard mypy clean, 6 : locale-prefixed links). Les 35 tests e2e, 603 tests backend, ruff, mypy, tsc et i18n checks passent tous sans régression.

Max severity: none
Ship allowed: yes
