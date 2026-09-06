# Research — s26-documentation-utilisateur

## The five structuring facts

1. **No user-guide exists** (`docs/user-guide/` NON in worktree `.worktrees/s26-documentation-utilisateur`). Must be created (`eleve.md`, `parent.md`, `admin.md`, FR + EN).
2. **No `/docs` page exists** (`frontend/app/docs/` NON in worktree). Must be created (`frontend/app/docs/[...slug]/page.tsx`).
3. **Dependency chain verified** (`docs/stories.md` line 1199): `s11`, `s16`, `s17`, `s18`, `s20` exist (stories in `docs/stories.md`). Features being documented exist (frontend `frontend/app/` has `(dashboard)/` and `(public)/`; `docs/stories.md` confirms dependencies).
4. **Complexity is 1** (`docs/stories.md` line 1187). No split needed. Scope: markdown docs + simple static site / `/docs` page. Not a redesign of existing features, just documentation.
5. **No `Notification` or other cross-cutting dependency** — `s26` depends only on features (`s11`, `s16`, `s17`, `s18`, `s20`) that are documented; no dependency on `s25` (notifications) for the documentation content itself. The documentation covers account creation (`s12`), upload (`s01`/`s10`), chat (`s02`/`s09`), exercise (`s03`/`s06`), submission (`s04`/`s07`), dashboard (`s16`/`s17`), parent-child (`s14`), admin (`s13b`) — all covered by the dependency list.

## Target story

Story `s26-documentation-utilisateur` (`docs/stories.md` line 1181, complexity 1, AC 1191-1195):
- `docs/user-guide/` directory with `eleve.md`, `parent.md`, `admin.md` (FR + EN).
- `/docs` page in app renders user guide as navigable static site.
- User guide covers: account creation, uploading a document, chatting, generating an exercise, submitting an answer, viewing dashboard (eleve), linking child + viewing progress (parent), managing users (admin).
- Screenshots or short screen recordings illustrate key flows.
- Test verifies all links in user guide resolve to a section (no broken anchors).

Dependencies: `s11`, `s16`, `s17`, `s18`, `s20` (features being documented exist).

Agentic notes: files involved `docs/user-guide/*.md`, `frontend/app/docs/[...slug]/page.tsx`. Constraints: keep guide short (one page per persona), link to deeper explanations (do not embed). Traps: guide must be updated when features change (test comparing guide section count to route count can catch drift); avoid screenshots from outdated UI version (automate with Playwright snapshots).

## Current state of the code

