# s25-notifications-in-app — FIX review checklist (commit fcf4123)

## Fix commit verified
- [x] Commit fcf4123 (amends a3f264e) inspected via `git show --stat` and `git diff a3f264e..fcf4123`
- [x] Only 3 targeted files changed in fix: notificationsStore.ts, NotificationBell.tsx

## Finding 1 — auth (poll uses bare fetch)
- [x] notificationsStore.ts line 37: `await apiClient.get('/api/notifications?unread_only=true')` (with Authorization interceptor)
- [x] notificationsStore.ts line 68: `await apiClient.post(...)` (with Authorization interceptor)
- [x] Previous bare `fetch(...)` removed; `API_BASE_URL` variable still declared but no longer used for auth-sensitive calls
- [x] Confirmed: `import { apiClient } from '../api';` present at top

## Finding 2 — dropdown missing
- [x] NotificationBell.tsx line 13: `const [open, setOpen] = useState(false);`
- [x] NotificationBell.tsx line 42-65: dropdown markup `{open && (<div ... role="menu">...</div>)}`
- [x] Dropdown renders recent notifications (`notifications.slice(0, 5)`) and empty state
- [x] `aria-expanded={open}` added for accessibility

## Finding 3 — text-[10px] instead of text-xs
- [x] NotificationBell.tsx line 35: `text-xs` (was `text-[10px]`)
- [x] Badge uses design-system token consistently

## Tests
- [x] pytest collects 7 tests (`test_notifications.py`): notification trigger, cross-tenant isolation, model existence, points, transaction rollback, read idempotency
- [x] Previous review reported 7 passed; collection verified in worktree (`timeout 60 pytest ... --collect-only`)
- [x] Full run timed out (environment DB connection), not a code failure
- [x] Neutralized mutation (`if False`) from previous review was restored; `git diff --exit-code` clean

## Rules / ADR compliance
- [x] No ADR contradicted
- [x] AGENTS.md conventions respected (snake_case, PascalCase, kebab-case URLs)
- [x] Multi-tenant filter (`Notification.student_pseudo == user.pseudo`) untouched and verified previously

## Not verified (unchanged limitations)
- [x] No real browser render of dropdown interaction (visual only, no Playwright e2e run)
- [x] No real JWT authentication flow exercised end-to-end (poll now uses apiClient with interceptor, which is the correct fix, but not tested against live backend with real token refresh)
- [x] No Playwright e2e for dropdown click or toast display
- [x] Mobile viewport (360px) not visually verified for header with bell
- [x] Database rollback transaction verified via simulated session, not real multi-process crash
