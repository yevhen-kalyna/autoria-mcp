"""raw_search: compact-by-default shaping vs. the full verbose payload."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import respx

from autoria_mcp.config import Settings
from autoria_mcp.models import SearchResult
from autoria_mcp.runtime import RuntimeContext
from autoria_mcp.tools.mirrors import raw_search_impl
from tests.conftest import load_fixture

BASE = "https://developers.ria.com"

MakeRuntime = Callable[[Settings], RuntimeContext]


@respx.mock
async def test_raw_search_compact_by_default(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    """ISSUE-7/13: default returns the compact SearchResult, OfferOfTheDay filtered."""
    respx.get(f"{BASE}/auto/search").mock(
        return_value=httpx.Response(200, json=load_fixture("search"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        result = await raw_search_impl(rt, {"marka_id[0]": 9, "countpage": 10})
    assert isinstance(result, SearchResult)
    assert result.count == 19679
    assert "100500" not in result.ids  # promo filtered out
    assert result.page_size == 10  # read from countpage


@respx.mock
async def test_raw_search_verbose_returns_full_payload(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    respx.get(f"{BASE}/auto/search").mock(
        return_value=httpx.Response(200, json=load_fixture("search"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        result = await raw_search_impl(rt, {"marka_id[0]": 9}, verbose=True)
    # The full raw payload retains the upstream envelope the compact shape drops.
    assert isinstance(result, dict)
    assert "result" in result
