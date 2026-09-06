---
validated: yes
---
# Plan — s25-notifications-in-app

Branch: `feature/s25-notifications-in-app`
Research: `.worktrees/s25-notifications/docs/research/s25-notifications-in-app.md`
Design: `.worktrees/s25-notifications/docs/designs/s25-notifications-in-app.md`

## Target story

Story s25 (docs/stories.md:1148, complexity 3, AC 1156-1165): notifications in-app déclenchées par le traitement d'une évaluation (`s18`) et par l'attribution de points (`s20`). Polling 30s. Toast + badge non lu dans le header.

Dependencies: s18 (Evaluation model), s20 (RewardLedger model) — both verified present in `.worktrees/s25-notifications/backend/app/core/database/models.py`.

## Tasks (ordered)

1. [x] **DB model `Notification`** (`models.py`): add `Notification` class (UUID PK, `student_pseudo` FK/index, `type` enum (`new_evaluation`, `points_awarded`), `message` String(512), `related_id` UUID nullable, `is_read` bool default False, `created_at` DateTime). No Alembic migration needed (init_db creates via `Base.metadata.create_all` per convention s04-s08).
2. [x] **Trigger integration — `Evaluation`**: in the evaluation router/service (`backend/app/api/evaluations/` or `services/evaluations/`), when status becomes `scored` (or `manual_review_needed`), insert `Notification(type='new_evaluation', message='...', student_pseudo=...)` in the same DB transaction.
3. [x] **Trigger integration — `RewardLedger`**: in `backend/app/services/rewards/ledger.py` (or wherever `RewardLedger` INSERT happens), when `points_awarded > 0`, insert `Notification(type='points_awarded', message='...', student_pseudo=...)` in the same transaction.
4. [x] **API endpoints** (`backend/app/api/notifications.py`): `GET /api/notifications?unread_only=<bool>` (filter by `student_pseudo` from JWT, optional `is_read=False`), `POST /api/notifications/{id}/read` (idempotent: returns 200 even if already read; updates `is_read` to True). Include router in `main.py`. Protect with JWT middleware (extract `sub` = pseudo, enforce `student_pseudo` filter).
5. [x] **Frontend store `notificationsStore`** (`frontend/lib/stores/notificationsStore.ts`): Zustand store (`notifications: Notification[]`, `unreadCount: number`, `poll(): void`, `startPoll()`, `stopPoll()`, `markRead(id): Promise<void>`). `poll()` calls `GET /api/notifications?unread_only=true` and updates store. `startPoll()` uses `setInterval(30000, ...)` with cleanup. Hydrate client-side only (like `authStore`).
6. [x] **Component `<NotificationBell>`** (`frontend/components/NotificationBell.tsx`): icon `bell` (Lucide), props `unreadCount`, `onClick`. Badge: `bg-error rounded-full` with count, visible only when `unreadCount > 0`. Click handler opens dropdown (simple `div` positioned absolute below header, max 5 notifications). Follows design-system conventions (no new tokens).
7. [x] **Component `<Toast>`** (`frontend/components/Toast.tsx`): props `message`, `type?: 'info' | 'success' | 'warning'`, `onClose?`. Style: `bg-surface border border-border shadow-kt-md rounded-md p-4`, icon `info` (`text-info`) / `check-circle` (`text-success`) / `alert-circle` (`text-warning`), message `text-text-primary`. `aria-live="polite"`. Auto-dismiss after 5s (`setTimeout`). Optional close button (`x`).
8. [x] **Header integration** (`frontend/components/Header.tsx`): add `<NotificationBell>` between `LanguageSwitcher` and pseudo/avatar. Wire `notificationsStore` (`useNotificationsStore`) to read `unreadCount`. Call `startPoll()` on mount (`useEffect`) and clean up on unmount. Ensure `NotificationBell` only renders when user has a valid pseudo (same guard as chat/upload buttons).
9. [x] **Cross-tenant isolation tests**: backend test verifies `pseudo_a` does not retrieve `Notification` rows of `pseudo_b` via `GET /api/notifications`. Frontend test verifies `NotificationBell` shows 0 for a user with no notifications.
10. [x] **Transaction test**: backend test verifies `Notification` INSERT occurs in same DB transaction as `RewardLedger` INSERT (simulate via session rollback after reward insert → notification should also rollback). If transaction isolation is not explicitly tested, at minimum verify notification exists after reward insert and is removed if reward is rolled back.
11. [x] **Read idempotency test**: `POST /api/notifications/{id}/read` called twice on same ID — second call returns 200 (not 409) and `is_read` remains True.
12. [x] **Design-system gaps verification**: confirm `docs/design-system.md` gap lines for `Toast` and `NotificationBell` are addressed (components exist in `frontend/components/`). No new gaps added (no new tokens invented).

## Run interdicts

