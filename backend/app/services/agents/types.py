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
"""

from __future__ import annotations

from pydantic import BaseModel


class SourceCitation(BaseModel):
    """A parsed source citation, attached to a :class:`ChatResult`."""

    filename: str
    chunk_index: int


class ChatResult(BaseModel):
    """The structured result of a one-shot chat invocation."""

    answer: str
    sources: list[SourceCitation]
