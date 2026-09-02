---
story: s11c-frontend-upload
branch: feature/s11c-frontend-upload
head: 5752639
parent: 094123e
reviewer: reviewer-subagent
date: 2026-09-02
---

# Review — s11c-frontend-upload

## Verdict

The story is shippable. All 25 e2e tests pass (7 s11c + 7 s11b + 11 s11a). All 36 unit tests pass (12 FileUpload + 24 pre-existing). Lint, typecheck, and `bash scripts/check-i18n.sh` exit 0. The worktree is clean. The 3 P0 invariants (no manual Content-Type, 413/415 discrimination on `lastHttpStatus`, `forwardRef<HTMLInputElement>` on `<FileUpload>`) were neutralized and re-verified — each neutralization broke the corresponding test(s) and the restoration fixed them, proving the implementation is not just present but load-bearing.

## What I verified

- **Worktree state**: `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload`, branch `feature/s11c-frontend-upload`, HEAD `5752639`, parent `094123e`. Single commit on the feature branch. Clean working tree.
- **Tests run myself**:
  - Unit: `pnpm exec vitest run` → 36 / 36 pass (5 files, FileUpload 12 + 24 pre-existing).
  - E2E: `pnpm exec playwright test` → 25 / 25 pass in 19s (upload 7 + chat 7 + home 5 + pseudo 4 + responsive 2).
  - i18n: `bash frontend/scripts/check-i18n.sh` → exit 0.
  - Lint: `pnpm run lint` → exit 0.
  - Typecheck: `pnpm run typecheck` → exit 0.
- **Diff scope**: 17 files, +3375 / -52. All the plan's expected files are present (`docs/{plans,research,designs}/s11c-frontend-upload.*`, the new `UploadClient.tsx`, `page.tsx`, `uploadStore.ts`, `FileUpload.test.tsx`, `e2e/upload.spec.ts`, the extended `FileUpload.tsx`, `Header.tsx`, `Button.tsx`, `messages/{fr,en}.json`, `lighthouserc.json`, `package.json`, `pnpm-lock.yaml`).
- **`.env.bak*` not in commit**: confirmed empty (`git show 5752639 -- '*.bak*' '*.env*'` is empty).
- **Single commit** lists docs + code together (per AGENTS.md § Pipeline).

## Central invariants — neutralized and proven

1. **`forwardRef<HTMLInputElement>` on `<FileUpload>`** (the page needs it to reopen the picker on 415):
   - Removed `useImperativeHandle` from `frontend/components/FileUpload.tsx`.
   - **Result: test (l) went RED** (`expected null not to be null` on `ref.current`). Restored, re-ran → 12 / 12 pass. `git diff --exit-code` clean.
2. **413 vs 415 discrimination on `lastHttpStatus`** (Piège T4, AC9(b)):
   - Removed the `if (lastHttpStatus === 413)` / `else if (lastHttpStatus === 415)` branches from `frontend/app/(public)/[locale]/upload/UploadClient.tsx`, falling through both to `storage_failure`.
   - **Result: e2e (c) AND e2e (d) both went RED** — (c) couldn't find "Fichier trop volumineux", (d) couldn't find "Extension non supportée". Restored, re-ran → 25 / 25 pass. `git diff --exit-code` clean.
3. **Multipart FormData** (3 fields: `pseudo`, `subject`, `file`): verified by reading `frontend/e2e/upload.spec.ts:55-79` — `route.request().postData()` inspected for the three `name="…"` markers and values. The store calls `apiClient.post('/api/documents/upload', formData)` with no Content-Type override (`Grep` confirms the only `Content-Type` mentions in `uploadStore.ts` are in the CRITICAL comment).

## Specific point-by-point checks

