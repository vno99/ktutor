# Research — s25-notifications-in-app

## The five structuring facts

1. **No `Notification` DB model exists** (`models.py` line 568 has `RewardLedger`, 604 `UserPoints`, 236 `Evaluation` — no `Notification`). Must be added.
2. **No notification API endpoints exist** (`backend/app/api/` has no `notifications.py`). Must be created: `GET /api/notifications?unread_only=true`, `POST /api/notifications/{id}/read`.
3. **No `notificationsStore` exists** (`frontend/lib/stores/` has `authStore`, `chatStore`, `uploadStore` — missing `notificationsStore`). Must be created.
4. **Design-system gaps confirm missing UI** (`docs/design-system.md`: `Pas de <Toast>` → s25; `Pas de <NotificationBell>` → s25). Both components must be created.
5. **Event sources (`s18` / `s20`) are verified**: `Evaluation` (line 236) and `RewardLedger` (line 568) exist. Triggers are evaluation processing (`status` change to `scored`) and points awarded (`points_awarded > 0`).

## Target story

Story `s25-notifications-in-app` (docs/stories.md line 1148, complexity 3, AC 1156-1165):
- When an `Evaluation` is processed (s18), a `Notification` row is created.
- When a `RewardLedger` entry awards points (s20), a `Notification` row is created.
- `GET /api/notifications?unread_only=true` returns user's notifications.
- `POST /api/notifications/{id}/read` marks a notification as read.
- Frontend: toast for new notifications + unread count in header.
- Polling every 30s (no WebSocket for POC).
- Tests: notification created on evaluation processing; unread count correct.

Dependencies: s18, s20 (events that trigger notifications).

## Current state of the code

- `backend/app/core/database/models.py` (worktree): `Document` (line 79), `Exercise` (127), `Attempt` (186), `Evaluation` (236), `User` (318), `ParentChildLink` (363), `Conversation` (430), `Message` (509), `RewardLedger` (568), `UserPoints` (604). No `Notification`.
- `backend/app/api/`: no `notifications.py`. Routes for `auth/`, `documents/`, `chat/`, `exercises/`, `evaluations/`, `users/` exist (verified in `.worktrees/s25-notifications/backend/app/api/`).
- `frontend/lib/stores/`: `authStore.ts`, `chatStore.ts`, `uploadStore.ts`. No `notificationsStore`.
- `frontend/components/`: `Button`, `Card`, `FileUpload`, `Header`, `Input`, `Label`, `LanguageSwitcher`, `Select`, `StreamingMessage`. No `Toast`, no `NotificationBell`.
- `docs/design-system.md`: confirms `Toast` gap (line 231) and `NotificationBell` gap (line 237) both assigned to s25.
- `docs/stories.md` agentic notes (line 1171-1177): mentions `Notification` model, `notificationsStore`, header unread count.

## Anchor points

- **DB model**: `backend/app/core/database/models.py` — add `Notification` after `UserPoints` (line 631+). Columns: `id` (UUID PK), `student_pseudo` (FK to users.pseudo, index), `type` (enum: `new_evaluation`, `points_awarded`), `message` (str), `is_read` (bool, default False), `created_at`, `related_id` (optional FK or UUID for linking to `Evaluation.id` or `RewardLedger.id`).
- **Triggers**: insert `Notification` in the same DB transaction as:
  - `Evaluation` status transition (`manual_review_needed` → `scored`) or creation (`scored`) in `backend/app/services/evaluations/` or the evaluation router.
  - `RewardLedger` INSERT (`points_awarded > 0`) in `backend/app/services/rewards/ledger.py`.
- **API routes**: `backend/app/api/notifications.py` — new router, included in `main.py`.
- **Frontend store**: `frontend/lib/stores/notificationsStore.ts` — Zustand store with `notifications`, `unreadCount`, `poll()` (30s interval), `markRead(id)`.
- **UI components**:
  - `<NotificationBell>` — header icon with unread badge (`badge` count from store).
  - `<Toast>` — inline toast (not `alert()`), shown when poll detects new unread notifications.
- **Header integration**: `frontend/components/Header.tsx` — add `<NotificationBell>` component link (or bell icon) and wire `notificationsStore` for unread count.
- **Layout**: `frontend/app/(dashboard)/eleve/layout.tsx` — mentioned in agentic notes (line 1173) as header integration point.

## Verified APIs / functions

