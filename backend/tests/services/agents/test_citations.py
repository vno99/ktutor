"""Tests for the shared citation constants.

``CITATION_FORMAT`` and ``CITATION_RE`` are promoted out of
``maths_agent.py`` in s05 so every subject agent (maths, francais, and
the future ones) can rely on a single, locked citation contract. The
regex is the public API: any LLM answer that does not match it is
silently ignored by the agent's source parser, so a malformed constant
here would let citations leak unparsed.
"""

from __future__ import annotations

import re

from app.services.agents.citations import CITATION_FORMAT, CITATION_RE


class TestCitations:
    def test_citation_format_constant_is_locked(self) -> None:
        # The exact format is the s02 contract: ``[source: <file>, chunk <n>]``.
        # Changing it is a breaking change for the UI badge parsing in s11.
        assert CITATION_FORMAT == "[source: {filename}, chunk {chunk_index}]"

    def test_citation_regex_matches_real_citation(self) -> None:
        # The regex must accept a real, formatted citation (post-formatting).
        m = CITATION_RE.search("[source: cours.pdf, chunk 3]")
        assert m is not None
        assert m.group("filename") == "cours.pdf"
        assert m.group("chunk_index") == "3"

    def test_citation_regex_rejects_wrong_field(self) -> None:
        # A typo in the field name (``page`` instead of ``chunk``) must
        # be rejected so a buggy prompt is caught early.
        assert CITATION_RE.search("[source: foo.pdf, page 3]") is None
        assert CITATION_RE.search("[source: foo.pdf, chunk 3]") is not None

    def test_citation_regex_is_compiled_pattern(self) -> None:
        # Importing the constant must give a usable compiled regex, not
        # a string — otherwise the agent would have to recompile on every
        # call.
        assert isinstance(CITATION_RE, re.Pattern)