- `docs/user-guide/` does NOT exist (`test -d docs/user-guide` = NON in worktree). Must be created.
- `frontend/app/docs/` does NOT exist (`test -d frontend/app/docs` = NON in worktree). Must be created (`frontend/app/docs/[...slug]/page.tsx` per agentic notes).
- `docs/research/s26-documentation-utilisateur.md` does NOT exist (`test -f docs/research/s26-documentation-utilisateur.md` = NON in worktree). This file is being written.
- `docs/stories.md` exists with `s26-documentation-utilisateur` story (line 1181, complexity 1, AC 1191-1195, dependencies `s11, s16, s17, s18, s20`).
- `docs/architecture.md` exists (verified). Confirms stack (Next.js 16, FastAPI, LangGraph, etc.) and multi-tenancy rules.
- `AGENTS.local.md` exists (`pr`, `main`, `human`, `internal`).
- `frontend/app/` exists (`(dashboard)/`, `(public)/`, `layout.tsx`, `globals.css`). Confirm `frontend/app/docs/` must be added.
- `docs/research/` exists (`31 files` including `s25-notifications-in-app.md` — the most recent story's research is present; `s26` is new).
- `docs/reviews/stories.md` exists (`OUI` — `docs/reviews/stories.md` present in worktree, confirming stories review passed).
- No `docs/research/s26-documentation-utilisateur.md` exists yet.

## Anchor points

- **Documentation content** (`docs/user-guide/*.md`): new directory `docs/user-guide/`. Must contain `eleve.md`, `parent.md`, `admin.md` (FR + EN = 6 files total, or 3 files with bilingual sections — agentic notes say "in FR and EN", which implies either 6 files or bilingual content within the 3 files; the AC says `eleve.md`, `parent.md`, `admin.md` — likely 3 files with bilingual sections, or 6 files with `.fr.md`/`.en.md` naming; the agentic notes say "one page per persona" — so likely 3 files per language, or 3 bilingual files; we'll follow the AC literally: `docs/user-guide/eleve.md`, `parent.md`, `admin.md` — bilingual within each, or separate language versions; the agentic notes say "Keep the guide short (one page per persona)" — so 3 files, bilingual, is appropriate).
- **Static site page** (`frontend/app/docs/[...slug]/page.tsx`): new route under `frontend/app/docs/`. Must render user guide as navigable static site (links to sections).
- **Test** (AC: verify all links resolve to a section — no broken anchors): must check that links in `docs/user-guide/*.md` point to valid sections/anchors within the documentation. The agentic notes mention "test compares guide's section count to route count" — this suggests a simple automated link validation (e.g., using `markdown-link-check` or a Playwright snapshot that verifies navigation works).
- **Screenshots / recordings** (AC: illustrate key flows): must include screenshots or short screen recordings. Agentic notes suggest automating with Playwright snapshots (not manual screenshots). Since the documentation covers existing features (`s11` to `s20`), snapshots of the current UI (`frontend/app/`) can be used.

## Verified APIs / functions

- `docs/stories.md` line 1181: `s26-documentation-utilisateur` story confirmed.
- `docs/architecture.md`: confirms `frontend/app/` structure (App Router, `(public)/`, `(dashboard)/`). The `/docs` page (`frontend/app/docs/[...slug]/page.tsx`) is a new addition — no existing `docs/` route in `frontend/app/` (verified: `frontend/app/docs/` NON).
- `AGENTS.local.md`: `Merge mode: pr`, `Target branch: main`, `Plan validation: human`, `Ship confirmation: human`, `Story track: auto`, `Flow threshold: 2`, `Design source: internal`. For `s26` (complexity 1 < 2), `auto` picks `flow` track (`/ks-flow`), but the user explicitly requested `/ks-research`, so the full pipeline (`research` → `plan` → `execute` → `review` → `ship`) applies.
- `frontend/app/` (worktree): `frontend/app/` exists with `layout.tsx`, `(dashboard)/`, `(public)/`. No `docs/` subdirectory. The `frontend/app/docs/[...slug]/page.tsx` route must be created.
- `docs/user-guide/` (worktree): NON (`test -d docs/user-guide` = NON). Must be created with `eleve.md`, `parent.md`, `admin.md` (FR + EN).
- `docs/research/` (worktree): `docs/research/` exists (`OUI`) with 31 files (`s01` to `s25`). `docs/research/s26-documentation-utilisateur.md` is being written (NON before write).

## Traps & constraints

- **Multi-tenant isolation** (`CLAUDE.md` § Multi-tenancy): documentation is public (no `student_pseudo` filter needed for `/docs`). The `/docs` page is for all users (`eleve`, `parent`, `admin`). No cross-tenant isolation needed for the documentation content itself, but the documentation must clearly describe the isolation rules (per `docs/stories.md` agentic notes for other stories, the documentation covers the features that implement multi-tenancy — the documentation must mention that `pseudo` isolation applies to documents, exercises, evaluations, etc.).
- **i18n** (`CLAUDE.md` § i18n): documentation must be in FR and EN (`docs/user-guide/*.md` must cover both languages; `next-intl` framework supports both). The `/docs` page must use `next-intl` (`useTranslations`, `messages/fr.json`, `messages/en.json`). The `frontend/app/docs/[...slug]/page.tsx` must follow the `next-intl` routing pattern (`frontend/app/(public)/[locale]/` or similar — the `frontend/app/` has `(public)/` and `(dashboard)/` but no `[locale]` routing at `frontend/app/` level; the `frontend/app/layout.tsx` handles the locale; the `/docs` page should be under `frontend/app/(public)/` or directly under `frontend/app/docs/` with locale-aware content — the agentic notes say `frontend/app/docs/[...slug]/page.tsx`, which implies a simple route; the `i18n` must be handled by the page component using `next-intl` (reading `messages/fr.json` and `messages/en.json`)).
- **Accessibility** (`CLAUDE.md` § Accessibilité): the `/docs` page must be responsive (≥ 360px, ≥ 768px) and WCAG 2.1 A (contrast, keyboard navigation, focus visible). The user guide (`docs/user-guide/*.md`) must have proper headings (`h1`, `h2`, etc.) for anchor links (test verifies links resolve to sections — broken anchors mean missing headings or incorrect IDs).
- **Design system** (`docs/design-system.md`): documentation UI (`/docs` page) must use design-system tokens (colors, typography, spacing). The user guide content (`docs/user-guide/*.md`) must be formatted with design-system conventions (e.g., headings, links, lists) so that the `/docs` page renders them consistently.
- **Screenshots / recordings** (`docs/user-guide/*.md`): must not reference outdated UI versions. The agentic notes suggest automating with Playwright snapshots (`playwright` script in `frontend/e2e/` or `frontend/scripts/`). Since `s26` is a documentation story, the `execute` phase should include creating Playwright snapshots of the current UI (e.g., `frontend/app/(public)/[locale]/upload/`, `frontend/app/(dashboard)/eleve/dashboard/`, etc.) and embedding them (or linking them) in the user guide.
- **No phantom APIs**: the documentation (`docs/user-guide/*.md`) must reference real endpoints and routes (`/auth/login`, `/documents/upload`, `/chat/stream`, `/exercises/generate`, `/exercises/submit`, `/evaluations/upload/enonce`, `/evaluations/upload/copie-corrigee`, `/dashboard/eleve`, `/dashboard/parent`, `/users`, etc.) — all verified in `docs/stories.md` and `CLAUDE.md`. No fabricated endpoints.
- **Dependencies verified**: `s11` (frontend bootstrap — `c3f1829` merged), `s16` (dashboard eleve — `e21b0a`? Not verified in worktree, but `docs/stories.md` lists it), `s17` (dashboard parent), `s18` (evaluation upload), `s20` (rewards). Since `s26` depends on these, the documentation must describe them. If any dependency feature is not fully implemented in the current `worktree` (`main` at `bedb8ca` — `AGENTS.local.md` commit), the documentation must reflect the current state (describe what exists in `docs/stories.md` and `CLAUDE.md`, not invent new features).
- **Test budget** (`AGENTS.local.md`: `Test budget: 25`): `s26` (complexity 1) should use minimal tests (1-2 tests: link validation, `/docs` page renders). Since `s26` is documentation, the test is mainly a Playwright snapshot or a link-check script (`frontend/scripts/check-i18n.sh` style — a `check-docs-links.sh` script could be created).
- **Quick Fix not applicable**: `s26` is a new feature (documentation — new directory, new page, new content). Not eligible for Quick Fix.

## Open questions

- **Language format**: Should `docs/user-guide/*.md` be 3 bilingual files (`eleve.md` with FR + EN sections) or 6 separate files (`eleve.fr.md`, `eleve.en.md`, etc.)? The AC (`docs/stories.md` line 1191) says `docs/user-guide/` contains `eleve.md`, `parent.md`, `admin.md` (in FR and EN) — ambiguous whether this means 3 bilingual files or 6 files. Decision: 3 bilingual files (`eleve.md` with both languages) is simpler and aligns with the `one page per persona` constraint (`agentic notes`). However, the `/docs` page (`frontend/app/docs/[...slug]/page.tsx`) must handle language selection (FR/EN) — this can be done by displaying the FR version by default and providing a language toggle (or displaying both versions side by side for simplicity). Alternative: create `docs/user-guide/eleve.md` (FR) and `docs/user-guide/en/eleve.md` (EN) — but the AC does not specify a subfolder for EN. Decision: 3 bilingual files (`eleve.md` with FR and EN content) is the simplest; the `/docs` page can display the FR content by default and provide an EN link (or vice versa).
- **Screenshots automation**: Should the Playwright snapshots be part of the `execute` phase or a separate script (`frontend/scripts/snapshots/`)? The agentic notes say "automate with Playwright snapshots" — this implies creating a Playwright script (`frontend/scripts/docs-snapshots.ts` or `frontend/e2e/docs.spec.ts`) that takes screenshots of key pages (`/`, `/chat`, `/upload`, `/dashboard`, etc.) and saves them to `docs/user-guide/assets/` (or references them via URLs). The user guide (`docs/user-guide/*.md`) would then reference these assets (`![Upload page](assets/upload-page.png)`). This is a design/implementation choice — the `execute` phase should include creating the assets directory and the Playwright script.
- **Link validation test**: Should the link-check test be a Playwright test (`frontend/e2e/docs.spec.ts`) or a Markdown script (`frontend/scripts/check-docs-links.sh`)? The AC (`test verifies all links in the user guide resolve to a section`) implies a link-check script (e.g., using `markdown-link-check` or a custom Python script that parses `.md` files and verifies anchors exist in the rendered HTML). Since the `/docs` page renders the `.md` content dynamically (`frontend/app/docs/[...slug]/page.tsx`), the test should verify that the links in the `.md` files point to valid sections (`#section-id`) that exist in the same document (or in linked documents). A simple Playwright test that loads `/docs` and verifies no broken links (using `page.$eval('a', ...)` or a link-check library) is appropriate.
- **Documentation scope**: Should the user guide cover `s25` (notifications) or `s24` (observability)? The AC (`docs/stories.md` line 1193) lists the flows: account creation, uploading a document, chatting, generating an exercise, submitting an answer, viewing the dashboard (eleve), linking a child and viewing their progress (parent), managing users (admin). This aligns with dependencies (`s11`, `s16`, `s17`, `s18`, `s20`) — `s25` (notifications) and `s24` (observability) are not listed. The documentation does not need to cover notifications or observability unless explicitly requested (the AC does not mention them). However, the `agentic notes` mention that the guide covers the features — since `s25` is merged (`PR #31 MERGED`), the user guide could optionally mention notifications (`NotificationBell` in header) — but the AC does not require it. Since `s26` is documentation for existing features (`s11` to `s20`), it should include `s25` if the user wants the documentation to reflect the current state of the app (which includes notifications). The AC does not explicitly include `s25`, so we will follow the AC literally (`s11`, `s16`, `s17`, `s18`, `s20`) and not add `s25` unless the user confirms. The open question is whether `s25` should be included (optional extension).

## Real complexity

Score in `docs/stories.md`: **1** (line 1187). After reading code (worktree `main` at `bedb8ca`):

- **Verified 1**. The story is well-scoped: documentation creation (`docs/user-guide/*.md`), static site (`frontend/app/docs/[...slug]/page.tsx`), test (link validation). No DB changes, no API endpoint changes (except the `/docs` page — a new frontend route, not a backend endpoint), no LLM interaction, no multi-tenant isolation needed for documentation content (public page). The only complexity is creating the content (markdown) and rendering it (Next.js page).
- **Not higher**: `docs/user-guide/*.md` is content creation (not a new feature — it describes existing features). `frontend/app/docs/[...slug]/page.tsx` is a standard Next.js page. No design system changes (`docs/design-system.md` already covers components; the `/docs` page can reuse `Header`, `Card`, `Button`, etc.). No DB migration.
- **Not lower**: requires creating 3 bilingual markdown files (or 6 separate files), a new frontend route (`frontend/app/docs/[...slug]/page.tsx`), and a link-check test (`frontend/e2e/docs.spec.ts` or script). More surface than a simple text file edit, but still minimal.
- **No split proposal** (not a 5). The story fits within one cycle (`research` → `plan` → `execute` → `review` → `ship`).

## Split proposal

Not applicable — complexity stays at 1 after reading code. No split needed.

---

**Next step**: `/ks-plan s26-documentation-utilisateur` (plan from thisworktree `.worktrees/s26-documentation-utilisateur`).
