---
name: s21-i18n-fr-en-research
description: Verified code context for s21-i18n-fr-en (FR/EN i18n consolidation) before planning.
metadata:
  type: project
---

# Research — s21-i18n-fr-en (i18n FR/EN consolidation)

## Story isolated

- **Id**: `s21-i18n-fr-en`
- **Title** (docs/stories.md l.1015): « Basculer l'interface entre français et anglais »
- **As a** utilisateur **I want** basculer entre FR et EN **so that** l'app soit utilisable dans les deux langues.
- **Complexity** (docs/stories.md): **3** — « next-intl setup + message catalogs + backend Accept-Language ». Confirmed after reading code: two surfaces with different contracts.
- **Dependencies** (docs/stories.md l.1034): `s11` (frontend chat page exists). Confirmed via docs/reviews/stories.md: s11 split into s11a (merged `c3f1829`), s11b, s11c — all shipped. No dependency blocker.

## Verified premise — what the story asserts

### 1. Frontend i18n infrastructure exists and works

| Assertion from story / docs | Verified in code | Status |
|---|---|---|
| `frontend/i18n/routing.ts` defines `locales: ['fr', 'en']`, `defaultLocale: 'fr'`, `localePrefix: 'always'` | Read `/c/Workspace/ktutor/.worktrees/s21-i18n-fr-en/frontend/i18n/routing.ts` (l. 9-13) — exact match | ✅ Confirmed |
| `frontend/middleware.ts` uses `next-intl/middleware` with cookie `NEXT_LOCALE` | Read `frontend/middleware.ts` (l. 1-14) — `createMiddleware(routing)`, cookie-based persistence per comment | ✅ Confirmed |
| `frontend/messages/fr.json` + `en.json` contain UI catalogs | Read both files fully — namespaces present: `common`, `chat`, `upload`, `auth`, `dashboard`, `history`, `rewards`, `errors`. `rewards` namespace added by s20 (level.apprentice/confirmed/expert, badgeAria, points). No missing namespace for s21. | ✅ Confirmed |
| `frontend/components/LanguageSwitcher.tsx` exists (switcher in header) | Read file fully — pill toggle FR \| EN, uses `useLocale()`, `router.replace(pathname, { locale })`, `aria-pressed`, `useTranslations('common')`. Already wired to cookie middleware. | ✅ Confirmed |
| No hardcoded strings in components (per design-system.md § i18n) | Design-system.md (l. 194-198) mandates `useTranslations()` everywhere. `frontend/scripts/check-i18n.sh` exists. No evidence of hardcoded UI strings in `components/` files inspected (`Header.tsx`, `Button.tsx`, etc.). | ✅ Confirmed (no contradiction found) |

### 2. Design-system reference for i18n exists

- `docs/design-system.md` (l. 191-198) defines i18n conventions: `next-intl`, catalogs `fr.json`/`en.json`, namespaces extensible, `<LanguageSwitcher>` component, cookie `NEXT_LOCALE`, `useTranslations()` everywhere.
- `<LanguageSwitcher>` component spec documented at design-system.md l. 127 (`LanguageSwitcher`) — props and behavior match the implemented component.
- No new design-system token or component needed for s21. The switcher uses existing tokens (`primary`, `surface-subtle`, `text-secondary`, `border`).

### 3. Backend `Accept-Language` — the open gap

- `CLAUDE.md` (line 539 area in original repo, confirmed in research context): backend `Accept-Language` is « préparé, à implémenter plus tard » — **not implemented**.
- `backend/app/core/config.py`: no `i18n` settings, no message catalog loader, no `Accept-Language` middleware.
- `backend/app/api/auth/schemas.py`: error messages (`RegisterErrorResponse.error`, `AuthErrorResponse.error`) are hardcoded in French (`message="Ce pseudo est déjà pris."`, `message="Pseudo ou mot de passe incorrect."`). No localization mechanism.
- `backend/app/api/auth/router.py`: error payloads (`_register_error_payload`, `_auth_error_payload`) pass literal French strings. The `code` field (`RegisterErrorCode`, `AuthErrorCode`) is the machine discriminator — this is the intended contract for backend i18n (per design-system.md note and agentic notes: « small JSON message catalog contract for backend (error codes → messages) »).
- `backend/app/services/ocr/` and other services: no i18n references found beyond language-related comments (not UI messages).
- **Conclusion**: the backend surface is the unimplemented part. The frontend surface (catalogs, switcher, cookie, routing) is complete.

## Verified code files (worktree absolute paths)

All reads performed in `.worktrees/s21-i18n-fr-en` (branch `feature/s21-i18n-fr-en`, clean — 0 uncommitted changes besides inherited `.env.bak` files which are gitignored/non-trackable per worktree-manager output).

- `frontend/i18n/routing.ts`
- `frontend/middleware.ts`
- `frontend/messages/fr.json` (full)
- `frontend/messages/en.json` (full)
- `frontend/components/LanguageSwitcher.tsx` (full)
- `frontend/components/Header.tsx` (partial — confirms switcher integration and pseudo cookie)
- `docs/stories.md` (s21 section, l. 1015-1046)
- `docs/design-system.md` (full — design-system reference for i18n)
- `docs/reviews/stories.md` (confirms s11 dependency resolved, s21 complexity 3)
- `backend/app/core/config.py` (confirms no i18n settings)
- `backend/app/api/auth/schemas.py` (confirms hardcoded French messages, stable `code` fields)
- `backend/app/api/auth/router.py` (confirms error payload pattern)

