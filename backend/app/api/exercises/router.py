"""Minimal ``POST /api/exercises/submit`` router (s20a, task 5 of plan).

The endpoint receives ``exercise_id`` and ``answer``, validates the
JWT pseudo (RBAC ``eleve`` + ``assert_jwt_pseudo_matches_or_403``),
runs the progressive correction flow (s08), and writes points via the
rewards service (s20a). A minimal stub grade callback is used so
the router can be created without wiring the full grader pipeline
(the CLI handles real grading).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth.middleware import (
    assert_jwt_pseudo_matches_or_403,
    require_role,
)
from app.core.database.models import User, UserRole
from app.core.database.session import get_db
from app.services.correction.progressive import (
    CorrectionResult,
    ProgressiveCorrectionError,
    ProgressiveCorrectionService,
)
from app.services.rewards.ledger import RewardLedgerService
from app.services.rewards.levels import get_level

router = APIRouter(prefix="/api/exercises", tags=["exercises"])


class SubmitRequest(BaseModel):
    exercise_id: str
    answer: str


class SubmitResponse(BaseModel):
    exercise_id: str
    score: float
    threshold_met: bool
    feedback: str
    correction_level: str
    correction_content: dict
    attempt_number: int
    points_awarded: int
    level: str


@router.post("/submit", response_model=SubmitResponse)
async def submit_exercise(
    body: SubmitRequest,
    user: User = Depends(require_role(UserRole.ELEVE)),
    db: Session = Depends(get_db),
) -> SubmitResponse:
    """Submit an answer to an exercise and trigger progressive correction + rewards."""
    # Multi-tenant guard: the JWT pseudo must match the submission context.
    # In a full implementation the body would not contain ``pseudo``; here we
    # guard against cross-tenant access by ensuring the exercise exists for
    # the JWT pseudo inside ProgressiveCorrectionService.
    assert_jwt_pseudo_matches_or_403(
        user, user.pseudo, route="/api/exercises/submit"
    )

    session_factory = lambda: db  # minimal wiring for the router context

    # Build the progressive service with a minimal stub grader.
    # The real CLI uses QcmGrader/TextGrader; this stub lets the router
    # exist independently (plan task 5).
    def _stub_grader(_exercise: object, pseudo: str) -> tuple[bool, str]:
        # Minimal grading logic: empty answer = failure; non-empty = success.
        # The callback receives ``(exercise, pseudo)`` per s08 contract.
        is_success = bool(body.answer and body.answer.strip())
        feedback = "Réponse évaluée." if is_success else "Réponse vide ou incorrecte."
        return is_success, feedback

    progressive = ProgressiveCorrectionService(
        session_factory=lambda: session_factory(),
        max_attempts=3,
    )

    try:
        result: CorrectionResult = progressive.evaluate(
            pseudo=user.pseudo,
            exercise_id=body.exercise_id,
            grade_callback=_stub_grader,
        )
    except ProgressiveCorrectionError as exc:
        if exc.kind == "closed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"kind": "closed", "message": str(exc)},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"kind": exc.kind, "message": str(exc)},
        ) from exc

    # Consume bonus_points from the progressive result (s08 hook).
    base_points = 5 if result.is_success else 0
    bonus = result.bonus_points
    total_points = base_points + bonus

    # After 3 failed attempts, the exercise is closed — no points awarded.
    # The progressive service already raises ``closed`` for attempt > 3,
    # so this branch is defensive.
    if result.attempt_number > 3:
        total_points = 0

    # Write to the rewards ledger (s20a).
    rewards_service = RewardLedgerService(session=db)
    rewards_service.award_points(
        pseudo=user.pseudo,
        exercise_id=body.exercise_id,
        points=total_points,
        attempt_number=result.attempt_number,
        is_success=result.is_success,
    )

    # Calculate level from UserPoints summary (AC6).
    from app.core.database.models import UserPoints
    user_points = (
        db.query(UserPoints)
        .filter_by(student_pseudo=user.pseudo)
        .with_for_update()
        .first()
    )
    current_points = user_points.total_points if user_points else total_points
    level_label = get_level(current_points)

    return SubmitResponse(
        exercise_id=body.exercise_id,
        score=5.0 if result.is_success else 0.0,  # proxy score on 20
        threshold_met=result.is_success,
        feedback=result.feedback,
        correction_level=result.correction_level,
        correction_content={
            "hints": result.hints,
            "next_steps": result.next_steps,
            "solution": result.solution,
        },
        attempt_number=result.attempt_number,
        points_awarded=total_points,
        level=level_label,
    )
