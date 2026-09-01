"""Subject supervisor factory (s09).

The factory wires a :class:`SubjectSupervisor` with the same plumbing
the CLI uses (ChromaDB + embeddings + LLM + MathsAgent + FrancaisAgent),
but exposes a single function the FastAPI ``Depends`` can call.

The factory is also reused by the CLI (``app/cli.py`` keeps its own
``_build_chat_service`` for the one-shot path; future stories can
migrate that onto the factory once the streaming path proves stable).
"""

from __future__ import annotations

from app.core.config import Settings
from app.services.agents import (
    FrancaisAgent,
    MathsAgent,
    SubjectSupervisor,
)
from app.services.llm.client import build_llm_client
from app.services.rag.chroma_store import ChromaStore
from app.services.rag.embeddings import build_embedding_provider
from app.services.rag.retriever import Retriever


def build_subject_supervisor(settings: Settings) -> SubjectSupervisor:
    """Build a :class:`SubjectSupervisor` from the application settings.

    Mirrors ``app.cli._build_chat_service`` so the API and the CLI share
    the same wiring. ``ChromaStore`` is created against the configured
    ``chroma_persist_directory`` (the same path the upload command
    writes to, so the stream endpoint sees the documents the student
    uploaded).
    """
    chroma = ChromaStore(persist_directory=settings.chroma_persist_directory)
    embeddings = build_embedding_provider(
        llm_provider=settings.llm_provider,
        openai_api_key=settings.openai_api_key,
    )
    llm = build_llm_client(settings)
    retriever = Retriever(chroma_store=chroma, embeddings=embeddings)
    maths = MathsAgent(
        llm=llm,
        retriever=retriever,
        top_k=settings.chat_top_k,
        no_document_message=settings.chat_no_document_message,
    )
    francais = FrancaisAgent(
        llm=llm,
        retriever=retriever,
        top_k=settings.chat_top_k,
        no_document_message=settings.chat_no_document_message,
    )
    return SubjectSupervisor(
        {
            "maths": maths,
            "francais": francais,
        }
    )
