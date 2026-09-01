"""Subject supervisor — a typed Python dispatcher for one-shot chat.

The supervisor receives ``(subject, pseudo, question)`` and forwards the
call to the agent bound to ``subject`` in its registry. It is NOT a
``StateGraph`` langgraph — the research D1 (and the ADR 003 update)
explicitly retain a typed dispatcher as long as the routing is
deterministic by flag. The migration to ``langgraph.supervisor`` is
deferred to the iteration that introduces content-based routing.

The supervisor is the single entry point used by the CLI and (in s09+)
by the FastAPI ``/chat`` endpoint. It adds one responsibility on top
of the underlying agents: it validates the ``subject`` against the
canonical enum (D3 — defense in depth with the agents' own check).

s09 extension: an :meth:`astream` method is exposed alongside :meth:`ask`.
Both methods share the same dispatch and validation logic; the router
in ``app/api/chat/router.py`` calls ``astream`` so the SSE frontend
receives tokens in real time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from app.core.database.models import Subject
from app.services.agents.types import ChatResult, StreamChunk


@runtime_checkable
class SubjectAgent(Protocol):
    """The minimal contract a subject agent must satisfy.

    Mirrors the ``ask`` and ``astream`` signatures of :class:`MathsAgent`
    and :class:`FrancaisAgent` so both concrete agents and any future
    one can be plugged into the supervisor without changes.
    """

    def ask(self, subject: str, pseudo: str, question: str) -> ChatResult:
        ...

    def astream(
        self, subject: str, pseudo: str, question: str
    ) -> AsyncIterator[StreamChunk]:
        ...


class SubjectSupervisor:
    """Dispatcher that routes by ``subject`` to a per-subject agent.

    The registry is fixed at construction: ``subject_agents`` is a
    ``dict[str, SubjectAgent]`` whose keys MUST be the ``.value`` of a
    :class:`app.core.database.models.Subject` enum member. The
    supervisor does NOT mutate the registry — the only safe way to
    change routing is to build a new supervisor.

    Validation:

    * ``subject`` MUST be a known :class:`Subject` enum value. Anything
      else raises :class:`ValueError` BEFORE any agent is invoked. The
      underlying agent also validates its own subject — defense in depth.
    """

    _VALID_SUBJECTS: frozenset[str] = frozenset(s.value for s in Subject)

    def __init__(self, subject_agents: dict[str, SubjectAgent]) -> None:
        unknown = set(subject_agents) - self._VALID_SUBJECTS
        if unknown:
            raise ValueError(
                f"SubjectSupervisor received unknown subject(s): {sorted(unknown)!r}. "
                f"Expected one of: {sorted(self._VALID_SUBJECTS)!r}."
            )
        self._subject_agents: dict[str, SubjectAgent] = dict(subject_agents)

    def ask(self, subject: str, pseudo: str, question: str) -> ChatResult:
        """Dispatch ``ask`` to the agent bound to ``subject``.

        Raises:
            ValueError: if ``subject`` is not a known :class:`Subject` value.
        """
        if subject not in self._subject_agents:
            raise ValueError(
                f"Unknown subject: {subject!r}. "
                f"Expected one of: {sorted(self._subject_agents)!r}."
            )
        agent = self._subject_agents[subject]
        return agent.ask(subject, pseudo, question)

    def astream(
        self, subject: str, pseudo: str, question: str
    ) -> AsyncIterator[StreamChunk]:
        """Dispatch ``astream`` to the agent bound to ``subject``.

        Yields:
            The underlying agent's ``StreamChunk`` events, in order.

        Raises:
            ValueError: if ``subject`` is not a known :class:`Subject` value.
        """
        if subject not in self._subject_agents:
            raise ValueError(
                f"Unknown subject: {subject!r}. "
                f"Expected one of: {sorted(self._subject_agents)!r}."
            )
        agent = self._subject_agents[subject]
        return agent.astream(subject, pseudo, question)


__all__ = ["SubjectAgent", "SubjectSupervisor"]
