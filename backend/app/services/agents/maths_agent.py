"""Maths RAG agent — one-shot, temperature 0, citation-locked.

The agent is intentionally narrow:

* One system prompt, locked by tests (``SYSTEM_PROMPT``).
* One citation format, locked by tests (``CITATION_FORMAT``).
* No chat memory, no tool calls. Those arrive in later stories (s19 history).

s09 extension: an :meth:`astream` method exposes the same retrieval +
prompt + LLM pipeline as :meth:`ask` but yields ``StreamChunk`` events as
the upstream model produces them, so the FastAPI SSE endpoint can flush
tokens to the browser in real time. The one-shot ``ask`` path is
preserved unchanged — CLI and tests still use it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.agents.types import ChatResult, SourceCitation, StreamChunk
from app.services.llm.client import LlmClient
from app.services.rag.retriever import RetrievedChunk

SYSTEM_PROMPT = """Tu es un assistant pédagogique de mathématiques pour un élève de collège.

Règles strictes :
1. Tu réponds UNIQUEMENT à partir des extraits de documents (chunks) fournis
   par le système dans le message de l'utilisateur. Tu n'utilises aucune
   connaissance générale, aucune source externe.
2. Si les chunks fournis ne contiennent pas l'information nécessaire pour
   répondre à la question, tu dois répondre EXACTEMENT :
   "Je n'ai pas trouvé d'information sur ce sujet dans tes documents."
   Tu ne dois jamais inventer, extrapoler ou compléter avec des
   connaissances générales.
3. Lorsque tu utilises une information issue d'un chunk, tu dois citer la
   source au format exact : [source: <nom_du_fichier>, chunk <index>]
   — une citation par source utilisée.
4. Tu réponds en français, de manière claire et concise, au niveau collège.
"""


class _RetrieverLike(Protocol):
    """The slice of :class:`Retriever` the agent actually uses."""

    def query(self, subject: str, pseudo: str, question: str, k: int = 4) -> list[RetrievedChunk]:
        ...


class MathsAgent:
    """RAG-backed agent for the maths subject.

    The constructor takes only the dependencies it needs — no global state,
    no implicit settings lookup. This is what the CLI wires up.
    """

    def __init__(
        self,
        *,
        llm: LlmClient,
        retriever: _RetrieverLike,
        top_k: int = 4,
        no_document_message: str = "Je n'ai pas trouvé d'information sur ce sujet dans tes documents.",
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._top_k = top_k
        self._no_document_message = no_document_message

    def ask(self, subject: str, pseudo: str, question: str) -> ChatResult:
        """Return a citation-bearing answer grounded in the per-pseudo RAG.

        If the collection is empty (no document uploaded for this subject /
        pseudo), the fallback message is returned without invoking the LLM
        — preventing hallucinations on a cold start.
        """
        chunks = self._retriever.query(subject, pseudo, question, k=self._top_k)
        if not chunks:
            return ChatResult(answer=self._no_document_message, sources=[])

        user_prompt = _build_user_prompt(question, chunks)
        response: AIMessage = self._llm.invoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
        )

        sources = _collect_sources(chunks)
        return ChatResult(answer=response.content, sources=sources)

    async def astream(
        self, subject: str, pseudo: str, question: str
    ) -> AsyncIterator[StreamChunk]:
        """Yield the agent's response as ``StreamChunk`` events (s09).

        Mirrors :meth:`ask` semantics (same retrieval, same prompt, same
        no-document fallback) but yields one ``token`` event per upstream
        chunk, then a single ``done`` event carrying the RAG sources.

        The no-document short-circuit yields a single ``token`` whose
        content is the fallback message — the SSE frontend can still
        display "no document" as a single rendered message.
        """
        chunks = self._retriever.query(subject, pseudo, question, k=self._top_k)
        sources = _collect_sources(chunks)

        if not chunks:
            yield StreamChunk(content=self._no_document_message, event="token")
            yield StreamChunk(content="", event="done", sources=[])
            return

        user_prompt = _build_user_prompt(question, chunks)
        async for ai_chunk in self._llm.astream(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_prompt)]
        ):
            text = ai_chunk.content
            # Upstream models may emit tool-call metadata chunks with
            # empty content — we forward them as empty token events so
            # the SSE stream doesn't lose ordering. The router / frontend
            # can ignore empty tokens.
            yield StreamChunk(content=text, event="token")

        yield StreamChunk(content="", event="done", sources=sources)


# ------------------------------------------------------------------
# Internals — module-level so the French agent can share them
# ------------------------------------------------------------------


def _build_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    """Format the user message: question + the retrieved chunks."""
    lines: list[str] = [
        "Question de l'élève :",
        question,
        "",
        "Extraits de documents pertinents (utilise UNIQUEMENT ces extraits) :",
    ]
    for i, chunk in enumerate(chunks):
        filename = chunk.metadata.get("filename", "unknown")
        chunk_index = chunk.metadata.get("chunk_index", i)
        lines.append(
            f"[chunk {i} | source: {filename}, chunk {chunk_index}] {chunk.content}"
        )
    lines.append("")
    lines.append("Réponds en français, en citant tes sources au format demandé.")
    return "\n".join(lines)


def _collect_sources(chunks: list[RetrievedChunk]) -> list[SourceCitation]:
    """Build the citations list from the retrieved chunks' metadata."""
    sources: list[SourceCitation] = []
    for chunk in chunks:
        filename = chunk.metadata.get("filename")
        chunk_index = chunk.metadata.get("chunk_index")
        if filename and chunk_index is not None:
            sources.append(
                SourceCitation(filename=str(filename), chunk_index=int(chunk_index))
            )
    return sources
