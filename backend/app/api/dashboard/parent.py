"""``GET /api/dashboard/parent`` — the parent dashboard endpoint (s17).

The endpoint returns a JSON :class:`ParentDashboardResponse` —
the list of children linked to the authenticated parent, each
wrapped in its own :class:`EleveDashboardResponse`. The list may
be empty (200, not 404) when the parent has no link at all.

The endpoint is **RBAC-strict** via
:func:`app.core.auth.middleware.require_role(["parent", "admin"])`:
an ``eleve`` who hits the URL gets a 403 ``forbidden`` (s15
contract), not an empty list.

Multi-tenancy: the list of children is **derived from the JWT**,
never from a body or URL field. ``user.pseudo`` is the
authoritative filter on :class:`ParentChildLink`. The single
admin bypass allows admins to see every link in the system
(debug workflow, ADR 005).

Cache reuse: each child's dashboard is fetched through
:func:`app.services.dashboard.cache.get_dashboard` first; on
miss, :func:`aggregate_eleve_dashboard` is called and the
result is stored under the same per-pseudo key as the
eleve-facing endpoint (``dashboard:eleve:{child_pseudo}``).
A new dashboard cache key is **not** introduced — the parent
benefits from the cache the eleve populates, and the
invalidation on a new ``Attempt`` clears it for both audiences
(s16 cache, reused here). Cf. research Piège 3.

Errors:

* **401 ``invalid_token``** — JWT missing, malformed, or
  expired (s13 contract).
* **403 ``forbidden``** — the caller's role is not
  ``parent`` or ``admin``.
* **500** — unhandled ``SQLAlchemyError`` etc. The router does
  NOT catch them (AGENTS.md § Erreurs).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dashboard.schemas import (
    ChildDashboardEntry,
    EleveDashboardResponse,
    ParentDashboardResponse,
)
from app.core.auth.middleware import require_role
from app.core.database.models import ParentChildLink, User, UserRole
from app.core.database.session import get_db
from app.services.dashboard.aggregator import aggregate_eleve_dashboard
from app.services.dashboard.cache import get_dashboard, set_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _aggregate_with_cache(db: Session, child_pseudo: str) -> EleveDashboardResponse:
    """Reuse the eleve cache: hit → return; miss → aggregate + store.

    The cache key is ``dashboard:eleve:{child_pseudo}`` (s16);
    the parent endpoint deliberately does not introduce a new
    key. See module docstring.
    """
    cached = get_dashboard(child_pseudo)
    if cached is not None:
        return cached
    data = aggregate_eleve_dashboard(db, child_pseudo)
    set_dashboard(child_pseudo, data)
    return data


@router.get("/parent", response_model=ParentDashboardResponse)
def get_parent_dashboard(
    user: User = Depends(require_role(UserRole.PARENT, UserRole.ADMIN)),
    db: Session = Depends(get_db),
) -> ParentDashboardResponse:
    """Aggregate the dashboards of all children linked to ``user``.

    For a parent: ``SELECT * FROM parent_child_links WHERE
    parent_pseudo = :user.pseudo ORDER BY created_at DESC``. For
    an admin: every row in the table (debug workflow, ADR 005).
    """
    if user.role is UserRole.ADMIN:
        links = db.query(ParentChildLink).order_by(ParentChildLink.created_at.desc()).all()
    else:
        links = (
            db.query(ParentChildLink)
            .filter(ParentChildLink.parent_pseudo == user.pseudo)
            .order_by(ParentChildLink.created_at.desc())
            .all()
        )

    children: list[ChildDashboardEntry] = []
    for link in links:
        dashboard = _aggregate_with_cache(db, link.child_pseudo)
        children.append(
            ChildDashboardEntry(
                pseudo=link.child_pseudo,
                linked_at=link.created_at,
                dashboard=dashboard,
            )
        )

    return ParentDashboardResponse(children=children)


__all__ = ["router"]
