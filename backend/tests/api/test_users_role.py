"""Tests for ``PUT /api/users/{pseudo}/role`` (s13b).

The endpoint is **admin-only** (JWT + ``require_role(UserRole.ADMIN)``)
and changes a user's role to one of ``eleve`` / ``parent`` / ``admin``.

The most delicate contract is the "last admin" self-demote guard
(``TestUpdateRoleSelfDemoteBlocked``): an admin who tries to demote
themselves while being the **only** admin in the system must be
rejected with 409 ``self_demote_blocked`` and the DB must remain
unchanged (the role stays ``ADMIN``).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth.jwt import create_access_token
from app.core.auth.passwords import hash_password
from app.core.database.models import Base, User, UserRole
from app.core.database.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# RSA keypair fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_users_role")
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


# ---------------------------------------------------------------------------
# DB + client fixtures
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


def _seeded(role: UserRole, pseudo: str) -> User:
    return User(
        pseudo=pseudo,
        password_hash=hash_password("seedpassword1"),
        role=role,
    )


@pytest.fixture()
def seeded_admin(session_factory) -> User:
    with session_factory() as db:
        user = _seeded(UserRole.ADMIN, "boss")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_parent(session_factory) -> User:
    with session_factory() as db:
        user = _seeded(UserRole.PARENT, "pat")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_eleve(session_factory) -> User:
    with session_factory() as db:
        user = _seeded(UserRole.ELEVE, "ali")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.pseudo, user.role)}"}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestUpdateRoleHappyPath:
    def test_admin_promote_eleve_to_parent(
        self, client: TestClient, seeded_admin: User, seeded_eleve: User, session_factory
    ) -> None:
        resp = client.put(
            f"/api/users/{seeded_eleve.pseudo}/role",
            json={"role": "parent"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"pseudo": "ali", "role": "parent"}

        with session_factory() as db:
            row = db.query(User).filter(User.pseudo == "ali").one()
        assert row.role is UserRole.PARENT

    def test_admin_change_parent_to_admin(
        self, client: TestClient, seeded_admin: User, seeded_parent: User, session_factory
    ) -> None:
        resp = client.put(
            f"/api/users/{seeded_parent.pseudo}/role",
            json={"role": "admin"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"pseudo": "pat", "role": "admin"}

        with session_factory() as db:
            row = db.query(User).filter(User.pseudo == "pat").one()
        assert row.role is UserRole.ADMIN

    def test_admin_demote_parent_to_eleve(
        self, client: TestClient, seeded_admin: User, seeded_parent: User, session_factory
    ) -> None:
        resp = client.put(
            f"/api/users/{seeded_parent.pseudo}/role",
            json={"role": "eleve"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"pseudo": "pat", "role": "eleve"}

        with session_factory() as db:
            row = db.query(User).filter(User.pseudo == "pat").one()
        assert row.role is UserRole.ELEVE


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class TestUpdateRoleAuth:
    def test_parent_caller_returns_403(
        self, client: TestClient, seeded_parent: User, seeded_eleve: User
    ) -> None:
        resp = client.put(
            f"/api/users/{seeded_eleve.pseudo}/role",
            json={"role": "parent"},
            headers=_bearer(seeded_parent),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_eleve_caller_returns_403(
        self, client: TestClient, seeded_eleve: User
    ) -> None:
        resp = client.put(
            f"/api/users/{seeded_eleve.pseudo}/role",
            json={"role": "parent"},
            headers=_bearer(seeded_eleve),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_no_token_returns_401(
        self, client: TestClient, seeded_eleve: User
    ) -> None:
        resp = client.put(
            f"/api/users/{seeded_eleve.pseudo}/role",
            json={"role": "parent"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestUpdateRoleValidation:
    def test_unknown_role_returns_422(
        self, client: TestClient, seeded_admin: User, seeded_eleve: User
    ) -> None:
        resp = client.put(
            f"/api/users/{seeded_eleve.pseudo}/role",
            json={"role": "guest"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 422

    def test_missing_body_returns_422(
        self, client: TestClient, seeded_admin: User, seeded_eleve: User
    ) -> None:
        resp = client.put(
            f"/api/users/{seeded_eleve.pseudo}/role",
            json={},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Not found
# ---------------------------------------------------------------------------


class TestUpdateRoleNotFound:
    def test_unknown_pseudo_returns_404(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        resp = client.put(
            "/api/users/ghost/role",
            json={"role": "parent"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "user_not_found"


# ---------------------------------------------------------------------------
# Self-demote guard: the contract that protects against locking the
# system out by removing the only admin.
# ---------------------------------------------------------------------------


class TestUpdateRoleSelfDemoteBlocked:
    def test_last_admin_self_demote_returns_409(
        self, client: TestClient, seeded_admin: User, session_factory
    ) -> None:
        """Sole admin tries to demote themselves → 409, DB unchanged."""
        resp = client.put(
            f"/api/users/{seeded_admin.pseudo}/role",
            json={"role": "eleve"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "self_demote_blocked"

        with session_factory() as db:
            row = db.query(User).filter(User.pseudo == seeded_admin.pseudo).one()
        assert row.role is UserRole.ADMIN

    def test_last_admin_self_demote_to_parent_returns_409(
        self, client: TestClient, seeded_admin: User, session_factory
    ) -> None:
        """``role: "parent"`` is also a self-demote (no longer ADMIN)."""
        resp = client.put(
            f"/api/users/{seeded_admin.pseudo}/role",
            json={"role": "parent"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "self_demote_blocked"

        with session_factory() as db:
            row = db.query(User).filter(User.pseudo == seeded_admin.pseudo).one()
        assert row.role is UserRole.ADMIN

    def test_admin_with_a_second_admin_can_self_demote(
        self, client: TestClient, seeded_admin: User, session_factory
    ) -> None:
        """With another admin present, the self-demote is allowed."""
        with session_factory() as db:
            db.add(
                User(
                    pseudo="co_admin",
                    password_hash=hash_password("secondadminpw"),
                    role=UserRole.ADMIN,
                )
            )
            db.commit()

        resp = client.put(
            f"/api/users/{seeded_admin.pseudo}/role",
            json={"role": "parent"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"pseudo": "boss", "role": "parent"}

        with session_factory() as db:
            row = db.query(User).filter(User.pseudo == "boss").one()
        assert row.role is UserRole.PARENT

    def test_admin_self_role_admin_is_not_a_demote(
        self, client: TestClient, seeded_admin: User, session_factory
    ) -> None:
        """Setting role to ``admin`` is a no-op change, not a self-demote."""
        resp = client.put(
            f"/api/users/{seeded_admin.pseudo}/role",
            json={"role": "admin"},
            headers=_bearer(seeded_admin),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"pseudo": "boss", "role": "admin"}


# ---------------------------------------------------------------------------
# Logging hygiene: the audit log must never carry the password or hash.
# ---------------------------------------------------------------------------


class TestUpdateRoleLoggingHygiene:
    def test_role_change_log_contains_admin_and_target_but_no_secret(
        self,
        client: TestClient,
        seeded_admin: User,
        seeded_eleve: User,
    ) -> None:
        log_buffer: list[str] = []
        from loguru import logger

        handler_id = logger.add(lambda msg: log_buffer.append(str(msg)), level="DEBUG")
        try:
            client.put(
                f"/api/users/{seeded_eleve.pseudo}/role",
                json={"role": "parent"},
                headers=_bearer(seeded_admin),
            )
        finally:
            logger.remove(handler_id)

        joined = "\n".join(log_buffer)
        # No password / hash leaks — even though we never touch them here,
        # the test pins the invariant.
        assert "studentpassword" not in joined
        assert "$2b$12$" not in joined
        # The audit log line was emitted.
        assert "security.role_change" in joined
        assert "admin=boss" in joined
        assert "target=ali" in joined
        assert "old=eleve" in joined
        assert "new=parent" in joined
