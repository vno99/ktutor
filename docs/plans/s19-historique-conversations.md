---
validated: yes
---
# Plan — Story s19-historique-conversations

Branch: `feature/s19-historique-conversations`
Research: `docs/research/s19-historique-conversations.md` — read it first; this plan does not repeat it.
Design: `docs/designs/s19-historique-conversations.md` (et `.html`) — read it second; the plan reuses the design-system components and never invents new ones.

## Target story

`docs/stories.md:945-974` — **s19 — Consulter l'historique de mes conversations.**

> As an élève I want consulter l'historique de mes conversations passées so that je retrouve une explication que j'ai eue.

### Acceptance criteria (verbatim)

- AC1. `GET /api/chat/history?limit=20&offset=0` (JWT auth) returns the user's past conversations, newest first.
- AC2. Each conversation includes: `id`, `subject`, `first_question`, `last_activity_at`, `message_count`.
- AC3. `GET /api/chat/history/{conversation_id}` returns the full message thread.
- AC4. The `/history` page lists the conversations and clicking one opens the detail.
- AC5. Pagination uses `limit` + `offset` (no cursor for the POC).
- AC6. A test verifies a student sees only their own conversations.
- AC7. A test verifies pagination works (limit=2 returns 2, offset=2 returns the next 2).

### Complexity

Re-scored **3** in the research (the doc lists 2). The bump reflects three things the original score missed: (a) `Conversation` and `Message` models do not exist yet — the story adds them, plus an Alembic-less schema bump via `init_db()`; (b) the stream must be wired to persist without regressing s09; (c) the RBAC matrix is 4 edges (eleve own, eleve other, parent linked, admin) not the single "student" edge named in the ACs. A score 3 fits in one cycle (≤ 10 tasks) — no split.

## Tasks (ordered)

