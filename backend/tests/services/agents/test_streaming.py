"""Tests for the streaming variant of the agents (s09).

The one-shot ``ask`` API is locked by s02 / s05; the streaming variant
is additive — it MUST NOT regress the one-shot path. The bites for this
phase are:

* ``MathsAgent.astream`` yields one ``StreamChunk(content=..., event="token")``
  per upstream chunk, in order, then a single final ``StreamChunk(content="",
  event="done")`` carrying the RAG citations.
* ``FrancaisAgent.astream`` rejects ``subject != "francais"`` BEFORE
  touching the retriever (defense in depth, same as ``ask``).
* ``SubjectSupervisor.astream`` dispatches to the agent bound to the
  requested subject — a maths request must NEVER call the French agent
  and vice versa.
* Each agent calls the retriever with the EXACT ``pseudo`` it received,
  so the multi-tenant invariant is preserved across the streaming path.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage

from app.core.database.models import Subject
from app.services.agents.francais_agent import FrancaisAgent
from app.services.agents.maths_agent import MathsAgent
from app.services.agents.supervisor import SubjectSupervisor
from app.services.agents.types import ChatResult, SourceCitation, StreamChunk
from app.services.rag.retriever import RetrievedChunk

# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class _RecordingRetriever:
    """A retriever double that records calls and returns controlled chunks."""

    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.calls: list[tuple[str, str, str, int]] = []

    def query(self, subject: str, pseudo: str, question: str, k: int = 4) -> list[RetrievedChunk]:
        self.calls.append((subject, pseudo, question, k))
        return self.chunks


class _StrictRecordingRetriever:
    """A retriever that raises if called with a ``pseudo`` other than expected."""

    def __init__(self, expected_pseudo: str, chunks: list[RetrievedChunk] | None = None) -> None:
        self.expected_pseudo = expected_pseudo
        self.chunks = chunks or []
        self.calls: list[tuple[str, str, str, int]] = []

    def query(self, subject: str, pseudo: str, question: str, k: int = 4) -> list[RetrievedChunk]:
        self.calls.append((subject, pseudo, question, k))
        if pseudo != self.expected_pseudo:
            raise AssertionError(
                f"Retriever called with pseudo={pseudo!r}, expected {self.expected_pseudo!r}"
            )
        return self.chunks


class _ScriptedStreamingLlm:
    """An ``LlmClient`` double that yields a fixed sequence of tokens.

    Implements both ``invoke`` (returns the concatenated string) and
    ``astream`` (yields ``AIMessageChunk(content=token)`` per token) so
    it can stand in for the real LangChain wrapper in both modes.
    """

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.invoke_calls: list[list[BaseMessage]] = []
        self.astream_calls: list[list[BaseMessage]] = []

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.invoke_calls.append(messages)
        return AIMessage(content="".join(self.tokens))

    async def astream(self, messages: list[BaseMessage]) -> AsyncIterator[AIMessageChunk]:
        self.astream_calls.append(messages)
        for token in self.tokens:
            yield AIMessageChunk(content=token)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drain(generator) -> list:
    """Materialise an async generator into a list (synchronous helper)."""

    async def _collect() -> list:
        items = []
        async for item in generator:
            items.append(item)
        return items

    return asyncio.run(_collect())


def _chunks_fixture() -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            content="La dérivée de x^2 est 2x.",
            metadata={"chunk_index": 0, "filename": "cours_maths.pdf"},
            distance=0.1,
        )
    ]


# ---------------------------------------------------------------------------
# Tests — MathsAgent.astream
# ---------------------------------------------------------------------------


class TestMathsAgentAstream:
    def test_astream_yields_incremental_tokens_then_done(self) -> None:
        """A scripted 3-token LLM must yield 3 token events and 1 done event,
        in that order. The done event carries the RAG sources.
        """
        retriever = _RecordingRetriever(chunks=_chunks_fixture())
        llm = _ScriptedStreamingLlm(tokens=["Hel", "lo ", "world"])
        agent = MathsAgent(llm=llm, retriever=retriever, top_k=4)

        events = _drain(agent.astream("maths", "alice", "2+2 ?"))

        assert [e.event for e in events] == ["token", "token", "token", "done"]
        assert [e.content for e in events] == ["Hel", "lo ", "world", ""]
        # The done event carries the citations derived from the retrieved chunks.
        done = events[-1]
        assert done.sources == [SourceCitation(filename="cours_maths.pdf", chunk_index=0)]

    def test_astream_with_empty_collection_yields_only_no_document_token(self) -> None:
        """No chunks → no LLM call; the agent yields a single token event
        whose content is the no-document message, then a done event with
        no sources.
        """
        retriever = _RecordingRetriever(chunks=[])
        llm = _ScriptedStreamingLlm(tokens=["UNUSED"])
        agent = MathsAgent(
            llm=llm,
            retriever=retriever,
            top_k=4,
            no_document_message="Je n'ai rien trouvé.",
        )

        events = _drain(agent.astream("maths", "alice", "Q ?"))

        assert [e.event for e in events] == ["token", "done"]
        assert events[0].content == "Je n'ai rien trouvé."
        assert events[0].sources == []
        # The LLM must NOT be invoked when there is no context.
        assert llm.astream_calls == []
        assert llm.invoke_calls == []
        assert events[-1].sources == []

    def test_astream_uses_retriever_with_correct_pseudo(self) -> None:
        """Bite test: the agent must query the retriever with the EXACT
        ``pseudo`` it received. A future regression that hardcodes a
        default pseudo would break cross-tenant isolation.
        """
        retriever = _StrictRecordingRetriever(
            expected_pseudo="alice",
            chunks=_chunks_fixture(),
        )
        llm = _ScriptedStreamingLlm(tokens=["ok"])
        agent = MathsAgent(llm=llm, retriever=retriever, top_k=4)

        events = _drain(agent.astream("maths", "alice", "Q ?"))

        # If the retriever were called with anything but "alice", the
        # _StrictRecordingRetriever would have raised.
        assert retriever.calls == [("maths", "alice", "Q ?", 4)]
        assert events[-1].event == "done"

    def test_ask_still_works_after_astream_added(self) -> None:
        """Regression: the one-shot ``ask`` path must still work."""
        retriever = _RecordingRetriever(chunks=_chunks_fixture())
        llm = _ScriptedStreamingLlm(tokens=["reponse [source: cours_maths.pdf, chunk 0]"])
        agent = MathsAgent(llm=llm, retriever=retriever, top_k=4)

        result = agent.ask("maths", "alice", "Q ?")

        assert isinstance(result, ChatResult)
        assert "reponse" in result.answer


# ---------------------------------------------------------------------------
# Tests — FrancaisAgent.astream
# ---------------------------------------------------------------------------


class TestFrancaisAgentAstream:
    def test_astream_rejects_other_subject(self) -> None:
        """Bite test: the French agent must refuse ``subject != "francais"``
        BEFORE touching the retriever, just like ``ask``.
        """
        retriever = _RecordingRetriever()
        llm = _ScriptedStreamingLlm(tokens=["x"])
        agent = FrancaisAgent(llm=llm, retriever=retriever, top_k=4)

        async def _collect() -> list:
            return [item async for item in agent.astream("maths", "alice", "Q ?")]

        with pytest.raises(ValueError, match="francais"):
            asyncio.run(_collect())

        # The retriever must NOT have been called.
        assert retriever.calls == []

    def test_astream_happy_path_yields_done(self) -> None:
        retriever = _RecordingRetriever(
            chunks=[
                RetrievedChunk(
                    content="Une métaphore lie deux termes.",
                    metadata={"chunk_index": 2, "filename": "lecon.pdf"},
                    distance=0.0,
                )
            ]
        )
        llm = _ScriptedStreamingLlm(tokens=["Une ", "métaphore."])
        agent = FrancaisAgent(llm=llm, retriever=retriever, top_k=4)

        events = _drain(agent.astream("francais", "bob", "Q ?"))

        assert [e.event for e in events] == ["token", "token", "done"]
        assert [e.content for e in events] == ["Une ", "métaphore.", ""]
        assert events[-1].sources == [SourceCitation(filename="lecon.pdf", chunk_index=2)]


# ---------------------------------------------------------------------------
# Tests — SubjectSupervisor.astream
# ---------------------------------------------------------------------------


class _StubAgent:
    """A SubjectAgent double that records calls to both ``ask`` and ``astream``."""

    def __init__(self, subject: str, tokens: list[str]) -> None:
        self.subject = subject
        self.tokens = tokens
        self.ask_calls: list[tuple[str, str, str]] = []
        self.astream_calls: list[tuple[str, str, str]] = []

    def ask(self, subject: str, pseudo: str, question: str) -> ChatResult:
        self.ask_calls.append((subject, pseudo, question))
        return ChatResult(answer="".join(self.tokens), sources=[])

    async def astream(self, subject: str, pseudo: str, question: str) -> AsyncIterator[StreamChunk]:
        self.astream_calls.append((subject, pseudo, question))
        for token in self.tokens:
            yield StreamChunk(content=token, event="token")
        yield StreamChunk(content="", event="done", sources=[])


class TestSupervisorAstream:
    def test_astream_routes_to_maths(self) -> None:
        maths = _StubAgent("maths", ["a", "b"])
        francais = _StubAgent("francais", ["c"])
        supervisor = SubjectSupervisor(
            {Subject.MATHS.value: maths, Subject.FRANCAIS.value: francais}
        )

        events = _drain(supervisor.astream(Subject.MATHS.value, "alice", "Q ?"))

        assert [e.content for e in events] == ["a", "b", ""]
        assert maths.astream_calls == [(Subject.MATHS.value, "alice", "Q ?")]
        assert francais.astream_calls == []

    def test_astream_routes_to_francais(self) -> None:
        maths = _StubAgent("maths", ["a"])
        francais = _StubAgent("francais", ["c", "d"])
        supervisor = SubjectSupervisor(
            {Subject.MATHS.value: maths, Subject.FRANCAIS.value: francais}
        )

        events = _drain(supervisor.astream(Subject.FRANCAIS.value, "bob", "Q ?"))

        assert [e.content for e in events] == ["c", "d", ""]
        assert francais.astream_calls == [(Subject.FRANCAIS.value, "bob", "Q ?")]
        assert maths.astream_calls == []

    def test_astream_rejects_unknown_subject(self) -> None:
        maths = _StubAgent("maths", ["a"])
        supervisor = SubjectSupervisor({Subject.MATHS.value: maths})

        async def _collect() -> list:
            return [item async for item in supervisor.astream("histoire", "alice", "Q ?")]

        with pytest.raises(ValueError, match="(?i)unknown subject|subject"):
            asyncio.run(_collect())
        assert maths.astream_calls == []

    def test_ask_still_works_after_astream_added(self) -> None:
        """Regression: the supervisor's one-shot ``ask`` path must still work."""
        maths = _StubAgent("maths", ["a"])
        francais = _StubAgent("francais", ["b"])
        supervisor = SubjectSupervisor(
            {Subject.MATHS.value: maths, Subject.FRANCAIS.value: francais}
        )

        result = supervisor.ask(Subject.MATHS.value, "alice", "Q ?")

        assert isinstance(result, ChatResult)
        assert result.answer == "a"
        assert maths.ask_calls == [(Subject.MATHS.value, "alice", "Q ?")]
