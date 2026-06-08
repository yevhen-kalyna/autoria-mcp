"""The curated ``search_used_cars`` tool.

Takes human-friendly inputs (brand/model/region names, year/price/mileage
ranges), resolves them to AUTO.RIA's **V1** numeric wire params via the shared
dictionary resolver, and makes exactly **one** ``/auto/search`` call. It returns
the total match ``count`` and the matching ids only (no auto-enrichment); the
agent drills into a specific id with ``get_car_details`` for its details and URL.

Three verified foot-guns are handled here:
  * **V1-only vocabulary.** ``/auto/search`` honors V1 names (``marka_id``,
    ``bodystyle``, ``type`` for fuel, ...); V3 names are silently ignored and the
    endpoint returns the entire site. After the call we sanity-check the echoed
    ``cleaned.marka_id`` whenever a brand was requested.
  * **New-auto contamination.** The default search mixes NEW cars into the
    results, inflating ``count``. We send ``searchType=4`` (used only) so the
    count is the true used-car total (verified live against the API).
  * **OfferOfTheDay.** RIA still injects a promo advert (id ``100500``) into the
    results even with ``searchType=4``; we keep only ``type == "UsedAuto"`` entries.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from autoria_mcp.cache import make_cache_key
from autoria_mcp.client import AutoRiaError
from autoria_mcp.models import SearchResult
from autoria_mcp.runtime import RuntimeContext, get_runtime
from autoria_mcp.shaping import cleaned_params, shape_search
from autoria_mcp.tools._errors import tool_errors

# v1 search is passenger-cars only; category 1 scopes the category-specific
# dictionaries (body styles, gearboxes) the resolver consults.
_CATEGORY_ID = 1
# Search currency codes are NOT the V3 codes: 1=USD, 2=EUR, 3=UAH.
_CURRENCY: dict[str, int] = {"USD": 1, "EUR": 2, "UAH": 3}

Currency = Literal["USD", "EUR", "UAH"]
SEARCH_PATH = "/auto/search"

# Named sort orders, mapped to the V1 ``order_by`` magic numbers. Agents may pass
# either the int or the name; a price-asc/price-desc slip silently flips
# "cheapest" to "most expensive", so the names make intent explicit.
_ORDER_BY_NAMES: dict[str, int] = {
    "relevance": 0,
    "price_asc": 2,
    "price_desc": 3,
    "year_desc": 5,  # newest first
    "year_asc": 6,  # oldest first
    "date_desc": 7,  # newest listing first
    "date_asc": 8,  # oldest listing first
    "mileage_desc": 12,
    "mileage_asc": 13,
}
_ORDER_BY_VALUES = frozenset(_ORDER_BY_NAMES.values())


def resolve_order_by(value: int | str) -> int:
    """Coerce a named or numeric ``order_by`` to its V1 int, validating the input."""
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly
        raise AutoRiaError("`order_by` must be a sort name or int, not a bool.")
    if isinstance(value, int):
        if value not in _ORDER_BY_VALUES:
            allowed = ", ".join(str(v) for v in sorted(_ORDER_BY_VALUES))
            raise AutoRiaError(f"`order_by` int must be one of {{{allowed}}}, got {value}.")
        return value
    key = value.strip().casefold()
    if key not in _ORDER_BY_NAMES:
        allowed = ", ".join(sorted(_ORDER_BY_NAMES))
        raise AutoRiaError(f"unknown `order_by` '{value}'. Use one of: {allowed}.")
    return _ORDER_BY_NAMES[key]


async def build_search_query(
    rt: RuntimeContext,
    *,
    brand: str | None = None,
    model: str | None = None,
    region: str | None = None,
    city: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    price_from: int | None = None,
    price_to: int | None = None,
    currency: Currency = "USD",
    fuel: str | None = None,
    gearbox: str | None = None,
    body: str | None = None,
    mileage_from: int | None = None,
    mileage_to: int | None = None,
    engine_volume_from: float | None = None,
    engine_volume_to: float | None = None,
    power_hp_from: int | None = None,
    power_hp_to: int | None = None,
    generation_id: list[int] | None = None,
    modification_id: list[int] | None = None,
    page: int = 0,
    page_size: int = 10,
    order_by: int | str = 0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve natural inputs to V1 wire params.

    Returns ``(wire, resolved)``: ``wire`` is the query dict for ``/auto/search``
    (V1 names, bracket-indexed arrays); ``resolved`` holds the resolved ids used
    to build the attribution URL and run the silent-ignore sanity check.
    """
    if model is not None and brand is None:
        raise AutoRiaError("`model` requires `brand` (resolve the model within its brand).")
    if city is not None and region is None:
        raise AutoRiaError("`city` requires `region` (resolve the city within its region).")

    order_by_int = resolve_order_by(order_by)

    marka_id = await rt.resolver.brand_id(brand) if brand else None
    model_id = await rt.resolver.model_id(brand, model) if (brand and model) else None
    state_id = await rt.resolver.region_id(region) if region else None
    city_id = await rt.resolver.city_id(region, city) if (region and city) else None
    fuel_id = await rt.resolver.fuel_id(fuel) if fuel else None
    gearbox_id = await rt.resolver.gearbox_id(gearbox) if gearbox else None
    body_id = await rt.resolver.body_id(body) if body else None

    wire: dict[str, Any] = {
        "category_id": _CATEGORY_ID,
        # searchType=4 = used cars only. The default mixes NEW autos into the
        # results, which inflates `count` even though `keep_used_autos` filters
        # the ids; with 4 the count is the true used-only total (verified live).
        "searchType": 4,
        "countpage": page_size,
        "page": page,
        "order_by": order_by_int,
        "currency": _CURRENCY[currency],
    }
    if marka_id is not None:
        wire["marka_id[0]"] = marka_id
    if model_id is not None:
        wire["model_id[0]"] = model_id
    if state_id is not None:
        wire["state[0]"] = state_id
    if city_id is not None:
        wire["city[0]"] = city_id
    if year_from is not None:
        wire["s_yers[0]"] = year_from
    if year_to is not None:
        wire["po_yers[0]"] = year_to
    if fuel_id is not None:
        wire["type[0]"] = fuel_id
    if gearbox_id is not None:
        wire["gearbox[0]"] = gearbox_id
    if body_id is not None:
        wire["bodystyle[0]"] = body_id
    if mileage_from is not None:
        wire["raceFrom"] = mileage_from // 1000  # API expects thousands of km
    if mileage_to is not None:
        wire["raceTo"] = mileage_to // 1000
    if price_from is not None:
        wire["price_ot"] = price_from
    if price_to is not None:
        wire["price_do"] = price_to
    # Engine volume is litres as a decimal string; power is an int in к.с.
    # (power_name=1). These were previously reachable only via raw_search.
    if engine_volume_from is not None:
        wire["engineVolumeFrom"] = str(engine_volume_from)
    if engine_volume_to is not None:
        wire["engineVolumeTo"] = str(engine_volume_to)
    if power_hp_from is not None or power_hp_to is not None:
        wire["power_name"] = 1  # 1 == к.с. (hp); 2 == kW
        if power_hp_from is not None:
            wire["powerFrom"] = power_hp_from
        if power_hp_to is not None:
            wire["powerTo"] = power_hp_to
    # Generation uses a 2-level bracket index, modification a 3-level one; the
    # outer indices are the (single) brand-model block, the inner one the value.
    for i, gid in enumerate(generation_id or []):
        wire[f"generation_id[0][{i}]"] = gid
    for i, mid in enumerate(modification_id or []):
        wire[f"modification_id[0][0][{i}]"] = mid

    resolved: dict[str, Any] = {"category_id": _CATEGORY_ID}
    if marka_id is not None:
        resolved["marka_id"] = marka_id
    if model_id is not None:
        resolved["model_id"] = model_id
    if state_id is not None:
        resolved["state_id"] = state_id

    return wire, resolved


