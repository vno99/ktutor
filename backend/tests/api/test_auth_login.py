"""Tests for the login / refresh / logout endpoints (s13).

The endpoints are wired into the **real** ``app.main:app`` — same
``TestClient`` pattern as ``test_auth_register.py``. The in-memory
SQLite is the source of truth for the ``users`` table; the RSA
keypair is generated once per session and pointed to via
``Settings.jwt_*_key_path``.

The tests cover:

* **AC1 + AC7 + AC8** — happy path login returns a
  :class:`TokenPairResponse` with a decodable JWT that carries
  ``sub``, ``role``, ``iat``, ``exp``, ``jti``, ``type='access'``.
* **AC2** — the token verifies against the public key with
  ``alg=RS256``; a token signed with a *different* RSA key is
  rejected (signature check).
* **AC3** — ``expires_in`` is 30 minutes worth of seconds.
* **AC4** — the refresh token's ``exp - iat`` is 7 days worth of
  seconds.
* **AC5** — ``/refresh`` returns a new pair and blacklists the
  old ``jti``; a second call with the old refresh fails.
* **AC6** — wrong password returns 401 ``invalid_credentials``
  with a generic message that does not leak whether the pseudo
  exists.
* **AC6 bis** — timing attack mitigation: ``/login`` is
  timing-constant for "unknown pseudo" vs "wrong password"
  (skip-able on slow CI).
* **AC9** — an expired access token is rejected by
  ``/api/auth/logout`` (which requires ``get_current_user``).
* **Logout** — a logged-out token is rejected on subsequent
  protected calls (blacklist check).
* **Logging hygiene** — no password, no hash, no token, no
  ``jti`` ever appears in the log buffer.
* **Register → login** — the user created by ``/register`` can
  log in immediately (s12 + s13 share the ``users`` table).
"""

from __future__ import annotations

import os
import re
import time
import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from loguru import logger
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth.jwt import create_access_token
from app.core.auth.passwords import hash_password
from app.core.config import get_settings
from app.core.database.models import Base, User, UserRole
from app.core.database.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# Keypair fixture — one pair per session, pointed via env.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_login")
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
    return {"private": private_path, "public": public_path, "private_pem": private_path.read_text(encoding="utf-8")}


@pytest.fixture(autouse=True)
def _point_settings(monkeypatch: pytest.MonkeyPatch, rsa_keypair: dict[str, Path]) -> None:
    monkeypatch.setenv("JWT_PRIVATE_KEY_PATH", str(rsa_keypair["private"]))
    monkeypatch.setenv("JWT_PUBLIC_KEY_PATH", str(rsa_keypair["public"]))
    monkeypatch.setenv("JWT_ALGORITHM", "RS256")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7")


# ---------------------------------------------------------------------------
# DB fixture — in-memory SQLite + StaticPool, same pattern as
# ``test_auth_register.py:32-70``.
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


@pytest.fixture()
def seeded_user(session_factory) -> User:
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


# ---------------------------------------------------------------------------
# Happy path — AC1 + AC7 + AC8
# ---------------------------------------------------------------------------


class TestLoginHappyPath:
    def test_login_returns_token_pair(self, client: TestClient, seeded_user: User) -> None:
        resp = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": "correcthorse"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert set(body.keys()) == {"access_token", "refresh_token", "token_type", "expires_in"}
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 30 * 60

    def test_login_token_is_decodable_with_expected_claims(
        self, client: TestClient, rsa_keypair: dict[str, str], seeded_user: User
    ) -> None:
        """AC7 + AC8 — the access token decodes to ``sub=ali`` and
        carries ``iat``/``exp``/``jti``/``type=access``."""
        resp = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": "correcthorse"}
        )
        body = resp.json()
        decoded = pyjwt.decode(
            body["access_token"],
            rsa_keypair["private"]  # private is also valid for verify in this test
            if False
            else rsa_keypair["public"].read_text(encoding="utf-8"),
            algorithms=["RS256"],
        )
        assert decoded["sub"] == "ali"
        assert decoded["role"] == "eleve"
        for key in ("iat", "exp", "jti", "type"):
            assert key in decoded
        assert decoded["type"] == "access"
        # ``jti`` is a valid UUID.
        uuid.UUID(decoded["jti"])

    def test_login_token_signed_with_correct_rsa_key(
        self, client: TestClient, rsa_keypair: dict[str, str], seeded_user: User
    ) -> None:
        """AC2 — the signature verifies with the public key."""
        resp = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": "correcthorse"}
        )
        body = resp.json()
        # Public-key verification of the signature.
        pyjwt.decode(
            body["access_token"],
            rsa_keypair["public"].read_text(encoding="utf-8"),
            algorithms=["RS256"],
        )
        # And a token forged with a *different* RSA key is rejected
        # (this is a sub-aspect of AC2: the signature is RSA, not
        # a placeholder).
        forged = pyjwt.encode(
            {
                "sub": "ali",
                "role": "eleve",
                "type": "access",
                "exp": 9_999_999_999,
                "iat": 0,
                "jti": str(uuid.uuid4()),
            },
            key=rsa.generate_private_key(public_exponent=65537, key_size=2048)
            .private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
            algorithm="RS256",
        )
        with pytest.raises(pyjwt.InvalidTokenError):
            pyjwt.decode(
                forged,
                rsa_keypair["public"].read_text(encoding="utf-8"),
                algorithms=["RS256"],
            )


