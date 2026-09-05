"""Tests for ``GET /api/dashboard/parent`` (s17).

Four behaviour families:

* **Auth** — no token → 401 ``invalid_token``; an ``eleve`` bearer
  → 403 ``forbidden`` (RBAC: parent or admin only).
* **Happy** — bearer parent with 0 children → 200 with
  ``children: []`` (empty list, not 404); bearer parent with
  N linked children → 200 with each child wrapped in its own
  :class:`EleveDashboardResponse`.
* **Cache** — the per-pseudo cache populated by the eleve
  endpoint is reused. A second call must NOT re-aggregate.
* **Cross-tenant** — parent Alice must NOT see parent Paul's
  children (parent-scoped filter); admin sees every link.

The fixtures are duplicated from ``test_eleve.py`` and
``test_users_parent_child.py`` per AGENTS.md « Pas de refactor
transverse ».
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth.jwt import create_access_token
from app.core.auth.passwords import hash_password
from app.core.database.models import (
    Attempt,
    Base,
    Document,
    DocumentStatus,
    Exercise,
    ExerciseType,
    ParentChildLink,
    Subject,
    User,
    UserRole,
)
from app.core.database.session import get_db
from app.main import app
from app.services.dashboard import cache as dashboard_cache

# ---------------------------------------------------------------------------
# RSA keypair + settings (duplicated per AGENTS.md).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_dashboard_parent")
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


def _seeded_user(session_factory, pseudo: str, role: UserRole) -> User:
    with session_factory() as db:
        user = User(
            pseudo=pseudo,
            password_hash=hash_password("seedpassword1"),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.pseudo, user.role)}"}


def _seed_link(session_factory, parent_pseudo: str, child_pseudo: str) -> None:
    with session_factory() as db:
        db.add(
            ParentChildLink(parent_pseudo=parent_pseudo, child_pseudo=child_pseudo)
        )
        db.commit()


def _seed_attempts(
    session_factory,
    pseudo: str,
    subject: Subject,
    successes: int,
    fails: int,
) -> None:
    """Mirror the s16 helper so the test surface is identical."""
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
        base = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
        for n, is_success in enumerate(
            [True] * successes + [False] * fails, start=1
        ):
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


@pytest.fixture()
def seeded_parent_alice(session_factory) -> User:
    return _seeded_user(session_factory, "alice", UserRole.PARENT)


@pytest.fixture()
def seeded_parent_paul(session_factory) -> User:
    return _seeded_user(session_factory, "paul", UserRole.PARENT)


@pytest.fixture()
def seeded_eleve_bob(session_factory) -> User:
    return _seeded_user(session_factory, "bob", UserRole.ELEVE)


@pytest.fixture()
def seeded_eleve_charlie(session_factory) -> User:
    return _seeded_user(session_factory, "charlie", UserRole.ELEVE)


@pytest.fixture()
def seeded_eleve_dave(session_factory) -> User:
    return _seeded_user(session_factory, "dave", UserRole.ELEVE)


@pytest.fixture()
def seeded_admin(session_factory) -> User:
    return _seeded_user(session_factory, "boss", UserRole.ADMIN)


@pytest.fixture(autouse=True)
def _reset_dashboard_cache() -> Iterator[None]:
    """Clear the in-process cache before and after each test.

    The cache key is per ``child_pseudo``; we wipe the four
    pseudos used by this suite. Anything left from a prior
    test would mask the cache assertions.
    """
    pseudos = ["alice", "bob", "charlie", "dave"]
    for p in pseudos:
        dashboard_cache.invalidate_dashboard(p)
    yield
    for p in pseudos:
        dashboard_cache.invalidate_dashboard(p)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestGetParentDashboardAuth:
    def test_no_token_returns_401_invalid_token(
        self, client: TestClient, session_factory
    ) -> None:
        _seeded_user(session_factory, "alice", UserRole.PARENT)
        resp = client.get("/api/dashboard/parent")
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"]["code"] == "invalid_token"

    def test_eleve_returns_403_forbidden(
        self,
        client: TestClient,
        seeded_eleve_bob: User,
    ) -> None:
        """The endpoint is parent-or-admin only. An eleve who hits it
        gets 403 ``forbidden`` (s15 RBAC contract), not an empty list."""
        resp = client.get("/api/dashboard/parent", headers=_bearer(seeded_eleve_bob))
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"


# ---------------------------------------------------------------------------
# Happy
# ---------------------------------------------------------------------------


class TestGetParentDashboardHappy:
    def test_returns_empty_list_when_parent_has_no_children(
        self,
        client: TestClient,
        seeded_parent_alice: User,
    ) -> None:
        resp = client.get(
            "/api/dashboard/parent", headers=_bearer(seeded_parent_alice)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"children": []}

    def test_returns_dashboards_for_all_linked_children(
        self,
        client: TestClient,
        seeded_parent_alice: User,
        seeded_eleve_bob: User,
        seeded_eleve_charlie: User,
        session_factory,
    ) -> None:
        _seed_link(session_factory, seeded_parent_alice.pseudo, seeded_eleve_bob.pseudo)
        _seed_link(session_factory, seeded_parent_alice.pseudo, seeded_eleve_charlie.pseudo)
        _seed_attempts(session_factory, "bob", Subject.MATHS, successes=2, fails=0)
        _seed_attempts(session_factory, "charlie", Subject.MATHS, successes=1, fails=1)

        resp = client.get(
            "/api/dashboard/parent", headers=_bearer(seeded_parent_alice)
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["children"]) == 2
        by_pseudo = {c["pseudo"]: c for c in body["children"]}
        assert by_pseudo["bob"]["dashboard"]["global"]["exercises_count"] == 2
        assert by_pseudo["charlie"]["dashboard"]["global"]["exercises_count"] == 2
        # linked_at is a string (ISO 8601) in the JSON.
        assert "linked_at" in by_pseudo["bob"]
        assert "linked_at" in by_pseudo["charlie"]


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestGetParentDashboardCache:
    def test_reuses_eleve_cache_for_child_dashboards(
        self,
        client: TestClient,
        seeded_parent_alice: User,
        seeded_eleve_bob: User,
        seeded_eleve_charlie: User,
        session_factory,
    ) -> None:
        """The parent endpoint must NOT introduce a new cache key.
        The per-child cache populated by the first call is hit on
        the second call → ``aggregate_eleve_dashboard`` is invoked
        0 times on the second call.

        The spy is patched at the helper's import path (the
        aggregator is invoked from ``app.api.dashboard.parent``).
        """
        _seed_link(session_factory, seeded_parent_alice.pseudo, seeded_eleve_bob.pseudo)
        _seed_link(session_factory, seeded_parent_alice.pseudo, seeded_eleve_charlie.pseudo)
        _seed_attempts(session_factory, "bob", Subject.MATHS, successes=1, fails=0)
        _seed_attempts(session_factory, "charlie", Subject.MATHS, successes=1, fails=0)

        # Import the original function so the spy can ``wraps`` it
        # (the test must exercise the real SQL, not a stub).
        from app.api.dashboard import parent as parent_module
        real_aggregator = parent_module.aggregate_eleve_dashboard

        with patch.object(
            parent_module, "aggregate_eleve_dashboard", wraps=real_aggregator
        ) as spy:
            first = client.get(
                "/api/dashboard/parent", headers=_bearer(seeded_parent_alice)
            )
            assert first.status_code == 200, first.text
            # 2 children → 2 cold aggregations.
            assert spy.call_count == 2

            second = client.get(
                "/api/dashboard/parent", headers=_bearer(seeded_parent_alice)
            )
            assert second.status_code == 200
            # Cache hit on both children → 0 additional aggregations.
            assert spy.call_count == 2


# ---------------------------------------------------------------------------
# Cross-tenant
# ---------------------------------------------------------------------------


class TestGetParentDashboardCrossTenant:
    def test_parent_alice_does_not_see_pauls_children(
        self,
        client: TestClient,
        seeded_parent_alice: User,
        seeded_parent_paul: User,
        seeded_eleve_bob: User,
        seeded_eleve_charlie: User,
        session_factory,
    ) -> None:
        """Cross-tenant isolation: Alice is linked to Bob, Paul is
        linked to Charlie. Alice must NOT see Charlie in her
        response."""
        _seed_link(session_factory, seeded_parent_alice.pseudo, seeded_eleve_bob.pseudo)
        _seed_link(session_factory, seeded_parent_paul.pseudo, seeded_eleve_charlie.pseudo)

        resp = client.get(
            "/api/dashboard/parent", headers=_bearer(seeded_parent_alice)
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [c["pseudo"] for c in body["children"]] == ["bob"]

    def test_admin_sees_all_links(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_parent_alice: User,
        seeded_parent_paul: User,
        seeded_eleve_bob: User,
        seeded_eleve_charlie: User,
        session_factory,
    ) -> None:
        """Admin bypass (ADR 005): the admin sees every link in the
        system, regardless of parent."""
        _seed_link(session_factory, seeded_parent_alice.pseudo, seeded_eleve_bob.pseudo)
        _seed_link(session_factory, seeded_parent_paul.pseudo, seeded_eleve_charlie.pseudo)

        resp = client.get("/api/dashboard/parent", headers=_bearer(seeded_admin))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        pseudos = {c["pseudo"] for c in body["children"]}
        assert {"bob", "charlie"} <= pseudos


# ---------------------------------------------------------------------------
# Integration: the /api/dashboard/eleve router must accept a parent
# caller for a linked child. The s17 plan documented the
# `assert_parent_linked_to_child_or_403` helper as "covering our
# case" through the s16 endpoint with `?pseudo=`, but the wiring
# was missed in commit f908d92: the endpoint only called
# `assert_jwt_pseudo_matches_or_403`, which 403s every non-self
# non-admin caller. Review #1 (critical).
# ---------------------------------------------------------------------------


class TestGetEleveDashboardAsParentViaEleveRouter:
    def test_parent_can_fetch_linked_child_dashboard(
        self,
        client: TestClient,
        seeded_parent_alice: User,
        seeded_eleve_bob: User,
        session_factory,
    ) -> None:
        """The real ``/api/dashboard/eleve?pseudo=bob`` endpoint must
        return 200 with Bob's dashboard when a parent Alice (linked
        to Bob) calls it. Before the fix the endpoint rejected every
        non-self parent with 403 ``forbidden``."""
        _seed_link(session_factory, seeded_parent_alice.pseudo, seeded_eleve_bob.pseudo)
        _seed_attempts(session_factory, "bob", Subject.MATHS, successes=1, fails=0)

        resp = client.get(
            "/api/dashboard/eleve",
            params={"pseudo": "bob"},
            headers=_bearer(seeded_parent_alice),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["global"]["exercises_count"] == 1

    def test_parent_cannot_fetch_unlinked_child_dashboard(
        self,
        client: TestClient,
        seeded_parent_alice: User,
        seeded_eleve_charlie: User,
        session_factory,
    ) -> None:
        """Same endpoint, but the parent is NOT linked to the child.
        Must 403 ``forbidden``."""
        # No _seed_link — Alice is not linked to charlie.
        resp = client.get(
            "/api/dashboard/eleve",
            params={"pseudo": "charlie"},
            headers=_bearer(seeded_parent_alice),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_parent_querying_own_dashboard_via_eleve_router(
        self,
        client: TestClient,
        seeded_parent_alice: User,
        session_factory,
    ) -> None:
        """A parent asking for their OWN dashboard (no link involved)
        must still get 200. The s15 self-match branch carries over."""
        resp = client.get(
            "/api/dashboard/eleve",
            params={"pseudo": "alice"},
            headers=_bearer(seeded_parent_alice),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The aggregator returns 0 attempts for a parent with none.
        assert body["global"]["exercises_count"] == 0

    def test_admin_can_fetch_any_child_dashboard_via_eleve_router(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_eleve_bob: User,
        session_factory,
    ) -> None:
        """The s15 admin-bypass branch must still work after the
        wiring change. Admin → Bob → 200."""
        _seed_attempts(session_factory, "bob", Subject.MATHS, successes=2, fails=0)

        resp = client.get(
            "/api/dashboard/eleve",
            params={"pseudo": "bob"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["global"]["exercises_count"] == 2

    def test_unlinked_eleve_cannot_fetch_another_eleve_dashboard(
        self,
        client: TestClient,
        seeded_eleve_bob: User,
        seeded_eleve_charlie: User,
        session_factory,
    ) -> None:
        """Regression check for the s15 contract: an eleve who is
        not linked to the requested child (no ParentChildLink row)
        must still 403. The new helper must not weaken the guard
        for non-parent roles."""
        # No link — bob and charlie are independent eleves.
        resp = client.get(
            "/api/dashboard/eleve",
            params={"pseudo": "charlie"},
            headers=_bearer(seeded_eleve_bob),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"
