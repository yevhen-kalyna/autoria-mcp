"""AutoRiaClient: auth injection, retry/backoff, and error-shape mapping.

All HTTP is intercepted by respx; an un-mocked request fails the test, proving
zero network and zero quota.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx

from autoria_mcp.client import (
    AutoRiaAPIError,
    AutoRiaAuthError,
    AutoRiaClient,
    AutoRiaConfigError,
    AutoRiaRateLimitError,
)
from autoria_mcp.config import Settings
from tests.conftest import load_fixture, noop_sleep

BASE = "https://developers.ria.com"


@respx.mock
async def test_get_injects_api_key(settings: Settings) -> None:
    route = respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    async with AutoRiaClient(settings, sleep=noop_sleep) as client:
        data = await client.get_json("/auto/categories/1/marks")

    assert route.called
    assert route.calls.last.request.url.params["api_key"] == "test-api-key"
    # The body parsed through untouched.
    assert data[4]["name"] == "BMW"


@respx.mock
async def test_post_injects_api_key_and_user_id(settings: Settings) -> None:
    route = respx.post(f"{BASE}/auto/params/by/vin-code/").mock(
        return_value=httpx.Response(200, json={"searchType": "VIN"})
    )
    async with AutoRiaClient(settings, sleep=noop_sleep) as client:
        await client.post_json("/auto/params/by/vin-code/")

    params = route.calls.last.request.url.params
    assert params["api_key"] == "test-api-key"
    assert params["user_id"] == "777"


@respx.mock
async def test_retries_then_succeeds_on_429(settings: Settings) -> None:
    route = respx.get(f"{BASE}/auto/colors").mock(
        side_effect=[
            httpx.Response(429, json=load_fixture("error_over_rate_limit")),
            httpx.Response(200, json=load_fixture("colors")),
        ]
    )
    async with AutoRiaClient(settings, sleep=noop_sleep) as client:
        data = await client.get_json("/auto/colors")

    assert route.call_count == 2
    assert data[1]["name"] == "Чорний"


@respx.mock
async def test_retries_exhaust_on_5xx_then_raises(settings: Settings) -> None:
    route = respx.get(f"{BASE}/auto/colors").mock(return_value=httpx.Response(503))
    async with AutoRiaClient(settings, sleep=noop_sleep) as client:
        with pytest.raises(AutoRiaAPIError) as exc:
            await client.get_json("/auto/colors")

    # max_retries (3) + the initial attempt == 4 wire calls.
    assert route.call_count == settings.max_retries + 1
    assert exc.value.status_code == 503


@respx.mock
async def test_auth_error_is_not_retried(settings: Settings) -> None:
    route = respx.get(f"{BASE}/auto/colors").mock(
        return_value=httpx.Response(403, json=load_fixture("error_api_key_missing"))
    )
    async with AutoRiaClient(settings, sleep=noop_sleep) as client:
        with pytest.raises(AutoRiaAuthError) as exc:
            await client.get_json("/auto/colors")

    assert route.call_count == 1  # 4xx auth must not retry
    assert exc.value.code == "API_KEY_MISSING"
    assert exc.value.status_code == 403


@respx.mock
async def test_persistent_429_maps_to_rate_limit_error(settings: Settings) -> None:
    respx.get(f"{BASE}/auto/colors").mock(
        return_value=httpx.Response(429, json=load_fixture("error_over_rate_limit"))
    )
    async with AutoRiaClient(settings, sleep=noop_sleep) as client:
        with pytest.raises(AutoRiaRateLimitError) as exc:
            await client.get_json("/auto/colors")

    assert exc.value.code == "OVER_RATE_LIMIT"
    assert exc.value.status_code == 429


@respx.mock
async def test_notice_data_error_on_http_200(settings: Settings) -> None:
    respx.post(f"{BASE}/auto/params/by/vin-code/").mock(
        return_value=httpx.Response(200, json=load_fixture("notice_error"))
    )
    async with AutoRiaClient(settings, sleep=noop_sleep) as client:
        with pytest.raises(AutoRiaAPIError) as exc:
            await client.post_json("/auto/params/by/vin-code/")

    assert exc.value.code == "NOTICE_ERROR"
    assert exc.value.status_code == 200
    assert "Некоректні" in str(exc.value)


@respx.mock
async def test_missing_api_key_raises_before_any_request(
    make_settings: Callable[..., Settings],
) -> None:
    route = respx.get(f"{BASE}/auto/colors").mock(return_value=httpx.Response(200, json=[]))
    settings = make_settings(api_key=None)
    async with AutoRiaClient(settings, sleep=noop_sleep) as client:
        with pytest.raises(AutoRiaConfigError):
            await client.get_json("/auto/colors")

    assert not route.called  # no quota spent


@respx.mock
async def test_missing_user_id_raises_before_post(
    make_settings: Callable[..., Settings],
) -> None:
    route = respx.post(f"{BASE}/auto/params/by/vin-code/").mock(
        return_value=httpx.Response(200, json={})
    )
    settings = make_settings(user_id=None)
    async with AutoRiaClient(settings, sleep=noop_sleep) as client:
        with pytest.raises(AutoRiaConfigError):
            await client.post_json("/auto/params/by/vin-code/")

    assert not route.called
