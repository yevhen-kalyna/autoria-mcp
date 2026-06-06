"""TTL cache abstraction for slow-changing dictionary data.

Phase 2 defines the interface only. Phase 3 implements a two-tier cache
(in-memory LRU in front of a JSON-on-disk store under ``Settings.cache_dir``),
keyed by endpoint + normalized params, with per-entry TTL.

The cache directory must stay out of git (see ``.gitignore``).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Cache(Protocol):
    """Minimal async cache contract used by the client and dictionary resolver."""

    async def get(self, key: str) -> object | None:
        """Return the cached value for ``key`` or ``None`` if absent/expired."""
        ...

    async def set(self, key: str, value: object, ttl: int) -> None:
        """Store ``value`` under ``key`` for ``ttl`` seconds."""
        ...

    async def clear(self) -> None:
        """Drop every entry (both tiers)."""
        ...


# TODO(phase 3): implement TwoTierCache(Cache) — in-memory dict + on-disk JSON,
# atomic writes, mtime-based expiry, and a stable cache-key builder
# (endpoint + sorted query params, excluding api_key/user_id).
