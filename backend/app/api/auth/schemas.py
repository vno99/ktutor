"""Pydantic schemas for the auth API (s12 + s13).

* :class:`RegisterRequest` — body of ``POST /api/auth/register``. The
  ``password`` field has a custom ``@field_validator`` that enforces
  the 72-byte UTF-8 bcrypt limit *in addition* to Pydantic's
  ``min_length`` of 8 characters (Pydantic's min_length counts chars,
  but bcrypt counts UTF-8 octets).
* :class:`RegisterResponse` — successful register (HTTP 201).
* :class:`RegisterErrorResponse` — 4xx/5xx body. The ``code`` field is
  a stable discriminator for the future frontend (s13).
* :class:`LoginRequest` / :class:`TokenPairResponse` /
  :class:`RefreshRequest` / :class:`AuthErrorResponse` (s13) — see
  the docstrings for each shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Pseudo bounds — aligned with the client-side regex enforced by ADR 011
# (``^[a-zA-Z0-9_]{3,32}$``) and the backend RAG store.
MIN_PSEUDO_CHARS = 3
MAX_PSEUDO_CHARS = 32
PSEUDO_PATTERN = r"^[a-zA-Z0-9_]+$"

# Password bounds — 8 chars minimum, 72 UTF-8 octets maximum (bcrypt limit).
MIN_PASSWORD_CHARS = 8
MAX_PASSWORD_BYTES = 72

# Stable machine codes for failure responses. Frontend (s13) switches
# on these to choose the right UI state without parsing the French
# human message. Aligned with ADR 005 § « register public crée
# eleve uniquement ».
RegisterErrorCode = Literal[
    "pseudo_taken",
    "invalid_pseudo",
    "weak_password",
    "internal",
]


class RegisterRequest(BaseModel):
    """Request body for ``POST /api/auth/register``."""

    pseudo: str = Field(
        ...,
        min_length=MIN_PSEUDO_CHARS,
        max_length=MAX_PSEUDO_CHARS,
        pattern=PSEUDO_PATTERN,
        description="Identifiant unique de l'élève (3-32 chars, alphanumérique + underscore).",
    )
    password: str = Field(
        ...,
        min_length=MIN_PASSWORD_CHARS,
        description=("Mot de passe (>= 8 chars, <= 72 octets UTF-8 à cause de la limite bcrypt)."),
    )

    @field_validator("password")
    @classmethod
    def _password_within_bcrypt_limit(cls, value: str) -> str:
        """Reject passwords whose UTF-8 encoding exceeds the bcrypt 72-byte limit.

        Pydantic ``min_length`` counts characters, not bytes. A French
        password like ``"é" * 37`` is 37 chars but 74 UTF-8 octets —
        bcrypt would refuse it with a low-level ``ValueError`` that we
        want to surface as a clean HTTP 422 instead of a 500.
        """
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password exceeds the 72-byte UTF-8 limit ({len(value.encode('utf-8'))} bytes)")
        return value


class RegisterResponse(BaseModel):
    """Successful register response (HTTP 201)."""

    pseudo: str = Field(..., description="Pseudo de l'élève (préservé tel quel).")


class RegisterErrorResponse(BaseModel):
    """Failure response body (4xx/5xx).

    The ``code`` discriminator lets the future frontend (s13) branch
    on the cause without parsing the French human message.
    """

    error: str = Field(..., description="Message d'erreur lisible.")
    code: RegisterErrorCode = Field(..., description="Code machine de l'erreur.")


# ---------------------------------------------------------------------------
# Login / refresh / logout (s13)
# ---------------------------------------------------------------------------

# Codes returned by ``POST /api/auth/login``, ``/api/auth/refresh``
# and ``/api/auth/logout``. Aligned with the middleware that raises
# 401 ``invalid_token`` and 403 ``forbidden`` (see
# ``app.core.auth.middleware``).
AuthErrorCode = Literal[
    "invalid_credentials",
    "invalid_token",
    "forbidden",
    "expired",
    "token_revoked",
]


class LoginRequest(BaseModel):
    """Request body for ``POST /api/auth/login``.

    The pseudo pattern is re-validated server-side as defence in
    depth (the frontend already enforces it for UX). The password
    is **not** length-bounded here — an overlong password returns
    401 ``invalid_credentials`` (generic) instead of 422, so the
    API never leaks the bcrypt limit through the wrong-password
    path.
    """

    pseudo: str = Field(
        ...,
        min_length=MIN_PSEUDO_CHARS,
        max_length=MAX_PSEUDO_CHARS,
        pattern=PSEUDO_PATTERN,
    )
    password: str = Field(..., min_length=1, max_length=MAX_PASSWORD_BYTES)


class TokenPairResponse(BaseModel):
    """Successful login / refresh response (HTTP 200).

    ``expires_in`` is in **seconds** (OAuth2 convention) and equals
    :data:`Settings.jwt_access_token_expire_minutes * 60`. The
    refresh token's lifetime is not exposed here; the client just
    has to call ``/refresh`` after the access token expires.
    """

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    """Request body for ``POST /api/auth/refresh``."""

    refresh_token: str = Field(..., min_length=1)


class AuthErrorResponse(BaseModel):
    """Failure response body for the login / refresh / logout endpoints.

    The ``code`` is the stable machine discriminator the frontend
    switches on. The human ``error`` message is intentionally short
    and never leaks *why* a token is invalid (Piège 2 bis).
    """

    error: str
    code: AuthErrorCode
