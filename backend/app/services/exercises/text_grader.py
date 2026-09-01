"""Free-form text grader (s07).

Grades a free-form text submission (``probleme`` or ``redaction``)
against a previously generated ``Exercise`` row using an LLM-as-judge.

The grading is NON-DETERMINISTIC by nature — the LLM produces a
qualitative ``VERDICT:`` line plus a one-sentence feedback. The pipeline:

  1. validate the answer length is within ``max_answer_chars`` (D4.a) —
     refuse early WITHOUT calling the LLM
  2. validate ``exercise_id`` is a UUID
  3. fetch the ``Exercise`` (or raise ``exercise_not_found``)
  4. **multi-tenant invariant**: ``Exercise.student_pseudo == pseudo``,
     otherwise ``cross_tenant`` (no leak — same message as not found)
  5. **D2.a / D2.b**: refuse if the exercise is not a free-form type
     (``PROBLEME`` or ``REDACTION``). ``QCM`` and ``FLASHCARDS`` are
     rejected with ``invalid_exercise_type``.
  6. **defense-in-depth**: check that ``statement``, ``expected_answer``
     and ``grading_criteria`` are non-empty
  7. build a soft prompt and call the LLM; on parse failure, retry
     ONCE with a strictly different prompt that drops any prose
     tolerance (Piège 4)
  8. parse the ``VERDICT:`` line with a strict regex; if neither
     attempt produced one, raise ``verdict_missing``
  9. derive ``attempt_number`` per ``(pseudo, exercise_id)`` via a
     ``MAX(attempt_number)`` query — *not* a global counter
  10. persist the ``Attempt`` row with ``answer_text`` populated and
      ``raw_answers=[]`` (rollback on failure)
  11. return the structured :class:`TextGradingResult`

The class is intentionally narrow — like :class:`QcmGrader`, it does
one thing and inherits the same dependency-injection convention (a
``session_factory`` and an ``LlmClient`` passed at construction time).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy import func

from app.core.database.models import Attempt, Exercise, ExerciseType
from app.services.llm.client import LlmClient

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# ``VERDICT:`` is the canonical line emitted by the LLM. The regex is
# case-insensitive (``re.IGNORECASE``) on the keyword and strict on the
# verdict value — an English ``VERDICT: SUCCESS`` does NOT match and
# the grade falls into ``verdict_missing`` (Piège 5).
VERDICT_RE = re.compile(r"VERDICT:\s*(REUSSITE|ECHEC)", re.IGNORECASE)

# A complete set of free-form exercise types. ``QCM`` and ``FLASHCARDS``
# are explicitly rejected — they have their own grading paths
# (``submit-qcm`` for QCM; flashcards are a study aid with no grading).
_FREE_FORM_TYPES: frozenset[ExerciseType] = frozenset(
    {ExerciseType.PROBLEME, ExerciseType.REDACTION}
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TextGradingError(Exception):
    """Controlled failure raised by :meth:`TextGrader.grade`.

    ``kind`` is a stable string the CLI / API can map to an exit code or
    HTTP status without parsing the message.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TextSubmission(BaseModel):
    """The student's free-form text answer, validated at the boundary.

    ``max_length=8000`` is the safety net below the ``String(8192)``
    column ceiling of ``Attempt.answer_text`` (models.py:194) — the
    CLI and the grader share the same value through
    ``settings.text_grader_max_answer_chars``.
    """

    answer: str = Field(min_length=1, max_length=8000)


class TextGradingResult(BaseModel):
    """The successful outcome of :meth:`TextGrader.grade`."""

    is_success: bool
    feedback: str
    attempt_id: uuid.UUID
    attempt_number: int


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

