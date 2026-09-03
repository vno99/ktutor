"""Admin user management endpoints (s13b).

The router exposes two admin-only (JWT) endpoints:

* ``POST /api/users`` — create a new ``parent`` or ``admin`` account.
  ``eleve`` is **not** creatable here on purpose: pupils self-register
  via :func:`app.api.auth.router.register` (s12, ADR 005).
* ``PUT /api/users/{pseudo}/role`` — change a user's role to one of
  ``eleve`` / ``parent`` / ``admin``. Includes a "last admin" guard:
  the only admin in the system cannot self-demote.

s14 adds the parent-child link endpoints:

* ``POST /api/users/{parent_pseudo}/children`` — link a child to a
  parent (owner-or-admin, idempotent 200/201).
* ``GET  /api/users/{parent_pseudo}/children`` — list the children
  of a parent (owner-or-admin).

The two new endpoints share a different authorisation model than
the s13b ones: a parent can manage their own links, an admin can
manage anyone's. They therefore depend on
:func:`get_current_user` (not :func:`require_role` — using the
latter would reject every parent, including the legitimate owner,
research fact 1).

Logging never includes the password, the hash, the JWT, or the
``jti`` (cf. AGENTS.md § Backend logging).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from loguru import logger
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.users.schemas import (
    AddChildRequest,
    ChildLinkResponse,
    ChildrenListResponse,
    ChildResponse,
    CreateUserRequest,
    CreateUserResponse,
    UpdateRoleRequest,
    UpdateUserRole,
    UserErrorCode,
    UserErrorResponse,
    UserResponse,
)
from app.core.auth.middleware import get_current_user, require_role
from app.core.auth.passwords import hash_password
from app.core.database.models import ParentChildLink, User, UserRole
from app.core.database.session import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_userrole(value: UpdateUserRole) -> UserRole:
    """Convert a role ``Literal`` to the :class:`UserRole` enum.

    The mapping is strict: any value outside the three allowed ones
    raises :class:`ValueError`. Pydantic already rejects the bad
    values at the boundary (422), so this defensive check is a
    belt-and-braces guarantee against any future refactor that
    bypasses the schema validation.
    """
    if value == "eleve":
        return UserRole.ELEVE
    if value == "parent":
        return UserRole.PARENT
    if value == "admin":
        return UserRole.ADMIN
    raise ValueError(f"unknown role: {value!r}")


def _error_payload(*, message: str, code: UserErrorCode) -> dict:
    """Canonical error body for the users router."""
    return UserErrorResponse(error=message, code=code).model_dump()  # type: ignore[arg-type]


def _pseudo_already_exists(db: Session, pseudo: str) -> bool:
    """Case-insensitive pre-check for a duplicate pseudo.

    The DB-level functional unique index
    ``uq_users_pseudo_lower`` (see ``models.py``) is the ultimate
    source of truth — the router pre-check is UX, not security. The
    pattern is intentionally identical to
    :func:`app.api.auth.router.register`'s pre-check; a shared
    helper is a s15+ refactor.
    """
    return (
        db.query(User).filter(func.lower(User.pseudo) == pseudo.lower()).first()
        is not None
    )


def _fetch_user_or_404(db: Session, pseudo: str) -> User:
    """Fetch a user by pseudo (case-insensitive) or raise 404.

    The lookup is aligned with the case-insensitive uniqueness
    convention (``func.lower``) used everywhere in the users
    router — see :func:`update_role` for the canonical pattern.
    The 404 body is the standard ``user_not_found`` shape so
    clients do not need a special case to distinguish "missing
    parent" from "missing child" or "missing user" on the role
    update endpoint.
    """
    user = (
        db.query(User).filter(func.lower(User.pseudo) == pseudo.lower()).one_or_none()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_payload(
                message="Utilisateur introuvable.",
                code="user_not_found",
            ),
        )
    return user


def _assert_owner_or_admin(
    *, current_user: User, parent: User, action: str
) -> None:
    """Reject the request if the caller is neither the parent nor an admin.

    404 is **before** this check (in the handler): the 404 is what
    hides the existence of the parent from a non-authorised caller.
    Once we have a real parent row, this function only knows about
    a 403 — there is no further "not found" path here.
    """
    if current_user.pseudo == parent.pseudo or current_user.role is UserRole.ADMIN:
        return
    logger.info(
        "users.children.forbidden caller={} parent={} action={}",
        current_user.pseudo,
        parent.pseudo,
        action,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=_error_payload(
            message="Accès refusé.",
            code="forbidden",
        ),
    )


# ---------------------------------------------------------------------------
# POST /api/users
# ---------------------------------------------------------------------------


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateUserResponse,
    responses={
        403: {"model": UserErrorResponse, "description": "Appelant non-admin."},
        409: {"model": UserErrorResponse, "description": "Pseudo déjà pris."},
        422: {"model": UserErrorResponse, "description": "Validation Pydantic."},
        500: {"model": UserErrorResponse, "description": "Erreur interne."},
    },
)
def create_user(
    body: CreateUserRequest,
    admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> CreateUserResponse:
    """Create a new ``parent`` or ``admin`` account.

    The body is validated by Pydantic **before** this handler runs
    (422 on invalid pseudo, weak password, password whose UTF-8
    encoding exceeds the 72-byte bcrypt limit, or ``role: "eleve"``).
    The handler then performs a fast-fail pre-check, hashes the
    password, and inserts a new ``User`` row. The DB-level
    functional unique index is the ultimate source of truth for
    case-insensitive uniqueness; the ``catch IntegrityError`` covers
    the race where two concurrent requests pass the pre-check at
    the same time.

    No JWT is issued — the new user must log in via
    ``POST /api/auth/login`` (s13).
    """
    # Step 1 — pre-check (UX, not security; the DB constraint is the
    # last line of defence, see ``models.py``).
    if _pseudo_already_exists(db, body.pseudo):
        logger.info("users.create.conflict admin={} pseudo={}", admin.pseudo, body.pseudo)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_error_payload(
                message="Ce pseudo est déjà pris.",
                code="pseudo_taken",
            ),
        )

    # Step 2 — hash. Pydantic already guards the 72-byte limit, so
    # the ValueError here is a defensive double-check (matches the
    # pattern in ``auth/router.py::register``).
    password_hash = hash_password(body.password)

    # Step 3 — insert. ``_to_userrole`` is the strict literal-to-enum
    # conversion; Pydantic already filtered the values, but we
    # re-validate here as defence in depth.
    try:
        new_role = _to_userrole(body.role)
    except ValueError as exc:
        logger.error(
            "users.create.unexpected_role admin={} pseudo={} err={}",
            admin.pseudo,
            body.pseudo,
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                message="Rôle invalide.",
                code="internal",
            ),
        )

    user = User(
        pseudo=body.pseudo,
        password_hash=password_hash,
        role=new_role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Race condition: a concurrent request created the same
        # pseudo between our pre-check and our commit. The DB
        # constraint rejects our row; roll back and return the
        # same 409 the pre-check would have.
        db.rollback()
        logger.info(
            "users.create.race_conflict admin={} pseudo={}",
            admin.pseudo,
            body.pseudo,
        )
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
            "users.create.unexpected admin={} pseudo={} err={}",
            admin.pseudo,
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

    logger.info(
        "users.create.created admin={} target={} role={}",
        admin.pseudo,
        user.pseudo,
        user.role.value,
    )
    return CreateUserResponse(pseudo=user.pseudo, role=body.role)


# ---------------------------------------------------------------------------
# PUT /api/users/{pseudo}/role
# ---------------------------------------------------------------------------


@router.put(
    "/{pseudo}/role",
    status_code=status.HTTP_200_OK,
    response_model=UserResponse,
    responses={
        403: {"model": UserErrorResponse, "description": "Appelant non-admin."},
        404: {"model": UserErrorResponse, "description": "Utilisateur introuvable."},
        409: {
            "model": UserErrorResponse,
            "description": "Auto-rétrogradation du dernier admin.",
        },
        422: {"model": UserErrorResponse, "description": "Validation Pydantic."},
        500: {"model": UserErrorResponse, "description": "Erreur interne."},
    },
)
def update_role(
    pseudo: str,
    body: UpdateRoleRequest,
    admin: User = Depends(require_role(UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Change a user's role.

    * 404 if the target ``pseudo`` does not exist.
    * 409 if the admin is the only admin in the system **and** tries
      to demote themselves (would lock the system out). With a
      second admin present, the self-demote is allowed.
    * 200 otherwise. The audit log line ``security.role_change``
      records the admin, the target, the old role, and the new role.
    """
    # Step 1 — fetch the target user. Case-insensitive match to stay
    # aligned with the unique index (so an admin who types ``Ali``
    # to refer to ``ali`` is consistent with the rest of the API).
    user = (
        db.query(User).filter(func.lower(User.pseudo) == pseudo.lower()).one_or_none()
    )
    if user is None:
        logger.info(
            "users.role_update.not_found admin={} target={}",
            admin.pseudo,
            pseudo,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_error_payload(
                message="Utilisateur introuvable.",
                code="user_not_found",
            ),
        )

    # Step 2 — convert the role literal. Pydantic already filtered
    # the values, but we re-validate as defence in depth.
    try:
        new_role = _to_userrole(body.role)
    except ValueError as exc:
        logger.error(
            "users.role_update.unexpected_role admin={} target={} err={}",
            admin.pseudo,
            user.pseudo,
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_payload(
                message="Rôle invalide.",
                code="internal",
            ),
        )

    old_role = user.role

    # Step 3 — "last admin" self-demote guard. The check is **after**
    # the mutation so the count is taken in the same transaction —
    # if the count falls below 1 we roll back and return 409. This
    # is the pragmatic SQLite-compatible approach documented in the
    # research (Trap 3, option (c)). A lock-based alternative is
    # left for s15+ if PostgreSQL production needs the guarantee.
    if new_role != UserRole.ADMIN and user.pseudo == admin.pseudo:
        user.role = new_role
        db.flush()
        remaining_admins = (
            db.query(User).filter(User.role == UserRole.ADMIN).count()
        )
        if remaining_admins < 1:
            db.rollback()
            logger.info(
                "users.role_update.self_demote_blocked admin={}",
                admin.pseudo,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_error_payload(
                    message=(
                        "Impossible de retirer le dernier administrateur "
                        "du système."
                    ),
                    code="self_demote_blocked",
                ),
            )

    # Step 4 — commit. If anything below this line raises, the
    # session is in an error state and the caller's fixture will
    # roll it back on close.
    user.role = new_role
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001 - intentional: convert to 500
        db.rollback()
        logger.error(
            "users.role_update.unexpected admin={} target={} err={}",
            admin.pseudo,
            user.pseudo,
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

    logger.info(
        "security.role_change admin={} target={} old={} new={}",
        admin.pseudo,
        user.pseudo,
        old_role.value,
        user.role.value,
    )
    return UserResponse(pseudo=user.pseudo, role=body.role)


# ---------------------------------------------------------------------------
# POST /api/users/{parent_pseudo}/children  (s14)
# ---------------------------------------------------------------------------


@router.post(
    "/{parent_pseudo}/children",
    status_code=status.HTTP_201_CREATED,
    response_model=ChildLinkResponse,
    responses={
        200: {"model": ChildLinkResponse, "description": "Lien déjà existant (idempotence)."},
        201: {"model": ChildLinkResponse, "description": "Lien créé."},
        401: {"model": UserErrorResponse, "description": "Token invalide ou expiré."},
        403: {"model": UserErrorResponse, "description": "Caller ≠ parent et ≠ admin."},
        404: {"model": UserErrorResponse, "description": "Parent ou enfant introuvable."},
        422: {"model": UserErrorResponse, "description": "Validation Pydantic."},
        500: {"model": UserErrorResponse, "description": "Erreur interne."},
    },
)
def add_child(
    parent_pseudo: str,
    body: AddChildRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChildLinkResponse:
    """Link a child to a parent (idempotent 200/201).

    The authorisation is **owner-or-admin**: a parent can manage
    their own links, an admin can manage anyone's. The check
    happens **after** the parent fetch, so a non-existent parent
    URL returns 404 (not 403) — research trap 5 / anti-leak.

    Idempotence: re-POSTing the same ``(parent, child)`` pair
    returns 200 with the same body and creates no extra row. The
    pre-check is read-only; the ``catch IntegrityError`` on the
    INSERT handles the rare race where two concurrent requests
    pass the pre-check at the same time (the DB composite PK
    would otherwise raise 409).
    """
    # Step 1 — fetch the parent. 404 before 403 (anti-leak).
    parent = _fetch_user_or_404(db, parent_pseudo)

    # Step 2 — owner-or-admin.
    _assert_owner_or_admin(
        current_user=current_user, parent=parent, action="add"
    )

    # Step 3 — fetch the child. Same anti-leak discipline.
    child = _fetch_user_or_404(db, body.child_pseudo)

    # Step 4 — pre-check (UX, not security; the DB composite PK is
    # the source of truth for the uniqueness rule).
    existing = (
        db.query(ParentChildLink)
        .filter(
            func.lower(ParentChildLink.parent_pseudo) == parent.pseudo.lower(),
            func.lower(ParentChildLink.child_pseudo) == child.pseudo.lower(),
        )
        .one_or_none()
    )
    if existing is not None:
        logger.info(
            "users.children.duplicate parent={} child={} actor={}",
            parent.pseudo,
            child.pseudo,
            current_user.pseudo,
        )
        response.status_code = status.HTTP_200_OK
        return ChildLinkResponse(
            parent_pseudo=parent.pseudo,
            child_pseudo=child.pseudo,
        )

    # Step 5 — insert. The pre-check + ``catch IntegrityError``
    # together guarantee we never return 409 on the duplicate case:
    # the pre-check catches the common path, the catch handles the
    # race.
    db.add(
        ParentChildLink(parent_pseudo=parent.pseudo, child_pseudo=child.pseudo)
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info(
            "users.children.race_duplicate parent={} child={} actor={}",
            parent.pseudo,
            child.pseudo,
            current_user.pseudo,
        )
        response.status_code = status.HTTP_200_OK
        return ChildLinkResponse(
            parent_pseudo=parent.pseudo,
            child_pseudo=child.pseudo,
        )
    except Exception as exc:  # noqa: BLE001 - intentional: convert to 500
        db.rollback()
        logger.error(
            "users.children.unexpected parent={} child={} actor={} err={}",
            parent.pseudo,
            child.pseudo,
            current_user.pseudo,
            exc.__class__.__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_error_payload(
                message="Erreur interne.",
                code="internal",
            ),
        )

    logger.info(
        "users.children.created parent={} child={} actor={}",
        parent.pseudo,
        child.pseudo,
        current_user.pseudo,
    )
    return ChildLinkResponse(
        parent_pseudo=parent.pseudo,
        child_pseudo=child.pseudo,
    )


# ---------------------------------------------------------------------------
# GET /api/users/{parent_pseudo}/children  (s14)
# ---------------------------------------------------------------------------


@router.get(
    "/{parent_pseudo}/children",
    response_model=ChildrenListResponse,
    responses={
        200: {"model": ChildrenListResponse, "description": "Liste (peut être vide)."},
        401: {"model": UserErrorResponse, "description": "Token invalide ou expiré."},
        403: {"model": UserErrorResponse, "description": "Caller ≠ parent et ≠ admin."},
        404: {"model": UserErrorResponse, "description": "Parent introuvable."},
        500: {"model": UserErrorResponse, "description": "Erreur interne."},
    },
)
def list_children(
    parent_pseudo: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChildrenListResponse:
    """List the children of a parent (owner-or-admin).

    Returns ``[]`` (NOT 404) when the parent has no linked children
    — absence of children is a valid state, not an error. The 404
    only fires when the parent itself does not exist (anti-leak,
    same as :func:`add_child`).
    """
    # Step 1 — fetch the parent. 404 before 403.
    parent = _fetch_user_or_404(db, parent_pseudo)

    # Step 2 — owner-or-admin.
    _assert_owner_or_admin(
        current_user=current_user, parent=parent, action="list"
    )

    # Step 3 — JOIN. The canonical pseudo (case-preserved) is the
    # one stored on the User row, so we filter on
    # ``ParentChildLink.parent_pseudo == parent.pseudo`` (no
    # ``func.lower`` — we already have the canonical form).
    children = (
        db.query(User)
        .join(ParentChildLink, ParentChildLink.child_pseudo == User.pseudo)
        .filter(ParentChildLink.parent_pseudo == parent.pseudo)
        .all()
    )

    response_list = [ChildResponse(child_pseudo=u.pseudo, role=u.role.value) for u in children]
    logger.info(
        "users.children.listed parent={} count={} actor={}",
        parent.pseudo,
        len(response_list),
        current_user.pseudo,
    )
    return response_list


__all__ = ["router"]
