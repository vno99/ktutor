"""Progressive correction service (s08).

The 4-state correction flow for QCM (s04) and free-form text (s07)
exercises. The service wraps the existing graders via a
``grade_callback`` callable — it does NOT modify s04 or s07.

State machine (D1 — pure function, ``next_correction_level``):

  | attempt | is_success | correction_level      |
  | ------- | ---------- | --------------------- |
  | 1       | True       | "full"                |
  | 1       | False      | "partial"             |
  | 2       | True       | "full"                |
  | 2       | False      | "partial_attempt_2"   |
  | 3       | True       | "full"                |
  | 3       | False      | "full_after_attempts" |
  | > 3     | any        | "closed" (exception)  |

Design notes:

  * ``partial_attempt_3`` listed in ``CLAUDE.md:307`` is NOT
    implemented — the story prime (AC5) only retains 4 states, and a
    4th attempt is closed rather than "partial_attempt_3".
  * The service's guard ordering is load-bearing: cross-tenant →
    type whitelist → attempt-closed → grade_callback. Any
    reordering breaks the multi-tenant bite tests.
  * The ``grade_callback`` is the **only** source of ``is_success``.
    s08 does not grade.
  * The service does NOT persist anything to ``reward_ledger`` — s20
    will consume ``bonus_points`` from the ``CorrectionResult``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import func

from app.core.database.models import Attempt, Exercise, ExerciseType

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProgressiveCorrectionError(Exception):
    """Controlled failure raised by :meth:`ProgressiveCorrectionService.evaluate`.

    ``kind`` is a stable string the CLI / API can map to an exit code or
    HTTP status without parsing the message. Allowed values:

    * ``exercise_not_found`` — UUID malformed or row missing
    * ``cross_tenant`` — ``Exercise.student_pseudo != pseudo``
    * ``closed`` — ``attempt_number > max_attempts`` (4th attempt)
    * ``invalid_exercise`` — exercise type is FLASHCARDS (not graded)
    * ``storage_failure`` — DB write/rollback failed
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


CorrectionLevel = Literal["partial", "partial_attempt_2", "full", "full_after_attempts"]


class CorrectionResult(BaseModel):
    """The structured outcome of :meth:`ProgressiveCorrectionService.evaluate`."""

    is_success: bool
    feedback: str
    correction_level: CorrectionLevel
    attempt_number: int
    attempt_id: uuid.UUID
    hints: list[str] = Field(default_factory=list)
    next_steps: str | None = None
    solution: str | None = None
    detailed_correction: str | None = None
    common_mistakes: str | None = None
    bonus_points: int = 0


# ---------------------------------------------------------------------------
# Pure state machine (D1)
# ---------------------------------------------------------------------------


def next_correction_level(
    attempt_number: int,
    is_success: bool,
    max_attempts: int = 3,
) -> CorrectionLevel:
    """Return the next ``correction_level`` for the state machine.

    The function is **total on the domain** ``[1, max_attempts]`` and
    raises :class:`ProgressiveCorrectionError` for any
    ``attempt_number > max_attempts``. The truth table is exhaustively
    tested with ``@pytest.mark.parametrize``.
    """
    if attempt_number > max_attempts:
        raise ProgressiveCorrectionError(
            "closed",
            (
                f"Exercice ferme apres {max_attempts} tentatives : "
                f"tentative {attempt_number} refusee."
            ),
        )
    if is_success:
        # AC4 / AC5 — any success at any allowed attempt yields ``full``.
        return "full"
    # Failure path — distinct correction levels per attempt.
    if attempt_number == 1:
        return "partial"
    if attempt_number == 2:
        return "partial_attempt_2"
    # attempt_number == max_attempts (3) and not success
    return "full_after_attempts"


# ---------------------------------------------------------------------------
# Session protocol
# ---------------------------------------------------------------------------


class _SessionLike(Protocol):
    """The slice of a SQLAlchemy session used by the service."""

    def add(self, obj: Any) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def get(self, entity: Any, ident: Any) -> Any: ...
    def query(self, *entities: Any) -> Any: ...


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


# Exercises eligible for the progressive correction flow. ``FLASHCARDS``
# is a study aid and is not graded (D10).
_PROGRESSIVE_TYPES: frozenset[ExerciseType] = frozenset(
    {ExerciseType.QCM, ExerciseType.PROBLEME, ExerciseType.REDACTION}
)


