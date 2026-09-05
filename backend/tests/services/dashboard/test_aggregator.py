"""Tests for ``app.services.dashboard.aggregator`` (s16).

The aggregator is a **pure function** over a SQLAlchemy session. The
tests build a tiny SQLite database in memory, seed an eleve + a few
exercises and attempts, and assert the aggregated output. Five cases
cover the contract:

* an eleve with zero attempts → empty list + zeroed global,
* multi-subject grouping with ``mean(is_success)``,
* global average is over **all** attempts, not the mean of subject
  averages (the classical bug),
* per-pseudo isolation (alice's attempts are never visible to bob's
  aggregator call),
* ``last_activity_at`` is the max of ``submitted_at`` per scope,
* ``CAST(is_success AS FLOAT)`` is present in the compiled SQL — a
  regression guard for the PostgreSQL/SQLite float-division drift
  (see Major #2 in docs/reviews/s16-dashboard-eleve.md).
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth.passwords import hash_password
from app.core.database.models import (
    Attempt,
    Base,
    Document,
    DocumentStatus,
    Exercise,
    ExerciseType,
    Subject,
    User,
    UserRole,
)
from app.services.dashboard.aggregator import aggregate_eleve_dashboard

# ---------------------------------------------------------------------------
# DB fixtures — local to this file (no refactor transverse per AGENTS.md).
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def session(session_factory) -> Iterator[Session]:
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


def _make_user(pseudo: str, role: UserRole = UserRole.ELEVE) -> User:
    return User(
        pseudo=pseudo,
        password_hash=hash_password("studentpassword"),
        role=role,
    )


def _make_document(pseudo: str, subject: Subject) -> Document:
    return Document(
        id=uuid.uuid4(),
        student_pseudo=pseudo,
        subject=subject,
        filename="cours.pdf",
        s3_key=f"students/{pseudo}/{uuid.uuid4()}/cours.pdf",
        chunks_count=1,
        status=DocumentStatus.INDEXED,
    )


def _make_exercise(
    pseudo: str,
    subject: Subject,
    document_id: uuid.UUID,
    type_: ExerciseType = ExerciseType.QCM,
) -> Exercise:
    return Exercise(
        id=uuid.uuid4(),
        student_pseudo=pseudo,
        subject=subject,
        type=type_,
        document_id=document_id,
        questions=[],
    )


def _make_attempt(
    exercise: Exercise,
    pseudo: str,
    is_success: bool,
    submitted_at: datetime,
    attempt_number: int = 1,
) -> Attempt:
    return Attempt(
        id=uuid.uuid4(),
        exercise_id=exercise.id,
        student_pseudo=pseudo,
        attempt_number=attempt_number,
        is_success=is_success,
        raw_answers=[],
        submitted_at=submitted_at,
    )


def _seed_eleve_with_attempts(
    session: Session,
    pseudo: str,
    attempts_per_subject: dict[Subject, list[tuple[bool, datetime]]],
) -> dict[Subject, Exercise]:
    """Create a user, one document + one exercise per subject, and a
    list of attempts. Returns a mapping subject → exercise for callers
    that need it (none of the current tests do, but kept for
    forward-compat)."""
    user = _make_user(pseudo)
    session.add(user)
    session.flush()

    exercises: dict[Subject, Exercise] = {}
    for subject in attempts_per_subject:
        doc = _make_document(pseudo, subject)
        session.add(doc)
        session.flush()
        exo = _make_exercise(pseudo, subject, doc.id)
        session.add(exo)
        session.flush()
        exercises[subject] = exo

    for subject, attempts in attempts_per_subject.items():
        exo = exercises[subject]
        for idx, (is_success, submitted_at) in enumerate(attempts, start=1):
            # SQLite drops the tzinfo on the way through; the test
            # backends expect naive datetimes, the production
            # PostgreSQL backend preserves them. We store tz-aware
            # values; assertions normalise both sides below.
            session.add(
                _make_attempt(exo, pseudo, is_success, submitted_at, attempt_number=idx)
            )
    session.commit()
    return exercises


def _as_naive(dt: datetime | None) -> datetime | None:
    """SQLite (the test backend) strips timezone info on roundtrip;
    PostgreSQL preserves it. Normalise both sides for comparison."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_empty_when_eleve_has_no_attempts(session: Session) -> None:
    _make_user("alice")
    session.commit()

    resp = aggregate_eleve_dashboard(session, "alice")

    assert resp.subjects == []
    assert resp.model_dump(by_alias=True)["global"] == {
        "score_avg": 0.0,
        "exercises_count": 0,
        "last_activity_at": None,
        "total_points": 0,
        "level": "Apprenti",
    }


