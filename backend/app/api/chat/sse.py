"""SSE formatting helpers (s09).

The format of a Server-Sent Event is::

    data: <payload as a single line>\\n\\n

Two pitfalls the helper avoids (research § 4.9):

* Trailing ``\\n\\n`` is required, otherwise the browser never fires
  ``onmessage``.
* ``ensure_ascii=False`` preserves non-ASCII characters (French
  accents) in the JSON payload, so the browser does not have to
  decode ``\\u00xx`` sequences.
"""

from __future__ import annotations

import json


def format_sse(payload: dict) -> bytes:
    """Encode ``payload`` as a single SSE event.

    Returns a single ``bytes`` object suitable to ``yield`` from a
    :class:`fastapi.responses.StreamingResponse` generator. The payload
    is serialized to compact JSON (no trailing whitespace) and
    ``ensure_ascii=False`` is set so the wire bytes are UTF-8, not
    ASCII-escaped Unicode.
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()