# System prompt — locks the role, the language and the format the LLM
# must respect. The two retry-attempt user prompts below re-emphasise
# these rules in case the LLM tries to slip.
_TEXT_GRADER_SYSTEM_PROMPT = (
    "Tu es un enseignant francophone qui évalue la réponse d'un élève. "
    "Tu n'es PAS un générateur d'exercices : tu compares la réponse de "
    "l'élève à la réponse attendue et aux critères d'évaluation fournis. "
    "Tu réponds UNIQUEMENT en français. Tu termines ta réponse par "
    "EXACTEMENT une ligne au format :\n"
    "  VERDICT: REUSSITE\n"
    "ou\n"
    "  VERDICT: ECHEC\n"
    "Tu peux écrire une ou deux phrases d'appréciation AVANT la ligne "
    "VERDICT, puis tu termines par la ligne VERDICT et rien d'autre. "
    "Tu es STRICT : ne donne REUSSITE que si la réponse couvre les "
    "critères principaux. Si la réponse est hors sujet, manifestement "
    "fausse ou ne démontre pas la compréhension attendue, donne ECHEC."
)

# Soft user prompt — used on the first attempt. Allows one or two
# sentences of prose before the ``VERDICT:`` line. The 1-based
# criteria are joined into a bullet list so the LLM has a clear
# checklist.
_USER_PROMPT_TEMPLATE = (
    "Énoncé :\n{statement}\n\n"
    "Réponse attendue :\n{expected_answer}\n\n"
    "Critères d'évaluation :\n{criteria}\n\n"
    "Réponse de l'élève :\n{answer}\n\n"
    "Donne ton appréciation en une ou deux phrases, puis termine par "
    "EXACTEMENT une ligne au format :\n"
    "  VERDICT: REUSSITE\n"
    "ou\n"
    "  VERDICT: ECHEC"
)

# Strict user prompt — used on the retry. Excludes any prose tolerance
# and re-emphasises the format. The prompt is genuinely different from
# the soft one so reloading the LLM with the same input has no chance
# of changing the output (Piège 4).
_STRICT_USER_PROMPT_TEMPLATE = (
    "Réponds UNIQUEMENT en français. Aucune autre langue acceptée.\n"
    "Format OBLIGATOIRE : une ou deux phrases d'appréciation, puis "
    "une ligne finale EXACTE :\n"
    "  VERDICT: REUSSITE\n"
    "ou\n"
    "  VERDICT: ECHEC\n"
    "Pas de JSON. Pas de markdown. Pas de traduction anglaise.\n\n"
    "Énoncé :\n{statement}\n\n"
    "Réponse attendue :\n{expected_answer}\n\n"
    "Critères d'évaluation :\n{criteria}\n\n"
    "Réponse de l'élève :\n{answer}"
)


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


