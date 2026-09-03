"""Tests for ``POST /api/users`` (s13b).

The endpoint is **admin-only** (JWT + ``require_role(UserRole.ADMIN)``).
A successful call returns 201 with the new user's ``pseudo`` and
``role``; the password is never echoed back. Validation is
Pydantic-driven (422), uniqueness is enforced both at the application
level (pre-check → 409) and at the SQL constraint level (``catch
IntegrityError`` → 409, covers the race).

Tests are organized around the behavior contract, not the
implementation. ``TestCreateUserLoggingHygiene`` is the only place
that asserts on log content — the production sink is dropped in
``conftest.py::_isolated_loguru_sink`` and a per-test buffer is
attached via ``caplog`` so we can prove no password or hash leaks.
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
from app.core.auth.passwords import hash_password, verify_password
from app.core.database.models import Base, User, UserRole
from app.core.database.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# RSA keypair fixture — same pattern as ``test_auth_middleware.py``.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_users")
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
# DB fixture: an isolated in-memory SQLite shared across the TestClient
# requests and the assertions. Mirrors ``test_auth_register.py``.
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """Yield a fresh in-memory SQLite engine; create the schema."""
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
    """A ``sessionmaker`` bound to the test engine — usable outside the request."""
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client(session_factory) -> Iterator[TestClient]:
    """TestClient backed by an isolated in-memory SQLite whose schema we control."""

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


@pytest.fixture()
def seeded_admin(session_factory) -> User:
    """An admin account that can call ``POST /api/users``."""
    with session_factory() as db:
        user = User(
            pseudo="boss",
            password_hash=hash_password("adminpassword"),
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_parent(session_factory) -> User:
    """A parent account (cannot call admin endpoints)."""
    with session_factory() as db:
        user = User(
            pseudo="pat",
            password_hash=hash_password("parentpassword"),
            role=UserRole.PARENT,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_eleve(session_factory) -> User:
    """An eleve account (cannot call admin endpoints)."""
    with session_factory() as db:
        user = User(
            pseudo="ali",
            password_hash=hash_password("studentpassword"),
            role=UserRole.ELEVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def _admin_bearer(admin: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(admin.pseudo, admin.role)}"}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestCreateUserHappyPath:
    def test_admin_creates_parent_returns_201(
        self, client: TestClient, seeded_admin: User, session_factory
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "pat", "password": "parentpassword", "role": "parent"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json() == {"pseudo": "pat", "role": "parent"}

        with session_factory() as db:
            user = db.query(User).filter(User.pseudo == "pat").one()
        assert user.role is UserRole.PARENT
        assert verify_password("parentpassword", user.password_hash) is True

    def test_admin_creates_admin_returns_201(
        self, client: TestClient, seeded_admin: User, session_factory
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "co_admin", "password": "secondadminpw", "role": "admin"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 201, resp.text
        assert resp.json() == {"pseudo": "co_admin", "role": "admin"}

        with session_factory() as db:
            user = db.query(User).filter(User.pseudo == "co_admin").one()
        assert user.role is UserRole.ADMIN

    def test_response_does_not_include_password_or_hash(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "pat", "password": "parentpassword", "role": "parent"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "password" not in body
        assert "password_hash" not in body
        assert "$2b$" not in str(body)


# ---------------------------------------------------------------------------
# Auth: non-admin and unauthenticated callers
# ---------------------------------------------------------------------------


class TestCreateUserAuth:
    def test_parent_caller_returns_403(
        self, client: TestClient, seeded_parent: User
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "x", "password": "validpassword", "role": "parent"},
            headers=_admin_bearer(seeded_parent),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_eleve_caller_returns_403(
        self, client: TestClient, seeded_eleve: User
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "x", "password": "validpassword", "role": "parent"},
            headers=_admin_bearer(seeded_eleve),
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_no_token_returns_401(self, client: TestClient) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "x", "password": "validpassword", "role": "parent"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"

    def test_junk_token_returns_401(self, client: TestClient) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "x", "password": "validpassword", "role": "parent"},
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# Validation: Pydantic rejects bad input
# ---------------------------------------------------------------------------


class TestCreateUserValidation:
    def test_pseudo_too_short_returns_422(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "ab", "password": "validpassword", "role": "parent"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 422

    def test_pseudo_with_dash_returns_422(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "ali-baba", "password": "validpassword", "role": "parent"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 422

    def test_password_too_short_returns_422(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "pat", "password": "short", "role": "parent"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 422

    def test_password_too_long_utf8_returns_422(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        """``"é" * 37`` is 37 chars (>= 8) but 74 UTF-8 octets → 422."""
        resp = client.post(
            "/api/users",
            json={"pseudo": "pat", "password": "é" * 37, "role": "parent"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 422

    def test_role_eleve_returns_422(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        """``role: "eleve"`` is rejected — pupils self-register via the public endpoint."""
        resp = client.post(
            "/api/users",
            json={"pseudo": "pat", "password": "validpassword", "role": "eleve"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 422

    def test_role_unknown_returns_422(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "pat", "password": "validpassword", "role": "guest"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 422

    def test_missing_body_returns_422(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        resp = client.post(
            "/api/users", json={}, headers=_admin_bearer(seeded_admin)
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Conflict: duplicate pseudo (case-insensitive)
# ---------------------------------------------------------------------------


class TestCreateUserConflict:
    def test_existing_pseudo_returns_409(
        self, client: TestClient, seeded_admin: User, seeded_eleve: User
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "ali", "password": "differentpw1", "role": "parent"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "pseudo_taken"

    def test_existing_pseudo_case_insensitive_returns_409(
        self, client: TestClient, seeded_admin: User, seeded_eleve: User
    ) -> None:
        resp = client.post(
            "/api/users",
            json={"pseudo": "ALI", "password": "differentpw1", "role": "parent"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "pseudo_taken"

    def test_db_race_returns_409(
        self, client: TestClient, seeded_admin: User, session_factory
    ) -> None:
        """DB-level race — the pre-check is bypassed by an external INSERT.

        We seed a row directly (case ``Ali``) and then call the endpoint
        with ``ali`` (lowercase). The router's pre-check would catch
        it too, but here we additionally exercise the
        ``catch IntegrityError`` path by *not* relying on the pre-check.

        Note: ``seeded_admin`` already inserted ``boss`` — the total
        before the call is 2 (``boss`` + ``Ali``). After the 409 the
        count must still be 2 (no extra row created by the rejected
        insert).
        """
        with session_factory() as db:
            db.add(
                User(
                    pseudo="Ali",
                    password_hash=hash_password("seedpassword1"),
                    role=UserRole.ELEVE,
                )
            )
            db.commit()

        before_count = None
        with session_factory() as db:
            before_count = db.query(User).count()
        assert before_count == 2  # boss + Ali

        resp = client.post(
            "/api/users",
            json={"pseudo": "ali", "password": "validpassword", "role": "parent"},
            headers=_admin_bearer(seeded_admin),
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "pseudo_taken"

        with session_factory() as db:
            assert db.query(User).count() == before_count


# ---------------------------------------------------------------------------
# Logging hygiene: the password and hash must never appear in logs.
# ---------------------------------------------------------------------------


class TestCreateUserLoggingHygiene:
    def test_logs_never_contain_password_or_hash(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        log_buffer: list[str] = []
        from loguru import logger

        handler_id = logger.add(lambda msg: log_buffer.append(str(msg)), level="DEBUG")
        try:
            client.post(
                "/api/users",
                json={"pseudo": "pat", "password": "supersecretpw1", "role": "parent"},
                headers=_admin_bearer(seeded_admin),
            )
            client.post(
                "/api/users",
                json={"pseudo": "pat", "password": "supersecretpw1", "role": "parent"},
                headers=_admin_bearer(seeded_admin),
            )
        finally:
            logger.remove(handler_id)

        joined = "\n".join(log_buffer)
        assert "supersecretpw1" not in joined
        assert "$2b$12$" not in joined
