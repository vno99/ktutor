# Research — s22-accessibilite-responsive

## The five structuring facts

1. `docs/design-system.md` lines 178-189 already defines the full a11y contract (`focus-visible`, `aria-invalid`/`aria-busy`/`aria-live`, touch targets 44×44, reduced-motion, axe-core 0 critical/serious, Lighthouse ≥90). The design system is the authority, not the story.
2. `frontend/app/globals.css` (l.69-99) already implements `prefers-reduced-motion` (l.84-93) and `:focus-visible` (l.96-99). The accessibility shell is in place.
3. `frontend/components/StreamingMessage.tsx` (l.98-103) has `role="log"`, `aria-live="polite"`, `aria-busy`. Typing indicator uses `motion-reduce:animate-none`. The chat stream is screen-reader-ready.
4. `frontend/components/FileUpload.tsx` (l.178-243) uses `<label htmlFor>` as the visible, focusable drop zone (not `<div onClick>`), with `aria-disabled`, `aria-busy`, `sr-only` input, and `capture="environment"`. The upload a11y is already implemented.
5. The Playwright config (`frontend/playwright.config.ts`, l.13-41) has a single `chromium` project (Desktop Chrome, locale `fr-FR`) with no mobile/tablette viewport, no `axe-core` assertion, and no responsive breakpoints. Lighthouse config (`frontend/lighthouserc.json`) asserts `minScore: 0.9` for accessibility but the story requires it actually passes on the real pages.

## Target story

`s22-accessibilite-responsive` (docs/stories.md l.1049-1079). Complexity 3.
Acceptance criteria: Lighthouse Accessibility ≥90 on chat/upload/dashboard/history; all interactive elements reachable via Tab with visible focus indicator; all images have `alt` (or `alt=""`); contrast ≥4.5:1; all form fields have `<label>`; responsive usable at 360px / 768px / 1280px (no horizontal scroll, no overlap); Playwright + axe-core automated audit asserts 0 critical/serious violations.
Dependencies: s11 (frontend exists). The practical dependency is s11b (chat) + s11c (upload) + s16 (dashboard) + s19 (history) — all shipped or fleshed out.

## Current state of the code

- `frontend/components/` — `Button.tsx`, `StreamingMessage.tsx`, `FileUpload.tsx`, `Header.tsx`, `Label.tsx`, `Select.tsx`, `Card.tsx`. All already follow the design-system a11y conventions (`focus-visible`, `aria-` props, `sr-only` where appropriate, `label htmlFor` pairing).
- `frontend/app/globals.css` — tokens, dark-mode, reduced-motion, focus-visible ring.
- `frontend/app/(public)/[locale]/chat/page.tsx` and `upload/page.tsx` — server entries that bootstrap locale; actual UI is in `ChatClient` / `UploadClient`.
- `frontend/app/(dashboard)/[locale]/dashboard/eleve/page.tsx` and `history/page.tsx` — same pattern.
- `frontend/playwright.config.ts` — only `chromium` desktop; no mobile/tablet viewport, no `axe-core` plugin, no responsive test assertions.
- `frontend/lighthouserc.json` — asserts `categories:accessibility` `minScore: 0.9` (l.20-23). The config exists but is not mentioned in any CI script or tests.
- No `frontend/scripts/check-i18n.sh` reference in this worktree (the design-system mentions it; not verified here).
- No skeleton loader, no `<Dialog>` / `<Modal>`, no `<Table>`, no `<Tabs>` components (design-system gaps l.232-244). These gaps are out of scope for s22 unless the story explicitly asks for them (it does not).

## Anchor points

