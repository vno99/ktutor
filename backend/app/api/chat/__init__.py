"""Chat API domain (s09).

The chat domain exposes a single streaming endpoint:

* ``POST /api/chat/stream`` — Server-Sent Events stream of the agent's
  response. Body: ``{pseudo, subject, question}``.

Other endpoints (chat history, conversations) ship in later stories
(s19 history, s18 conversation persistence).
"""
