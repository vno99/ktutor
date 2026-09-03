"""FastAPI auth dependencies (s13, ADR 005).

Two building blocks are exposed:

* :func:`get_current_user` — a FastAPI dependency that extracts the
  ``Authorization: Bearer <token>`` header, validates the JWT via
  :func:`app.core.auth.jwt.decode_token`, fetches the
  corresponding :class:`User`, and returns it. On any failure the
  dependency raises ``HTTPException(401, ...)`` with a generic
  ``invalid_token`` body — the response never leaks *why* the
  token is invalid (Piège 2 bis : an expired token, a revoked
  ``jti``, a missing user, or a malformed JWT all return the same
  401 with the same body).
* :func:`require_role` — a higher-order dependency that wraps
  :func:`get_current_user` and rejects the request with
  ``HTTPException(403, ...)`` if the resolved user's role is not
  in the allow-list. The 401 / 403 split is intentional: 401 means
  *who are you?*; 403 means *I know who you are, but you cannot
  do this*.

The module depends on :mod:`app.core.auth.jwt` (the only verify
path) and on :class:`app.core.database.models.User`. There is no
global state; everything is per-request.
"""

from __future__ import annotations

from typing import Iterable

import jwt as pyjwt
from fastapi import Depends, Header, HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from app.core.auth.jwt import decode_token
from app.core.database.models import User, UserRole
from app.core.database.session import get_db

# 401 detail body — generic on purpose. The ``code`` discriminator
# matches :class:`app.api.auth.schemas.AuthErrorResponse`.
_INVALID_TOKEN_DETAIL: dict[str, str] = {
    "error": "Token invalide ou expiré.",
    "code": "invalid_token",
}

_FORBIDDEN_DETAIL: dict[str, str] = {
    "error": "Accès refusé.",
    "code": "forbidden",
}


def _raise_invalid_token() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=dict(_INVALID_TOKEN_DETAIL),
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    """Return the authenticated :class:`User`.

    * No ``Authorization`` header → 401 ``invalid_token``.
    * Header that is not ``Bearer ...`` → 401 ``invalid_token``.
    * Token that fails :func:`decode_token` (expired, revoked,
      wrong type, alg mismatch, missing claims) → 401
      ``invalid_token``. The underlying exception is logged at
      DEBUG level so the operator can correlate, but no token
      material or hash is ever written to the log.
    * Token whose ``sub`` resolves to a deleted user → 401
      ``invalid_token`` (same body as above — the response does
      not leak the existence of the user).
    """
    if not authorization:
        logger.debug("auth.middleware.missing_header")
        _raise_invalid_token()

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        logger.debug("auth.middleware.bad_scheme scheme={}", scheme)
        _raise_invalid_token()

    try:
        claims = decode_token(token, "access")
    except pyjwt.InvalidTokenError as exc:
        # Generic 401 — never surface the underlying reason to the
        # client. The log line carries the exception class so an
        # operator can spot an attack pattern.
        logger.debug("auth.middleware.decode_failed reason={}", exc.__class__.__name__)
        _raise_invalid_token()

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        logger.debug("auth.middleware.missing_sub")
        _raise_invalid_token()

    user = db.query(User).filter(User.pseudo == sub).one_or_none()
    if user is None:
        logger.info("auth.middleware.user_missing pseudo={}", sub)
        _raise_invalid_token()

    return user


def require_role(*allowed: UserRole):
    """Build a FastAPI dependency that requires a role from ``allowed``.

    The returned dependency first resolves :func:`get_current_user`
    (which can raise 401), then checks the user's role. A role
    mismatch raises 403 ``forbidden``.

    Usage::

        @router.get("/admin")
        def admin_only(user = Depends(require_role(UserRole.ADMIN))):
            ...
    """
    allowed_set: frozenset[UserRole] = frozenset(allowed)

    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_set:
            logger.info(
                "auth.middleware.forbidden pseudo={} role={} required={}",
                user.pseudo,
                user.role.value,
                sorted(r.value for r in allowed_set),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=dict(_FORBIDDEN_DETAIL),
            )
        return user

    return _dep


__all__ = ["get_current_user", "require_role"]
