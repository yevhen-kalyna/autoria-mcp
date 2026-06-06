"""Shared test fixtures.

Every test in this suite runs with **zero network**: HTTP is intercepted by
respx, which raises on any un-mocked request. Fixtures are replayed from
``tests/fixtures/*.json`` (sanitized dictionary/error bodies derived from the
OpenAPI spec), so the suite burns no API quota.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from autoria_mcp.cache import MemoryCache, TwoTierCache
from autoria_mcp.client import AutoRiaClient
from autoria_mcp.config import Settings
from autoria_mcp.dictionaries import DictionaryResolver
from autoria_mcp.runtime import RuntimeContext

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load and decode ``tests/fixtures/<name>.json``."""
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


async def noop_sleep(_seconds: float) -> None:
    """Drop-in for ``asyncio.sleep`` so retry tests don't actually wait."""
    return None


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """An isolated, writable cache directory per test."""
    path = tmp_path / "cache"
    path.mkdir()
    return path


@pytest.fixture
def make_settings(cache_dir: Path) -> Callable[..., Settings]:
    """Factory for a fully-configured ``Settings`` with credentials present.

    Tests override individual fields via keyword args. ``_env_file=None`` keeps
    the developer's real ``.env`` from leaking into the test environment.
    """

    def _make(**overrides: Any) -> Settings:
        params: dict[str, Any] = {
            "api_key": "test-api-key",
            "user_id": "777",
            "base_url": "https://developers.ria.com",
            "cache_dir": cache_dir,
            # Tiny backoff so the (no-op-sleep) retry path stays trivial.
            "backoff_base": 0.001,
            "backoff_cap": 0.004,
            "_env_file": None,
        }
        params.update(overrides)
        return Settings(**params)

    return _make


@pytest.fixture
def settings(make_settings: Callable[..., Settings]) -> Settings:
    """A ready-to-use ``Settings`` instance with credentials."""
    return make_settings()


@pytest.fixture
def make_runtime() -> Callable[[Settings], RuntimeContext]:
    """Factory for a hand-wired :class:`RuntimeContext` for tool unit tests.

    Mirrors :func:`autoria_mcp.runtime.build_runtime` but injects ``noop_sleep``
    so retry paths never wait. Use ``async with rt.client:`` to close the pool.
    """

    def _make(settings: Settings) -> RuntimeContext:
        client = AutoRiaClient(settings, sleep=noop_sleep)
        dict_cache = TwoTierCache(settings.cache_dir, max_memory_entries=settings.memory_cache_max)
        volatile_cache = MemoryCache(settings.memory_cache_max)
        resolver = DictionaryResolver(client, dict_cache)
        return RuntimeContext(
            settings=settings,
            client=client,
            resolver=resolver,
            dict_cache=dict_cache,
            volatile_cache=volatile_cache,
        )

    return _make