def test_groups_by_subject_with_mean_is_success(session: Session) -> None:
    base = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    _seed_eleve_with_attempts(
        session,
        "alice",
        {
            Subject.MATHS: [
                (True, base),
                (True, base + timedelta(hours=1)),
                (False, base + timedelta(hours=2)),
            ],
            Subject.FRANCAIS: [
                (True, base + timedelta(hours=3)),
                (False, base + timedelta(hours=4)),
            ],
        },
    )

    resp = aggregate_eleve_dashboard(session, "alice")
    by_subject = {s.name: s for s in resp.subjects}

    assert by_subject["maths"].score_avg == pytest.approx(2 / 3)
    assert by_subject["maths"].exercises_count == 3
    assert _as_naive(by_subject["maths"].last_activity_at) == _as_naive(base + timedelta(hours=2))

    assert by_subject["francais"].score_avg == pytest.approx(0.5)
    assert by_subject["francais"].exercises_count == 2
    assert _as_naive(by_subject["francais"].last_activity_at) == _as_naive(base + timedelta(hours=4))


def test_global_avg_is_overall_not_mean_of_subjects(session: Session) -> None:
    # 3 maths attempts (2 success, 1 fail) + 1 francais attempt (fail).
    # Global mean over 4 attempts = (2 + 0) / 4 = 0.5.
    # Mean of subject means = (2/3 + 0/1) / 2 = 1/3 — WRONG.
    base = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    _seed_eleve_with_attempts(
        session,
        "alice",
        {
            Subject.MATHS: [
                (True, base),
                (True, base + timedelta(hours=1)),
                (False, base + timedelta(hours=2)),
            ],
            Subject.FRANCAIS: [
                (False, base + timedelta(hours=3)),
            ],
        },
    )

    resp = aggregate_eleve_dashboard(session, "alice")
    assert resp.model_dump(by_alias=True)["global"]["score_avg"] == pytest.approx(0.5)
    assert resp.model_dump(by_alias=True)["global"]["exercises_count"] == 4


def test_filters_by_student_pseudo(session: Session) -> None:
    # alice has 3 maths attempts, bob has 2 francais attempts. The
    # aggregator must ONLY return alice's data when called for alice.
    base = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    _seed_eleve_with_attempts(
        session,
        "alice",
        {Subject.MATHS: [(True, base), (True, base + timedelta(hours=1)), (False, base + timedelta(hours=2))]},
    )
    _seed_eleve_with_attempts(
        session,
        "bob",
        {Subject.FRANCAIS: [(True, base + timedelta(hours=3)), (False, base + timedelta(hours=4))]},
    )

    alice_resp = aggregate_eleve_dashboard(session, "alice")
    assert [s.name for s in alice_resp.subjects] == ["maths"]
    assert alice_resp.model_dump(by_alias=True)["global"]["exercises_count"] == 3

    bob_resp = aggregate_eleve_dashboard(session, "bob")
    assert [s.name for s in bob_resp.subjects] == ["francais"]
    assert bob_resp.model_dump(by_alias=True)["global"]["exercises_count"] == 2


