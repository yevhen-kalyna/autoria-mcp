"""Paid tools: fail-fast, period/required validation, modes, notice-error, shaping."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
import respx

from autoria_mcp.client import AutoRiaAPIError, AutoRiaConfigError, AutoRiaError
from autoria_mcp.config import Settings
from autoria_mcp.runtime import RuntimeContext
from autoria_mcp.tools.paid import (
    build_avg_price_params,
    get_average_price_impl,
    get_average_price_over_periods_impl,
    get_params_by_vin_impl,
    validate_period,
)
from tests.conftest import load_fixture

BASE = "https://developers.ria.com"
AVG = f"{BASE}/auto/ai-avarage-price/"
STAT = f"{BASE}/auto/statistic-avarage-price/"
VIN = f"{BASE}/auto/params/by/vin-code/"

MakeRuntime = Callable[[Settings], RuntimeContext]


def _mock_renault_megane() -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=[{"name": "Renault", "value": 62}])
    )
    respx.get(f"{BASE}/auto/categories/1/marks/62/models").mock(
        return_value=httpx.Response(200, json=[{"name": "Megane", "value": 586}])
    )


@respx.mock
async def test_fail_fast_without_user_id(
    make_settings: Callable[..., Settings], make_runtime: MakeRuntime
) -> None:
    route = respx.post(AVG).mock(return_value=httpx.Response(200, json={}))
    rt = make_runtime(make_settings(user_id=None))
    async with rt.client:
        with pytest.raises(AutoRiaConfigError):
            await get_average_price_impl(rt, omni_id="WVWZZZ1KZ8P029153")
    # The credential check must short-circuit before any request is spent.
    assert route.call_count == 0


def test_validate_period() -> None:
    assert validate_period(365) == 365
    for good in (30, 90, 180, 365):
        assert validate_period(good) == good
    with pytest.raises(AutoRiaError):
        validate_period(168)


@respx.mock
async def test_period_validation_in_tool(settings: Settings, make_runtime: MakeRuntime) -> None:
    route = respx.post(AVG).mock(return_value=httpx.Response(200, json={}))
    rt = make_runtime(settings)
    async with rt.client:
        with pytest.raises(AutoRiaError):
            await get_average_price_impl(rt, omni_id="X", period=168)
    assert route.call_count == 0


@respx.mock
async def test_params_mode_requires_extra_filter(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    _mock_renault_megane()
    rt = make_runtime(settings)
    async with rt.client:
        with pytest.raises(AutoRiaError):
            # category+brand+model only — no additional filter.
            await get_average_price_impl(rt, brand="Renault", model="Megane")


@respx.mock
async def test_build_avg_price_params_wire_vocabulary(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    _mock_renault_megane()
    rt = make_runtime(settings)
    async with rt.client:
        params = await build_avg_price_params(
            rt,
            brand="Renault",
            model="Megane",
            year_from=2009,
            year_to=2014,
            mileage_from=100000,
            mileage_to=150000,
        )
    assert params["categoryId"] == "1"
    assert params["brandId"] == "62"
    assert params["modelId"] == "586"
    assert params["year"] == {"gte": "2009", "lte": "2014"}
    assert params["mileage"] == {"gte": "100", "lte": "150"}  # km -> thousands


@respx.mock
async def test_build_avg_price_params_includes_engine_volume(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    """ISSUE-1: engine volume constrains the priced cohort (no raw_search needed)."""
    _mock_renault_megane()
    rt = make_runtime(settings)
    async with rt.client:
        params = await build_avg_price_params(
            rt,
            brand="Renault",
            model="Megane",
            engine_volume_from=1.9,
            engine_volume_to=2.1,
        )
    assert params["engineVolume"] == {"gte": "1.9", "lte": "2.1"}


@respx.mock
async def test_get_average_price_by_params(settings: Settings, make_runtime: MakeRuntime) -> None:
    _mock_renault_megane()
    route = respx.post(AVG).mock(
        return_value=httpx.Response(200, json=load_fixture("ai_average_price_params"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        result = await get_average_price_impl(
            rt, brand="Renault", model="Megane", year_from=2009, year_to=2014
        )
    assert result.statistic_data[0].price_usd == 7415
    assert result.similar_cars[0].city == "Рівне"
    # G/ISSUE-9/K: reliability + provenance metadata is attached to the result.
    assert result.avg_price_usd == 7415
    assert result.sample_count == 1
    assert result.price_consistency == "avg_below_sample"
    assert result.status == "ok"
    assert result.cohort is not None and result.cohort["brandId"] == "62"
    assert result.quota is not None and "month_limit" in result.quota
    # The request body carries the JSON shape, not query params.
    body = json.loads(route.calls.last.request.content)
    assert body["period"] == 365
    assert body["params"]["brandId"] == "62"


@respx.mock
async def test_get_average_price_stats_only_omits_samples(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    """ISSUE-8: include_samples=False drops the listings but keeps the stats."""
    _mock_renault_megane()
    respx.post(AVG).mock(
        return_value=httpx.Response(200, json=load_fixture("ai_average_price_params"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        result = await get_average_price_impl(
            rt, brand="Renault", model="Megane", year_from=2009, include_samples=False
        )
    assert result.similar_cars == []  # verbose listings dropped
    assert result.sample_count == 1  # but the sample size/spread survive
    assert result.sample_max_usd == 7650


@respx.mock
async def test_get_average_price_by_omni_id(settings: Settings, make_runtime: MakeRuntime) -> None:
    route = respx.post(AVG).mock(
        return_value=httpx.Response(200, json=load_fixture("ai_average_price_omni"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        result = await get_average_price_impl(rt, omni_id="WVWZZZ1KZ8P029153")
    assert result.similar_cars[0].title == "Skoda Octavia"
    body = json.loads(route.calls.last.request.content)
    assert body["params"] == {"omniId": "WVWZZZ1KZ8P029153"}


@respx.mock
async def test_average_price_over_periods(settings: Settings, make_runtime: MakeRuntime) -> None:
    respx.post(STAT).mock(return_value=httpx.Response(200, json=load_fixture("statistic")))
    rt = make_runtime(settings)
    async with rt.client:
        series = await get_average_price_over_periods_impl(rt, omni_id="TMBGP21U432674944")
    assert len(series.graph_data) == 3
    assert series.graph_data[0].date == "06.25"


@respx.mock
async def test_get_params_by_vin_success(settings: Settings, make_runtime: MakeRuntime) -> None:
    respx.post(VIN).mock(return_value=httpx.Response(200, json=load_fixture("vin_params")))
    rt = make_runtime(settings)
    async with rt.client:
        params = await get_params_by_vin_impl(rt, omni_id="TMBGP21U432674944")
    assert params.search_type == "VIN"
    assert any(c.name == "Skoda" for c in params.chips)


@respx.mock
async def test_get_params_by_vin_notice_error(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    # Invalid omniId returns HTTP 200 + noticeType "error" -> mapped to AutoRiaAPIError.
    respx.post(VIN).mock(return_value=httpx.Response(200, json=load_fixture("notice_error")))
    rt = make_runtime(settings)
    async with rt.client:
        with pytest.raises(AutoRiaAPIError) as exc:
            await get_params_by_vin_impl(rt, omni_id="bad-vin")
    assert exc.value.code == "NOTICE_ERROR"


@respx.mock
async def test_omni_and_params_mutually_exclusive(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    rt = make_runtime(settings)
    async with rt.client:
        with pytest.raises(AutoRiaError):
            await get_average_price_impl(rt, omni_id="X", brand="Renault", model="Megane")
        # Any by-params filter alongside omni_id must also raise (never silently dropped).
        with pytest.raises(AutoRiaError):
            await get_average_price_impl(rt, omni_id="X", year_from=2010)
