"""Hint generation for the progressive correction service (s08).

The hint generator is LLM-backed. For each ``(exercise_type, attempt)``
pair a distinct prompt is used:

  * ``HINT_PROMPT_V1_QCM``  — first attempt on a QCM (concept hint)
  * ``HINT_PROMPT_V2_QCM``  — second attempt on a QCM (error type)
  * ``HINT_PROMPT_V1_TEXT`` — first attempt on free-form text
  * ``HINT_PROMPT_V2_TEXT`` — second attempt on free-form text

The generator does 1 retry on malformed output and falls back to a
generic hint if the second attempt also fails. The fallback is
deterministic (Piège n°7) so the test suite and the user experience
are predictable when the upstream LLM misbehaves.

The hint generator does NOT use ``_parsing.extract_json_block`` (the
mutualized s06 helper) — its LLM output is simpler (a single JSON
object) and a regex pass is enough. Keeping this dependency out
preserves s08's footprint.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from app.core.database.models import ExerciseType

# ---------------------------------------------------------------------------
# Prompt templates (D2 — 4 distinct versioned prompts)
# ---------------------------------------------------------------------------


# V1 QCM: ask the LLM to point the student at the underlying CONCEPT
# (the lesson notion the QCM is testing). One to three short hints.
HINT_PROMPT_V1_QCM = (
    "L'eleve a echoue a un QCM. Donne 1 a 3 indices sur le CONCEPT teste "
    "(la notion du cours que l'exercice evalue). Sois bref, encourageant. "
    "Reponds UNIQUEMENT en JSON valide de la forme : "
    '{"hints": ["..."], "next_steps": "..."}. '
    "Aucun texte autour du JSON. Aucun markdown. Aucune excuse."
)

# V2 QCM: the student has already seen V1 hints. The V2 prompt asks
# the LLM to identify the TYPE OF ERROR (misunderstanding vs
# inattention) and to be more specific. Intentionally distinct from
# V1 — AC7.
HINT_PROMPT_V2_QCM = (
    "L'eleve a deja recu les indices generaux (V1) et a re-echoue. "
    "Identifie le TYPE D'ERREUR (mauvaise comprehension du concept vs "
    "distraction / lecture rapide) et donne 1 a 3 indices PRECIS sur "
    "l'erreur. Reponds UNIQUEMENT en JSON valide : "
    '{"hints": ["..."], "next_steps": "..."}. '
    "Aucun texte autour. Aucun markdown."
)

# V1 TEXT: free-form text. The hint must point the student at
# grading criteria they DID NOT meet.
HINT_PROMPT_V1_TEXT = (
    "L'eleve a soumis une reponse libre a un probleme ou une redaction "
    "et a echoue. Donne 1 a 3 indices sur les CRITERES D'EVALUATION "
    "qu'il n'a PAS remplis (cf. grading_criteria ci-dessous). "
    "Reponds UNIQUEMENT en JSON valide : "
    '{"hints": ["..."], "next_steps": "..."}. '
    "Aucun texte autour du JSON. Aucun markdown."
)

# V2 TEXT: see V1, plus the error type and the history of prior
# hints. Intentionally distinct from V1 — AC7.
HINT_PROMPT_V2_TEXT = (
    "L'eleve a deja recu les indices generaux (V1) sur les criteres non "
    "remplis et a re-echoue. Identifie le TYPE D'ERREUR (reponse "
    "hors-sujet vs incomplete vs mal structuree) et donne 1 a 3 "
    "indices PRECIS. Reponds UNIQUEMENT en JSON valide : "
    '{"hints": ["..."], "next_steps": "..."}. '
    "Aucun texte autour. Aucun markdown."
)


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


# Deterministic generic hint returned after 1+1 failed LLM attempts.
# Same content regardless of the exercise — the goal is to keep the
# CLI flow responsive even when the LLM is down.
_FALLBACK_HINTS: tuple[str, ...] = (
    "Relis le cours lie a cet exercice et reessaye.",
)
_FALLBACK_NEXT_STEPS = "Consulte tes notes et reessaye demain."


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HintContext:
    """The minimum the hint generator needs to build a prompt."""

    statement: str
    exercise_type: ExerciseType
    attempt_number: int
    feedback: str
    grading_criteria: list[str] | None
    questions: list[dict[str, Any]] | None


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class HintGenerator:
    """Call the LLM to produce a list of progressive hints.

    The generator is intentionally narrow — it does not own a
    database, an exercise loader or a session. The service s08
    fetches the ``Exercise`` and hands the relevant context to
    :meth:`generate_hints`.
    """

    def __init__(self, *, llm: Any, max_retries: int = 1) -> None:
        self._llm = llm
        self._max_retries = max_retries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_hints(
        self, context: HintContext
    ) -> tuple[list[str], str]:
        """Return ``(hints, next_steps)`` for the given context.

        On the first attempt, the configured prompt is sent. On a
        malformed response, ONE strict retry is sent. If the retry
        also fails, a deterministic fallback is returned.
        """
        prompt = self._build_prompt(context)
        attempts = max(1, self._max_retries + 1)
        for i in range(attempts):
            user = prompt if i == 0 else self._strict_prompt(prompt)
            try:
                response_text = self._safe_invoke(user)
            except Exception as exc:  # noqa: BLE001
                # LLM-side failure — go to the next attempt or fall
                # back. The error is not re-raised: the service must
                # always return a usable (hints, next_steps) tuple.
                # The bare except is intentional: the LLM client
                # surface is broad (timeouts, JSON errors, transport,
                # OpenRouter upstream). We log the failure so the
                # operator can see it; the fallback keeps the user
                # flow responsive.
                logger.warning(
                    "hint_generator.llm_failure attempt={} error={!r}",
                    i + 1,
                    exc,
                )
                continue
            parsed = self._parse_hints(response_text)
            if parsed is not None:
                return parsed
        return list(_FALLBACK_HINTS), _FALLBACK_NEXT_STEPS

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_prompt(self, context: HintContext) -> str:
        """Return the user-prompt body for the given context."""
        criteria_text = ""
        if context.grading_criteria:
            criteria_text = "\n".join(f"  - {c}" for c in context.grading_criteria)
        questions_text = ""
        if context.questions:
            questions_text = "\n".join(
                f"  Q{i + 1}: {q.get('question', '')}" for i, q in enumerate(context.questions)
            )

        # Choose the versioned prompt template.
        is_qcm = context.exercise_type == ExerciseType.QCM
        if context.attempt_number <= 1:
            template = HINT_PROMPT_V1_QCM if is_qcm else HINT_PROMPT_V1_TEXT
        else:
            template = HINT_PROMPT_V2_QCM if is_qcm else HINT_PROMPT_V2_TEXT

        return (
            f"{template}\n\n"
            f"Enonce : {context.statement}\n\n"
            f"Reponse de l'eleve (apprise par le grader) : {context.feedback}\n\n"
            f"Critere(s) d'evaluation :\n{criteria_text or '  (aucun)'}\n\n"
            f"Questions :\n{questions_text or '  (aucune)'}\n"
        )

    @staticmethod
    def _strict_prompt(soft_prompt: str) -> str:
        """Return a strict version of the prompt for the retry attempt.

        The strict variant re-emphasises that the LLM must output
        ONLY the JSON object — no prose, no markdown, no apology."""
        return (
            "Reponds UNIQUEMENT en JSON valide. Aucun texte autour. "
            "Aucun markdown. Aucune phrase d'introduction. "
            "Format EXACT : {\"hints\": [str, ...], \"next_steps\": str}\n\n"
            f"{soft_prompt}"
        )

    def _safe_invoke(self, user_prompt: str) -> str:
        """Call the LLM and return the text content. Never raises."""
        from langchain_core.messages import AIMessage

        message = self._llm.invoke(
            [SystemMessage(content="Tu es un enseignant."), HumanMessage(content=user_prompt)]
        )
        content = message.content if isinstance(message, AIMessage) else str(message)
        if isinstance(content, list):
            content = " ".join(
                str(block.get("text", "")) if isinstance(block, dict) else str(block)
                for block in content
            )
        return str(content)

    @staticmethod
    def _parse_hints(output: str) -> tuple[list[str], str] | None:
        """Return ``(hints, next_steps)`` parsed from the LLM output.

        Returns ``None`` if the output is not parseable — the caller
        will then either retry or fall back. The parser tolerates
        fenced code blocks (``\\`\\`\\`json ... \\`\\`\\```) and bare
        JSON objects.
        """
        if not output:
            return None
        # Strip a leading/trailing markdown fence if present.
        cleaned = output.strip()
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match is None:
            return None
        try:
            data = json.loads(match.group(0))
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        hints = data.get("hints")
        next_steps = data.get("next_steps")
        if not isinstance(hints, list) or not all(isinstance(h, str) for h in hints):
            return None
        if not isinstance(next_steps, str):
            return None
        if not hints:
            return None
        return hints, next_steps
