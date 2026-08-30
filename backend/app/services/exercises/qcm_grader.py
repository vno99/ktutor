"""QCM grader (s04).

Grades a QCM submission against a previously generated ``Exercise`` row.

The grading is 100% deterministic — no LLM call. The pipeline:

  1. validate ``exercise_id`` is a UUID
  2. fetch the ``Exercise`` (or raise ``exercise_not_found``)
  3. **multi-tenant invariant**: ``Exercise.student_pseudo == pseudo``,
     otherwise ``cross_tenant`` (no leak — same message as not found)
  4. **defense-in-depth**: re-validate every dict in ``Exercise.questions``
     through the existing ``QcmQuestion`` Pydantic model. A malformed row
     raises ``invalid_exercise`` instead of crashing.
  5. validate the submitted ``raw_answers`` length and value range through
     ``SubmittedAnswers``; bad input raises ``invalid_answers``
  6. compute ``correct_count`` and the binary ``is_success`` (all-or-nothing
     per AC2 — no partial credit)
  7. derive ``attempt_number`` per ``(pseudo, exercise_id)`` via a
     ``MAX(attempt_number)`` query — *not* a global counter
  8. persist the ``Attempt`` row (rollback on failure)
  9. return the structured :class:`GradingResult`

The class is intentionally narrow — like :class:`QcmGenerator`, it does
one thing and inherits the same dependency-injection convention (a
``session_factory`` passed at construction time, no LLM).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError, field_validator, model_validator

from app.core.database.models import Attempt, Exercise
from app.services.exercises.qcm_generator import QcmQuestion

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class QcmGradingError(Exception):
    """Controlled failure raised by :meth:`QcmGrader.grade`.

    ``kind`` is a stable string the CLI / API can map to an exit code or
    HTTP status without parsing the message.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class GradingResult(BaseModel):
    """The successful outcome of :meth:`QcmGrader.grade`."""

    is_success: bool
    correct_count: int
    total: int
    feedback: str
    attempt_id: uuid.UUID
    attempt_number: int


class SubmittedAnswers(BaseModel):
    """The student's answers, validated against the expected shape.

    Each element must be an integer in ``[0, 3]`` (a QCM has 4 options).
    The total length must equal ``expected_length`` (the QCM's question
    count). The model is constructed with ``expected_length`` as an
    additional keyword argument on top of the Pydantic root — this is
    why the validator also re-asserts the length.
    """

    model_config = {"arbitrary_types_allowed": True}

    root: list[int]
    expected_length: int

    @field_validator("root")
    @classmethod
    def _validate_values(cls, value: list[int]) -> list[int]:
        if len(value) < 1:
            raise ValueError("at least one answer is required")
        for i, v in enumerate(value):
            if not isinstance(v, int) or isinstance(v, bool):
                raise TypeError(f"answer[{i}]={v!r} is not an int")
            if v < 0 or v > 3:
                raise ValueError(f"answer[{i}]={v} is out of range [0, 3]")
        return value

    @model_validator(mode="after")
    def _validate_length(self) -> SubmittedAnswers:
        if len(self.root) != self.expected_length:
            raise ValueError(
                f"expected {self.expected_length} answers, got {len(self.root)}"
            )
        return self


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class _SessionLike(Protocol):
    """The slice of a SQLAlchemy session the grader uses."""

    def add(self, obj: Any) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def get(self, entity: Any, ident: Any) -> Any: ...
    def query(self, *entities: Any) -> Any: ...


