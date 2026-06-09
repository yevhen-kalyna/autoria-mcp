"""search_used_cars: id resolution, OfferOfTheDay filtering, sanity check, caching."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx

from autoria_mcp.client import AutoRiaError
from autoria_mcp.config import Settings
from autoria_mcp.runtime import RuntimeContext
from autoria_mcp.tools.search import (
    build_search_query,
    resolve_order_by,
    search_used_cars_impl,
)
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
async def test_search_resolves_filters_and_returns_ids(
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
    assert wire["searchType"] == 4  # used-only, so count excludes new autos
    assert wire["countpage"] == 10
    assert resolved == {"category_id": 1, "marka_id": 9, "model_id": 3219}


@respx.mock
async def test_search_include_details_attaches_batch(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    """include_details=True enriches the page's ids in one call (no manual 2nd round)."""
    _mock_brand_model()
    respx.get(f"{BASE}/auto/search").mock(
        return_value=httpx.Response(200, json=load_fixture("search"))
    )
    respx.get(f"{BASE}/auto/info").mock(return_value=httpx.Response(200, json=load_fixture("info")))
    rt = make_runtime(settings)
    async with rt.client:
        result = await search_used_cars_impl(
            rt, brand="BMW", model="3 Series", include_details=True
        )
    assert result.ids == ["39728975", "39837585", "39963555"]
    assert result.details is not None
    assert len(result.details) == len(result.ids)


@respx.mock
async def test_search_without_include_details_has_none(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    _mock_brand_model()
    respx.get(f"{BASE}/auto/search").mock(
        return_value=httpx.Response(200, json=load_fixture("search"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        result = await search_used_cars_impl(rt, brand="BMW", model="3 Series")
    assert result.details is None


async def test_search_include_details_rejects_large_page_size(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    """include_details fans out one detail call per id, so it's capped at the batch size."""
    rt = make_runtime(settings)
    async with rt.client:
        with pytest.raises(AutoRiaError):
            await search_used_cars_impl(rt, brand="BMW", include_details=True, page_size=51)


@respx.mock
async def test_search_hybrid_fuel_emits_multiple_type_params(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    """fuel='Гібрид' fans out to type[0..3] in one wire query (all hybrid subtypes)."""
    _mock_brand_model()
    respx.get(f"{BASE}/auto/type").mock(
        return_value=httpx.Response(200, json=load_fixture("fuel_types"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        wire, _ = await build_search_query(rt, brand="BMW", fuel="Гібрид")
    type_values = sorted(v for k, v in wire.items() if k.startswith("type["))
    assert type_values == [5, 10, 11, 12]


@respx.mock
async def test_search_single_fuel_emits_one_type_param(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    _mock_brand_model()
    respx.get(f"{BASE}/auto/type").mock(
        return_value=httpx.Response(200, json=load_fixture("fuel_types"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        wire, _ = await build_search_query(rt, brand="BMW", fuel="Дизель")
    assert wire["type[0]"] == 2
    assert "type[1]" not in wire


async def test_search_model_without_brand_raises(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    rt = make_runtime(settings)
    async with rt.client:
        with pytest.raises(AutoRiaError):
            await build_search_query(rt, model="3 Series")


def test_resolve_order_by_accepts_names_and_ints() -> None:
    """L: named sorts map to V1 ints; ints pass through; junk is rejected."""
    assert resolve_order_by("price_asc") == 2
    assert resolve_order_by("PRICE_DESC") == 3
    assert resolve_order_by("relevance") == 0
    assert resolve_order_by(13) == 13  # mileage_asc legacy int
    with pytest.raises(AutoRiaError):
        resolve_order_by("cheapest")
    with pytest.raises(AutoRiaError):
        resolve_order_by(99)


@respx.mock
async def test_search_named_order_by_reaches_wire(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    _mock_brand_model()
    rt = make_runtime(settings)
    async with rt.client:
        wire, _ = await build_search_query(rt, brand="BMW", order_by="price_asc")
    assert wire["order_by"] == 2


@respx.mock
async def test_search_maps_engine_power_generation_modification(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    """D: engine/power/generation/modification filters reach their V1 wire keys."""
    _mock_brand_model()
    rt = make_runtime(settings)
    async with rt.client:
        wire, _ = await build_search_query(
            rt,
            brand="BMW",
            engine_volume_from=1.9,
            engine_volume_to=2.1,
            power_hp_from=150,
            power_hp_to=250,
            generation_id=[559, 560],
            modification_id=[135908],
        )
    assert wire["engineVolumeFrom"] == "1.9"
    assert wire["engineVolumeTo"] == "2.1"
    assert wire["powerFrom"] == 150
    assert wire["powerTo"] == 250
    assert wire["power_name"] == 1  # hp
    # Generation = 2-level index, modification = 3-level; multiple span facelifts.
    assert wire["generation_id[0][0]"] == 559
    assert wire["generation_id[0][1]"] == 560
    assert wire["modification_id[0][0][0]"] == 135908
