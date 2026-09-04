"""Tests for ``app.services.dashboard.cache`` (s16).

The cache is an in-process TTL dict guarded by a lock. The four
behaviours that matter:

* ``set`` then ``get`` (within TTL) returns the stored value.
* ``get`` after TTL expiry returns ``None`` (the caller is expected
  to re-aggregate). Crucially: NOT raise.
* ``invalidate`` removes the entry so a subsequent ``get`` returns
  ``None``.
* Two different pseudos have independent keys (no global state
  leak).

The clock is injectable via ``now_fn`` so the tests do not depend
on ``time.monotonic``; they assert behaviour, not "the wall clock
moved 301 seconds".
"""
from __future__ import annotations

import pytest

from app.api.dashboard.schemas import EleveDashboardResponse, GlobalSummary
from app.services.dashboard.cache import (
    get_dashboard,
    invalidate_dashboard,
    set_dashboard,
)


def _make_response(pseudo: str) -> EleveDashboardResponse:
    return EleveDashboardResponse(
        subjects=[],
        **{"global": GlobalSummary(score_avg=0.0, exercises_count=0, last_activity_at=None)},
    )


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    # Each test starts with a fresh in-process state. The module
    # keeps a module-level dict; the helper ``invalidate_dashboard``
    # is the public way to clear an entry. The autouse fixture clears
    # both alice and bob so cross-test state never bleeds.
    invalidate_dashboard("alice")
    invalidate_dashboard("bob")


def test_set_then_get_returns_data() -> None:
    data = _make_response("alice")
    set_dashboard("alice", data, ttl_seconds=300, now_fn=lambda: 1000.0)
    result = get_dashboard("alice", now_fn=lambda: 1010.0)
    assert result is data


def test_expired_entry_returns_none() -> None:
    data = _make_response("alice")
    set_dashboard("alice", data, ttl_seconds=300, now_fn=lambda: 1000.0)
    result = get_dashboard("alice", now_fn=lambda: 1301.0)
    assert result is None


def test_invalidate_removes_entry() -> None:
    data = _make_response("alice")
    set_dashboard("alice", data, ttl_seconds=300, now_fn=lambda: 1000.0)
    invalidate_dashboard("alice")
    result = get_dashboard("alice", now_fn=lambda: 1010.0)
    assert result is None


def test_different_pseudos_have_separate_keys() -> None:
    alice = _make_response("alice")
    bob = _make_response("bob")
    set_dashboard("alice", alice, ttl_seconds=300, now_fn=lambda: 1000.0)
    set_dashboard("bob", bob, ttl_seconds=300, now_fn=lambda: 1000.0)
    assert get_dashboard("alice", now_fn=lambda: 1010.0) is alice
    assert get_dashboard("bob", now_fn=lambda: 1010.0) is bob


def test_get_returns_none_for_missing_key() -> None:
    # No set, just a get. The cache must NOT raise; it returns None
    # so the caller can fall through to the aggregator.
    assert get_dashboard("nobody", now_fn=lambda: 1000.0) is None
