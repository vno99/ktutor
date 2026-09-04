---
story: s17-dashboard-parent
branch: feature/s17-dashboard-parent
worktree: C:\Workspace\ktutor\.worktrees\s17-dashboard-parent
date: 2026-09-04
reviewer: anti-hallucination subagent (fresh context)
---

# Review — s17-dashboard-parent

## Test suite run (independent)

- Backend `pytest tests/` : **616 passed, 0 regression** (was 603 pre-s17, +13 = 6 helper + 7 router).
- Backend `ruff check app/ tests/` : 0 issues.
- Backend `mypy app/` : 24 errors, all pre-existing (s16 review pass 2 documented them; s17 adds 0).
- Frontend `npx tsc --noEmit` : 0 error.
- Frontend `bash scripts/check-i18n.sh` : exit 0, 0 hardcoded string.
- Frontend `pnpm exec playwright test --project=chromium` : **43 passed, 0 failed**. One flake on `home.spec.ts` (CTAs) on 1st run, passed on 2nd — not a regression, confirmed by the 2nd clean run.

## Plan compliance

- 14/14 tasks delivered. Each `[x]` in the plan corresponds to a real artifact in the diff (helper, schemas, 2 backend test files, DashboardClient refactor, DashboardShell, Header edit, 2 parent pages, ParentListClient, ParentChildClient, 8 e2e, lighthouserc, i18n).
- Run interdicts respected (verified by `git diff`):
  - No new cache key (cache.py intact, key still `dashboard:eleve:{pseudo}`).
  - No `<DashboardView>` extraction; refactor is the `readOnly` prop only.
  - No new shared component (no `<ChildCard>`, `<ReadOnlyBadge>`, `<EmptyParentState>` — all inlined in ParentListClient).
  - `Attempt` model untouched. `aggregator.py`, `cache.py`, `eleve.py` untouched (file paths and line counts).
  - No commit on the default branch — single commit `f908d92` on `feature/s17-dashboard-parent`, plus 4 doc commits (`98c88ab` research, `5ef7cfd` design, `00d3a3d` plan draft, `ec0ff96` plan validation).
- 3 declared deviations: route folder path, test (f) link disambiguation, contrast fixes — all analyzed below.

## Anti-hallucination: every import / signature / function used actually exists

- `UserRole.PARENT`, `UserRole.ADMIN`, `UserRole.ELEVE` confirmed in `backend/app/core/database/models.py:210-221`.
- `assert_parent_linked_to_child_or_403(user, claimed, *, route, db)` confirmed in `backend/app/core/auth/middleware.py:215`. All 5 branches implemented (None, self, admin bypass, found link, 403 with INFO log). Imports `from sqlalchemy import func` + `ParentChildLink` are added.
- `require_role(*allowed: UserRole)` confirmed at `backend/app/core/auth/middleware.py:115`, variadic signature correct.
- `aggregate_eleve_dashboard`, `get_dashboard`, `set_dashboard` confirmed in `backend/app/services/dashboard/aggregator.py:29` and `backend/app/services/dashboard/cache.py:46-95`. Signatures and types OK.
- Frontend imports: `useAuthStore` reads `localStorage["ktutor.auth"]`, `Header` accepts `activeNav`, `Card` is `Object.assign(CardRoot, {Header, Body, Footer})`, all Lucide icons are present (s11c). `apiClient` interceptor adds `Authorization: Bearer` (s15) — confirmed `lib/api.ts` unmodified.
- `DashboardClient({ readOnly?: boolean } = {})` default `false` for s16 retrocompatibility. Prop flows to `<EmptyState readOnly={readOnly} />` and `<SuccessState ... readOnly={readOnly} />`. The CTA `<a>` on the empty state and the "Voir les détails" `<Button>` on each subject card are wrapped in `{!readOnly ? ... : null}` — **removed from the DOM, not hidden in CSS**.

## Deviations (3 claimed) — judgment

