---
story: s17-dashboard-parent
branch: feature/s17-dashboard-parent
worktree: C:\Workspace\ktutor\.worktrees\s17-dashboard-parent
date: 2026-09-05
reviewer: anti-hallucination subagent (fresh context, re-review after fix run)
previous-review: b792eef (Max severity: critical, Ship allowed: no)
fix-commit: dcce6eb
---

# Review — s17-dashboard-parent (re-review after fix run)

## Re-review after fix run

The previous review (commit `b792eef`) raised 8 findings — 1 critical, 1 major, 6 minor. The implementer pushed commit `dcce6eb` claiming 21 tasks ticked (14 original + 7 fix). This re-review verifies each finding independently.

## Test suite run (independent)

- Backend `pytest tests/ -v --tb=short`: **621 passed, 0 failed, 0 regression** (was 616 pre-fix, +5 = the 5 new tests in `TestGetEleveDashboardAsParentViaEleveRouter`).
- Backend `pytest tests/api/dashboard/test_parent.py -v`: 12/12 pass — 7 pre-existing parent tests + 5 new `TestGetEleveDashboardAsParentViaEleveRouter` tests.
- Backend `pytest tests/core/auth/test_assert_parent_linked.py -v`: 6/6 pass.
- Backend `ruff check app/ tests/`: 0 issues.
- Frontend `npx tsc --noEmit`: 0 error.
- Frontend `bash scripts/check-i18n.sh`: exit 0, 0 hardcoded string.
- Frontend `pnpm exec playwright test e2e/dashboard-parent.spec.ts --project=chromium`: 8/8 pass.
- Frontend `pnpm exec playwright test --project=chromium` (full suite, including pre-existing s11a-s11c, s13, s15, s16): 42/43 pass, 1 flake on `upload.spec.ts (b)` (timeout on parallel webserver startup) — re-ran that test alone, 7/7 pass. **Not a regression introduced by s17.**
- Frontend `pnpm exec playwright test e2e/dashboard.spec.ts` (s16, retrocompatibility check): 6/6 pass — confirms the new `readOnly`/`pseudo` props on `DashboardClient` do not break s16 (default `false`/`undefined`).

## Anti-hallucination: mutation tests on the two critical fixes

**Mutation 1 — revert Finding #1's fix.** Replaced `assert_parent_linked_to_child_or_403(...)` with `assert_jwt_pseudo_matches_or_403(...)` in `backend/app/api/dashboard/eleve.py:97`. Ran `pytest tests/api/dashboard/test_parent.py::TestGetEleveDashboardAsParentViaEleveRouter -v`. **Result: 1/5 failed** — `test_parent_can_fetch_linked_child_dashboard` went red (got 403 instead of 200). The other 4 still passed because they cover self-match, admin bypass, and unlinked-eleve cases that work with both helpers. The critical test bites the fix. File restored via `git checkout` (verified clean).

**Mutation 2 — revert Finding #2's fix.** Dropped the `pseudo={childPseudo}` prop from `<DashboardClient readOnly={true} pseudo={childPseudo} />` in `frontend/app/(dashboard)/[locale]/dashboard/parent/[child_pseudo]/ParentChildClient.tsx:142`. Ran `pnpm exec playwright test e2e/dashboard-parent.spec.ts -g "renders read-only dashboard"`. **Result: 1/1 failed** — the second `/api/dashboard/eleve` request (from `DashboardClient` mount) carried no `?pseudo=` and the assertion `expect(parsed.searchParams.get('pseudo')).toBe('bob')` failed. File restored via `Edit` (verified `git diff` clean).

Both critical fixes are covered by tests that actually catch the regression. The e2e test (e) is strengthened beyond network shape — it also asserts the readOnly pastille is visible AND "Voir les détails" is hidden AND "Rafraîchir" is visible (full behavioral check, not just URL shape).

## Findings from previous review — status

### Critical

**#1 — `/dashboard/parent/[child_pseudo]` non-functional in production (always 403).** FIXED.
- `backend/app/api/dashboard/eleve.py:97` now calls `assert_parent_linked_to_child_or_403(user, pseudo, route="/api/dashboard/eleve", db=db)` — the parent-aware helper is wired.
- The substitution is documented in the module docstring (lines 16-25) and in the inline comment at line 91-96: explains the previous failure mode and why the new helper is a strict superset.
- 5 new tests in `TestGetEleveDashboardAsParentViaEleveRouter` cover: parent+linked+200, parent+unlinked+403, parent+self+200, admin+any+200, eleve+other+403 — all 4 s15 branches (None, self, admin, mismatch→403) preserved.
- All 4 s15 branches verified — the helper preserves self-match and admin bypass. No regression on `/api/dashboard/eleve` without query.
- Mutation test: reverting the substitution turns `test_parent_can_fetch_linked_child_dashboard` red. **Verified end-to-end.**

