# Review — s25-notifications-in-app

## Plan compliance
- Code covers all 12 tasks from the validated plan (checked via `grep -c "\[x\]"` in docs/plans/s25-notifications-in-app.md: 12/12 checked).
- Interdicts respected: no `EventSource` (polling uses `fetch` — though auth issue noted), no `localStorage`, no pagination, no new tokens invented, `Notification` model lives in `models.py`, no `WebSocket`.

## Anti-hallucination
- Every import verified by opening files: `Notification` model exists (`models.py` line 611+); `NotificationType` enum (`models.py` line 604+); `notifications.py` endpoints (`GET /` with `unread_only`, `POST /{id}/read`); `notificationsStore` (`poll`, `startPoll`, `stopPoll`, `markRead`); `NotificationBell` (lucide `Bell`, `onClick` prop, `unreadCount` prop); `Toast` (props `message`, `type`, `onClose`).
- No phantom APIs referenced; `main.py` includes router.

## Rules compliance
- `AGENTS.md` conventions followed (snake_case files, PascalCase classes, kebab-case URLs `/api/notifications`).
- Multi-tenant filter present (`Notification.student_pseudo == user.pseudo`).
- Design-system gaps (`docs/design-system.md` lines 231, 237) addressed: `Toast` and `NotificationBell` components created, reuse existing tokens (`bg-error`, `text-info`, `text-success`, `text-warning`, `shadow-kt-md`, `rounded-md`). No new CSS variables.
- No ADR contradicted.

## Tests
- Tests run by reviewer: 7 passed; neutralized reward trigger (`if False`) → 1 test failed (`test_reward_ledger_insert_creates_notification`); restored (`git diff --exit-code` clean after fixing trigger).
- Assertions cover: notification creation on `Evaluation` status change, notification creation on `RewardLedger` insert, read idempotency, cross-tenant isolation, transaction rollback.

## Regressions
- `models.py`, `main.py`, `Header.tsx` modified; existing endpoints (`chat`, `documents`, `exercises`) untouched in diff. `notification_type_enum` added to DB — no collision.

## Findings
- Major — `frontend/lib/stores/notificationsStore.ts` line 36: `poll()` uses bare `fetch()` without `Authorization: Bearer <token>`. The backend `notifications.py` endpoints require JWT (`Depends(get_current_user)`), so polling will always get 401 in a real session. Must use `apiClient` (axios with interceptor) or attach `Authorization` header manually.
- Major — `frontend/components/NotificationBell.tsx` line 15: `onClick={onClick}` is a prop but the dropdown is never rendered (no dropdown state/markup). The design (`docs/designs/s25-notifications-in-app.md` § Mockup) expects a dropdown showing recent notifications. Currently clicking the bell does nothing visible.
- Minor — `frontend/components/NotificationBell.tsx` line 21: badge uses `text-[10px]` instead of design-system token `text-xs`. Should use `text-xs` for consistency.

## Not verified
- No real browser render (no `npm run dev` + visual inspection of `NotificationBell` dropdown or `Toast` appearance).
- No real JWT authentication flow tested (poll uses bare `fetch`, so auth path wasn't actually exercised in integration tests beyond stubbed requests).
- No Playwright e2e for dropdown interaction or toast display.
- Database rollback transaction consistency was verified via simulated session rollback test, not via a real multi-process crash scenario.
- Mobile viewport (360px) not verified for new header layout with bell.

## Verdict
Max severity: major
Ship allowed: no
