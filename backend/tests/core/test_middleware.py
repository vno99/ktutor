"""Tests for :func:`app.core.auth.middleware.assert_jwt_pseudo_matches_or_403`.

The helper is the HTTP-level cross-tenant guard introduced in s15
(ADR 005, plan s15-restrictions-rbac). It complements
:func:`get_current_user` — the dependency decodes the JWT and
returns a :class:`User`; the helper compares that user's
``pseudo`` to any ``pseudo`` the caller may have supplied in the
body / URL / query, rejecting the request with 403 on mismatch
(unless the caller is an admin).

Behaviour matrix proven here (the rule lives here, the callers
just invoke it):

* ``claimed=None`` is a no-op — the endpoint did not receive a
  ``pseudo`` from the body, so nothing to compare.
* ``claimed == user.pseudo`` (case-insensitive) is a no-op.
* ``claimed != user.pseudo`` raises 403 ``forbidden`` for an
  eleve / parent.
* ``claimed != user.pseudo`` is a no-op for an admin (ADR 005
  admin bypass).
* The log line emitted on a block never contains token material
  (no ``Bearer``, no ``jti``, no password, no body payload).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.orm import sessionmaker

from app.core.auth.middleware import assert_jwt_pseudo_matches_or_403
from app.core.auth.passwords import hash_password
from app.core.database.models import Base, User, UserRole

# ---------------------------------------------------------------------------
# RSA keypair — same pattern as test_auth_middleware / test_users_create.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    tmp = tmp_path_factory.mktemp("jwt_keys_middleware_helper")
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


@pytest.fixture()
def seeded_eleve_alice(session_factory) -> User:
    with session_factory() as db:
        user = User(
            pseudo="alice",
            password_hash=hash_password("studentpassword"),
            role=UserRole.ELEVE,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture()
def isolated_log_buffer() -> Iterator[list[str]]:
    """Drop the production loguru sink and yield a per-test buffer.

    Re-uses the same trick as ``conftest.py::_isolated_loguru_sink``
    but local to this file so we can read it after the helper
    returns.
    """
    from loguru import logger

    buffer: list[str] = []
    handler_id = logger.add(lambda message: buffer.append(str(message)), level="DEBUG")
    try:
        yield buffer
    finally:
        logger.remove(handler_id)


# ---------------------------------------------------------------------------
# The rule, pinned at itself.
# ---------------------------------------------------------------------------


class TestAssertJwtPseudoMatches:
    def test_claimed_none_is_noop(
        self, seeded_eleve_alice: User, isolated_log_buffer: list[str]
    ) -> None:
        """No `pseudo` in the body → nothing to compare, no raise."""
        assert_jwt_pseudo_matches_or_403(
            seeded_eleve_alice, None, route="/api/chat/stream"
        )
        # No INFO cross-tenant log on the no-op path.
        joined = "\n".join(isolated_log_buffer)
        assert "security.cross_tenant_attempt" not in joined

    def test_claimed_matches_user_pseudo_is_noop(
        self, seeded_eleve_alice: User, isolated_log_buffer: list[str]
    ) -> None:
        assert_jwt_pseudo_matches_or_403(
            seeded_eleve_alice, "alice", route="/api/chat/stream"
        )
        joined = "\n".join(isolated_log_buffer)
        assert "security.cross_tenant_attempt" not in joined

    def test_claimed_matches_user_pseudo_case_insensitive(
        self, seeded_eleve_alice: User
    ) -> None:
        """The functional index `uq_users_pseudo_lower` is the source of
        truth for case-insensitive pseudo equality (s12). The guard
        must align with it, otherwise `Alice` would slip past the
        pre-check on the unique index."""
        assert_jwt_pseudo_matches_or_403(
            seeded_eleve_alice, "ALICE", route="/api/chat/stream"
        )
        assert_jwt_pseudo_matches_or_403(
            seeded_eleve_alice, "Alice", route="/api/documents/upload"
        )

    def test_claimed_mismatch_raises_403_for_eleve(
        self, seeded_eleve_alice: User, isolated_log_buffer: list[str]
    ) -> None:
        """An eleve sending a body pseudo that does not match the JWT
        pseudo is rejected with 403 `forbidden`, and the cross-tenant
        log line carries the four required fields."""
        with pytest.raises(HTTPException) as exc_info:
            assert_jwt_pseudo_matches_or_403(
                seeded_eleve_alice, "bob", route="/api/chat/stream"
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == {"error": "Accès refusé.", "code": "forbidden"}

        joined = "\n".join(isolated_log_buffer)
        assert "security.cross_tenant_attempt" in joined
        # The log line carries caller, claimed, role, route.
        assert "caller=alice" in joined
        assert "claimed=bob" in joined
        assert "role=eleve" in joined
        assert "route=/api/chat/stream" in joined

    def test_claimed_mismatch_is_noop_for_admin(
        self, seeded_admin: User, isolated_log_buffer: list[str]
    ) -> None:
        """ADR 005 admin bypass: the guard is a no-op when the caller
        is an admin. The DEBUG line `auth.middleware.admin_bypass`
        is emitted so an operator can correlate the action."""
        assert_jwt_pseudo_matches_or_403(
            seeded_admin, "alice", route="/api/chat/stream"
        )
        joined = "\n".join(isolated_log_buffer)
        assert "auth.middleware.admin_bypass" in joined
        # The cross-tenant INFO line is NOT emitted for the admin bypass.
        assert "security.cross_tenant_attempt" not in joined

    def test_log_does_not_contain_token_material(
        self, seeded_eleve_alice: User, isolated_log_buffer: list[str]
    ) -> None:
        """The cross-tenant log line MUST NOT contain the JWT, the
        bearer scheme, the jti, the password, or the raw body
        (AGENTS.md § Backend logging). A regression that introduced
        a ``request.headers`` dump or echoed the body payload
        would fail this test."""
        with pytest.raises(HTTPException):
            assert_jwt_pseudo_matches_or_403(
                seeded_eleve_alice, "bob", route="/api/chat/stream"
            )
        joined = "\n".join(isolated_log_buffer)
        forbidden_substrings = [
            "Bearer ",
            "bearer ",
            "eyJ",  # JWT header / payload always starts with `eyJ`
            "jti=",
            "jti:",
            "password",
            "Password",
            "$2b$",
            "Authorization:",
            "request_body",
            '"body":',
        ]
        for needle in forbidden_substrings:
            assert needle not in joined, (
                f"Cross-tenant log line leaked sensitive material: "
                f"found {needle!r} in:\n{joined}"
            )
