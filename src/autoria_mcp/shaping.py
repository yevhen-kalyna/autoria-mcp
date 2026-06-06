"""Pure response-shaping and URL helpers (no I/O).

The curated and paid tools return *compact*, agent-readable JSON: the relevant
fields lifted out of RIA's deeply nested, mixed-language payloads, plus the
mandatory ``auto.ria.com`` attribution link. All of that flattening lives here
as pure functions so it can be unit-tested without the network or the MCP layer.

Two URL forms, both deliberate:
  * :func:`listing_url` — prefixes the *guaranteed* ``linkToView``/``uri`` slug
    that ``/auto/info`` and the paid endpoints return. This is the canonical
    per-listing deep link.
  * :func:`web_search_url` — reconstructs the auto.ria.com web *search* URL from
    the resolved query (the web param vocabulary, mirroring the VIN endpoint's
    ``link.url``). Search returns only ids, so this set-level link is how the
    search tool satisfies the attribution requirement; it is always valid even
    when only some filters are mappable.
"""

from __future__ import annotations

from typing import Any

from autoria_mcp.models import (
    AveragePriceResult,
    CarDetails,
    GraphPoint,
    SearchResult,
    SimilarCar,
    StatisticDatum,
    StatisticSeries,
    VinChip,
    VinParams,
)

AUTO_RIA = "https://auto.ria.com"
# The promotional "Offer of the Day" advert RIA injects into search data[]. It is
# not a normal used-car listing and must be filtered out of curated results.
OFFER_OF_THE_DAY_ID = "100500"


def _dig(obj: Any, *path: str) -> Any:
    """Walk a chain of dict keys, returning ``None`` on any missing/!dict hop."""
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _thousands_km(race_int: Any) -> int | None:
    """RIA reports mileage in thousands of km (``raceInt=140`` → 140 000 km)."""
    if isinstance(race_int, bool) or not isinstance(race_int, int):
        return None
    return race_int * 1000


def listing_url(link_to_view: str | None) -> str | None:
    """Prefix a relative ``linkToView``/``uri`` slug with the auto.ria.com host."""
    if not link_to_view:
        return None
    if link_to_view.startswith("http://") or link_to_view.startswith("https://"):
        return link_to_view
    return f"{AUTO_RIA}{link_to_view}"


def web_search_url(resolved: dict[str, Any]) -> str:
    """Build the canonical auto.ria.com web *search* URL from resolved IDs.

    Uses the web param vocabulary (``categories.main.id``, ``brand.id[0]``,
    ``model.id[0]``, ``region.id[0]``) seen in the VIN endpoint's ``link.url``.
    Only the dimensions that map cleanly are included; the result is always a
    valid auto.ria.com search link (so it satisfies attribution) even if finer
    filters (price/year/mileage) are applied via the API but not mirrored here.
    """
    parts = ["indexName=auto,order_auto,newauto_search"]
    category_id = resolved.get("category_id")
    if category_id is not None:
        parts.append(f"categories.main.id={category_id}")
    marka_id = resolved.get("marka_id")
    if marka_id is not None:
        parts.append(f"brand.id[0]={marka_id}")
    model_id = resolved.get("model_id")
    if model_id is not None:
        parts.append(f"model.id[0]={model_id}")
    state_id = resolved.get("state_id")
    if state_id is not None:
        parts.append(f"region.id[0]={state_id}")
    return f"{AUTO_RIA}/uk/search/?{'&'.join(parts)}"


def keep_used_autos(data: Any) -> list[str]:
    """Return the ids of genuine used-car entries from a search ``data[]`` array.

    Keeping only ``type == "UsedAuto"`` inherently drops the ``OfferOfTheDay``
    promo (id ``100500``) and any new-auto entries.
    """
    if not isinstance(data, list):
        return []
    ids: list[str] = []
    for entry in data:
        if not isinstance(entry, dict) or entry.get("type") != "UsedAuto":
            continue
        entry_id = entry.get("id")
        # Belt-and-suspenders: exclude the promo id even if it ever arrives typed
        # as a UsedAuto (today it carries type "OfferOfTheDay").
        if entry_id is not None and str(entry_id) != OFFER_OF_THE_DAY_ID:
            ids.append(str(entry_id))
    return ids


def cleaned_params(raw: Any) -> dict[str, Any]:
    """Return the echoed ``result.additional.search_params.cleaned`` map.

    AUTO.RIA echoes the filters it actually applied here. An empty/missing
    ``marka_id`` after a brand was requested is the V1 silent-ignore foot-gun
    (V3 param names return the whole site at HTTP 200), so callers sanity-check
    this before trusting the result.
    """
    cleaned = _dig(raw, "result", "additional", "search_params", "cleaned")
    return cleaned if isinstance(cleaned, dict) else {}


