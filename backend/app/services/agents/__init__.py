"""Specialised LangChain agents (one per subject) and their supervisor.

Public surface (s05):

* :class:`MathsAgent` — RAG-backed maths agent (s02).
* :class:`FrancaisAgent` — RAG-backed French agent (s05).
* :class:`SubjectSupervisor` — typed Python dispatcher (s05, ADR 003
  update). Routes by ``--subject`` flag. NOT a ``StateGraph`` langgraph
  — that swap is deferred to the content-routing iteration.
* :class:`SubjectAgent` — the Protocol the supervisor speaks against.
* :class:`ChatResult`, :class:`SourceCitation`, :class:`StreamChunk` —
  shared output schema (s05 + s09).
"""

from app.services.agents.citations import CITATION_FORMAT, CITATION_RE
from app.services.agents.francais_agent import FrancaisAgent
from app.services.agents.maths_agent import MathsAgent
from app.services.agents.supervisor import SubjectAgent, SubjectSupervisor
from app.services.agents.types import ChatResult, SourceCitation, StreamChunk

__all__ = [
    "CITATION_FORMAT",
    "CITATION_RE",
    "ChatResult",
    "FrancaisAgent",
    "MathsAgent",
    "SourceCitation",
    "StreamChunk",
    "SubjectAgent",
    "SubjectSupervisor",
]
