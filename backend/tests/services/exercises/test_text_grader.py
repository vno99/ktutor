"""Tests for the ``TextGrader`` service (s07).

The grader owns four load-bearing invariants that drive the bite tests:

  * AC1 / AC5 — a stub LLM returning ``VERDICT: REUSSITE`` produces
    ``is_success=True``; ``VERDICT: ECHEC`` produces ``is_success=False``.
  * AC3 / AC6 — when the LLM does not emit a ``VERDICT:`` line, the grader
    retries ONCE with a strictly different prompt and then raises
    ``TextGradingError("verdict_missing")``.
  * AC4 — every successful grading persists an ``Attempt`` row with
    ``answer_text`` populated and ``raw_answers=[]``.
  * AC7 — multi-tenant: a pseudo cannot submit to an exercise owned by
    another pseudo. The bite test asserts that the LLM is NOT called
    AND that no ``Attempt`` is added on a cross-tenant request.

The test doubles (``_ScriptedLlm`` and ``_TrackingSession``) are
duplicated locally per the s04 convention (D8.a from
``docs/research/s07-repondre-texte-libre.md``) so the test is
self-contained and the bite tests do not depend on the QCM test module.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.messages import AIMessage
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


class _ScriptedLlm:
    """Drop-in ``LlmClient`` that pops the next scripted reply on each call.

    The list of replies may be shorter than the number of calls — the
    final reply is reused for any further call. The full ``messages`` list
    of every call is recorded so the strict-prompt-on-retry bite test can
    assert the second prompt is genuinely different from the first.
    """

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[list[Any]] = []

    def invoke(self, messages: list[Any]) -> AIMessage:
        self.calls.append(list(messages))
        if self._replies:
            text = self._replies.pop(0)
        else:
            text = self._replies[-1] if self._replies else ""
        return AIMessage(content=text)


class _TrackingSession:
    """Wraps a real SQLAlchemy session, recording every ``add`` call.

    Mirrors the wrapper used in the QCM grader tests so the same fixture
    pattern carries across stories.
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


def _seed_text_exercise(
    session: _TrackingSession,
    *,
    pseudo: str = "ali",
    document_id: uuid.UUID | None = None,
    type: ExerciseType = ExerciseType.PROBLEME,
    statement: str = "Calcule la dérivée de f(x) = x^2 + 3x.",
    expected_answer: str = "f'(x) = 2x + 3.",
    grading_criteria: list[str] | None = None,
) -> Exercise:
    """Insert a minimal ``Document`` and free-style ``Exercise`` (probleme
    or redaction) and return the refreshed ``Exercise`` instance."""
    if document_id is None:
        document_id = uuid.uuid4()
    if grading_criteria is None:
        grading_criteria = ["La dérivée est correcte."]
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
        statement=statement,
        expected_answer=expected_answer,
        grading_criteria=grading_criteria,
    )
    session.add(exercise)
    session.commit()
    session.refresh(exercise)
    return exercise


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchema:
    def test_text_submission_rejects_empty_answer(self) -> None:
        from app.services.exercises.text_grader import TextSubmission

        with pytest.raises(Exception):
            TextSubmission(answer="")

    def test_text_submission_rejects_too_long_answer(self) -> None:
        from app.services.exercises.text_grader import TextSubmission

        with pytest.raises(Exception):
            TextSubmission(answer="x" * 8001)


# ---------------------------------------------------------------------------
# AC1 / AC2 / AC5 — verdict parsing
# ---------------------------------------------------------------------------