def shape_search(raw: Any, *, page: int, page_size: int, search_url: str) -> SearchResult:
    """Flatten a ``/auto/search`` response into a :class:`SearchResult`."""
    result = raw.get("result") if isinstance(raw, dict) else None
    result = result if isinstance(result, dict) else {}

    common = result.get("search_result_common")
    common = common if isinstance(common, dict) else {}
    search_result = result.get("search_result")
    search_result = search_result if isinstance(search_result, dict) else {}

    data = common.get("data")
    if isinstance(data, list) and data:
        ids = keep_used_autos(data)
    else:
        raw_ids = search_result.get("ids")
        ids = [
            str(i)
            for i in (raw_ids if isinstance(raw_ids, list) else [])
            if str(i) != OFFER_OF_THE_DAY_ID
        ]

    count = search_result.get("count")
    if not isinstance(count, int):
        count = common.get("count")
    count_int = count if isinstance(count, int) else 0

    return SearchResult(
        count=count_int,
        page=page,
        page_size=page_size,
        ids=ids,
        search_url=search_url,
    )


def shape_car_details(raw: Any) -> CarDetails:
    """Flatten a ``/auto/info`` payload into a compact :class:`CarDetails`."""
    auto = raw.get("autoData") if isinstance(raw, dict) else None
    auto = auto if isinstance(auto, dict) else {}

    return CarDetails(
        id=auto.get("autoId"),
        title=raw.get("title") if isinstance(raw, dict) else None,
        brand=raw.get("markName") if isinstance(raw, dict) else None,
        model=raw.get("modelName") if isinstance(raw, dict) else None,
        price_usd=raw.get("USD") if isinstance(raw, dict) else None,
        price_uah=raw.get("UAH") if isinstance(raw, dict) else None,
        price_eur=raw.get("EUR") if isinstance(raw, dict) else None,
        year=auto.get("year"),
        mileage_km=_thousands_km(auto.get("raceInt")),
        fuel=auto.get("fuelName"),
        gearbox=auto.get("gearboxName"),
        drive=auto.get("driveName"),
        body_id=auto.get("bodyId"),
        generation=auto.get("generationName"),
        modification=auto.get("modificationName"),
        color=_dig(raw, "color", "name"),
        city=_dig(raw, "stateData", "name"),
        region=_dig(raw, "stateData", "regionName"),
        vin=(raw.get("VIN") or None) if isinstance(raw, dict) else None,
        phone=_dig(raw, "userPhoneData", "phone"),
        url=listing_url(raw.get("linkToView") if isinstance(raw, dict) else None),
    )


def _shape_similar_car(entry: Any) -> SimilarCar:
    entry = entry if isinstance(entry, dict) else {}
    return SimilarCar(
        id=entry.get("id"),
        title=entry.get("title"),
        year=entry.get("year"),
        price_usd=_dig(entry, "price", "all", "USD", "value"),
        price_uah=_dig(entry, "price", "all", "UAH", "value"),
        mileage_km=_thousands_km(entry.get("raceInt")),
        fuel=_dig(entry, "fuel", "name"),
        gearbox=_dig(entry, "gearbox", "name"),
        city=_dig(entry, "location", "city", "name"),
        url=listing_url(entry.get("uri")),
    )


def shape_average_price(raw: Any) -> AveragePriceResult:
    """Flatten a ``/auto/ai-avarage-price/`` response."""
    similar = raw.get("similarCars") if isinstance(raw, dict) else None
    stats = raw.get("statisticData") if isinstance(raw, dict) else None

    similar_cars = [_shape_similar_car(c) for c in (similar if isinstance(similar, list) else [])]
    statistic_data = [
        StatisticDatum(
            id=s.get("id"),
            name=s.get("name"),
            type=s.get("type"),
            price_uah=_dig(s, "price", "UAH"),
            price_usd=_dig(s, "price", "USD"),
        )
        for s in (stats if isinstance(stats, list) else [])
        if isinstance(s, dict)
    ]
    return AveragePriceResult(similar_cars=similar_cars, statistic_data=statistic_data)


def shape_statistic(raw: Any) -> StatisticSeries:
    """Flatten a ``/auto/statistic-avarage-price/`` response."""
    graph = raw.get("graphData") if isinstance(raw, dict) else None
    graph_data = [
        GraphPoint(
            date=g.get("date"),
            adv_cnt=g.get("advCnt"),
            price_uah=_dig(g, "price", "UAH"),
            price_usd=_dig(g, "price", "USD"),
        )
        for g in (graph if isinstance(graph, list) else [])
        if isinstance(g, dict)
    ]
    notice = raw.get("noticeData") if isinstance(raw, dict) else None
    period = raw.get("periodSelectorData") if isinstance(raw, dict) else None
    return StatisticSeries(
        graph_data=graph_data,
        period_selector=period if isinstance(period, dict) else None,
        notice=notice if isinstance(notice, list) else [],
    )


def shape_vin(raw: Any) -> VinParams:
    """Flatten a ``/auto/params/by/vin-code/`` response into decoded chips."""
    chips_raw = _dig(raw, "chipsData", "chips")
    chips = [
        VinChip(entity=c.get("entity"), id=c.get("id"), name=c.get("name"))
        for c in (chips_raw if isinstance(chips_raw, list) else [])
        if isinstance(c, dict)
    ]
    link = _dig(raw, "chipsData", "link")
    notice = raw.get("noticeData") if isinstance(raw, dict) else None
    return VinParams(
        chips=chips,
        link=link if isinstance(link, dict) else None,
        search_type=raw.get("searchType") if isinstance(raw, dict) else None,
        notice=notice if isinstance(notice, list) else [],
    )
