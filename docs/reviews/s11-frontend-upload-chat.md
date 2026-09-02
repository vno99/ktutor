# Review — s11-frontend-upload-chat (s11a-frontend-bootstrap)

**Diff reviewed** : `git diff main...feature/s11-frontend-upload-chat` (5 commits: fff54d5 scaffold + c0dd47a Corepack + a9dfa41 order swap + 0572a9a pnpm 10 downgrade + 96f8c9b drop cache-from; 46 files, +10248 / -38).

**Tests run by reviewer** (fresh, not trusted from the summary):
- `pnpm run typecheck` — exit 0
- `pnpm run lint` — exit 0
- `pnpm run build` — exit 0; routes `/[locale]`, `/fr`, `/en` static-generated
- `pnpm exec playwright test` — **11/11 green** in 14.3s
- `bash frontend/scripts/check-i18n.sh` — exit 0

**Tests bite** : proved by neutralization on the central Piège #8 invariant (locale-routing). Replacing `createMiddleware(routing)` with `createMiddleware({locales:['fr','en'] as const, defaultLocale:'fr', localePrefix:'never'})` in `frontend/middleware.ts` made `home.spec.ts:17 "redirects / to /fr/"` and `home.spec.ts:30 "toggle to English works and persists"` go red (2/5 in home.spec.ts). `pseudo.spec.ts` and `responsive.spec.ts` stayed green (they don't exercise locale redirect). File restored, `git diff frontend/middleware.ts` is empty, tree clean.

**Plan compliance** : T0.1 (s11→s11a/b/c split in `docs/stories.md`), T0.3 (`.gitignore`), T1.x (scaffold), T2.x (i18n + 8 composants signature + auth store), T4.x (3 Playwright specs — 11 tests, plan said 10, the 11th is `marks aria-invalid when the pseudo is malformed`, a real test on the `isValidPseudo` reject path, acceptable extension), T5.x (CI hardening, no `continue-on-error` on lint/typecheck, pnpm via Corepack, Lighthouse CI, Playwright in CI, i18n check). The 4 CI-fix commits are not scope creep — they are the iterations the plan T5.1 required to make the job green.

**Anti-hallucination** : every imported symbol (`next-intl/plugin`, `next-intl/middleware`, `next-intl/routing`, `next-intl/navigation`, `useTranslations`, `getTranslations`, `setRequestLocale`, `getMessages`, `hasLocale`, `useLocale`, `useTransition`, `useId`, `forwardRef`, `create`, `AxeBuilder`, `@lhci/cli`) resolves to a real export. All declared dependency versions exist on npm. `next.config.ts` uses `typedRoutes: true` at the top level (correct for Next 16; `experimental.typedRoutes` is `@deprecated` per `node_modules/next/dist/server/config-shared.d.ts:416` — the plan was slightly stale on this, the code is right). The frontend pseudo regex `/^[a-zA-Z0-9_]{3,32}$/` matches the backend's strict validation in `chroma_store.py:PSEUDO_RE`.

**Rules compliance** : AGENTS.md § Frontend / Git / i18n all respected. ADR 006 not violated (no structural change required, no new ADR needed). Design-system tokens used everywhere (verified — no raw hex in components, no inline color styles). `check-i18n.sh` exits 0.

**Findings** (each with severity):

- **Minor — `frontend/components/Header.tsx:78-91`** : the `<Link href="/chat" aria-disabled="true">` and `<Link href="/upload" aria-disabled="true">` lack `tabIndex={-1}`. The design-system l.228 and the plan § 4.2 explicitly call for `aria-disabled="true"` AND `tabindex="-1"`. Without `tabIndex={-1}`, the link stays in the tab order and clicking it still navigates to a 404. WCAG 2.4.7 / 2.1.1 concern, not flagged by the current axe-core config.
- **Minor — `frontend/app/layout.tsx:26`** : `<html lang="fr">` is hardcoded. When the user toggles to English, the page renders English content but `<html lang="fr">` — screen readers will mispronounce English text. The file's own comment (lines 14-18) acknowledges this as a Next 16 limitation. Real product behavior but known framework constraint; flag for s11b/s11c follow-up.
- **Minor — `frontend/next.config.ts:11-15`** deviates from the plan T1.5 promise of `output: "standalone"`. The implementer correctly left it out (standalone requires symlink support, EPERM on Windows without elevation). The plan is wrong on this; the code is right. Not blocking.
- **Minor — Lighthouse score ≥ 90 on `/fr/`** : the `lighthouserc.json` threshold is correct and the CI step exists, but the reviewer did not run `lhci autorun` locally (requires Chrome + built app). The CI gate is what enforces it.

**Could NOT verify** : Lighthouse score (CI-only), axe-core on `/en/` (only `/fr/` is tested in `home.spec.ts:54-66`), visual rendering of `docs/designs/s11-frontend-upload-chat.html` (T3.1 is human validation), CI environment exactness (ubuntu-latest + SeaweedFS service container not exercised locally). Recommended human gestures: open the mockup in a browser, watch a CI run of the `frontend` job end-to-end (Lighthouse in particular), exercise the Header nav links at the keyboard to confirm the tab-order finding.

**No critical, no major, four minors.** Story is solid. Ship.Key paths reviewed:
- `C:/Workspace/ktutor/.worktrees/s11-frontend-upload-chat/docs/plans/s11-frontend-upload-chat.md` (validated: yes)
- `C:/Workspace/ktutor/.worktrees/s11-frontend-upload-chat/docs/research/s11-frontend-upload-chat.md`
- `C:/Workspace/ktutor/.worktrees/s11-frontend-upload-chat/frontend/middleware.ts` (the neutralization target, restored clean)
- `C:/Workspace/ktutor/.worktrees/s11-frontend-upload-chat/frontend/components/Header.tsx` (minor finding source)
- `C:/Workspace/ktutor/.worktrees/s11-frontend-upload-chat/frontend/app/layout.tsx` (minor finding source)
- `C:/Workspace/ktutor/.worktrees/s11-frontend-upload-chat/frontend/next.config.ts` (deviation from plan T1.5, justified)
- `C:/Workspace/ktutor/.worktrees/s11-frontend-upload-chat/.github/workflows/ci.yml` (4 follow-up commits are in scope)


---

Max severity: minor
Ship allowed: yes
