"""Chat history read-side service (s19, ADR 015).

:class:`ChatHistoryService` is the closest-to-the-DB layer for the
``/api/chat/history`` endpoints. It applies the cross-tenant filter
(``student_pseudo`` from the JWT) INSIDE the SQL query — never
after a load. A "load then check" pattern would leak via a race
when the conversation is deleted between the load and the check.

The service is read-only; writes are best-effort and live in the
streaming router (``app/api/chat/router.py`` — T5) because the
stream needs them in a ``try/finally`` and the persistence is
triggered by the same supervisor events the SSE wire format
consumes.

Limits:

* ``limit`` is clamped to ``[1, 100]`` as a safety net. The router
  Pydantic layer enforces the same range, so this is a second
  wall, not the only one. A malicious client that bypasses the
  router (no Pydantic validation) cannot pull a million rows.
* ``offset`` is clamped to ``[0, ∞)`` — a negative offset becomes
  0 rather than raising.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database.models import Conversation, Message, Subject

# Bounds — see module docstring.
_MAX_LIMIT = 100
_MIN_LIMIT = 1


class ChatHistoryService:
    """Read-side service for the chat history endpoints (s19).

    The service is constructed with a ``session_factory`` callable
    that returns a fresh :class:`sqlalchemy.orm.Session` (the same
    factory :func:`app.core.database.session.get_session_factory`
    returns). Each query opens its own session so the service is
    safe to use across concurrent requests.
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # list_conversations
    # ------------------------------------------------------------------
    def list_conversations(
        self,
        *,
        student_pseudo: str,
        subject: Subject | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Conversation], int]:
        """Return ``(rows, total_for_filter)`` for one student.

        Args:
            student_pseudo: the JWT pseudo (the only source of
                truth for the cross-tenant filter — never read from
                the body or URL).
            subject: ``None`` for "all subjects", a :class:`Subject`
                enum value for "this subject only".
            limit: clamped to ``[1, 100]``.
            offset: clamped to ``[0, ∞)``.

        Returns:
            ``(rows, total)`` where ``rows`` is the page of
            :class:`Conversation` ordered by ``last_activity_at
            DESC, id DESC`` (the ``id DESC`` tie-breaker keeps
            pagination stable when two rows share a timestamp) and
            ``total`` is the count for the filter (a pagination
            total, not a global count).
        """
        safe_limit = max(_MIN_LIMIT, min(limit, _MAX_LIMIT))
        safe_offset = max(0, offset)

        # The cross-tenant filter is in the SQL query, NOT in Python
        # after a load.
        with self._session_factory() as s:
            count_q = select(func.count(Conversation.id)).where(
                Conversation.student_pseudo == student_pseudo
            )
            rows_q = (
                select(Conversation)
                .where(Conversation.student_pseudo == student_pseudo)
                .order_by(Conversation.last_activity_at.desc(), Conversation.id.desc())
                .limit(safe_limit)
                .offset(safe_offset)
            )
            if subject is not None:
                count_q = count_q.where(Conversation.subject == subject)
                rows_q = rows_q.where(Conversation.subject == subject)
            total = int(s.execute(count_q).scalar_one())
            rows = list(s.execute(rows_q).scalars().all())
            return rows, total

    # ------------------------------------------------------------------
    # get_conversation_with_messages
    # ------------------------------------------------------------------
    def get_conversation_with_messages(
        self,
        *,
        student_pseudo: str,
        conversation_id: uuid.UUID,
    ) -> tuple[Conversation, list[Message]] | None:
        """Return ``(conversation, messages)`` or ``None``.

        The cross-tenant filter is in the SQL query — a
        cross-tenant query returns ``None`` (the router surfaces a
        404). Messages are ordered by ``created_at ASC`` so the
        client renders them in chronological order.
        """
        with self._session_factory() as s:
            conv = s.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.student_pseudo == student_pseudo,
                )
            ).scalar_one_or_none()
            if conv is None:
                return None
            messages = list(
                s.execute(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at.asc())
                ).scalars().all()
            )
            return conv, messages


__all__ = ["ChatHistoryService"]
