"""Tests for the dashboard API schemas (s16).

The schema constraints are the contract that the aggregator and the
router inherit: ``score_avg`` must be in [0, 1], ``exercises_count``
must be >= 0, and the ``name`` field is a closed Literal so the
frontend can build a switch on it. These tests pin those invariants
at the schema layer; a violation caught here is much cheaper to fix
than a 422 surfacing deep in a router handler.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.dashboard.schemas import (
    EleveDashboardResponse,
    GlobalSummary,
    SubjectName,
    SubjectSummary,
)


def _subject(name: SubjectName = "maths", score: float = 0.5, count: int = 1) -> SubjectSummary:
    return SubjectSummary(name=name, score_avg=score, exercises_count=count, last_activity_at=None)


def _global(score: float = 0.5, count: int = 1) -> GlobalSummary:
    return GlobalSummary(score_avg=score, exercises_count=count, last_activity_at=None)


def test_subject_summary_rejects_score_avg_above_one() -> None:
    with pytest.raises(ValidationError):
        SubjectSummary(name="maths", score_avg=1.5, exercises_count=1, last_activity_at=None)


def test_subject_summary_rejects_negative_score_avg() -> None:
    with pytest.raises(ValidationError):
        SubjectSummary(name="maths", score_avg=-0.1, exercises_count=1, last_activity_at=None)


def test_subject_summary_rejects_negative_exercises_count() -> None:
    with pytest.raises(ValidationError):
        SubjectSummary(name="maths", score_avg=0.5, exercises_count=-1, last_activity_at=None)


def test_global_summary_rejects_score_avg_above_one() -> None:
    with pytest.raises(ValidationError):
        GlobalSummary(score_avg=1.1, exercises_count=0, last_activity_at=None)


def test_global_summary_rejects_negative_exercises_count() -> None:
    with pytest.raises(ValidationError):
        GlobalSummary(score_avg=0.0, exercises_count=-3, last_activity_at=None)


def test_response_accepts_empty_subjects_list() -> None:
    # The empty case is a valid dashboard for an eleve with zero attempts.
    resp = EleveDashboardResponse(subjects=[], **{"global": _global(score=0.0, count=0)})
    assert resp.subjects == []
    assert getattr(resp, "global_").exercises_count == 0


def test_subject_name_rejects_unknown_value() -> None:
    # Literal["maths", "francais"] must reject anything else.
    with pytest.raises(ValidationError):
        SubjectSummary(name="histoire", score_avg=0.5, exercises_count=1, last_activity_at=None)  # type: ignore[arg-type]


def test_response_serializes_with_global_alias_in_json() -> None:
    # The wire format MUST use ``global`` (the design's contract),
    # even though the Python attribute is ``global_`` (soft-keyword
    # workaround). A regression that drops the alias breaks the
    # frontend's `data.global` access.
    resp = EleveDashboardResponse(
        subjects=[_subject(name="maths", score=0.75, count=3)],
        **{"global": _global(score=0.75, count=3)},
    )
    payload = resp.model_dump(by_alias=True)
    assert "global" in payload
    assert "global_" not in payload
    assert payload["global"] == {"score_avg": 0.75, "exercises_count": 3, "last_activity_at": None}


def test_score_avg_boundary_values_accepted() -> None:
    # 0.0 and 1.0 are valid edges (no attempts → 0.0, all attempts
    # successful → 1.0). The aggregator never emits exactly 1.0 in
    # practice but the schema must allow it for forward-compat.
    SubjectSummary(name="maths", score_avg=0.0, exercises_count=0, last_activity_at=None)
    SubjectSummary(name="maths", score_avg=1.0, exercises_count=2, last_activity_at=None)
    GlobalSummary(score_avg=0.0, exercises_count=0, last_activity_at=None)
    GlobalSummary(score_avg=1.0, exercises_count=2, last_activity_at=None)
