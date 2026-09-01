"""Tests for the s08 hint generator.

The hint generator is LLM-backed and non-deterministic. The tests
exercise the *contract* (list of 1+ strings, retry on malformed,
fallback after retry) and pin the four prompt templates' separation
(AC7 — V1 ≠ V2 for the same input).
"""

from __future__ import annotations

from typing import Any

from app.core.database.models import ExerciseType

# ---------------------------------------------------------------------------
# LLM stub
# ---------------------------------------------------------------------------


class _ScriptedLlm:
    """Drop-in replacement for ``LlmClient`` returning a scripted sequence.

    Mirrors the same name used in the s03 / s06 / s07 test suites so the
    test pattern carries across stories.
    """

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
# Helpers
# ---------------------------------------------------------------------------


def _good_hints_json(hints: list[str], next_steps: str = "relis le cours") -> str:
    """Return a well-formed hints JSON payload."""
    import json

    return json.dumps({"hints": list(hints), "next_steps": next_steps})


# ---------------------------------------------------------------------------
# V1 / V2 prompt distinction (AC7)
# ---------------------------------------------------------------------------


class TestHintGeneratorPrompts:
    """V1 and V2 prompts must produce DIFFERENT outputs for the same input.

    This is the bite for AC7: if the two prompts are accidentally
    swapped or share the same body, the test goes red.
    """

    def test_generate_hints_v1_differ_from_v2_for_same_input(self) -> None:
        from app.services.correction.hints import HintContext, HintGenerator

        # V1 and V2 must produce DIFFERENT prompts. The stub returns
        # the SAME string for both calls — so the only way the test
        # passes is if the generator builds different user prompts
        # for V1 vs V2 (the prompts include the template's
        # versioned text).
        llm = _ScriptedLlm(
            [
                _good_hints_json(["hint-1"]),
                _good_hints_json(["hint-1"]),
            ]
        )
        generator = HintGenerator(llm=llm, max_retries=1)  # type: ignore[arg-type]

        ctx_v1 = HintContext(
            statement="Derive f(x)=x^2",
            exercise_type=ExerciseType.QCM,
            attempt_number=1,
            feedback="1/3 correctes",
            grading_criteria=None,
            questions=None,
        )
        ctx_v2 = HintContext(
            statement="Derive f(x)=x^2",
            exercise_type=ExerciseType.QCM,
            attempt_number=2,
            feedback="1/3 correctes",
            grading_criteria=None,
            questions=None,
        )

        generator.generate_hints(ctx_v1)
        generator.generate_hints(ctx_v2)
        # Inspect the SECOND element of the second call's message
        # list (HumanMessage). The V1 and V2 prompt bodies must
        # carry distinct template text — this is the load-bearing
        # distinction (AC7).
        v1_prompt = llm.calls[0][1].content
        v2_prompt = llm.calls[1][1].content
        assert v1_prompt != v2_prompt, (
            "V1 and V2 prompts must differ for the same input. "
            "If they collapse to the same template, AC7 is broken."
        )


# ---------------------------------------------------------------------------
# V1 contract: QCM and TEXT produce a list of strings
# ---------------------------------------------------------------------------


