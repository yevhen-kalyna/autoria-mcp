"""Paid statistics tools (POST endpoints).

Three tools, all requiring ``user_id`` (in addition to ``api_key``):
  * ``get_average_price`` — point-in-time AI average price + comparable listings.
  * ``get_average_price_over_periods`` — average-price time series.
  * ``get_params_by_vin`` — decode a VIN/plate/advert id into car-parameter chips.

The two average-price tools accept **natural** inputs (brand/model names, year/
mileage ranges) resolved internally — exactly like ``search_used_cars`` — with a
raw-id escape hatch for ``generation_id``/``modification_id`` (which can't be
cleanly name-resolved). They also accept an ``omni_id`` (VIN/plate/advert id) that
short-circuits all resolution. ``get_params_by_vin`` is omniId-only.

Each tool **fails fast** (no request spent) when ``user_id`` is unset, validates
``period`` against the API's allowed set, and enforces the by-params required
rule (category + brand + model + at least one more) before posting. The avg-price
wire vocabulary differs from search (``brandId``/``gearBoxId``/``bodyId``, all
strings; ranges as ``{gte, lte}`` strings) — a dedicated mapper builds it.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from autoria_mcp.client import AutoRiaConfigError, AutoRiaError
from autoria_mcp.models import AveragePriceResult, StatisticSeries, VinParams
from autoria_mcp.quota import QuotaUsage
from autoria_mcp.runtime import RuntimeContext, get_runtime
from autoria_mcp.shaping import shape_average_price, shape_statistic, shape_vin
from autoria_mcp.tools._errors import tool_errors

AVG_PRICE_PATH = "/auto/ai-avarage-price/"
STATISTIC_PATH = "/auto/statistic-avarage-price/"
VIN_PATH = "/auto/params/by/vin-code/"

_LANG_ID = 4  # UK
_CATEGORY_ID = 1  # passenger cars (default)
_ALLOWED_PERIODS = frozenset({30, 90, 180, 365})
# The 3 always-present required keys; by-params mode needs at least one beyond these.
_REQUIRED_KEYS = frozenset({"categoryId", "brandId", "modelId"})


def _quota_snapshot(usage: QuotaUsage) -> dict[str, int]:
    """Flatten the quota usage into a plain ``dict[str, int]`` for the response."""
    return {
        "hour_count": usage["hour_count"],
        "hour_limit": usage["hour_limit"],
        "month_count": usage["month_count"],
        "month_limit": usage["month_limit"],
    }


def _require_user_id(rt: RuntimeContext) -> None:
    """Fail fast (before any request) when the paid credential is missing."""
    if not rt.settings.user_id:
        raise AutoRiaConfigError(
            "AUTORIA_USER_ID is required for paid endpoints but is not set. Set it "
            "alongside AUTORIA_API_KEY to use the average-price and VIN tools."
        )


def validate_period(period: int) -> int:
    """Return ``period`` if allowed (30/90/180/365), else raise."""
    if period not in _ALLOWED_PERIODS:
        allowed = ", ".join(str(p) for p in sorted(_ALLOWED_PERIODS))
        raise AutoRiaError(f"period must be one of {{{allowed}}}, got {period}.")
    return period


def _range(lo: int | float | None, hi: int | float | None) -> dict[str, str] | None:
    """Build a ``{gte, lte}`` string range, including only the present bounds."""
    span: dict[str, str] = {}
    if lo is not None:
        span["gte"] = str(lo)
    if hi is not None:
        span["lte"] = str(hi)
    return span or None


async def build_avg_price_params(
    rt: RuntimeContext,
    *,
    category: str | None = None,
    brand: str,
    model: str,
    region: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    mileage_from: int | None = None,
    mileage_to: int | None = None,
    fuel: str | None = None,
    gearbox: str | None = None,
    drive: str | None = None,
    body: str | None = None,
    color: str | None = None,
    engine_volume_from: float | None = None,
    engine_volume_to: float | None = None,
    generation_id: int | None = None,
    modification_id: int | None = None,
) -> dict[str, Any]:
    """Resolve natural inputs into the avg-price ``CarParams`` (string-id) body.

    Enforces the API's required rule: category + brand + model + at least one
    more parameter, raising before any request is spent if it is not met.
    """
    category_id = await rt.resolver.category_id(category) if category else _CATEGORY_ID
    brand_id = await rt.resolver.brand_id(brand, category_id=category_id)
    model_id = await rt.resolver.model_id(brand, model, category_id=category_id)

    params: dict[str, Any] = {
        "categoryId": str(category_id),
        "brandId": str(brand_id),
        "modelId": str(model_id),
    }
    if region:
        params["stateId"] = str(await rt.resolver.region_id(region))
    if fuel:
        params["fuelId"] = str(await rt.resolver.fuel_id(fuel))
    if gearbox:
        params["gearBoxId"] = str(await rt.resolver.gearbox_id(gearbox, category_id=category_id))
    if drive:
        params["driveId"] = str(await rt.resolver.drive_id(drive, category_id=category_id))
    if body:
        params["bodyId"] = str(await rt.resolver.body_id(body, category_id=category_id))
    if color:
        params["colorId"] = str(await rt.resolver.color_id(color))
    if generation_id is not None:
        params["generationId"] = str(generation_id)
    if modification_id is not None:
        params["modificationId"] = str(modification_id)

    engine_volume = _range(engine_volume_from, engine_volume_to)
    if engine_volume is not None:
        params["engineVolume"] = engine_volume

    year = _range(year_from, year_to)
    if year is not None:
        params["year"] = year
    # API mileage is in thousands of km; the tool accepts km.
    mileage = _range(
        mileage_from // 1000 if mileage_from is not None else None,
        mileage_to // 1000 if mileage_to is not None else None,
    )
    if mileage is not None:
        params["mileage"] = mileage

    if set(params) <= _REQUIRED_KEYS:
        raise AutoRiaError(
            "Average price by parameters needs at least one filter beyond "
            "category/brand/model (e.g. year, mileage, fuel, gearbox, body)."
        )
    return params


async def _params_or_omni(
    rt: RuntimeContext,
    *,
    omni_id: str | None,
    brand: str | None,
    model: str | None,
    **resolved: Any,
) -> dict[str, Any]:
    """Return the request ``params`` for either omniId or by-params mode."""
    if omni_id is not None:
        # omniId is exclusive: reject ANY by-params field so filters are never
        # silently dropped (the same vigilance as the search silent-ignore guard).
        if brand or model or any(value is not None for value in resolved.values()):
            raise AutoRiaError("Provide either omni_id OR car parameters, not both.")
        return {"omniId": omni_id}
    if not brand or not model:
        raise AutoRiaError("Provide omni_id, or at least brand and model.")
    return await build_avg_price_params(rt, brand=brand, model=model, **resolved)


async def _post_cached(rt: RuntimeContext, path: str, body: dict[str, Any]) -> Any:
    """POST ``body`` to ``path`` through the short-TTL volatile cache.

    Only successful responses are cached: the client raises on the HTTP-200
    notice-error shape before we get here, so failures are never memoized.
    """
    key = f"{path}?{json.dumps(body, sort_keys=True, ensure_ascii=False)}"
    raw = await rt.volatile_cache.get(key)
    if raw is None:
        raw = await rt.client.post_json(path, json_body=body)
        await rt.volatile_cache.set(key, raw, rt.settings.volatile_ttl)
    return raw


async def get_average_price_impl(
    rt: RuntimeContext,
    *,
    omni_id: str | None = None,
    period: int = 365,
    category: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    region: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    mileage_from: int | None = None,
    mileage_to: int | None = None,
    fuel: str | None = None,
    gearbox: str | None = None,
    drive: str | None = None,
    body: str | None = None,
    color: str | None = None,
    engine_volume_from: float | None = None,
    engine_volume_to: float | None = None,
    generation_id: int | None = None,
    modification_id: int | None = None,
    include_samples: bool = True,
) -> AveragePriceResult:
    _require_user_id(rt)
    validate_period(period)
    params = await _params_or_omni(
        rt,
        omni_id=omni_id,
        brand=brand,
        model=model,
        category=category,
        region=region,
        year_from=year_from,
        year_to=year_to,
        mileage_from=mileage_from,
        mileage_to=mileage_to,
        fuel=fuel,
        gearbox=gearbox,
        drive=drive,
        body=body,
        color=color,
        engine_volume_from=engine_volume_from,
        engine_volume_to=engine_volume_to,
        generation_id=generation_id,
        modification_id=modification_id,
    )
    body_payload = {"langId": _LANG_ID, "period": period, "params": params}
    raw = await _post_cached(rt, AVG_PRICE_PATH, body_payload)
    result = shape_average_price(raw, cohort=params, period=period)
    result.quota = _quota_snapshot(await rt.client.quota.usage())
    if not include_samples:
        # Stats-only mode: keep the sample size/spread, drop the verbose listings.
        result.similar_cars = []
    return result


async def get_average_price_over_periods_impl(
    rt: RuntimeContext,
    *,
    omni_id: str | None = None,
    period: int = 365,
    category: str | None = None,
    brand: str | None = None,
    model: str | None = None,
    region: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    mileage_from: int | None = None,
    mileage_to: int | None = None,
    fuel: str | None = None,
    gearbox: str | None = None,
    drive: str | None = None,
    body: str | None = None,
    color: str | None = None,
    engine_volume_from: float | None = None,
    engine_volume_to: float | None = None,
    generation_id: int | None = None,
    modification_id: int | None = None,
) -> StatisticSeries:
    _require_user_id(rt)
    validate_period(period)
    params = await _params_or_omni(
        rt,
        omni_id=omni_id,
        brand=brand,
        model=model,
        category=category,
        region=region,
        year_from=year_from,
        year_to=year_to,
        mileage_from=mileage_from,
        mileage_to=mileage_to,
        fuel=fuel,
        gearbox=gearbox,
        drive=drive,
        body=body,
        color=color,
        engine_volume_from=engine_volume_from,
        engine_volume_to=engine_volume_to,
        generation_id=generation_id,
        modification_id=modification_id,
    )
    body_payload = {"langId": _LANG_ID, "period": period, "params": params}
    raw = await _post_cached(rt, STATISTIC_PATH, body_payload)
    result = shape_statistic(raw, cohort=params, period=period)
    result.quota = _quota_snapshot(await rt.client.quota.usage())
    return result


async def get_params_by_vin_impl(rt: RuntimeContext, *, omni_id: str) -> VinParams:
    _require_user_id(rt)
    body_payload = {"langId": _LANG_ID, "period": 365, "params": {"omniId": omni_id}}
    raw = await _post_cached(rt, VIN_PATH, body_payload)
    return shape_vin(raw)


# -- shared tool argument annotations ----------------------------------------

_OmniId = Annotated[
    str | None,
    Field(default=None, description="VIN, plate number, or advert id. Skips by-params mode."),
]
_Period = Annotated[
    int,
    Field(default=365, description="Period in days; one of 30, 90, 180, 365."),
]


def register_paid_tools(mcp: FastMCP) -> None:
    """Register the paid statistics tools on ``mcp`` (always registered)."""

    @mcp.tool()
    async def get_average_price(
        omni_id: _OmniId = None,
        period: _Period = 365,
        brand: Annotated[str | None, Field(default=None, description="Brand name.")] = None,
        model: Annotated[str | None, Field(default=None, description="Model name.")] = None,
        region: Annotated[str | None, Field(default=None, description="Region name.")] = None,
        year_from: Annotated[int | None, Field(default=None, description="Earliest year.")] = None,
        year_to: Annotated[int | None, Field(default=None, description="Latest year.")] = None,
        mileage_from: Annotated[
            int | None, Field(default=None, description="Min mileage in km.")
        ] = None,
        mileage_to: Annotated[
            int | None, Field(default=None, description="Max mileage in km.")
        ] = None,
        fuel: Annotated[str | None, Field(default=None, description="Fuel type name.")] = None,
        gearbox: Annotated[str | None, Field(default=None, description="Gearbox name.")] = None,
        drive: Annotated[str | None, Field(default=None, description="Drive type name.")] = None,
        body: Annotated[str | None, Field(default=None, description="Body style name.")] = None,
        color: Annotated[str | None, Field(default=None, description="Colour name.")] = None,
        engine_volume_from: Annotated[
            float | None,
            Field(
                default=None,
                description=(
                    "Min engine volume in litres, e.g. 1.9. Narrows the comparable "
                    "sample, NOT the model-level headline estimate."
                ),
            ),
        ] = None,
        engine_volume_to: Annotated[
            float | None,
            Field(
                default=None,
                description=(
                    "Max engine volume in litres, e.g. 2.1. Narrows the comparable "
                    "sample, NOT the model-level headline estimate."
                ),
            ),
        ] = None,
        generation_id: Annotated[
            int | None,
            Field(
                default=None,
                description=(
                    "Raw generation id (improves accuracy). One only — facelifts are "
                    "separate ids, so call once per generation to span them."
                ),
            ),
        ] = None,
        modification_id: Annotated[
            int | None, Field(default=None, description="Raw modification id (improves accuracy).")
        ] = None,
        include_samples: Annotated[
            bool,
            Field(
                default=True,
                description=(
                    "Include the `similar_cars` comparable listings. Set False for a "
                    "lighter stats-only response (sample size + spread are still returned)."
                ),
            ),
        ] = True,
    ) -> AveragePriceResult:
        """**Paid.** AI average price + comparable listings (point-in-time).

        Two modes: pass `omni_id` (VIN/plate/advert id), OR car parameters by
        name (`brand`+`model` required, plus at least one more filter such as
        `year_from`/`mileage_to`/`fuel`/`engine_volume_from`). Names are resolved
        to ids for you; `generation_id`/`modification_id` are optional raw ids.
        Requires `AUTORIA_USER_ID`. `period` ∈ {30, 90, 180, 365}.

        The headline `avg_price_usd`/`avg_price_uah` is AUTO.RIA's own **model-level**
        AI estimate — it is only weakly sensitive to `engine_volume`/`modification`,
        so do NOT read it as an engine-precise fair value. For that, prefer
        `cohort_estimate_usd` (the median of the comparable listings), keeping in mind
        the sample is small. To judge reliability, the response also returns
        `sample_count` and the sample's own `sample_min_usd`/`sample_median_usd`/
        `sample_max_usd`, plus a `price_consistency` flag that is `avg_below_sample`/
        `avg_above_sample` when the headline falls outside its own comparables.
        `status` is `no_data` / `insufficient_sample` / `ok` — it is
        `insufficient_sample` when fewer than 5 comps are in-cohort or when a tight
        cohort was requested yet the headline ignored it. Comps are flagged `in_cohort`
        and `cohort_estimate_usd` uses only those (`in_cohort_count` reports how many).
        `cohort` echoes the resolved filters. `quota` is a LOCAL, advisory, warn-only
        counter (it can exceed its limit and never blocks) — not AUTO.RIA's enforced
        budget, so don't hard-gate on it.

        Note: facelifts are distinct `generation_id`s and this endpoint takes a
        single one — call once per generation to price a whole family.

        Example: `get_average_price(brand="Peugeot", model="308", fuel="Дизель",
        engine_volume_from=1.9, engine_volume_to=2.1, year_from=2014, period=365)`.
        """
        async with tool_errors():
            return await get_average_price_impl(
                get_runtime(),
                omni_id=omni_id,
                period=period,
                brand=brand,
                model=model,
                region=region,
                year_from=year_from,
                year_to=year_to,
                mileage_from=mileage_from,
                mileage_to=mileage_to,
                fuel=fuel,
                gearbox=gearbox,
                drive=drive,
                body=body,
                color=color,
                engine_volume_from=engine_volume_from,
                engine_volume_to=engine_volume_to,
                generation_id=generation_id,
                modification_id=modification_id,
                include_samples=include_samples,
            )

    @mcp.tool()
    async def get_average_price_over_periods(
        omni_id: _OmniId = None,
        period: _Period = 365,
        brand: Annotated[str | None, Field(default=None, description="Brand name.")] = None,
        model: Annotated[str | None, Field(default=None, description="Model name.")] = None,
        region: Annotated[str | None, Field(default=None, description="Region name.")] = None,
        year_from: Annotated[int | None, Field(default=None, description="Earliest year.")] = None,
        year_to: Annotated[int | None, Field(default=None, description="Latest year.")] = None,
        mileage_from: Annotated[
            int | None, Field(default=None, description="Min mileage in km.")
        ] = None,
        mileage_to: Annotated[
            int | None, Field(default=None, description="Max mileage in km.")
        ] = None,
        fuel: Annotated[str | None, Field(default=None, description="Fuel type name.")] = None,
        gearbox: Annotated[str | None, Field(default=None, description="Gearbox name.")] = None,
        drive: Annotated[str | None, Field(default=None, description="Drive type name.")] = None,
        body: Annotated[str | None, Field(default=None, description="Body style name.")] = None,
        color: Annotated[str | None, Field(default=None, description="Colour name.")] = None,
        engine_volume_from: Annotated[
            float | None,
            Field(
                default=None,
                description=(
                    "Min engine volume in litres, e.g. 1.9. Narrows the comparable "
                    "sample, NOT the model-level headline estimate."
                ),
            ),
        ] = None,
        engine_volume_to: Annotated[
            float | None,
            Field(
                default=None,
                description=(
                    "Max engine volume in litres, e.g. 2.1. Narrows the comparable "
                    "sample, NOT the model-level headline estimate."
                ),
            ),
        ] = None,
        generation_id: Annotated[
            int | None,
            Field(
                default=None,
                description=(
                    "Raw generation id (improves accuracy). One only — facelifts are "
                    "separate ids, so call once per generation to span them."
                ),
            ),
        ] = None,
        modification_id: Annotated[
            int | None, Field(default=None, description="Raw modification id (improves accuracy).")
        ] = None,
    ) -> StatisticSeries:
        """**Paid.** Average-price time series (monthly) for a car or `omni_id`.

        Same inputs and modes as `get_average_price`; returns `graph_data`
        (monthly average price, `date` as "MM.YY") plus the available period
        presets. Requires `AUTORIA_USER_ID`. `period` ∈ {30, 90, 180, 365}.
        """
        async with tool_errors():
            return await get_average_price_over_periods_impl(
                get_runtime(),
                omni_id=omni_id,
                period=period,
                brand=brand,
                model=model,
                region=region,
                year_from=year_from,
                year_to=year_to,
                mileage_from=mileage_from,
                mileage_to=mileage_to,
                fuel=fuel,
                gearbox=gearbox,
                drive=drive,
                body=body,
                color=color,
                engine_volume_from=engine_volume_from,
                engine_volume_to=engine_volume_to,
                generation_id=generation_id,
                modification_id=modification_id,
            )

    @mcp.tool()
    async def get_params_by_vin(
        omni_id: Annotated[str, Field(description="VIN, plate number, or advert id to decode.")],
    ) -> VinParams:
        """**Paid.** Decode a VIN / plate / advert id into car-parameter chips.

        Returns the decoded attributes (category, brand, model, body, fuel,
        gearbox, drive, colour, year, ...) plus a link to equivalent listings.
        Only works if the vehicle was ever listed on AUTO.RIA. Requires
        `AUTORIA_USER_ID`. An unresolvable id surfaces as a tool error.
        """
        async with tool_errors():
            return await get_params_by_vin_impl(get_runtime(), omni_id=omni_id)
