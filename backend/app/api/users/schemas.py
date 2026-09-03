"""Pydantic schemas for the admin user management API (s13b).

* :class:`CreateUserRequest` — body of ``POST /api/users``. Carries the
  shared pseudo + password invariants (length, pattern, 72-byte
  bcrypt limit) by **reusing the constants** declared in
  :mod:`app.api.auth.schemas` (DRY with s12). The ``role`` field is
  a strict ``Literal`` of the values an admin is allowed to create
  — ``parent`` or ``admin``. ``eleve`` is intentionally absent:
  pupils self-register via ``POST /api/auth/register`` (s12).
* :class:`CreateUserResponse` — 201 body. No JWT is issued; the new
  user must log in through ``POST /api/auth/login`` (s13).
* :class:`UpdateRoleRequest` — body of ``PUT /api/users/{pseudo}/role``.
  The role here is a wider ``Literal`` that **includes** ``eleve`` so
  an admin can demote a parent back to a pupil. The asymmetry with
  :class:`CreateUserRequest` is deliberate.
* :class:`UserResponse` — 200 body of the role-update endpoint.
* :class:`UserErrorCode` / :class:`UserErrorResponse` — failure bodies.

The new :data:`UserErrorCode` is a **separate** ``Literal`` from
:data:`app.api.auth.schemas.AuthErrorCode`: Pydantic cannot model
hierarchies, and the routers serialize the response into the matching
``*ErrorResponse`` model, so the same string appearing in both
``Literal``s is harmless duplication.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.api.auth.schemas import (
    MAX_PASSWORD_BYTES,
    MAX_PSEUDO_CHARS,
    MIN_PASSWORD_CHARS,
    MIN_PSEUDO_CHARS,
    PSEUDO_PATTERN,
)

# Stable machine codes for the admin user management endpoints.
# ``"forbidden"`` is duplicated from :data:`AuthErrorCode` on
# purpose (the routers serialize into different ``*ErrorResponse``
# models). See module docstring.
UserErrorCode = Literal[
    "invalid_pseudo",
    "weak_password",
    "pseudo_taken",
    "user_not_found",
    "self_demote_blocked",
    "forbidden",
    "internal",
]


# Roles an admin is allowed to assign at creation time. ``eleve`` is
# absent on purpose: pupils self-register through the public
# ``POST /api/auth/register`` endpoint (s12, ADR 005).
CreateUserRole = Literal["parent", "admin"]

# Roles an admin is allowed to set via ``PUT /api/users/{pseudo}/role``.
# Wider than :data:`CreateUserRole` so an admin can demote a parent
# back to ``eleve`` (or promote an ``eleve`` to ``parent``).
UpdateUserRole = Literal["eleve", "parent", "admin"]


class CreateUserRequest(BaseModel):
    """Request body for ``POST /api/users``.

    The pseudo and password invariants are enforced by Pydantic
    **before** the handler runs (422 on failure), mirroring
    :class:`RegisterRequest` without forcing an inheritance
    relationship — the two endpoints have different role semantics
    and we want each to express them locally.
    """

    pseudo: str = Field(
        ...,
        min_length=MIN_PSEUDO_CHARS,
        max_length=MAX_PSEUDO_CHARS,
        pattern=PSEUDO_PATTERN,
        description=(
            "Identifiant unique de l'utilisateur (3-32 chars, "
            "alphanumérique + underscore)."
        ),
    )
    password: str = Field(
        ...,
        min_length=MIN_PASSWORD_CHARS,
        description=(
            "Mot de passe (>= 8 chars, <= 72 octets UTF-8 à cause "
            "de la limite bcrypt)."
        ),
    )
    role: CreateUserRole = Field(
        ...,
        description="Rôle assigné à la création. ``eleve`` exclu (public register, s12).",
    )

    @field_validator("password")
    @classmethod
    def _password_within_bcrypt_limit(cls, value: str) -> str:
        """Reject passwords whose UTF-8 encoding exceeds the 72-byte bcrypt limit.

        Mirrors :meth:`RegisterRequest._password_within_bcrypt_limit`
        so a French password like ``"é" * 37`` returns a clean 422
        instead of a 500 from bcrypt.
        """
        encoded_len = len(value.encode("utf-8"))
        if encoded_len > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"password exceeds the 72-byte UTF-8 limit ({encoded_len} bytes)"
            )
        return value


class CreateUserResponse(BaseModel):
    """Successful create response (HTTP 201).

    No token is issued — the new user must log in through
    ``POST /api/auth/login`` (s13).
    """

    pseudo: str = Field(..., description="Pseudo du compte créé.")
    role: CreateUserRole = Field(..., description="Rôle assigné.")


class UpdateRoleRequest(BaseModel):
    """Request body for ``PUT /api/users/{pseudo}/role``."""

    role: UpdateUserRole = Field(
        ...,
        description="Nouveau rôle de l'utilisateur (``eleve`` / ``parent`` / ``admin``).",
    )


class UserResponse(BaseModel):
    """Successful role-update response (HTTP 200)."""

    pseudo: str = Field(..., description="Pseudo de l'utilisateur mis à jour.")
    role: UpdateUserRole = Field(..., description="Nouveau rôle.")


class UserErrorResponse(BaseModel):
    """Failure response body (4xx/5xx)."""

    error: str = Field(..., description="Message d'erreur lisible.")
    code: UserErrorCode = Field(..., description="Code machine de l'erreur.")


# ---------------------------------------------------------------------------
# s14 — parent-child link schemas
# ---------------------------------------------------------------------------
#
# The ``UserErrorCode`` literal above is reused as the failure code
# for the two new endpoints (``"user_not_found"`` and ``"forbidden"``
# are already declared). We do **not** introduce a separate
# ``ParentChildErrorCode`` — the same string appearing in two
# literals is the documented Pydantic constraint, and it would be
# duplication for no semantic gain.

ChildRole = Literal["eleve", "parent", "admin"]


class AddChildRequest(BaseModel):
    """Body of ``POST /api/users/{parent_pseudo}/children``.

    The ``child_pseudo`` field reuses the same invariants as
    :class:`CreateUserRequest.pseudo` — length, encoding, pattern.
    The handler is responsible for fetching the child by
    case-insensitive match (``func.lower``), so the value sent
    here can be of any case; only the *shape* is enforced here.
    """

    child_pseudo: str = Field(
        ...,
        min_length=MIN_PSEUDO_CHARS,
        max_length=MAX_PSEUDO_CHARS,
        pattern=PSEUDO_PATTERN,
        description=(
            "Pseudo de l'enfant à lier (3-32 chars, alphanumérique + underscore)."
        ),
    )


class ChildLinkResponse(BaseModel):
    """Successful ``POST .../children`` body (200 / 201)."""

    parent_pseudo: str = Field(..., description="Pseudo du parent (canonique, DB).")
    child_pseudo: str = Field(..., description="Pseudo de l'enfant (canonique, DB).")


class ChildResponse(BaseModel):
    """One element of the ``GET .../children`` list (200)."""

    child_pseudo: str = Field(..., description="Pseudo de l'enfant lié.")
    role: ChildRole = Field(..., description="Rôle du compte enfant.")


ChildrenListResponse = list[ChildResponse]
"""Body of ``GET /api/users/{parent_pseudo}/children`` (200).

A top-level JSON array. An empty list means the parent has no linked
children — a valid state (not a 404). FastAPI serialises a
``list[ChildResponse]`` directly as the response body, so no
wrapper class is needed (and Pydantic 2 does not need
``__root__`` for that case)."""


__all__ = [
    "AddChildRequest",
    "ChildLinkResponse",
    "ChildResponse",
    "ChildRole",
    "ChildrenListResponse",
    "CreateUserRequest",
    "CreateUserResponse",
    "CreateUserRole",
    "UpdateRoleRequest",
    "UpdateUserRole",
    "UserErrorCode",
    "UserErrorResponse",
    "UserResponse",
]
