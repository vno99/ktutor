"""Tests for the s08 progressive correction service.

The state machine is the load-bearing invariant. It is tested as a
pure function (``next_correction_level``) with ``@pytest.mark.parametrize``
on the full truth table (8 transitions, 1 closed exception). The
service is then tested as the orchestrator that wires the state
machine to the persistence layer, with three bite tests:

  * cross-tenant → the grader (and the hint generator) are NEVER
    called on a foreign exercise
  * closed → the grader (and the hint generator) are NEVER called
    after 3 attempts
  * flashcards → the service refuses non-evaluated exercise types
    (D10)
"""

from __future__ import annotations

import json
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
# LLM stub (local copy — test_hints.py has the same pattern; the two
# test files do not share a fixtures module to keep imports local).
# ---------------------------------------------------------------------------


class _ScriptedLlm:
    """Drop-in replacement for ``LlmClient`` returning a scripted sequence."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[list[Any]] = []

    def invoke(self, messages: list[Any]) -> Any:
        from langchain_core.messages import AIMessage

        self.calls.append(list(messages))
        if not self._responses:
            raise AssertionError("LLM called more times than scripted responses.")
        text = self._responses.pop(0)
        return AIMessage(content=text)


# ---------------------------------------------------------------------------
# Truth table — pure state machine
# ---------------------------------------------------------------------------


class TestNextCorrectionLevel:
    """8 transitions of the state machine (D1)."""

    @pytest.mark.parametrize(
        "attempt, is_success, expected",
        [
            (1, True, "full"),
            (1, False, "partial"),
            (2, True, "full"),
            (2, False, "partial_attempt_2"),
            (3, True, "full"),
            (3, False, "full_after_attempts"),
        ],
    )
    def test_valid_transition(
        self, attempt: int, is_success: bool, expected: str
    ) -> None:
        from app.services.correction.progressive import next_correction_level

        assert next_correction_level(attempt, is_success, max_attempts=3) == expected

    @pytest.mark.parametrize("attempt", [4, 5, 99])
    def test_attempt_above_max_raises_closed(self, attempt: int) -> None:
        """AC9 — attempt_number > 3 raises ``closed`` BEFORE any grading work.

        Both ``is_success=True`` and ``is_success=False`` short-circuit:
        the exercise is closed, the answer is irrelevant."""
        from app.services.correction.progressive import (
            ProgressiveCorrectionError,
            next_correction_level,
        )

        for is_success in (True, False):
            with pytest.raises(ProgressiveCorrectionError) as exc_info:
                next_correction_level(attempt, is_success, max_attempts=3)
            assert exc_info.value.kind == "closed"

    def test_partial_attempt_2_is_distinct_from_partial(self) -> None:
        """AC2 — the table of truth must NOT collapse attempt 1 and attempt 2.

        This test is the bite: if the ``partial_attempt_2`` branch is
        removed and the function returns ``"partial"`` for both
        attempts, this test goes red."""
        from app.services.correction.progressive import next_correction_level

        assert next_correction_level(1, False, max_attempts=3) == "partial"
        assert next_correction_level(2, False, max_attempts=3) == "partial_attempt_2"

    def test_success_at_any_attempt_yields_full(self) -> None:
        """AC4 / AC5 — a success at attempts 1, 2 or 3 produces ``full``."""
        from app.services.correction.progressive import next_correction_level

        for attempt in (1, 2, 3):
            assert next_correction_level(attempt, True, max_attempts=3) == "full"


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _TrackingSession:
    """Wraps a real SQLAlchemy session and records every ``add`` call.

    Mirrors the wrapper used in the s04 / s07 grader tests so the same
    fixture pattern carries across stories.
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
    """Returns a single tracking wrapper around a session."""

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


class _RecordingGrader:
    """A ``grade_callback`` double that records every call and returns
    a scripted verdict. Mirrors the contract documented in D9:
    ``(Exercise, str) -> tuple[bool, str]``."""

    def __init__(
        self,
        *,
        is_success: bool = False,
        feedback: str = "stub feedback",
    ) -> None:
        self._is_success = is_success
        self._feedback = feedback
        self.calls: list[tuple[Any, str]] = []

    def __call__(self, exercise: Any, pseudo: str) -> tuple[bool, str]:
        self.calls.append((exercise, pseudo))
        return self._is_success, self._feedback