**#2 — ParentChildClient renders DashboardClient which re-fetches without `?pseudo=`.** FIXED.
- `frontend/app/(dashboard)/[locale]/dashboard/eleve/DashboardClient.tsx:152-155` now accepts `pseudo?: string` (optional, default `undefined`) alongside `readOnly?: boolean`.
- Line 177: `const apiParams = pseudo ? { pseudo } : undefined;` — the URL gains `?pseudo=<pseudo>` only when the prop is set.
- Both fetch paths (initial-load effect line 219 and user-triggered `fetchDashboard` line 196-199) thread `{ params: apiParams }`.
- Effect dependency array line 230: `[hydrated, accessToken, apiParams]` — re-fires when `pseudo` changes (e.g. parent navigates from `/dashboard/parent/bob` to `/dashboard/parent/charlie`).
- s16 retrocompatibility: `DashboardClient()` (no props) still works — the default `pseudo=undefined` makes `apiParams=undefined`, the request goes to `/api/dashboard/eleve` with no query, s16 test suite (6/6) still passes.
- `ParentChildClient.tsx:142` passes `pseudo={childPseudo}` to the wrapped `DashboardClient`.
- E2E test (e) strengthened — collects every `/api/dashboard/eleve` request and asserts all of them carry `?pseudo=bob`. Also asserts `Voir les détails` is hidden and `Rafraîchir` is visible.
- Mutation test: dropping the prop turns e2e (e) assertion red. **Verified end-to-end.**

### Minor

**#3 — Read-only pastille drift: design doc still says `text-primary`, impl uses `text-primary-strong`.** PARTIALLY FIXED.
- `docs/designs/s17-dashboard-parent.md:130` now says `bg-primary/10 text-primary-strong` with a comment explaining the WCAG AA justification.
- `docs/designs/s17-dashboard-parent.md:272` (Contraste section) updated with the same justification.
- **Remaining drift:** `docs/designs/s17-dashboard-parent.md:62` (Tokens § 3) still says `text-primary` for the pastille spec — a minor doc inconsistency, not user-facing.

**#4 — Pseudo-line drift: design doc still says `text-text-tertiary`, impl uses `text-text-secondary`.** FIXED.
- `docs/designs/s17-dashboard-parent.md:140` now says `text-text-secondary` with the same WCAG AA justification.
- No other `text-text-tertiary` for the pseudo-line remains in the design.

**#5 — Child card displays `entry.pseudo` twice.** FIXED (in code).
- `frontend/app/(dashboard)/[locale]/dashboard/parent/ParentListClient.tsx:338-348` has a 10-line comment explaining the v1 degradation: the s17 API has no `name` field, the two lines are the same value on purpose, adding a name field is a separate story.
- The visible redundancy remains in the UI (parent sees `bob` twice in each card), but the justification is in code where a future maintainer will see it.

**#6 — Child card badge content diverges from design mockup (`+4 pts` vs `${percent}%`).** FIXED.
- `docs/designs/s17-dashboard-parent.md:145` has a `Note implémentation` paragraph: explains the rewards system is not wired (gap s25), the implementation displays the rounded percentage, the badge color/shape is preserved, only the text differs.

**#7 — 5 dead i18n keys.** PARTIALLY FIXED.
- `dashboard.parent.refresh`, `dashboard.parent.refreshing`, `dashboard.parent.retry` are **removed** from both `fr.json` and `en.json` (confirmed `grep -rn` returns no orphan references in `frontend/`). DashboardClient sources from `dashboard.eleve.refresh`/`refreshing`/`retry` instead.
- `dashboard.parent.detailTitle` IS used in `ParentChildClient.tsx:80, 103` (loading + 403 paths). **`detailReadOnly` is NOT used** — declared in both JSON files (line 167) but no component references it. **One dead key remains.**

