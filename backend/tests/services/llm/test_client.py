"""Tests for the LLM client factory.

The factory routes ``minimax`` and ``openai`` through the OpenAI-compatible
``ChatOpenAI`` (so we don't need a native minimax SDK); ``ollama`` is
intentionally not wired and raises ``NotImplementedError`` (its SDK is
absent from ``requirements.txt``).
"""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.config import Settings
from app.services.llm.client import LlmClient, build_llm_client


class TestFactoryProvider:
    def test_openai_returns_wrapper(self) -> None:
        settings = Settings(
            llm_provider="openai",
            llm_api_key="sk-test",
            llm_model="gpt-4o-mini",
            llm_base_url="https://api.openai.com/v1",
        )
        client = build_llm_client(settings)
        assert isinstance(client, LlmClient)

    def test_minimax_routes_via_openrouter(self) -> None:
        settings = Settings(
            llm_provider="minimax",
            llm_api_key="sk-or-test",
            llm_model="minimax/minimax-m3:free",
            llm_base_url="https://openrouter.ai/api/v1",
        )
        client = build_llm_client(settings)
        assert isinstance(client, LlmClient)

    def test_ollama_raises_not_implemented(self) -> None:
        settings = Settings(
            llm_provider="ollama",
            llm_api_key="",
            llm_model="llama3",
            llm_base_url="http://localhost:11434",
        )
        with pytest.raises(NotImplementedError):
            build_llm_client(settings)

    def test_unknown_provider_raises(self) -> None:
        # ``Settings`` enforces the provider literal at construction time, so we
        # bypass it and call the factory directly with an invalid value.
        settings = Settings(
            llm_provider="openai",  # valid for construction
            llm_api_key="k",
            llm_model="m",
            llm_base_url="http://x",
        )
        # Patch the provider attribute post-hoc to simulate a runtime mismatch.
        object.__setattr__(settings, "llm_provider", "bogus-provider")
        with pytest.raises(ValueError):
            build_llm_client(settings)


class TestWrapperInvocation:
    def test_wrapper_invokes_underlying_chat_model(self) -> None:
        """The wrapper must adapt a ``BaseChatModel`` to the ``LlmClient`` contract."""
        fake = FakeListChatModel(responses=["reponse"])
        from app.services.llm.client import _LangChainChatWrapper

        wrapper = _LangChainChatWrapper(fake)
        out = wrapper.invoke([SystemMessage(content="sys"), HumanMessage(content="q")])
        assert isinstance(out, AIMessage)
        assert out.content == "reponse"
