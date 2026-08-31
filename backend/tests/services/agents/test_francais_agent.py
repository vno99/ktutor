"""Tests for ``FrancaisAgent``.

The French agent is a clone of the maths agent with two differences:

* a different ``SYSTEM_PROMPT`` (literary register, college-level, refusal
  rules, mandatory citations) — locked by tests at the prompt level,
* a defensive ``subject == "francais"`` check at the top of ``ask`` — so
  a wrong caller cannot silently query the wrong ChromaDB collection.

All other behaviour (multi-tenant, citation format, no-document fallback,
LLM grounding) is shared with :class:`MathsAgent` and the same contract
tests run on both agents.
"""

from __future__ import annotations

import uuid

import chromadb
import pytest
from langchain_core.messages import AIMessage, BaseMessage

from app.services.agents.citations import CITATION_FORMAT
from app.services.agents.francais_agent import SYSTEM_PROMPT, FrancaisAgent
from app.services.agents.types import ChatResult
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


def _seed_maths(chroma: ChromaStore, pseudo: str, n: int = 1) -> None:
    coll = chroma.get_collection("maths", pseudo)
    chunks = [
        {
            "id": f"{pseudo}-m-{i}",
            "content": f"maths chunk for {pseudo} {i}: la derivee de x^2 est 2x",
            "metadata": {
                "chunk_index": i,
                "filename": "cours_maths.pdf",
                "document_id": str(uuid.uuid4()),
            },
        }
        for i in range(n)
    ]
    chroma.add_chunks(coll, chunks, [[0.1, 0.2, 0.3] for _ in range(n)])


def _seed_francais(chroma: ChromaStore, pseudo: str, n: int = 1) -> None:
    coll = chroma.get_collection("francais", pseudo)
    chunks = [
        {
            "id": f"{pseudo}-f-{i}",
            "content": f"francais chunk for {pseudo} {i}: les metaplasmes",
            "metadata": {
                "chunk_index": i,
                "filename": "cours_francais.pdf",
                "document_id": str(uuid.uuid4()),
            },
        }
        for i in range(n)
    ]
    chroma.add_chunks(coll, chunks, [[0.1, 0.2, 0.3] for _ in range(n)])


# ---------------------------------------------------------------------------
# Tests — system prompt invariants (D4 of the research)
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_system_prompt_contains_5_invariants(self) -> None:
        """The French prompt must lock 5 invariants from the research D4."""
        text = SYSTEM_PROMPT
        lowered = text.lower()
        # 1) French language expected
        assert "français" in lowered or "francais" in lowered
        # 2) College-level (collège)
        assert "collège" in lowered or "college" in lowered
        # 3) Mandatory citation format
        assert "source" in lowered
        assert "[source:" in text or "source: " in lowered
        # 4) No general knowledge — must say "uniquement" or "tes documents"
        assert "uniquement" in lowered or "tes documents" in lowered
        # 5) Refusal when no chunks (explicit instruction not to invent)
        assert (
            "inventer" in lowered
            or "pas d'information" in lowered
            or "n'ai pas trouvé" in lowered
            or "refuse" in lowered
        )

    def test_system_prompt_shares_citation_format_constant(self) -> None:
        """The prompt must reference the exact CITATION_FORMAT constant."""
        # The format must be in the prompt so the LLM emits it verbatim.
        assert CITATION_FORMAT in SYSTEM_PROMPT

    def test_system_prompt_locks_no_general_knowledge(self) -> None:
        """The bite test: removing 'UNIQUEMENT' must break the contract."""
        # Assert the exact phrase used in the lock — not just any synonym.
        # The word "UNIQUEMENT" must appear in caps in the prompt so the
        # LLM treats it as a hard rule.
        assert "UNIQUEMENT" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Tests — happy path (AC4: response cites French sources)
# ---------------------------------------------------------------------------


class TestAskHappyPath:
    def test_ask_returns_answer_citing_sources(self) -> None:
        chunks = [
            RetrievedChunk(
                content="Les métaplasmes sont des modifications phonétiques.",
                metadata={"chunk_index": 0, "filename": "cours_francais.pdf"},
                distance=0.1,
            )
        ]
        retriever = _RecordingRetriever(chunks=chunks)
        llm = _CapturingLlm(
            answer="Les métaplasmes sont des modifications phonétiques. [source: cours_francais.pdf, chunk 0]"
        )
        agent = FrancaisAgent(llm=llm, retriever=retriever, top_k=4, no_document_message="NO_DOC")

        result = agent.ask("francais", "alice", "C'est quoi un métaplasme ?")

        assert isinstance(result, ChatResult)
        assert "métaplasme" in result.answer
        # The citation is parsed out of the LLM answer (best-effort): a
        # SourceCitation is added for any chunk that carries filename +
        # chunk_index metadata.
        assert result.sources
        assert result.sources[0].filename == "cours_francais.pdf"
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
        agent = FrancaisAgent(llm=llm, retriever=retriever, top_k=2)

        agent.ask("francais", "bob", "Q ?")

        # AC2 — the agent MUST query the per-(francais, bob) collection.
        assert retriever.calls == [("francais", "bob", "Q ?", 2)]


# ---------------------------------------------------------------------------
# Tests — empty collection: AC5 (no document → no fallback)
# ---------------------------------------------------------------------------