async def search_used_cars_impl(
    rt: RuntimeContext,
    *,
    brand: str | None = None,
    model: str | None = None,
    region: str | None = None,
    city: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    price_from: int | None = None,
    price_to: int | None = None,
    currency: Currency = "USD",
    fuel: str | None = None,
    gearbox: str | None = None,
    body: str | None = None,
    mileage_from: int | None = None,
    mileage_to: int | None = None,
    engine_volume_from: float | None = None,
    engine_volume_to: float | None = None,
    power_hp_from: int | None = None,
    power_hp_to: int | None = None,
    generation_id: list[int] | None = None,
    modification_id: list[int] | None = None,
    page: int = 0,
    page_size: int = 10,
    order_by: int | str = 0,
) -> SearchResult:
    """Run one search and return the shaped, OfferOfTheDay-filtered result."""
    wire, resolved = await build_search_query(
        rt,
        brand=brand,
        model=model,
        region=region,
        city=city,
        year_from=year_from,
        year_to=year_to,
        price_from=price_from,
        price_to=price_to,
        currency=currency,
        fuel=fuel,
        gearbox=gearbox,
        body=body,
        mileage_from=mileage_from,
        mileage_to=mileage_to,
        engine_volume_from=engine_volume_from,
        engine_volume_to=engine_volume_to,
        power_hp_from=power_hp_from,
        power_hp_to=power_hp_to,
        generation_id=generation_id,
        modification_id=modification_id,
        page=page,
        page_size=page_size,
        order_by=order_by,
    )

    key = make_cache_key(SEARCH_PATH, wire)
    raw = await rt.volatile_cache.get(key)
    if raw is None:
        raw = await rt.client.get_json(SEARCH_PATH, wire)
        await rt.volatile_cache.set(key, raw, rt.settings.volatile_ttl)

    # V1 silent-ignore guard: if we asked for a brand but the API echoed no
    # marka_id back, our params were ignored and these results are the whole site.
    if "marka_id" in resolved and not cleaned_params(raw).get("marka_id"):
        raise AutoRiaError(
            "AUTO.RIA ignored the requested filters (echoed cleaned.marka_id is empty); "
            "the result would be the entire catalogue. Aborting rather than return it."
        )

    return shape_search(raw, page=page, page_size=page_size)


