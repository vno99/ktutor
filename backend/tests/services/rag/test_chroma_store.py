"""Tests for ``ChromaStore``.

The most important test here is the cross-tenant isolation one (AC7):
an upload for ``pseudo_a`` must never be visible from the collection of
``pseudo_b`` because they are two distinct ChromaDB collections.

Note: ``chromadb.EphemeralClient`` keeps a process-global registry of
collections, so each test uses unique pseudo names to remain independent.
"""

from __future__ import annotations

import uuid

import chromadb
import pytest

from app.services.rag.chroma_store import (
    PSEUDO_RE,
    ChromaStore,
    InvalidPseudoError,
    collection_name,
    validate_pseudo,
)


@pytest.fixture()
def chroma_store() -> ChromaStore:
    """Ephemeral ChromaDB client wrapped in a ``ChromaStore``."""
    client = chromadb.EphemeralClient()
    return ChromaStore(client=client)


@pytest.fixture()
def unique_pseudo() -> str:
    """A pseudo that won't collide with any other test's collections."""
    return f"u{uuid.uuid4().hex[:10]}"


class TestPseudoValidation:
    @pytest.mark.parametrize(
        "pseudo",
        ["ali", "bob_le_bg", "a_b_c", "X" * 32, "user_123"],
    )
    def test_valid_pseudo_accepted(self, pseudo: str) -> None:
        validate_pseudo(pseudo)  # no raise

    @pytest.mark.parametrize(
        "pseudo",
        [
            "ab",  # too short
            "X" * 33,  # too long
            "ali-baba",  # dash not allowed
            "ali baba",  # space not allowed
            "ali@example.com",  # email
            "élève",  # non-ASCII
            "",  # empty
        ],
    )
    def test_invalid_pseudo_rejected(self, pseudo: str) -> None:
        with pytest.raises(InvalidPseudoError):
            validate_pseudo(pseudo)

    def test_regex_exposed(self) -> None:
        # Locked by the design — used by the CLI error message.
        assert PSEUDO_RE.pattern == r"^[a-zA-Z0-9_]{3,32}$"


class TestCollectionName:
    def test_format(self) -> None:
        assert collection_name("maths", "ali") == "rag_maths_ali"
        assert collection_name("francais", "bob_le_bg") == "rag_francais_bob_le_bg"


class TestGetCollection:
    def test_returns_collection_with_expected_name(self, chroma_store: ChromaStore, unique_pseudo: str) -> None:
        coll = chroma_store.get_collection("maths", unique_pseudo)
        assert coll.name == f"rag_maths_{unique_pseudo}"

    def test_is_idempotent(self, chroma_store: ChromaStore, unique_pseudo: str) -> None:
        a = chroma_store.get_collection("maths", unique_pseudo)
        b = chroma_store.get_collection("maths", unique_pseudo)
        assert a.name == b.name

    def test_distinct_pseudos_get_distinct_collections(self, chroma_store: ChromaStore) -> None:
        a = chroma_store.get_collection("maths", f"u1_{uuid.uuid4().hex[:8]}")
        b = chroma_store.get_collection("maths", f"u2_{uuid.uuid4().hex[:8]}")
        assert a.name != b.name

    def test_invalid_pseudo_raises(self, chroma_store: ChromaStore) -> None:
        with pytest.raises(InvalidPseudoError):
            chroma_store.get_collection("maths", "bad-pseudo")


class TestAddChunks:
    def test_adds_documents_to_collection(self, chroma_store: ChromaStore, unique_pseudo: str) -> None:
        coll = chroma_store.get_collection("maths", unique_pseudo)
        chunks = [
            {"id": f"{unique_pseudo}-1", "content": "alpha", "metadata": {"i": 0}},
            {"id": f"{unique_pseudo}-2", "content": "beta", "metadata": {"i": 1}},
        ]
        embeddings = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        chroma_store.add_chunks(coll, chunks, embeddings)

        assert coll.count() == 2
        results = coll.get(
            ids=[f"{unique_pseudo}-1", f"{unique_pseudo}-2"],
            include=["documents", "metadatas"],
        )
        assert results["documents"] == ["alpha", "beta"]
        assert results["metadatas"] == [{"i": 0}, {"i": 1}]

    def test_length_mismatch_raises(self, chroma_store: ChromaStore, unique_pseudo: str) -> None:
        coll = chroma_store.get_collection("maths", unique_pseudo)
        with pytest.raises(ValueError):
            chroma_store.add_chunks(coll, [{"id": "1", "content": "a", "metadata": {}}], [[0.1]])

    def test_empty_chunks_is_no_op(self, chroma_store: ChromaStore, unique_pseudo: str) -> None:
        coll = chroma_store.get_collection("maths", unique_pseudo)
        chroma_store.add_chunks(coll, [], [])
        assert coll.count() == 0


class TestMultiTenantIsolation:
    """AC7 — A document uploaded for pseudo_a must not appear in pseudo_b's collection."""

    def test_pseudo_a_cannot_see_pseudo_b_chunks(self, chroma_store: ChromaStore) -> None:
        pseudo_a = f"alice_{uuid.uuid4().hex[:8]}"
        pseudo_b = f"bob_{uuid.uuid4().hex[:8]}"
        coll_a = chroma_store.get_collection("maths", pseudo_a)
        coll_b = chroma_store.get_collection("maths", pseudo_b)

        chroma_store.add_chunks(
            coll_a,
            [
                {"id": "ali-1", "content": "secret pour alice", "metadata": {"pseudo": pseudo_a}},
                {"id": "ali-2", "content": "autre secret alice", "metadata": {"pseudo": pseudo_a}},
            ],
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        )
        chroma_store.add_chunks(
            coll_b,
            [{"id": "bob-1", "content": "secret pour bob", "metadata": {"pseudo": pseudo_b}}],
            [[0.0, 0.0, 1.0]],
        )

        assert coll_a.count() == 2
        assert coll_b.count() == 1

        # Querying B's collection by the id of A's chunk must return nothing.
        bob_lookalike_query = coll_b.get(ids=["ali-1"], include=["documents"])
        assert bob_lookalike_query["documents"] == []

        # And the inverse: A's collection never carries B's id.
        ali_lookalike_query = coll_a.get(ids=["bob-1"], include=["documents"])
        assert ali_lookalike_query["documents"] == []

    def test_list_collections_for_pseudo_scopes_by_suffix(self, chroma_store: ChromaStore) -> None:
        pseudo = f"l_{uuid.uuid4().hex[:8]}"
        chroma_store.get_collection("maths", pseudo)
        chroma_store.get_collection("francais", pseudo)
        ali_collections = chroma_store.list_collections_for_pseudo(pseudo)
        assert set(ali_collections) == {f"rag_maths_{pseudo}", f"rag_francais_{pseudo}"}
