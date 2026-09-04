"""In-process TTL cache for the eleve dashboard (s16).

The cache key is the JWT pseudo. Values are full
:class:`EleveDashboardResponse` objects. Entries are removed on:

* TTL expiry (default 5 min, ``set_dashboard(..., ttl_seconds=300)``),
* explicit :func:`invalidate_dashboard` (called by the exercises
  router whenever a new ``Attempt`` is created, so the next read
  re-aggregates from the source of truth — see s04 / s07 / s08).

Design choices:

* **Module-level dict + ``threading.Lock``**: uvicorn workers are
  single-threaded async, but pytest fixtures and middleware can
  re-enter the helper from another thread. The lock makes the
  set/get/invalidate trio atomic. No ``asyncio.Lock`` — the helper
  is sync.
* **``time.monotonic`` as the default clock**: immune to system
  clock adjustments (NTP, manual). The helper accepts an injectable
  ``now_fn`` so the test suite can drive the clock without
  ``sleep``.
* **No telemetry, no logging**: the cache is hot; logging every
  hit/miss would dwarf the work it caches. A miss is a normal
  control flow, not an error.
* **No size bound, no LRU**: a POC has at most one cache entry per
  active student. The story plans to migrate to Redis when the app
  scales (out of scope for s16).
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from app.api.dashboard.schemas import EleveDashboardResponse

# Key: f"dashboard:eleve:{pseudo}". Value: (expires_at_monotonic, data).
_store: dict[str, tuple[float, EleveDashboardResponse]] = {}
_lock = threading.Lock()


def _key(pseudo: str) -> str:
    return f"dashboard:eleve:{pseudo}"


def get_dashboard(
    pseudo: str,
    *,
    now_fn: Callable[[], float] = time.monotonic,
) -> EleveDashboardResponse | None:
    """Return the cached dashboard for ``pseudo`` if still valid, else ``None``.

    A miss is the expected outcome on the first call after invalidation
    or TTL expiry; the caller is expected to fall through to the
    aggregator. The function never raises on a miss.
    """
    with _lock:
        entry = _store.get(_key(pseudo))
    if entry is None:
        return None
    expires_at, data = entry
    if now_fn() > expires_at:
        # Lazy eviction: drop the stale entry so the next set does
        # not leak a tombstone. The lock is re-acquired for the
        # write; this is rare enough that the cost is negligible.
        with _lock:
            # Re-check inside the lock in case another caller already
            # removed the key.
            current = _store.get(_key(pseudo))
            if current is entry:
                _store.pop(_key(pseudo), None)
        return None
    return data


def set_dashboard(
    pseudo: str,
    data: EleveDashboardResponse,
    *,
    ttl_seconds: int = 300,
    now_fn: Callable[[], float] = time.monotonic,
) -> None:
    """Store ``data`` under the pseudo's key with a TTL of ``ttl_seconds``.

    The default 5-minute TTL matches the story's AC. A 0 or negative
    TTL is clamped to 0 — the value expires immediately, so the
    next ``get`` is a miss. This is the desired behaviour for tests
    that want to exercise the miss path without sleeping.
    """
    expires_at = now_fn() + max(ttl_seconds, 0)
    with _lock:
        _store[_key(pseudo)] = (expires_at, data)


def invalidate_dashboard(pseudo: str) -> None:
    """Drop the cached entry for ``pseudo``.

    Called by the exercises router after a new ``Attempt`` is
    inserted, so the dashboard reflects the new attempt on the next
    read rather than waiting for the TTL. Idempotent: invalidating
    a non-existent key is a no-op (no warning, no exception).
    """
    with _lock:
        _store.pop(_key(pseudo), None)


__all__ = ["get_dashboard", "invalidate_dashboard", "set_dashboard"]