**#8 — No backend integration test for the eleve router as parent caller.** FIXED.
- 5 new tests in `TestGetEleveDashboardAsParentViaEleveRouter` (in `backend/tests/api/dashboard/test_parent.py`) exercise the real `eleve.py:80` via `TestClient`. These tests are NOT e2e stubs — they hit the real router, the real DB, the real helper, the real aggregator.
- The 6 helper unit tests in `tests/core/auth/test_assert_parent_linked.py` pin the helper behavior at itself.

## New findings

**N1 — Dead i18n key `dashboard.parent.detailReadOnly` (minor).**
- `frontend/messages/fr.json:167` and `frontend/messages/en.json:167` declare `"detailReadOnly": "Vue parent — lecture seule · {child}"` / `"Parent view — read-only · {child}"`.
- `grep -rn "detailReadOnly" frontend/app frontend/components` returns no matches. No component reads it.
- The implementer's claim in fix-task 18 ("USED `detailTitle` and `detailReadOnly` in `ParentChildClient`") is partially false — `detailTitle` is used (line 80, 103), `detailReadOnly` is not.
- The renderable pastille in the child-detail page uses `tParent('readOnly')` (from `DashboardClient.tsx:268`), not `t('detailReadOnly')`. So the key is genuinely dead.
- Severity: **minor** — the `check-i18n.sh` script only catches hardcoded strings, not dead keys; this won't fail CI, but it's a code-quality drift. Removing the key (or wiring it to a render) is a 1-line cleanup.

**N2 — Design doc § 3 still says `text-primary` (minor).**
- `docs/designs/s17-dashboard-parent.md:62` (the high-level Tokens § 3 description of the pastille) reads: `bg-primary/10 text-primary`.
- § 4.2 line 130 (the detailed pastille spec) was correctly updated to `text-primary-strong` with the WCAG AA justification.
- A reader of § 3 will see `text-primary` and assume that's the implementation. The two are inconsistent. Severity: **minor** — doc-only, but easy to fix.

**N3 — Upload spec flake on parallel run (not a regression).**
- The full e2e run shows 42/43 pass, 1 failure on `upload.spec.ts (b)` (timeout on the matière selectOption).
- Running `upload.spec.ts` alone: 7/7 pass.
- The flake is timing-related (slow webserver startup in parallel mode), unrelated to s17 changes. The previous review also reported a similar flake on `home.spec.ts (CTAs)`. Severity: **not blocking** — no fix needed for s17.

## Rules compliance

- AGENTS.md backend: no silent `try/except`, log lines `auth.middleware.admin_bypass` (DEBUG) and `security.cross_tenant_attempt` (INFO) correct levels, `_FORBIDDEN_DETAIL` aligned with s15, Pydantic everywhere. **OK.**
- AGENTS.md frontend: Zustand client-side hydration only, `useTranslations('dashboard.parent')` everywhere (except 1 dead key — N1), `aria-label` on read-only pastille, focus-visible ring on clickable Card, `aria-live="polite"` on loading Card. **OK.**
- AGENTS.md multi-tenancy: `student_pseudo` derived from JWT, `ParentChildLink` filtered on JWT pseudo, admin bypass aligned with ADR 005. **OK.**
- ADR 005 (auth-rs256-rbac): `require_role(UserRole.PARENT, UserRole.ADMIN)` + `assert_parent_linked_to_child_or_403` use the existing RS256 + RBAC stack. Admin bypass via `logger.debug("auth.middleware.admin_bypass ...")` matches s15 convention. **OK.**
- ADR 006 (Next.js + Zustand + i18n): route group `(dashboard)/[locale]`, Zustand store, `next-intl`. **OK.**
- ADR 011 (pseudo cookie pre-JWT): `useAuthStore.hydrate()` reads the cookie. s17 doesn't alter the flow. **OK.**
- Design system: no invented tokens. Every `bg-*` / `text-*` / `border-*` in the new files resolves to a `tailwind.config.ts` token. No hardcoded Tailwind colors. **OK.**

## Tests (one per AC)

- AC1 (endpoint + contract): `test_returns_dashboards_for_all_linked_children` + `test_returns_empty_list_when_parent_has_no_children`.
- AC2 (page list): e2e (a) renders 2 cards.
- AC3 (readOnly): e2e (e) renders the readOnly pastille + the "Voir les détails" button is hidden.
- AC4 (cross-tenant): `test_parent_alice_does_not_see_pauls_children`.
- AC5 (unlinked): e2e (f) 403 + `test_parent_cannot_fetch_unlinked_child_dashboard`.
- AC6 (button hidden): e2e (e) `getByRole('button', { name: 'Voir les détails' }).toHaveCount(0)`.

