---
validated: yes
---
# Plan — Story s26-documentation-utilisateur

Branch: `feature/s26-documentation-utilisateur`
Research: `docs/research/s26-documentation-utilisateur.md` — read it first; this plan does not repeat it.

## Target story

Story `s26-documentation-utilisateur` (`docs/stories.md` line 1181, complexity 1, AC 1191-1195):
- Create `docs/user-guide/` directory with `eleve.md`, `parent.md`, `admin.md` (FR + EN, bilingual within each file — one page per persona).
- Create `/docs` page (`frontend/app/docs/[...slug]/page.tsx`) rendering the guide as navigable static site.
- Cover 7 flows: account creation, document upload, chat, exercise generation, answer submission, dashboard view (eleve), child link + progress (parent), user management (admin).
- Include screenshots or short screen recordings illustrating key flows.
- Link-check test verifies all links in user guide resolve to a section (no broken anchors).

Dependencies verified (`docs/stories.md` line 1199): `s11`, `s16`, `s17`, `s18`, `s20` — features being documented exist.

## Tasks (ordered)

1. [ ] Create `docs/user-guide/eleve.md` (FR + EN sections, one page per persona). Covers: account creation, upload, chat, generate exercise, submit answer, view dashboard. Includes headings with anchor IDs for link-check test.
2. [ ] Create `docs/user-guide/parent.md` (FR + EN sections). Covers: linking child, viewing child progress, managing users. Includes headings with anchor IDs.
3. [ ] Create `docs/user-guide/admin.md` (FR + EN sections). Covers: managing users, overview of student flows. Includes headings with anchor IDs.
4. [ ] Create `frontend/app/docs/[...slug]/page.tsx` — new route rendering user guide markdown as navigable static site (links to sections, no new design tokens; reuse design-system components). Must use `next-intl` (`useTranslations`) for locale-aware content.
5. [ ] Create Playwright snapshot script (`frontend/scripts/docs-snapshots.ts` or `frontend/e2e/docs.spec.ts`) taking automated screenshots of key pages (`/`, `/upload`, `/chat`, `/dashboard/eleve`, etc.) to `docs/user-guide/assets/`. Link assets in `.md` files.
6. [ ] Create link-check test (`frontend/scripts/check-docs-links.sh` or `frontend/e2e/docs.spec.ts`) that parses `docs/user-guide/*.md` and verifies all internal anchor links (`#section-id`) resolve to headings present in the rendered HTML (`/docs` page). At minimum: load `/docs` in Playwright and verify no `404` anchors; optionally compare section count to anchor links.
7. [ ] Update `frontend/messages/fr.json` and `en.json` with any new i18n keys used by `/docs` page (e.g., documentation navigation labels).

## Run interdicts

- Must NOT invent phantom APIs/endpoints — documentation references only real endpoints (`/auth/login`, `/documents/upload`, `/chat/stream`, `/exercises/generate`, `/exercises/submit`, `/evaluations/upload/enonce`, `/dashboard/eleve`, etc.).
- Must NOT include `s25` (notifications) content unless explicitly confirmed — AC does not list notifications; the guide covers `s11` to `s20` only.
- Must NOT embed full feature explanations in the guide — link to deeper docs (`docs/stories.md`, `CLAUDE.md` sections) instead; guide stays short (one page per persona).
- Must NOT use outdated screenshots — automate with Playwright snapshots (`frontend/scripts/docs-snapshots.ts`) against current UI state (`main` at current worktree).
- Must NOT create `docs/designs/s26-documentation-utilisateur/` — no new screen design needed (story has no UI redesign; `/docs` page is derived, not a new design screen).

## The point everything turns on

Whether `docs/user-guide/*.md` covers all 7 flows from AC line 1193 (`eleve.md`: 5 flows; `parent.md`: 2 flows; `admin.md`: 1 flow) while staying short (`one page per persona`). If any flow is missing, the documentation is incomplete; if the guide becomes too long, it violates the `agentic notes` constraint (`Keep the guide short`). The reviewer should verify section headings match the 7 flows.

Second point: whether `/docs` page (`frontend/app/docs/[...slug]/page.tsx`) uses existing design-system components (no new tokens) and `next-intl` (`useTranslations`). If new components are invented, the design system is violated; if `useTranslations` is missing, i18n is broken.

Third point: link-check test must actually run and pass. A missing or non-running test means broken anchors go undetected.

## Files touched

- `docs/user-guide/eleve.md` (new)
- `docs/user-guide/parent.md` (new)
- `docs/user-guide/admin.md` (new)
- `frontend/app/docs/[...slug]/page.tsx` (new)
- `frontend/app/docs/layout.tsx` (new — optional, if sub-section layout needed)
- `frontend/scripts/docs-snapshots.ts` (new — Playwright snapshot script)
- `frontend/e2e/docs.spec.ts` or `frontend/scripts/check-docs-links.sh` (new — link validation test)
- `docs/user-guide/assets/` (new directory — screenshot assets)
- `frontend/messages/fr.json`, `frontend/messages/en.json` (updated with `/docs` page i18n keys)

## Test strategy

- **Link validation** (behavior test, closest layer): Playwright test (`frontend/e2e/docs.spec.ts`) loads `/docs` page and verifies all `<a href="#...">` anchors resolve to existing `<h2>`/`<h3>` headings in the rendered HTML. 1 test covering all 3 `.md` files.
- **i18n** (behavior): verify `/docs` page uses `useTranslations()` — check `frontend/app/docs/[...slug]/page.tsx` for `next-intl` import; no hardcoded `fr` strings.
- **Render verification** (visual/browser check): load `/docs` in browser (development server), verify navigation links work and content renders correctly for both `fr` and `en` locales. Not an automated test assertion, just a focused visual check.
- **No cross-tenant isolation test needed**: `/docs` is public (no `student_pseudo` filter); no student-specific data accessed.
- **Test budget**: `Test budget: 25` (default per `AGENTS.local.md`). `s26` (complexity 1) uses 2 tests (link validation + i18n check) — well within budget. No full-suite run needed (story touches only docs + one new route; no DB/model changes).
- **No phantom APIs** verified by review: documentation references only endpoints listed in `CLAUDE.md` § APIs et Endpoints.

## Definition of Done

- `docs/user-guide/eleve.md`, `parent.md`, `admin.md` exist and contain FR + EN sections covering the 7 flows.
- `frontend/app/docs/[...slug]/page.tsx` exists, renders guide, uses `next-intl`, reuses design-system components, no new tokens.
- Link-check test (`frontend/e2e/docs.spec.ts`) passes (no broken anchors).
- Playwright snapshot assets (`docs/user-guide/assets/`) exist for key flows.
- No phantom APIs, no outdated screenshots, no `s25` content unless explicitly added.
- Review report (`docs/reviews/s26-documentation-utilisateur.md`) ends with `Ship allowed: yes` and `Max severity: none` (or `minor` if only style issues).
