"""Tests for ``SubjectSupervisor``.

The supervisor is the entry point used by the CLI (and the future FastAPI
``/chat`` endpoint). It MUST:

* dispatch to the right agent based on the ``subject`` argument (AC3),
* validate ``subject`` against the canonical enum (D3 — defense in depth
  with the agents' own validation),
* propagate the ``ChatResult`` unchanged,
* propagate exceptions from the underlying agent unchanged.

The supervisor is NOT a ``StateGraph`` langgraph — it's a typed
dispatcher (research D1). The Protocol it speaks against keeps the door
open to a future ``Pregel.invoke(...)`` swap.
"""

from __future__ import annotations

import pytest

from app.core.database.models import Subject
from app.services.agents.supervisor import (
    SubjectAgent,
    SubjectSupervisor,
)
from app.services.agents.types import ChatResult, SourceCitation

# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _RecordingSubjectAgent:
    """A SubjectAgent double that records the calls and returns a controlled result."""

    def __init__(self, expected_subject: str, *, result: ChatResult | None = None) -> None:
        self.expected_subject = expected_subject
        self.result = result or ChatResult(answer="ok", sources=[])
        self.calls: list[tuple[str, str, str]] = []

    def ask(self, subject: str, pseudo: str, question: str) -> ChatResult:
        self.calls.append((subject, pseudo, question))
        return self.result


# ---------------------------------------------------------------------------
# Tests — protocol conformance
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_subject_agent_protocol_is_runtime_checkable(self) -> None:
        """The protocol must accept any object that implements ``ask``."""
        agent = _RecordingSubjectAgent(expected_subject="maths")
        assert isinstance(agent, SubjectAgent)


# ---------------------------------------------------------------------------
# Tests — dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_dispatch_to_maths_when_subject_is_maths(self) -> None:
        maths = _RecordingSubjectAgent(
            expected_subject="maths",
            result=ChatResult(
                answer="2x", sources=[SourceCitation(filename="cours.pdf", chunk_index=0)]
            ),
        )
        supervisor = SubjectSupervisor(
            {Subject.MATHS.value: maths, Subject.FRANCAIS.value: _RecordingSubjectAgent("francais")}
        )

        result = supervisor.ask(Subject.MATHS.value, "alice", "Q ?")

        assert result.answer == "2x"
        assert maths.calls == [(Subject.MATHS.value, "alice", "Q ?")]

    def test_dispatch_to_francais_when_subject_is_francais(self) -> None:
        francais = _RecordingSubjectAgent(
            expected_subject="francais",
            result=ChatResult(
                answer="métaplasme",
                sources=[SourceCitation(filename="lecon.pdf", chunk_index=2)],
            ),
        )
        supervisor = SubjectSupervisor(
            {Subject.MATHS.value: _RecordingSubjectAgent("maths"), Subject.FRANCAIS.value: francais}
        )

        result = supervisor.ask(Subject.FRANCAIS.value, "bob", "Q ?")

        assert result.answer == "métaplasme"
        assert francais.calls == [(Subject.FRANCAIS.value, "bob", "Q ?")]


# ---------------------------------------------------------------------------
# Tests — validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_ask_rejects_unknown_subject(self) -> None:
        """D3 — unknown subject MUST be rejected before the retriever is touched."""
        maths = _RecordingSubjectAgent("maths")
        supervisor = SubjectSupervisor({Subject.MATHS.value: maths})

        with pytest.raises(ValueError, match="(?i)unknown subject|subject"):
            supervisor.ask("histoire", "alice", "Q ?")

        # The maths agent must NOT have been called for a wrong subject.
        assert maths.calls == []

    def test_ask_rejects_empty_subject(self) -> None:
        """Empty string is an unknown subject — refuse before dispatch."""
        maths = _RecordingSubjectAgent("maths")
        supervisor = SubjectSupervisor({Subject.MATHS.value: maths})

        with pytest.raises(ValueError):
            supervisor.ask("", "alice", "Q ?")
        assert maths.calls == []


# ---------------------------------------------------------------------------
# Tests — passthrough
# ---------------------------------------------------------------------------


class TestPassthrough:
    def test_chat_result_propagated_unchanged(self) -> None:
        expected = ChatResult(
            answer="une réponse",
            sources=[SourceCitation(filename="f.pdf", chunk_index=1)],
        )
        supervisor = SubjectSupervisor(
            {Subject.MATHS.value: _RecordingSubjectAgent("maths", result=expected)}
        )

        result = supervisor.ask(Subject.MATHS.value, "alice", "Q ?")

        assert result is expected
        assert result.sources == expected.sources

    def test_agent_exception_propagated(self) -> None:
        class _Boom:
            def ask(self, subject, pseudo, question):
                raise RuntimeError("kaboom")

        supervisor = SubjectSupervisor({Subject.MATHS.value: _Boom()})

        with pytest.raises(RuntimeError, match="kaboom"):
            supervisor.ask(Subject.MATHS.value, "alice", "Q ?")


# ---------------------------------------------------------------------------
# Tests — isolation: a request for one subject must NEVER touch the other
# ---------------------------------------------------------------------------


class TestIsolation:
    def test_supervisor_does_not_route_to_other_subject(self) -> None:
        """A bite test: requesting maths must NEVER call the French agent."""
        maths = _RecordingSubjectAgent("maths")
        francais = _RecordingSubjectAgent("francais")
        supervisor = SubjectSupervisor(
            {Subject.MATHS.value: maths, Subject.FRANCAIS.value: francais}
        )

        supervisor.ask(Subject.MATHS.value, "alice", "Q ?")

        assert maths.calls == [(Subject.MATHS.value, "alice", "Q ?")]
        assert francais.calls == []

    def test_supervisor_does_not_route_francais_to_maths(self) -> None:
        """Symmetric bite test: requesting French must NEVER call the maths agent."""
        maths = _RecordingSubjectAgent("maths")
        francais = _RecordingSubjectAgent("francais")
        supervisor = SubjectSupervisor(
            {Subject.MATHS.value: maths, Subject.FRANCAIS.value: francais}
        )

        supervisor.ask(Subject.FRANCAIS.value, "bob", "Q ?")

        assert francais.calls == [(Subject.FRANCAIS.value, "bob", "Q ?")]
        assert maths.calls == []
