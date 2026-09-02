"""``POST /api/auth/register`` — public account creation (s12).

The endpoint is the only way a visitor becomes an ``eleve`` in the
system (cf. ADR 005). The flow:

1. Pydantic validates ``{pseudo, password}`` (422 on bad shape or
   oversize password). The router never sees an unvalidated body.
2. Pre-check :func:`User` uniqueness case-insensitively. If a row
   already exists → 409 ``pseudo_taken`` without touching the DB
   writer.
3. Hash the password with bcrypt and insert a new ``User`` row with
   ``role=UserRole.ELEVE`` (D8: the endpoint never creates ``parent``
   or ``admin``).
4. If the DB constraint catches a duplicate that the pre-check missed
   (race condition between two concurrent requests) → 409
   ``pseudo_taken``. ``db.rollback()`` is mandatory to avoid leaving
   the session in a broken state.
5. Any other failure → 500 ``internal`` with ``db.rollback()``.

Logging never includes the password or its hash (cf. AGENTS.md §
Backend logging and the research § Traps 4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth.schemas import (
    RegisterErrorCode,
    RegisterErrorResponse,
    RegisterRequest,
    RegisterResponse,
)
from app.core.auth.passwords import hash_password
from app.core.database.models import User, UserRole
from app.core.database.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _error_payload(*, message: str, code: RegisterErrorCode) -> dict:
    """Build the canonical error body for HTTPException details."""
    return RegisterErrorResponse(error=message, code=code).model_dump()


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
            detail=_error_payload(
                message="Ce pseudo est déjà pris.",
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
            detail=_error_payload(
                message="Ce pseudo est déjà pris.",
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
            detail=_error_payload(
                message="Erreur interne.",
                code="internal",
            ),
        )
    db.refresh(user)

    logger.info("register.created pseudo={}", body.pseudo)
    return RegisterResponse(pseudo=user.pseudo)


__all__ = ["router"]