1. [x] **T1 — Add `Conversation` and `Message` SQLAlchemy models, plus a unique index on `(student_pseudo, subject)`.**
   - In `backend/app/core/database/models.py` (after `class Evaluation`):
     - `class Conversation` (table `conversations`) :
       - `id: Mapped[uuid.UUID]` PK, `default=uuid.uuid4`.
       - `student_pseudo: Mapped[str]` `String(32)`, `ForeignKey("users.pseudo", ondelete="CASCADE")`, `nullable=False`, `index=True`.
       - `subject: Mapped[Subject]` (reuse the existing `subject_enum` from `Document`/`Exercise`).
       - `first_question: Mapped[str]` `String(2000)`, `nullable=False` (sized to fit a 2000-char question, the doc's `first_question` was unbounded `TEXT`; `String(2000)` matches `ChatStreamRequest.question`'s `max_length=2000` so we can never silently truncate the user's first message).
       - `message_count: Mapped[int]` `Integer`, `nullable=False`, `default=0` (denormalised counter, story agentic note § « Constraints »).
       - `last_activity_at: Mapped[datetime]` `DateTime(timezone=True)`, `nullable=False`, `server_default=func.now()`.
       - `created_at: Mapped[datetime]` `DateTime(timezone=True)`, `nullable=False`, `server_default=func.now()`.
       - `__table_args__ = (UniqueConstraint("student_pseudo", "subject", name="uq_conversation_student_subject"),)` — see ADR 015 § Decision 1.
     - `class Message` (table `messages`) :
       - `id: Mapped[uuid.UUID]` PK, `default=uuid.uuid4`.
       - `conversation_id: Mapped[uuid.UUID]` `ForeignKey("conversations.id", ondelete="CASCADE")`, `nullable=False`, `index=True`.
       - `role: Mapped[str]` `String(16)`, `nullable=False` — values `"user"` or `"assistant"`, enforced by a `CheckConstraint("role IN ('user','assistant')")`.
       - `content: Mapped[str]` `String(8192)`, `nullable=False` — see ADR 015 § Decision 2.
       - `sources: Mapped[list[dict] | None]` `JSON`, `nullable=True` (assistant messages only; `null` on user messages).
       - `created_at: Mapped[datetime]` `DateTime(timezone=True)`, `nullable=False`, `server_default=func.now()`.
   - **No Alembic migration** — `init_db()` (`database/session.py:56`) recreates everything via `Base.metadata.create_all`; the new tables appear at the next app start, exactly the pattern that s06, s18, s18b followed. The `Attempt` docstring (lines 175-184) is the reference for the convention.
   - **Failing tests first** (`backend/tests/core/test_models.py` — extend the s06 suite if it exists, otherwise create a new `tests/core/test_models.py` that imports `Base.metadata`):
     - `::test_conversation_table_has_expected_columns` — reads the `conversations` table metadata, asserts each named column with its type and nullability (catches typos in `mapped_column`).
     - `::test_message_table_has_expected_columns` (same shape for `messages`).
     - `::test_unique_constraint_student_subject_rejects_duplicate` — inserts two `Conversation` rows with the same `(student_pseudo, subject)` and expects `IntegrityError` (the doc's strategy of « one conversation per (eleve, subject) » is enforced at the DB level, last line of defence).

2. [x] **T2 — `ChatHistoryService` for read-side queries (no persistence yet).**
   - New file `backend/app/services/chat_history/__init__.py` and `backend/app/services/chat_history/service.py` :
     - `class ChatHistoryService` :
       - Constructor takes a `session_factory: Callable[[], Session]`.
       - `def list_conversations(self, *, student_pseudo: str, subject: Subject | None, limit: int, offset: int) -> tuple[list[Conversation], int]` — returns `(rows, total_count_for_filter)`. Subject filter is `None` for "toutes matières". `ORDER BY last_activity_at DESC, id DESC` (the `id DESC` breaks ties for stable pagination). `limit` clamped to `[1, 100]`, `offset` clamped to `[0, ∞)`; Pydantic in the router enforces the same so the service is a safety net.
       - `def get_conversation_with_messages(self, *, student_pseudo: str, conversation_id: uuid.UUID) -> tuple[Conversation, list[Message]] | None` — returns the row + the messages sorted by `created_at ASC`, or `None` if no row matches `(id == conversation_id AND student_pseudo == student_pseudo)`. **Filter is on the DB query, not in Python** — the wrong "load then check" pattern lets cross-tenant leaks through a race.
   - **Failing tests first** (`backend/tests/services/chat_history/test_service.py`):
     - `::test_list_conversations_orders_by_last_activity_desc` — seed 3 conversations with `last_activity_at` at T-2h, T-1h, T-3h, assert order is T-1h, T-2h, T-3h, then a 4th row with the same `last_activity_at` as T-1h but a smaller `id` (created second) → confirms `id DESC` tie-breaker.
     - `::test_list_conversations_filter_by_subject` — seed 2 maths + 1 francais, ask subject=maths → 2 rows; ask subject=francais → 1 row; ask subject=None → 3 rows.
     - `::test_list_conversations_paginates_with_limit_and_offset` — seed 5 rows, `limit=2 offset=0` returns 2, `limit=2 offset=2` returns the next 2, `limit=2 offset=4` returns 1. **This is AC7** (the doc demanded a test that exercises `offset=2`).
     - `::test_get_conversation_returns_none_for_other_student` — seed alice's conversation; query with `student_pseudo="bob"` → `None` (the read-side defence; the router layer has a second gate, but the service is the closest-testable layer).
     - `::test_get_conversation_returns_messages_in_chronological_order` — seed a conversation with 4 messages out of order, assert return is by `created_at ASC`.

3. [x] **T3 — New router `backend/app/api/chat/history.py` with two endpoints.**
   - `prefix = "/api/chat"` (so the paths are `/api/chat/history` and `/api/chat/history/{conversation_id}`). **No new top-level include_router needed** — see the run interdicts, the existing `chat_router` will be re-exported to include the history sub-router. The `chat/__init__.py` is updated to expose both routers.
   - `GET /api/chat/history` :
     - Query: `limit: int = 20`, `offset: int = 0`, `subject: Literal["maths","francais"] | None = None`. Validated by FastAPI (Pydantic), 422 on bad input.
     - `user: User = Depends(get_current_user)` (401 otherwise).
     - **RBAC gate** : `role in {ELEVE, PARENT, ADMIN}` (all three can call; the cross-tenant filter is `student_pseudo == user.pseudo` for the first two, bypass for `ADMIN` — see T4).
     - Calls `ChatHistoryService.list_conversations(student_pseudo=..., subject=..., limit=..., offset=...)`.
     - Returns `HistoryListResponse { items: list[ConversationListItem], total: int, limit: int, offset: int }`. `total` is the count *for the filter* (a pagination total, not a global count) so the client can render "page X of Y".
   - `GET /api/chat/history/{conversation_id}` :
     - Path: `conversation_id: uuid.UUID`. Pydantic coerces the string, 422 on malformed.
     - `user: User = Depends(get_current_user)`.
     - **RBAC gate** : ELEVE or PARENT or ADMIN; the cross-tenant bite lives in T4.
     - Calls `ChatHistoryService.get_conversation_with_messages(...)`. **404 `not_found`** if `None`, **200** with `ConversationDetail { ..., messages: list[MessageItem] }` otherwise.
   - Schemas in `backend/app/api/chat/history_schemas.py` (new file) :
     - `ConversationListItem { id: UUID, subject: Subject, first_question: str, last_activity_at: datetime, message_count: int }`.
     - `MessageItem { id: UUID, role: Literal["user","assistant"], content: str, sources: list[SourceCitation] | None, created_at: datetime }` — `sources` mirrors the existing `SourceCitation` (`filename`, `chunk_index`).
     - `HistoryListResponse { items: list[ConversationListItem], total: int, limit: int, offset: int }`.
     - `ConversationDetail { id, subject, first_question, last_activity_at, message_count, messages: list[MessageItem] }`.
     - `NotFoundResponse { error: str, code: Literal["not_found"] }` — mirrors the s18b convention.
   - **`history.py` is a sibling of `router.py`, NOT a split** — same justification as s18b (the repo's "one router per sub-domain" rule still holds, `chat` is the sub-domain, `history` is a sub-feature inside it). The agentic note that names the file `backend/app/api/chat/history.py` is honored verbatim.
   - **Failing tests first** (`backend/tests/api/test_chat_history.py`, new file) :
     - `::test_list_history_returns_401_without_bearer`.
     - `::test_list_history_returns_200_with_default_pagination` (AC1) — seed 3 conversations for alice; expect `items` of length 3, `limit=20`, `offset=0`, `total=3`, sorted by `last_activity_at DESC`.
     - `::test_list_history_item_shape` (AC2) — assert the JSON keys are exactly `{id, subject, first_question, last_activity_at, message_count}` (the Pydantic `model_dump` will surface any extra field).
     - `::test_list_history_paginates_with_limit_and_offset` (AC7) — seed 5 conversations, hit with `?limit=2&offset=0` then `?limit=2&offset=2`; assert disjoint sets of ids, correct `total` (`5`).
     - `::test_list_history_filters_by_subject` — seed 2 maths + 1 francais, `?subject=maths` → 2 items.
     - `::test_get_history_returns_full_thread` (AC3) — seed 1 conversation with 4 messages (2 user + 2 assistant), GET by id, assert all 4 messages in `created_at` order, `role` enum respected, `sources` on assistant messages.
     - `::test_get_history_returns_404_for_unknown_id` (AC3 negative) — GET `/api/chat/history/{random_uuid}` → 404 + `code: "not_found"`.
     - `::test_get_history_returns_404_for_other_student_conversation` (AC6 read side, see T4 for the cross-tenant bite).

4. [x] **T4 — RBAC strict + 4-edge cross-tenant bite (AC6 + AGENTS.md DoD).**
   - The router's RBAC is the load-bearing part. **Do not call `require_role`** (which would block `eleve`, the primary user). The contract is:
     - `ELEVE` : only sees `student_pseudo == user.pseudo`.
     - `PARENT` : only sees a `student_pseudo` they are linked to via `ParentChildLink` (the same `assert_parent_linked_to_child_or_403` helper used by s18b on the `score-manual` endpoint).
     - `ADMIN` : bypass (ADR 005 § RBAC).
   - For the list endpoint, the helper is called **with `user.pseudo` as the `claimed` arg** (`assert_jwt_pseudo_matches_or_403` for `ELEVE`/non-parent-with-no-link; `assert_parent_linked_to_child_or_403` is N/A here because the parent is querying for *themselves* — the linked children are surfaced via the parent-dashboard endpoint, not via the student's history. So **the list endpoint only ever returns the caller's own conversations; parents do NOT browse their child's history through this endpoint** — that surface is out of scope for s19, flagged as a follow-up in the ADR 015 § Decision 3.). Admin impersonation on the list endpoint returns all conversations (no `student_pseudo` filter).
   - For the detail endpoint, the contract is : `ELEVE` → 404 if the conversation's `student_pseudo != user.pseudo`; `PARENT` → 404 unless the conversation's `student_pseudo` is in the parent's `ParentChildLink` set; `ADMIN` → 200.
   - **Failing tests first** (same file, four edges) :
     - `::test_list_history_other_eleve_sees_only_own_conversations` (AC6) — seed alice with 2 convs and bob with 1; alice's token → 2 items, bob's token → 1 item. A regression that lets alice's filter through (`"student_pseudo = body.pseudo"` after s15) breaks this.
     - `::test_get_history_other_eleve_gets_404` — alice's token + bob's conversation id → 404 + `code: "not_found"` (the same 404 as "unknown id" so we don't leak the existence of the row to a cross-tenant attacker).
     - `::test_get_history_linked_parent_succeeds` — alice + parent + link; parent's token + alice's conversation id → 200.
     - `::test_get_history_unlinked_parent_gets_404` — alice + parent (no link) + bob; parent's token + bob's conversation id → 404.
     - `::test_get_history_admin_succeeds_for_any_student` — admin token + alice's conversation id → 200 (admin impersonation per ADR 005).
     - `::test_list_history_admin_sees_all` — admin token → returns alice's and bob's items (no `student_pseudo` filter).

5. [x] **T5 — Wire stream-side persistence in `stream_chat` (s09) without regression.**
   - In `backend/app/api/chat/router.py` :
     - Add a `Depends(get_db)` parameter to `stream_chat`. Import `ChatHistoryService` from `app.services.chat_history.service`.
     - Inside `event_generator`, accumulate `full_response: list[str]` and `final_sources: list[SourceCitation] | None` as the events stream past (`event.event == "token"` → append `event.content`; `event.event == "done"` → snapshot `event.sources`).
     - **Persistance AFTER the loop closes**, in a `try/finally` (the `finally` runs even if the client disconnects mid-stream, which is the "best-effort" branch — see ADR 015 § Decision 4). Strategy :
       1. Re-use an existing `Conversation` for `(student_pseudo, subject)` (the `UNIQUE` constraint from T1 guarantees at most one row). If absent, `INSERT` a new one with `first_question = body.question`, `message_count = 2`, `last_activity_at = func.now()`.
       2. `INSERT` the user `Message` (role=`"user"`, `content = body.question`, `sources = None`).
       3. `INSERT` the assistant `Message` (role=`"assistant"`, `content = "".join(full_response)`, `sources = [s.model_dump() for s in final_sources or []]`).
       4. If the conversation was new, we're done. If it already existed, `UPDATE conversations SET message_count = message_count + 2, last_activity_at = func.now() WHERE id = ...`.
     - **The persistence is opt-in via an env flag** : `CHAT_PERSIST_HISTORY` (default `true`). The s09 test suite sets it to `false` via a fixture-level monkeypatch so the existing `test_chat_stream.py` (3-token, done-event, cross-tenant, error event, etc.) keeps passing with **zero** DB writes — a regression in the persistence path that fires during a stream is caught by T6's test, not by re-running the s09 suite. The flag is an internal implementation knob, not a product feature (the ADR 015 § Decision 4 records why).
     - The DB writes happen on a SEPARATE `Session` (the `get_db` factory, opened **after** the `async for` loop yields its last `done` event) so the streaming connection is not held by the DB transaction.
   - **Failing tests first** (`tests/api/test_chat_stream.py` — extend, do not duplicate fixtures) :
     - `::test_stream_persists_user_and_assistant_messages` — happy path; assert the new `Conversation` row and the 2 `Message` rows after the stream ends, with `first_question == "2+2 ?"`, `message_count == 2`, assistant message carries the stub's `sources`.
     - `::test_stream_aggregates_assistant_content_from_tokens` — assert the assistant message's `content` is the concatenation `"Hel" + "lo " + "world"` (the stub returns these three tokens). A regression that persisted only the last token (or nothing) breaks this.
     - `::test_stream_persists_reuses_existing_conversation` — call `/api/chat/stream` twice for the same `(student, subject)`; assert ONE `Conversation` row with `message_count == 4` (the second call's `+2`).
     - `::test_stream_persists_with_persist_flag_off_does_not_write` — set `CHAT_PERSIST_HISTORY=false`; call the stream; assert no new `Conversation` / `Message` rows. Confirms the s09 happy path stays a no-op on the DB.
     - `::test_stream_persists_error_event_does_not_write_assistant_message` — the stub raises a `ValueError("Unknown subject")`; the stream emits the error event and closes; assert NO `Conversation` row, NO `Message` row. The user message also stays out (the user never saw a response, the conversation was never started). **This is the bite on ADR 015 § Decision 4 (best-effort, no half-written row).**

6. [x] **T6 — Register the new router in `main.py` and the chat package's `__init__.py`.**
   - `backend/app/api/chat/__init__.py` : expose both `chat_router` and a new `chat_history_router`. The current `chat/__init__.py` is a docstring-only file; the export is added at the bottom.
   - `backend/app/main.py` : `app.include_router(chat_history_router)` after the existing `app.include_router(chat_router)`. No new top-level prefix.
   - **Failing test** : `tests/api/test_chat_history.py::test_history_endpoints_are_mounted` — the absence of this test is what allows a missed `include_router` to ship; the new file's first test is an end-to-end `GET /api/chat/history?limit=20&offset=0` against the live `app` instance, which fails with 404 if the router was not mounted.

7. [x] **T7 — Frontend: `lib/api/history.ts` + types + the two pages.**
   - `frontend/lib/api/history.ts` (new file, mirrors `chat.ts`'s style) :
     - `export type ConversationListItem { id: string; subject: 'maths' | 'francais'; first_question: string; last_activity_at: string; message_count: number; }`.
     - `export type MessageItem { id: string; role: 'user' | 'assistant'; content: string; sources: SourceCitation[] | null; created_at: string; }` — `SourceCitation` is re-imported from `./chat`.
     - `export type HistoryListResponse { items: ConversationListItem[]; total: number; limit: number; offset: number; }`.
     - `export type ConversationDetail = ConversationListItem & { messages: MessageItem[]; }`.
     - `export async function fetchHistory({ limit, offset, subject }: { limit?: number; offset?: number; subject?: 'maths' | 'francais' | null; }): Promise<HistoryListResponse>` — uses `apiClient.get('/api/chat/history', { params: { limit, offset, subject } })`. The `apiClient` interceptor adds the JWT bearer (s15); no `pseudo` is read from the cookie or the URL.
     - `export async function fetchConversation(id: string): Promise<ConversationDetail>` — `apiClient.get('/api/chat/history/${id}')`.
     - `export class HistoryError extends Error { code: 'network' | 'http' | 'unknown' }` — mirrors the chat-side error shape so the page can branch on `code`.
   - `frontend/app/(dashboard)/[locale]/history/page.tsx` (new) — server entry, mirrors `dashboard/eleve/page.tsx`:
     - `export const dynamic = 'force-dynamic'`.
     - `generateMetadata` → `t('history.title')`.
     - Renders `<HistoryListClient />` (the actual UI is a client component because it consumes the store and reads `next/navigation` for the pagination state).
   - `frontend/app/(dashboard)/[locale]/history/[conversation_id]/page.tsx` (new) — server entry, mirrors `dashboard/parent/[child_pseudo]/page.tsx`:
     - `generateMetadata` → `t('history.detailTitle')`.
     - Renders `<HistoryDetailClient conversationId={...} />`.
   - `HistoryListClient.tsx` (new, in the same folder) :
     - Reads `useTranslations('history')` for all strings (NO hardcoded text per the design system + AGENTS.md i18n rule).
     - Fetches on mount and on `[subject, offset]` change via `useEffect`.
     - 4 states (per `docs/designs/s19-historique-conversations.md` § States) : loading (`aria-busy="true"` on `<ul>`, no skeleton per design system), empty (centered card + CTA to `/chat`), error (inline card with `Réessayer`), pagination (Précédent / Suivant, `aria-disabled` at the ends).
     - Renders cards from `<Card>` (already in `components/Card.tsx`); each card is an `<a>` (the design uses a real `<a>` for the full-card link, mirroring the s11c upload card pattern).
     - Uses `useRelativeTime` — a NEW helper in `frontend/lib/intl/relativeTime.ts`. ADR 015 § Decision 5 records why we don't add a `<RelativeTime>` component yet (it's a 10-line helper, defer to s22 if 3+ stories need it).
   - `HistoryDetailClient.tsx` (new, same folder) :
     - `useTranslations('history')` + `useLocale()` for the date formatter (the design spec uses `Intl.RelativeTimeFormat(locale, { numeric: 'auto' })`).
     - Fetches via `fetchConversation(id)`. 4 states (loading, not-found, error, success). The not-found state shows a `<Card>` with the `history.notFound` string + a back button.
     - Renders the thread as a list of message bubbles: user = right-aligned `bg-surface-subtle`, assistant = left-aligned with `border-l-4 border-primary` (per the design `.html` mockup).
     - Sources are listed as `<span class="source-pill">` with a `file-text` Lucide icon + `filename:chunk_index` (the design pattern; link is `href="#"`, the click afford is reserved for s22 where the document viewer lives).
   - **Pure presentational tasks** (no failing-test naming) : the two pages + the two client components. Visual verification at 360px and 768px via Playwright e2e (T8). `ruff check` and `tsc --noEmit` must stay green.
   - **Header / tab bar** : the design calls for a "history" entry in the bottom tab bar (the design system gap #3 in `docs/designs/s19-historique-conversations.md`). Quick investigation in T7: open the bottom tab bar component (the one referenced by the `(public)/[locale]/layout.tsx` and the `DashboardShell`); if it already accepts an arbitrary list of entries, add a 5th (`/history`, Lucide `clock` icon, label `Historique`); if it is hardcoded to 4, the implementation adds the entry inline with a one-line change. **No new shared component** — a tab-bar refactor is out of scope for s19 and belongs to a dedicated a11y/UX pass (s22).

8. [x] **T8 — i18n catalogues + Playwright e2e + a11y scans.**
   - `frontend/messages/fr.json` and `frontend/messages/en.json` :
     - New namespace `history` with the keys used by the pages : `title`, `detailTitle`, `empty`, `emptyCta`, `filterAllSubjects`, `filterMaths`, `filterFrancais`, `previous`, `next`, `metaCount` ("{count} messages"), `metaDate` is handled by the formatter (not in the catalogue), `loading`, `errorTitle`, `errorBody`, `retry`, `notFound`, `back`, `roleYou` ("Toi"), `roleAssistant` ("ktutor · {subject}"), `sourcesLabel` ("Sources :"), `paginationLabel` ("Pagination").
   - `frontend/scripts/check-i18n.sh` must exit 0 (CI gate).
   - `frontend/e2e/history.spec.ts` (new, mirrors `dashboard.spec.ts`):
     - Stub the `GET /api/chat/history` response with a 3-conversation payload via `page.route` (the s11b pattern).
     - **(a)** Renders the 3 cards, with the right subject pill colour (maths vs francais), the `first_question` line, and the meta line. (AC4)
     - **(b)** Empty state when the stub returns `{ items: [], total: 0 }`. The CTA links to `/chat`.
     - **(c)** Pagination — stub returns `total: 5` and 2 items, the "Suivant" button navigates to `?offset=2` and the URL updates (AC5).
     - **(d)** Click a card → URL becomes `/{locale}/history/{id}`, the detail page renders the user/assistant messages in order, with the source pills. (AC4)
     - **(e)** Not-found — stub returns 404, the page renders `history.notFound` + back button. (AC3 negative)
     - **(a11y fr / en)** axe-core on `/{locale}/history` and `/{locale}/history/{stubbed_id}` — 0 critical / 0 serious. (AGENTS.md DoD § A11y)

9. [x] **T9 — ADR 015 + final commit.**
   - `docs/decisions/015-chat-history-conversation-granularity-and-storage.md` (MADR format) records:
     - **Decision 1** : `Conversation` is keyed by `(student_pseudo, subject)` — UNIQUE constraint enforces "one conversation per (eleve, subject)" at the DB level. Considered alternatives (B: per-day grouping, C: per-session-id from the client) rejected because (a) the story's AC2 is singular (`first_question`, `message_count`); (b) per-day creates an arbitrary cut at midnight UTC; (c) per-session is a UI-controlled parameter, not in the ACs. The research open question 1 recommended (A) — this ADR is the formalisation.
     - **Decision 2** : `Message.content` is `String(8192)`, not `Text` nor the doc's `TEXT`. The `String(8192)` matches the codebase convention (`Document.filename=512`, `Evaluation.teacher_comments=8192`); the port-SQLite constraint in `architecture.md:230-233` forbids unbounded `TEXT` for this codebase; an 8KB cap is enough for the POC. The "no silent truncation" is enforced by `ChatStreamRequest.question`'s `max_length=2000` (already in place) and a future LLM-output cap (out of s19 scope — flagged as a follow-up).
     - **Decision 3** : the history endpoints filter on `student_pseudo == user.pseudo` (eleve) or `student_pseudo in linked_children` (parent). **The list endpoint does not surface a parent's linked children's history** — that is a separate product surface (parent dashboard detail, s17 already shows the per-child summary, the per-child *history* is a follow-up). The story's AC6 names "a student sees only their own" — the parent edge is the AGENTS.md DoD's cross-tenant bite, not a new feature.
     - **Decision 4** : stream-side persistence is best-effort and lives in a `try/finally` AFTER the `async for` loop closes. The persistence is gated by `CHAT_PERSIST_HISTORY` (default `true`) so the s09 test suite (3-token stub) stays a no-op on the DB. An error event from the agent writes nothing — the user message is not persisted either, because the user never saw a response. The flag is an internal knob, not a product feature.
     - **Decision 5** : a 10-line `formatRelativeTime(locale, value)` helper lives in `frontend/lib/intl/relativeTime.ts`; the `<RelativeTime>` component is **not** added (design system gap #2). If 3+ stories need it after s22, a component is extracted at that point.
     - Each decision records the considered alternatives with the reason they were rejected (2+ per decision).
   - **One single commit** at the end of the story (cf. `ks-execute` contract: never one commit per task). Conventional-commit title : `feat: add chat history (s19)`. The commit carries the story docs (`research/`, `designs/`, `plans/`, `decisions/015-…`) and every task.

## Run interdicts

- **Do NOT add a new Alembic migration.** `init_db()` recreates the schema in dev/CI; the `Attempt` and `Evaluation` docstrings document the convention. SQLAlchemy `Base.metadata.create_all` is the single source of truth for the schema in this codebase.
- **Do NOT add a per-`subject` `Conversation` flag other than the `UNIQUE(student_pseudo, subject)` constraint.** Strategy A from the research is the only path that fits the story's AC2; the other two are explicitly rejected in ADR 015.
- **Do NOT cross-load the conversation row in Python and then check `student_pseudo` in the router.** The filter MUST be in the SQL query (`WHERE student_pseudo = :pseudo AND id = :id`). A "load then check" pattern leaks via a race when the conversation is deleted between the load and the check.
- **Do NOT return 403 for cross-tenant detail access.** The detail endpoint returns 404 + `code: "not_found"` so a cross-tenant attacker cannot distinguish "exists but not yours" from "doesn't exist". 403 is reserved for role mismatches (e.g. an `eleve` calling a parent-only endpoint).
- **Do NOT add a `GET /api/chat/history/{id}/messages` sub-endpoint.** The detail endpoint returns the conversation + the messages in one shot (AC3: "the full message thread"). Splitting it forces the client to do two round trips for no gain.
- **Do NOT edit the `subject` filter to support `None` as a special value other than "all subjects".** A `?subject=invalid` returns 422 from the Pydantic literal type; the absence of the param is the "all" case. Don't invent a "subject=null" string.
- **Do NOT add a `<RelativeTime>` component.** Inline `formatRelativeTime` helper in `lib/intl/relativeTime.ts` only (ADR 015 § Decision 5).
- **Do NOT add a `GET /api/chat/history/{id}/sources` sub-endpoint.** The sources ride on the `MessageItem.sources` field; the design's source pills are a list of links, not a navigation surface (s22 will add the document viewer).
- **Do NOT add a `parent` bypass to the list endpoint.** Parents do NOT browse their child's history through `GET /api/chat/history` — they go through the parent dashboard's per-child detail (out of s19 scope, flagged in ADR 015 § Decision 3).
- **Do NOT log the JWT, the bearer, the request body, the `first_question` content, or any message text in the new endpoints.** The audit log line carries `caller`, `conversation_id`, `action` (`read_list` | `read_detail`); the AGENTS.md § Backend logging rules apply unchanged.
- **Do NOT edit `docs/stories.md`.** The ACs are preserved as-is; any drift is in the research + ADR.
- **Do NOT modify `subject` to a non-`Enum` column.** The codebase uses SQLAlchemy `Enum(Subject, native_enum=False)` (lines 89-92 of `models.py`); `Conversation.subject` follows the same pattern for parity.
- **Do NOT add a `<Skeleton>` loader.** The design system § States says "no skeleton (skeleton loaders are a s22 gap)". `aria-busy="true"` on the `<ul>` is the loading afford.

## The point everything turns on

The single decision this plan stands on is **stream-side persistence without regressing s09** (T5). The plan hesitated the most here. The wrong alternatives, and how to spot them:

- **Persisting inside the `async for` loop** (after every token) → would couple the streaming latency to the DB write latency. The wrong alternative is detected by a benchmark: a happy-path stream that previously took ~10ms per token suddenly takes 50ms. No test catches this today, but a future perf test in s22 would.
- **Persisting before the stream is fully drained** (after the user message is read but before the assistant is done) → leaks half-written `Conversation` rows when the client disconnects. The right alternative is the `try/finally` AFTER the `async for` loop. The bite test is `::test_stream_persists_error_event_does_not_write_assistant_message` : a `ValueError` mid-stream must leave no row.
- **Re-using the same `Session` for the streaming and the persistence** → holds a DB transaction open for the duration of the stream, exhausting the connection pool under load. The right alternative is a SECOND `Session` opened in the `finally`. The bite test is implicit: 100 concurrent streams under the existing `chat_stream_max_chunks=200` cap should not deadlock the pool — this is not directly testable, so the interdict "no shared session" is the guardrail.
- **Letting the `CHAT_PERSIST_HISTORY=false` flag become a public feature** → it is an internal knob for s09's test suite. The ADR 015 § Decision 4 records why; a reviewer should ask "is the env var documented in the user-facing env reference?" The answer must be **no** — only the operator-facing `.env.example` mentions it with a "test only" comment.

The secondary decision is the **4-edge RBAC matrix** (T4). The risk is the parent branch: a regression that calls `assert_jwt_pseudo_matches_or_403` for the parent (instead of `assert_parent_linked_to_child_or_403`) blocks every parent — a real product bug. The bite is `::test_get_history_unlinked_parent_gets_404` : a parent calling for a non-linked child must get 404, not 403, not 500.

## Files touched

**Created** :
- `backend/app/services/chat_history/__init__.py` (T2).
- `backend/app/services/chat_history/service.py` (T2).
- `backend/app/api/chat/history.py` (T3).
- `backend/app/api/chat/history_schemas.py` (T3).
- `backend/tests/api/test_chat_history.py` (T3 + T4 + T6).
- `backend/tests/services/chat_history/__init__.py` (T2).
- `backend/tests/services/chat_history/test_service.py` (T2).
- `backend/tests/core/test_models.py` if absent (T1).
- `frontend/lib/api/history.ts` (T7).
- `frontend/lib/intl/relativeTime.ts` (T7 + ADR 015 § Decision 5).
- `frontend/app/(dashboard)/[locale]/history/page.tsx` (T7).
- `frontend/app/(dashboard)/[locale]/history/HistoryListClient.tsx` (T7).
- `frontend/app/(dashboard)/[locale]/history/[conversation_id]/page.tsx` (T7).
- `frontend/app/(dashboard)/[locale]/history/[conversation_id]/HistoryDetailClient.tsx` (T7).
- `frontend/e2e/history.spec.ts` (T8).
- `docs/decisions/015-chat-history-conversation-granularity-and-storage.md` (T9).

**Modified** :
- `backend/app/core/database/models.py` — add `Conversation` + `Message` (T1).
- `backend/app/api/chat/router.py` — add the `try/finally` persistence block in `event_generator` (T5).
- `backend/app/api/chat/__init__.py` — export `chat_history_router` (T6).
- `backend/app/main.py` — `app.include_router(chat_history_router)` (T6).
- `backend/tests/api/test_chat_stream.py` — extend with T5's 5 persistence tests.
- `frontend/messages/fr.json` + `frontend/messages/en.json` — add the `history` namespace (T8).
- `frontend/components/Header.tsx` — if a 5th bottom-tab-bar entry is needed, the one-line addition lives here (T7 quick fix; if a refactor is required, T7 is escalated to a "blocked — needs a tab-bar refactor story" status, the implementer MUST NOT invent a new component).

**Unchanged** (verified by `git diff main...feature/s19-historique-conversations`) :
- `backend/app/api/chat/sse.py` (the SSE wire format is unchanged).
- `backend/app/services/agents/*` (the supervisor / agents are not touched — persistence consumes the same `StreamChunk` events).
- `backend/app/core/auth/middleware.py` (the helpers exist already; the new router calls them, does not modify them).
- `frontend/lib/api.ts`, `frontend/lib/stores/authStore.ts`, `frontend/lib/stores/chatStore.ts` (no JWT / streaming logic changes).
- `docs/stories.md` (per the research override pattern).

## Test strategy

| Layer | Tests | Where | What they prove |
| --- | --- | --- | --- |
| DB model | 3 (T1) | `tests/core/test_models.py` | `Conversation` / `Message` columns + `UNIQUE(student_pseudo, subject)` constraint. |
| Service unit | 5 (T2) | `tests/services/chat_history/test_service.py` | Read-side queries: ordering, subject filter, pagination, cross-tenant filter, chronological message order. |
| API integration | 13 (T3 + T4 + T6) | `tests/api/test_chat_history.py` | 401 without bearer, AC1 / AC2 / AC3 / AC5 / AC6 / AC7 bit-tests, 404 for unknown + cross-tenant, RBAC 4 edges, router mounted. |
| Stream regression | 5 (T5) | `tests/api/test_chat_stream.py` (extended) | Persistence on happy path, content aggregation, re-use of existing conversation, `CHAT_PERSIST_HISTORY=false` no-op, error event writes nothing. |
| Frontend e2e | 7 (T8) | `frontend/e2e/history.spec.ts` | AC4 (list + click), empty, pagination, detail page, not-found, a11y × 2 locales. |
| i18n | 1 (T8) | `frontend/scripts/check-i18n.sh` | No hardcoded strings. |
| Lint | 1 (T9) | `ruff check backend/ tests/` + `tsc --noEmit` in `frontend/` | No regressions. |

**Total new tests** : 35 (3 + 5 + 13 + 5 + 7 + 1 + 1). The 5 s09 stream tests are added to the existing `test_chat_stream.py` file (no duplication of fixtures; the existing `seeded_eleve_alice`, `maths_stub`, `jwt_client` are reused).

**Bite-defence tests** (intentionally called out in the plan, not in the AC list) :
- T4's 6 RBAC tests (the 4 edges × 2 endpoints) are the four-corners truth table. A regression that flips one row is caught.
- T5's `::test_stream_persists_error_event_does_not_write_assistant_message` is the bite on ADR 015 § Decision 4.
- T1's `::test_unique_constraint_student_subject_rejects_duplicate` is the bite on the "one conversation per (eleve, subject)" invariant.
- T2's `::test_get_conversation_returns_none_for_other_student` is the service-side defence (the router has a second gate).
- T8's `axe-core` scans on both pages and both locales are the bite on the design system's WCAG 2.1 A claim.

**Test independence** : the API tests don't share `Conversation` / `Message` rows across tests (each test seeds its own rows in its own `session_factory` block). The stream-persistence tests reuse the existing s09 fixtures (a new `monkeypatch` on `CHAT_PERSIST_HISTORY` per test, not a session-scoped fixture).

**Cross-tenant bite** : `::test_list_history_other_eleve_sees_only_own_conversations` (AC6) + `::test_get_history_other_eleve_gets_404` (T4 second edge) cover the read side; the write side is the stream's persistence on the JWT `pseudo` (a regression that hard-codes `"alice"` is caught by `test_stream_persists_*_for_bob` which is added in T5 if the existing `seeded_eleve_bob` fixture is missing — otherwise it is folded into the existing happy-path test).

## Definition of Done

- One PR opened from `feature/s19-historique-conversations` to `main`. Conventional-commit title `feat: add chat history (s19)`. Body carries the AC table (AC1-AC7) with each one ticked, the research summary, the design links, the ADR pointer, and the review verdict (placeholder — filled in by the review).
- `pytest backend/tests` green (full suite, no regression on s09, s15, s17, s18, s18b; the existing baseline noted in the s18b review holds).
- `ruff check backend/ tests/` clean.
- `cd frontend && pnpm tsc --noEmit` clean.
- `cd frontend && pnpm exec playwright test e2e/history.spec.ts` green (or `pnpm test` if the runner is unified).
- `frontend/scripts/check-i18n.sh` exits 0.
- `git diff main...feature/s19-historique-conversations` shows touches only in the files listed above. No collateral damage in `models.py`'s `Document` / `Exercise` / `Attempt` / `Evaluation` / `User` / `ParentChildLink` definitions, in `subjects.py` / `jwt.py` / `passwords.py` (auth core), in `agents/*`, in the existing `chat/router.py`'s `event_generator` (T5 only appends, the streaming behaviour is unchanged), or in `docs/stories.md`.
- A passing review (no critical findings) per AGENTS.md § Gate.
- No code on `main` directly — the PR is the only delivery vehicle (manual ship mode, AGENTS.md § Stratégie de ship).
