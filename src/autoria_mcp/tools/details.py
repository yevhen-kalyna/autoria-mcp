"""The curated ``get_car_details`` tool: one advert id -> compact details."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from autoria_mcp.models import CarDetails
from autoria_mcp.runtime import RuntimeContext, get_runtime
from autoria_mcp.shaping import shape_car_details
from autoria_mcp.tools._errors import tool_errors

INFO_PATH = "/auto/info"


async def get_car_details_impl(rt: RuntimeContext, *, auto_id: int) -> CarDetails:
    """Fetch ``/auto/info`` for ``auto_id`` and shape it into :class:`CarDetails`.

    Listing detail is volatile (price/status change), so it goes through the
    short-TTL volatile cache rather than the 7-day dictionary cache.
    """
    params = {"auto_id": auto_id}
    key = f"{INFO_PATH}?auto_id={auto_id}"
    raw = await rt.volatile_cache.get(key)
    if raw is None:
        raw = await rt.client.get_json(INFO_PATH, params)
        await rt.volatile_cache.set(key, raw, rt.settings.volatile_ttl)
    return shape_car_details(raw)


def register_details_tools(mcp: FastMCP) -> None:
    """Register the listing-detail tool on ``mcp``."""

    @mcp.tool()
    async def get_car_details(
        auto_id: Annotated[int, Field(description="Advert id (from `search_used_cars` `ids`).")],
    ) -> CarDetails:
        """Get compact details for a single AUTO.RIA advert by its id.

        Returns price (USD/UAH/EUR), year, mileage (km), fuel, gearbox, drive,
        body, generation, modification, colour, location, the VIN (only if the
        seller revealed it), the masked phone, and the canonical listing `url`.
        The phone is always masked by AUTO.RIA — this tool never exposes a real
        number. Pair with `search_used_cars`, which returns the ids to look up.
        """
        async with tool_errors():
            return await get_car_details_impl(get_runtime(), auto_id=auto_id)
