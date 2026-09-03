"""Tests for the in-process JWT blacklist (s13).

The blacklist is the single point of truth for ``jti`` revocation
between the moment a token is added (``POST /api/auth/logout`` or
``POST /api/auth/refresh``) and the moment it is checked
(``decode_token``). The contract:

* :func:`add` is **idempotent** : adding the same ``jti`` twice is
  a no-op (we don't want a flaky test or a duplicate revoke to
  blow up the route).
* :func:`is_revoked` is monotonic : once a ``jti`` is in the set,
  it stays until :func:`clear` is called.
* :func:`clear` is **test-only** : it is exposed because the
  pytest fixture needs a clean slate between tests (the blacklist
  is a module-level mutable state).

The blacklist is in-memory. It is not safe for multi-process
deployments; this is documented as s15+ debt (ADR 005).
"""

from __future__ import annotations

import pytest

from app.core.auth.token_blacklist import add, clear, is_revoked


@pytest.fixture(autouse=True)
def _reset_blacklist() -> None:
    """Each test gets a fresh blacklist. Order-independence is required
    because the blacklist is a module-level ``set``."""
    clear()
    yield
    clear()


class TestAdd:
    def test_add_marks_jti_revoked(self) -> None:
        add("jti-abc")
        assert is_revoked("jti-abc") is True

    def test_add_is_idempotent(self) -> None:
        """``add`` called twice with the same ``jti`` must not raise."""
        add("jti-dup")
        add("jti-dup")
        assert is_revoked("jti-dup") is True


class TestIsRevoked:
    def test_unknown_jti_is_not_revoked(self) -> None:
        assert is_revoked("jti-never-seen") is False

    def test_other_jti_remains_unrevoked(self) -> None:
        add("jti-1")
        assert is_revoked("jti-2") is False


class TestClear:
    def test_clear_removes_everything(self) -> None:
        add("jti-1")
        add("jti-2")
        clear()
        assert is_revoked("jti-1") is False
        assert is_revoked("jti-2") is False