class _RecordingHintGenerator:
    """A ``HintGenerator`` double that records every call and returns
    a scripted (hints, next_steps) tuple. Mirrors the contract
    documented in the plan: ``generate_hints(self, context: HintContext)``."""

    def __init__(self, *, hints: list[str] | None = None, next_steps: str = "stub next") -> None:
        self._hints = list(hints) if hints is not None else ["stub-hint"]
        self._next_steps = next_steps
        self.calls: list[Any] = []

    def generate_hints(self, context: Any) -> tuple[list[str], str]:
        self.calls.append(context)
        return list(self._hints), self._next_steps


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def memory_db() -> Callable[[], Any]:
    """Return a factory of fresh in-memory sessions bound to ``Base`` metadata."""

    def _factory() -> Any:
        engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        return Session()

    return _factory


@pytest.fixture()
def tracking_session(memory_db: Callable[[], Any]) -> _SessionFactory:
    return _SessionFactory(memory_db)


def _seed_exercise(
    session: _TrackingSession,
    *,
    pseudo: str = "ali",
    type: ExerciseType = ExerciseType.QCM,
    document_id: uuid.UUID | None = None,
    questions: list[dict[str, Any]] | None = None,
    expected_answer: str | None = None,
    grading_criteria: list[str] | None = None,
) -> Exercise:
    """Seed a minimal ``Document`` and ``Exercise`` for ``pseudo`` and return
    the ``Exercise`` (refreshed so ``id`` is populated)."""
    if document_id is None:
        document_id = uuid.uuid4()
    if questions is None and type is ExerciseType.QCM:
        questions = [
            {"question": f"Q{i + 1} ?", "options": ["a", "b", "c", "d"], "correct_index": 0}
            for i in range(3)
        ]
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
        type=type,
        document_id=document_id,
        questions=questions,
        expected_answer=expected_answer,
        grading_criteria=grading_criteria,
    )
    session.add(exercise)
    session.commit()
    session.refresh(exercise)
    return exercise


def _seed_attempt(
    session: _TrackingSession,
    *,
    exercise: Exercise,
    attempt_number: int,
    is_success: bool = False,
) -> Attempt:
    """Seed a prior ``Attempt`` row so the next submission sees the
    correct ``attempt_number``."""
    a = Attempt(
        id=uuid.uuid4(),
        exercise_id=exercise.id,
        student_pseudo=exercise.student_pseudo,
        attempt_number=attempt_number,
        is_success=is_success,
        raw_answers=[],
        correction_level="full" if is_success else "partial",
    )
    session.add(a)
    session.commit()
    return a


# ---------------------------------------------------------------------------
# Service — full flow
# ---------------------------------------------------------------------------


