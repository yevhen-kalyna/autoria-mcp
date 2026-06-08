"""Curated lookup tools: list a dictionary, or resolve one name to its id.

These wrap the shared :class:`DictionaryResolver` (for name->id, with
nearest-candidate errors on a miss) and the 7-day dictionary cache (for listing),
so an agent can discover valid brand/model/region/city values or confirm a single
one without guessing ids.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from autoria_mcp.models import parse_dictionary
from autoria_mcp.runtime import RuntimeContext, get_runtime
from autoria_mcp.tools._common import cached_get
from autoria_mcp.tools._errors import tool_errors

_CATEGORY_ID = 1


async def _list_items(rt: RuntimeContext, path: str) -> list[dict[str, Any]]:
    """Return a dictionary at ``path`` as ``[{"id", "name"}, ...]``."""
    raw = await cached_get(rt, path)
    return [{"id": item.id, "name": item.name} for item in parse_dictionary(raw)]


def _pick(items: list[dict[str, Any]], target_id: int) -> list[dict[str, Any]]:
    """Return the single item whose id matches ``target_id`` (resolved match)."""
    match = [item for item in items if item["id"] == target_id]
    return match or [{"id": target_id, "name": None}]


async def lookup_brands_impl(
    rt: RuntimeContext, *, name: str | None = None
) -> list[dict[str, Any]]:
    path = f"/auto/categories/{_CATEGORY_ID}/marks"
    items = await _list_items(rt, path)
    if name is None:
        return items
    return _pick(items, await rt.resolver.brand_id(name))


async def lookup_models_impl(
    rt: RuntimeContext, *, brand: str, name: str | None = None
) -> list[dict[str, Any]]:
    marka_id = await rt.resolver.brand_id(brand)
    path = f"/auto/categories/{_CATEGORY_ID}/marks/{marka_id}/models"
    items = await _list_items(rt, path)
    if name is None:
        return items
    return _pick(items, await rt.resolver.model_id(brand, name))


async def lookup_regions_impl(
    rt: RuntimeContext, *, name: str | None = None
) -> list[dict[str, Any]]:
    items = await _list_items(rt, "/auto/states")
    if name is None:
        return items
    return _pick(items, await rt.resolver.region_id(name))


async def lookup_cities_impl(
    rt: RuntimeContext, *, region: str, name: str | None = None
) -> list[dict[str, Any]]:
    state_id = await rt.resolver.region_id(region)
    items = await _list_items(rt, f"/auto/states/{state_id}/cities")
    if name is None:
        return items
    return _pick(items, await rt.resolver.city_id(region, name))


def register_lookup_tools(mcp: FastMCP) -> None:
    """Register the name<->id lookup tools on ``mcp``."""

    @mcp.tool()
    async def lookup_brands(
        name: Annotated[
            str | None,
            Field(default=None, description="Optional brand name to resolve to its id."),
        ] = None,
    ) -> list[dict[str, Any]]:
        """List passenger-car brands, or resolve one brand name to its id.

        With no `name`, returns every brand as `{id, name}`. With a `name`,
        returns the single matching brand (or an error listing close matches).
        """
        async with tool_errors():
            return await lookup_brands_impl(get_runtime(), name=name)

    @mcp.tool()
    async def lookup_models(
        brand: Annotated[str, Field(description="Brand name to list/resolve models within.")],
        name: Annotated[
            str | None,
            Field(default=None, description="Optional model name to resolve to its id."),
        ] = None,
    ) -> list[dict[str, Any]]:
        """List a brand's models, or resolve one model name to its id.

        `brand` is required (models are scoped to a brand). With no `name`,
        returns every model of that brand; with a `name`, the single match.
        """
        async with tool_errors():
            return await lookup_models_impl(get_runtime(), brand=brand, name=name)

    @mcp.tool()
    async def lookup_regions(
        name: Annotated[
            str | None,
            Field(default=None, description="Optional region/oblast name to resolve."),
        ] = None,
    ) -> list[dict[str, Any]]:
        """List regions (oblasts), or resolve one region name to its id.

        Note: Kyiv city and Kyiv oblast are distinct, region-scoped entities — a
        "Kyiv city + surrounding oblast" search may need two passes.
        """
        async with tool_errors():
            return await lookup_regions_impl(get_runtime(), name=name)

    @mcp.tool()
    async def lookup_cities(
        region: Annotated[str, Field(description="Region name to list/resolve cities within.")],
        name: Annotated[
            str | None,
            Field(default=None, description="Optional city name to resolve to its id."),
        ] = None,
    ) -> list[dict[str, Any]]:
        """List a region's cities, or resolve one city name to its id.

        `region` is required (cities are scoped to a region).
        """
        async with tool_errors():
            return await lookup_cities_impl(get_runtime(), region=region, name=name)