def register_search_tools(mcp: FastMCP) -> None:
    """Register the curated search tool on ``mcp``."""

    @mcp.tool()
    async def search_used_cars(
        brand: Annotated[
            str | None,
            Field(default=None, description="Brand/marque name, e.g. 'BMW', 'Toyota'."),
        ] = None,
        model: Annotated[
            str | None,
            Field(default=None, description="Model name; requires `brand`, e.g. '3 Series'."),
        ] = None,
        region: Annotated[
            str | None,
            Field(default=None, description="Region/oblast name, e.g. 'Київська'."),
        ] = None,
        city: Annotated[
            str | None,
            Field(default=None, description="City name; requires `region`, e.g. 'Жмеринка'."),
        ] = None,
        year_from: Annotated[
            int | None, Field(default=None, description="Earliest model year, e.g. 2015.")
        ] = None,
        year_to: Annotated[
            int | None, Field(default=None, description="Latest model year, e.g. 2020.")
        ] = None,
        price_from: Annotated[
            int | None, Field(default=None, description="Minimum price in `currency`.")
        ] = None,
        price_to: Annotated[
            int | None, Field(default=None, description="Maximum price in `currency`.")
        ] = None,
        currency: Annotated[
            Currency, Field(default="USD", description="Price currency: USD, EUR, or UAH.")
        ] = "USD",
        fuel: Annotated[
            str | None,
            Field(default=None, description="Fuel type name, e.g. 'Дизель', 'Електро'."),
        ] = None,
        gearbox: Annotated[
            str | None,
            Field(default=None, description="Gearbox name, e.g. 'Автомат', 'Ручна / Механіка'."),
        ] = None,
        body: Annotated[
            str | None,
            Field(default=None, description="Body style name, e.g. 'Седан', 'Універсал'."),
        ] = None,
        mileage_from: Annotated[
            int | None, Field(default=None, description="Minimum mileage in km, e.g. 50000.")
        ] = None,
        mileage_to: Annotated[
            int | None, Field(default=None, description="Maximum mileage in km, e.g. 150000.")
        ] = None,
        engine_volume_from: Annotated[
            float | None,
            Field(default=None, description="Min engine volume in litres, e.g. 1.9."),
        ] = None,
        engine_volume_to: Annotated[
            float | None,
            Field(default=None, description="Max engine volume in litres, e.g. 2.1."),
        ] = None,
        power_hp_from: Annotated[
            int | None, Field(default=None, description="Min engine power in hp (к.с.).")
        ] = None,
        power_hp_to: Annotated[
            int | None, Field(default=None, description="Max engine power in hp (к.с.).")
        ] = None,
        generation_id: Annotated[
            list[int] | None,
            Field(
                default=None,
                description=(
                    "Generation id(s) from `list_generations`. Pass several to span "
                    "facelifts of one generation (e.g. C7, C7 FL)."
                ),
            ),
        ] = None,
        modification_id: Annotated[
            list[int] | None,
            Field(default=None, description="Modification id(s) from `list_modifications`."),
        ] = None,
        page: Annotated[int, Field(default=0, ge=0, description="0-based page number.")] = 0,
        page_size: Annotated[
            int, Field(default=10, ge=1, le=100, description="Results per page (1-100).")
        ] = 10,
        order_by: Annotated[
            int | str,
            Field(
                default="relevance",
                description=(
                    "Sort order — pass a name (preferred) or the legacy int: "
                    "relevance (0), price_asc (2), price_desc (3), year_desc (5, "
                    "newest), year_asc (6), date_desc (7, newest listing), date_asc "
                    "(8), mileage_desc (12), mileage_asc (13)."
                ),
            ),
        ] = "relevance",
    ) -> SearchResult:
        """Search AUTO.RIA used-car listings (passenger cars) by friendly inputs.

        Resolves brand/model/region/city/fuel/gearbox/body **names** to AUTO.RIA
        ids for you, then makes a single search call. Returns the total match
        `count`, the current `page`/`page_size`, and the matching advert `ids`
        (used cars only — the OfferOfTheDay promo is filtered out). To get a
        specific listing's details and its own auto.ria.com URL, pass an id to
        `get_car_details`.

        Notes:
          * Mileage is in **km** (e.g. `mileage_to=150000`); engine volume is in
            **litres** (`engine_volume_from=1.9`), power in **hp** (`power_hp_from`).
          * Engine volume is stored imprecisely upstream (a 2.0 may appear as 1.97),
            so use a band (e.g. 1.9–2.1) rather than an exact value.
          * `model` requires `brand`; `city` requires `region`. Filter by
            `generation_id`/`modification_id` (from `list_generations` /
            `list_modifications`) to isolate a specific generation or engine/trim.
          * v1 supports a single brand+model block. For multi-brand queries use
            the `raw_search` tool.

        Example: `search_used_cars(brand="Audi", model="A6", body="Універсал",
        engine_volume_from=1.9, engine_volume_to=2.1, fuel="Дизель", order_by="price_asc")`.
        """
        async with tool_errors():
            return await search_used_cars_impl(
                get_runtime(),
                brand=brand,
                model=model,
                region=region,
                city=city,
                year_from=year_from,
                year_to=year_to,
                price_from=price_from,
                price_to=price_to,
                currency=currency,
                fuel=fuel,
                gearbox=gearbox,
                body=body,
                mileage_from=mileage_from,
                mileage_to=mileage_to,
                engine_volume_from=engine_volume_from,
                engine_volume_to=engine_volume_to,
                power_hp_from=power_hp_from,
                power_hp_to=power_hp_to,
                generation_id=generation_id,
                modification_id=modification_id,
                page=page,
                page_size=page_size,
                order_by=order_by,
            )