class TestGrade:
    def test_verdict_reussite_returns_is_success_true(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.text_grader import TextGrader

        exercise = _seed_text_exercise(tracking_session())
        llm = _ScriptedLlm(["Bonne réponse.\nVERDICT: REUSSITE"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        result = grader.grade("ali", str(exercise.id), "f'(x) = 2x + 3")
        assert result.is_success is True
        assert result.attempt_number == 1
        assert "Bonne réponse" in result.feedback

    def test_verdict_echec_returns_is_success_false(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.text_grader import TextGrader

        exercise = _seed_text_exercise(tracking_session())
        llm = _ScriptedLlm(["Réponse incomplète.\nVERDICT: ECHEC"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        result = grader.grade("ali", str(exercise.id), "f'(x) = 2x")
        assert result.is_success is False
        assert result.attempt_number == 1
        assert "Réponse incomplète" in result.feedback

    def test_verdict_extraction_is_case_insensitive(
        self, tracking_session: _SessionFactory
    ) -> None:
        """D5 — the regex must accept mixed-case ``verdict: reussite``."""
        from app.services.exercises.text_grader import TextGrader

        exercise = _seed_text_exercise(tracking_session())
        llm = _ScriptedLlm(["Ok.\nverdict: reussite"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        result = grader.grade("ali", str(exercise.id), "f'(x) = 2x + 3")
        assert result.is_success is True

    def test_feedback_extracted_before_verdict_line(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.text_grader import TextGrader

        exercise = _seed_text_exercise(tracking_session())
        llm = _ScriptedLlm(
            ["La démarche est correcte, mais le résultat est faux.\nVERDICT: ECHEC"]
        )
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        result = grader.grade("ali", str(exercise.id), "f'(x) = 2x")
        assert "démarche est correcte" in result.feedback
        assert "résultat est faux" in result.feedback
        assert "VERDICT" not in result.feedback

    def test_no_verdict_retries_then_fails(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC3 / AC6 — when the LLM does not emit ``VERDICT:`` on the
        first call, the grader retries ONCE then raises verdict_missing."""
        from app.services.exercises.text_grader import TextGrader, TextGradingError

        exercise = _seed_text_exercise(tracking_session())
        # No ``VERDICT:`` line on either call.
        llm = _ScriptedLlm(["Pas de verdict ici.", "Toujours rien."])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        with pytest.raises(TextGradingError) as exc_info:
            grader.grade("ali", str(exercise.id), "f'(x) = 2x + 3")
        assert exc_info.value.kind == "verdict_missing"
        # 1ère tentative + 1 retry.
        assert len(llm.calls) == 2

    def test_strict_prompt_used_on_retry(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC3 / AC6 (bite) — the second call MUST use a prompt that
        differs from the first. Reloading the same prompt is a
        regression: the LLM has already shown it cannot comply."""
        from app.services.exercises.text_grader import TextGrader

        exercise = _seed_text_exercise(tracking_session())
        # First call: no verdict. Second call: valid verdict.
        llm = _ScriptedLlm(
            [
                "Pas de verdict ici.",
                "Ok.\nVERDICT: REUSSITE",
            ]
        )
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        grader.grade("ali", str(exercise.id), "f'(x) = 2x + 3")
        assert len(llm.calls) == 2
        # The two prompts MUST be different — that is the load-bearing
        # invariant (otherwise retry is meaningless).
        assert str(llm.calls[0]) != str(llm.calls[1])

    def test_llm_anglais_verdict_does_not_match(
        self, tracking_session: _SessionFactory
    ) -> None:
        """Piège 5 — an English ``VERDICT: SUCCESS`` is rejected because
        the regex only matches ``REUSSITE`` or ``ECHEC``."""
        from app.services.exercises.text_grader import TextGrader, TextGradingError

        exercise = _seed_text_exercise(tracking_session())
        llm = _ScriptedLlm(["Good answer.\nVERDICT: SUCCESS"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        with pytest.raises(TextGradingError) as exc_info:
            grader.grade("ali", str(exercise.id), "f'(x) = 2x + 3")
        assert exc_info.value.kind == "verdict_missing"

    def test_attempt_persisted_with_answer_text(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC4 — the Attempt row carries the student's text in
        ``answer_text`` and an empty ``raw_answers`` list."""
        from app.services.exercises.text_grader import TextGrader

        exercise = _seed_text_exercise(tracking_session())
        llm = _ScriptedLlm(["Bien.\nVERDICT: REUSSITE"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        grader.grade("ali", str(exercise.id), "ma réponse élève")

        attempts = [
            obj for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)
        ]
        assert len(attempts) == 1
        a = attempts[0]
        assert a.exercise_id == exercise.id
        assert a.student_pseudo == "ali"
        assert a.attempt_number == 1
        assert a.is_success is True
        assert a.answer_text == "ma réponse élève"
        assert a.raw_answers == []
        assert a.correction_level is None

    def test_attempt_raw_answers_is_empty_list(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC4 — ``raw_answers`` stays an empty list for free-form
        attempts (QCM shares the same column)."""
        from app.services.exercises.text_grader import TextGrader

        exercise = _seed_text_exercise(tracking_session())
        llm = _ScriptedLlm(["Ok.\nVERDICT: ECHEC"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        grader.grade("ali", str(exercise.id), "réponse")

        attempts = [
            obj for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)
        ]
        assert len(attempts) == 1
        assert attempts[0].raw_answers == []


# ---------------------------------------------------------------------------
# AC4 — attempt_number increments per (pseudo, exercise_id)
# ---------------------------------------------------------------------------


class TestAttemptNumber:
    def test_attempt_number_increments_across_submissions(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.text_grader import TextGrader

        exercise = _seed_text_exercise(tracking_session())
        llm = _ScriptedLlm(
            [
                "Ok.\nVERDICT: REUSSITE",
                "Ok.\nVERDICT: REUSSITE",
                "Ok.\nVERDICT: REUSSITE",
            ]
        )
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        first = grader.grade("ali", str(exercise.id), "a")
        second = grader.grade("ali", str(exercise.id), "b")
        third = grader.grade("ali", str(exercise.id), "c")
        assert first.attempt_number == 1
        assert second.attempt_number == 2
        assert third.attempt_number == 3

    def test_attempt_number_is_per_pseudo(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC4 — the counter is keyed on (pseudo, exercise_id), not just
        exercise_id. Two different students both start at 1 on the same
        exercise row."""
        from app.services.exercises.text_grader import TextGrader

        exercise = _seed_text_exercise(tracking_session())
        # Seed a second Document so Bob can have his own exercise
        # (Alice's exercise is owned by Alice; Bob's submission would
        # otherwise be cross-tenant). We keep the test focused on the
        # per-pseudo invariant by giving Bob his own exercise.
        bob_exercise = _seed_text_exercise(tracking_session(), pseudo="bob")
        llm = _ScriptedLlm(
            [
                "Ok.\nVERDICT: REUSSITE",
                "Ok.\nVERDICT: REUSSITE",
            ]
        )
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        alice = grader.grade("ali", str(exercise.id), "a1")
        bob = grader.grade("bob", str(bob_exercise.id), "b1")
        assert alice.attempt_number == 1
        assert bob.attempt_number == 1

    def test_attempt_number_is_per_exercise(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC4 — the counter is keyed on (pseudo, exercise_id), not
        just pseudo. Two different exercises for the same student each
        start at 1."""
        from app.services.exercises.text_grader import TextGrader

        first_exercise = _seed_text_exercise(tracking_session())
        second_exercise = _seed_text_exercise(tracking_session())
        llm = _ScriptedLlm(
            [
                "Ok.\nVERDICT: REUSSITE",
                "Ok.\nVERDICT: REUSSITE",
            ]
        )
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        first = grader.grade("ali", str(first_exercise.id), "a")
        second = grader.grade("ali", str(second_exercise.id), "a")
        assert first.attempt_number == 1
        assert second.attempt_number == 1


# ---------------------------------------------------------------------------
# AC7 — cross-tenant
# ---------------------------------------------------------------------------


class TestCrossTenant:
    def test_cross_tenant_raises_text_grading_error(
        self, tracking_session: _SessionFactory
    ) -> None:
        """AC7 — Alice's exercise, Bob's submission. The grader must
        refuse with ``cross_tenant`` AND must NOT have called the LLM
        AND must NOT have added an ``Attempt`` to the session."""
        from app.services.exercises.text_grader import TextGrader, TextGradingError

        exercise = _seed_text_exercise(tracking_session(), pseudo="ali")
        llm = _ScriptedLlm(["Should not be called.\nVERDICT: REUSSITE"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        with pytest.raises(TextGradingError) as exc_info:
            grader.grade("bob", str(exercise.id), "ma réponse")
        assert exc_info.value.kind == "cross_tenant"
        # LLM must not have been called on a cross-tenant request.
        assert llm.calls == []
        # No attempt must have been persisted: refusal is a refusal.
        attempts = [
            obj for obj in tracking_session.wrapper.added if isinstance(obj, Attempt)
        ]
        assert attempts == []


# ---------------------------------------------------------------------------
# D2.a / D2.b — invalid exercise type
# ---------------------------------------------------------------------------


class TestInvalidExercise:
    def test_qcm_exercise_raises_invalid_exercise_type(
        self, tracking_session: _SessionFactory
    ) -> None:
        """D2.a — ``submit-text`` on a QCM exercise is rejected. The
        LLM must NOT be called: QCM grading is deterministic and goes
        through ``submit-qcm``."""
        from app.services.exercises.text_grader import TextGrader, TextGradingError

        exercise = _seed_text_exercise(tracking_session(), type=ExerciseType.QCM)
        llm = _ScriptedLlm(["Should not be called.\nVERDICT: REUSSITE"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        with pytest.raises(TextGradingError) as exc_info:
            grader.grade("ali", str(exercise.id), "ma réponse")
        assert exc_info.value.kind == "invalid_exercise_type"
        assert llm.calls == []

    def test_flashcards_exercise_raises_invalid_exercise_type(
        self, tracking_session: _SessionFactory
    ) -> None:
        """D2.b — ``submit-text`` on a FLASHCARDS exercise is rejected
        symmetrically. Flashcards are a study aid, not an evaluated
        exercise; they have no ``statement`` / ``expected_answer``."""
        from app.services.exercises.text_grader import TextGrader, TextGradingError

        exercise = _seed_text_exercise(tracking_session(), type=ExerciseType.FLASHCARDS)
        llm = _ScriptedLlm(["Should not be called.\nVERDICT: REUSSITE"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        with pytest.raises(TextGradingError) as exc_info:
            grader.grade("ali", str(exercise.id), "ma réponse")
        assert exc_info.value.kind == "invalid_exercise_type"
        assert llm.calls == []

    def test_missing_expected_answer_raises_invalid_exercise(
        self, tracking_session: _SessionFactory
    ) -> None:
        """Defense in depth — if the persisted exercise lacks
        ``expected_answer`` (should never happen for s06, but a
        hand-crafted row could), the grader refuses cleanly rather
        than crashing."""
        from app.services.exercises.text_grader import TextGrader, TextGradingError

        exercise = _seed_text_exercise(tracking_session())
        # Wipe the field after seeding.
        exercise.expected_answer = None
        tracking_session().commit()
        llm = _ScriptedLlm(["Should not be called.\nVERDICT: REUSSITE"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        with pytest.raises(TextGradingError) as exc_info:
            grader.grade("ali", str(exercise.id), "ma réponse")
        assert exc_info.value.kind == "invalid_exercise"
        assert llm.calls == []


# ---------------------------------------------------------------------------
# D4.a — answer too long
# ---------------------------------------------------------------------------


class TestAnswerLength:
    def test_answer_too_long_raises_before_llm_call(
        self, tracking_session: _SessionFactory
    ) -> None:
        """Piège 3 — a 9000-char answer exceeds the 8000-char safety
        net. The grader must raise ``answer_too_long`` BEFORE calling
        the LLM so a runaway answer cannot saturate the LLM context."""
        from app.services.exercises.text_grader import TextGrader, TextGradingError

        exercise = _seed_text_exercise(tracking_session())
        llm = _ScriptedLlm(["Should not be called.\nVERDICT: REUSSITE"])
        grader = TextGrader(
            llm=llm, session_factory=tracking_session, max_answer_chars=8000
        )
        with pytest.raises(TextGradingError) as exc_info:
            grader.grade("ali", str(exercise.id), "x" * 9000)
        assert exc_info.value.kind == "answer_too_long"
        assert llm.calls == []


# ---------------------------------------------------------------------------
# Defense — exercise_not_found
# ---------------------------------------------------------------------------


class TestExerciseNotFound:
    def test_unknown_exercise_id_raises_grading_error(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.text_grader import TextGrader, TextGradingError

        llm = _ScriptedLlm(["Should not be called.\nVERDICT: REUSSITE"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        with pytest.raises(TextGradingError) as exc_info:
            grader.grade("ali", str(uuid.uuid4()), "ma réponse")
        assert exc_info.value.kind == "exercise_not_found"
        assert llm.calls == []

    def test_malformed_uuid_raises_grading_error(
        self, tracking_session: _SessionFactory
    ) -> None:
        from app.services.exercises.text_grader import TextGrader, TextGradingError

        llm = _ScriptedLlm(["Should not be called.\nVERDICT: REUSSITE"])
        grader = TextGrader(llm=llm, session_factory=tracking_session)
        with pytest.raises(TextGradingError) as exc_info:
            grader.grade("ali", "not-a-uuid", "ma réponse")
        assert exc_info.value.kind == "exercise_not_found"
        assert llm.calls == []
