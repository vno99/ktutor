"""Embedding provider for the RAG pipeline.

Default backend: **FastEmbed** (ONNX, runs locally, no API key needed).
Fallback: **OpenAI** text-embedding-3-small, used only when ``LLM_PROVIDER=openai``
and ``OPENAI_API_KEY`` is set (see ADR 002).

The vision / OCR stack is *separate* and is not affected by this choice
(see ADR 008).
"""

from __future__ import annotations

import os
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Abstract embedding backend.

    Implementations must return one 384-dim float vector per input string
    (FastEmbed) — for OpenAI the dim is 1536 but the value is configurable at
    the call site through ``embed_documents``.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...


class FastEmbedProvider:
    """Local ONNX embeddings via fastembed (default)."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        # Import lazily so tests can patch the class without downloading the model.
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # ``TextEmbedding.embed`` is a generator of numpy arrays.
        return [list(map(float, vec)) for vec in self._model.embed(texts)]


class OpenAIEmbeddingProvider:
    """OpenAI embeddings, used only as a fallback (see ADR 002)."""

    def __init__(self, api_key: str | None = None, model: str = "text-embedding-3-small") -> None:
        from langchain_openai import OpenAIEmbeddings

        self._impl = OpenAIEmbeddings(
            api_key=api_key or os.environ.get("OPENAI_API_KEY", ""),
            model=model,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # ``OpenAIEmbeddings.embed_documents`` already returns list[list[float]].
        return self._impl.embed_documents(texts)


def build_embedding_provider(
    llm_provider: str,
    openai_api_key: str | None = None,
) -> EmbeddingProvider:
    """Factory selecting the embedding backend from settings.

    The rule:
    * ``openai`` provider with a non-empty key → OpenAI.
    * anything else → FastEmbed (local, free).
    """
    if llm_provider == "openai" and (openai_api_key or os.environ.get("OPENAI_API_KEY", "")):
        return OpenAIEmbeddingProvider(api_key=openai_api_key)
    return FastEmbedProvider()