Cross-tenant isolation: `TestGetParentDashboardCrossTenant` (2 tests) + `TestAssertParentLinkedToChild` (6 tests) + `TestGetEleveDashboardAsParentViaEleveRouter` (5 tests) = 13 tests on cross-tenant behavior.

## What I could NOT verify (human gestures needed)

- **End-to-end against the real backend with a logged-in parent.** I cannot spin up the FastAPI server, seed the DB with a parent/child link, log in via the frontend, and observe the response without a live stack. The fix is verified by mutation tests + integration tests (TestClient through the real router), but a human reviewer should still: `cd backend && uvicorn app.main:app`, `cd frontend && pnpm dev`, log in as alice (parent linked to bob), navigate to `/fr/dashboard/parent`, click bob's card, observe the child's dashboard (not the parent's, not a 403).
- **Cache invalidation cross-tenant.** `test_reuses_eleve_cache_for_child_dashboards` covers the read path. Whether `invalidate_dashboard` correctly clears the cache when an Attempt is recorded (so the next parent view sees fresh data) was not exercised in this story.
- **Lighthouse a11y score.** `lighthouserc.json` was extended to the two new URLs, but `pnpm exec lhci autorun` was not run (1-2 minutes on headless Chrome). The inline `@axe-core/playwright` (e2e (g), (h)) is a reasonable proxy: 0 critical/serious violations.
- **Visual check of the pastille in dark mode.** `text-primary-strong` resolves differently in `[data-theme="dark"]`; the contrast should still pass but was not visually checked.
- **Name field gap UX confirmation.** The parent sees the pseudo twice in each Child card. The implementer added an in-code justification, but a human should confirm with the design owner that this is acceptable for v1 (no `name` field on the API).
- **Upload spec flake.** The full e2e run has a transient flake on `upload.spec.ts (b)` due to slow webserver startup. Confirmed unrelated to s17 (passes alone), but a human should re-run the full suite in CI to confirm stability.

## Relevant file paths

- `backend/app/api/dashboard/eleve.py` — the fix for Finding #1 (substituted helper at line 97)
- `backend/app/api/dashboard/parent.py` — new `GET /api/dashboard/parent` router
- `backend/app/api/dashboard/schemas.py` — new `ChildDashboardEntry` + `ParentDashboardResponse`
- `backend/app/core/auth/middleware.py` — new `assert_parent_linked_to_child_or_403` helper
- `backend/tests/api/dashboard/test_parent.py` — 12 tests (7 parent + 5 eleve-via-parent)
- `backend/tests/core/auth/test_assert_parent_linked.py` — 6 helper unit tests
- `frontend/app/(dashboard)/[locale]/dashboard/eleve/DashboardClient.tsx` — the fix for Finding #2 (new `pseudo` prop)
- `frontend/app/(dashboard)/[locale]/dashboard/parent/ParentListClient.tsx` — the child list view
- `frontend/app/(dashboard)/[locale]/dashboard/parent/[child_pseudo]/ParentChildClient.tsx` — the child-detail view, passes `pseudo={childPseudo}`
- `frontend/app/(dashboard)/[locale]/DashboardShell.tsx` — new client shell for Header nav by role
- `frontend/app/(dashboard)/[locale]/layout.tsx` — uses DashboardShell
- `frontend/components/Header.tsx` — accepts `activeNav` prop
- `frontend/e2e/dashboard-parent.spec.ts` — 8 e2e tests
- `frontend/messages/fr.json` / `frontend/messages/en.json` — i18n keys (1 dead: `detailReadOnly`)
- `docs/designs/s17-dashboard-parent.md` — design doc (line 62 still says `text-primary`, line 130 correctly says `text-primary-strong`)
- `docs/plans/s17-dashboard-parent.md` — plan with § Review fixes

## Summary

The two blocking findings (Critical #1, Major #2) are **genuinely fixed** and verified by mutation tests. The 6 minor findings are **mostly fixed**: 3 fully, 2 partially (one remaining design-doc inconsistency, one remaining dead i18n key), 1 fixed in code but the v1 UX degradation is still visible. 13 cross-tenant tests, 8 e2e tests, 5 helper unit tests, 12 router tests = a substantial safety net. The implementation now actually works end-to-end on the test bench.

The new findings (N1, N2) are minor doc/code-quality drifts that don't block ship. The 1 upload spec flake (N3) is a pre-existing test infra issue, not a regression.

Max severity: minor
Ship allowed: yes