class TextGrader:
    """Grade a free-form text submission via an LLM-as-judge.

    The grader enforces the multi-tenant invariant and the type
    whitelist on the ``Exercise`` BEFORE doing any LLM work. The
    ``attempt_number`` is per ``(pseudo, exercise_id)`` so concurrent
    attempts on different exercises do not interfere.
    """

    def __init__(
        self,
        *,
        llm: LlmClient,
        session_factory: Callable[[], _SessionLike] | None = None,
        max_retries: int = 1,
        temperature: float = 0.0,
        max_answer_chars: int = 8000,
    ) -> None:
        self._llm = llm
        self._session_factory = session_factory
        self._max_retries = max_retries
        self._temperature = temperature
        self._max_answer_chars = max_answer_chars

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def grade(
        self,
        pseudo: str,
        exercise_id: str,
        answer: str,
    ) -> TextGradingResult:
        """Grade ``answer`` against the exercise ``exercise_id``.

        Raises :class:`TextGradingError` on every controlled failure. On
        success, returns the structured result AND has persisted the
        matching ``Attempt`` row.

        The method does not call the LLM unless ownership, type and
        payload invariants are all satisfied — see the module docstring
        for the full pipeline.
        """
        # 1. Boundary validation: refuse early WITHOUT calling the LLM
        #    if the answer is empty or too long. Pydantic's
        #    ``TextSubmission`` enforces ``min_length=1`` and
        #    ``max_length=8000`` (the same value as the column ceiling
        #    margin).
        try:
            submission = TextSubmission(answer=answer)
        except Exception as exc:  # Pydantic ValidationError
            # Empty / too-long answer: D4.a refuses rather than
            # silently truncating (Piège 3).
            if len(answer) > self._max_answer_chars:
                raise TextGradingError(
                    "answer_too_long",
                    (
                        f"Réponse trop longue : {len(answer)} caractères, "
                        f"maximum {self._max_answer_chars}."
                    ),
                ) from exc
            raise TextGradingError(
                "invalid_answers", f"Réponse invalide : {exc}"
            ) from exc

        # 2. Validate the UUID format up front.
        try:
            exercise_uuid = uuid.UUID(exercise_id)
        except (ValueError, TypeError) as exc:
            raise TextGradingError(
                "exercise_not_found", f"exercise_id invalide: {exercise_id}"
            ) from exc

        if self._session_factory is None:
            raise TextGradingError(
                "storage_failure",
                "TextGrader n'a pas de session_factory : impossible de charger l'exercice.",
            )

        session = self._session_factory()

        # 3. Fetch the exercise.
        exercise = session.get(Exercise, exercise_uuid)
        if exercise is None:
            raise TextGradingError(
                "exercise_not_found",
                f"Exercise {exercise_uuid} introuvable pour le pseudo {pseudo!r}.",
            )

        # 4. Multi-tenant invariant. Same message as not-found so we
        #    never leak the existence of a foreign exercise.
        if exercise.student_pseudo != pseudo:
            raise TextGradingError(
                "cross_tenant",
                f"Exercise {exercise_uuid} introuvable pour le pseudo {pseudo!r}.",
            )

        # 5. D2.a / D2.b: refuse any non-free-form exercise type. The
        #    LLM must NOT be called on a QCM (deterministic grading
        #    goes through ``submit-qcm``) or on flashcards (study aid,
        #    no grading).
        if exercise.type not in _FREE_FORM_TYPES:
            raise TextGradingError(
                "invalid_exercise_type",
                (
                    f"Exercise {exercise_uuid} est de type "
                    f"{exercise.type.value!r} ; ``submit-text`` n'accepte "
                    f"que les exercices de type probleme ou redaction."
                ),
            )

        # 6. Defense-in-depth — every free-form exercise must carry
        #    statement / expected_answer / grading_criteria. The
        #    ``submit-text`` command is the only call site of this
        #    grader, so a missing field here means a malformed DB row.
        if (
            not exercise.statement
            or not exercise.expected_answer
            or not exercise.grading_criteria
        ):
            raise TextGradingError(
                "invalid_exercise",
                (
                    f"Exercise {exercise_uuid} n'a pas les champs requis "
                    f"(statement, expected_answer, grading_criteria)."
                ),
            )

        # 7. Build the prompts once (the inputs are stable across the
        #    retry loop) and call the LLM.
        criteria_text = "\n".join(f"  - {c}" for c in (exercise.grading_criteria or []))
        system = SystemMessage(content=_TEXT_GRADER_SYSTEM_PROMPT)
        user_soft = HumanMessage(
            content=_USER_PROMPT_TEMPLATE.format(
                statement=exercise.statement,
                expected_answer=exercise.expected_answer,
                criteria=criteria_text,
                answer=submission.answer,
            )
        )
        user_strict = HumanMessage(
            content=_STRICT_USER_PROMPT_TEMPLATE.format(
                statement=exercise.statement,
                expected_answer=exercise.expected_answer,
                criteria=criteria_text,
                answer=submission.answer,
            )
        )

        is_success, feedback = self._grade_with_retry(system, user_soft, user_strict)

        # 8. Per-(pseudo, exercise_id) attempt counter. ``MAX(attempt_number)``
        #    is the only reliable source of truth: an in-memory counter
        #    would be wrong across grader instances / process restarts.
        attempt_number = self._next_attempt_number(session, exercise_uuid, pseudo)

        # 9. Persist the attempt. ``raw_answers=[]`` because free-form
        #    submissions do not carry question/option indices (QCM does).
        attempt_id = uuid.uuid4()
        try:
            session.add(
                Attempt(
                    id=attempt_id,
                    exercise_id=exercise_uuid,
                    student_pseudo=pseudo,
                    attempt_number=attempt_number,
                    is_success=is_success,
                    raw_answers=[],
                    answer_text=submission.answer,
                )
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            raise TextGradingError(
                "storage_failure",
                f"Impossible de persister l'attempt : {exc}",
            ) from exc

        return TextGradingResult(
            is_success=is_success,
            feedback=feedback,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _grade_with_retry(
        self,
        system: SystemMessage,
        user_soft: HumanMessage,
        user_strict: HumanMessage,
    ) -> tuple[bool, str]:
        """Call the LLM with the soft prompt, then the strict prompt.

        Returns ``(is_success, feedback)`` on the first call that emits
        a parseable ``VERDICT:`` line. Raises ``TextGradingError(
        "verdict_missing")`` after the configured number of retries.
        """
        # The number of attempts is ``max_retries + 1``: the soft call
        # plus ``max_retries`` strict calls. The default (1 retry)
        # gives 2 total attempts which matches s03 / s06 / s06b.
        attempts = max(1, self._max_retries + 1)
        for i in range(attempts):
            user = user_soft if i == 0 else user_strict
            output = self._safe_invoke(system, user)
            verdict, feedback = self._parse_verdict(output)
            if verdict is not None:
                return verdict == "reussite", feedback
        # No verdict on any attempt — refuse with a clear error.
        raise TextGradingError(
            "verdict_missing",
            (
                "Le service n'a pas pu analyser ta réponse. Réessaye."
            ),
        )

    def _safe_invoke(self, system: SystemMessage, user: HumanMessage) -> str:
        """Call the LLM and return the text content; never raise.

        ``AIMessage.content`` is normally a string, but some LangChain
        adapters return a list of content blocks. We coerce to ``str``
        so the regex never trips on the wrong type.
        """
        try:
            message = self._llm.invoke([system, user])
        except Exception as exc:
            raise TextGradingError(
                "llm_failure",
                f"Appel LLM impossible : {exc}",
            ) from exc
        content = message.content if isinstance(message, AIMessage) else str(message)
        if isinstance(content, list):
            # Multimodal responses are out of scope; flatten to text.
            content = " ".join(
                str(block.get("text", "")) if isinstance(block, dict) else str(block)
                for block in content
            )
        return str(content)

    @staticmethod
    def _parse_verdict(output: str) -> tuple[str | None, str]:
        """Return ``(verdict_lower | None, feedback)`` from the LLM output.

        ``verdict_lower`` is one of ``"reussite"`` or ``"echec"``. The
        feedback is the text BEFORE the matched ``VERDICT:`` line,
        stripped of leading/trailing whitespace and any leading prose
        markers. ``None`` means the regex did not match — the caller
        will then either retry or raise ``verdict_missing``.
        """
        match = VERDICT_RE.search(output)
        if match is None:
            return None, ""
        verdict = match.group(1).lower()
        # ``re.IGNORECASE`` lets ``REUSSITE``/``reussite``/``Reussite``
        # all match; ``.lower()`` normalises to the canonical form.
        feedback = output[: match.start()].strip()
        return verdict, feedback

    @staticmethod
    def _next_attempt_number(
        session: _SessionLike, exercise_uuid: uuid.UUID, pseudo: str
    ) -> int:
        """Return the next ``attempt_number`` for ``(pseudo, exercise_id)``.

        Uses ``MAX(attempt_number)`` so concurrent grader instances see
        a consistent view. On an empty table, ``MAX`` returns ``None``
        and we start at ``1``.

        Duplicated from :class:`QcmGrader` per D9.a — a refactor into a
        shared helper belongs to s08 (correction progressive) which is
        the first story that needs it from both graders.
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
        # ``func.max`` returns ``None`` on an empty table.
        return (current_max or 0) + 1
