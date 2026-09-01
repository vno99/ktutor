"""French RAG agent — one-shot, temperature 0, citation-locked, subject-locked.

Identical in shape to :class:`app.services.agents.maths_agent.MathsAgent`.
The only differences are:

* the :data:`SYSTEM_PROMPT` (literary register, college-level, refusal rules,
  mandatory citations) — locked by tests,
* a defensive ``subject == "francais"`` check at the top of both
  :meth:`ask` and :meth:`astream` so a wrong caller cannot silently
  query the wrong ChromaDB collection (defense in depth, s05 + s09).

The two agents share the same :class:`Retriever` and the same
:class:`LlmClient` interfaces — no duplication, no new dependency.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.services.agents.citations import CITATION_FORMAT
from app.services.agents.maths_agent import (
    _build_user_prompt,
    _collect_sources,
    _RetrieverLike,
)
from app.services.agents.types import ChatResult, StreamChunk
from app.services.llm.client import LlmClient

# 5 invariants from the research D4, locked by tests:
# 1. Response in French, college-level (collège).
# 2. Citation format locked to CITATION_FORMAT (the exact string).
# 3. No general knowledge — grounded in the supplied chunks only.
# 4. Polite refusal if the chunks do not answer the question.
# 5. No fabrication, no extrapolation.
SYSTEM_PROMPT = f"""Tu es un assistant pédagogique de français pour un élève de collège.

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
   source au format exact : {CITATION_FORMAT}
   — une citation par source utilisée.
4. Tu réponds en français, de manière claire, concise et adaptée à un
   élève de collège (ni registre littéraire soutenu, ni familier).
"""


class FrancaisAgent:
    """RAG-backed agent for the French subject.

    Mirrors :class:`MathsAgent` 1-for-1 except for the system prompt and
    the ``subject == "francais"`` invariant. The constructor takes only
    the dependencies it needs — no global state, no implicit settings
    lookup. This is what the CLI wires up via the supervisor.
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

        Defense in depth: the agent refuses any ``subject`` other than
        ``"francais"`` BEFORE touching the retriever, so a misrouted call
        cannot accidentally query the maths collection (AC5).
        """
        if subject != "francais":
            raise ValueError(
                f"FrancaisAgent only handles subject 'francais' (got {subject!r})."
            )

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

        Mirrors :meth:`ask` semantics (same subject guard, same retrieval,
        same prompt, same no-document fallback) but yields one ``token``
        event per upstream chunk, then a single ``done`` event carrying
        the RAG sources.
        """
        if subject != "francais":
            raise ValueError(
                f"FrancaisAgent only handles subject 'francais' (got {subject!r})."
            )

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
            yield StreamChunk(content=ai_chunk.content, event="token")

        yield StreamChunk(content="", event="done", sources=sources)


# Re-export the protocol so callers can import it from this module too.
__all__ = ["SYSTEM_PROMPT", "FrancaisAgent", "_RetrieverLike"]
