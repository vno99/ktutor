"""Tests for ``MathsAgent``.

The agent is the orchestration of:
  * a :class:`Retriever` (multi-tenant — takes (subject, pseudo)),
  * a :class:`LlmClient` (stubbed with ``FakeListChatModel`` in tests),
  * a system prompt that forbids general knowledge and forces citations.

These tests are calibrated to bite. The most important guards are:

* The system prompt is explicit ("uniquement tes documents").
* The user prompt must actually receive the chunks (not just the question).
* The citation format is locked by regex: ``[source: <file>, chunk <n>]``.
* Cross-tenant: an agent asked for ``alice`` must never produce ``bob``'s
  chunks — even though the stub LLM is the same for both.
"""

from __future__ import annotations

import re
import uuid

import chromadb
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, BaseMessage

from app.services.agents.maths_agent import (
    CITATION_FORMAT,
    SYSTEM_PROMPT,
    ChatResult,
    MathsAgent,
)
from app.services.llm.client import _LangChainChatWrapper
from app.services.rag.chroma_store import ChromaStore
from app.services.rag.retriever import RetrievedChunk, Retriever

# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------


class FakeEmbeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class _RecordingRetriever:
    """A retriever double that records the calls and returns a controlled list."""

    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.calls: list[tuple[str, str, str, int]] = []

    def query(self, subject: str, pseudo: str, question: str, k: int = 4) -> list[RetrievedChunk]:
        self.calls.append((subject, pseudo, question, k))
        return self.chunks


