"""lookup_*: list a dictionary or resolve one name, with candidate errors."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import respx

from autoria_mcp.client import AutoRiaLookupError
from autoria_mcp.config import Settings
from autoria_mcp.runtime import RuntimeContext
from autoria_mcp.tools.lookups import (
    lookup_brands_impl,
    lookup_cities_impl,
    lookup_models_impl,
    lookup_regions_impl,
)
from tests.conftest import load_fixture

BASE = "https://developers.ria.com"

MakeRuntime = Callable[[Settings], RuntimeContext]


@respx.mock
async def test_lookup_brands_lists_all(settings: Settings, make_runtime: MakeRuntime) -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        items = await lookup_brands_impl(rt)
    assert {"id": 9, "name": "BMW"} in items


@respx.mock
async def test_lookup_brands_resolves_one(settings: Settings, make_runtime: MakeRuntime) -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        items = await lookup_brands_impl(rt, name="BMW")
    assert items == [{"id": 9, "name": "BMW"}]


@respx.mock
async def test_lookup_brands_unknown_lists_candidates(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        with pytest.raises(AutoRiaLookupError) as exc:
            await lookup_brands_impl(rt, name="Audii")
    assert "Audi (id=6)" in str(exc.value)


@respx.mock
async def test_lookup_models_within_brand(settings: Settings, make_runtime: MakeRuntime) -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    respx.get(f"{BASE}/auto/categories/1/marks/9/models").mock(
        return_value=httpx.Response(200, json=load_fixture("models"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        listed = await lookup_models_impl(rt, brand="BMW")
        resolved = await lookup_models_impl(rt, brand="BMW", name="X5")
    assert {"id": 96, "name": "X5"} in listed
    assert resolved == [{"id": 96, "name": "X5"}]


@respx.mock
async def test_lookup_regions_and_cities(settings: Settings, make_runtime: MakeRuntime) -> None:
    respx.get(f"{BASE}/auto/states").mock(
        return_value=httpx.Response(200, json=load_fixture("states"))
    )
    respx.get(f"{BASE}/auto/states/1/cities").mock(
        return_value=httpx.Response(200, json=load_fixture("cities"))
    )
    rt = make_runtime(settings)
    async with rt.client:
        region = await lookup_regions_impl(rt, name="Вінницька")
        city = await lookup_cities_impl(rt, region="Вінницька", name="Жмеринка")
    assert region == [{"id": 1, "name": "Вінницька"}]
    assert city == [{"id": 27, "name": "Жмеринка"}]
