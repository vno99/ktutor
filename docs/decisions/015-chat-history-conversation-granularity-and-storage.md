# ADR 015 — Chat history : granularity, storage, RBAC matrix, persistence strategy, relative-time helper

- Status: accepted
- Date: 2026-09-05
- Scope: story s19-historique-conversations
- Supersedes: none

## Context

Story s19 (chat history) adds two read-only endpoints under `/api/chat` and
stream-side persistence of the user + assistant messages to PostgreSQL. The
plan (`docs/plans/s19-historique-conversations.md`) lists five decisions the
story has to take and freeze. They are independent in the implementation but
they share the same cross-cutting concerns: storage cost, RBAC surface, and
UX consistency. This ADR records the chosen paths and the rejected
alternatives, with the research's verified facts cited in each section.

The five decisions:

1. **Conversation granularity** — one `Conversation` row per (eleve, subject),
   or per-day, or per-session?
2. **Message content column width** — `Text` (unbounded), `String(N)` (fixed),
   or `JSON`?
3. **RBAC surface of the two history endpoints** — does the parent see a
   linked child's history through `GET /api/chat/history`, or only the
   child themselves?
4. **Stream-side persistence lifecycle** — when, where, and how is the
   user + assistant message written to the DB?
5. **Relative-time UX helper** — new shared `<RelativeTime>` component, or a
   10-line inline helper?

## Decision

### Decision 1 — One `Conversation` per `(student_pseudo, subject)`

The `Conversation` model has a `UNIQUE(student_pseudo, subject)` constraint
at the DB level (T1). The persistence path re-uses an existing row if one
exists; otherwise it `INSERT`s a new one. The list endpoint returns the
caller's conversation rows (one per subject the caller has chatted about),
ordered by `last_activity_at DESC, id DESC`.

**Considered alternatives**:

- **B. Per-day grouping** — rejected. The story's AC2 is `first_question`
  and `message_count` (singular). A per-day cut creates an arbitrary
  midnight-UTC boundary that does not match the UX intent (a continuous
  "session" with a teacher). It also multiplies the row count with no
  product gain.
- **C. Per-session-id from the client** — rejected. The session id would
  be a UI-controlled parameter not in any AC. The backend would have to
  trust the client, and the story's tests (`test_chat_stream.py`) do not
  seed a session id. The UNIQUE constraint is also a natural "at most
  one row per (eleve, subject)" invariant the research open question 1
  recommended as strategy A.

### Decision 2 — `Message.content` is `String(8192)`

The `Message.content` column is `String(8192)` (not `Text`, not `JSON`).
The 8KB cap matches the codebase convention (`Evaluation.teacher_comments=8192`,
`Document.filename=512`). The architecture's port-SQLite constraint
(`docs/architecture.md:230-233`) forbids unbounded `TEXT` for this codebase
because the SQLite CI engine does not enforce a length and a runaway LLM
output would fill the disk. The upstream guard is `ChatStreamRequest.question`
`max_length=2000` (s09, frozen). A future LLM-output cap is flagged as a
follow-up (out of s19 scope — the assistant message is built from the
streamed tokens, which the LLM provider already constrains).

**Considered alternatives**:

- **B. `Text` (unbounded)** — rejected. Violates the port-SQLite constraint
  documented in `architecture.md:230-233`. The codebase's CI runs against
  SQLite via the `DATABASE_URL=sqlite:///:memory:` shim; a `Text` column
  is silently truncated on SQLite and accepted on PostgreSQL — a
  classic two-engine trap.
- **C. `JSON` with structured `blocks` array** — rejected. The streamed
  output is plain text; structuring it as JSON would force the agent to
  emit well-formed JSON tokens, which the LLM provider does not guarantee.
  The current `{role, content, sources}` shape is enough for the read
  endpoint and the design's message bubbles.

### Decision 3 — Parent does NOT see a linked child's history through `GET /api/chat/history`

