"""DictionaryResolver: name->id resolution, matching, errors, and caching."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from autoria_mcp.cache import TwoTierCache
from autoria_mcp.client import AutoRiaClient, AutoRiaLookupError
from autoria_mcp.config import Settings
from autoria_mcp.dictionaries import DictionaryResolver
from tests.conftest import load_fixture, noop_sleep

BASE = "https://developers.ria.com"


def _resolver(settings: Settings) -> tuple[AutoRiaClient, DictionaryResolver]:
    client = AutoRiaClient(settings, sleep=noop_sleep)
    cache = TwoTierCache(settings.cache_dir)
    return client, DictionaryResolver(client, cache)


@respx.mock
async def test_brand_id_resolves(settings: Settings) -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    client, resolver = _resolver(settings)
    async with client:
        assert await resolver.brand_id("BMW") == 9


@respx.mock
async def test_brand_id_is_case_insensitive(settings: Settings) -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    client, resolver = _resolver(settings)
    async with client:
        assert await resolver.brand_id("  bmw ") == 9


@respx.mock
async def test_model_id_resolves_within_brand(settings: Settings) -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    respx.get(f"{BASE}/auto/categories/1/marks/9/models").mock(
        return_value=httpx.Response(200, json=load_fixture("models"))
    )
    client, resolver = _resolver(settings)
    async with client:
        assert await resolver.model_id("BMW", "X5") == 96


@respx.mock
async def test_region_and_city_resolve(settings: Settings) -> None:
    respx.get(f"{BASE}/auto/states").mock(
        return_value=httpx.Response(200, json=load_fixture("states"))
    )
    respx.get(f"{BASE}/auto/states/1/cities").mock(
        return_value=httpx.Response(200, json=load_fixture("cities"))
    )
    client, resolver = _resolver(settings)
    async with client:
        assert await resolver.region_id("Вінницька") == 1
        assert await resolver.city_id("Вінницька", "Жмеринка") == 27


@respx.mock
async def test_fuel_and_drive_resolve(settings: Settings) -> None:
    respx.get(f"{BASE}/auto/type").mock(
        return_value=httpx.Response(200, json=load_fixture("fuel_types"))
    )
    respx.get(f"{BASE}/auto/categories/1/driverTypes").mock(
        return_value=httpx.Response(200, json=load_fixture("driver_types"))
    )
    client, resolver = _resolver(settings)
    async with client:
        assert await resolver.fuel_id("Гібрид (MHEV)") == 11
        assert await resolver.drive_id("Повний") == 1


@respx.mock
async def test_english_fuel_alias_resolves(settings: Settings) -> None:
    """C: an English fuel name resolves to its localized id."""
    respx.get(f"{BASE}/auto/type").mock(
        return_value=httpx.Response(200, json=load_fixture("fuel_types"))
    )
    client, resolver = _resolver(settings)
    async with client:
        assert await resolver.fuel_id("Diesel") == 2
        assert await resolver.fuel_id("petrol") == 1
        assert await resolver.fuel_id("Electric") == 6


@respx.mock
async def test_english_gearbox_alias_resolves(settings: Settings) -> None:
    respx.get(f"{BASE}/auto/categories/1/gearboxes").mock(
        return_value=httpx.Response(200, json=load_fixture("gearboxes"))
    )
    client, resolver = _resolver(settings)
    async with client:
        assert await resolver.gearbox_id("automatic") == 2
        assert await resolver.gearbox_id("manual") == 1


@respx.mock
async def test_body_alias_and_homoglyph_resolve(settings: Settings) -> None:
    """C: 'wagon' and Cyrillic 'Універсал' both match RIA's Latin-i 'Унiверсал'."""
    respx.get(f"{BASE}/auto/categories/1/bodystyles").mock(
        return_value=httpx.Response(200, json=load_fixture("bodystyles"))
    )
    client, resolver = _resolver(settings)
    async with client:
        assert await resolver.body_id("wagon") == 2
        assert await resolver.body_id("Універсал") == 2  # Cyrillic і vs stored Latin i
        assert await resolver.body_id("hatchback") == 4


@respx.mock
async def test_unknown_english_fuel_suggests_localized_first(settings: Settings) -> None:
    """C: a near-miss English fuel surfaces the right localized option first."""
    respx.get(f"{BASE}/auto/type").mock(
        return_value=httpx.Response(200, json=load_fixture("fuel_types"))
    )
    client, resolver = _resolver(settings)
    async with client:
        with pytest.raises(AutoRiaLookupError) as exc:
            await resolver.fuel_id("Dizel")
    assert "Дизель (id=2)" in str(exc.value)


@respx.mock
async def test_unknown_name_lists_candidates(settings: Settings) -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    client, resolver = _resolver(settings)
    async with client:
        with pytest.raises(AutoRiaLookupError) as exc:
            await resolver.brand_id("Audii")
    # A near-miss should surface the real candidate with its id.
    assert "Audi (id=6)" in str(exc.value)


@respx.mock
async def test_ambiguous_match_raises(settings: Settings) -> None:
    duplicated = [
        {"name": "Сірий", "value": 8},
        {"name": " сірий ", "value": 99},
    ]
    respx.get(f"{BASE}/auto/colors").mock(return_value=httpx.Response(200, json=duplicated))
    client, resolver = _resolver(settings)
    async with client:
        with pytest.raises(AutoRiaLookupError) as exc:
            await resolver.color_id("Сірий")
    assert "ambiguous" in str(exc.value)


@respx.mock
async def test_second_lookup_is_served_from_cache(settings: Settings) -> None:
    route = respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    client, resolver = _resolver(settings)
    async with client:
        await resolver.brand_id("BMW")
        await resolver.brand_id("Audi")
    # Two resolutions, one network fetch — the dictionary was cached.
    assert route.call_count == 1


@respx.mock
async def test_concurrent_cold_misses_fetch_once(settings: Settings) -> None:
    route = respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    client, resolver = _resolver(settings)
    async with client:
        # Both miss the cold cache and race on the same dictionary path.
        bmw, audi = await asyncio.gather(
            resolver.brand_id("BMW"),
            resolver.brand_id("Audi"),
        )
    assert (bmw, audi) == (9, 6)
    # Single-flight collapses the concurrent misses into one upstream request.
    assert route.call_count == 1