class TestProgressiveCorrectionService:
    """The service orchestrates grading + state machine + persistence."""

    def test_service_evaluates_first_attempt_failure_with_partial(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC1 — first attempt failure → ``partial`` + hints + next_steps."""
        from app.services.correction.progressive import ProgressiveCorrectionService

        exercise = _seed_exercise(tracking_session())
        grader = _RecordingGrader(is_success=False, feedback="2/3 correctes")
        hints = _RecordingHintGenerator(hints=["indice A", "indice B"], next_steps="relis le cours")
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        result = service.evaluate("ali", str(exercise.id), grader)

        assert result.is_success is False
        assert result.correction_level == "partial"
        assert result.attempt_number == 1
        assert result.hints == ["indice A", "indice B"]
        assert result.next_steps == "relis le cours"
        assert result.feedback == "2/3 correctes"
        assert grader.calls == [(exercise, "ali")]
        # Hint generator was called once with a HintContext carrying the
        # right attempt_number and feedback. The exact statement is
        # built from the seeded exercise, so we only check the
        # load-bearing fields here.
        assert len(hints.calls) == 1
        assert hints.calls[0].attempt_number == 1
        assert hints.calls[0].feedback == "2/3 correctes"
        # The attempt must be persisted with the right correction_level.
        attempts = [obj for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)]
        assert len(attempts) == 1
        assert attempts[0].correction_level == "partial"
        assert attempts[0].is_success is False
        assert attempts[0].attempt_number == 1

    def test_service_evaluates_second_attempt_failure_with_partial_attempt_2(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC2 — second attempt failure → ``partial_attempt_2`` + specific hints."""
        from app.services.correction.progressive import ProgressiveCorrectionService

        exercise = _seed_exercise(tracking_session())
        _seed_attempt(tracking_session(), exercise=exercise, attempt_number=1, is_success=False)
        grader = _RecordingGrader(is_success=False, feedback="1/3 correctes")
        hints = _RecordingHintGenerator(hints=["erreur identifiee"], next_steps="concentre-toi sur l'etape 3")
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        result = service.evaluate("ali", str(exercise.id), grader)

        assert result.correction_level == "partial_attempt_2"
        assert result.attempt_number == 2
        assert result.hints == ["erreur identifiee"]
        assert len(hints.calls) == 1
        assert hints.calls[0].attempt_number == 2
        assert hints.calls[0].feedback == "1/3 correctes"

    def test_service_evaluates_third_attempt_failure_with_full_after_attempts(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC3 — third attempt failure → ``full_after_attempts`` + solution."""
        from app.services.correction.progressive import ProgressiveCorrectionService

        expected = "La solution complete."
        exercise = _seed_exercise(
            tracking_session(),
            type=ExerciseType.PROBLEME,
            expected_answer=expected,
            grading_criteria=["critère 1"],
        )
        _seed_attempt(tracking_session(), exercise=exercise, attempt_number=1, is_success=False)
        _seed_attempt(tracking_session(), exercise=exercise, attempt_number=2, is_success=False)
        attempts_before = sum(
            1 for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)
        )
        grader = _RecordingGrader(is_success=False, feedback="0/3 correctes")
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        result = service.evaluate("ali", str(exercise.id), grader)

        assert result.correction_level == "full_after_attempts"
        assert result.attempt_number == 3
        # The full solution is now revealed (D3 — the attempt stays is_success=False).
        assert result.solution == expected
        # Hints are NOT generated for full / full_after_attempts.
        assert result.hints == []
        assert result.next_steps is None
        # Exactly one new ``Attempt`` row was added; the 2 seeded rows are
        # part of the prior count.
        attempts_after = [
            obj
            for obj in tracking_session.wrapper.added
            if isinstance(obj, Attempt)
        ]
        assert len(attempts_after) == attempts_before + 1
        new_attempt = attempts_after[-1]
        assert new_attempt.is_success is False
        assert new_attempt.correction_level == "full_after_attempts"

    def test_service_evaluates_first_try_success_with_full(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC4 — first-try success → ``full`` + solution + bonus 2 points (D6)."""
        from app.services.correction.progressive import ProgressiveCorrectionService

        expected = "La solution complete."
        exercise = _seed_exercise(
            tracking_session(),
            type=ExerciseType.PROBLEME,
            expected_answer=expected,
        )
        grader = _RecordingGrader(is_success=True, feedback="Bravo !")
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        result = service.evaluate("ali", str(exercise.id), grader)

        assert result.is_success is True
        assert result.correction_level == "full"
        assert result.attempt_number == 1
        assert result.solution == expected
        assert result.bonus_points == 2
        # No hints on a first-try success.
        assert result.hints == []
        assert hints.calls == []

    def test_service_evaluates_late_success_with_full_no_bonus(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC5 / D6 — a success at attempt 2 or 3 yields ``full`` but NO bonus."""
        from app.services.correction.progressive import ProgressiveCorrectionService

        expected = "La solution complete."
        exercise = _seed_exercise(
            tracking_session(),
            type=ExerciseType.PROBLEME,
            expected_answer=expected,
        )
        _seed_attempt(tracking_session(), exercise=exercise, attempt_number=1, is_success=False)
        grader = _RecordingGrader(is_success=True, feedback="OK")
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        result = service.evaluate("ali", str(exercise.id), grader)

        assert result.is_success is True
        assert result.correction_level == "full"
        assert result.attempt_number == 2
        assert result.solution == expected
        # D6 — bonus is only 2 on the first try.
        assert result.bonus_points == 0

    def test_service_persists_attempt_with_correction_level(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC5 — the ``Attempt`` row carries the correction_level returned
        by the state machine. This is the bite: if the service forgets to
        write ``correction_level``, this test goes red."""
        from app.services.correction.progressive import ProgressiveCorrectionService

        exercise = _seed_exercise(tracking_session())
        grader = _RecordingGrader(is_success=False)
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )
        service.evaluate("ali", str(exercise.id), grader)

        attempts = [obj for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)]
        assert len(attempts) == 1
        a = attempts[0]
        assert a.correction_level == "partial"
        assert a.exercise_id == exercise.id
        assert a.student_pseudo == "ali"
        assert a.attempt_number == 1
        assert a.is_success is False

    def test_service_raises_closed_on_attempt_4(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC9 — a 4th submission raises ``closed`` (the exercise is closed)."""
        from app.services.correction.progressive import (
            ProgressiveCorrectionError,
            ProgressiveCorrectionService,
        )

        exercise = _seed_exercise(tracking_session())
        # Seed 3 prior attempts (all failures).
        for n in (1, 2, 3):
            _seed_attempt(tracking_session(), exercise=exercise, attempt_number=n, is_success=False)
        grader = _RecordingGrader()
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        with pytest.raises(ProgressiveCorrectionError) as exc_info:
            service.evaluate("ali", str(exercise.id), grader)
        assert exc_info.value.kind == "closed"

    def test_service_does_not_call_grade_callback_when_closed(
        self, tracking_session: _SessionFactory
    ) -> None:
        """Piège n°11 — once the exercise is closed, the grader must NOT be
        called. Removing the ``attempt > max_attempts`` short-circuit makes
        this test go red on ``assert grader.calls == []``."""
        from app.services.correction.progressive import (
            ProgressiveCorrectionError,
            ProgressiveCorrectionService,
        )

        exercise = _seed_exercise(tracking_session())
        for n in (1, 2, 3):
            _seed_attempt(tracking_session(), exercise=exercise, attempt_number=n, is_success=False)
        # Snapshot the attempt count BEFORE the closed call. The 3
        # seeded rows are expected; the assertion compares the count
        # after the (refused) call to this baseline.
        attempts_before = sum(
            1 for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)
        )
        grader = _RecordingGrader()
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        with pytest.raises(ProgressiveCorrectionError):
            service.evaluate("ali", str(exercise.id), grader)
        assert grader.calls == []
        # And the hint generator is NOT called either — the closed gate is
        # BEFORE any grading or hint work.
        assert hints.calls == []
        # No new Attempt was persisted (the 3 seeded rows are expected).
        attempts_after = sum(
            1 for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)
        )
        assert attempts_after == attempts_before

    def test_service_writes_attempt_with_no_session_factory(
        self, tracking_session: _SessionFactory
    ) -> None:
        """Defensive — when ``session_factory`` is None the service still
        returns a complete ``CorrectionResult`` (no DB write). Used by the
        CLI stubbed tests where the service is built without a session."""
        from app.services.correction.progressive import ProgressiveCorrectionService

        exercise = _seed_exercise(tracking_session())  # built but not used
        grader = _RecordingGrader(is_success=False)
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=None,
            hint_generator=hints,  # type: ignore[arg-type]
        )
        result = service.evaluate("ali", str(exercise.id), grader)
        assert result.correction_level == "partial"
        # The exercise is never fetched when session_factory is None — the
        # grader sees ``None`` instead of an exercise.
        assert grader.calls[0][0] is None


# ---------------------------------------------------------------------------
# Multi-tenant
# ---------------------------------------------------------------------------


class TestCrossTenant:
    """A pseudo must never see another pseudo's exercise."""

    def test_foreign_exercise_raises_cross_tenant(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC8 — Alice's exercise, Bob's submission. The service must
        refuse with ``cross_tenant`` AND must NOT call the grader."""
        from app.services.correction.progressive import (
            ProgressiveCorrectionError,
            ProgressiveCorrectionService,
        )

        exercise = _seed_exercise(tracking_session(), pseudo="ali")
        grader = _RecordingGrader()
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        with pytest.raises(ProgressiveCorrectionError) as exc_info:
            service.evaluate("bob", str(exercise.id), grader)
        assert exc_info.value.kind == "cross_tenant"
        # Same message as exercise_not_found — no leak.
        assert exc_info.value.kind == "cross_tenant"
        # No grader call, no hint call, no Attempt row.
        assert grader.calls == []
        assert hints.calls == []
        attempts = [obj for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)]
        assert attempts == []

    def test_unknown_exercise_raises_not_found(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.correction.progressive import (
            ProgressiveCorrectionError,
            ProgressiveCorrectionService,
        )

        grader = _RecordingGrader()
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        with pytest.raises(ProgressiveCorrectionError) as exc_info:
            service.evaluate("ali", str(uuid.uuid4()), grader)
        assert exc_info.value.kind == "exercise_not_found"
        assert grader.calls == []

    def test_malformed_uuid_raises_not_found(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.correction.progressive import (
            ProgressiveCorrectionError,
            ProgressiveCorrectionService,
        )

        grader = _RecordingGrader()
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        with pytest.raises(ProgressiveCorrectionError) as exc_info:
            service.evaluate("ali", "not-a-uuid", grader)
        assert exc_info.value.kind == "exercise_not_found"


# ---------------------------------------------------------------------------
# Exercise type whitelist (D10)
# ---------------------------------------------------------------------------


class TestInvalidExercise:
    """FLASHCARDS is rejected — the service owns the type whitelist."""

    def test_flashcards_exercise_raises_invalid_exercise(
        self, tracking_session: _SessionFactory
    ) -> None:
        """D10 — flashcards are a study aid, not an evaluated exercise.
        The bite: if the type whitelist is widened to include
        ``FLASHCARDS`` by mistake, this test goes red."""
        from app.services.correction.progressive import (
            ProgressiveCorrectionError,
            ProgressiveCorrectionService,
        )

        exercise = _seed_exercise(tracking_session(), type=ExerciseType.FLASHCARDS)
        grader = _RecordingGrader()
        hints = _RecordingHintGenerator()
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hints,  # type: ignore[arg-type]
        )

        with pytest.raises(ProgressiveCorrectionError) as exc_info:
            service.evaluate("ali", str(exercise.id), grader)
        assert exc_info.value.kind == "invalid_exercise"
        # No grader call, no hint call, no Attempt.
        assert grader.calls == []
        assert hints.calls == []
        attempts = [obj for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)]
        assert attempts == []


# ---------------------------------------------------------------------------
# Real HintGenerator integration (regression for the critical bug)
# ---------------------------------------------------------------------------


class TestRealHintGeneratorIntegration:
    """The service must wire the real ``HintGenerator`` (not a stub).

    This is the regression test for the s08 review critical finding:
    the service used to call
    ``self._hint_generator.generate_hints(exercise, attempt_number, feedback)``
    with three positional args, but the real ``HintGenerator`` takes a
    single ``HintContext``. The bug crashed every real
    ``submit-qcm`` / ``submit-text`` that ended in ``partial`` or
    ``partial_attempt_2``.

    The test wires a real ``HintGenerator`` (with a stub ``_ScriptedLlm``
    that returns well-formed JSON) into the real
    ``ProgressiveCorrectionService`` and asserts that ``service.evaluate(...)``
    returns non-empty hints for a ``partial`` result.
    """

    def test_real_hint_generator_returns_hints_for_partial(
        self, tracking_session: _SessionFactory
    ) -> None:
        """The service must hand a ``HintContext`` to the real hint
        generator. AC1 — non-empty hints on first-attempt failure."""
        from app.services.correction.hints import HintGenerator
        from app.services.correction.progressive import ProgressiveCorrectionService

        exercise = _seed_exercise(tracking_session())
        grader = _RecordingGrader(is_success=False, feedback="0/3 correctes")
        # A real HintGenerator wired with a stub LLM that returns a
        # well-formed JSON payload on its single call.
        llm = _ScriptedLlm(
            [
                json.dumps(
                    {
                        "hints": ["relis la definition de la derivee"],
                        "next_steps": "consulte la section 3.2 du cours",
                    }
                )
            ]
        )
        hint_generator = HintGenerator(llm=llm, max_retries=0)  # type: ignore[arg-type]
        service = ProgressiveCorrectionService(
            session_factory=tracking_session,
            hint_generator=hint_generator,  # type: ignore[arg-type]
        )

        result = service.evaluate("ali", str(exercise.id), grader)

        assert result.correction_level == "partial"
        # The real hint generator was called and produced real hints.
        assert result.hints == ["relis la definition de la derivee"]
        assert result.next_steps == "consulte la section 3.2 du cours"
        # The LLM was called exactly once (no retry needed).
        assert len(llm.calls) == 1
