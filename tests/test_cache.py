"""TwoTierCache: memory/disk tiers, TTL expiry, persistence, key normalization."""

from __future__ import annotations

from pathlib import Path

from autoria_mcp.cache import TwoTierCache, make_cache_key


class FakeClock:
    """A controllable monotonic clock for deterministic TTL tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def test_set_then_get_hits(cache_dir: Path) -> None:
    cache = TwoTierCache(cache_dir)
    await cache.set("k", {"v": 1}, ttl=60)
    assert await cache.get("k") == {"v": 1}


async def test_missing_key_returns_none(cache_dir: Path) -> None:
    cache = TwoTierCache(cache_dir)
    assert await cache.get("absent") is None


async def test_ttl_expiry(cache_dir: Path) -> None:
    clock = FakeClock()
    cache = TwoTierCache(cache_dir, time_fn=clock)
    await cache.set("k", [1, 2, 3], ttl=100)

    clock.advance(99)
    assert await cache.get("k") == [1, 2, 3]

    clock.advance(2)  # now 101s elapsed > 100s ttl
    assert await cache.get("k") is None


async def test_persists_across_instances(cache_dir: Path) -> None:
    first = TwoTierCache(cache_dir)
    await first.set("dict", [{"name": "BMW", "value": 9}], ttl=3600)

    # A brand new instance (cold memory tier) reads the value from disk.
    second = TwoTierCache(cache_dir)
    assert await second.get("dict") == [{"name": "BMW", "value": 9}]


async def test_expired_disk_entry_is_a_miss_for_new_instance(cache_dir: Path) -> None:
    clock = FakeClock()
    first = TwoTierCache(cache_dir, time_fn=clock)
    await first.set("k", "v", ttl=10)

    clock.advance(20)
    second = TwoTierCache(cache_dir, time_fn=clock)
    assert await second.get("k") is None


async def test_corrupt_file_is_treated_as_miss(cache_dir: Path) -> None:
    cache = TwoTierCache(cache_dir)
    await cache.set("k", "v", ttl=60)
    # Corrupt the backing file and drop the warm memory copy.
    target = next(cache_dir.glob("*.json"))
    target.write_text("{not json", encoding="utf-8")

    cold = TwoTierCache(cache_dir)
    assert await cold.get("k") is None


async def test_clear_wipes_both_tiers(cache_dir: Path) -> None:
    cache = TwoTierCache(cache_dir)
    await cache.set("k", "v", ttl=60)
    await cache.clear()
    assert await cache.get("k") is None
    assert list(cache_dir.glob("*.json")) == []


def test_cache_key_excludes_secrets_and_is_order_invariant() -> None:
    a = make_cache_key("/auto/search", {"marka_id": 9, "api_key": "secret", "user_id": "777"})
    b = make_cache_key("/auto/search", {"marka_id": 9})
    assert a == b
    assert "secret" not in a
    assert "777" not in a

    # Param order does not change the key.
    k1 = make_cache_key("/p", {"b": 2, "a": 1})
    k2 = make_cache_key("/p", {"a": 1, "b": 2})
    assert k1 == k2


def test_cache_key_without_params_is_just_path() -> None:
    assert make_cache_key("/auto/colors") == "/auto/colors"
