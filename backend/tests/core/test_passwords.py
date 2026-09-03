"""Tests for the bcrypt password wrapper (s12).

The wrapper exposes :func:`hash_password` and :func:`verify_password`.
Bcrypt has a hard 72-octet limit on the input, so the wrapper is
defensive (it rejects empty and oversized inputs with ``ValueError``)
and counts *bytes*, not characters — a French password like ``"é" * 37``
is 74 octets UTF-8 even though it is 37 characters.
"""

from __future__ import annotations

import pytest

from app.core.auth.passwords import hash_password, verify_password


class TestHashPassword:
    def test_hash_password_returns_bcrypt_string(self) -> None:
        hashed = hash_password("correct horse battery staple")
        assert hashed.startswith("$2b$12$")

    def test_hash_password_is_deterministic_in_length_only(self) -> None:
        """Two hashs of the same password are different (random salt) but equal length."""
        a = hash_password("correct horse battery staple")
        b = hash_password("correct horse battery staple")
        assert a != b  # different salts
        assert len(a) == len(b)  # same scheme → same length

    def test_hash_password_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            hash_password("")

    def test_hash_password_rejects_too_long(self) -> None:
        # 73 ASCII bytes > the 72-byte bcrypt limit.
        with pytest.raises(ValueError):
            hash_password("a" * 73)

    def test_hash_password_accepts_exactly_72_bytes(self) -> None:
        # Boundary: 72 ASCII bytes is exactly the limit and must succeed.
        hashed = hash_password("a" * 72)
        assert hashed.startswith("$2b$12$")

    def test_hash_password_counts_bytes_not_chars(self) -> None:
        # "é" is 2 bytes in UTF-8. 25 chars → 50 bytes (allowed).
        assert hash_password("é" * 25).startswith("$2b$12$")
        # 37 chars → 74 bytes (rejected).
        with pytest.raises(ValueError):
            hash_password("é" * 37)


class TestVerifyPassword:
    def test_verify_password_accepts_correct(self) -> None:
        plain = "correct horse battery staple"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_password_rejects_wrong(self) -> None:
        hashed = hash_password("right")
        assert verify_password("wrong", hashed) is False

    def test_verify_password_rejects_malformed_hash(self) -> None:
        # Malformed hash must NOT raise — return False (no info leak).
        assert verify_password("anything", "not-a-bcrypt-hash") is False
