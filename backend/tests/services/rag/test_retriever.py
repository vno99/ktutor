"""Tests for ``Retriever`` — the RAG query layer.

The retriever is the multi-tenant choke point: it takes ``(subject, pseudo,
question)`` and never a collection name. The tests below are calibrated to
bite: removing the call to ``get_collection`` (e.g. substituting
``list_collections_for_pseudo``) must turn the cross-tenant test red.
"""

from __future__ import annotations

import uuid

import chromadb
import pytest

from app.services.rag.chroma_store import ChromaStore
from app.services.rag.retriever import RetrievedChunk, Retriever

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeEmbeddings:
    """Deterministic 3-dim embeddings, derived from the text length."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        # Each call: identical texts -> identical vectors. Distance ordering
        # is therefore not based on content (FakeListLLM doesn't care); we
        # only need the call to succeed and pass a vector into Chroma.
        return [[0.1, 0.2, 0.3] for _ in texts]


class _RecordingChroma(ChromaStore):
    """A ``ChromaStore`` that records the methods called on it."""

    def __init__(self) -> None:  # type: ignore[no-untyped-def]
        client = chromadb.EphemeralClient()
        super().__init__(client=client)
        self.get_collection_calls: list[tuple[str, str]] = []
        self.list_collections_calls: list[str] = []

    def get_collection(self, subject: str, pseudo: str):  # type: ignore[override]
        self.get_collection_calls.append((subject, pseudo))
        return super().get_collection(subject, pseudo)

    def list_collections_for_pseudo(self, pseudo: str) -> list[str]:  # type: ignore[override]
        self.list_collections_calls.append(pseudo)
        return super().list_collections_for_pseudo(pseudo)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def chroma_store() -> _RecordingChroma:
    return _RecordingChroma()


@pytest.fixture()
def embeddings() -> FakeEmbeddings:
    return FakeEmbeddings()


@pytest.fixture()
def retriever(chroma_store: _RecordingChroma, embeddings: FakeEmbeddings) -> Retriever:
    return Retriever(chroma_store=chroma_store, embeddings=embeddings)


@pytest.fixture()
def unique_pseudo() -> str:
    return f"u{uuid.uuid4().hex[:10]}"


def _seed(chroma: ChromaStore, pseudo: str, subject: str, n: int) -> None:
    coll = chroma.get_collection(subject, pseudo)
    chunks = [
        {
            "id": f"{pseudo}-{i}",
            "content": f"chunk {i}",
            "metadata": {"chunk_index": i, "filename": "doc.pdf", "document_id": str(uuid.uuid4())},
        }
        for i in range(n)
    ]
    chroma.add_chunks(coll, chunks, [[0.1 * (i + 1), 0.2, 0.3] for i in range(n)])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestQueryTopK:
    def test_query_returns_top_k_chunks_in_distance_order(
        self, retriever: Retriever, chroma_store: ChromaStore, unique_pseudo: str
    ) -> None:
        _seed(chroma_store, unique_pseudo, "maths", 6)
        result = retriever.query("maths", unique_pseudo, "What is a derivative?", k=4)
        assert isinstance(result, list)
        assert len(result) == 4
        assert all(isinstance(c, RetrievedChunk) for c in result)
        # Distances are sorted ascending (Chroma returns closest first).
        distances = [c.distance for c in result if c.distance is not None]
        assert distances == sorted(distances)

    def test_query_passes_top_k_to_chromadb(
        self, retriever: Retriever, chroma_store: ChromaStore, unique_pseudo: str
    ) -> None:
        _seed(chroma_store, unique_pseudo, "maths", 5)
        result = retriever.query("maths", unique_pseudo, "anything", k=2)
        assert len(result) == 2

    def test_query_embeds_only_the_question(
        self, retriever: Retriever, chroma_store: ChromaStore, embeddings: FakeEmbeddings, unique_pseudo: str
    ) -> None:
        _seed(chroma_store, unique_pseudo, "maths", 3)
        retriever.query("maths", unique_pseudo, "Why?", k=3)
        # The retriever must call the embedder with exactly one text: the question.
        assert embeddings.calls == [["Why?"]]


class TestQueryEmpty:
    def test_query_with_empty_collection_returns_empty_list(
        self, retriever: Retriever, unique_pseudo: str
    ) -> None:
        # No seeding — collection is created lazily on first call but stays empty.
        result = retriever.query("maths", unique_pseudo, "Anything?", k=4)
        assert result == []


class TestCrossTenant:
    def test_query_cross_tenant_isolation(
        self, retriever: Retriever, chroma_store: ChromaStore
    ) -> None:
        """AC6 — ``pseudo_a`` must never see ``pseudo_b``'s chunks."""
        pseudo_a = f"alice_{uuid.uuid4().hex[:8]}"
        pseudo_b = f"bob_{uuid.uuid4().hex[:8]}"
        # Tag each chunk's content with the pseudo so any leak is obvious.
        coll_a = chroma_store.get_collection("maths", pseudo_a)
        coll_b = chroma_store.get_collection("maths", pseudo_b)
        chroma_store.add_chunks(
            coll_a,
            [
                {
                    "id": f"{pseudo_a}-1",
                    "content": f"secret for {pseudo_a}",
                    "metadata": {"chunk_index": 0, "filename": "alice.pdf"},
                }
            ],
            [[0.1, 0.2, 0.3]],
        )
        chroma_store.add_chunks(
            coll_b,
            [
                {
                    "id": f"{pseudo_b}-1",
                    "content": f"secret for {pseudo_b}",
                    "metadata": {"chunk_index": 0, "filename": "bob.pdf"},
                }
            ],
            [[0.1, 0.2, 0.3]],
        )

        result = retriever.query("maths", pseudo_a, "What is the secret?", k=4)
        contents = {c.content for c in result}
        assert contents  # alice has 1 chunk
        assert f"secret for {pseudo_a}" in contents
        assert f"secret for {pseudo_b}" not in contents

    def test_query_uses_get_collection_not_list_collections(
        self, retriever: Retriever, chroma_store: _RecordingChroma, unique_pseudo: str
    ) -> None:
        """The retriever MUST route through ``get_collection`` — never
        ``list_collections_for_pseudo`` (which would let one tenant read all
        collections of any pseudo that happens to share a suffix)."""
        _seed(chroma_store, unique_pseudo, "maths", 2)
        retriever.query("maths", unique_pseudo, "Q", k=2)
        assert ("maths", unique_pseudo) in chroma_store.get_collection_calls
        assert chroma_store.list_collections_calls == []


