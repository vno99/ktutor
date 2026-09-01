# ADR 010 — FastAPI streaming architecture for `/api/chat/stream`

## Status

Accepted — s09 (2026-09-01).

## Context

Story s09 introduces the first HTTP entry point of the ktutor backend:
`POST /api/chat/stream` exposes the existing one-shot chat agents
(`MathsAgent`, `FrancaisAgent`, `SubjectSupervisor` — s02 / s05) as a
Server-Sent Events stream so the future Next.js frontend (s11) can
display the answer token-by-token.

Three decisions had to be locked before any code was written, because
each one cascades through the test suite, the contract, and the
operations:

1. **How the agents expose a streaming API** — the existing
   `LlmClient` Protocol has a single `invoke` method. The chosen
   shape determines whether the agents themselves need to be
   touched, and which one-shot call sites must be re-tested.
2. **How the SSE bytes are written to the wire** — the FastAPI
   ecosystem offers `StreamingResponse` (native) and
   `sse-starlette.EventSourceResponse` (idiomatic but external). The
   trade-off between an extra dependency and ergonomics is
   non-obvious and the decision is reversible only with a router
   rewrite.
3. **The auth stub boundary** — s09 is `pseudo`-in-body; s15 will
   migrate to JWT. The decision about where `pseudo` is read
   determines which line of code must move in s15.
4. **The error event payload** — the story says `{error: "..."}`;
   the rest of the codebase (`QcmGradingError.kind`,
   `TextGradingError.kind`) uses a stable `code` discriminator.
   Aligning the two makes the frontend contract easier to evolve.

The `LlmClient` extension (D1) and the SSE helper choice (D2) are
the most consequential — they bind the public contract of the agent
and the router, respectively.

## Decision

We lock the following four choices:

### D1 — `LlmClient.astream` is added to the Protocol (passthrough).

The `LlmClient` Protocol in `app/services/llm/client.py` gains a
second method:

```python
def astream(
    self, messages: list[BaseMessage]
) -> AsyncIterator[AIMessageChunk]: ...
```

The `_LangChainChatWrapper` implementation is a passthrough to
`BaseChatModel.astream`. The `invoke` method is preserved unchanged
so the CLI one-shot path and the existing tests are untouched.

`MathsAgent.astream`, `FrancaisAgent.astream`, and
`SubjectSupervisor.astream` are added next to the existing `ask`
methods. They share the retrieval + prompt construction with `ask`
and yield `StreamChunk(content=..., event="token")` per upstream
token, then a final `StreamChunk(content="", event="done", sources=[...])`
carrying the RAG citations.

`ask` is **not** removed. The CLI and the unit-test corpus keep
using it.

### D2 — SSE via `StreamingResponse` (native). No `sse-starlette`.

The router uses `fastapi.responses.StreamingResponse(generator,
media_type="text/event-stream")`. The generator yields bytes built
by `app.api.chat.sse.format_sse`:

```python
def format_sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
```

`sse-starlette` is **not** added to `requirements.txt`. The native
helper is two lines, the ergonomics gain (ping, retry) is not
needed in s09, and an extra dependency is an extra supply-chain
surface.

### D3 — `pseudo` in the body (auth stub).

The `ChatStreamRequest` body carries `pseudo`, `subject`, and
`question`. The router passes `body.pseudo` to the supervisor
unchanged. There is **no** `X-Pseudo` header, no JWT, no middleware
in s09.

The migration to JWT is owned by s15; the only line that must
change in s15 is the one that reads `body.pseudo` (replaced by
`request.state.pseudo` populated by the auth dependency).

### D5 — `error` events carry a stable `code`.

Every `ValueError` raised by the agent is caught by the router and
forwarded as `{"error": str(exc), "code": "..."}`. The mapping is
`app.api.chat.router._map_code`:

| Substring in message   | `code`            |
| ---------------------- | ----------------- |
| `different` or `cross` | `cross_tenant`    |
| `subject`              | `no_subject`      |
| `pseudo`               | `invalid_pseudo`  |
| (default)              | `unknown`         |

The frontend maps `code` to a UI state (toast / redirect / retry)
without parsing the human-readable `error` string.

## Considered options

### D1 — alternatives rejected

- **Replace `ask` by `astream` everywhere.** Would have forced the
  CLI to consume the streaming API and buffered the one-shot
  response, costing a refactor across s02–s07.
- **New `StreamingSubjectAgent` Protocol.** Would have duplicated
  the registry for no benefit — the existing Protocol can carry
  both methods.

### D2 — alternatives rejected

- **`sse-starlette.EventSourceResponse`.** Adds a dependency for
  a marginal ergonomics gain. The native `StreamingResponse` plus
  a two-line `format_sse` helper is enough for s09's needs (no
  heartbeat, no retry).

### D3 — alternatives rejected

- **`X-Pseudo` header.** More RESTful but the story is explicit
  on the body shape, and the migration to JWT in s15 will
  supersede both anyway.

### D5 — alternatives rejected

- **Raw `{error: "..."}` without `code`.** The frontend would
  have to substring-match the human message — fragile and against
  the existing `kind` convention.

## Consequences

* `LlmClient` now has a stable two-method surface. Any future
  provider wrapper must implement both `invoke` and `astream`.
* The CLI's `_build_chat_service` keeps using `ask`. A future
  story can migrate the CLI to `astream` (consuming a one-shot
  async iterator) without touching the agents.
* The s10 upload router will reuse the same FastAPI lifespan,
  CORS middleware, and supervisor factory. The factory lives at
  `app/services/agents/factory.py:build_subject_supervisor` so the
  wiring is shared.
* s15 (JWT auth) will replace `body.pseudo` with
  `request.state.pseudo`. The test `test_cross_tenant_via_body_swap`
  must be updated to inject the JWT context; the underlying
  guarantee (the router never hardcodes a pseudo) is preserved.
* s19 (chat history) will add a second endpoint under the same
  `/api/chat` prefix (`GET /api/chat/history`).
* The `chat_stream_max_chunks` safety net defaults to 5000 — high
  enough not to fire on any reasonable response, low enough to
  detect a runaway agent within seconds.
