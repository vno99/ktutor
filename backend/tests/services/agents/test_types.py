"""Tests for the shared agent types (SourceCitation, ChatResult).

These types are extracted from ``maths_agent.py`` in s05 so that
``francais_agent.py`` and ``supervisor.py`` can import them without
creating a circular import. The types themselves are unchanged: a
``SourceCitation`` carries a (filename, chunk_index) pair, and a
``ChatResult`` bundles the answer text with the list of citations.
"""

from __future__ import annotations

from app.services.agents.types import ChatResult, SourceCitation


class TestTypes:
    def test_chat_result_round_trip(self) -> None:
        result = ChatResult(
            answer="Une dérivée mesure la pente.",
            sources=[SourceCitation(filename="cours.pdf", chunk_index=0)],
        )
        # Pydantic round-trip — ``model_dump`` then ``model_validate`` is
        # the cheapest way to assert the schema is serialisable and that
        # the public field names are stable.
        data = result.model_dump()
        assert data == {
            "answer": "Une dérivée mesure la pente.",
            "sources": [{"filename": "cours.pdf", "chunk_index": 0}],
        }
        restored = ChatResult.model_validate(data)
        assert restored == result

    def test_sourcecitation_accepts_int_chunk_index(self) -> None:
        # The chunk_index is 0-based and stored as int — agents MUST NOT
        # serialize it as a string.
        c = SourceCitation(filename="a.pdf", chunk_index=3)
        assert isinstance(c.chunk_index, int)
        assert c.chunk_index == 3