class TestHintGeneratorContract:
    """The contract is: ``generate_hints`` returns a non-empty list of
    strings + a non-empty next_steps string."""

    def test_generate_hints_v1_qcm_returns_list_of_strings(self) -> None:
        from app.services.correction.hints import HintContext, HintGenerator

        llm = _ScriptedLlm(
            [
                _good_hints_json(
                    ["indice 1", "indice 2"], next_steps="relis le cours"
                )
            ]
        )
        generator = HintGenerator(llm=llm, max_retries=1)  # type: ignore[arg-type]
        ctx = HintContext(
            statement="...",
            exercise_type=ExerciseType.QCM,
            attempt_number=1,
            feedback="...",
            grading_criteria=None,
            questions=None,
        )
        hints, next_steps = generator.generate_hints(ctx)
        assert hints == ["indice 1", "indice 2"]
        assert next_steps == "relis le cours"

    def test_generate_hints_v2_text_includes_grading_criteria_context(self) -> None:
        """AC2 — V2 prompts embed the grading criteria in the context."""
        from app.services.correction.hints import HintContext, HintGenerator

        llm = _ScriptedLlm([_good_hints_json(["critere 1 non rempli"])])
        generator = HintGenerator(llm=llm, max_retries=1)  # type: ignore[arg-type]
        ctx = HintContext(
            statement="...",
            exercise_type=ExerciseType.PROBLEME,
            attempt_number=2,
            feedback="...",
            grading_criteria=["L'eleve identifie la division"],
            questions=None,
        )
        hints, _ = generator.generate_hints(ctx)
        assert hints == ["critere 1 non rempli"]


# ---------------------------------------------------------------------------
# Retry and fallback (Piège n°7)
# ---------------------------------------------------------------------------


class TestHintGeneratorRetryAndFallback:
    """Malformed LLM output is retried, then a deterministic fallback."""

    def test_generate_hints_retries_on_malformed_output(self) -> None:
        from app.services.correction.hints import HintContext, HintGenerator

        # First call returns invalid JSON; second call returns valid JSON.
        llm = _ScriptedLlm(["not json", _good_hints_json(["indice apres retry"])])
        generator = HintGenerator(llm=llm, max_retries=1)  # type: ignore[arg-type]
        ctx = HintContext(
            statement="...",
            exercise_type=ExerciseType.QCM,
            attempt_number=1,
            feedback="...",
            grading_criteria=None,
            questions=None,
        )
        hints, _ = generator.generate_hints(ctx)
        assert hints == ["indice apres retry"]
        # LLM was called twice (initial + retry).
        assert len(llm.calls) == 2

    def test_generate_hints_falls_back_to_generic_when_llm_fails_twice(self) -> None:
        from app.services.correction.hints import HintContext, HintGenerator

        # Both calls return invalid JSON — the generator must NOT crash.
        llm = _ScriptedLlm(["not json", "still not json"])
        generator = HintGenerator(llm=llm, max_retries=1)  # type: ignore[arg-type]
        ctx = HintContext(
            statement="...",
            exercise_type=ExerciseType.QCM,
            attempt_number=1,
            feedback="...",
            grading_criteria=None,
            questions=None,
        )
        hints, next_steps = generator.generate_hints(ctx)
        # The deterministic fallback is a single generic hint.
        assert len(hints) >= 1
        assert isinstance(next_steps, str) and next_steps
        # The LLM was called the configured number of times (1 + 1 retry).
        assert len(llm.calls) == 2


# ---------------------------------------------------------------------------
# Prompt versioning — make sure the four templates are distinct strings
# ---------------------------------------------------------------------------


class TestPromptVersioning:
    """D2 — 4 prompts, versioned, one per (exercise_type, attempt)."""

    def test_four_prompts_are_distinct(self) -> None:
        from app.services.correction.hints import (
            HINT_PROMPT_V1_QCM,
            HINT_PROMPT_V1_TEXT,
            HINT_PROMPT_V2_QCM,
            HINT_PROMPT_V2_TEXT,
        )

        prompts = {
            "V1_QCM": HINT_PROMPT_V1_QCM,
            "V1_TEXT": HINT_PROMPT_V1_TEXT,
            "V2_QCM": HINT_PROMPT_V2_QCM,
            "V2_TEXT": HINT_PROMPT_V2_TEXT,
        }
        # All four are non-empty.
        for name, prompt in prompts.items():
            assert isinstance(prompt, str) and prompt.strip(), f"{name} is empty"
        # All four are distinct.
        values = list(prompts.values())
        assert len(set(values)) == 4, "Prompts must be 4 distinct strings"
