"""JWT encode / decode helpers (s13, ADR 005).

Three responsibilities:

* :func:`create_access_token` — produces a short-lived (30 min by
  default) bearer token carrying ``{sub, role, iat, exp, jti, type}``.
* :func:`create_refresh_token` — same shape, ``type="refresh"``,
  long-lived (7 days by default). Refresh tokens are **rotated** by
  :func:`app.api.auth.router.refresh`; the old ``jti`` is added
  to the blacklist before the new pair is returned.
* :func:`decode_token` — the **only** verify path. It:

  - requires the RS256 algorithm explicitly (Piège 1 — the
    whitelist rejects ``alg: none`` and ``alg: HS256`` tokens),
  - requires the ``sub``, ``role``, ``iat``, ``exp``, ``jti``,
    ``type`` claims (Pydantic-equivalent — pyjwt raises
    ``MissingRequiredClaimError``),
  - checks ``type`` against the caller's expectation (Piège 3 —
    passing an access token to ``/refresh`` is rejected),
  - checks the blacklist (revoked ``jti`` is rejected).

Keys are loaded from the paths declared in :class:`Settings`. The
PEM files are written by ``backend/scripts/generate_jwt_keys.py``.
The keys are cached at module level after the first read — loading
a PEM on every call would add measurable cost to ``decode_token``.
"""

from __future__ import annotations

import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal, get_args

import jwt as pyjwt
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key,
    load_pem_public_key,
)

from app.core.auth import token_blacklist
from app.core.config import get_settings
from app.core.database.models import UserRole

# Whitelisted algorithms for ``decode``. Hardcoded — never read from
# the token's own header (Piège 1 — alg-confusion attack). The set
# has a single element today; if the project later adds RS384 /
# RS512, extend the set here AND add a knob to ``Settings``.
_ALLOWED_ALGORITHMS: tuple[str, ...] = ("RS256",)

_REQUIRED_CLAIMS: tuple[str, ...] = (
    "sub",
    "role",
    "iat",
    "exp",
    "jti",
    "type",
)

TokenType = Literal["access", "refresh"]


# ---------------------------------------------------------------------------
# Key loading (cached)
# ---------------------------------------------------------------------------


_private_key = None
_public_key = None


def _load_private_key():
    """Load the private key from :data:`Settings.jwt_private_key_path`.

    Cached at module level because PEM deserialization is not free
    (~1ms) and the key is needed on every ``create_access_token``
    call.
    """
    global _private_key
    if _private_key is None:
        path = Path(get_settings().jwt_private_key_path)
        _private_key = load_pem_private_key(path.read_bytes(), password=None)
    return _private_key


def _load_public_key():
    """Load the public key from :data:`Settings.jwt_public_key_path`."""
    global _public_key
    if _public_key is None:
        path = Path(get_settings().jwt_public_key_path)
        _public_key = load_pem_public_key(path.read_bytes())
    return _public_key


def reset_key_cache() -> None:
    """Test-only — drop the cached key handles so a new ``Settings``
    (``JWT_*_KEY_PATH``) is picked up on the next call."""
    global _private_key, _public_key
    _private_key = None
    _public_key = None


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------


def _now() -> int:
    return int(time.time())


def _create_token(
    pseudo: str,
    role: UserRole,
    expires_delta: timedelta,
    token_type: TokenType,
) -> str:
    settings = get_settings()
    now = _now()
    payload: dict[str, Any] = {
        "sub": pseudo,
        "role": role.value,
        "iat": now,
        "exp": now + int(expires_delta.total_seconds()),
        "jti": str(uuid.uuid4()),
        "type": token_type,
    }
    return pyjwt.encode(
        payload,
        _load_private_key(),
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(
    pseudo: str,
    role: UserRole,
    expires_delta: timedelta | None = None,
) -> str:
    """Produce a signed RS256 access token.

    The default lifetime is :data:`Settings.jwt_access_token_expire_minutes`
    (30 min). ``expires_delta`` lets callers override for tests
    (``timedelta(seconds=-1)`` to forge an already-expired token).
    """
    settings = get_settings()
    delta = expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    return _create_token(pseudo, role, delta, "access")


def create_refresh_token(pseudo: str, role: UserRole) -> str:
    """Produce a signed RS256 refresh token.

    The lifetime is :data:`Settings.jwt_refresh_token_expire_days`
    (7 days). The refresh helper does not accept ``expires_delta``
    — refresh tokens are not exercised in unit tests; the test
    that needs an expired refresh hand-crafts one.
    """
    settings = get_settings()
    delta = timedelta(days=settings.jwt_refresh_token_expire_days)
    return _create_token(pseudo, role, delta, "refresh")


# ---------------------------------------------------------------------------
# Decode
# ---------------------------------------------------------------------------


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    """Verify a JWT and return its claims.

    Raises :class:`jwt.InvalidTokenError` (or one of its subclasses:
    ``ExpiredSignatureError``, ``MissingRequiredClaimError``,
    ``InvalidAlgorithmError``) on any failure. The router is
    responsible for converting the error into a 401 ``invalid_token``.

    The algorithm whitelist is **hardcoded** to :data:`_ALLOWED_ALGORITHMS`
    so a token with ``alg: none`` or ``alg: HS256`` is rejected even
    if the upstream library would accept it. The ``type`` claim is
    checked against ``expected_type`` to prevent the access-vs-
    refresh swap (Piège 3). The ``jti`` is checked against the
    in-process blacklist.
    """
    if expected_type not in get_args(TokenType):
        raise ValueError(f"expected_type must be one of {get_args(TokenType)!r}")

    try:
        claims = pyjwt.decode(
            token,
            _load_public_key(),
            algorithms=list(_ALLOWED_ALGORITHMS),
            options={"require": list(_REQUIRED_CLAIMS)},
        )
    except pyjwt.InvalidTokenError:
        # Let the specific subclass (ExpiredSignatureError,
        # MissingRequiredClaimError, ...) propagate unchanged so the
        # router can format the response. We do not log the token
        # itself here.
        raise

    if claims.get("type") != expected_type:
        raise pyjwt.InvalidTokenError(
            f"token type mismatch: expected {expected_type!r}, "
            f"got {claims.get('type')!r}"
        )

    jti = claims.get("jti")
    if not isinstance(jti, str) or not jti:
        raise pyjwt.InvalidTokenError("missing jti claim")
    if token_blacklist.is_revoked(jti):
        # The blacklist is the canonical place where the message
        # "revoked" is exposed. The router maps this to a 401 with
        # ``code=invalid_token`` (the contract does not differentiate
        # expired from revoked for the client).
        raise pyjwt.InvalidTokenError("token revoked")

    return claims


__all__ = [
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "reset_key_cache",
    "TokenType",
]
