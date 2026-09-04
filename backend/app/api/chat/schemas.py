"""Pydantic schemas for the chat API (s09, s15).

Two request/response shapes are exposed here:

* :class:`ChatStreamRequest` — the body of ``POST /api/chat/stream``.
  Validated by FastAPI BEFORE the handler runs, so a malformed body
  yields 422 (Pydantic's ``RequestValidationError``) without opening
  the stream. The ``pseudo`` is **no longer in the body** — it
  comes from the JWT (s15, plan s15-restrictions-rbac, ADR 005 §
  « RBAC »). Any client still sending ``pseudo`` is rejected with
  422 by Pydantic (the hard cut decided in research Piège 1).
* :class:`StreamErrorEvent` — the body of the ``error`` event emitted
  in the SSE stream when the agent raises. The ``code`` field is
  machine-readable so the frontend can map the error to a UI state
  (toast, redirect, retry) without parsing the human message.

The token / done events are streamed as raw ``dict`` payloads, not
Pydantic models, because the router constructs them inline and they
carry a discriminated shape (``token`` vs ``done``). Tests assert on
the raw JSON.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Maximum question length — bound by the LLM context window plus a
# safety margin. Matches the convention used by the CLI ``chat`` command.
_MAX_QUESTION_CHARS = 2000


class ChatStreamRequest(BaseModel):
    """Body of ``POST /api/chat/stream`` (s15).

    The tenant identity is taken from the JWT
    (``Depends(get_current_user)`` in the router). The body carries
    only the conversation inputs. ``model_config`` rejects any
    unknown field — a client that still sends ``pseudo`` (s09
    contract) gets 422 from Pydantic BEFORE the handler runs,
    which is the s15 hard-cut behaviour decided in research
    Piège 1 (the only known client is the frontend shipped in
    the same repo).
    """

    model_config = ConfigDict(extra="forbid")

    subject: Literal["maths", "francais"] = Field(
        ...,
        description="Matière sur laquelle porte la question.",
    )
    question: str = Field(
        ...,
        min_length=1,
        max_length=_MAX_QUESTION_CHARS,
        description="Question posée à l'agent.",
    )


class StreamErrorEvent(BaseModel):
    """An ``error`` event in the SSE stream.

    The frontend uses ``code`` to decide the recovery action:

    * ``cross_tenant`` — the request attempted to query another
      student's collection; refuse and log.
    * ``no_subject`` — the subject is unknown; surface as a config
      error.
    * ``invalid_pseudo`` — the pseudo is malformed; surface as a
      validation error.
    * ``unknown`` — fallback for any other ``ValueError`` raised by
      the agent.
    """

    error: str
    code: Literal["cross_tenant", "no_subject", "invalid_pseudo", "unknown"]
