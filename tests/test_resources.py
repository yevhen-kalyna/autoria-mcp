"""Dictionary resources: listing, templated resolution, and 7-day caching."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import respx

from autoria_mcp.config import Settings
from autoria_mcp.runtime import RuntimeContext, reset_runtime, set_runtime
from autoria_mcp.server import build_server
from tests.conftest import load_fixture

BASE = "https://developers.ria.com"

MakeRuntime = Callable[[Settings], RuntimeContext]


async def test_lists_resources_and_template(settings: Settings) -> None:
    mcp = build_server(settings)
    uris = {str(r.uri) for r in await mcp.list_resources()}
    assert {
        "autoria://dict/categories",
        "autoria://dict/colors",
        "autoria://dict/countries",
        "autoria://dict/fuel-types",
        "autoria://dict/gearboxes",
        "autoria://dict/body-styles",
        "autoria://dict/states",
    } <= uris

    templates = {t.uriTemplate for t in await mcp.list_resource_templates()}
    assert "autoria://dict/models/{categoryId}/{markId}" in templates


@respx.mock
async def test_read_param_less_resource(settings: Settings, make_runtime: MakeRuntime) -> None:
    respx.get(f"{BASE}/auto/categories").mock(
        return_value=httpx.Response(200, json=load_fixture("categories"))
    )
    mcp = build_server(settings)
    rt = make_runtime(settings)
    set_runtime(rt)
    try:
        async with rt.client:
            contents = list(await mcp.read_resource("autoria://dict/categories"))
    finally:
        reset_runtime()

    payload = json.loads(contents[0].content)
    assert any(item["name"] == "Легкові" for item in payload)


@respx.mock
async def test_read_templated_models_resource(
    settings: Settings, make_runtime: MakeRuntime
) -> None:
    route = respx.get(f"{BASE}/auto/categories/1/marks/9/models").mock(
        return_value=httpx.Response(200, json=load_fixture("models"))
    )
    mcp = build_server(settings)
    rt = make_runtime(settings)
    set_runtime(rt)
    try:
        async with rt.client:
            first = list(await mcp.read_resource("autoria://dict/models/1/9"))
            # A repeat read is served from the 7-day dictionary cache.
            list(await mcp.read_resource("autoria://dict/models/1/9"))
    finally:
        reset_runtime()

    payload = json.loads(first[0].content)
    assert any(item["name"] == "3 Series" for item in payload)
    assert route.call_count == 1
