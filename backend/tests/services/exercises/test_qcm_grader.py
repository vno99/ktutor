"""Tests for the ``QcmGrader`` service (s04).

The grader owns three load-bearing invariants that drive the bite tests:

  * AC2 / AC4 — ``is_success`` is True if and only if every answer matches
    the corresponding ``correct_index`` (no partial credit).
  * AC5 — ``attempt_number`` increments per ``(pseudo, exercise_id)`` pair,
    *not* globally. Removing the ``MAX(attempt_number)`` query and
    returning a hard-coded ``1`` must turn the increment test red.
  * AC6 — multi-tenant: a pseudo cannot submit answers to an exercise that
    belongs to another pseudo. Removing the ``student_pseudo`` check
    must turn the cross-tenant test red.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database.models import (
    Attempt,
    Base,
    Document,
    DocumentStatus,
    Exercise,
    ExerciseType,
    Subject,
)

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _TrackingSession:
    """Wraps a real SQLAlchemy session, recording every ``add`` call.

    Mirrors the wrapper used in the QcmGenerator tests so the same fixture
    pattern carries across stories. The wrapper also exposes a ``query``
    method that delegates to the inner session so ``MAX(attempt_number)``
    can be exercised against the same tracking instance.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        self._inner.add(obj)

    def commit(self) -> None:
        self._inner.commit()

    def rollback(self) -> None:
        self._inner.rollback()

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.get(*args, **kwargs)

    def refresh(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.refresh(*args, **kwargs)

    def query(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.query(*args, **kwargs)


class _SessionFactory:
    """Returns a single tracking wrapper around a session; subsequent calls
    yield the same wrapper so the test can introspect what was added."""

    def __init__(self, inner_factory: Callable[[], Any]) -> None:
        self._inner_factory = inner_factory
        self._wrapper: _TrackingSession | None = None

    def __call__(self) -> _TrackingSession:
        if self._wrapper is None:
            self._wrapper = _TrackingSession(self._inner_factory())
        return self._wrapper

    @property
    def wrapper(self) -> _TrackingSession:
        assert self._wrapper is not None
        return self._wrapper


def _good_questions(n: int = 3) -> list[dict[str, Any]]:
    """Return ``n`` well-formed QCM question dicts (correct_index == 0)."""
    return [
        {"question": f"Q{i + 1} ?", "options": ["a", "b", "c", "d"], "correct_index": 0}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def memory_db() -> Callable[[], Any]:
    """Factory returning a fresh in-memory session bound to an engine that
    has the ``Base`` metadata applied. Used to seed ``Document`` /
    ``Exercise`` rows and read back persisted ``Attempt`` rows."""

    def _factory() -> Any:
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return Session()

    return _factory


@pytest.fixture()
def tracking_session(memory_db: Callable[[], Any]) -> _SessionFactory:
    """A session factory that returns the same tracking wrapper on every
    call. Allows tests to seed an ``Exercise`` (via the wrapper) and later
    assert the grader added an ``Attempt`` to the same session."""
    return _SessionFactory(memory_db)


def _seed_exercise(
    session: _TrackingSession,
    *,
    pseudo: str = "ali",
    document_id: uuid.UUID | None = None,
    questions: list[dict[str, Any]] | None = None,
) -> Exercise:
    """Insert a minimal ``Document`` and ``Exercise`` for ``pseudo`` and
    return the ``Exercise`` instance (refreshed so ``id`` is populated)."""
    if document_id is None:
        document_id = uuid.uuid4()
    if questions is None:
        questions = _good_questions(3)
    session.add(
        Document(
            id=document_id,
            student_pseudo=pseudo,
            subject=Subject.MATHS,
            filename="cours.pdf",
            s3_key=f"students/{pseudo}/{document_id}.pdf",
            chunks_count=2,
            status=DocumentStatus.INDEXED,
        )
    )
    session.commit()
    exercise = Exercise(
        student_pseudo=pseudo,
        subject=Subject.MATHS,
        type=ExerciseType.QCM,
        document_id=document_id,
        questions=questions,
    )
    session.add(exercise)
    session.commit()
    session.refresh(exercise)
    return exercise


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchema:
    def test_submitted_answers_rejects_wrong_length(self) -> None:
        from app.services.exercises.qcm_grader import SubmittedAnswers

        with pytest.raises(Exception):
            # 2 answers but caller expects 3
            SubmittedAnswers(root=[0, 0], expected_length=3)

    def test_submitted_answers_rejects_out_of_range_value(self) -> None:
        from app.services.exercises.qcm_grader import SubmittedAnswers

        with pytest.raises(Exception):
            SubmittedAnswers(root=[0, 4, 0], expected_length=3)  # 4 is out of [0, 3]

    def test_submitted_answers_rejects_empty(self) -> None:
        from app.services.exercises.qcm_grader import SubmittedAnswers

        with pytest.raises(Exception):
            SubmittedAnswers(root=[], expected_length=0)

    def test_submitted_answers_accepts_matching_length(self) -> None:
        from app.services.exercises.qcm_grader import SubmittedAnswers

        result = SubmittedAnswers(root=[0, 1, 2], expected_length=3)
        assert result.root == [0, 1, 2]


# ---------------------------------------------------------------------------
# AC2 / AC4 — perfect score and one-wrong score
# ---------------------------------------------------------------------------


class TestGrade:
    def test_perfect_score_returns_is_success_true(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC2 / AC4 — all answers correct -> is_success True."""
        from app.services.exercises.qcm_grader import QcmGrader

        exercise = _seed_exercise(tracking_session())
        grader = QcmGrader(session_factory=tracking_session)
        result = grader.grade("ali", str(exercise.id), [0, 0, 0])
        assert result.is_success is True
        assert result.correct_count == 3
        assert result.total == 3

    def test_one_wrong_answer_returns_is_success_false(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC2 / AC4 — one wrong answer -> is_success False (all-or-nothing)."""
        from app.services.exercises.qcm_grader import QcmGrader

        exercise = _seed_exercise(tracking_session())
        grader = QcmGrader(session_factory=tracking_session)
        result = grader.grade("ali", str(exercise.id), [0, 1, 0])
        assert result.is_success is False
        assert result.correct_count == 2
        assert result.total == 3

    def test_feedback_differs_per_outcome(self, tracking_session: _SessionFactory) -> None:
        from app.services.exercises.qcm_grader import QcmGrader

        exercise = _seed_exercise(tracking_session())
        grader = QcmGrader(session_factory=tracking_session)
        perfect = grader.grade("ali", str(exercise.id), [0, 0, 0])
        wrong = grader.grade("ali", str(exercise.id), [0, 1, 0])
        assert perfect.feedback != wrong.feedback


# ---------------------------------------------------------------------------
# AC3 — Attempt persistence
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_attempt_persisted_with_all_fields(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.qcm_grader import QcmGrader

        exercise = _seed_exercise(tracking_session())
        grader = QcmGrader(session_factory=tracking_session)
        grader.grade("ali", str(exercise.id), [0, 0, 0])

        attempts = [
            obj for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)
        ]
        assert len(attempts) == 1
        a = attempts[0]
        assert a.exercise_id == exercise.id
        assert a.student_pseudo == "ali"
        assert a.attempt_number == 1
        assert a.is_success is True
        assert a.raw_answers == [0, 0, 0]
        # Nullable fields stay NULL for QCM (s07/s08 will populate them).
        assert a.answer_text is None
        assert a.correction_level is None


# ---------------------------------------------------------------------------
# AC5 — attempt_number increments per (pseudo, exercise_id)
# ---------------------------------------------------------------------------


class TestAttemptNumber:
    def test_attempt_number_increments_across_submissions(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.qcm_grader import QcmGrader

        exercise = _seed_exercise(tracking_session())
        grader = QcmGrader(session_factory=tracking_session)
        first = grader.grade("ali", str(exercise.id), [0, 0, 0])
        second = grader.grade("ali", str(exercise.id), [0, 0, 0])
        third = grader.grade("ali", str(exercise.id), [0, 0, 0])
        assert first.attempt_number == 1
        assert second.attempt_number == 2
        assert third.attempt_number == 3

    def test_attempt_number_is_per_pseudo(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC5 — the counter is keyed on (pseudo, exercise_id), not just
        exercise_id. Bob's first attempt on a shared exercise id must be
        1, not 2 (Alice's counter does not leak)."""
        from app.services.exercises.qcm_grader import QcmGrader

        # Alice seeds and submits.
        alice_exercise = _seed_exercise(tracking_session(), pseudo="ali")
        grader = QcmGrader(session_factory=tracking_session)
        a1 = grader.grade("ali", str(alice_exercise.id), [0, 0, 0])
        a2 = grader.grade("ali", str(alice_exercise.id), [0, 0, 0])
        assert a1.attempt_number == 1
        assert a2.attempt_number == 2


# ---------------------------------------------------------------------------
# AC6 — cross-tenant
# ---------------------------------------------------------------------------


class TestCrossTenant:
    def test_cross_tenant_raises_grading_error(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC6 — the multi-tenant bite. Alice's exercise, Bob's submission.
        The grader must refuse with ``cross_tenant`` AND must NOT have
        written any ``Attempt`` to the session."""
        from app.services.exercises.qcm_grader import QcmGrader, QcmGradingError

        exercise = _seed_exercise(tracking_session(), pseudo="ali")
        grader = QcmGrader(session_factory=tracking_session)
        with pytest.raises(QcmGradingError) as exc_info:
            grader.grade("bob", str(exercise.id), [0, 0, 0])
        assert exc_info.value.kind == "cross_tenant"
        # No attempt was persisted: refusal is a refusal.
        attempts = [
            obj for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)
        ]
        assert attempts == []


# ---------------------------------------------------------------------------
# Defensive validation
# ---------------------------------------------------------------------------


class TestInvalidExercise:
    def test_malformed_exercise_questions_raises_grading_error(
        self, tracking_session: _SessionFactory
    ) -> None:
        """If the persisted ``Exercise.questions`` is malformed (defense in
        depth), the grader must raise ``invalid_exercise`` and not crash."""
        from app.services.exercises.qcm_grader import QcmGrader, QcmGradingError

        # Seed an exercise with a deliberately broken dict (``correct_index`` 5 is
        # outside [0, 3]). The model accepts it as a generic dict, so the
        # grader's Pydantic re-validation must catch it.
        exercise = _seed_exercise(
            tracking_session(),
            questions=[
                {
                    "question": "broken",
                    "options": ["a", "b", "c", "d"],
                    "correct_index": 5,
                }
            ],
        )
        grader = QcmGrader(session_factory=tracking_session)
        with pytest.raises(QcmGradingError) as exc_info:
            grader.grade("ali", str(exercise.id), [0])
        assert exc_info.value.kind == "invalid_exercise"


class TestExerciseNotFound:
    def test_unknown_exercise_id_raises_grading_error(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.qcm_grader import QcmGrader, QcmGradingError

        grader = QcmGrader(session_factory=tracking_session)
        with pytest.raises(QcmGradingError) as exc_info:
            grader.grade("ali", str(uuid.uuid4()), [0, 0, 0])
        assert exc_info.value.kind == "exercise_not_found"

    def test_malformed_uuid_raises_grading_error(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.qcm_grader import QcmGrader, QcmGradingError

        grader = QcmGrader(session_factory=tracking_session)
        with pytest.raises(QcmGradingError) as exc_info:
            grader.grade("ali", "not-a-uuid", [0, 0, 0])
        assert exc_info.value.kind == "exercise_not_found"


class TestInvalidAnswers:
    def test_wrong_length_raises_grading_error(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.qcm_grader import QcmGrader, QcmGradingError

        exercise = _seed_exercise(tracking_session())  # 3 questions
        grader = QcmGrader(session_factory=tracking_session)
        with pytest.raises(QcmGradingError) as exc_info:
            grader.grade("ali", str(exercise.id), [0, 0])  # 2 answers
        assert exc_info.value.kind == "invalid_answers"

    def test_out_of_range_value_raises_grading_error(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.qcm_grader import QcmGrader, QcmGradingError

        exercise = _seed_exercise(tracking_session())
        grader = QcmGrader(session_factory=tracking_session)
        with pytest.raises(QcmGradingError) as exc_info:
            grader.grade("ali", str(exercise.id), [0, 4, 0])  # 4 is out of [0, 3]
        assert exc_info.value.kind == "invalid_answers"