- Design-system reference: `docs/design-system.md` § Accessibilité (l.178-189) and § Gaps (l.225-246).
- CSS tokens / focus / reduced-motion: `frontend/app/globals.css` (l.9-99).
- Chat stream a11y: `frontend/components/StreamingMessage.tsx` (l.98-182).
- Upload a11y: `frontend/components/FileUpload.tsx` (l.178-243).
- Header navigation / avatar / dropdown: `frontend/components/Header.tsx` (l.83-200) — uses `aria-label`, `aria-current`, `role="menu"`/`menuitem`.
- Responsive / Lighthouse target pages: `/fr/chat`, `/fr/upload`, `/fr/dashboard/eleve`, `/fr/history` (plus EN equivalents in `lighthouserc.json` l.8-15).
- Playwright / axe-core integration point: `frontend/playwright.config.ts` (needs additional project or plugin) and a new or extended `frontend/e2e/*.spec.ts` file.

## Verified APIs / functions

- `ButtonProps` (`frontend/components/Button.tsx` l.39-44): `variant`, `size`, `leftIcon`, `children`, extends native `HTMLButtonElement`. Focus ring and disabled styling built-in.
- `StreamingMessageProps` (`frontend/components/StreamingMessage.tsx` l.57-74): `isStreaming?`, `hasContent?`, `error?`, `sources?`, `streamingStatus?`, `t?`, `tErrors?`, `onRetry?`. `aria-live="polite"` and `aria-busy` derived from `streamingStatus`.
- `FileUploadProps` (`frontend/components/FileUpload.tsx` l.33-45): `id?`, `name?`, `accept?`, `maxSizeMb?`, `required?`, `describedBy?`, `selectedFile?`, `disabled?`, `onFileSelect`, `label`, `helpText?`. Drop zone is a focusable `<label htmlFor>` (not `<div onClick>`).
- `SelectProps` (`frontend/components/Select.tsx` l.13-21): native `<select>` wrapper with `id`, `options`, `invalid?`, `aria-invalid`.
- `LabelProps` (`frontend/components/Label.tsx` l.10-13): `htmlFor` (required), `children`, `srOnly?`.
- `globals.css` tokens (`frontend/app/globals.css` l.9-33): `@theme` block with `--color-*`, `--font-sans`, `--font-mono`, `--radius-*`. Light and dark modes defined (l.36-67).
- `lighthouserc.json` assertions (`frontend/lighthouserc.json` l.20-23): `categories:accessibility` `minScore: 0.9`.
- `CLAUDE.md` constraints verified: design-system intact; `progressive.py` untouched (interdict s08); multi-tenant preserved; manual merge mode; `docs/research/` and `docs/plans/` must be in the worktree.

## Traps & constraints