class TestInvalidPseudo:
    def test_query_invalid_pseudo_raises(self, retriever: Retriever) -> None:
        from app.services.rag.chroma_store import InvalidPseudoError

        with pytest.raises(InvalidPseudoError):
            retriever.query("maths", "bad-pseudo", "Q", k=4)


class TestRetrievedChunkModel:
    def test_chunk_model_serializes(self) -> None:
        chunk = RetrievedChunk(
            content="text", metadata={"filename": "x.pdf", "chunk_index": 1}, distance=0.1
        )
        assert chunk.content == "text"
        assert chunk.metadata["filename"] == "x.pdf"
        assert chunk.distance == 0.1


class TestGetChunksForDocument:
    """s03 — chunk retrieval filtered by document_id, multi-tenant safe."""

    def _seed_document(
        self, chroma: ChromaStore, pseudo: str, subject: str, document_id: uuid.UUID, n: int
    ) -> None:
        coll = chroma.get_collection(subject, pseudo)
        chunks = [
            {
                "id": f"{pseudo}-{document_id}-{i}",
                "content": f"chunk {i}",
                "metadata": {
                    "chunk_index": i,
                    "filename": "doc.pdf",
                    "document_id": str(document_id),
                },
            }
            for i in range(n)
        ]
        chroma.add_chunks(coll, chunks, [[0.1 * (i + 1), 0.2, 0.3] for i in range(n)])

    def test_get_chunks_for_document_returns_only_target_document(
        self, retriever: Retriever, chroma_store: ChromaStore, unique_pseudo: str
    ) -> None:
        target_id = uuid.uuid4()
        other_id = uuid.uuid4()
        self._seed_document(chroma_store, unique_pseudo, "maths", target_id, 3)
        self._seed_document(chroma_store, unique_pseudo, "maths", other_id, 2)

        chunks = retriever.get_chunks_for_document(
            "maths", unique_pseudo, str(target_id), k=20
        )
        assert len(chunks) == 3
        assert all(c.metadata["document_id"] == str(target_id) for c in chunks)

    def test_get_chunks_for_document_cross_tenant_isolation(
        self, retriever: Retriever, chroma_store: ChromaStore
    ) -> None:
        """AC3 — requesting by ``pseudo_a`` must never surface ``pseudo_b``'s chunks."""
        pseudo_a = f"alice_{uuid.uuid4().hex[:8]}"
        pseudo_b = f"bob_{uuid.uuid4().hex[:8]}"
        target_id = uuid.uuid4()
        # Same document_id used in two collections, with different content.
        self._seed_document(chroma_store, pseudo_a, "maths", target_id, 2)
        self._seed_document(chroma_store, pseudo_b, "maths", target_id, 2)

        chunks = retriever.get_chunks_for_document(
            "maths", pseudo_a, str(target_id), k=20
        )
        assert all(c.metadata.get("document_id") == str(target_id) for c in chunks)
        # The collection for pseudo_a only has the 2 chunks we seeded for it.
        assert len(chunks) == 2

    def test_get_chunks_for_document_invalid_uuid_raises(
        self, retriever: Retriever
    ) -> None:
        with pytest.raises(ValueError):
            retriever.get_chunks_for_document(
                "maths", "alice", "not-a-uuid", k=20
            )

    def test_get_chunks_for_document_empty_when_no_match(
        self, retriever: Retriever, chroma_store: ChromaStore, unique_pseudo: str
    ) -> None:
        chunks = retriever.get_chunks_for_document(
            "maths", unique_pseudo, str(uuid.uuid4()), k=20
        )
        assert chunks == []
