"""Chat history read-side service (s19).

Exposes :class:`ChatHistoryService` — the closest-to-the-DB layer
for the ``/api/chat/history`` endpoints. The router (T3) calls this
service to keep the SQL in one place; the cross-tenant filter
(``student_pseudo`` from the JWT) is applied INSIDE the SQL query
(not after a load) so a race between the load and the filter cannot
leak cross-tenant data.

Persistence is a separate concern (T5 — the stream-side
persistence in ``app/api/chat/router.py``). The service is
read-only; writes are best-effort and live in the router because
the streaming flow needs them in a ``try/finally``.
"""
