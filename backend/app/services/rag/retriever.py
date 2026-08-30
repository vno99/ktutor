"""RAG query layer — the multi-tenant choke point of the chat pipeline.

The retriever is intentionally narrow:

* It accepts ``(subject, pseudo, question)`` — **never a collection name**.
  This is the multi-tenant invariant: the only way to access a ChromaDB
  collection is through :meth:`ChromaStore.get_collection`, which validates
  the pseudo and constructs the canonical ``rag_<subject>_<pseudo>`` name.
* It embeds the question with the injected embedder (so the embedding
  backend choice lives in one place, not duplicated per agent).
* It returns a list of :class:`RetrievedChunk` (Pydantic), so the agent
  can iterate without caring about ChromaDB internals.

The CLI / agent does **not** call ``ChromaStore.list_collections_for_pseudo``
on the hot path — that would let a request for ``alice`` accidentally surface
chunks from a different ``alice_*`` pseudo (suffix collision). The only safe
way to read a tenant's data is to ask for it by ``(subject, pseudo)``.

In s03, the retriever also exposes :meth:`get_chunks_for_document`, which
filters the tenant's collection by ``document_id`` metadata. The same
multi-tenant invariant holds: only the collection ``rag_<subject>_<pseudo>``
is ever read.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.services.rag.chroma_store import ChromaStore, validate_pseudo
from app.services.rag.embeddings import EmbeddingProvider


class RetrievedChunk(BaseModel):
    """One chunk returned by :class:`Retriever`."""

    content: str
    metadata: dict
    distance: float | None = None


class Retriever:
    """Embed a question, query the per-(subject, pseudo) ChromaDB collection.

    The constructor takes interfaces for the ChromaDB store and the embedding
    provider so the unit tests can inject cheap in-memory doubles.
    """

    def __init__(
        self,
        *,
        chroma_store: ChromaStore,
        embeddings: EmbeddingProvider,
    ) -> None:
        self._chroma = chroma_store
        self._embeddings = embeddings

    def query(
        self,
        subject: str,
        pseudo: str,
        question: str,
        k: int = 4,
    ) -> list[RetrievedChunk]:
        """Return the ``k`` closest chunks of ``(subject, pseudo)`` to ``question``.

        Empty list when the collection is empty or no chunk matches. Raises
        :class:`InvalidPseudoError` when the pseudo is malformed (the same
        rule enforced at upload time).
        """
        # Multi-tenant invariant: the pseudo is validated up front so a
        # malformed value never reaches ChromaDB naming.
        validate_pseudo(pseudo)

        # Embed the question with a single-element list (don't go through a
        # batch that could be confused with a corpus embedding).
        query_vec = self._embeddings.embed_documents([question])[0]

        # The ONLY way to access a tenant's data: ask for the collection by
        # (subject, pseudo). Never accept a collection name.
        collection = self._chroma.get_collection(subject, pseudo)
        raw = collection.query(
            query_embeddings=[query_vec],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )

        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]

        chunks: list[RetrievedChunk] = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            chunks.append(
                RetrievedChunk(
                    content=doc,
                    metadata=dict(meta) if meta else {},
                    distance=float(dist) if dist is not None else None,
                )
            )
        return chunks

    def get_chunks_for_document(
        self,
        subject: str,
        pseudo: str,
        document_id: str,
        k: int = 20,
    ) -> list[RetrievedChunk]:
        """Return the chunks of ``(subject, pseudo)`` belonging to ``document_id``.

        Used by the QCM generator (s03) to ground the LLM on a single source
        document. The query is double-locked: the collection is selected by
        ``(subject, pseudo)`` (multi-tenant), then filtered by
        ``document_id`` metadata (per-document). No semantic search — the
        generator wants the full document, not the closest chunks.

        Returns an empty list when no chunk matches. Raises ``ValueError``
        when ``document_id`` is not a valid UUID.
        """
        # Validate the UUID up-front so a malformed value never reaches
        # ChromaDB (and the caller can short-circuit on bad input).
        uuid.UUID(document_id)

        # Multi-tenant invariant: the pseudo is validated up front so a
        # malformed value never reaches ChromaDB naming.
        validate_pseudo(pseudo)

        # The ONLY way to access a tenant's data: ask for the collection by
        # (subject, pseudo). Never accept a collection name.
        collection = self._chroma.get_collection(subject, pseudo)
        raw = collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
            limit=k,
        )

        documents = raw.get("documents") or []
        metadatas = raw.get("metadatas") or []

        chunks: list[RetrievedChunk] = []
        for doc, meta in zip(documents, metadatas):
            chunks.append(
                RetrievedChunk(
                    content=doc,
                    metadata=dict(meta) if meta else {},
                    distance=None,
                )
            )
        return chunks
