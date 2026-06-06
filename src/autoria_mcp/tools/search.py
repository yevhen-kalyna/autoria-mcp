"""The curated ``search_used_cars`` tool.

Takes human-friendly inputs (brand/model/region names, year/price/mileage
ranges), resolves them to AUTO.RIA's **V1** numeric wire params via the shared
dictionary resolver, and makes exactly **one** ``/auto/search`` call. It returns
ids only (no auto-enrichment) plus a set-level attribution ``search_url``; the
agent drills into a specific id with ``get_car_details``.

Two verified foot-guns are handled here:
  * **V1-only vocabulary.** ``/auto/search`` honors V1 names (``marka_id``,
    ``bodystyle``, ``type`` for fuel, ...); V3 names are silently ignored and the
    endpoint returns the entire site. After the call we sanity-check the echoed
    ``cleaned.marka_id`` whenever a brand was requested.
  * **OfferOfTheDay.** RIA injects a promo advert (id ``100500``) into the
    results; we keep only ``type == "UsedAuto"`` entries.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from autoria_mcp.cache import make_cache_key
from autoria_mcp.client import AutoRiaError
from autoria_mcp.models import SearchResult
from autoria_mcp.runtime import RuntimeContext, get_runtime
from autoria_mcp.shaping import cleaned_params, shape_search, web_search_url
from autoria_mcp.tools._errors import tool_errors

# v1 search is passenger-cars only; category 1 scopes the category-specific
# dictionaries (body styles, gearboxes) the resolver consults.
_CATEGORY_ID = 1
# Search currency codes are NOT the V3 codes: 1=USD, 2=EUR, 3=UAH.
_CURRENCY: dict[str, int] = {"USD": 1, "EUR": 2, "UAH": 3}

Currency = Literal["USD", "EUR", "UAH"]
SEARCH_PATH = "/auto/search"


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
    page: int = 0,
    page_size: int = 10,
    order_by: int = 0,
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

    marka_id = await rt.resolver.brand_id(brand) if brand else None
    model_id = await rt.resolver.model_id(brand, model) if (brand and model) else None
    state_id = await rt.resolver.region_id(region) if region else None
    city_id = await rt.resolver.city_id(region, city) if (region and city) else None
    fuel_id = await rt.resolver.fuel_id(fuel) if fuel else None
    gearbox_id = await rt.resolver.gearbox_id(gearbox) if gearbox else None
    body_id = await rt.resolver.body_id(body) if body else None

    wire: dict[str, Any] = {
        "category_id": _CATEGORY_ID,
        "searchType": 1,
        "countpage": page_size,
        "page": page,
        "order_by": order_by,
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
    page: int = 0,
    page_size: int = 10,
    order_by: int = 0,
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

    return shape_search(raw, page=page, page_size=page_size, search_url=web_search_url(resolved))


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
        page: Annotated[int, Field(default=0, ge=0, description="0-based page number.")] = 0,
        page_size: Annotated[
            int, Field(default=10, ge=1, le=100, description="Results per page (1-100).")
        ] = 10,
        order_by: Annotated[
            int,
            Field(
                default=0,
                description=(
                    "Sort: 0 relevance, 2 price asc, 3 price desc, 5 year newest, "
                    "6 year oldest, 7 date newest, 8 date oldest, 12 mileage desc, "
                    "13 mileage asc."
                ),
            ),
        ] = 0,
    ) -> SearchResult:
        """Search AUTO.RIA used-car listings (passenger cars) by friendly inputs.

        Resolves brand/model/region/city/fuel/gearbox/body **names** to AUTO.RIA
        ids for you, then makes a single search call. Returns the total match
        `count`, the current `page`/`page_size`, the matching advert `ids` (used
        cars only — the OfferOfTheDay promo is filtered out), and a `search_url`
        that reproduces the query on auto.ria.com (the canonical attribution
        link). To get a specific listing's details and its own URL, pass an id to
        `get_car_details`.

        Notes:
          * Mileage is in **km** (e.g. `mileage_to=150000`).
          * `model` requires `brand`; `city` requires `region`.
          * v1 supports a single brand+model+year block. For multi-brand or
            advanced raw queries use the `raw_search` tool.

        Example: `search_used_cars(brand="BMW", model="3 Series", year_from=2018,
        price_to=30000, currency="USD", gearbox="Автомат", order_by=2)`.
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
                page=page,
                page_size=page_size,
                order_by=order_by,
            )
