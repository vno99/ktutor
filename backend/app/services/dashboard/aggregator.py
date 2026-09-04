"""Aggregation service for the eleve dashboard (s16).

The aggregator turns a (session, pseudo) pair into a fully-populated
:class:`EleveDashboardResponse`. It runs two SQL queries:

* **Per subject**: ``AVG(CAST(is_success AS FLOAT))``, ``COUNT(attempts)``,
  ``MAX(submitted_at)`` grouped by ``exercises.subject``, filtered by
  ``attempts.student_pseudo``. The result feeds the ``subjects`` list.
* **Global**: the same three aggregates, un-grouped, for the
  ``global`` block.

Why the explicit ``CAST(is_success AS FLOAT)``?

* SQLite (test backend) computes ``AVG(0)`` and ``AVG(1)`` as
  integer division; ``AVG(CAST(0 AS FLOAT))`` is the only way to
  get a fractional result. Without the cast, ``2/3`` rounds to
  ``0.0`` and the dashboard's success rate is wrong on the test
  backend.
* PostgreSQL (prod) accepts the same syntax; the cast is a no-op
  on numeric operands.

The function is **pure**: it takes a session, runs queries, builds
Pydantic models, returns. No I/O, no caching (the cache lives in
``app.services.dashboard.cache``), no auth (the router does that).
"""
from __future__ import annotations

from sqlalchemy import Float, cast, func
from sqlalchemy.orm import Session

from app.api.dashboard.schemas import (
    EleveDashboardResponse,
    GlobalSummary,
    SubjectSummary,
)
from app.core.database.models import Attempt, Exercise


def aggregate_eleve_dashboard(db: Session, pseudo: str) -> EleveDashboardResponse:
    """Aggregate an eleve's attempts into the dashboard response.

    The function is a synchronous SQL pass; it does NOT open a
    transaction, mutate state, or call out to LLM / ChromaDB / S3.
    Caching is the caller's responsibility (the router layer).
    """
    # ---- Per-subject aggregation -------------------------------------------
    per_subject_rows = (
        db.query(
            Exercise.subject.label("subject"),
            func.avg(cast(Attempt.is_success, Float)).label("score_avg"),
            func.count(Attempt.id).label("exercises_count"),
            func.max(Attempt.submitted_at).label("last_activity_at"),
        )
        .join(Exercise, Attempt.exercise_id == Exercise.id)
        .filter(Attempt.student_pseudo == pseudo)
        .group_by(Exercise.subject)
        .all()
    )

    subjects: list[SubjectSummary] = []
    for row in per_subject_rows:
        # The Subject enum stores its string value; the schema's
        # ``SubjectName`` Literal is the same string. Pydantic validates
        # at construction time.
        subjects.append(
            SubjectSummary(
                name=row.subject.value,
                score_avg=float(row.score_avg) if row.score_avg is not None else 0.0,
                exercises_count=int(row.exercises_count),
                last_activity_at=row.last_activity_at,
            )
        )

    # ---- Global aggregation ------------------------------------------------
    global_row = (
        db.query(
            func.avg(cast(Attempt.is_success, Float)).label("score_avg"),
            func.count(Attempt.id).label("exercises_count"),
            func.max(Attempt.submitted_at).label("last_activity_at"),
        )
        .filter(Attempt.student_pseudo == pseudo)
        .one()
    )

    global_summary = GlobalSummary(
        score_avg=float(global_row.score_avg) if global_row.score_avg is not None else 0.0,
        exercises_count=int(global_row.exercises_count),
        last_activity_at=global_row.last_activity_at,
    )

    return EleveDashboardResponse(subjects=subjects, global_=global_summary)


__all__ = ["aggregate_eleve_dashboard"]
