"""Pydantic schemas for the dashboard endpoints (s16).

The schemas are the **only** contract the frontend (and any future
external client) depends on. Three rules:

* ``SubjectName`` is a closed :class:`typing.Literal` — the frontend
  builds a switch on it and ``i18n`` keys the subject label. Adding
  a new subject means adding a value here AND a new branch in the
  frontend, deliberately. Reusing the runtime :class:`Subject` enum
  (model enum) would create a drift surface (the enum can grow
  without the schema noticing), so we mirror only the two values
  s16 ships with.

* ``score_avg`` is a **proxy** for the dashboard metric, computed
  as ``mean(Attempt.is_success)`` by the aggregator. The range
  [0, 1] is enforced at the schema layer; a violation that reaches
  here means a regression in the aggregator's SQL (e.g. forgetting
  the ``CAST(... AS FLOAT)``).

* ``exercises_count`` is the count of attempts (not distinct
  exercises) per the story's wording. The schema does not enforce
  this; the aggregator's contract does. A negative count is
  rejected at the schema layer as a final safety net.

The top-level field ``global`` is a Python soft-keyword, so the
underlying attribute is ``global_`` with a Pydantic ``Field(alias="global")``.
``model_dump(by_alias=True)`` and ``model_validate`` accept both
the alias and the python name; the JSON wire format uses ``global``
everywhere, matching the API contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Closed subject set. Keep in lockstep with
# ``app.core.database.models.Subject`` for the two values s16 ships
# with (maths, francais). Drift is detected by the schema's
# ``Literal`` validation.
SubjectName = Literal["maths", "francais"]


class SubjectSummary(BaseModel):
    """Per-subject progress for one eleve."""

    name: SubjectName
    score_avg: float = Field(..., ge=0.0, le=1.0)
    exercises_count: int = Field(..., ge=0)
    last_activity_at: datetime | None = None


class GlobalSummary(BaseModel):
    """Overall progress across all subjects for one eleve."""

    score_avg: float = Field(..., ge=0.0, le=1.0)
    exercises_count: int = Field(..., ge=0)
    last_activity_at: datetime | None = None


class EleveDashboardResponse(BaseModel):
    """Top-level response of ``GET /api/dashboard/eleve``.

    ``subjects`` may be empty when the eleve has never attempted an
    exercise (the response is still 200; the frontend renders the
    empty state). The ``global`` block is always present and
    defaults to zeros when no attempts exist.
    """

    # ``global`` is a soft-keyword in Python class bodies. Pydantic
    # supports it through an alias; the wire format is ``global``
    # (matches the design's JSON shape exactly).
    model_config = ConfigDict(populate_by_name=True)

    subjects: list[SubjectSummary]
    global_: GlobalSummary = Field(..., alias="global")


class ChildDashboardEntry(BaseModel):
    """One child of the authenticated parent (s17).

    ``linked_at`` mirrors :attr:`ParentChildLink.created_at` — the
    timestamp at which the parent-child link was created (s14).
    The frontend sorts on this field (the router applies
    ``ORDER BY created_at DESC``) and renders a localised
    "Linked since …" label.

    ``dashboard`` is a full :class:`EleveDashboardResponse` — the
    parent's read-only view is a thin wrapper around the
    student-facing payload. Reusing the schema avoids drift
    between the two endpoints.
    """

    pseudo: str
    linked_at: datetime
    dashboard: EleveDashboardResponse


class ParentDashboardResponse(BaseModel):
    """Top-level response of ``GET /api/dashboard/parent`` (s17).

    ``children`` may be empty when the parent has no link row at
    all. The empty list is a 200, **not** a 404 — a parent with
    no children linked is a valid, expected state (the s14
    story's "ask the admin" workflow).
    """

    children: list[ChildDashboardEntry]


__all__ = [
    "ChildDashboardEntry",
    "EleveDashboardResponse",
    "GlobalSummary",
    "ParentDashboardResponse",
    "SubjectName",
    "SubjectSummary",
]
