"""Tests for ``app.core.auth.jwt`` (s13).

The contract verified here is the **only** wall between an attacker
and authenticated endpoints. We pin the following invariants:

* The access and refresh tokens are **RS256** (never ``HS256``,
  never ``none`` — Piège 1, alg-confusion attack).
* The claims ``sub``, ``role``, ``iat``, ``exp``, ``jti``, ``type``
  are all present and ``type`` discriminates ``access`` from
  ``refresh`` (Piège 3 — passing an access token to ``/refresh``
  must fail).
* A token with ``alg: none`` is **rejected** by ``decode_token``
  even though ``pyjwt`` would happily sign it.
* A revoked ``jti`` is rejected (``token_blacklist.add``).
* An expired token is rejected by ``decode_token`` (AC9 — generated
  via ``expires_delta=timedelta(seconds=-1)``, not by sleeping).

The keys are generated **once per session** (fixture
``rsa_keypair`` with ``scope="session"``) to keep the test suite
fast — generating a 2048-bit RSA keypair takes ~200ms on a modern
CPU. The keypair is also written to disk so ``Settings`` and the
runtime code can read the same files. This is the **same** keypair
the application would use in production, except in a tempdir; the
keys are wiped when the session ends.

The Settings singleton is reset between tests so each test sees
the fresh ``JWT_PRIVATE_KEY_PATH`` / ``JWT_PUBLIC_KEY_PATH`` env.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.auth import token_blacklist
from app.core.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.database.models import UserRole

# ---------------------------------------------------------------------------
# Keypair fixture — one RSA 2048 pair per pytest session.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def rsa_keypair(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Path]]:
    """Generate an RSA 2048 keypair in a session-scoped tempdir.

    Yields ``{"private": Path, "public": Path, "private_pem": str, "public_pem": str}``.
    """
    tmp = tmp_path_factory.mktemp("jwt_keys")
    private_path = tmp / "jwt_private.pem"
    public_path = tmp / "jwt_public.pem"

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    private_path.write_text(private_pem, encoding="utf-8")
    public_path.write_text(public_pem, encoding="utf-8")

    yield {
        "private": private_path,
        "public": public_path,
        "private_pem": private_pem,
        "public_pem": public_pem,
    }


@pytest.fixture(autouse=True)
def _point_settings_to_test_keys(
    rsa_keypair: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make ``Settings`` and the runtime code read the test keypair.

    The monkeypatch is autouse so the test does not need to remember
    to wire it. ``config.reset_settings()`` is called by the
    top-level ``_reset_settings`` fixture (tests/conftest.py).
    """
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateAccessToken:
    def test_create_access_token_round_trip(self) -> None:
        token = create_access_token("ali", UserRole.ELEVE)
        claims = decode_token(token, "access")
        assert claims["sub"] == "ali"
        assert claims["role"] == "eleve"

    def test_create_access_token_contains_required_claims(self) -> None:
        """AC7 — ``sub``, ``role``, ``iat``, ``exp`` are present, plus ``jti`` and ``type``."""
        token = create_access_token("ali", UserRole.PARENT)
        claims = decode_token(token, "access")
        for key in ("sub", "role", "iat", "exp", "jti", "type"):
            assert key in claims, f"missing claim {key}"
        assert claims["sub"] == "ali"
        assert claims["role"] == "parent"
        assert claims["type"] == "access"
        # ``jti`` is a UUID4 string.
        uuid.UUID(claims["jti"])  # raises if not a valid UUID

    def test_create_access_token_uses_rs256(self, rsa_keypair: dict[str, str]) -> None:
        """AC2 — token is signed with RS256 (verified by decoding the header)."""
        token = create_access_token("ali", UserRole.ELEVE)
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "RS256"
        # The signature verifies against the *public* key.
        decoded = pyjwt.decode(
            token,
            rsa_keypair["public_pem"],
            algorithms=["RS256"],
        )
        assert decoded["sub"] == "ali"


class TestCreateRefreshToken:
    def test_create_refresh_token_type_is_refresh(self) -> None:
        token = create_refresh_token("ali", UserRole.ELEVE)
        claims = decode_token(token, "refresh")
        assert claims["type"] == "refresh"
        assert claims["sub"] == "ali"
        assert claims["role"] == "eleve"


class TestTypeDiscriminator:
    def test_access_token_rejected_by_refresh_decode(self) -> None:
        """Piège 3 — passing an access token to ``/refresh`` must fail."""
        token = create_access_token("ali", UserRole.ELEVE)
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(token, "refresh")

    def test_refresh_token_rejected_by_access_decode(self) -> None:
        token = create_refresh_token("ali", UserRole.ELEVE)
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(token, "access")


