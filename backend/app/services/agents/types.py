"""Shared types for specialised agents.

These Pydantic models are the public output contract of every one-shot
chat invocation. They are promoted out of :mod:`app.services.agents.maths_agent`
in s05 so that:

* :mod:`app.services.agents.francais_agent` does not need to import
  from ``maths_agent`` (which would create a cycle once ``supervisor``
  imports both).
* :mod:`app.services.agents.supervisor` can declare its
  :class:`~app.services.agents.supervisor.SubjectAgent` Protocol against
  a stable schema.

The shape is unchanged from s02 — only the import path moves.

s09 extension: :class:`StreamChunk` is the per-event schema yielded by the
agents' new ``astream`` method (one chunk per upstream token, plus a
trailing ``done`` event carrying the RAG sources). The router in
``app/api/chat/router.py`` translates each ``StreamChunk`` into an SSE
event.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    """A parsed source citation, attached to a :class:`ChatResult`."""

    filename: str
    chunk_index: int


class ChatResult(BaseModel):
    """The structured result of a one-shot chat invocation."""

    answer: str
    sources: list[SourceCitation]


class StreamChunk(BaseModel):
    """One event emitted by the agents' ``astream`` method (s09).

    Three shapes — distinguished by the ``event`` field:

    * ``event="token"`` — a chunk of LLM text. ``content`` is the delta
      (non-empty for real tokens, may be empty if the upstream model
      emits a non-content chunk such as tool-call metadata).
    * ``event="sources"`` — attached at the end of a successful stream to
      expose the RAG sources. ``content`` is empty, ``sources`` carries
      the :class:`SourceCitation` list.
    * ``event="done"`` — sent as the FINAL event of every successful
      stream, after all tokens. ``content`` is empty.

    Failure events are NOT modeled here: the agents surface errors by
    raising, and the SSE router translates the raise into an
    ``{error, code}`` event.
    """

    content: str = ""
    event: Literal["token", "sources", "done"] = "token"
    sources: list[SourceCitation] = Field(default_factory=list)
