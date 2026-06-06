"""Browsable MCP resources for the param-less reference dictionaries.

Resources let an MCP client *browse* the slow-changing dictionaries (categories,
colours, countries, fuel types, gearboxes, body styles, regions) as addressable
``autoria://dict/...`` documents, plus a templated models-by-brand resource. All
go through the 7-day dictionary cache, so browsing costs no quota after the first
fetch. The category-scoped dictionaries (gearboxes, body styles) are exposed for
passenger cars (category 1); use the mirror tools for other categories.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from autoria_mcp.runtime import get_runtime
from autoria_mcp.tools._common import cached_get

_CATEGORY_ID = 1


async def _dump(path: str) -> str:
    """Fetch ``path`` (7-day cached) and return it as a JSON string."""
    raw = await cached_get(get_runtime(), path)
    return json.dumps(raw, ensure_ascii=False)


def register_resources(mcp: FastMCP) -> None:
    """Register the dictionary resources (and the models template) on ``mcp``."""

    @mcp.resource("autoria://dict/categories", mime_type="application/json")
    async def categories() -> str:
        """All transport categories (ids + names)."""
        return await _dump("/auto/categories")

    @mcp.resource("autoria://dict/colors", mime_type="application/json")
    async def colors() -> str:
        """All paint colours (ids + names)."""
        return await _dump("/auto/colors")

    @mcp.resource("autoria://dict/countries", mime_type="application/json")
    async def countries() -> str:
        """Manufacturer/origin countries (note the custom 900+ block)."""
        return await _dump("/auto/countries")

    @mcp.resource("autoria://dict/fuel-types", mime_type="application/json")
    async def fuel_types() -> str:
        """Fuel types (includes MHEV 11 / REEV 12)."""
        return await _dump("/auto/type")

    @mcp.resource("autoria://dict/gearboxes", mime_type="application/json")
    async def gearboxes() -> str:
        """Gearboxes for passenger cars (category 1)."""
        return await _dump(f"/auto/categories/{_CATEGORY_ID}/gearboxes")

    @mcp.resource("autoria://dict/body-styles", mime_type="application/json")
    async def body_styles() -> str:
        """Body styles for passenger cars (category 1)."""
        return await _dump(f"/auto/categories/{_CATEGORY_ID}/bodystyles")

    @mcp.resource("autoria://dict/states", mime_type="application/json")
    async def states() -> str:
        """Regions (oblasts) with ids."""
        return await _dump("/auto/states")

    @mcp.resource("autoria://dict/models/{categoryId}/{markId}", mime_type="application/json")
    async def models(categoryId: str, markId: str) -> str:  # noqa: N803 (URI template param names)
        """Models for a given category + brand id."""
        return await _dump(f"/auto/categories/{categoryId}/marks/{markId}/models")