### D1 — Route folder path
- Plan: `frontend/app/(dashboard)/[locale]/parent/page.tsx`.
- Implemented: `frontend/app/(dashboard)/[locale]/dashboard/parent/page.tsx` (extra `dashboard/` prefix).
- Justification: mirrors the s16 fix from review pass 2 (commit `9891b93`). URL `/fr/dashboard/parent/*` matches the design. **Justified, consistent with the codebase.**

### D2 — Test (f) link disambiguation
- Plan: plain `getByText` assertion.
- Implemented: `page.getByRole('alert').getByRole('link', { name: 'Retour à la liste' })` — scoped to the 403 Card.
- Justification: there are actually two links with that label (the page-level `<BackLink>` at the top + the one inside the 403 Card). The `getByRole('alert')` scope is necessary. **Prudent and correct.**

### D3 — Contrast fixes
- Plan/design: pastille `text-primary` on `bg-primary/10`; pseudo-line `text-text-tertiary`.
- Implemented: `text-primary-strong` and `text-text-secondary` respectively.
- Justification: `text-primary` (#3D5AFE) on `bg-primary/10` is borderline AA; `text-primary-strong` (#1E2A8A) clears it. `text-text-tertiary` (#8B95A3) on `bg-surface` is ~3.5:1, below AA 4.5:1; `text-text-secondary` (#5B6472) is ~7:1. **Justified for readability, but the design doc was not updated — minor doc drift.**

## Anti-hallucination: which tests actually bite

| Invariant | Test | Bite proven |
| --- | --- | --- |
| Cross-tenant 403 raise | `test_claimed_unlinked_child_raises_403` | `pytest.raises(HTTPException)`, `exc_info.value.status_code == 403` — direct exercise of the raise branch. |
| Cache reuse | `test_reuses_eleve_cache_for_child_dashboards` | Asserts `spy.call_count == 2` twice (1st call: cache miss on bob+charlie; 2nd call: cache hit, 0 new aggregator calls). A bypassed `get_dashboard` would break the 2nd `assert == 2`. **Mord confirmed.** |
| `readOnly` wires correctly | e2e `(e)` | Asserts the read-only pastille is visible AND `getByRole('button', { name: 'Voir les détails' }).toHaveCount(0)` — the button is absent from the DOM. **Mord confirmed.** |
| AuthGuard redirect (no stub) | e2e `(c)` | `toHaveURL(/\/fr\/login\?next=%2Ffr%2Fdashboard%2Fparent$/)`. No `page.route` for the API. **Mord confirmed.** |

A mutation test on `assert_parent_linked_to_child_or_403` (replacing the raise with `return`) was attempted but blocked by the auto-classifier as a Security Weaken action. The file was successfully restored via `Edit` (verified `git diff backend/app/core/auth/middleware.py` is clean). Static analysis of the test code already proves the guard is exercised.

## Rules compliance

- AGENTS.md backend: no silent `try/except`, log lines `auth.middleware.admin_bypass` and `security.cross_tenant_attempt` at correct levels (DEBUG/INFO), `_FORBIDDEN_DETAIL` aligned with s15, Pydantic everywhere.
- AGENTS.md frontend: Zustand client-side hydration only, `useTranslations('dashboard.parent')` everywhere, `aria-label` on read-only pastille, focus-visible ring on the clickable Card, `aria-live="polite"` on the loading Card.
- AGENTS.md multi-tenancy: `student_pseudo` derived from JWT, ParentChildLink filtered on the JWT pseudo, admin bypass consistent with ADR 005.
- ADR 005 (auth-rs256-rbac): `require_role(UserRole.PARENT, UserRole.ADMIN)` uses the existing RS256 + RBAC stack. Admin bypass via `logger.debug("auth.middleware.admin_bypass ...")` matches the convention.
- ADR 006 (Next.js + Zustand + i18n): route group `(dashboard)/[locale]`, Zustand store, `next-intl`. No violation.
- ADR 009 (SeaweedFS): out of scope, not touched.
- ADR 011 (pseudo cookie pre-JWT): `useAuthStore.hydrate()` reads the cookie. s17 does not alter the flow.
- Design system: no invented tokens. Every `bg-*` / `text-*` / `border-*` in the new files resolves to a `tailwind.config.ts` token. No hardcoded Tailwind colors (`red-500`, `blue-50`, etc.).

## Tests (one per AC)

- AC1: `test_returns_dashboards_for_all_linked_children`.
- AC2: e2e (a) renders 2 cards linking to detail.
- AC3: e2e (e) read-only dashboard.
- AC4: `test_parent_alice_does_not_see_pauls_children` + `test_admin_sees_all_links`.
- AC5: e2e (f) + `test_claimed_unlinked_child_raises_403`.
- AC6: e2e (e) `getByRole('button', { name: 'Voir les détails' }).toHaveCount(0)`.

Cross-tenant isolation: `TestGetParentDashboardCrossTenant` (2 tests) + `TestAssertParentLinkedToChild` (6 tests).

## Findings

### Critical

**#1 — The `/dashboard/parent/[child_pseudo]` page is non-functional in production (always 403).**

- `frontend/app/(dashboard)/[locale]/dashboard/parent/[child_pseudo]/ParentChildClient.tsx:64` calls `apiClient.get('/api/dashboard/eleve', { params: { pseudo: childPseudo } })`.
- `backend/app/api/dashboard/eleve.py:80` invokes `assert_jwt_pseudo_matches_or_403(user, childPseudo, route="/api/dashboard/eleve")`. For a caller whose `role is PARENT` and `childPseudo != user.pseudo`, that helper unconditionally raises HTTPException(403, "forbidden"). The s15 helper blocks every non-admin non-self caller.
- The new helper `assert_parent_linked_to_child_or_403` (s17) is defined in `backend/app/core/auth/middleware.py:215` and tested by 6 tests, but **no router calls it** (`grep -rn "assert_parent_linked_to_child_or_403" backend/app/` returns only the definition).
- Consequence: any authenticated parent navigating to `/fr/dashboard/parent/bob` (where `bob` is linked) gets 403 and sees the "Cet enfant n'est pas lié à ton compte" 403 Card. Every parent, for every child, linked or not.
- Why tests miss this: the 8 e2e stub `page.route('**/api/dashboard/eleve**', ...)` to return 200/403 directly, never hitting the real backend. The bug is invisible in CI.
- The plan § Task 11 "Note" says the parent helper "covers our case" through the s16 endpoint with `?pseudo=`. That claim is false: the parent helper was never wired into `eleve.py`, and the plan § Files touched explicitly lists `eleve.py` as "not modified". The plan contradicts itself.
- Fix options:
  (a) Modify `eleve.py:80` to call `assert_parent_linked_to_child_or_403(user, pseudo, route="/api/dashboard/eleve", db=db)` in addition to or instead of `assert_jwt_pseudo_matches_or_403`. More surgical but touches a file the plan said not to touch.
  (b) Create a dedicated endpoint `/api/dashboard/parent/eleve/{child_pseudo}` that uses the new helper. Cleaner separation but duplicates the aggregation call.

### Major

**#2 — ParentChildClient renders DashboardClient which re-fetches `/api/dashboard/eleve` without `?pseudo=`, returning the parent's own dashboard.**

- `frontend/app/(dashboard)/[locale]/dashboard/parent/[child_pseudo]/ParentChildClient.tsx:131` renders `<DashboardClient readOnly={true} />` with no `pseudo` prop.
- `DashboardClient.tsx:205` calls `apiClient.get<EleveDashboardResponse>('/api/dashboard/eleve')` (no query param), which returns the dashboard of the JWT caller — i.e. the parent.
- Consequence: even if Finding #1 is fixed, the child-detail page would display the parent's own numbers under a header bearing the child's pseudo. The bug is again masked by the e2e stubs.
- Fix: extend the DashboardClient signature to `{ readOnly?: boolean; pseudo?: string }` and use `pseudo` in the apiClient URL when provided.

### Minor

**#3 — Read-only pastille drift: `text-primary` (design) → `text-primary-strong` (impl).**
Design docs `docs/designs/s17-dashboard-parent.md:130` and `:272` still say `text-primary`; the implementation uses `text-primary-strong` with the commit message "to clear WCAG AA (4.5:1)". Drift between code and design doc, otherwise justified.

**#4 — Pseudo-line drift: `text-text-tertiary` → `text-text-secondary`.**
Design doc line 140 still says `text-text-tertiary`; the implementation uses `text-text-secondary` for the same contrast reason. Drift doc.

**#5 — Child card displays `entry.pseudo` twice (name + pseudo lines).**
`ParentListClient.tsx:339` and `:342` both render `entry.pseudo`. The design mockup has "Alice Dupont" (real name) + "alice" (pseudo), but the s17 API has no `name` field. The fallback is visibly redundant. Acceptable degradation, but the UX diverges from the mockup.

**#6 — Child card badge content diverges from design mockup.**
Design HTML line 668: badge contains `+4 pts` (today's points delta). Implementation: `${Math.round(percent * 100)} %`, which duplicates the prominent `text-lg` value. Less informative but functional; the rewards system is not yet wired (plan § Run interdicts), so the fallback is reasonable.

**#7 — 5 dead i18n keys in `fr.json` / `en.json`.**
`dashboard.parent.detailTitle`, `detailReadOnly`, `refresh`, `refreshing`, `retry` are declared (plan § Task 10) but no component reads them. `check-i18n.sh` only catches hardcoded strings, not dead keys. Cleanup recommended.

**#8 — E2E tests stub `/api/dashboard/eleve` and hide findings #1 and #2.**
5 e2e tests on the child-detail page (e, f, h) use `page.route('**/api/dashboard/eleve**', ...)` to fake 200/403. There is no integration test that exercises the real backend with a parent caller. Adding one would have caught Finding #1.

## Not verified (human gestures needed)

- **End-to-end against the real backend.** The Playwright suite stubs both `/api/dashboard/parent` and `/api/dashboard/eleve`. A human should: start the API, seed a parent + child link in the DB, log in as the parent, navigate to `/fr/dashboard/parent/<child_lié>`, and observe whether the 403 Card appears (it will, per Finding #1). Same for `/fr/dashboard/parent/<child_non_lié>` (also 403, but for the wrong reason).
- **No backend integration test for Finding #1.** `pytest tests/api/dashboard/ -v` has no test that simulates a parent caller passing `?pseudo=<child>`. A human reviewer should write that test before re-running review.
- **Lighthouse a11y score.** `lighthouserc.json` was extended to the two new URLs, but `pnpm exec lhci autorun` was not run (it takes 1-2 minutes on headless Chrome). The inline `@axe-core/playwright` (e2e (g), (h)) is a reasonable proxy: 0 critical/serious violations.
- **Cache invalidation cross-tenant.** `test_reuses_eleve_cache_for_child_dashboards` covers the read path. Whether `invalidate_dashboard` correctly clears the cache when an Attempt is recorded (so the next parent view sees fresh data) was not verified.
- **Visual check of the pastille in dark mode.** `text-primary-strong` resolves differently in `[data-theme="dark"]`; the contrast should still pass but was not visually checked.
- **Name field gap.** The plan assumes the API will return a real name; it does not. If the parent UX is shipping with this gap, a human should confirm with the design owner that showing the pseudo twice is acceptable for v1.

## Summary

The plan is otherwise executed very cleanly: cache reuse is correctly implemented and tested, Run interdicts are respected, the 3 declared deviations are all justified, the design system is honored, and i18n/a11y/RBAC are aligned. The blocker is the missing wiring of `assert_parent_linked_to_child_or_403` into any router, which makes the entire child-detail page non-functional in production. The e2e stubs mask the issue.

**Required before ship**: pick option (a) or (b) for Finding #1; add the missing `?pseudo=` plumbing for Finding #2; add a backend integration test that exercises the real `eleve.py` with a parent caller; add or remove the 5 dead i18n keys; update `docs/designs/s17-dashboard-parent.md` to match the contrast fixes.

Max severity: critical
Ship allowed: no
