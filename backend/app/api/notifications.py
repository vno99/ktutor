"""Notifications API endpoints (s25)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth.middleware import get_current_user
from app.core.database.models import Notification, User
from app.core.database.session import get_db

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get(
    "/",
    response_model=list[dict],
)
async def list_notifications(
    unread_only: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = db.query(Notification).filter(Notification.student_pseudo == user.pseudo)
    if unread_only:
        query = query.filter(Notification.is_read == False)
    notifications = query.order_by(Notification.created_at.desc()).all()
    return [
        {
            "id": str(n.id),
            "type": n.type.value,
            "message": n.message,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
            "related_id": str(n.related_id) if n.related_id else None,
        }
        for n in notifications
    ]


@router.post(
    "/{notification_id}/read",
    response_model=dict,
)
async def read_notification(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.student_pseudo == user.pseudo,
        )
        .first()
    )
    if row is None:
        # Defensive: do not reveal cross-tenant existence.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Notification non trouvée.", "code": "not_found"},
        )

    if not row.is_read:
        row.is_read = True
        db.commit()
    return {
        "id": str(row.id),
        "is_read": row.is_read,
    }
