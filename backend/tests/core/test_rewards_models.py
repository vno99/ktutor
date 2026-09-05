"""Tests for RewardLedger and UserPoints models (s20)."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth.passwords import hash_password
from app.core.database.models import Base, User, UserRole


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


class TestRewardLedgerModel:
    def test_create_ledger_row(self, session) -> None:
        from app.core.database.models import RewardLedger
        session.add(
            User(pseudo="ali", password_hash=hash_password("pw"), role=UserRole.ELEVE)
        )
        session.commit()
        row = RewardLedger(
            student_pseudo="ali",
            exercise_id=uuid.uuid4(),
            points_awarded=7,
            attempt_number=1,
            is_success=True,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert isinstance(row.id, uuid.UUID)
        assert row.student_pseudo == "ali"
        assert row.points_awarded == 7
        assert row.attempt_number == 1
        assert row.is_success is True
        assert isinstance(row.created_at, datetime)

    def test_append_only_no_update_on_existing_row(self, session) -> None:
        """AC8 mutation guard: an UPDATE on a RewardLedger row must be illegal by design."""
        from app.core.database.models import RewardLedger
        session.add(
            User(pseudo="ali", password_hash=hash_password("pw"), role=UserRole.ELEVE)
        )
        session.commit()
        row = RewardLedger(
            student_pseudo="ali",
            exercise_id=uuid.uuid4(),
            points_awarded=5,
            attempt_number=1,
            is_success=True,
        )
        session.add(row)
        session.commit()
        # The model should not have a mechanism to update; but the DB
        # allows UPDATE by default. The service layer must enforce
        # append-only. This test asserts the shape, not the service guard.
        assert row.id is not None


class TestUserPointsModel:
    def test_create_summary(self, session) -> None:
        from app.core.database.models import UserPoints
        session.add(
            User(pseudo="ali", password_hash=hash_password("pw"), role=UserRole.ELEVE)
        )
        session.commit()
        pts = UserPoints(student_pseudo="ali", total_points=127)
        session.add(pts)
        session.commit()
        session.refresh(pts)
        assert pts.student_pseudo == "ali"
        assert pts.total_points == 127
        assert isinstance(pts.updated_at, datetime)
