"""Reward ledger service (s20a, AC1-AC5, AC8)."""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy.orm import Session

from app.core.database.models import RewardLedger, User, UserPoints


class RewardLedgerService:
    """Append-only ledger for exercise submission rewards.

    The service writes one ``RewardLedger`` row per submission (even
    for 0-point failures, so the audit trail is complete — D3 / AC5).
    The ``UserPoints`` summary is updated in the same transaction with
    ``SELECT ... FOR UPDATE`` (AC5 concurrency guard).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def award_points(
        self,
        pseudo: str,
        exercise_id: Any,
        points: int,
        attempt_number: int,
        is_success: bool,
    ) -> None:
        """Award ``points`` for a submission and update the denormalised summary."""
        # Verify the pseudo exists (multi-tenant guard at DB level).
        user = self._session.query(User).filter_by(pseudo=pseudo).first()
        if user is None:
            raise ValueError(f"Unknown pseudo: {pseudo}")

        # AC5 — SELECT ... FOR UPDATE on UserPoints for concurrency.
        user_points_row = (
            self._session.query(UserPoints)
            .filter_by(student_pseudo=pseudo)
            .with_for_update()
            .first()
        )
        if user_points_row is None:
            user_points_row = UserPoints(student_pseudo=pseudo, total_points=0)
            self._session.add(user_points_row)
            # Flush to get the row for the lock (if DB requires it to exist).
            self._session.flush()

        # Append-only ledger insert (AC8).
        ledger_row = RewardLedger(
            student_pseudo=pseudo,
            exercise_id=exercise_id,
            points_awarded=points,
            attempt_number=attempt_number,
            is_success=is_success,
        )
        self._session.add(ledger_row)

        # Update denormalised total.
        user_points_row.total_points += points
        # The update triggers the server-side onupdate.
        self._session.commit()

        logger.bind(
            request_id="rewards",
            pseudo=pseudo,
            route="/rewards/award_points",
        ).info(
            "rewards.awarded exercise_id={} points={} attempt={} success={}",
            str(exercise_id),
            points,
            attempt_number,
            is_success,
        )
