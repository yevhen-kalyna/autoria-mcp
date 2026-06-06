"""get_car_details: shaping from /auto/info, masked phone, canonical url."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import respx

from autoria_mcp.config import Settings
from autoria_mcp.runtime import RuntimeContext
from autoria_mcp.shaping import AUTO_RIA
from autoria_mcp.tools.details import get_car_details_impl
from tests.conftest import load_fixture

BASE = "https://developers.ria.com"

MakeRuntime = Callable[[Settings], RuntimeContext]


@respx.mock
async def test_get_car_details_shapes_payload(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    respx.get(f"{BASE}/auto/info").mock(return_value=httpx.Response(200, json=load_fixture("info")))
    rt = make_runtime(settings)
    async with rt.client:
        details = await get_car_details_impl(rt, auto_id=36756951)

    assert details.id == 36756951
    assert details.title == "BMW 3 Series"
    assert details.price_usd == 32999
    assert details.mileage_km == 140000
    assert details.phone == "(xxx) xxx xx xx"  # always masked upstream
    assert details.url == f"{AUTO_RIA}/auto_bmw_3_series_36756951.html"


@respx.mock
async def test_get_car_details_second_call_cached(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    route = respx.get(f"{BASE}/auto/info").mock(
        return_value=httpx.Response(200, json=load_fixture("info"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        await get_car_details_impl(rt, auto_id=36756951)
        await get_car_details_impl(rt, auto_id=36756951)
    assert route.call_count == 1