class QcmGrader:
    """Grade a QCM submission deterministically (no LLM call).

    The grader enforces the multi-tenant invariant on the ``Exercise``
    before doing any grading work. ``attempt_number`` is per
    ``(pseudo, exercise_id)`` so concurrent attempts on different
    exercises do not interfere.
    """

    def __init__(self, *, session_factory: Callable[[], _SessionLike]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def grade(
        self,
        pseudo: str,
        exercise_id: str,
        raw_answers: list[int],
    ) -> GradingResult:
        """Grade ``raw_answers`` against the exercise ``exercise_id``.

        Raises :class:`QcmGradingError` on every controlled failure. On
        success, returns the structured result AND has persisted the
        matching ``Attempt`` row.
        """
        # 1. Validate the UUID format up front.
        try:
            exercise_uuid = uuid.UUID(exercise_id)
        except (ValueError, TypeError) as exc:
            raise QcmGradingError(
                "exercise_not_found", f"exercise_id invalide: {exercise_id}"
            ) from exc

        session = self._session_factory()

        # 2. Fetch the exercise.
        exercise = session.get(Exercise, exercise_uuid)
        if exercise is None:
            raise QcmGradingError(
                "exercise_not_found",
                f"Exercise {exercise_uuid} introuvable pour le pseudo {pseudo!r}.",
            )

        # 3. Multi-tenant invariant. Same message as not-found so we
        # never leak the existence of a foreign exercise.
        if exercise.student_pseudo != pseudo:
            raise QcmGradingError(
                "cross_tenant",
                f"Exercise {exercise_uuid} introuvable pour le pseudo {pseudo!r}.",
            )

        # 4. Defense-in-depth: re-validate every dict through the
        # Pydantic schema used by the generator. A malformed row (e.g.
        # ``correct_index`` 5) raises a clean error rather than crashing
        # deeper down.
        if exercise.questions is None:
            raise QcmGradingError(
                "invalid_exercise",
                f"Exercise {exercise_uuid} n'a pas de questions.",
            )
        try:
            questions = [QcmQuestion.model_validate(d) for d in exercise.questions]
        except ValidationError as exc:
            raise QcmGradingError(
                "invalid_exercise",
                f"Exercise {exercise_uuid} a des questions mal formees: {exc}",
            ) from exc

        # 5. Validate the submitted answers.
        try:
            answers = SubmittedAnswers(
                root=list(raw_answers), expected_length=len(questions)
            )
        except ValidationError as exc:
            raise QcmGradingError(
                "invalid_answers",
                f"Reponses invalides: {exc}",
            ) from exc

        # 6. Grading: every answer must match the corresponding
        # ``correct_index`` (AC2 — all-or-nothing).
        correct_count = sum(
            1 for a, q in zip(answers.root, questions) if a == q.correct_index
        )
        total = len(questions)
        is_success = correct_count == total

        # 7. Per-(pseudo, exercise_id) attempt counter. ``MAX(attempt_number)``
        # is the only reliable source of truth: an in-memory counter
        # would be wrong across grader instances / process restarts.
        attempt_number = self._next_attempt_number(session, exercise_uuid, pseudo)

        # 8. Persist the attempt.
        attempt_id = uuid.uuid4()
        try:
            session.add(
                Attempt(
                    id=attempt_id,
                    exercise_id=exercise_uuid,
                    student_pseudo=pseudo,
                    attempt_number=attempt_number,
                    is_success=is_success,
                    raw_answers=list(answers.root),
                )
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            raise QcmGradingError(
                "storage_failure",
                f"Impossible de persister l'attempt: {exc}",
            ) from exc

        # 9. Build the feedback.
        feedback = (
            "Toutes les réponses sont correctes."
            if is_success
            else f"{correct_count}/{total} réponses correctes."
        )

        return GradingResult(
            is_success=is_success,
            correct_count=correct_count,
            total=total,
            feedback=feedback,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _next_attempt_number(
        session: _SessionLike, exercise_uuid: uuid.UUID, pseudo: str
    ) -> int:
        """Return the next ``attempt_number`` for ``(pseudo, exercise_id)``.

        Uses ``MAX(attempt_number)`` so concurrent grader instances see
        a consistent view. On an empty table, ``MAX`` returns ``None``
        and we start at ``1``.
        """
        from sqlalchemy import func

        current_max = (
            session.query(Attempt)
            .filter(
                Attempt.exercise_id == exercise_uuid,
                Attempt.student_pseudo == pseudo,
            )
            .with_entities(func.max(Attempt.attempt_number))
            .scalar()
        )
        # ``func.max`` returns ``None`` on an empty table.
        return (current_max or 0) + 1