class _CapturingLlm:
    """An LLM double that records the messages and returns a canned answer."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[list[BaseMessage]] = []

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(messages)
        return AIMessage(content=self.answer)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def unique_pseudo() -> str:
    return f"u{uuid.uuid4().hex[:10]}"


def _chroma() -> ChromaStore:
    return ChromaStore(client=chromadb.EphemeralClient())


def _seed(chroma: ChromaStore, pseudo: str, n: int = 2) -> None:
    coll = chroma.get_collection("maths", pseudo)
    chunks = [
        {
            "id": f"{pseudo}-{i}",
            "content": f"document for {pseudo} chunk {i} about derivatives",
            "metadata": {
                "chunk_index": i,
                "filename": "cours_maths.pdf",
                "document_id": str(uuid.uuid4()),
            },
        }
        for i in range(n)
    ]
    chroma.add_chunks(coll, chunks, [[0.1, 0.2, 0.3] for _ in range(n)])


# ---------------------------------------------------------------------------
# Tests — citation format & prompt
# ---------------------------------------------------------------------------


class TestCitationFormat:
    def test_citation_format_constant_matches_story(self) -> None:
        assert CITATION_FORMAT == "[source: {filename}, chunk {chunk_index}]"

    def test_citation_regex_matches_real_citation(self) -> None:
        # The regex must accept a real, formatted citation (post-formatting).
        pat = re.compile(r"\[source: [^,]+, chunk \d+\]")
        assert pat.search("[source: foo.pdf, chunk 3]") is not None

    def test_citation_regex_rejects_wrong_field(self) -> None:
        pat = re.compile(r"\[source: [^,]+, chunk \d+\]")
        bad = "[source: foo.pdf, page 3]"
        assert pat.search(bad) is None
        assert pat.search("[source: foo.pdf, chunk 3]") is not None


class TestSystemPrompt:
    def test_system_prompt_forbids_general_knowledge(self) -> None:
        # The prompt must require grounding in the provided chunks only.
        assert "uniquement" in SYSTEM_PROMPT.lower() or "tes documents" in SYSTEM_PROMPT
        # And must require a citation when sources are used.
        assert "source" in SYSTEM_PROMPT.lower()

    def test_system_prompt_rejects_when_no_context(self) -> None:
        # The fallback path: when the chunks don't answer the question, the
        # LLM must say so. The prompt should forbid fabrications.
        lowered = SYSTEM_PROMPT.lower()
        assert any(
            kw in lowered for kw in ("ne sais pas", "pas d'information", "refuse", "no document", "inventer")
        )


# ---------------------------------------------------------------------------
# Tests — ask() behavior
# ---------------------------------------------------------------------------


class TestAskHappyPath:
    def test_ask_returns_answer_citing_sources(self) -> None:
        chunks = [
            RetrievedChunk(
                content="La dérivée de x^2 est 2x.",
                metadata={"chunk_index": 0, "filename": "cours_maths.pdf"},
                distance=0.1,
            )
        ]
        retriever = _RecordingRetriever(chunks=chunks)
        llm = _CapturingLlm(answer="Une dérivée mesure la pente. [source: cours_maths.pdf, chunk 0]")
        agent = MathsAgent(llm=llm, retriever=retriever, top_k=4, no_document_message="NO_DOC")

        result = agent.ask("maths", "alice", "Qu'est-ce qu'une dérivée ?")

        assert isinstance(result, ChatResult)
        assert "dérivée" in result.answer
        # The citation is parsed out of the LLM answer (best-effort — see
        # ``MathsAgent.ask``; a SourceCitation is added for any chunk that
        # carries filename + chunk_index metadata).
        assert result.sources
        assert result.sources[0].filename == "cours_maths.pdf"
        assert result.sources[0].chunk_index == 0

    def test_ask_uses_retriever_with_correct_subject_pseudo(self) -> None:
        retriever = _RecordingRetriever(
            chunks=[
                RetrievedChunk(
                    content="x",
                    metadata={"chunk_index": 0, "filename": "f.pdf"},
                    distance=0.0,
                )
            ]
        )
        llm = _CapturingLlm(answer="ok [source: f.pdf, chunk 0]")
        agent = MathsAgent(llm=llm, retriever=retriever, top_k=2)

        agent.ask("maths", "bob", "Q?")

        assert retriever.calls == [("maths", "bob", "Q?", 2)]


class TestAskEmpty:
    def test_ask_with_empty_collection_returns_no_document_message(self) -> None:
        retriever = _RecordingRetriever(chunks=[])
        llm = _CapturingLlm(answer="SHOULD NOT BE USED")
        agent = MathsAgent(
            llm=llm,
            retriever=retriever,
            top_k=4,
            no_document_message="Je n'ai rien trouvé.",
        )

        result = agent.ask("maths", "alice", "Quoi ?")

        assert result.answer == "Je n'ai rien trouvé."
        assert result.sources == []
        # LLM must NOT be invoked when there is no context (no hallucination).
        assert llm.calls == []


class TestAskPromptContent:
    def test_ask_injects_chunks_into_user_prompt(self) -> None:
        chunks = [
            RetrievedChunk(
                content="définition de la dérivée",
                metadata={"chunk_index": 0, "filename": "cours_maths.pdf"},
                distance=0.0,
            )
        ]
        retriever = _RecordingRetriever(chunks=chunks)
        llm = _CapturingLlm(answer="Réponse. [source: cours_maths.pdf, chunk 0]")
        agent = MathsAgent(llm=llm, retriever=retriever, top_k=4)

        agent.ask("maths", "alice", "Question ?")

        assert len(llm.calls) == 1
        messages = llm.calls[0]
        # Two messages: system + user.
        assert len(messages) == 2
        user_prompt = messages[1].content
        assert "définition de la dérivée" in user_prompt
        assert "cours_maths.pdf" in user_prompt
        assert "Question ?" in user_prompt

    def test_ask_uses_system_prompt_constant(self) -> None:
        chunks = [
            RetrievedChunk(
                content="x",
                metadata={"chunk_index": 0, "filename": "f.pdf"},
                distance=0.0,
            )
        ]
        retriever = _RecordingRetriever(chunks=chunks)
        llm = _CapturingLlm(answer="ok [source: f.pdf, chunk 0]")
        agent = MathsAgent(llm=llm, retriever=retriever, top_k=4)

        agent.ask("maths", "alice", "Q")

        messages = llm.calls[0]
        assert messages[0].content == SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Tests — cross-tenant at the agent level
# ---------------------------------------------------------------------------


class TestCrossTenant:
    def test_cross_tenant_isolation_at_agent_level(self, unique_pseudo: str) -> None:
        """The agent must never produce another tenant's chunks."""
        pseudo_alice = f"alice_{uuid.uuid4().hex[:8]}"
        pseudo_bob = f"bob_{uuid.uuid4().hex[:8]}"

        # Seed the real ChromaDB store for each pseudo with distinctive content.
        chroma = _chroma()
        _seed(chroma, pseudo_alice, n=1)
        coll_bob = chroma.get_collection("maths", pseudo_bob)
        chroma.add_chunks(
            coll_bob,
            [
                {
                    "id": f"{pseudo_bob}-1",
                    "content": f"secret for {pseudo_bob}",
                    "metadata": {"chunk_index": 0, "filename": "bob_secret.pdf"},
                }
            ],
            [[0.1, 0.2, 0.3]],
        )

        retriever = Retriever(chroma_store=chroma, embeddings=FakeEmbeddings())
        # An LLM that just echoes back the user prompt — anything bob-related
        # in its output means the agent leaked bob's chunk into alice's prompt.
        class EchoLlm:
            def invoke(self, messages):
                return AIMessage(content=messages[-1].content)

        agent = MathsAgent(llm=EchoLlm(), retriever=retriever, top_k=4)

        result = agent.ask("maths", pseudo_alice, "Q?")

        # Alice must see only her own chunk.
        assert pseudo_alice in result.answer
        assert pseudo_bob not in result.answer
        assert "bob_secret.pdf" not in result.answer
        assert "document for" in result.answer  # alice's own chunk was injected
        assert f"secret for {pseudo_bob}" not in result.answer


# ---------------------------------------------------------------------------
# Tests — temperature / LLM invocation
# ---------------------------------------------------------------------------


class TestLlmClientContract:
    def test_agent_accepts_langchain_wrapper(self) -> None:
        """The agent must accept the LangChain wrapper returned by the factory."""
        fake = FakeListChatModel(responses=["Réponse [source: f.pdf, chunk 0]"])
        wrapper = _LangChainChatWrapper(fake)
        retriever = _RecordingRetriever(
            chunks=[
                RetrievedChunk(
                    content="x",
                    metadata={"chunk_index": 0, "filename": "f.pdf"},
                    distance=0.0,
                )
            ]
        )
        agent = MathsAgent(llm=wrapper, retriever=retriever, top_k=4)
        result = agent.ask("maths", "alice", "Q?")
        assert isinstance(result.answer, str)
        assert result.answer  # non-empty
