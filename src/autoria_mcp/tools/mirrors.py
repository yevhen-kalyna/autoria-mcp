"""Thin, raw-passthrough mirrors of the long-tail AUTO.RIA endpoints.

These return the upstream JSON unshaped (raw ids and labels) for power users and
for dimensions the curated tools don't cover (generations, modifications,
equipment trims, options, etc.). Reference dictionaries go through the 7-day
cache; the raw search mirror goes through the short-TTL volatile cache.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from autoria_mcp.cache import make_cache_key
from autoria_mcp.runtime import RuntimeContext, get_runtime
from autoria_mcp.shaping import shape_search
from autoria_mcp.tools._common import cached_get
from autoria_mcp.tools._errors import tool_errors

_CATEGORY_ID = 1
SEARCH_PATH = "/auto/search"


async def raw_search_impl(
    rt: RuntimeContext, params: dict[str, Any], *, verbose: bool = False
) -> Any:
    """Run a raw ``/auto/search`` and return the compact (default) or full payload."""
    key = make_cache_key(SEARCH_PATH, params)
    raw = await rt.volatile_cache.get(key)
    if raw is None:
        raw = await rt.client.get_json(SEARCH_PATH, params)
        await rt.volatile_cache.set(key, raw, rt.settings.volatile_ttl)
    if verbose:
        return raw
    page = params.get("page", 0)
    page_size = params.get("countpage", 10)
    return shape_search(
        raw,
        page=page if isinstance(page, int) else 0,
        page_size=page_size if isinstance(page_size, int) else 10,
    )


def register_mirror_tools(mcp: FastMCP) -> None:
    """Register the thin endpoint mirrors on ``mcp``."""

    @mcp.tool()
    async def list_categories() -> Any:
        """List all transport categories (ids + names). Cached 7 days."""
        async with tool_errors():
            return await cached_get(get_runtime(), "/auto/categories")

    @mcp.tool()
    async def list_all_models() -> Any:
        """List all models across every brand/category (raw). Cached 7 days."""
        async with tool_errors():
            return await cached_get(get_runtime(), "/auto/models")

    @mcp.tool()
    async def list_models_grouped(
        mark_id: Annotated[int, Field(description="Brand id.")],
        category_id: Annotated[
            int, Field(default=_CATEGORY_ID, description="Category id.")
        ] = _CATEGORY_ID,
    ) -> Any:
        """List a brand's models grouped into families (heterogeneous). Cached 7d."""
        async with tool_errors():
            path = f"/auto/categories/{category_id}/marks/{mark_id}/models/_group"
            return await cached_get(get_runtime(), path)

    @mcp.tool()
    async def list_generations(
        model_id: Annotated[int, Field(description="Model id.")],
    ) -> Any:
        """List generations for a model. Cached 7 days.

        Raw upstream shape (camelCase: `generationId`, `yearFrom`, `yearTo`). Note
        `yearTo: 0` is a sentinel for "current / still produced", not a literal year.
        """
        async with tool_errors():
            path = f"/generations/by/models/{model_id}/generations"
            return await cached_get(get_runtime(), path)

    @mcp.tool()
    async def list_modifications(
        generation_id: Annotated[int, Field(description="Generation id.")],
    ) -> Any:
        """List modifications (engine/trim variants) for a generation. Cached 7d."""
        async with tool_errors():
            path = f"/modifications/by/generation/{generation_id}/modifications"
            return await cached_get(get_runtime(), path)

    @mcp.tool()
    async def list_modifications_by_body(
        generation_id: Annotated[int, Field(description="Generation id.")],
        body_id: Annotated[int, Field(description="Body-style id.")],
    ) -> Any:
        """List modifications for a generation restricted to a body type. Cached 7d."""
        async with tool_errors():
            path = f"/modifications/by/generation/{generation_id}/body/{body_id}/modifications"
            return await cached_get(get_runtime(), path)

    @mcp.tool()
    async def list_equipment(
        modification_id: Annotated[int, Field(description="Modification id.")],
    ) -> Any:
        """List equipment trims for a modification. Cached 7 days."""
        async with tool_errors():
            params = {"modificationId": modification_id}
            return await cached_get(get_runtime(), "/auto_ria/equips_by_modifications", params)

    @mcp.tool()
    async def list_options(
        category_id: Annotated[
            int, Field(default=_CATEGORY_ID, description="Category id.")
        ] = _CATEGORY_ID,
    ) -> Any:
        """List the flat option/equipment vocabulary for a category. Cached 7d."""
        async with tool_errors():
            return await cached_get(get_runtime(), f"/auto/categories/{category_id}/options")

    @mcp.tool()
    async def list_options_v2(
        category_id: Annotated[
            int, Field(default=_CATEGORY_ID, description="Category id.")
        ] = _CATEGORY_ID,
    ) -> Any:
        """List the grouped (publishing) options V2 structure for a category. Cached 7d."""
        async with tool_errors():
            return await cached_get(
                get_runtime(), f"/used_auto/get_options/{category_id}/optionsV2"
            )

    @mcp.tool()
    async def list_colors() -> Any:
        """List paint colours (ids + names). Cached 7 days."""
        async with tool_errors():
            return await cached_get(get_runtime(), "/auto/colors")

    @mcp.tool()
    async def list_countries() -> Any:
        """List manufacturer/origin countries (note the custom 900+ block). Cached 7d."""
        async with tool_errors():
            return await cached_get(get_runtime(), "/auto/countries")

    @mcp.tool()
    async def list_drive_types(
        category_id: Annotated[
            int, Field(default=_CATEGORY_ID, description="Category id.")
        ] = _CATEGORY_ID,
    ) -> Any:
        """List drive types for a category (ids are category-specific). Cached 7d."""
        async with tool_errors():
            return await cached_get(get_runtime(), f"/auto/categories/{category_id}/driverTypes")

    @mcp.tool()
    async def list_fuel_types() -> Any:
        """List fuel types (ids + names; includes MHEV 11 / REEV 12). Cached 7d."""
        async with tool_errors():
            return await cached_get(get_runtime(), "/auto/type")

    @mcp.tool()
    async def list_gearboxes(
        category_id: Annotated[
            int, Field(default=_CATEGORY_ID, description="Category id.")
        ] = _CATEGORY_ID,
    ) -> Any:
        """List gearboxes for a category. Cached 7 days."""
        async with tool_errors():
            return await cached_get(get_runtime(), f"/auto/categories/{category_id}/gearboxes")

    @mcp.tool()
    async def list_body_styles(
        category_id: Annotated[
            int, Field(default=_CATEGORY_ID, description="Category id.")
        ] = _CATEGORY_ID,
    ) -> Any:
        """List body styles for a category (parentId groups them). Cached 7d."""
        async with tool_errors():
            return await cached_get(get_runtime(), f"/auto/categories/{category_id}/bodystyles")

    @mcp.tool()
    async def list_body_styles_grouped(
        category_id: Annotated[
            int, Field(default=_CATEGORY_ID, description="Category id.")
        ] = _CATEGORY_ID,
    ) -> Any:
        """List body styles for a category as groups (array of arrays). Cached 7d."""
        async with tool_errors():
            return await cached_get(
                get_runtime(), f"/auto/categories/{category_id}/bodystyles/_group"
            )

    @mcp.tool()
    async def list_all_body_styles() -> Any:
        """List all body styles across categories (raw). Cached 7 days."""
        async with tool_errors():
            return await cached_get(get_runtime(), "/auto/bodystyles")

    @mcp.tool()
    async def list_bodies_by_generation(
        generation_id: Annotated[int, Field(description="Generation id.")],
    ) -> Any:
        """List body types available for a generation. Cached 7 days."""
        async with tool_errors():
            path = f"/bodies/by/generation/{generation_id}/bodies"
            return await cached_get(get_runtime(), path)

    @mcp.tool()
    async def raw_search(
        params: Annotated[
            dict[str, Any],
            Field(description="Raw AUTO.RIA V1 search params, e.g. {'marka_id[0]': 9}."),
        ],
        verbose: Annotated[
            bool,
            Field(
                default=False,
                description=(
                    "False (default) returns the compact {count, page, page_size, ids} "
                    "shape (OfferOfTheDay filtered out). True returns the full raw API "
                    "response — large; use only when you need the echoed params/metadata."
                ),
            ),
        ] = False,
    ) -> Any:
        """Run a raw ``/auto/search`` with V1 params (power users).

        Bypasses the curated name-resolution of `search_used_cars`; you supply V1
        wire params directly (e.g. `marka_id[0]`, `category_id`, `s_yers[0]`).
        Cached briefly (volatile). By default returns the same compact shape as
        `search_used_cars` (ids + count); pass `verbose=True` for the full raw
        payload (~150 lines of echoed params/metadata).
        """
        async with tool_errors():
            return await raw_search_impl(get_runtime(), params, verbose=verbose)