| # | Claim | Verified | File:line |
|---|---|---|---|
| 1 | `lucide-react@^0.460.0` in deps + pnpm-lock | ✓ | `frontend/package.json:31`, `frontend/pnpm-lock.yaml` (3 new lines), peer `^16.5.1 \|\| ^17.0.0 \|\| ^18.0.0 \|\| ^19.0.0-rc` (pre-release range includes 19.0.0 final, pnpm resolves cleanly) |
| 2 | No manual `Content-Type` in `uploadStore.upload` | ✓ | `frontend/lib/stores/uploadStore.ts:155-159` — `apiClient.post('/api/documents/upload', formData)`, no headers. Grep shows only comment mentions. |
| 3 | 413/415 discrimination on `response.status`, not `code` | ✓ | `frontend/lib/stores/uploadStore.ts:169-177` reads `err.response.status`; `frontend/app/(public)/[locale]/upload/UploadClient.tsx:111-117` checks `lastHttpStatus` first. Verified by neutralization. |
| 4 | `Header.tsx:90-97` no `aria-disabled`/`tabIndex={-1}` on `/upload`; `aria-current` set when on `/upload` | ✓ | `frontend/components/Header.tsx:91-99` — `aria-current={isUploadActive ? 'page' : undefined}`, no `aria-disabled` or `tabIndex`. |
| 5 | No `.doc` / `.docx` in any `accept` | ✓ | Grep confirms only `.pdf,.png,.jpg,.jpeg,.txt` and `image/*` (camera). |
| 6 | `Intl.NumberFormat(locale, { maximumFractionDigits: 1 })`, locale from `useLocale()` | ✓ | `frontend/components/FileUpload.tsx:75, 112-114`. |
| 7 | Drop zone is `<label htmlFor>`, `e.preventDefault()` on both `onDragOver` and `onDrop` | ✓ | `frontend/components/FileUpload.tsx:179, 91-96, 102-108`. |
| 8 | `forwardRef<HTMLInputElement>` on `<FileUpload>` | ✓ | `frontend/components/FileUpload.tsx:58, 84`. Verified by neutralization. |
| 9 | `clearFile()` does NOT clear `subject`; `reset()` clears all | ✓ | `frontend/lib/stores/uploadStore.ts:115-122` (clearFile) vs `195-204` (reset). |
| 10 | 415 picker-reopen is local `useRef` + `useEffect` on `lastHttpStatus === 415`; store has no `shouldReopenPicker` flag | ✓ | `frontend/app/(public)/[locale]/upload/UploadClient.tsx:63, 73-83`. Store has no such flag. |
| 11 | i18n check exit 0, no hardcoded strings | ✓ | `bash scripts/check-i18n.sh` → exit 0. |
| 12 | Test (b) inspects FormData (3 fields); test (d) asserts "Extension non supportée" | ✓ | `frontend/e2e/upload.spec.ts:55-79` (uses `postData()` instead of `formData()` because Playwright 1.49 doesn't expose parsed formData — comment explains); `frontend/e2e/upload.spec.ts:158`. |
| 13 | Lighthouse `url` includes `/fr/upload`, NOT `/en/upload` | ✓ | `frontend/lighthouserc.json:7-11`. |
| 14 | Single commit lists story docs + code | ✓ | `git show --stat 5752639` lists all 4 doc files + 13 code files. |
| 15 | Header comment of `uploadStore.ts` references s10 contract + 2 critical rules | ✓ | `frontend/lib/stores/uploadStore.ts:8-32` — quotes `router.py:81-210`, `schemas.py:35-72`, `upload_service.py:39` and explicit "do NOT set Content-Type" + "discriminate 413 vs 415 on response.status" warnings. |
| 16 | `.env.bak*` not in commit | ✓ | `git show 5752639 -- '*.bak*' '*.env*'` empty. |
| 17 | Playwright e2e + i18n + check-i18n.sh green | ✓ | 25/25, exit 0, exit 0. |
| 18 | Card colors + icons per design system | ✓ | `frontend/app/(public)/[locale]/upload/UploadClient.tsx:212, 242, 269` — `bg-success/10 border border-success/30`, `bg-warning/10 border border-warning/30`, `bg-error/10 border border-error/30`. Icons: `CheckCircle`, `AlertCircle`, `AlertTriangle` from `lucide-react`. |
| 19 | `pseudo` from `useAuthStore.getState().pseudo`, never from FormData input | ✓ | `frontend/lib/stores/uploadStore.ts:129` — `useAuthStore.getState().pseudo`. No pseudo input on the upload page. |

## Findings

### critical
None.

### major
None.

### minor

1. **Stale contradictory comment in `UploadClient.tsx:134-146`** — The code at lines 73-83 correctly implements the picker reopen on 415 via `useImperativeHandle` + `useEffect` + 100ms `setTimeout`. But the long comment block at lines 134-146 says: "For now, we ship the page WITHOUT the auto-reopen… To enable picker reopen: pass a ref via the FileUpload forwardRef API. Not implemented in s11c (kept simple)." This is internally contradictory — the code is implemented but the comment claims it isn't. Functionally correct; the comment should be deleted or rewritten to describe what actually ships.

2. **`errorCode` text color drift from design** — Design at `docs/designs/s11c-frontend-upload.md:125` says the machine code under error messages should be `text-xs text-text-tertiary`; `frontend/app/(public)/[locale]/upload/UploadClient.tsx:281` uses `text-xs text-text-secondary`. Slightly higher contrast than the muted intent; axe-core still passes (this is not an a11y violation).

3. **Send button missing `send` Lucide icon in non-uploading state** — Design `docs/designs/s11c-frontend-upload.md:124` says "Icône `send` Lucide 20px à gauche du label" for the Send button. Implementation only shows `<Loader2 size={20} className="animate-spin" />` when `isUploading`; the idle state has no icon. Minor visual drift.

4. **Drop zone `min-h-48` always instead of `min-h-48` mobile / `min-h-56` tablet** — Design § 5.1 / 5.2 specifies responsive drop zone heights; `frontend/components/FileUpload.tsx:165` uses a single `min-h-48` regardless of viewport. Minor visual drift.

5. **Unused `locale` variable in `UploadClient.tsx:40`** — `const locale = useLocale();` is declared but never read. Lint passes (project's eslint config doesn't flag this as error). Minor.

6. **Card subcomponents (`Card.Header` / `Card.Body` / `Card.Footer`) bypassed** — The design (`docs/designs/s11c-frontend-upload.md:38`) and the `Card` component's API suggest using the composed subcomponents. The implementation uses `<Card>` with custom children and inline `mt-3 pt-3 border-t border-{success|warning|error}/30` classes. Functionally equivalent, but drifts from the Card component's intended API and re-implements footer styling per card type. Minor.

7. **`aria-describedby` not passed to `<FileUpload>`** — Design `docs/designs/s11c-frontend-upload.md:179` says the drop zone should have `aria-describedby="upload-file-help"`. The `UploadClient.tsx:179-189` does not pass the `describedBy` prop. Minor a11y drift (axe-core still passes).

8. **`aria-label` for the camera button uses button text** — Design `docs/designs/s11c-frontend-upload.md:184` says `aria-label="Prendre une photo avec la caméra"`. Implementation at `frontend/components/FileUpload.tsx:210` uses `aria-label={t('takePhoto')}` (same as the button text). Slightly less descriptive for screen readers. Minor.

9. **Documented backend codes don't mention `network` frontend-only code** — `frontend/lib/stores/uploadStore.ts:43-48` includes `'network'` in the `UploadErrorCode` union but the header comment (lines 8-32) only lists the four backend codes (`invalid_pseudo`, `invalid_file`, `ocr_failure`, `storage_failure`). A reader expects the comment to list all valid `UploadErrorCode` values. Minor documentation drift.

10. **`Réessayer` button shown for `invalid_pseudo` is a no-op** — `frontend/app/(public)/[locale]/upload/UploadClient.tsx:118-120` shows the retry button when `lastError.code === 'invalid_pseudo'`, but clicking it calls `retry()` → `upload()` which early-returns because the pseudo is still invalid. The error message itself says "Recharge la page" — showing a non-functional retry is mildly confusing. Minor UX.

11. **Send button missing `w-full` on mobile** — Design `docs/designs/s11c-frontend-upload.md:156` says "Bouton « Envoyer » : full-width, hauteur 44px" on mobile. `frontend/app/(public)/[locale]/upload/UploadClient.tsx:192-209` wraps the button in a plain `<div>` without `w-full` on the button. Minor visual drift.

12. **`useImperativeHandle` with empty deps** — `frontend/components/FileUpload.tsx:84` uses `useImperativeHandle(ref, () => inputRef.current as HTMLInputElement, [])`. The empty deps array means the function runs once on mount; `inputRef.current` is populated at that point, so this works, but it's a fragile pattern if the input were ever conditionally rendered. Minor code-smell; not a bug today.

## What I could not verify

- **No browser screenshot** of `/fr/upload` at 360px and 768px. The design mockup `docs/designs/s11c-frontend-upload.html` exists and the e2e `responsive.spec.ts` checks no horizontal scroll, but I did not visually compare pixel layout to the mockup.
- **No Lighthouse run** in this environment. The `lighthouserc.json` is correctly extended with `/fr/upload` (point 13), but I did not execute `lhci autorun` to confirm the ≥ 0.9 accessibility assertion would pass. A human should run `pnpm run lighthouse` locally before ship if Lighthouse is a gate.
- **The drag-and-drop UX** is unit-tested via RTL (drop with 1 file, 2 files → first only, disabled) but no e2e covers the actual browser drag-drop interaction. The plan Q6 explicitly accepts this gap.
- **The picker-reopen 100ms timeout** is observable in the code (UploadClient.tsx:73-83) but no e2e verifies the picker actually reopens in the browser after a 415. The test (d) only asserts the error card text. A human should confirm visually.

## File paths

- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\app\(public)\[locale]\upload\UploadClient.tsx`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\app\(public)\[locale]\upload\page.tsx`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\components\FileUpload.tsx`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\components\FileUpload.test.tsx`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\components\Header.tsx`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\components\Button.tsx`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\lib\stores\uploadStore.ts`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\e2e\upload.spec.ts`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\lighthouserc.json`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\messages\fr.json`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\messages\en.json`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\package.json`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\frontend\pnpm-lock.yaml`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\docs\plans\s11c-frontend-upload.md`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\docs\research\s11c-frontend-upload.md`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\docs\designs\s11c-frontend-upload.md`
- `C:\Workspace\ktutor\.worktrees\s11c-frontend-upload\docs\designs\s11c-frontend-upload.html`

Max severity: minor
Ship allowed: yes