class TestAlgorithmWhitelist:
    def test_alg_none_token_is_rejected(self, rsa_keypair: dict[str, str]) -> None:
        """Piège 1 — ``alg: none`` is rejected by ``decode_token``.

        ``pyjwt`` happily signs a token with ``alg: none`` when the
        caller passes ``key=""`` and ``algorithm="none"``. A naive
        ``decode`` that trusts the token's own ``alg`` header would
        accept it (the ``none`` alg is unsigned). Our ``decode_token``
        whitelists ``["RS256"]`` and must reject.
        """
        forged = pyjwt.encode(
            {"sub": "ali", "role": "eleve", "type": "access", "exp": 9_999_999_999},
            key="",
            algorithm="none",
        )
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(forged, "access")

    def test_alg_hs256_token_is_rejected(self) -> None:
        """Piège 1 (variant) — a token signed with HS256 using an
        arbitrary secret must be rejected (alg-confusion attack
        vector). We forge the token with a known secret; ``decode_token``
        must reject because HS256 is not in the algorithm whitelist,
        not because the signature is wrong (the signature is ``valid``
        for the secret — the only thing protecting us is the
        whitelist)."""
        forged = pyjwt.encode(
            {"sub": "ali", "role": "eleve", "type": "access", "exp": 9_999_999_999},
            key="some-hmac-secret",
            algorithm="HS256",
        )
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(forged, "access")

    def test_token_signed_by_other_keypair_is_rejected(
        self, rsa_keypair: dict[str, str]
    ) -> None:
        """A token signed with a *different* RSA keypair must be rejected."""
        other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other_private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        forged = pyjwt.encode(
            {
                "sub": "ali",
                "role": "eleve",
                "type": "access",
                "exp": 9_999_999_999,
                "iat": 0,
                "jti": str(uuid.uuid4()),
            },
            key=other_pem,
            algorithm="RS256",
        )
        with pytest.raises(pyjwt.InvalidTokenError):
            decode_token(forged, "access")


class TestBlacklist:
    def test_blacklisted_jti_is_rejected(self) -> None:
        token = create_access_token("ali", UserRole.ELEVE)
        claims_before = decode_token(token, "access")
        token_blacklist.add(claims_before["jti"])
        with pytest.raises(pyjwt.InvalidTokenError, match="revoked"):
            decode_token(token, "access")


class TestExpiration:
    def test_expired_access_token_is_rejected(self) -> None:
        """AC9 — an expired access token is rejected by ``decode_token``."""
        # ``expires_delta`` of -1s produces a token whose ``exp`` is
        # already in the past. No sleep required.
        token = create_access_token(
            "ali", UserRole.ELEVE, expires_delta=timedelta(seconds=-1)
        )
        with pytest.raises(pyjwt.InvalidTokenError, match="expired"):
            decode_token(token, "access")

    def test_expired_refresh_token_is_rejected(self) -> None:
        """Symmetric guarantee for the refresh path."""
        token = create_refresh_token("ali", UserRole.ELEVE)
        # The refresh helper does not accept ``expires_delta``; we
        # forge an expired refresh by re-encoding with the same key
        # and a 1-second-lifetime exp claim.
        # The cleanest way: re-use ``create_access_token`` with a
        # negative delta but ``type=refresh`` is enforced by the
        # payload, not the helper. We test the public surface:
        # ``decode_token`` rejects any token whose ``exp`` is past.
        import time

        from app.core.config import get_settings

        private_key_pem = Path(get_settings().jwt_private_key_path).read_text(
            encoding="utf-8"
        )
        now = int(time.time())
        token = pyjwt.encode(
            {
                "sub": "ali",
                "role": "eleve",
                "type": "refresh",
                "iat": now - 10,
                "exp": now - 1,
                "jti": str(uuid.uuid4()),
            },
            key=private_key_pem,
            algorithm="RS256",
        )
        with pytest.raises(pyjwt.InvalidTokenError, match="expired"):
            decode_token(token, "refresh")


class TestLifetime:
    def test_access_token_default_lifetime_is_30_minutes(self) -> None:
        token = create_access_token("ali", UserRole.ELEVE)
        claims = decode_token(token, "access")
        assert claims["exp"] - claims["iat"] == 30 * 60

    def test_access_token_respects_custom_expires_delta(self) -> None:
        token = create_access_token(
            "ali", UserRole.ELEVE, expires_delta=timedelta(minutes=5)
        )
        claims = decode_token(token, "access")
        assert claims["exp"] - claims["iat"] == 5 * 60