class ProgressiveCorrectionService:
    """Apply the 4-state correction flow to a graded submission.

    The service wraps an external grader (``grade_callback``) that
    already produced a binary ``is_success`` verdict. The flow:

      1. Validate the ``exercise_id`` UUID.
      2. (If ``session_factory`` is wired) Fetch the ``Exercise`` and
         enforce ``Exercise.student_pseudo == pseudo`` (multi-tenant).
         Refused submissions do not call the grader or the hint
         generator.
      3. Refuse ``FLASHCARDS`` exercises (D10).
      4. Compute ``attempt_number`` from the prior ``Attempt`` rows
         and refuse (``closed``) if it would exceed
         ``max_attempts``. **The grader is NOT called on a closed
         exercise** (Piège n°11).
      5. Delegate scoring to ``grade_callback``.
      6. Resolve ``correction_level`` via
         :func:`next_correction_level` (pure).
      7. Build the ``CorrectionResult`` (hints for partials, full
         content for ``full`` / ``full_after_attempts``).
      8. Persist the ``Attempt`` row with ``correction_level``
         populated.

    ``session_factory=None`` is allowed and disables persistence —
    used by CLI stub tests where the service is built without a DB.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], _SessionLike] | None,
        hint_generator: Any | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._session_factory = session_factory
        self._hint_generator = hint_generator
        self._max_attempts = max_attempts

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        pseudo: str,
        exercise_id: str,
        grade_callback: Callable[[Any, str], tuple[bool, str]],
    ) -> CorrectionResult:
        """Run the 4-state correction flow.

        ``grade_callback(exercise, pseudo)`` returns
        ``(is_success, feedback)``. The callback is NEVER called if the
        ownership check, the type whitelist or the closed gate fires.
        """
        # 1. UUID format — same generic error as ``exercise_not_found``
        #    so we never leak the existence of a foreign row. We
        #    deliberately do NOT include the raw input value in the
        #    message — it would distinguish "malformed UUID" from
        #    "unknown UUID" and let an attacker probe the format.
        try:
            exercise_uuid = uuid.UUID(exercise_id)
        except (ValueError, TypeError) as exc:
            raise ProgressiveCorrectionError(
                "exercise_not_found",
                f"Exercise {pseudo!r} introuvable.",
            ) from exc

        # 2. Fetch the exercise (only if a session is wired). The
        #    multi-tenant guard is the FIRST runnable check — the
        #    grader and the hint generator MUST NOT see the foreign
        #    exercise. The same session is reused for the write at
        #    step 8 to keep the read and the persist in one
        #    transaction (avoids the fragility of a double
        #    session_factory call).
        exercise: Any = None
        session: _SessionLike | None = None
        if self._session_factory is not None:
            session = self._session_factory()
            exercise = session.get(Exercise, exercise_uuid)
            if exercise is None:
                raise ProgressiveCorrectionError(
                    "exercise_not_found",
                    f"Exercise {exercise_uuid} introuvable pour le pseudo {pseudo!r}.",
                )
            # Multi-tenant invariant. Same message as not-found so we
            # never leak the existence of a foreign exercise.
            if exercise.student_pseudo != pseudo:
                raise ProgressiveCorrectionError(
                    "cross_tenant",
                    f"Exercise {exercise_uuid} introuvable pour le pseudo {pseudo!r}.",
                )

            # 3. Type whitelist — flashcards are not graded (D10).
            if exercise.type not in _PROGRESSIVE_TYPES:
                raise ProgressiveCorrectionError(
                    "invalid_exercise",
                    (
                        f"Exercise {exercise_uuid} est de type "
                        f"{exercise.type.value!r} ; la correction progressive "
                        f"n'accepte que les exercices de type QCM, PROBLEME ou REDACTION."
                    ),
                )

            # 4. Closed gate — attempt_number computed BEFORE the
            #    grader is called (Piège n°11). This is the load-bearing
            #    guard ordering: closed BEFORE grade_callback.
            attempt_number = self._next_attempt_number(
                session, exercise_uuid, pseudo
            )
            if attempt_number > self._max_attempts:
                raise ProgressiveCorrectionError(
                    "closed",
                    (
                        f"Exercice ferme apres {self._max_attempts} tentatives : "
                        f"tentative {attempt_number} refusee."
                    ),
                )
        else:
            # No session — no DB. ``attempt_number`` defaults to 1.
            attempt_number = 1

        # 5. Delegate scoring to the wrapped grader. By now the
        #    ownership, type and closed gates have all passed.
        is_success, feedback = grade_callback(exercise, pseudo)

        # 6. Resolve the correction level via the pure state machine.
        correction_level: CorrectionLevel = next_correction_level(
            attempt_number, is_success, max_attempts=self._max_attempts
        )

        # 7. Build the result payload.
        attempt_id = uuid.uuid4()
        hints: list[str] = []
        next_steps: str | None = None
        solution: str | None = None
        detailed_correction: str | None = None
        common_mistakes: str | None = None
        bonus_points = 2 if is_success and attempt_number == 1 else 0

        if correction_level in ("partial", "partial_attempt_2"):
            # Hint generator is None-safe: a missing generator yields
            # an empty hints list (the ``full`` / ``full_after_attempts``
            # paths must NOT depend on a generator).
            if self._hint_generator is not None and exercise is not None:
                # Build a HintContext from the exercise. The real
                # ``HintGenerator.generate_hints`` takes a single
                # ``HintContext`` argument — calling it with raw
                # positional args raises ``TypeError`` (this was the
                # s08 review critical finding).
                from app.services.correction.hints import HintContext

                raw_criteria = exercise.grading_criteria
                if isinstance(raw_criteria, list):
                    criteria_list: list[str] | None = [str(c) for c in raw_criteria]
                elif isinstance(raw_criteria, dict):
                    criteria_list = [str(v) for v in raw_criteria.values()]
                else:
                    criteria_list = None
                raw_questions = exercise.questions
                questions_list: list[dict[str, Any]] | None = (
                    [dict(q) for q in raw_questions] if raw_questions else None
                )
                context = HintContext(
                    statement=exercise.statement or "",
                    exercise_type=exercise.type,
                    attempt_number=attempt_number,
                    feedback=feedback,
                    grading_criteria=criteria_list,
                    questions=questions_list,
                )
                hints, next_steps = self._hint_generator.generate_hints(context)
        else:
            # ``full`` or ``full_after_attempts`` — reveal the solution
            # from the persisted exercise. The QCM solution is
            # reconstructed from ``questions``; text exercises use
            # ``expected_answer`` directly.
            solution, detailed_correction, common_mistakes = self._build_solution(exercise)

        # 8. Persist the Attempt row. Same DB row as s04 / s07: the
        #    ``correction_level`` is new (s08) and the rest mirrors
        #    what s04 already writes. The same session opened at
        #    step 2 is reused here so the read and the write are
        #    bound to the same transaction.
        if session is not None:
            try:
                session.add(
                    Attempt(
                        id=attempt_id,
                        exercise_id=exercise_uuid,
                        student_pseudo=pseudo,
                        attempt_number=attempt_number,
                        is_success=is_success,
                        raw_answers=[],
                        correction_level=correction_level,
                    )
                )
                session.commit()
            except Exception as exc:
                session.rollback()
                raise ProgressiveCorrectionError(
                    "storage_failure",
                    f"Impossible de persister l'attempt: {exc}",
                ) from exc

        return CorrectionResult(
            is_success=is_success,
            feedback=feedback,
            correction_level=correction_level,
            attempt_number=attempt_number,
            attempt_id=attempt_id,
            hints=hints,
            next_steps=next_steps,
            solution=solution,
            detailed_correction=detailed_correction,
            common_mistakes=common_mistakes,
            bonus_points=bonus_points,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _build_solution(exercise: Any) -> tuple[str | None, str | None, str | None]:
        """Return ``(solution, detailed_correction, common_mistakes)``.

        For QCM: reconstruct the solution from ``questions`` JSON. For
        text exercises: use ``expected_answer`` directly. ``common_mistakes``
        is left None — there is no field on the ``Exercise`` model for
        it, and s20/s16 will derive it from past attempts if needed.
        """
        if exercise is None:
            return None, None, None
        type_value = getattr(exercise.type, "value", exercise.type)
        if type_value == ExerciseType.QCM.value:
            questions = exercise.questions or []
            lines: list[str] = []
            for i, q in enumerate(questions, 1):
                idx = q.get("correct_index")
                options = q.get("options") or []
                if isinstance(idx, int) and 0 <= idx < len(options):
                    lines.append(f"Q{i}: {options[idx]}")
                else:
                    lines.append(f"Q{i}: (réponse correcte inconnue)")
            return "\n".join(lines), "\n".join(lines) or None, None
        # Probleme / redaction.
        solution = exercise.expected_answer
        return solution, solution, None

    @staticmethod
    def _next_attempt_number(
        session: _SessionLike, exercise_uuid: uuid.UUID, pseudo: str
    ) -> int:
        """Return the next ``attempt_number`` for ``(pseudo, exercise_id)``.

        Mirrors the s04 / s07 ``MAX(attempt_number)`` pattern. On an
        empty table, ``MAX`` returns ``None`` and we start at ``1``.
        """
        current_max = (
            session.query(Attempt)
            .filter(
                Attempt.exercise_id == exercise_uuid,
                Attempt.student_pseudo == pseudo,
            )
            .with_entities(func.max(Attempt.attempt_number))
            .scalar()
        )
        return (current_max or 0) + 1
