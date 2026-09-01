"""Shared citation constants for specialised agents.

The format and the regex are promoted out of
:mod:`app.services.agents.maths_agent` in s05 so every subject agent
(maths, francais, and the future ones) can rely on a single, locked
citation contract. The format is consumed by the LLM (the agent's
system prompt must instruct the model to emit it verbatim); the regex
is consumed by the agent's source parser and by the future UI badge
renderer (s11).
"""

from __future__ import annotations

import re

CITATION_FORMAT = "[source: {filename}, chunk {chunk_index}]"
"""Citation string format. Locked by AC2 — agents must produce a string
that matches the regex ``\\[source: [^,]+, chunk \\d+\\]``."""

CITATION_RE = re.compile(r"\[source: (?P<filename>[^,]+), chunk (?P<chunk_index>\d+)\]")
"""Compiled regex used to extract ``(filename, chunk_index)`` pairs from
LLM answers. The named groups keep the parser readable; the
``chunk_index`` is captured as a string and converted to ``int`` by the
caller (see :class:`app.services.agents.maths_agent.MathsAgent._collect_sources`)."""