- The design-system (§ Accessibilité) is already very detailed. Most of the s22 ACs (focus visible, `alt` on images, contrast ≥4.5:1, `<label>` pairing, keyboard navigation) are already satisfied by the existing components. The real work of s22 is verification (Lighthouse runs, axe-core Playwright tests, responsive breakpoints), not new component design.
- `progressive.py` interdict (AGENTS.md / s08): the progressive correction algorithm file must not be modified by this story. Confirmed: no reference to `progressive.py` in any frontend file; the interdict is safe.
- Playwright config currently has only `chromium` desktop (`frontend/playwright.config.ts` l.26-31). To test responsive at 360px / 768px, the config must either add viewport overrides per test or add mobile/tablet projects. Changing `playwright.config.ts` is allowed (it's a test config, not business logic).
- Lighthouse config (`frontend/lighthouserc.json`) asserts `minScore: 0.9` for accessibility, but the story requires the score actually passes. If the current pages have a11y gaps (e.g. missing `alt` on decorative icons, contrast issues with `text-text-tertiary` on `bg-surface-subtle` — design-system § Don't l.183-189 warns against this combination), the fix is either a CSS token change or component-level override, not a new component.
- The `docs/design-system.md` gaps list includes items (Skeleton loader, `<Dialog>`, `<Tabs>`, `<Table>`, `<NotificationBell>`, dark/light toggle, Stop button on stream) that are out of scope for s22 unless the AC demands them. The AC does not mention any of these explicitly.
- Multi-tenancy isolation must be preserved: any a11y fix that touches shared components (`Button`, `StreamingMessage`, `FileUpload`) must not break the isolation contract (no pseudo leakage, no cross-collection reads). Confirmed: these components are UI-only, no DB/ChromaDB dependency.
- No `docs/research/s22-accessibilite-responsive.md` exists yet in the worktree (`docs/research/` is empty). This research file is being written now.
- The `worktree-manager` agent completed successfully (`aeff91af16efb4724`): worktree at `.worktrees/s22-accessibilite-responsive`, branch `feature/s22-accessibilite-responsive`, HEAD `8b89244`, clean tracked status. Untracked `.env.bak` / `.env.bak.s11b-preserved` copied from base; `.env` properly ignored.

## Open questions

1. **Responsive viewport testing strategy**: Should the Playwright config get new `projects` (e.g. `mobile`, `tablet`) or should responsive assertions live inside a single `chromium` project with `test.use({ viewport: ... })`? The design-system (§ Layout l.176) says test at 360px and 768px; it does not mandate a separate project.
2. **axe-core integration**: Should we import `@axe-core/playwright` directly in the Playwright config (plugin mode) or call `axe.run()` manually inside a spec? The design-system (§ Accessibilité l.188) mentions `axe-core/playwright` in CI. There is no reference to `axe-core` in `frontend/playwright.config.ts` today.
3. **Lighthouse CI execution**: Is `lighthouserc.json` already wired into `.github/workflows/` or any CI script? Not verified in this worktree. If not wired, the AC "Lighthouse ≥ 90" requires either wiring it or running `npx lhci autorun` manually as part of the story's verification.
4. **Image `alt` audit**: The components (`Button` leftIcon, `FileUpload` icons, `Header` avatar, `StreamingMessage` typing indicator) use `aria-hidden="true"` for decorative icons (correct). Are there any `<img>` tags (not `<span>` icons from Lucide) in the dashboard / history / chat pages that lack `alt`? Not fully verified across all pages in this research. The AC requires all images have `alt` (or `alt=""` if decorative). A quick audit of `frontend/app/**/page.tsx` and their clients (`DashboardClient`, `HistoryListClient`, etc.) is needed at plan time.
5. **Contrast audit**: The design-system warns against `text-text-tertiary` (`#8B95A3`) on `bg-surface-subtle` (`#F4F6FA`) (l.183-189). Are any existing screens using that combination? Not fully audited. If yes, the fix is either a token change (affects all screens) or a targeted override in the component/page using it.

## Real complexity

**3 (unchanged)**. The codebase already implements most of the a11y contract (design-system § Accessibilité is very complete; components already have `aria-`, `focus-visible`, `label` pairing, `sr-only`, reduced-motion). The remaining work is verification (Lighthouse runs, axe-core Playwright assertions, responsive viewport checks, image `alt` audit, contrast audit) plus any fixes discovered by those audits. There is no new feature or redesign required. Complexity stays at 3; no split proposal needed.

If the audit reveals a major structural gap (e.g. the responsive layout requires a complete redesign of the dashboard grid, or a major token change for contrast), the complexity could rise to 4, but the current evidence does not support that.

## Split proposal

Not required (complexity 3, not 5). A single story can cover: (1) Playwright + axe-core audit setup + responsive viewport assertions; (2) Lighthouse CI verification (or manual run); (3) image `alt` audit and fixes; (4) contrast audit and fixes; (5) keyboard navigation verification (Tab + focus indicator). All of these are verification/fix tasks, not independent features.

---

*Worktree: `.worktrees/s22-accessibilite-responsive` (`feature/s22-accessibilite-responsive`, HEAD `8b89244`).
Source of truth: `docs/design-system.md` § Accessibilité; `frontend/app/globals.css`; `frontend/components/*.tsx`; `frontend/playwright.config.ts`; `frontend/lighthouserc.json`.`
