"""LLM client factory + ``LlmClient`` Protocol.

Decisions locked in the s02 plan:

* ``minimax`` and ``openai`` both go through ``langchain_openai.ChatOpenAI``.
  OpenRouter exposes an OpenAI-compatible endpoint so ``minimax`` can be
  reached by setting ``base_url`` accordingly — no native SDK needed.
* ``ollama`` is NOT wired (its SDK is not in ``requirements.txt``) — calling
  the factory with that provider raises ``NotImplementedError``. A future
  story can add ``langchain-ollama`` and re-enable the path.
* The factory returns a thin ``_LangChainChatWrapper`` so the rest of the
  codebase depends on a small ``LlmClient`` Protocol, not on a LangChain
  type directly.

s09 extension: an ``astream`` method has been added to the Protocol so the
FastAPI SSE endpoint can yield tokens as they arrive from the upstream
chat model. The ``invoke`` method is preserved for the one-shot CLI and
the non-streaming agent path. Both go through the same wrapper.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage

from app.core.config import Settings


@runtime_checkable
class LlmClient(Protocol):
    """Minimal contract used by the agent. Implementations wrap a chat model.

    Marked ``runtime_checkable`` so callers (and tests) can use
    ``isinstance(instance, LlmClient)``.

    The s09 addition is :meth:`astream` — a passthrough async generator
    yielding :class:`AIMessageChunk` instances. The chunked streaming
    contract is the only way the FastAPI SSE endpoint (``/api/chat/stream``)
    can yield tokens as they arrive without buffering the full response.
    """

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        ...

    def astream(self, messages: list[BaseMessage]) -> AsyncIterator[AIMessageChunk]:
        ...


class _LangChainChatWrapper:
    """Adapt a LangChain ``BaseChatModel`` to the :class:`LlmClient` interface."""

    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat = chat_model

    def invoke(self, messages: list[BaseMessage]) -> AIMessage:
        # ``BaseChatModel.invoke`` already returns an ``AIMessage``; we type
        # the wrapper contract on that to keep the agent's import surface small.
        result = self._chat.invoke(messages)
        return result  # type: ignore[return-value]

    async def astream(self, messages: list[BaseMessage]) -> AsyncIterator[AIMessageChunk]:
        """Yield ``AIMessageChunk`` instances as the upstream model produces them.

        This is a thin pass-through to ``BaseChatModel.astream`` — the
        contract is whatever the upstream model decides to emit (the agent
        only consumes ``chunk.content``). Buffers and reorderings are
        upstream concerns; the wrapper preserves the order.
        """
        async for chunk in self._chat.astream(messages):
            yield chunk  # type: ignore[misc]


def build_llm_client(settings: Settings) -> LlmClient:
    """Build the LLM client from the application settings.

    Raises:
        NotImplementedError: if ``settings.llm_provider == "ollama"``.
        ValueError: for any other provider not in {``minimax``, ``openai``}.
    """
    provider = settings.llm_provider
    if provider == "ollama":
        raise NotImplementedError(
            "Ollama is not wired in s02 — adding it requires 'langchain-ollama' "
            "in requirements.txt. Tracked as a follow-up."
        )
    if provider not in {"minimax", "openai"}:
        raise ValueError(
            f"LLM provider {provider!r} is not supported by build_llm_client. "
            "Expected one of: minimax, openai."
        )

    # Lazy import so a missing SDK only blows up when actually used.
    from langchain_openai import ChatOpenAI

    chat = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key or None,
        base_url=settings.llm_base_url,
        temperature=settings.chat_temperature,
    )
    return _LangChainChatWrapper(chat)