No code edits made. No writes made. This file (`docs/research/s21-i18n-fr-en.md`) is the deliverable.

## Complexity re-score (after reading code)

- `docs/stories.md` assigns **3**.
- Verified: low risk for frontend (catalogs already present, switcher implemented, middleware configured). Higher risk for backend (`Accept-Language` not implemented; requires new message-catalog mechanism or Pydantic-based translation layer). Two surfaces with different contracts = complexity holds at 3.
- **No split proposal needed** — 3 is below the split threshold (5). If backend `Accept-Language` proves larger than a small catalog contract, split proposal can be raised at `/ks-plan`.

## Open questions (honest unknowns — not guesses)

1. **Backend message-catalog format**: should the backend reuse the same JSON format as frontend (`messages/<locale>.json`) or use a minimal Pydantic-based catalog (e.g., `backend/app/core/i18n/messages_fr.json`)? The design-system note (l. 200) mentions « Pydantic + gettext approach » for growth, but the story note (agentic notes) suggests « small JSON message catalog contract (error codes → messages) ». Which format does the user want? Not settled in code.
2. **Cookie locale routing vs URL locale routing**: the middleware (`routing.ts`) uses `localePrefix: 'always'` — URLs are `/fr/chat`, `/en/chat`. The cookie (`NEXT_LOCALE`) drives the redirect. The story AC does not specify whether the backend should read locale from URL (`/fr/chat`) or cookie (`Accept-Language` header). The design-system (l. 198) says cookie. The backend AC (l. 1028) says `Accept-Language` header. Both must work; the interaction is not specified. Not a blocker, but needs clarification at `/ks-plan`.
3. **Scope of backend messages to translate**: the AC says « any user-facing string (errors, prompts) ». In the current backend, user-facing strings are: auth errors (`register`, `login`, `refresh`, `logout`), document upload errors (`upload_service.py` — not fully read, needs verification), chat stream errors (`chat/stream` — SSE events with `{error, code}`). Does the story cover ALL endpoints or just auth + upload? Not fully specified. Research did not read every router file for messages; only auth schemas verified. Additional verification needed at plan time.
4. **No design file exists for s21**: `docs/designs/` has no `s21-i18n-fr-en.md` or `.html`. The design-system (l. 191-198) already covers the switcher and i18n conventions. A dedicated design file is optional for a non-UI-heavy story, but the pipeline convention (`/ks-design`) expects one for UI stories. Must decide at `/ks-plan`: is s21 a UI story (language switcher in header — yes) requiring a design mockup, or is the design-system reference sufficient?
5. **No backend `Accept-Language` middleware exists**: the story assumes it will be added. No existing middleware file (`app/core/auth/middleware.py` handles JWT only; `app/api/` routers don't parse headers for language). Implementation approach: add a small helper in `app/core/i18n/` or extend `app/api/` routers individually. Not decided.

## Traps spotted (verified from code and docs)

- **Trap 1 — Do not translate user-uploaded content** (agentic notes): the `frontend/messages/fr.json` only contains UI chrome; no mechanism exists to translate document content. Confirmed: design-system (l. 203) explicitly excludes user content. No trap in implementation, but a reminder.
- **Trap 2 — Locale routing consistency**: the middleware rewrites URLs; the cookie is the source of truth. If backend reads `Accept-Language` but frontend uses URL-based locale (`/fr/chat`), a mismatch could occur (e.g., user visits `/en/chat` with `Accept-Language: fr` header). The story AC requires both to work; the design-system picks cookie for frontend. Not a contradiction, but needs alignment at plan.
- **Trap 3 — Design-system gap**: `docs/design-system.md` (l. 244) notes `output: "standalone"` missing and `capture` limitations as gaps, but does NOT list any i18n-related gap. The switcher design is fully covered. No gap for s21.
- **Trap 4 — Multi-tenant unaffected**: i18n does not touch `student_pseudo`, `rag_` collections, or S3 prefixes. Confirmed: no isolation impact.
- **Trap 5 — Progressive.py untouched**: `docs/research/s20-systeme-recompenses.md` (carried from previous session) confirms progressive correction untouched. s21 does not touch it either. Confirmed.

## Re-score and verdict

- Score in `docs/stories.md`: 3
- Re-score after reading code: **3** (holds)
- Risk: backend `Accept-Language` unimplemented; two surfaces (frontend complete, backend missing). Mitigation: define small JSON catalog contract (as noted in agentic notes) rather than full gettext.
- Verdict: **ready for `/ks-plan`** (or `/ks-design` first if design mockup required). No split needed.

## Next step

- `/ks-plan s21-i18n-fr-en` (plan validated with `validated: yes` required before `/ks-execute`).
- Before `/ks-plan`, consider whether `/ks-design s21-i18n-fr-en` is needed — the design-system covers the switcher; a dedicated design mockup may be optional but recommended for a UI story (language switcher in header). Decision needed at plan time (see open question 4).

---
*End of research. File written to `.worktrees/s21-i18n-fr-en/docs/research/s21-i18n-fr-en.md`. Worktree at `/c/Workspace/ktutor/.worktrees/s21-i18n-fr-en`, branch `feature/s21-i18n-fr-en`, clean status. No code edited. Next: `/ks-plan s21-i18n-fr-en` or `/ks-design s21-i18n-fr-en` (optional, depending on open question 4).*
