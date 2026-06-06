"""End-to-end MCP wiring.

The substantive test drives the real MCP protocol in-process via
``create_connected_server_and_client_session`` (which runs the server lifespan,
installing the runtime) against respx fixtures — exercising
initialize -> list_tools/list_resources -> call_tool. A second, network-free test
boots the server over **real stdio** as a subprocess and asserts it advertises
its tool/resource surface (transport smoke test only — no API-hitting tool).
"""

from __future__ import annotations

import os
import sys

import httpx
import respx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from autoria_mcp.config import Settings
from autoria_mcp.server import build_server
from tests.conftest import load_fixture

BASE = "https://developers.ria.com"


@respx.mock
async def test_in_process_roundtrip(settings: Settings) -> None:
    respx.get(f"{BASE}/auto/categories/1/marks").mock(
        return_value=httpx.Response(200, json=load_fixture("marks"))
    )
    respx.get(f"{BASE}/auto/categories/1/marks/9/models").mock(
        return_value=httpx.Response(200, json=load_fixture("models"))
    )
    respx.get(f"{BASE}/auto/search").mock(
        return_value=httpx.Response(200, json=load_fixture("search"))
    )

    mcp = build_server(settings)
    async with create_connected_server_and_client_session(mcp) as session:
        await session.initialize()

        tool_names = {t.name for t in (await session.list_tools()).tools}
        assert {
            "ping",
            "search_used_cars",
            "get_car_details",
            "get_average_price",
            "get_average_price_over_periods",
            "get_params_by_vin",
            "lookup_brands",
            "raw_search",
            "list_colors",
        } <= tool_names

        resource_uris = {str(r.uri) for r in (await session.list_resources()).resources}
        assert "autoria://dict/categories" in resource_uris

        ping = await session.call_tool("ping", {})
        assert ping.isError is False

        result = await session.call_tool("search_used_cars", {"brand": "BMW", "model": "3 Series"})
        assert result.isError is False
        assert result.structuredContent is not None
        assert "100500" not in result.structuredContent["ids"]
        assert result.structuredContent["count"] == 19679


async def test_stdio_subprocess_boot() -> None:
    """Boot the entry point over real stdio and list its surface (zero network)."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "autoria_mcp.server"],
        # Inherit the venv (PATH/VIRTUAL_ENV) so the package imports; a dummy key
        # lets the server boot. No tool here touches the network.
        env={**os.environ, "AUTORIA_API_KEY": "test", "AUTORIA_TRANSPORT": "stdio"},
    )
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tool_names = {t.name for t in (await session.list_tools()).tools}
        assert "search_used_cars" in tool_names
        assert (await session.list_resources()).resources
