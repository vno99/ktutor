"""``GET /api/chat/history`` and ``GET /api/chat/history/{id}`` (s19, ADR 015).

Two read-only endpoints under the same ``/api/chat`` prefix as
``POST /api/chat/stream`` (s09). The wire format mirrors the
``ChatStreamRequest`` contract from :mod:`app.api.chat.schemas`:

* ``GET /api/chat/history`` — paginated list of the caller's
  conversations, newest first. Query params: ``limit`` (default
  20, clamped to ``[1, 100]``), ``offset`` (default 0, clamped
  to ``[0, ∞)``), ``subject`` (``"maths"`` / ``"francais"`` /
  ``None`` for all). 401 without bearer, 422 on bad input.
* ``GET /api/chat/history/{conversation_id}`` — the conversation
  + its messages in one shot (AC3). 404 ``not_found`` for
  unknown or cross-tenant ids (the two share the same body so
  a cross-tenant attacker cannot distinguish "exists but not
  yours" from "doesn't exist" — ADR 015 § Decision 3).

Cross-tenant rules (T4, AGENTS.md DoD):

* ``ELEVE`` — only sees ``student_pseudo == user.pseudo``.
* ``PARENT`` — only sees a ``student_pseudo`` they are linked
  to via :class:`app.core.database.models.ParentChildLink`.
  The list endpoint does NOT surface a parent's linked
  children — that is a separate product surface (s17 dashboard
  per-child detail). Parents querying the list endpoint see
  their own (empty) history, the same way an eleve with no
  conversation sees an empty list. This is the AGENTS.md DoD
  "list endpoint" branch.
* ``ADMIN`` — bypass (ADR 005 § RBAC). Admin sees every
  conversation on the list endpoint; admin reads any
  conversation on the detail endpoint.

All DB filters on ``student_pseudo`` are applied INSIDE the
SQL query (via the service layer — T2). A "load then check"
pattern in the router would leak via a race when the
conversation is deleted between the load and the check. The
service's cross-tenant filter is the first wall; the router's
404 surface is the second wall; the DB-level
``UNIQUE(student_pseudo, subject)`` (T1) is the last.

s19 implementation note: the admin branch reads conversations
directly via SQLAlchemy (bypassing the service's
``student_pseudo`` filter). The alternative — adding a
``student_pseudo: str | None = None`` "admin mode" on the
service — would push RBAC into the data layer, which the
repo's separation-of-concerns convention forbids (the
service is closest-to-the-DB and stays role-blind). The
filter is therefore reapplied in the router using the same
SQL idiom the service uses (T2 has both clauses commented
in its docstring for parity).
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func as sql_func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.chat.history_schemas import (
    ConversationDetail,
    ConversationListItem,
    HistoryListResponse,
    MessageItem,
    NotFoundResponse,
)
from app.core.auth.middleware import (
    assert_jwt_pseudo_matches_or_403,
    assert_parent_linked_to_child_or_403,
    get_current_user,
)
from app.core.database.models import (
    Conversation,
    Message,
    Subject,
    User,
    UserRole,
)
from app.core.database.session import get_db
from app.services.chat_history.service import ChatHistoryService

router = APIRouter(prefix="/api/chat", tags=["chat-history"])


# Pagination bounds — duplicated from the service layer so the
# router Pydantic layer enforces them BEFORE the service is
# called. The service still clamps as a safety net (T2).
_MAX_LIMIT = 100
_MIN_LIMIT = 1
_DEFAULT_LIMIT = 20


def _not_found() -> None:
    """Raise the canonical 404 body for both unknown and
    cross-tenant ids (the two share the same body so a
    cross-tenant attacker cannot distinguish them — ADR
    015 § Decision 3).
    """
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": "Conversation introuvable.", "code": "not_found"},
    )


# ---------------------------------------------------------------------------
# GET /api/chat/history
# ---------------------------------------------------------------------------


@router.get(
    "/history",
    response_model=HistoryListResponse,
    status_code=status.HTTP_200_OK,
)
def list_history(
    limit: int = Query(
        _DEFAULT_LIMIT,
        ge=_MIN_LIMIT,
        le=_MAX_LIMIT,
        description="Nombre maximum de conversations à retourner.",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Décalage (0 = première page).",
    ),
    subject: Literal["maths", "francais"] | None = Query(
        None,
        description=(
            "Filtre par matière. Omis = toutes matières. "
            "Toute autre valeur est rejetée par Pydantic en 422."
        ),
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HistoryListResponse:
    """Return the caller's conversation history, newest first.

    The cross-tenant contract (T4):

    * ``ELEVE`` — only the caller's own rows.
    * ``PARENT`` — only the caller's own rows (a parent sees
      their own history, not their linked children's — that
      surface is the parent dashboard per-child detail, out
      of scope for s19; ADR 015 § Decision 3).
    * ``ADMIN`` — every row, no ``student_pseudo`` filter.

    The ``subject`` query param is optional. ``None`` (the
    absence of the param) means "all subjects"; the Pydantic
    literal rejects any other value with 422.
    """
    subj_enum = Subject(subject) if subject is not None else None

    if user.role is UserRole.ADMIN:
        # Admin bypass — no student filter. Same SQL idiom as
        # the service (T2) minus the ``student_pseudo`` clause.
        count_q = select(sql_func.count(Conversation.id))
        rows_q = (
            select(Conversation)
            .order_by(Conversation.last_activity_at.desc(), Conversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        if subj_enum is not None:
            count_q = count_q.where(Conversation.subject == subj_enum)
            rows_q = rows_q.where(Conversation.subject == subj_enum)
        total = int(db.execute(count_q).scalar_one())
        rows = list(db.execute(rows_q).scalars().all())
    else:
        # ELEVE and PARENT — the service applies the
        # ``student_pseudo`` filter INSIDE the SQL query. The
        # parent sees their own (typically empty) history;
        # linked children are surfaced through the parent
        # dashboard, not this endpoint (ADR 015 § Decision 3).
        service = ChatHistoryService(lambda: db)
        rows, total = service.list_conversations(
            student_pseudo=user.pseudo,
            subject=subj_enum,
            limit=limit,
            offset=offset,
        )

    items = [
        ConversationListItem(
            id=r.id,
            subject=r.subject,
            first_question=r.first_question,
            last_activity_at=r.last_activity_at,
            message_count=r.message_count,
        )
        for r in rows
    ]
    return HistoryListResponse(items=items, total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# GET /api/chat/history/{conversation_id}
# ---------------------------------------------------------------------------


@router.get(
    "/history/{conversation_id}",
    response_model=ConversationDetail,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": NotFoundResponse,
            "description": "Conversation introuvable (ou non autorisée).",
        }
    },
)
def get_history(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationDetail:
    """Return the conversation and its messages in chronological order.

    Cross-tenant rules (T4):

    * ``ELEVE`` — 404 unless ``conversation.student_pseudo ==
      user.pseudo``.
    * ``PARENT`` — 404 unless ``user`` is linked to
      ``conversation.student_pseudo`` via
      :class:`ParentChildLink`.
    * ``ADMIN`` — 200 (impersonation, ADR 005).

    The 404 response is the same body for "unknown id" and
    "cross-tenant" so an attacker cannot enumerate ids (ADR
    015 § Decision 3).
    """
    # Step 1 — load the conversation row (no student_pseudo
    # filter here, the RBAC layer applies the rule below).
    conv = db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    ).scalar_one_or_none()
    if conv is None:
        _not_found()

    # Step 2 — RBAC. The two helpers (parent-link and
    # pseudo-match) are the same ones the upload / evaluation
    # routers use; a regression that drops them is caught
    # by the cross-tenant bite tests in T4.
    _check_tenant_access(user, db, conv.student_pseudo)

    # Step 3 — load the messages in chronological order.
    messages = list(
        db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at.asc())
        ).scalars().all()
    )

    return ConversationDetail(
        id=conv.id,
        subject=conv.subject,
        first_question=conv.first_question,
        last_activity_at=conv.last_activity_at,
        message_count=conv.message_count,
        messages=[
            MessageItem(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=m.sources,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


def _check_tenant_access(
    user: User, db: Session, claimed: str
) -> None:
    """Apply the role-specific cross-tenant rule.

    * ``ELEVE`` — pseudo must match (via
      :func:`assert_jwt_pseudo_matches_or_403`).
    * ``PARENT`` — must be linked to ``claimed`` via
      :func:`assert_parent_linked_to_child_or_403`. A parent
      may always access their own data.
    * ``ADMIN`` — bypass (ADR 005).

    The parent-link helper raises 403 on a miss; the
    pseudo-match helper also raises 403. Both surface a
    ``forbidden`` body. The router catches the 403 and
    re-raises it as a 404 + ``not_found`` body so the
    cross-tenant attacker cannot enumerate ids. This is
    the "404 not 403" interdict from the plan (ADR 015
    § Decision 3) and matches s18b's score-manual endpoint.
    """
    try:
        if user.role is UserRole.PARENT:
            assert_parent_linked_to_child_or_403(
                user, claimed, route="/api/chat/history", db=db
            )
        else:
            # ``ELEVE`` and ``ADMIN`` both go through this
            # branch; ``ADMIN`` is allowed by the helper.
            assert_jwt_pseudo_matches_or_403(
                user, claimed, route="/api/chat/history"
            )
    except HTTPException as exc:
        # The helpers raise 403 ``forbidden``. The plan
        # forbids 403 on this endpoint (a cross-tenant
        # attacker must see the same body as "unknown id"),
        # so we re-raise as 404 ``not_found``.
        if exc.status_code == status.HTTP_403_FORBIDDEN:
            _not_found()
        raise


__all__ = ["router"]
