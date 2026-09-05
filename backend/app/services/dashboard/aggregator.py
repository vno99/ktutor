"""Aggregation service for the eleve dashboard (s16).

The aggregator turns a (session, pseudo) pair into a fully-populated
:class:`EleveDashboardResponse`. It runs two SQL queries:

* **Per subject**: ``AVG(CAST(is_success AS FLOAT))``, ``COUNT(attempts)``,
  ``MAX(submitted_at)`` grouped by ``exercises.subject``, filtered by
  ``attempts.student_pseudo``. The result feeds the ``subjects`` list.
* **Global**: the same three aggregates, un-grouped, for the
  ``global`` block.

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
from app.core.database.models import Attempt, Exercise, RewardLedger
from app.services.rewards.levels import get_level


def aggregate_eleve_dashboard(db: Session, pseudo: str) -> EleveDashboardResponse:
    """Aggregate an eleve's attempts into the dashboard response.

    The function is a synchronous SQL pass; it does NOT open a
    transaction, mutate state, or call out to LLM / ChromaDB / S3.
    Caching is the caller's responsibility (the router layer).
    """
    # CRITICAL: CAST(is_success AS FLOAT) is required for PostgreSQL.
    # SQLite 3.x returns float for AVG(bool) even without CAST, so the
    # test backend (in-memory SQLite) silently masks a missing CAST.
    # PostgreSQL, on the other hand, returns numeric with integer
    # division semantics: AVG of (0, 0, 1) = 0 instead of 0.333. The
    # test ``test_aggregator_compiles_cast_is_success_as_float`` in
    # ``tests/services/dashboard/test_aggregator.py`` pins this
    # invariant by capturing the rendered SQL and asserting the CAST
    # is present in BOTH queries below. Removing the CAST from either
    # expression turns that test red regardless of the database
    # backend. See ``docs/reviews/s16-dashboard-eleve.md`` Major #2
    # for the original finding and the trap.

    # ---- Points & level (global) ------------------------------------------
    points_result = (
        db.query(func.sum(RewardLedger.points_awarded))
        .filter(RewardLedger.student_pseudo == pseudo)
        .scalar()
    )
    total_points: int = int(points_result or 0)
    level_label: str = get_level(total_points)

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
                total_points=total_points,
                level=level_label,
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
        total_points=total_points,
        level=level_label,
    )

    return EleveDashboardResponse.model_validate(
        {"subjects": subjects, "global": global_summary}
    )


__all__ = ["aggregate_eleve_dashboard"]