The list endpoint applies the same `student_pseudo == user.pseudo` filter
for both `ELEVE` and `PARENT`. A parent who calls `GET /api/chat/history`
sees their own (typically empty) history, the same way an eleve with no
conversation sees an empty list. The detail endpoint allows a parent to
read a linked child's conversation (`assert_parent_linked_to_child_or_403`),
but the *list* endpoint does not surface a parent's linked children — that
is a separate product surface (the parent dashboard per-child detail, s17,
which already shows the per-child summary; the per-child *history* is a
follow-up). The story's AC6 names "a student sees only their own" — the
parent edge is the AGENTS.md DoD's cross-tenant bite, not a new feature.

**Considered alternatives**:

- **B. Parent sees a flat list of all linked children's conversations**
  (interleaved by `last_activity_at`) — rejected. The story's scope is
  "the student sees their own history". The parent dashboard is a
  separate surface that already aggregates per-child summaries. Adding
  a flat list on `GET /api/chat/history` would duplicate the
  dashboard's per-child view, fragment the RBAC story (the same URL
  has a different meaning for eleve vs parent), and break the
  "list endpoint" branch of the AGENTS.md DoD (a parent expects their
  own history, not their children's).
- **C. A separate `GET /api/chat/history?child=<pseudo>` parameter**
  (admin or parent) — rejected for s19 (out of scope). The dashboard
  already passes `?pseudo=` for the eleve dashboard read-only view
  (s17, plan § Cross-tenant rules), so a parallel history filter
  would be a one-line follow-up — flagged as a `s19+1` task in the
  review notes.

### Decision 4 — Stream-side persistence in `try/finally` AFTER the `async for` loop

`/api/chat/stream` accumulates the streamed tokens in a `full_response`
list and the final `sources` in a `final_sources` list. The
`event_generator` wraps the loop in a `try/except ValueError / finally`
block:

- On `ValueError` (agent refused), the router yields an error event and
  `return`s — the `finally` is skipped. **No row is written.** The user
  never saw a response, so the conversation was never started.
- On a successful close (the `async for` exits), the `finally` runs and
  writes the user + assistant messages. The guard is
  `if persist and full_response:` — empty `full_response` means the
  stream was empty (a misbehaving agent that yielded a `done` event
  with no tokens), and persistence is skipped to avoid writing a
  conversation with an empty assistant message.

The persistence is gated by `CHAT_PERSIST_HISTORY` (default `true`). The
s09 test suite (3-token stub, `done` event, error event, cross-tenant
bite) sets the flag to `false` via a fixture-level monkeypatch so the
existing `test_chat_stream.py` keeps passing with **zero** DB writes.
A regression in the persistence path that fires during a stream is
caught by T6's test, not by re-running the s09 suite. The flag is an
internal implementation knob, **not a product feature** (the ADR
records the design rationale; the env var has no UI surface).

The `try/finally` is the right pattern for this use case because the
stream has three terminal branches (success, agent error, safety-net
hit) and exactly one of them must reach the write path. A
"write-on-success" branch would miss the safety-net case; an
"always-write" branch would write a half-baked row on agent error.

**Considered alternatives**:

- **B. Write the user message as soon as the request body is parsed,
  the assistant message as the tokens stream** — rejected. The user
  message is not a stable "the user said this" until the agent
  commits to a response. If the agent refuses (wrong subject,
  cross-tenant, malformed pseudo), the user message is misleading:
  it implies a conversation was started when it was not. The ADR
  015 § Decision 4 forbids this — the row is written only when the
  user saw a response.
- **C. Write in a Celery task after the stream closes** — rejected
  for s19. The `try/finally` path is synchronous (FastAPI's
  StreamingResponse is awaited), the DB session is open, and the
  write is fast (< 50 ms). Celery would add a queue hop and a
  failure mode (the Celery worker is down) for no gain. If the
  write becomes a bottleneck in production, a follow-up can move
  it to Celery; the persistence helper is a single function and
  the swap is one line.

### Decision 5 — `formatRelativeTime` helper, not a `<RelativeTime>` component

The relative-time formatter is a 10-line pure helper in
`frontend/lib/intl/relativeTime.ts`. It takes an ISO 8601 string, a
locale, and an optional `now` (for deterministic tests). It returns a
localised string in French / English (the two supported locales) via
`Intl.RelativeTimeFormat(locale, { numeric: 'auto' })`. The 7-day
fall-through boundary is in the formatter itself; after a week the
helper returns a short, locale-aware date ("12 sept." / "Sep 12").

The `<RelativeTime>` shared component is **not** added (design system
gap #2). If 3+ stories need it after s22 (the a11y/UX pass), a
component is extracted at that point and the helper becomes its
internal implementation. The two history pages (list + detail) call
the helper inline.

**Considered alternatives**:

- **B. Add a `<RelativeTime>` shared component now** — rejected. The
  helper is 10 lines; the component would be a thin wrapper around
  the helper. Adding a shared component for a single story is YAGNI
  per `docs/architecture.md`. The s22 a11y/UX pass is the natural
  moment to extract: it can audit the locale behaviour, the
  fall-through boundary, and the ARIA live region afford together.
- **C. Use a date-only formatter (`Intl.DateTimeFormat`)** — rejected.
  The "il y a 2 heures" / "2 hours ago" afford is the design's
  primary cue for the recency of a conversation. A bare date loses
  the "this happened today" signal. The 7-day fall-through is the
  compromise: relative below the week boundary, absolute above.

## Consequences

- The `Conversation` table is small (one row per (eleve, subject)). The
  `Message` table is the hot path. Indexes on `Message.conversation_id` +
  `Message.created_at` cover the detail endpoint's "messages in
  chronological order" query (s18b's pattern).
- The stream-side persistence adds one INSERT (the conversation row) +
  two INSERTs (user message + assistant message) on every successful
  stream. The s09 test suite is gated by the env flag so the test
  runtime is unaffected. The production write is in the same request
  as the stream (no Celery hop), so the user sees the same latency
  profile as before s19.
- The parent's history surface is unchanged. The parent dashboard
  (s17) keeps its per-child summary; the per-child *history* is a
  documented follow-up (`s19+1` in the review notes). The 4-edge
  RBAC matrix (eleve self, parent linked, parent unlinked, admin)
  is the AGENTS.md DoD's cross-tenant bite — the plan § Run
  interdicts forbid adding a parent bypass to the list endpoint.
- The relative-time helper is a leaf module with no dependency on
  React or next-intl (it only uses `Intl`). It is exported as a
  named function so future stories can import it without going
  through a component.

## Considered options (cross-cutting)

- **Drop the new endpoints and reuse the SSE stream with `?history=true`**
  — rejected. The SSE stream is one-shot (the response is the
  streamed tokens). A history query is a paginated read of the
  past, not a live stream. Reusing the SSE wire format would
  require a new event shape (`{history, items}`) and would couple
  the read surface to the stream's parser. The two read endpoints
  are 80 lines of router + schema; the coupling cost is not worth
  it.
- **Store the messages in ChromaDB alongside the RAG chunks** —
  rejected. The history is operational state (the user wants to
  re-read it), not retrieval state (the RAG agent wants to search
  it). Mixing them in ChromaDB would conflate the two, break the
  RAG isolation (cf. ADR 004), and make pagination a quadratic
  scan. PostgreSQL is the right home.

## Open follow-ups

- `s19+1` — `GET /api/chat/history?child=<pseudo>` (parent / admin)
  wired through the parent dashboard. The s17 eleve dashboard
  already uses `?pseudo=`; the wiring is one line in the parent
  dashboard's read-only view.
- `s19+2` — LLM-output cap (max tokens for the assistant message).
  The current cap is implicit (the LLM provider's max_tokens). An
  explicit cap in the persistence path would close the "no silent
  truncation" gap.
- `s22` — extract `<RelativeTime>` from `formatRelativeTime` if
  3+ stories consume it.
- `s22` — design-system `<Badge>` component (currently inlined as
  a `<span>` in the history pages).
