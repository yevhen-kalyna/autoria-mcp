"""Drive the autoria-mcp server from an in-process MCP client session.

A minimal, network-free demo: it builds the server, connects a client over an
in-memory transport, lists the tool/resource surface, and calls the zero-quota
``ping`` tool. No API key is required — none of these calls hit the network.

Run it with::

    uv run python examples/inproc_session.py

To go further and actually query AUTO.RIA, set ``AUTORIA_API_KEY`` (and
``AUTORIA_USER_ID`` for the paid tools) and call, e.g.,
``session.call_tool("lookup_brands", {"name": "BMW"})`` followed by
``search_used_cars`` / ``get_car_details`` — each such call spends scarce quota.
"""

from __future__ import annotations

import asyncio

from mcp.shared.memory import create_connected_server_and_client_session

from autoria_mcp.config import Settings
from autoria_mcp.server import build_server


async def main() -> None:
    server = build_server(Settings())

    async with create_connected_server_and_client_session(server) as session:
        await session.initialize()

        tools = (await session.list_tools()).tools
        resources = (await session.list_resources()).resources
        templates = (await session.list_resource_templates()).resourceTemplates

        print(f"tools ({len(tools)}):")
        for tool in sorted(tools, key=lambda t: t.name):
            print(f"  - {tool.name}")

        print(f"\nresources ({len(resources)}):")
        for resource in sorted(resources, key=lambda r: str(r.uri)):
            print(f"  - {resource.uri}")

        print(f"\nresource templates ({len(templates)}):")
        for template in templates:
            print(f"  - {template.uriTemplate}")

        ping = await session.call_tool("ping", {})
        print(f"\nping isError={ping.isError}")


if __name__ == "__main__":
    asyncio.run(main())
