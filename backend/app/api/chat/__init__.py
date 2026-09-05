"""Chat API domain (s09, s19).

The chat domain exposes three endpoints under the same
``/api/chat`` prefix:

* ``POST /api/chat/stream`` (s09) — Server-Sent Events
  stream of the agent's response. Body: ``{subject, question}``;
  the ``pseudo`` is taken from the JWT (s15).
* ``GET /api/chat/history`` (s19) — paginated list of the
  caller's past conversations, newest first.
* ``GET /api/chat/history/{conversation_id}`` (s19) — the
  conversation + its messages in one shot.

The two routers are exported separately so :mod:`app.main`
mounts them with a single ``include_router`` call per
endpoint group. The history router is defined in
:mod:`app.api.chat.history` (s19).
"""

from app.api.chat.history import router as chat_history_router
from app.api.chat.router import router as chat_router

__all__ = ["chat_history_router", "chat_router"]
