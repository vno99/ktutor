"""Auth endpoints (s12 register, s13 login / refresh / logout).

The router is the **only** HTTP entry point to the auth subsystem.
It delegates to:

* :mod:`app.core.auth.passwords` — bcrypt hash + verify.
* :mod:`app.core.auth.jwt` — RS256 encode / decode + whitelist.
* :mod:`app.core.auth.middleware` — ``get_current_user`` dependency.
* :mod:`app.core.auth.token_blacklist` — ``jti`` revocation list.

Logging never includes the password, the hash, the JWT, the
``jti``, or the refresh token (cf. AGENTS.md § Backend logging
and research § Traps 4, 16).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from loguru import logger
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth.schemas import (
    AuthErrorResponse,
    LoginRequest,
    RefreshRequest,
    RegisterErrorCode,
    RegisterErrorResponse,
    RegisterRequest,
    RegisterResponse,
    TokenPairResponse,
)
from app.core.auth import token_blacklist
from app.core.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.auth.middleware import get_current_user
from app.core.auth.passwords import hash_password, verify_password
from app.core.config import get_settings
from app.core.database.models import User, UserRole
from app.core.database.session import get_db
from app.core.i18n import get_message


def _locale_from_header(accept_language: str | None) -> str:
    if accept_language is None:
        return "fr"
    primary = accept_language.split(",")[0].strip()
    lang = primary.split(";")[0].strip().lower()[:2]
    return lang if lang in ("en", "fr") else ("en" if "en" in accept_language.lower() else "fr")

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Module-level dummy hash — timing-constant login (Piège 2).
# ``verify_password`` is constant-time over the bcrypt cost factor
# (~250ms at cost 12), regardless of whether the row exists. The
# dummy hash is computed once at import time and is the
# ``verify_password`` target when ``user is None``. This equalises
# the timing of the "unknown pseudo" and "wrong password" branches
# so an attacker cannot probe the database through latency.
# ---------------------------------------------------------------------------
_DUMMY_HASH: str = hash_password("dummy_password_for_timing")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_error_payload(*, message: str, code: RegisterErrorCode) -> dict:
    """Canonical error body for the register endpoint."""
    return RegisterErrorResponse(error=message, code=code).model_dump()


def _auth_error_payload(*, message: str, code: str) -> dict:
    """Canonical error body for the login / refresh / logout endpoints."""
    return AuthErrorResponse(error=message, code=code).model_dump()  # type: ignore[arg-type]


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterResponse,
    responses={
        409: {"model": RegisterErrorResponse, "description": "Pseudo déjà pris."},
        422: {"model": RegisterErrorResponse, "description": "Validation Pydantic."},
        500: {"model": RegisterErrorResponse, "description": "Erreur interne."},
    },
)
def register(
    body: RegisterRequest,
    db: Session = Depends(get_db),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> RegisterResponse:
    """Create a new ``eleve`` account.

    The body is validated by Pydantic BEFORE this handler runs
    (422 on invalid pseudo, weak password, or password whose UTF-8
    encoding exceeds the 72-byte bcrypt limit). The handler then
    performs a fast-fail pre-check, hashes the password, and inserts
    a new ``User`` row. The DB-level functional unique index is the
    ultimate source of truth for case-insensitive uniqueness; the
    ``catch IntegrityError`` covers the race where two concurrent
    requests pass the pre-check at the same time.
    """
    # Step 1 — pre-check (UX, not security; the DB constraint is the
    # last line of defence, see ``models.py``).
    existing = db.query(User).filter(func.lower(User.pseudo) == body.pseudo.lower()).first()
    if existing is not None:
        logger.info("register.conflict pseudo={}", body.pseudo)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_register_error_payload(
                message=get_message(_locale_from_header(accept_language), "register", "pseudo_taken"),
                code="pseudo_taken",
            ),
        )

    # Step 2 — hash. Pydantic already guards the 72-byte limit, so
    # the ValueError here is a defensive double-check.
    password_hash = hash_password(body.password)

    # Step 3 — insert.
    user = User(
        pseudo=body.pseudo,
        password_hash=password_hash,
        role=UserRole.ELEVE,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Race condition: a concurrent request created the same pseudo
        # between our pre-check and our commit. The DB constraint
        # rejects our row; roll back and return the same 409 the
        # pre-check would have.
        db.rollback()
        logger.info("register.race_conflict pseudo={}", body.pseudo)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_register_error_payload(
                message=get_message(_locale_from_header(accept_language), "register", "pseudo_taken"),
                code="pseudo_taken",
            ),
        )
    except Exception as exc:  # noqa: BLE001 - intentional: convert to 500
        db.rollback()
        logger.error(
            "register.unexpected pseudo={} err={}",
            body.pseudo,
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_register_error_payload(
                message=get_message(_locale_from_header(accept_language), "register", "internal"),
                code="internal",
            ),
        )
    db.refresh(user)

    logger.info("register.created pseudo={}", body.pseudo)
    return RegisterResponse(pseudo=user.pseudo)


# ---------------------------------------------------------------------------
# POST /api/auth/login (s13)
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=TokenPairResponse,
    responses={
        401: {"model": AuthErrorResponse, "description": "Identifiants invalides."},
    },
)
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
) -> TokenPairResponse:
    """Authenticate a user and return an access + refresh token pair.

    The endpoint is timing-constant (Piège 2): the "unknown pseudo"
    branch invokes ``verify_password`` on a dummy hash so the
    response time matches the "wrong password" branch within the
    bcrypt cost factor. The 401 body is identical in both cases.
    """
    # Step 1 — case-insensitive lookup. ``User.pseudo`` preserves
    # case; the case-insensitive unique index (D3 s12) backs the
    # equality.
    user = (
        db.query(User)
        .filter(func.lower(User.pseudo) == body.pseudo.lower())
        .one_or_none()
    )

    # Step 2 — verify. If the user does not exist, ``verify_password``
    # is called on the dummy hash; the call is constant-time and
    # the cost factor is identical to a real hash. The decision
    # (``if``) is taken **after** the verify so the timing is
    # uniform.
    password_ok = (
        verify_password(body.password, user.password_hash)
        if user is not None
        else verify_password(body.password, _DUMMY_HASH)
    )

    if user is None or not password_ok:
        # Generic 401 — same body whether the pseudo is unknown or
        # the password is wrong (Piège 2 + 2 bis). The log line
        # carries the pseudo provided so an operator can spot a
        # brute-force pattern, but never the password or the hash.
        logger.info("login.failed pseudo={}", body.pseudo)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_auth_error_payload(
                message=get_message(_locale_from_header(accept_language), "login", "invalid_credentials"),
                code="invalid_credentials",
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 3 — issue tokens. The role is taken from the DB row, not
    # the request body, so an admin who demoted the user between
    # requests cannot be bypassed.
    settings = get_settings()
    access = create_access_token(user.pseudo, user.role)
    refresh = create_refresh_token(user.pseudo, user.role)
    logger.info("login.success pseudo={} role={}", user.pseudo, user.role.value)
    return TokenPairResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ---------------------------------------------------------------------------
# POST /api/auth/refresh (s13)
# ---------------------------------------------------------------------------


@router.post(
    "/refresh",
    status_code=status.HTTP_200_OK,
    response_model=TokenPairResponse,
    responses={
        401: {"model": AuthErrorResponse, "description": "Refresh token invalide."},
    },
)
def refresh(
    body: RefreshRequest,
    db: Session = Depends(get_db),
) -> TokenPairResponse:
    """Rotate the refresh token and return a new pair.

    The old refresh's ``jti`` is added to the in-process blacklist
    **before** the new pair is returned. A subsequent call to
    ``/refresh`` with the old token is rejected with 401
    ``invalid_token`` (AC5). The role is re-read from the database
    so a role change between two refreshes is honoured.
    """
    # Step 1 — decode the refresh token. ``decode_token`` enforces
    # the algorithm whitelist, the required claims, the ``type``
    # claim (= "refresh"), and the blacklist. Any failure is a 401.
    try:
        claims = decode_token(body.refresh_token, "refresh")
    except Exception:  # noqa: BLE001 - intentional: convert to 401
        logger.info("refresh.decode_failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_auth_error_payload(
                message="Refresh token invalide.",
                code="invalid_token",
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = claims.get("sub")
    jti = claims.get("jti")

    # Step 2 — fetch the user. If the user has been deleted between
    # login and refresh, the refresh is rejected.
    user = (
        db.query(User).filter(User.pseudo == sub).one_or_none()
        if isinstance(sub, str) and sub
        else None
    )
    if user is None:
        logger.info("refresh.user_missing pseudo={}", sub)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_auth_error_payload(
                message="Refresh token invalide.",
                code="invalid_token",
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 3 — rotate. The old ``jti`` is blacklisted BEFORE the new
    # pair is returned, so a stolen refresh that is replayed after
    # the legitimate refresh will fail.
    if isinstance(jti, str) and jti:
        token_blacklist.add(jti)

    settings = get_settings()
    new_access = create_access_token(user.pseudo, user.role)
    new_refresh = create_refresh_token(user.pseudo, user.role)
    logger.info("refresh.success pseudo={}", user.pseudo)
    return TokenPairResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ---------------------------------------------------------------------------
# POST /api/auth/logout (s13)
# ---------------------------------------------------------------------------


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": AuthErrorResponse, "description": "Token manquant ou invalide."},
    },
)
def logout(
    user: User = Depends(get_current_user),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    """Revoke the current access token (returns 204 No Content).

    The dependency ``get_current_user`` decodes the token and
    raises 401 on any failure; the handler is only reached with a
    valid access token. The token's ``jti`` is added to the
    blacklist; subsequent calls to any protected endpoint with
    the same access token are rejected with 401 ``invalid_token``.
    """
    # We need the ``jti`` to blacklist. ``get_current_user``
    # validated the token via the same header, so we re-decode it
    # here using the public key. The decode is fast and the
    # dependency has already filtered out the bad cases.
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                claims = decode_token(token, "access")
            except Exception:  # noqa: BLE001
                # The dependency already 401'd; this branch is
                # defensive and should be unreachable in practice.
                claims = None
            if claims is not None:
                jti = claims.get("jti")
                if isinstance(jti, str) and jti:
                    token_blacklist.add(jti)

    logger.info("logout.success pseudo={}", user.pseudo)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
