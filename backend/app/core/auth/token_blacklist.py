"""In-process JWT ``jti`` revocation list (s13).

The blacklist is a **module-level set** of ``jti`` strings. The set
is consulted by :func:`app.core.auth.jwt.decode_token` on every
verify; a hit means the token has been revoked (typically by
``POST /api/auth/logout`` or by ``POST /api/auth/refresh`` when an
old refresh is rotated out).

Storage and trade-offs:

* **In-memory only** (cf. ADR 005). The POC runs under a single
  ``uvicorn`` process and does not need to coordinate with peers.
* **Not durable**. A process restart drops every ``jti``. Acceptable
  for the POC: the worst that happens is that a token whose
  ``exp`` is still in the future is treated as valid after a
  restart. The window is bounded by the access-token lifetime
  (:data:`Settings.jwt_access_token_expire_minutes`, default 30 min).
* **Multi-worker unsafe**. Two ``uvicorn --workers 2`` processes
  hold two independent blacklists; a token revoked on worker A is
  still accepted on worker B. Documented as s15+ debt. Production
  is expected to swap the set for a Redis SET or a PostgreSQL
  table.

Thread safety: the Python GIL makes ``set.add`` atomic for
strings, and FastAPI's ``def`` endpoints run on a thread pool.
The :func:`add` / :func:`is_revoked`` / :func:`clear` contract is
safe under FastAPI's default worker model.
"""

from __future__ import annotations

_revoked: set[str] = set()


def add(jti: str) -> None:
    """Mark ``jti`` as revoked. Idempotent."""
    _revoked.add(jti)


def is_revoked(jti: str) -> bool:
    """Return ``True`` iff ``jti`` is in the revocation set."""
    return jti in _revoked


def clear() -> None:
    """Empty the revocation set. Test-only — production code never calls it."""
    _revoked.clear()


__all__ = ["add", "is_revoked", "clear"]
