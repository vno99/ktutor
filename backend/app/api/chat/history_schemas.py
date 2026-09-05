"""Pydantic schemas for ``GET /api/chat/history`` (s19, ADR 015).

Four shapes are exposed here, all rooted on the read-side of
the chat history feature:

* :class:`ConversationListItem` — one row in the history list.
  Mirrors the SQL columns of :class:`app.core.database.models.Conversation`
  the doc's AC2 names verbatim: ``id``, ``subject``,
  ``first_question``, ``last_activity_at``, ``message_count``.
* :class:`MessageItem` — one message in a conversation detail
  (user / assistant, optional sources).
* :class:`HistoryListResponse` — the envelope for the list
  endpoint, carrying the pagination total.
* :class:`ConversationDetail` — the envelope for the detail
  endpoint (the conversation + its messages in one shot,
  per the AC3 contract: "the full message thread").
* :class:`NotFoundResponse` — 404 body shape; mirrors the s18b
  convention (``code: "not_found"``).

The ``model_config = ConfigDict(extra="forbid")`` is the same
strict shape Pydantic enforces everywhere else in the chat
package — a regression that adds an undocumented field is caught
by the response-shape tests in :mod:`tests.api.test_chat_history`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.database.models import Subject

# Mirror of :class:`app.services.agents.types.SourceCitation` —
# the source is a tuple ``(filename, chunk_index)`` so the frontend
# can render the citation as ``"filename:chunk"``. The shape is
# duplicated here (not imported) to keep the Pydantic layer free
# of an agents-layer dependency.
SourceCitation = dict[str, str | int]


class ConversationListItem(BaseModel):
    """One row in the history list (AC2).

    Fields are exactly the ones the doc's AC2 names — no extras.
    The ``model_config = ConfigDict(extra="forbid")`` from the
    base class surfaces a future regression that adds a field
    in the response (caught by ``test_list_history_item_shape``).
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    subject: Subject
    first_question: str
    last_activity_at: datetime
    message_count: int


class MessageItem(BaseModel):
    """One message in a :class:`ConversationDetail`.

    ``role`` is the literal ``"user"`` or ``"assistant"`` (the
    same two values enforced by the ``messages.role`` CHECK
    constraint in the model — T1). ``sources`` is a list of
    ``SourceCitation``-shaped dicts (filename + chunk_index)
    on assistant messages, ``None`` on user messages.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceCitation] | None = None
    created_at: datetime


class HistoryListResponse(BaseModel):
    """Envelope for ``GET /api/chat/history``.

    ``total`` is the count for the active filter (a pagination
    total, not a global count) so the client can render
    "page X of Y". ``limit`` and ``offset`` are echoed back
    so the client does not have to re-read the query string.
    """

    model_config = ConfigDict(extra="forbid")

    items: list[ConversationListItem]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)


class ConversationDetail(BaseModel):
    """Envelope for ``GET /api/chat/history/{conversation_id}`` (AC3).

    The conversation's fields are flat on the response (same
    shape as :class:`ConversationListItem`); the ``messages``
    list rides alongside so the client renders the thread
    without a second round trip.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    subject: Subject
    first_question: str
    last_activity_at: datetime
    message_count: int
    messages: list[MessageItem]


class NotFoundResponse(BaseModel):
    """404 body for both the unknown-id and the cross-tenant
    cases (the two share the same body so a cross-tenant
    attacker cannot distinguish "exists but not yours" from
    "doesn't exist" — see ADR 015 § Decision 3).
    """

    model_config = ConfigDict(extra="forbid")

    error: str
    code: Literal["not_found"]


__all__ = [
    "ConversationDetail",
    "ConversationListItem",
    "HistoryListResponse",
    "MessageItem",
    "NotFoundResponse",
    "SourceCitation",
]
