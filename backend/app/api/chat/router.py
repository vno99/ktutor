"""``POST /api/chat/stream`` — Server-Sent Events stream of agent tokens.

The endpoint accepts a JSON body :class:`ChatStreamRequest` and returns
a ``text/event-stream`` response. Each event is a single JSON payload
serialized with :func:`app.api.chat.sse.format_sse`.

The three event shapes the client receives:

* ``data: {"token": "..."}`` — one per upstream LLM token (or a single
  token carrying the no-document fallback message when the collection
  is empty).
* ``data: {"done": true, "sources": [...]}`` — emitted as the FINAL
  event of every successful stream. ``sources`` mirrors
  :class:`SourceCitation` objects: ``[{filename, chunk_index}, ...]``.
* ``data: {"error": "...", "code": "..."}`` — emitted when the agent
  raises a ``ValueError``. The stream then closes.

The supervisor is built once per request via a FastAPI dependency that
defers to :func:`app.services.agents.factory.build_subject_supervisor`.
Building per-request is fine for s09 (no auth, no cache) — a future
story can pool the supervisor if benchmarks warrant it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.chat.schemas import ChatStreamRequest
from app.api.chat.sse import format_sse
from app.core.config import Settings, get_settings
from app.services.agents import SubjectSupervisor
from app.services.agents.factory import build_subject_supervisor

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _build_supervisor_dep() -> SubjectSupervisor:
    """FastAPI dependency that returns a fresh :class:`SubjectSupervisor`."""
    settings = get_settings()
    return build_subject_supervisor(settings)


def _map_code(exc: ValueError) -> str:
    """Map a :class:`ValueError` raised by an agent to a stable error code.

    The mapping is intentionally narrow (substring match on the message)
    so we can avoid leaking agent implementation details. The default
    is ``"unknown"`` — a safety net so the frontend always gets a code
    it can map.
    """
    message = str(exc).lower()
    if "different" in message or "cross" in message:
        return "cross_tenant"
    if "subject" in message:
        return "no_subject"
    if "pseudo" in message:
        return "invalid_pseudo"
    return "unknown"


@router.post("/stream")
async def stream_chat(
    body: ChatStreamRequest,
    supervisor: SubjectSupervisor = Depends(_build_supervisor_dep),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Stream the agent's response as SSE.

    The body is validated by Pydantic BEFORE this handler runs (422
    on bad input, never an opened stream). The handler itself never
    inspects ``body`` for anything other than the three fields the
    supervisor needs — keeping the router thin lets the rule about
    passing ``body.pseudo`` to the supervisor live in exactly one
    place.
    """
    max_chunks = settings.chat_stream_max_chunks

    async def event_generator() -> AsyncIterator[bytes]:
        try:
            chunk_count = 0
            async for event in supervisor.astream(
                body.subject, body.pseudo, body.question
            ):
                chunk_count += 1
                if chunk_count > max_chunks:
                    # Safety net: a runaway agent must not stream forever.
                    yield format_sse(
                        {
                            "error": (
                                f"Stream exceeded the {max_chunks}-chunk safety net."
                            ),
                            "code": "unknown",
                        }
                    )
                    return
                if event.event == "token":
                    # The frontend can ignore empty tokens (upstream models
                    # occasionally emit tool-call metadata chunks).
                    yield format_sse({"token": event.content})
                elif event.event == "done":
                    yield format_sse(
                        {
                            "done": True,
                            "sources": [
                                {"filename": s.filename, "chunk_index": s.chunk_index}
                                for s in event.sources
                            ],
                        }
                    )
                # ``event == "sources"`` is reserved for a future story
                # (D3 currently folds the sources into ``done``). The
                # router ignores it explicitly so a stray ``sources``
                # chunk is never forwarded to the client.
        except ValueError as exc:
            # Agent refused the request (wrong subject, cross-tenant,
            # malformed pseudo, etc.). Surface as an error event then
            # close the stream cleanly.
            yield format_sse({"error": str(exc), "code": _map_code(exc)})
            return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Disable nginx-style buffering so tokens reach the browser
            # as they are produced.
            "X-Accel-Buffering": "no",
        },
    )