# ---------------------------------------------------------------------------
# AC3 / AC4 — lifetime invariants
# ---------------------------------------------------------------------------


class TestTokenLifetimes:
    def test_access_token_expires_in_30_minutes(
        self, client: TestClient, seeded_user: User
    ) -> None:
        resp = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": "correcthorse"}
        )
        access = resp.json()["access_token"]
        with open(get_settings().jwt_public_key_path) as _f:
            public_pem = _f.read()
        claims = pyjwt.decode(access, public_pem, algorithms=["RS256"])
        assert claims["exp"] - claims["iat"] == 30 * 60

    def test_refresh_token_expires_in_7_days(
        self, client: TestClient, seeded_user: User
    ) -> None:
        resp = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": "correcthorse"}
        )
        refresh = resp.json()["refresh_token"]
        with open(get_settings().jwt_public_key_path) as _f:
            public_pem = _f.read()
        claims = pyjwt.decode(refresh, public_pem, algorithms=["RS256"])
        assert claims["exp"] - claims["iat"] == 7 * 86400


# ---------------------------------------------------------------------------
# AC5 — refresh rotation + blacklist
# ---------------------------------------------------------------------------


class TestRefresh:
    def test_refresh_returns_new_pair(self, client: TestClient, seeded_user: User) -> None:
        login = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": "correcthorse"}
        )
        old_refresh = login.json()["refresh_token"]

        resp = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["access_token"] != login.json()["access_token"]
        assert body["refresh_token"] != old_refresh

    def test_old_refresh_is_blacklisted_after_rotation(
        self, client: TestClient, seeded_user: User
    ) -> None:
        login = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": "correcthorse"}
        )
        old_refresh = login.json()["refresh_token"]

        # First refresh succeeds.
        first = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
        assert first.status_code == 200

        # Second refresh with the same old token is rejected.
        second = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
        assert second.status_code == 401
        assert second.json()["detail"]["code"] == "invalid_token"

    def test_refresh_with_access_token_fails(
        self, client: TestClient, seeded_user: User
    ) -> None:
        """Piège 3 — passing an access token to ``/refresh`` is rejected."""
        login = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": "correcthorse"}
        )
        access = login.json()["access_token"]
        resp = client.post("/api/auth/refresh", json={"refresh_token": access})
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"

    def test_refresh_with_junk_token_fails(
        self, client: TestClient, seeded_user: User
    ) -> None:
        resp = client.post(
            "/api/auth/refresh", json={"refresh_token": "not-a-jwt"}
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"


# ---------------------------------------------------------------------------
# AC6 — wrong password / unknown pseudo
# ---------------------------------------------------------------------------


class TestWrongCredentials:
    def test_wrong_password_returns_401_generic(
        self, client: TestClient, seeded_user: User
    ) -> None:
        resp = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": "wrong"}
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"]["code"] == "invalid_credentials"
        # Generic message — does not leak that the pseudo exists.
        lower = body["detail"]["error"].lower()
        assert "introuvable" not in lower
        assert "existe" not in lower
        assert "inconnu" not in lower

    def test_unknown_pseudo_returns_401_generic(
        self, client: TestClient, seeded_user: User
    ) -> None:
        resp = client.post(
            "/api/auth/login", json={"pseudo": "ghost", "password": "anything"}
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_credentials"

    def test_login_timing_is_constant_unknown_vs_wrong_password(
        self, client: TestClient, seeded_user: User
    ) -> None:
        """AC6 bis — login latency for "unknown pseudo" must be close
        to "wrong password" (Piège 2). The check is intentionally
        lenient (P95 < 200ms gap) and is skipped in fast-CI mode
        via ``KTUTOR_SKIP_TIMING=1`` (timing tests are notoriously
        flaky on shared CI runners)."""
        if os.environ.get("KTUTOR_SKIP_TIMING") == "1":
            pytest.skip("KTUTOR_SKIP_TIMING=1 — timing test skipped")

        # Warmup — bcrypt cost 12 takes ~250ms; first call may be slower.
        for _ in range(3):
            client.post(
                "/api/auth/login", json={"pseudo": "ghost", "password": "warmup"}
            )
            client.post(
                "/api/auth/login", json={"pseudo": "ali", "password": "warmup"}
            )

        unknown_times: list[float] = []
        wrong_times: list[float] = []
        n = 25
        for i in range(n):
            t0 = time.perf_counter()
            client.post(
                "/api/auth/login", json={"pseudo": "ghost", "password": "x" * 12}
            )
            unknown_times.append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            client.post(
                "/api/auth/login", json={"pseudo": "ali", "password": "wrong"}
            )
            wrong_times.append(time.perf_counter() - t0)

        def median(xs: list[float]) -> float:
            xs_sorted = sorted(xs)
            return xs_sorted[len(xs_sorted) // 2]

        med_unknown = median(unknown_times)
        med_wrong = median(wrong_times)
        # The medians must be close — allow up to 200ms gap for CI noise.
        assert abs(med_unknown - med_wrong) < 0.200, (
            f"timing leak: unknown_pseudo={med_unknown*1000:.1f}ms, "
            f"wrong_pw={med_wrong*1000:.1f}ms"
        )


# ---------------------------------------------------------------------------
# AC9 + logout
# ---------------------------------------------------------------------------


class TestExpiredAndLogout:
    def test_expired_access_token_rejected_by_protected_endpoint(
        self, client: TestClient, seeded_user: User
    ) -> None:
        """AC9 — an expired access token is rejected by the
        middleware (``/api/auth/logout`` is the canonical
        protected endpoint in s13)."""
        expired = create_access_token(
            seeded_user.pseudo,
            seeded_user.role,
            expires_delta=timedelta(seconds=-1),
        )
        resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {expired}"})
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "invalid_token"

    def test_logout_returns_204_and_blacklists_token(
        self, client: TestClient, seeded_user: User
    ) -> None:
        login = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": "correcthorse"}
        )
        access = login.json()["access_token"]

        resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {access}"})
        assert resp.status_code == 204

        # The same token cannot be used again on a protected endpoint.
        reuse = client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {access}"}
        )
        assert reuse.status_code == 401
        assert reuse.json()["detail"]["code"] == "invalid_token"

    def test_logout_without_token_returns_401(
        self, client: TestClient, seeded_user: User
    ) -> None:
        resp = client.post("/api/auth/logout")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Logging hygiene — Trap 16
# ---------------------------------------------------------------------------


class TestLoggingHygiene:
    def test_login_refresh_logout_logs_never_carry_token_material(
        self, client: TestClient, seeded_user: User
    ) -> None:
        buffer: list[str] = []
        handler_id = logger.add(lambda msg: buffer.append(str(msg)), level="DEBUG")
        try:
            login = client.post(
                "/api/auth/login", json={"pseudo": "ali", "password": "correcthorse"}
            )
            access = login.json()["access_token"]
            refresh = login.json()["refresh_token"]
            client.post("/api/auth/refresh", json={"refresh_token": refresh})
            client.post("/api/auth/logout", headers={"Authorization": f"Bearer {access}"})
        finally:
            logger.remove(handler_id)

        joined = "\n".join(buffer)
        # No JWT (starts with "eyJ") in any log line.
        assert "eyJ" not in joined, f"JWT leaked in logs: {joined[:500]}"
        # No jti UUIDs.
        # Match the 36-char UUID hex pattern.
        uuid_re = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
        assert not uuid_re.search(joined), f"jti leaked in logs: {joined[:500]}"
        # No password.
        assert "correcthorse" not in joined
        # No bcrypt hash signature.
        assert "$2b$12$" not in joined


# ---------------------------------------------------------------------------
# Register → login (s12 + s13 share the users table)
# ---------------------------------------------------------------------------


class TestRegisterThenLogin:
    def test_register_then_login_succeeds(self, client: TestClient) -> None:
        register = client.post(
            "/api/auth/register",
            json={"pseudo": "newcomer", "password": "validpassword1"},
        )
        assert register.status_code == 201, register.text

        login = client.post(
            "/api/auth/login",
            json={"pseudo": "newcomer", "password": "validpassword1"},
        )
        assert login.status_code == 200, login.text
        body = login.json()
        assert body["token_type"] == "bearer"
        # The token decodes to the same pseudo.
        with open(get_settings().jwt_public_key_path) as _f:
            public_pem = _f.read()
        claims = pyjwt.decode(body["access_token"], public_pem, algorithms=["RS256"])
        assert claims["sub"] == "newcomer"


# ---------------------------------------------------------------------------
# Validation — Pydantic-level guard rails
# ---------------------------------------------------------------------------


class TestLoginValidation:
    def test_login_invalid_pseudo_too_short_returns_422(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/api/auth/login", json={"pseudo": "ab", "password": "anything"}
        )
        assert resp.status_code == 422

    def test_login_invalid_pseudo_special_chars_returns_422(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/api/auth/login", json={"pseudo": "ali-baba", "password": "anything"}
        )
        assert resp.status_code == 422

    def test_login_empty_password_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/api/auth/login", json={"pseudo": "ali", "password": ""}
        )
        assert resp.status_code == 422
