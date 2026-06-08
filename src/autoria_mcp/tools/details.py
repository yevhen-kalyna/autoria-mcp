"""The curated ``get_car_details`` tools: advert id(s) -> compact details."""

from __future__ import annotations

import asyncio
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from autoria_mcp.client import AutoRiaError
from autoria_mcp.models import CarDetails
from autoria_mcp.runtime import RuntimeContext, get_runtime
from autoria_mcp.shaping import shape_car_details
from autoria_mcp.tools._errors import tool_errors

INFO_PATH = "/auto/info"
# A single batch call is capped to keep one tool invocation from exhausting the
# scarce API quota; fetches run a few at a time rather than all at once.
_BATCH_CAP = 50
_BATCH_CONCURRENCY = 8


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


async def get_car_details_batch_impl(
    rt: RuntimeContext, *, auto_ids: list[int]
) -> list[CarDetails]:
    """Fetch details for several ids concurrently (deduped, order-preserving).

    A failed individual fetch yields a sparse ``CarDetails(id=...)`` (its ``url``
    is ``None``) rather than failing the whole batch, so one dead listing never
    sinks the other 49.
    """
    unique = list(dict.fromkeys(auto_ids))  # dedupe, preserve first-seen order
    if not unique:
        return []
    if len(unique) > _BATCH_CAP:
        raise AutoRiaError(
            f"get_car_details_batch accepts at most {_BATCH_CAP} ids, got {len(unique)}."
        )

    semaphore = asyncio.Semaphore(_BATCH_CONCURRENCY)

    async def _one(auto_id: int) -> CarDetails:
        async with semaphore:
            return await get_car_details_impl(rt, auto_id=auto_id)

    results = await asyncio.gather(*(_one(a) for a in unique), return_exceptions=True)
    return [
        res if isinstance(res, CarDetails) else CarDetails(id=auto_id)
        for auto_id, res in zip(unique, results, strict=True)
    ]


def register_details_tools(mcp: FastMCP) -> None:
    """Register the listing-detail tool on ``mcp``."""

    @mcp.tool()
    async def get_car_details(
        auto_id: Annotated[int, Field(description="Advert id (from `search_used_cars` `ids`).")],
    ) -> CarDetails:
        """Get compact details for a single AUTO.RIA advert by its id.

        Returns price (USD/UAH/EUR), year, mileage (km), fuel + `engine_volume_l`
        + `power_hp`, gearbox, drive, `body_name`, generation, modification,
        colour, location, the VIN (only if the seller revealed it), the masked
        phone, and the canonical listing `url`.

        For due diligence it also returns SELLER-DECLARED, UNVERIFIED provenance:
        `condition` (1 undamaged … 4 for-parts), the `risk` block
        (damaged/for_parts/under_credit/confiscated/imported/needs_customs),
        VIN/inspection `verification`, `seller` trust, `photo` links, plus
        `is_sold`/`is_leasing`/`price_negotiable`/`exchange_possible` and the
        seller `description`. Check `risk` and `condition` before trusting a
        listing — `mileage_km` and prices are claims, not facts. The phone is
        always masked. To look up many ids at once use `get_car_details_batch`.
        """
        async with tool_errors():
            return await get_car_details_impl(get_runtime(), auto_id=auto_id)

    @mcp.tool()
    async def get_car_details_batch(
        auto_ids: Annotated[
            list[int],
            Field(description="Advert ids (from `search_used_cars` `ids`); up to 50 per call."),
        ],
    ) -> list[CarDetails]:
        """Get compact details for several adverts in one call (up to 50 ids).

        The agent-efficiency counterpart to `get_car_details`: instead of one
        round-trip per id when ranking a result page, pass the whole id list and
        get an array back, in the same order, deduplicated. A listing that fails
        to load comes back as a sparse entry (its `url` is null) rather than
        failing the batch. Same fields and caveats as `get_car_details`
        (mileage/price are seller-declared and unverified).
        """
        async with tool_errors():
            return await get_car_details_batch_impl(get_runtime(), auto_ids=auto_ids)
