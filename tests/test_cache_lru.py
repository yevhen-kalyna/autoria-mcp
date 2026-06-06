"""Bounded-LRU memory tier (TwoTierCache) and the memory-only MemoryCache."""

from __future__ import annotations

from pathlib import Path

from autoria_mcp.cache import MemoryCache, TwoTierCache


class FakeClock:
    """A controllable clock for deterministic TTL tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def test_two_tier_memory_tier_evicts_lru(cache_dir: Path) -> None:
    cache = TwoTierCache(cache_dir, max_memory_entries=2)
    await cache.set("a", 1, ttl=3600)
    await cache.set("b", 2, ttl=3600)
    # Touch "a" so "b" becomes the least-recently-used entry.
    assert await cache.get("a") == 1
    await cache.set("c", 3, ttl=3600)  # exceeds cap -> evict LRU ("b")

    # "b" fell out of memory but is still on disk (disk tier is unbounded).
    assert await cache.get("b") == 2
    # The disk rehydrate of "b" now evicts the new LRU; "a"/"c" remain reachable.
    assert await cache.get("a") == 1
    assert await cache.get("c") == 3


async def test_memory_cache_set_get(cache_dir: Path) -> None:
    cache = MemoryCache(max_entries=8)
    await cache.set("k", {"v": 1}, ttl=60)
    assert await cache.get("k") == {"v": 1}
    assert await cache.get("absent") is None


async def test_memory_cache_ttl_expiry() -> None:
    clock = FakeClock()
    cache = MemoryCache(max_entries=8, time_fn=clock)
    await cache.set("k", [1, 2], ttl=100)

    clock.advance(99)
    assert await cache.get("k") == [1, 2]

    clock.advance(2)  # 101s > 100s ttl
    assert await cache.get("k") is None


async def test_memory_cache_evicts_lru() -> None:
    cache = MemoryCache(max_entries=2)
    await cache.set("a", 1, ttl=60)
    await cache.set("b", 2, ttl=60)
    assert await cache.get("a") == 1  # "b" is now LRU
    await cache.set("c", 3, ttl=60)  # evicts "b"

    assert await cache.get("b") is None
    assert await cache.get("a") == 1
    assert await cache.get("c") == 3


async def test_memory_cache_writes_no_disk(cache_dir: Path) -> None:
    cache = MemoryCache(max_entries=8)
    await cache.set("k", "v", ttl=60)
    # The volatile cache must never persist to disk.
    assert list(cache_dir.iterdir()) == []
