"""``GET /api/dashboard/eleve`` — the student dashboard endpoint (s16).

The endpoint returns a JSON :class:`EleveDashboardResponse` with the
per-subject and global progress of the authenticated eleve. Two
flavours:

* ``GET /api/dashboard/eleve`` — the JWT's own ``pseudo`` is used
  (the common case; an eleve looking at their own dashboard).
* ``GET /api/dashboard/eleve?pseudo=alice`` — admin only. The
  s15 helper :func:`assert_jwt_pseudo_matches_or_403` raises 403
  ``forbidden`` if a non-admin caller names a different pseudo. No
  body echo of the rejected pseudo (AGENTS.md § Backend logging).

The response is served from a per-pseudo in-process cache
(``app.services.dashboard.cache``). The cache is bypassed implicitly
on TTL expiry (5 min) and explicitly on a new ``Attempt`` (the
caller in ``app.api.exercises.router`` calls
``invalidate_dashboard`` — task 8 of the plan, conditional on the
exercises router existing at the time of merge).

Errors:

* **401 ``invalid_token``** — the JWT is missing, malformed, or
  expired. Same body for every failure path (s13 contract).
* **403 ``forbidden``** — the caller named a ``pseudo`` that does
  not match the JWT's ``sub``, and is not an admin.
* **500** — unhandled ``SQLAlchemyError`` etc. The router does
  NOT catch them; FastAPI's default handler converts to a 500.
  ``AGENTS.md § Erreurs`` forbids silent ``try/except``.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth.schemas import MAX_PSEUDO_CHARS, PSEUDO_PATTERN
from app.api.dashboard.schemas import EleveDashboardResponse
from app.core.auth.middleware import (
    assert_jwt_pseudo_matches_or_403,
    get_current_user,
)
from app.core.database.models import User
from app.core.database.session import get_db
from app.services.dashboard.aggregator import aggregate_eleve_dashboard
from app.services.dashboard.cache import (
    get_dashboard,
    set_dashboard,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Constants duplicated from auth.schemas rather than imported as a
# module-level ``from app.api.auth.schemas import ...`` to keep the
# query-param schema self-contained. The values are stable and
# aligned with the auth registration contract (ADR 011).
_PSEUDO_QUERY_PATTERN = PSEUDO_PATTERN
_PSEUDO_QUERY_MAX = MAX_PSEUDO_CHARS


@router.get("/eleve", response_model=EleveDashboardResponse)
def get_eleve_dashboard(
    pseudo: str | None = Query(
        default=None,
        max_length=_PSEUDO_QUERY_MAX,
        pattern=_PSEUDO_QUERY_PATTERN,
        description=(
            "Admin-only: query another eleve's dashboard. "
            "When omitted, the JWT's own pseudo is used."
        ),
    ),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EleveDashboardResponse:
    """Aggregate and return the dashboard for ``pseudo`` (or the caller)."""
    # Cross-tenant guard. The helper is a no-op when ``pseudo is None``
    # (the common path). For an admin, ``pseudo != user.pseudo`` is
    # also a no-op. For a non-admin trying to read another eleve's
    # dashboard, the helper raises 403 ``forbidden`` and logs the
    # ``security.cross_tenant_attempt`` event.
    assert_jwt_pseudo_matches_or_403(user, pseudo, route="/api/dashboard/eleve")

    target_pseudo = pseudo or user.pseudo

    cached = get_dashboard(target_pseudo)
    if cached is not None:
        return cached

    data = aggregate_eleve_dashboard(db, target_pseudo)
    set_dashboard(target_pseudo, data)
    return data


__all__ = ["router"]