- `backend/app/core/database/models.py`: `Evaluation` (line 236) has `student_pseudo`, `subject`, `status` (`SCORED` / `MANUAL_REVIEW_NEEDED`), `score`, `annotations`, `teacher_comments`. Confirms event trigger source.
- `backend/app/core/database/models.py`: `RewardLedger` (line 568) has `student_pseudo`, `exercise_id`, `points_awarded`, `is_success`. Confirms points trigger source.
- `docs/design-system.md`: `Pas de <Toast>` (line 231) and `Pas de <NotificationBell>` (line 237) — both gaps assigned to s25. Confirms design dependency.
- `docs/stories.md`: AC lines 1158-1165 verified at exact lines. Confirms scope.
- `backend/app/api/`: no `notifications.py` (verified by `ls` in worktree). Confirms missing endpoint file.
- `frontend/lib/stores/`: no `notificationsStore` (verified by `ls`). Confirms missing store.
- `frontend/components/`: no `Toast` or `NotificationBell` (verified by `ls`). Confirms missing components.

## Traps & constraints

- **Transaction consistency** (agentic notes line 1175-1176): the `Notification` INSERT must be in the SAME DB transaction as the event (`Evaluation` status update, `RewardLedger` INSERT). Use `session.commit()` once after both inserts. If using SQLAlchemy sessions, ensure both operations share the session.
- **Idempotency of read** (agentic notes line 1177): `POST /api/notifications/{id}/read` must return 200 (not 404 or 409) if already read. Check `is_read` before updating; return the row regardless.
- **Poll interval** (agentic notes line 1174, AC line 1163): 30s. Use `setInterval` in `notificationsStore` with cleanup on unmount (store destroy or component unmount). Avoid WebSocket.
- **Design system compliance**: use `docs/design-system.md` tokens (`--color-info` `#0284C7` for notification info, `--color-success` `#16A34A` for points, `--color-warning` `#D97706` for evaluation). No new tokens needed (info token reserved for notifications).
- **Multi-tenancy**: `Notification` model must filter by `student_pseudo` from JWT (`sub`). Endpoint queries `SELECT * FROM notifications WHERE student_pseudo = ?` (or `unread_only` filter added). Never expose another student's notifications.
- **No `NotificationBell` component exists**: must follow design-system conventions (`Header.tsx` pattern, `lucide` icon `bell` or similar, `badge` count). The component must be a new file `frontend/components/NotificationBell.tsx` (one component per file, props typed).
- **No `Toast` component exists**: must follow design-system conventions (`Card` success/warning pattern for inline feedback, but toast is floating/in-app). Can reuse `Card` styling or create minimal `Toast` with `bg-surface-subtle` + `border-info`. Must include `aria-live="polite"` (like `StreamingMessage`).
- **Dependencies**: `s18` (evaluation model/event) and `s20` (reward model/event) are prerequisites. Without them, the trigger sources don't exist.
- **Tests**: at least one cross-tenant isolation test for `/api/notifications` (a student sees only their notifications). At least one test verifying `Notification` created on `Evaluation` update (`scored`).

## Open questions

- What exact `Notification` enum values? Story AC implies `new_evaluation` and `points_awarded`. Confirm enum names (suggest: `NotificationType.NEW_EVALUATION`, `NotificationType.POINTS_AWARDED`).
- Does `Notification` link to the source row (`Evaluation.id` or `RewardLedger.id`)? Story AC doesn't specify, but agentic notes (`related_id`) suggest an optional link. Confirm at plan: include `related_id: UUID | None` and `related_type: str | None` for future linking? Or keep simple (message string only, no link)?
- Should the `Notification` include `subject`? Story AC doesn't require it. Keep minimal (message, type, is_read, created_at) to avoid over-engineering.
- Should `GET /api/notifications` support pagination? Story AC only asks for `unread_only=true`. For POC, no pagination (return all unread, or last N). Confirm at plan.
- Should `notificationsStore` use `useEffect` with interval (poll) or a custom hook (`useInterval`)? Either works; confirm pattern that matches `chatStore` (Zustand + `useEffect` with `setInterval`).

## Real complexity

Score in `docs/stories.md`: **3**. After reading code:

- **Verified 3**. No split needed. The story is well-scoped: one DB model (`Notification`), two API endpoints, two frontend components (`Toast`, `NotificationBell`), one store (`notificationsStore`), and integration with existing `Evaluation` / `RewardLedger` models. The complexity matches: DB addition (1), API endpoints (2), UI components (3), store (4), poll mechanism (5), multi-tenant isolation (6), transaction consistency (7). Fits within one cycle.
- **Not higher**: `Evaluation` and `RewardLedger` already exist; no redesign needed. `Toast` and `NotificationBell` are new components but small (single file each, props typed, no complex logic).
- **Not lower**: requires DB model, API endpoints, frontend components, store, and transaction-level trigger integration — more surface than a simple endpoint.
- **No split proposal** (not a 5).

## Split proposal

Not applicable — complexity stays at 3 after reading code. No split needed.

---

**Next step**: `/ks-plan s25-notifications-in-app` (plan from this worktree `.worktrees/s25-notifications/`).