def test_last_activity_at_is_max_submitted_at(session: Session) -> None:
    # The aggregator must pick the latest submitted_at across all of
    # alice's attempts, not the first. With three timestamps, the
    # global last_activity_at must equal the max — the same as the
    # most recent attempt, which is not necessarily the most recent
    # per subject.
    base = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    ts1 = base
    ts2 = base + timedelta(days=5)  # the max
    ts3 = base + timedelta(days=2)
    _seed_eleve_with_attempts(
        session,
        "alice",
        {
            Subject.MATHS: [(True, ts1), (True, ts2), (False, ts3)],
            Subject.FRANCAIS: [(True, ts3)],
        },
    )

    resp = aggregate_eleve_dashboard(session, "alice")
    assert _as_naive(resp.model_dump(by_alias=True)["global"]["last_activity_at"]) == _as_naive(ts2)

    maths = next(s for s in resp.subjects if s.name == "maths")
    assert _as_naive(maths.last_activity_at) == _as_naive(ts2)

    francais = next(s for s in resp.subjects if s.name == "francais")
    assert _as_naive(francais.last_activity_at) == _as_naive(ts3)


def test_aggregator_compiles_cast_is_success_as_float(db_engine) -> None:
    """Regression guard: ``CAST(is_success AS FLOAT)`` must be present in
    BOTH queries (per-subject + global) emitted by the aggregator.

    Why this test exists: SQLite (test backend) returns a float for
    ``AVG(bool_col)`` even without an explicit CAST, so the existing
    behaviour-driven tests do NOT catch a missing CAST. PostgreSQL
    (production) does integer division on a bool column, which would
    silently produce 0.0 for any eleve whose success rate is below
    100% and non-zero attempts. Hooking into SQLAlchemy's
    ``before_cursor_execute`` event to capture the rendered SQL is
    the only backend-agnostic way to pin the invariant (cf. review
    Major #2).

    See ``docs/reviews/s16-dashboard-eleve.md`` and the inline
    comment in ``app.services.dashboard.aggregator`` for the full
    rationale.
    """
    Sess = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    s = Sess()
    try:
        # Seed one user + one exercise to give the per-subject query
        # a single row to aggregate. No attempts needed: the CAST
        # appears in the SELECT list regardless of result rows.
        user = _make_user("alice")
        s.add(user)
        s.flush()
        doc = _make_document("alice", Subject.MATHS)
        s.add(doc)
        s.flush()
        exo = _make_exercise("alice", Subject.MATHS, doc.id)
        s.add(exo)
        s.commit()

        # Capture the SQL the aggregator actually emits.
        captured: list[str] = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            captured.append(statement)

        from sqlalchemy import event

        event.listen(db_engine, "before_cursor_execute", _record)
        try:
            aggregate_eleve_dashboard(s, "alice")
        finally:
            event.remove(db_engine, "before_cursor_execute", _record)
    finally:
        s.close()

    # The aggregator runs three SELECTs: points query, per-subject query,
    # and global query. We assert the CAST appears in the two attempt queries.
    assert len(captured) == 3, (
        f"Expected 3 SELECTs from the aggregator, got {len(captured)}: {captured}"
    )

    # captured[0] = points SELECT, [1] = per-subject, [2] = global
    per_subject_sql, global_sql = captured[1], captured[2]
    assert "CAST(attempts.is_success AS FLOAT)" in per_subject_sql, (
        "Per-subject query is missing CAST(is_success AS FLOAT). "
        "Without the cast, PostgreSQL returns integer-division AVG "
        "(0 instead of 0.667 for 2/3 successes). SQLite silently "
        "returns a float and hides the bug from the test suite."
    )
    assert "CAST(attempts.is_success AS FLOAT)" in global_sql, (
        "Global query is missing CAST(is_success AS FLOAT). Same "
        "PostgreSQL/SQLite drift as the per-subject query."
    )
