"""Tests for the JWT auth middleware (s13).

Two FastAPI dependencies are tested:

* :func:`get_current_user` — extracts the bearer token, calls
  :func:`app.core.auth.jwt.decode_token`, fetches the
  corresponding :class:`User`, and returns it. On any failure
  (missing header, junk token, expired, revoked) the dependency
  raises ``HTTPException(401, ...)`` with a generic
  ``invalid_token`` body — the response never leaks *why* the
  token is invalid (Piège 2 bis).
* :func:`require_role` — wraps ``get_current_user`` with a role
  whitelist. A user whose ``role`` is not in the allowed set is
  rejected with ``403 forbidden``.

The tests use the same in-memory SQLite + StaticPool pattern as
``test_auth_register.py`` (D7 s12) and a session-scoped RSA keypair
to keep the suite fast.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import token_blacklist
from app.core.auth.jwt import create_access_token, decode_token
from app.core.auth.middleware import get_current_user, require_role
from app.core.auth.passwords import hash_password
from app.core.database.models import Base, User, UserRole
from app.core.database.session import get_db

# ---------------------------------------------------------------------------
# Fixtures — keypair + DB
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_middleware")
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
def _point_settings(monkeypatch: pytest.MonkeyPatch, rsa_keypair: dict[str, Path]) -> None:
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(rsa_keypair["private"]))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(rsa_keypair["public"]))
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")


@pytest.fixture(autouse=True)
def _clean_blacklist() -> Iterator[None]:
    token_blacklist.clear()
    yield
    token_blacklist.clear()


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
def seeded_user(session_factory) -> User:
    """Insert a default ``eleve`` user and return it."""
    with session_factory() as db:
        user = User(
            pseudo="ali",
            password_hash=hash_password("correcthorse"),
            role=UserRole.ELEVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def seeded_admin(session_factory) -> User:
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


# ---------------------------------------------------------------------------
# Per-test app
# ---------------------------------------------------------------------------


def _build_app() -> FastAPI:
    """Build a tiny FastAPI app exercising the middleware in isolation.

    The app has a single protected endpoint per scenario. The
    ``get_db`` dependency is overridden by the ``client`` fixture
    so each test sees the same in-memory SQLite.
    """
    test_app = FastAPI()

    @test_app.get("/me")
    def me(user: User = Depends(get_current_user)) -> dict:
        return {"pseudo": user.pseudo, "role": user.role.value}

    @test_app.get("/admin-only")
    def admin_only(user: User = Depends(require_role(UserRole.ADMIN))) -> dict:
        return {"pseudo": user.pseudo, "role": user.role.value}

    @test_app.get("/eleves-only")
    def eleves_only(user: User = Depends(require_role(UserRole.ELEVE))) -> dict:
        return {"pseudo": user.pseudo, "role": user.role.value}

    return test_app


@pytest.fixture()
def client(session_factory) -> Iterator[TestClient]:
    def _override_get_db() -> Iterator[Session]:
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app = _build_app()
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests — get_current_user
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    def test_valid_token_returns_user(self, client: TestClient, seeded_user: User) -> None:
        token = create_access_token(seeded_user.pseudo, seeded_user.role)
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == {"pseudo": "ali", "role": "eleve"}

    def test_missing_authorization_header_returns_401(
        self, client: TestClient, seeded_user: User
    ) -> None:
        resp = client.get("/me")
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"

    def test_junk_token_returns_401(self, client: TestClient, seeded_user: User) -> None:
        resp = client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"

    def test_expired_token_returns_401(self, client: TestClient, seeded_user: User) -> None:
        """AC9 — expired token rejected by the middleware."""
        token = create_access_token(
            seeded_user.pseudo, seeded_user.role, expires_delta=timedelta(seconds=-1)
        )
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"

    def test_revoked_jti_returns_401(self, client: TestClient, seeded_user: User) -> None:
        """A logged-out token is rejected by the middleware."""
        token = create_access_token(seeded_user.pseudo, seeded_user.role)
        # Read the jti, then blacklist it. The next request must
        # fail with 401.
        claims = decode_token(token, "access")
        token_blacklist.add(claims["jti"])
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"

    def test_token_for_missing_user_returns_401(self, client: TestClient) -> None:
        """A token whose ``sub`` points to a deleted user is rejected.

        The middleware is **generic** on this — the 401 is the
        same as for an invalid token. We don't leak that the user
        was deleted (Piège 2 bis).
        """
        token = create_access_token("ghost", UserRole.ELEVE)
        resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# Tests — require_role
# ---------------------------------------------------------------------------


class TestRequireRole:
    def test_admin_can_hit_admin_endpoint(
        self, client: TestClient, seeded_admin: User
    ) -> None:
        token = create_access_token(seeded_admin.pseudo, seeded_admin.role)
        resp = client.get(
            "/admin-only", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    def test_eleve_blocked_from_admin_endpoint(
        self, client: TestClient, seeded_user: User
    ) -> None:
        token = create_access_token(seeded_user.pseudo, seeded_user.role)
        resp = client.get(
            "/admin-only", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "forbidden"

    def test_eleve_can_hit_eleve_endpoint(
        self, client: TestClient, seeded_user: User
    ) -> None:
        token = create_access_token(seeded_user.pseudo, seeded_user.role)
        resp = client.get(
            "/eleves-only", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200

    def test_invalid_token_does_not_reach_role_check(
        self, client: TestClient, seeded_user: User
    ) -> None:
        """An invalid token must fail at ``get_current_user`` (401), not
        leak through to the role check (which would be 403)."""
        resp = client.get(
            "/admin-only", headers={"Authorization": "Bearer garbage"}
        )
        assert resp.status_code == 401
