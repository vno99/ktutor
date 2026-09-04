"""Tests for ``GET /api/dashboard/eleve`` (s16).

Four behaviour families:

* **Auth** — no token or expired token → 401 ``invalid_token``;
  the body never reveals *why* the token is invalid.
* **Happy** — bearer alice + N attempts → 200 with the aggregated
  payload; bearer bob with no attempts → 200 with the empty
  payload (not 404 — the dashboard is a "no data" state, not a
  missing resource).
* **Cache** — two consecutive calls return the same payload and
  the aggregator is called once; an explicit invalidation forces a
  re-aggregation on the next call.
* **Cross-tenant** — bob with ``?pseudo=alice`` → 403
  ``forbidden``; admin with ``?pseudo=alice`` → 200 (admin bypass
  via the s15 helper). Same for ``?pseudo=self``.

The router lives in ``backend/app/api/dashboard/eleve.py`` and the
helper is wired in :func:`client` via the same JWT-fixture pattern
as the other API tests.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker
from unittest.mock import patch

from app.core.auth.jwt import create_access_token
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
from app.core.database.session import get_db
from app.main import app
from app.services.dashboard import cache as dashboard_cache


# ---------------------------------------------------------------------------
# RSA keypair + settings (duplicated from test_users_create / test_documents
# per AGENTS.md « Pas de refactor transverse »).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_dashboard")
    private_path = tmp / "jwt_private.pem"
    public_path = tmp / "jwt_public.pem"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return {"private": private_path, "public": public_path}


@pytest.fixture(autouse=True)
def _point_settings(
    monkeypatch: pytest.MonkeyPatch, rsa_keypair: dict[str, Path]
) -> None:
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(rsa_keypair["private"]))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(rsa_keypair["public"]))
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")


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
def client(session_factory) -> Iterator[TestClient]:
    def _override_get_db() -> Iterator[Session]:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_user(session_factory, pseudo: str, role: UserRole) -> User:
    with session_factory() as db:
        user = User(
            pseudo=pseudo,
            password_hash=hash_password("studentpassword"),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.pseudo, user.role)}"}


def _seed_attempts(
    session_factory,
    pseudo: str,
    subject: Subject,
    successes: int,
    fails: int,
) -> None:
    """Create one document + one exercise for ``pseudo`` and a number
    of attempts (``successes`` True, ``fails`` False) for the given
    subject. Submitted-at increases monotonically so the tests can
    assert on ``last_activity_at``."""
    with session_factory() as db:
        doc = Document(
            id=uuid.uuid4(),
            student_pseudo=pseudo,
            subject=subject,
            filename="cours.pdf",
            s3_key=f"students/{pseudo}/{uuid.uuid4()}/cours.pdf",
            chunks_count=1,
            status=DocumentStatus.INDEXED,
        )
        db.add(doc)
        db.flush()
        exo = Exercise(
            id=uuid.uuid4(),
            student_pseudo=pseudo,
            subject=subject,
            type=ExerciseType.QCM,
            document_id=doc.id,
            questions=[],
        )
        db.add(exo)
        db.flush()
        base = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
        n = 0
        for is_success in [True] * successes + [False] * fails:
            n += 1
            db.add(
                Attempt(
                    id=uuid.uuid4(),
                    exercise_id=exo.id,
                    student_pseudo=pseudo,
                    attempt_number=n,
                    is_success=is_success,
                    raw_answers=[],
                    submitted_at=base + timedelta(hours=n),
                )
            )
        db.commit()


@pytest.fixture(autouse=True)
def _reset_dashboard_cache() -> Iterator[None]:
    # Each test starts with an empty in-process cache. The helpers
    # below are the only public way to clear; calling them for the
    # pseudos that show up in this suite is enough.
    dashboard_cache.invalidate_dashboard("alice")
    dashboard_cache.invalidate_dashboard("bob")
    yield
    dashboard_cache.invalidate_dashboard("alice")
    dashboard_cache.invalidate_dashboard("bob")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestGetEleveDashboardAuth:
    def test_no_token_returns_401_invalid_token(
        self, client: TestClient, session_factory
    ) -> None:
        _seed_user(session_factory, "alice", UserRole.ELEVE)
        resp = client.get("/api/dashboard/eleve")
        assert resp.status_code == 401
        body = resp.json()
        # FastAPI wraps the HTTPException detail under "detail" — the
        # body itself is the {error, code} dict the contract documents.
        assert body["detail"]["code"] == "invalid_token"

    def test_expired_token_returns_401_invalid_token(
        self, client: TestClient, session_factory
    ) -> None:
        alice = _seed_user(session_factory, "alice", UserRole.ELEVE)
        token = create_access_token(
            alice.pseudo, alice.role, expires_delta=timedelta(seconds=-1)
        )
        resp = client.get(
            "/api/dashboard/eleve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# Happy
# ---------------------------------------------------------------------------


class TestGetEleveDashboardHappy:
    def test_returns_aggregated_data_for_authenticated_eleve(
        self, client: TestClient, session_factory
    ) -> None:
        alice = _seed_user(session_factory, "alice", UserRole.ELEVE)
        _seed_attempts(session_factory, "alice", Subject.MATHS, successes=2, fails=1)
        _seed_attempts(session_factory, "alice", Subject.FRANCAIS, successes=1, fails=1)

        resp = client.get("/api/dashboard/eleve", headers=_bearer(alice))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["global"]["exercises_count"] == 5
        # 3 successes / 5 attempts
        assert body["global"]["score_avg"] == pytest.approx(0.6)
        by_subject = {s["name"]: s for s in body["subjects"]}
        assert by_subject["maths"]["exercises_count"] == 3
        assert by_subject["maths"]["score_avg"] == pytest.approx(2 / 3)
        assert by_subject["francais"]["exercises_count"] == 2
        assert by_subject["francais"]["score_avg"] == pytest.approx(0.5)

    def test_returns_empty_when_eleve_has_no_attempts(
        self, client: TestClient, session_factory
    ) -> None:
        bob = _seed_user(session_factory, "bob", UserRole.ELEVE)
        resp = client.get("/api/dashboard/eleve", headers=_bearer(bob))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["subjects"] == []
        assert body["global"]["exercises_count"] == 0
        assert body["global"]["score_avg"] == 0.0
        assert body["global"]["last_activity_at"] is None


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestGetEleveDashboardCache:
    def test_second_call_within_ttl_returns_cached_data(
        self, client: TestClient, session_factory
    ) -> None:
        alice = _seed_user(session_factory, "alice", UserRole.ELEVE)
        _seed_attempts(session_factory, "alice", Subject.MATHS, successes=1, fails=0)

        with patch(
            "app.api.dashboard.eleve.aggregate_eleve_dashboard",
            wraps=__import__(
                "app.api.dashboard.eleve", fromlist=["aggregate_eleve_dashboard"]
            ).aggregate_eleve_dashboard,
        ) as spy:
            first = client.get("/api/dashboard/eleve", headers=_bearer(alice))
            second = client.get("/api/dashboard/eleve", headers=_bearer(alice))
            assert first.status_code == 200
            assert second.status_code == 200
            assert first.json() == second.json()
            assert spy.call_count == 1

    def test_invalidation_clears_cache(
        self, client: TestClient, session_factory
    ) -> None:
        alice = _seed_user(session_factory, "alice", UserRole.ELEVE)
        _seed_attempts(session_factory, "alice", Subject.MATHS, successes=1, fails=0)

        with patch(
            "app.api.dashboard.eleve.aggregate_eleve_dashboard",
            wraps=__import__(
                "app.api.dashboard.eleve", fromlist=["aggregate_eleve_dashboard"]
            ).aggregate_eleve_dashboard,
        ) as spy:
            client.get("/api/dashboard/eleve", headers=_bearer(alice))
            assert spy.call_count == 1
            dashboard_cache.invalidate_dashboard("alice")
            client.get("/api/dashboard/eleve", headers=_bearer(alice))
            assert spy.call_count == 2


# ---------------------------------------------------------------------------
# Cross-tenant
# ---------------------------------------------------------------------------


class TestGetEleveDashboardCrossTenant:
    def test_eleve_bob_cannot_query_alice_via_query_param(
        self, client: TestClient, session_factory
    ) -> None:
        _seed_user(session_factory, "alice", UserRole.ELEVE)
        bob = _seed_user(session_factory, "bob", UserRole.ELEVE)
        _seed_attempts(session_factory, "alice", Subject.MATHS, successes=1, fails=0)

        resp = client.get(
            "/api/dashboard/eleve",
            params={"pseudo": "alice"},
            headers=_bearer(bob),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_admin_can_query_any_eleve_via_query_param(
        self, client: TestClient, session_factory
    ) -> None:
        _seed_user(session_factory, "alice", UserRole.ELEVE)
        admin = _seed_user(session_factory, "boss", UserRole.ADMIN)
        _seed_attempts(session_factory, "alice", Subject.MATHS, successes=1, fails=0)

        resp = client.get(
            "/api/dashboard/eleve",
            params={"pseudo": "alice"},
            headers=_bearer(admin),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["global"]["exercises_count"] == 1

    def test_eleve_alice_cannot_query_bob_via_query_param(
        self, client: TestClient, session_factory
    ) -> None:
        _seed_user(session_factory, "bob", UserRole.ELEVE)
        alice = _seed_user(session_factory, "alice", UserRole.ELEVE)

        resp = client.get(
            "/api/dashboard/eleve",
            params={"pseudo": "bob"},
            headers=_bearer(alice),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"
