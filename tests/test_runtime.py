"""RuntimeContext wiring and the lifespan's set/reset + client teardown."""

from __future__ import annotations

import pytest

from autoria_mcp.config import Settings
from autoria_mcp.runtime import (
    build_runtime,
    get_runtime,
    make_runtime_lifespan,
    reset_runtime,
)
from autoria_mcp.server import build_server


async def test_build_runtime_wires_all_fields(settings: Settings) -> None:
    rt = build_runtime(settings)
    try:
        assert rt.settings is settings
        assert rt.client is not None
        assert rt.resolver is not None
        assert rt.dict_cache is not None
        assert rt.volatile_cache is not None
        # Volatile and dictionary caches must be distinct instances.
        assert rt.dict_cache is not rt.volatile_cache
    finally:
        await rt.client.aclose()


async def test_lifespan_sets_then_resets_and_closes_client(settings: Settings) -> None:
    reset_runtime()
    lifespan = make_runtime_lifespan(settings)
    mcp = build_server(settings)

    async with lifespan(mcp) as rt:
        assert get_runtime() is rt

    # After exit the singleton is cleared and the HTTP pool is closed.
    with pytest.raises(RuntimeError):
        get_runtime()
    assert rt.client._http.is_closed
