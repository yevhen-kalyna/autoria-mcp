"""search_used_cars: id resolution, OfferOfTheDay filtering, sanity check, caching."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx

from autoria_mcp.client import AutoRiaError
from autoria_mcp.config import Settings
from autoria_mcp.runtime import RuntimeContext
from autoria_mcp.tools.search import build_search_query, search_used_cars_impl
from tests.conftest import load_fixture

BASE = "https://developers.ria.com"

MakeRuntime = Callable[[Settings], RuntimeContext]


def _mock_brand_model() -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    respx.get(f"{BASE}/auto/categories/1/marks/9/models").mock(
        return_value=httpx.Response(200, json=load_fixture("models"))
    )


@respx.mock
async def test_search_resolves_filters_and_builds_url(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    _mock_brand_model()
    respx.get(f"{BASE}/auto/search").mock(
        return_value=httpx.Response(200, json=load_fixture("search"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        result = await search_used_cars_impl(rt, brand="BMW", model="3 Series")

    assert result.count == 19679
    assert result.ids == ["39728975", "39837585", "39963555"]  # 100500 filtered out
    assert "brand.id[0]=9" in result.search_url
    assert "model.id[0]=3219" in result.search_url


@respx.mock
async def test_search_aborts_when_filters_silently_ignored(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    _mock_brand_model()
    respx.get(f"{BASE}/auto/search").mock(
        return_value=httpx.Response(200, json=load_fixture("search_ignored"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        with pytest.raises(AutoRiaError) as exc:
            await search_used_cars_impl(rt, brand="BMW")
    assert "ignored" in str(exc.value).lower()


@respx.mock
async def test_search_second_identical_call_is_cached(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    _mock_brand_model()
    route = respx.get(f"{BASE}/auto/search").mock(
        return_value=httpx.Response(200, json=load_fixture("search"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        await search_used_cars_impl(rt, brand="BMW", model="3 Series")
        await search_used_cars_impl(rt, brand="BMW", model="3 Series")
    # The volatile cache serves the repeat search without a second wire call.
    assert route.call_count == 1


@respx.mock
async def test_build_search_query_maps_to_v1_wire_names(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    _mock_brand_model()
    rt = make_runtime(settings)
    async with rt.client:
        wire, resolved = await build_search_query(
            rt,
            brand="BMW",
            model="3 Series",
            year_from=2015,
            year_to=2020,
            price_from=5000,
            price_to=30000,
            currency="EUR",
            mileage_from=50000,
            mileage_to=150000,
        )

    assert wire["marka_id[0]"] == 9
    assert wire["model_id[0]"] == 3219
    assert wire["s_yers[0]"] == 2015
    assert wire["po_yers[0]"] == 2020
    assert wire["price_ot"] == 5000
    assert wire["price_do"] == 30000
    assert wire["currency"] == 2  # EUR
    assert wire["raceFrom"] == 50  # km -> thousands
    assert wire["raceTo"] == 150
    assert wire["searchType"] == 1
    assert wire["countpage"] == 10
    assert resolved == {"category_id": 1, "marka_id": 9, "model_id": 3219}


async def test_search_model_without_brand_raises(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    rt = make_runtime(settings)
    async with rt.client:
        with pytest.raises(AutoRiaError):
            await build_search_query(rt, model="3 Series")
