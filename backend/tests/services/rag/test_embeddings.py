"""Tests for the embedding provider factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.rag.embeddings import (
    FastEmbedProvider,
    OpenAIEmbeddingProvider,
    build_embedding_provider,
)


class TestFactory:
    def test_default_provider_is_fastembed(self) -> None:
        with patch("app.services.rag.embeddings.FastEmbedProvider") as fastembed_cls:
            fastembed_cls.return_value = MagicMock(spec=FastEmbedProvider)
            provider = build_embedding_provider(llm_provider="minimax", openai_api_key="")
            assert isinstance(provider, MagicMock)
            fastembed_cls.assert_called_once()

    def test_openai_selected_when_provider_and_key(self) -> None:
        with patch("app.services.rag.embeddings.OpenAIEmbeddingProvider") as openai_cls:
            openai_cls.return_value = MagicMock(spec=OpenAIEmbeddingProvider)
            provider = build_embedding_provider(llm_provider="openai", openai_api_key="sk-test")
            assert provider is not None
            openai_cls.assert_called_once()
            # The factory must forward the key.
            assert openai_cls.call_args.kwargs.get("api_key") == "sk-test"

    def test_fastembed_when_openai_provider_but_no_key(self) -> None:
        with patch("app.services.rag.embeddings.FastEmbedProvider") as fastembed_cls:
            fastembed_cls.return_value = MagicMock(spec=FastEmbedProvider)
            # Even if the provider says openai, an empty key falls back to local.
            build_embedding_provider(llm_provider="openai", openai_api_key="")
            fastembed_cls.assert_called_once()
