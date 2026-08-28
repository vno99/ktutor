"""ChromaDB wrapper enforcing the per-(subject, pseudo) collection convention.

Convention (ADR 004): each (subject, pseudo) pair maps to a single collection
named ``rag_<subject>_<pseudo>``. The class validates the pseudo before
constructing the name, so an invalid pseudo never reaches ChromaDB.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

import chromadb

PSEUDO_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
"""Strict validation: alphanumeric + underscore, 3-32 chars.

Mismatches the well-known email / space / dash patterns that would corrupt
the collection name. The CLI is responsible for surfacing this rule to users
(code 5 on rejection)."""


class InvalidPseudoError(ValueError):
    """Raised when the pseudo does not satisfy the multi-tenant contract."""


def validate_pseudo(pseudo: str) -> None:
    """Raise :class:`InvalidPseudoError` if ``pseudo`` is not safe to use in a name."""
    if not isinstance(pseudo, str) or not PSEUDO_RE.match(pseudo):
        raise InvalidPseudoError(
            f"Pseudo {pseudo!r} invalide. Attendu: regex ^[a-zA-Z0-9_]{{3,32}}$"
        )


def collection_name(subject: str, pseudo: str) -> str:
    """Build the canonical collection name; the caller is expected to validate first."""
    return f"rag_{subject}_{pseudo}"


class _ClientLike(Protocol):
    def get_or_create_collection(self, name: str, embedding_function: Any | None = None): ...
    def get_collection(self, name: str, embedding_function: Any | None = None): ...
    def list_collections(self) -> list: ...
    def delete_collection(self, name: str) -> None: ...


class ChromaStore:
    """Thin wrapper around a ChromaDB client.

    We *do not* pass an ``embedding_function`` to the collection: embeddings
    are computed up-stream by :class:`EmbeddingProvider` and stored as
    pre-computed vectors. This keeps the dependency between the two services
    one-directional (RAG owns the embedding choice).
    """

    def __init__(self, client: _ClientLike | None = None, persist_directory: str | None = None) -> None:
        if client is not None:
            self._client = client
        else:
            # ``chromadb.PersistentClient`` is the default; tests inject ``EphemeralClient``.
            self._client = chromadb.PersistentClient(path=persist_directory or "./chroma_data")

    def get_collection(self, subject: str, pseudo: str):
        """Return the collection for ``(subject, pseudo)``, creating it on first use."""
        validate_pseudo(pseudo)
        name = collection_name(subject, pseudo)
        return self._client.get_or_create_collection(name=name, embedding_function=None)

    def add_chunks(
        self,
        collection,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        """Add pre-embedded chunks to ``collection``.

        Each chunk dict must contain ``id`` (str), ``content`` (str) and
        ``metadata`` (dict). IDs are deterministic (caller-controlled) so
        re-ingesting the same file is idempotent at the ChromaDB level.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks / embeddings length mismatch: {len(chunks)} vs {len(embeddings)}"
            )
        if not chunks:
            return
        collection.add(
            ids=[c["id"] for c in chunks],
            embeddings=embeddings,
            documents=[c["content"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
        )

    def list_collections_for_pseudo(self, pseudo: str) -> list[str]:
        """List collection names belonging to ``pseudo`` (across subjects)."""
        validate_pseudo(pseudo)
        suffix = f"_{pseudo}"
        return [c.name for c in self._client.list_collections() if c.name.endswith(suffix)]