- **No `EventSource`**: not relevant (polling uses `fetch`, not SSE).
- **No `Toast` outside design system**: must reuse existing tokens (`--color-info`, `--color-success`, `--color-warning`, `--radius-md`, `shadow-kt-md`). No new CSS variables.
- **No `NotificationBell` invented outside design system**: must follow existing icon/library (`lucide` `bell`), color tokens (`--color-error` for badge, `--color-info` for icon default).
- **No `Notification` model outside `models.py`**: model must live in `backend/app/core/database/models.py`, not a separate file.
- **No `notificationsStore` using `localStorage`**: must follow `authStore` pattern (cookie-backed pseudo, Zustand hydratation client-side, no `localStorage`).
- **No hardcoded pseudo** in frontend (`Header.tsx`): always read from `useAuthStore.getState().pseudo` / `useNotificationsStore`.
- **No WebSocket / SSE** for notifications (interdict: POC uses polling 30s, per AC line 1163 and agentic notes line 1174).
- **No pagination** on `GET /api/notifications` unless explicitly added (interdict: AC doesn't require pagination; keep it simple for POC).

## The point everything turns on

- **Transaction consistency** (agentic notes line 1175-1176): the `Notification` INSERT must share the DB transaction with the event (`Evaluation` update / `RewardLedger` insert). If the implementer uses separate transactions, a crash after the event but before the notification leaves the user uninformed. Verify by reading the service code (`services/evaluations/` or `services/rewards/`) that the notification INSERT is inside the same `with session.begin()` or `session.commit()` block.
- **Poll interval** (agentic notes line 1174): `setInterval(30000, ...)`. If interval is shorter, server load increases unnecessarily; if missing, notifications never arrive. Verify in `notificationsStore.ts` that `poll()` is called by `startPoll()` and the interval is exactly `30000`.
- **Design-system gap closure** (design-system.md lines 231, 237): if `<Toast>` or `<NotificationBell>` invents new tokens or ignores existing ones (`--color-info`, `--radius-md`, `shadow-kt-md`), the design drifts. Compare the new component files against `docs/design-system.md` tokens.

## Files touched

- `backend/app/core/database/models.py` (new `Notification` model)
- `backend/app/services/evaluations/` or `backend/app/api/evaluations/` (trigger insert)
- `backend/app/services/rewards/ledger.py` (trigger insert)
- `backend/app/api/notifications.py` (new)
- `backend/app/main.py` (router include)
- `frontend/lib/stores/notificationsStore.ts` (new)
- `frontend/components/NotificationBell.tsx` (new)
- `frontend/components/Toast.tsx` (new)
- `frontend/components/Header.tsx` (modified)
- `docs/research/s25-notifications-in-app.md` (exists)
- `docs/designs/s25-notifications-in-app.md` (exists)
- `docs/plans/s25-notifications-in-app.md` (this file)
- `docs/reviews/s25-notifications-in-app.md` (to be produced by `/ks-review`)

## Test strategy

- **Unit**: `Notification` model instantiates correctly (Pydantic-like validation via SQLAlchemy constraints not required but basic creation test). `notificationsStore` unit test with mocked `fetch` (stub `GET /api/notifications`) verifying `poll()` updates `notifications` and `unreadCount`, `markRead()` updates local state.
- **Integration (backend)**: test `GET /api/notifications` with JWT (`sub` = pseudo) returns empty list initially. After inserting `Notification` row (via DB directly or via trigger), returns the row. `POST /api/notifications/{id}/read` updates `is_read`.
- **Integration (trigger)**: simulate `Evaluation` status change to `scored` (or `RewardLedger` INSERT with `points_awarded > 0`) and verify `Notification` row exists in DB.
- **Cross-tenant isolation**: create `Notification` for `pseudo_a`; verify `GET /api/notifications` with JWT for `pseudo_b` returns empty list.
- **Idempotency**: call `POST /api/notifications/{id}/read` twice; verify second returns 200 and `is_read` stays True.
- **Frontend e2e (optional but recommended)**: Playwright test stubbing `GET /api/notifications` with `{unreadCount: 1}` verifies `NotificationBell` shows badge and `Toast` displays when poll detects new notification. If e2e is too complex for the POC, at least verify via component render in manual/visual review (see `/ks-review`).

## Definition of Done

- `docs/reviews/s25-notifications-in-app.md` exists with `Ship allowed: yes` and `Max severity: none`.
- `docs/plans/s25-notifications-in-app.md` has `validated: yes`.
- `Notification` DB model exists and is used in triggers.
- `GET /api/notifications` and `POST /api/notifications/{id}/read` endpoints exist, protected by JWT, filter by `student_pseudo`.
- `Notification` inserted in same DB transaction as `Evaluation` update and `RewardLedger` insert.
- `notificationsStore` exists with `poll()` (30s interval) and `markRead()`.
- `<NotificationBell>` and `<Toast>` components exist, use only existing design-system tokens, have typed props, and include appropriate `aria-*` attributes (`aria-live="polite"` for Toast, `aria-label` for NotificationBell).
- `Header.tsx` integrates `<NotificationBell>`.
- At least one backend test verifies notification creation on event trigger, one verifies cross-tenant isolation, one verifies read idempotency.
- Design-system gaps (`Toast`, `NotificationBell`) are confirmed addressed (components exist in `frontend/components/`); no new design-system tokens invented.
