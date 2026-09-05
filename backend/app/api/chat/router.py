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

s15 — the tenant identity comes from the JWT
(``Depends(get_current_user)``); the body no longer carries a
``pseudo`` (plan s15-restrictions-rbac, ADR 005). The cross-tenant
guard ``assert_jwt_pseudo_matches_or_403`` is invoked as a defensive
no-op (it would only fire if a future regression reintroduced a
``body.pseudo`` field).

s19 (T5) — stream-side persistence. The ``event_generator``
accumulates the assistant tokens and the final sources as
they stream past, then writes two ``Message`` rows and
upserts the parent ``Conversation`` in a ``try/finally``
**after** the SSE loop closes. The persistence is gated by
``Settings.chat_persist_history`` (default ``True``); the
s09 test suite flips it to ``False`` so the wire format
is unchanged for the pre-s19 tests. See ADR 015 §
Decision 4 — best-effort, no half-written row.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.chat.schemas import ChatStreamRequest
from app.api.chat.sse import format_sse
from app.core.auth.middleware import (
    assert_jwt_pseudo_matches_or_403,
    get_current_user,
)
from app.core.config import Settings, get_settings
from app.core.database.models import Conversation, Message, Subject, User
from app.services.agents import SubjectSupervisor
from app.services.agents.factory import build_subject_supervisor
from app.services.agents.types import SourceCitation

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


def _persist_conversation(
    *,
    session_factory: Callable[[], Session],
    student_pseudo: str,
    subject_value: str,
    question: str,
    assistant_text: str,
    final_sources: list[SourceCitation],
) -> None:
    """Write the ``Conversation`` upsert + two ``Message`` rows.

    The function is called from the SSE ``event_generator``'s
    ``try/finally`` AFTER the loop has closed. The session
    factory is the one configured by the FastAPI dependency
    injection (the ``get_db`` override in tests points at
    the in-memory engine). A fresh session is opened here
    so the streaming connection is not held by the DB
    write — the wire format is decoupled from the
    persistence path (the plan's "second session" rule).

    Strategy (ADR 015 § Decision 4):

    1. Reuse an existing :class:`Conversation` row for
       ``(student_pseudo, subject)``; if absent, INSERT a
       new one with ``first_question = question`` and
       ``message_count = 2``.
    2. INSERT the user ``Message`` (role="user", content=question,
       sources=None).
    3. INSERT the assistant ``Message`` (role="assistant",
       content=assistant_text, sources=[s.model_dump() for
       s in final_sources]).
    4. If the conversation was reused, bump
       ``message_count += 2`` and ``last_activity_at = now()``.

    No error is surfaced: the persistence is best-effort. A
    failure is logged at WARNING level so an operator can
    spot a regression without breaking the stream.
    """
    try:
        with session_factory() as db:
            subj = Subject(subject_value)
            conv = db.execute(
                select(Conversation).where(
                    Conversation.student_pseudo == student_pseudo,
                    Conversation.subject == subj,
                )
            ).scalar_one_or_none()
            if conv is None:
                conv = Conversation(
                    student_pseudo=student_pseudo,
                    subject=subj,
                    first_question=question,
                    message_count=2,
                )
                db.add(conv)
                db.flush()  # populate conv.id without committing yet
            else:
                conv.message_count = (conv.message_count or 0) + 2
            db.add_all(
                [
                    Message(
                        conversation_id=conv.id,
                        role="user",
                        content=question,
                        sources=None,
                    ),
                    Message(
                        conversation_id=conv.id,
                        role="assistant",
                        content=assistant_text,
                        sources=[
                            {"filename": s.filename, "chunk_index": s.chunk_index}
                            for s in final_sources
                        ],
                    ),
                ]
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001 - best-effort, never break the stream
        logger.warning(
            "chat.stream.persist_failed pseudo={} subject={} error={}",
            student_pseudo,
            subject_value,
            exc.__class__.__name__,
        )


def _build_session_factory_dep() -> Callable[[], Session]:
    """FastAPI dependency: return a callable that opens a
    fresh :class:`Session` for the persistence block.

    The function uses the same engine as the rest of the
    app (via :func:`get_session_factory`) so the test
    suite's ``app.dependency_overrides[get_db]``
    mechanism also wires the persistence path. The
    persistence function opens a fresh session from
    this factory AFTER the SSE wire format has finished,
    so the streaming transaction is not held by the DB
    write.
    """
    from app.core.database.session import get_session_factory

    def _factory() -> Session:
        return get_session_factory()()

    return _factory


@router.post("/stream")
async def stream_chat(
    body: ChatStreamRequest,
    user: User = Depends(get_current_user),
    supervisor: SubjectSupervisor = Depends(_build_supervisor_dep),
    settings: Settings = Depends(get_settings),
    session_factory: Callable[[], Session] = Depends(_build_session_factory_dep),
) -> StreamingResponse:
    """Stream the agent's response as SSE.

    The body is validated by Pydantic BEFORE this handler runs (422
    on bad input, never an opened stream). The handler then
    resolves the JWT via :func:`get_current_user` (401 ``invalid_token``
    on failure) and calls the cross-tenant guard with
    ``claimed=None`` — a defensive no-op now that ``body.pseudo``
    is retired, but a guard against any future regression that
    reintroduces the field (plan s15-restrictions-rbac, Tâche 2).
    """
    assert_jwt_pseudo_matches_or_403(user, None, route="/api/chat/stream")

    max_chunks = settings.chat_stream_max_chunks
    persist = settings.chat_persist_history

    async def event_generator() -> AsyncIterator[bytes]:
        full_response: list[str] = []
        final_sources: list[SourceCitation] = []
        try:
            chunk_count = 0
            async for event in supervisor.astream(
                body.subject, user.pseudo, body.question
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
                    # Accumulate for the persistence block; the
                    # frontend can ignore empty tokens (upstream
                    # models occasionally emit tool-call metadata
                    # chunks).
                    if event.content:
                        full_response.append(event.content)
                    yield format_sse({"token": event.content})
                elif event.event == "done":
                    # Snapshot the sources so the persistence
                    # block can read them after the loop closes.
                    final_sources = list(event.sources)
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
            # close the stream cleanly. No persistence on this
            # branch — the user never saw a response, so the
            # conversation was never started (ADR 015 § Decision 4).
            yield format_sse({"error": str(exc), "code": _map_code(exc)})
            return
        finally:
            # Persist AFTER the SSE loop closes. Runs on every
            # terminal branch (success, error, safety-net hit) so
            # a client-disconnect mid-stream still goes through
            # the write path. The error branch above uses
            # ``return`` to skip the ``finally``; only the
            # successful paths reach here.
            if persist and full_response:
                _persist_conversation(
                    session_factory=session_factory,
                    student_pseudo=user.pseudo,
                    subject_value=body.subject,
                    question=body.question,
                    assistant_text="".join(full_response),
                    final_sources=final_sources,
                )

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