class TestAskEmpty:
    def test_ask_with_empty_collection_returns_no_document_message(self) -> None:
        retriever = _RecordingRetriever(chunks=[])
        llm = _CapturingLlm(answer="SHOULD NOT BE USED")
        agent = FrancaisAgent(
            llm=llm,
            retriever=retriever,
            top_k=4,
            no_document_message="Je n'ai rien trouvé.",
        )

        result = agent.ask("francais", "alice", "Quoi ?")

        assert result.answer == "Je n'ai rien trouvé."
        assert result.sources == []
        # LLM must NOT be invoked when there is no context (no hallucination).
        assert llm.calls == []


# ---------------------------------------------------------------------------
# Tests — prompt content
# ---------------------------------------------------------------------------


class TestAskPromptContent:
    def test_ask_injects_chunks_into_user_prompt(self) -> None:
        chunks = [
            RetrievedChunk(
                content="définition d'un métaplasme",
                metadata={"chunk_index": 0, "filename": "cours_francais.pdf"},
                distance=0.0,
            )
        ]
        retriever = _RecordingRetriever(chunks=chunks)
        llm = _CapturingLlm(answer="Réponse. [source: cours_francais.pdf, chunk 0]")
        agent = FrancaisAgent(llm=llm, retriever=retriever, top_k=4)

        agent.ask("francais", "alice", "Question ?")

        assert len(llm.calls) == 1
        messages = llm.calls[0]
        # Two messages: system + user.
        assert len(messages) == 2
        user_prompt = messages[1].content
        assert "définition d'un métaplasme" in user_prompt
        assert "cours_francais.pdf" in user_prompt
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
        agent = FrancaisAgent(llm=llm, retriever=retriever, top_k=4)

        agent.ask("francais", "alice", "Q")

        messages = llm.calls[0]
        assert messages[0].content == SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Tests — validation: subject MUST be "francais" (D3 + AC1)
# ---------------------------------------------------------------------------


class TestValidation:
    def test_ask_rejects_non_french_subject(self) -> None:
        """Bite test: a wrong subject must be refused before the retriever is touched."""
        retriever = _RecordingRetriever(chunks=[])
        llm = _CapturingLlm(answer="SHOULD NOT BE USED")
        agent = FrancaisAgent(llm=llm, retriever=retriever, top_k=4)

        with pytest.raises(ValueError, match="francais"):
            agent.ask("maths", "alice", "Q ?")

        # The retriever MUST NOT have been called with the wrong subject.
        assert retriever.calls == []
        # The LLM MUST NOT have been called either — failure is fast.
        assert llm.calls == []


# ---------------------------------------------------------------------------
# Tests — cross-tenant at the agent level (AC6) + no-fallback-to-maths (AC5)
# ---------------------------------------------------------------------------


class TestCrossTenant:
    def test_cross_tenant_isolation_at_french_agent_level(self) -> None:
        """The French agent must never leak another tenant's chunks."""
        pseudo_alice = f"alice_{uuid.uuid4().hex[:8]}"
        pseudo_bob = f"bob_{uuid.uuid4().hex[:8]}"

        chroma = _chroma()
        _seed_francais(chroma, pseudo_alice, n=1)
        coll_bob = chroma.get_collection("francais", pseudo_bob)
        chroma.add_chunks(
            coll_bob,
            [
                {
                    "id": f"{pseudo_bob}-1",
                    "content": f"secret de {pseudo_bob}",
                    "metadata": {"chunk_index": 0, "filename": "bob_secret.pdf"},
                }
            ],
            [[0.1, 0.2, 0.3]],
        )

        retriever = Retriever(chroma_store=chroma, embeddings=FakeEmbeddings())

        class EchoLlm:
            def invoke(self, messages):
                return AIMessage(content=messages[-1].content)

        agent = FrancaisAgent(llm=EchoLlm(), retriever=retriever, top_k=4)

        result = agent.ask("francais", pseudo_alice, "Q ?")

        # Alice must see only her own chunk.
        assert pseudo_alice in result.answer
        assert pseudo_bob not in result.answer
        assert "bob_secret.pdf" not in result.answer
        assert "francais chunk for" in result.answer  # alice's own chunk
        assert f"secret de {pseudo_bob}" not in result.answer

    def test_french_question_with_no_french_doc_does_not_query_maths(
        self, unique_pseudo: str
    ) -> None:
        """AC5 — a French question must NEVER fall back to the maths collection.

        The test seeds the maths collection for the same pseudo and asserts
        that the French agent returns the no-document message and never
        surfaces the maths chunk.
        """
        chroma = _chroma()
        _seed_maths(chroma, unique_pseudo, n=1)  # maths has data
        # Do NOT seed the French collection — it stays empty.

        # Use a recording retriever so we can assert what the agent asked.
        retriever = Retriever(chroma_store=chroma, embeddings=FakeEmbeddings())
        agent = FrancaisAgent(
            llm=_CapturingLlm(answer="SHOULD NOT BE USED"),
            retriever=retriever,
            top_k=4,
            no_document_message="Aucun document français trouvé.",
        )

        result = agent.ask("francais", unique_pseudo, "Q ?")

        # The agent must report the no-document state, not maths.
        assert result.answer == "Aucun document français trouvé."
        assert result.sources == []
