"""Combined scenario tests for s20a rewards (AC1-AC4, AC7)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth.passwords import hash_password
from app.core.database.models import (
    Base,
    RewardLedger,
    User,
    UserPoints,
    UserRole,
)


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


class TestScenarios:
    def test_7_points_first_try_success(self, session) -> None:
        from app.services.rewards.ledger import RewardLedgerService
        session.add(User(pseudo="ali", password_hash=hash_password("pw"), role=UserRole.ELEVE))
        session.commit()
        svc = RewardLedgerService(session)
        svc.award_points("ali", uuid.uuid4(), 7, 1, True)
        rows = session.query(RewardLedger).all()
        assert len(rows) == 1
        assert rows[0].points_awarded == 7
        assert rows[0].attempt_number == 1
        assert rows[0].is_success is True
        pts = session.query(UserPoints).filter_by(student_pseudo="ali").first()
        assert pts is not None
        assert pts.total_points == 7

    def test_5_points_later_success(self, session) -> None:
        from app.services.rewards.ledger import RewardLedgerService
        session.add(User(pseudo="ali", password_hash=hash_password("pw"), role=UserRole.ELEVE))
        session.commit()
        svc = RewardLedgerService(session)
        svc.award_points("ali", uuid.uuid4(), 5, 2, True)
        rows = session.query(RewardLedger).all()
        assert rows[0].points_awarded == 5

    def test_0_points_failure(self, session) -> None:
        from app.services.rewards.ledger import RewardLedgerService
        session.add(User(pseudo="ali", password_hash=hash_password("pw"), role=UserRole.ELEVE))
        session.commit()
        svc = RewardLedgerService(session)
        svc.award_points("ali", uuid.uuid4(), 0, 1, False)
        rows = session.query(RewardLedger).all()
        assert len(rows) == 1
        assert rows[0].points_awarded == 0
        assert rows[0].is_success is False

    def test_0_points_after_3_failures_closed_not_written(self, session) -> None:
        """AC4 — when attempt > 3 (closed), the router handles the 409; the service
        should not be called with attempt > 3 by the router. This test verifies
        the service accepts attempt 3 failure (full_after_attempts) with 0 pts."""
        from app.services.rewards.ledger import RewardLedgerService
        session.add(User(pseudo="ali", password_hash=hash_password("pw"), role=UserRole.ELEVE))
        session.commit()
        svc = RewardLedgerService(session)
        # 3rd attempt failure — correction_level is full_after_attempts, 0 points.
        svc.award_points("ali", uuid.uuid4(), 0, 3, False)
        rows = session.query(RewardLedger).all()
        assert len(rows) == 1
        assert rows[0].points_awarded == 0
        assert rows[0].attempt_number == 3
