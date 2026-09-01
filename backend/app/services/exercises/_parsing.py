"""Shared JSON-block extraction for LLM outputs (s03 + s06).

Both the QCM generator and the free-style generator expect the LLM to
return a JSON object (often wrapped in markdown fences, often preceded by a
short preamble). This helper centralises the recovery strategy:

  1. strip the markdown fences (``\\`\\`\\`json`` … ``\\`\\`\\```) and
     parse the whole payload;
  2. if that fails, look for the first ``{...}`` block via a permissive
     regex and parse it.

Centralising the helper means a fix here lands for both generators at
once — divergence between the two paths is a known source of bugs
(reviewed in the s03 review).
"""

from __future__ import annotations

import json
import re

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_block(text: str) -> str | None:
    """Best-effort JSON object extraction.

    LLM outputs often wrap JSON in markdown fences (``\\`\\`\\`json``) or
    add a short preamble. We try (a) stripping fences and parsing, (b) a
    regex search for the first ``{...}`` block and parsing that. Returns
    the raw JSON string on success, ``None`` on failure.
    """
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        json.loads(candidate)
        return candidate
    except (ValueError, TypeError):
        pass
    match = _JSON_OBJECT_RE.search(text)
    if match is None:
        return None
    block = match.group(0)
    try:
        json.loads(block)
    except (ValueError, TypeError):
        return None
    return block
