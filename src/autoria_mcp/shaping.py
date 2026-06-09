"""Pure response-shaping and URL helpers (no I/O).

The curated and paid tools return *compact*, agent-readable JSON: the relevant
fields lifted out of RIA's deeply nested, mixed-language payloads, plus the
mandatory ``auto.ria.com`` attribution link. All of that flattening lives here
as pure functions so it can be unit-tested without the network or the MCP layer.

:func:`listing_url` prefixes the *guaranteed* ``linkToView``/``uri`` slug that
``/auto/info`` and the paid endpoints return — the canonical per-listing deep
link. The Public API mandates no set-level attribution link and search returns
only ids + a count, so the search result carries no invented search URL.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from autoria_mcp.models import (
    AveragePriceResult,
    CarDetails,
    Condition,
    GraphPoint,
    PhotoLinks,
    RiskFlags,
    SearchResult,
    SellerInfo,
    SimilarCar,
    StatisticDatum,
    StatisticSeries,
    VinChip,
    VinParams,
    VinVerification,
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


# Engine displacement lives only inside RIA's free-text ``fuelName`` ("Дизель,
# 2 л.", "Бензин, 1.97 л.") and power only inside ``modificationName`` ("320d
# Steptronic (190 к.с.) xDrive"). Agents otherwise have to regex these out of a
# localized string, so we lift structured numbers here.
_VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*л\b")
_POWER_RE = re.compile(r"(\d+)\s*(?:к\.?\s?с|л\.?\s?с)\.?", re.IGNORECASE)


def parse_engine_volume(text: Any) -> float | None:
    """Extract litres from a label like ``"Дизель, 1.97 л."`` → ``1.97``."""
    if not isinstance(text, str):
        return None
    match = _VOLUME_RE.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def nominal_volume_class(volume: float | None) -> float | None:
    """Round a measured displacement to its nominal class (1.97 → 2.0, 1.56 → 1.6).

    RIA stores the *measured* litres inconsistently (the same 2.0 TDI appears as
    ``2``/``1.97``; a 1.6 as ``1.56``/``1.58``). The nominal class is the figure
    buyers actually filter on, so we expose both. Uses explicit half-up rounding
    (not ``round()``, whose ties-to-even + float repr give surprising results on
    ``.x5`` values, e.g. ``round(1.45, 1) == 1.4``).
    """
    if volume is None:
        return None
    return float(Decimal(str(volume)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def parse_power_hp(text: Any) -> int | None:
    """Extract horsepower from a label like ``"... (190 к.с.) xDrive"`` → ``190``."""
    if not isinstance(text, str):
        return None
    match = _POWER_RE.search(text)
    if not match:
        return None
    return int(match.group(1))


def price_to_int(value: Any) -> int | None:
    """Parse a RIA price into an int (``"7 650"`` → ``7650``; spaces/nbsp stripped)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        digits = re.sub(r"\D", "", value)
        return int(digits) if digits else None
    return None


def listing_url(link_to_view: str | None) -> str | None:
    """Prefix a relative ``linkToView``/``uri`` slug with the auto.ria.com host."""
    if not link_to_view:
        return None
    if link_to_view.startswith("http://") or link_to_view.startswith("https://"):
        return link_to_view
    return f"{AUTO_RIA}{link_to_view}"


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


def shape_search(raw: Any, *, page: int, page_size: int) -> SearchResult:
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
    )


# Sellers tag the same physical transmission inconsistently (a DCT shows up as
# Автомат / Робот / Типтронік). The canonical class lets an agent group and
# compare without losing the raw label.
_GEARBOX_CLASS: dict[str, str] = {
    "ручна / механіка": "manual",
    "автомат": "automatic",
    "типтронік": "automatic",
    "робот": "automatic",
    "варіатор": "cvt",
}


def canonical_gearbox(name: Any) -> str | None:
    """Map a RIA gearbox label to a canonical class (manual/automatic/cvt)."""
    if not isinstance(name, str):
        return None
    return _GEARBOX_CLASS.get(name.strip().casefold())


def _opt_bool(value: Any) -> bool | None:
    """Coerce RIA's mixed bool/int flags (``isLeasing: 0``) to ``bool`` or ``None``."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return None


def _condition(raw: dict[str, Any]) -> Condition | None:
    tc = raw.get("technicalCondition")
    if not isinstance(tc, dict):
        return None
    return Condition(id=tc.get("id"), title=tc.get("title"), note=tc.get("annotation"))


def _risk(raw: dict[str, Any]) -> RiskFlags | None:
    bar = raw.get("autoInfoBar")
    if not isinstance(bar, dict):
        return None
    return RiskFlags(
        damaged=bar.get("damage"),
        for_parts=bar.get("onRepairParts"),
        confiscated=bar.get("confiscatedCar"),
        under_credit=bar.get("underCredit"),
        imported=bar.get("abroad"),
        needs_customs=bar.get("custom"),
    )


def _verification(raw: dict[str, Any]) -> VinVerification:
    return VinVerification(
        vin_shown=_dig(raw, "checkedVin", "isShow"),
        has_history_report=raw.get("haveInfotechReport"),
        inspection_verified=raw.get("verifiedByInspectionCenter"),
        technical_checked=raw.get("technicalChecked"),
    )


def _clean_str(value: Any) -> str | None:
    """Trim a string, returning ``None`` for empty/blank (RIA sends ``""`` a lot)."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _seller(raw: dict[str, Any]) -> SellerInfo:
    # RIA returns a dealer object even for private sellers, with blank strings —
    # so a missing OR empty type both mean "private", never a bare "".
    dealer = raw.get("dealer")
    dealer = dealer if isinstance(dealer, dict) else {}
    return SellerInfo(
        type=_clean_str(dealer.get("type")) or "private",
        name=_clean_str(dealer.get("name")),
        verified=dealer.get("verified"),
        reliable=dealer.get("isReliable"),
    )


def _photo(raw: dict[str, Any]) -> PhotoLinks | None:
    data = raw.get("photoData")
    if not isinstance(data, dict):
        return None
    return PhotoLinks(
        count=data.get("count"),
        b=data.get("seoLinkB"),
        f=data.get("seoLinkF"),
        m=data.get("seoLinkM"),
        sx=data.get("seoLinkSX"),
    )


def shape_car_details(raw: Any) -> CarDetails:
    """Flatten a ``/auto/info`` payload into a compact :class:`CarDetails`.

    Every dictionary attribute is returned as an id **and** a human label
    (``body_id``/``body_name``, ``fuel_id``/``fuel``, ...) so an agent never has
    to reverse an opaque integer; displacement and power are lifted out of RIA's
    free-text strings into structured numbers while the raw labels are kept.

    Provenance the API carries but a bare-scalar shape would drop is surfaced
    too: ``condition`` (1–4 severity), the ``risk`` red-flag block (damaged /
    for-parts / under-credit / confiscated / imported / customs), VIN/inspection
    ``verification``, ``seller`` trust, and ``photo`` links. ``mileage_km`` and
    the prices remain **seller-declared and unverified**.
    """
    src = raw if isinstance(raw, dict) else {}
    auto = src.get("autoData")
    auto = auto if isinstance(auto, dict) else {}

    fuel_label = auto.get("fuelName")
    engine_volume_l = parse_engine_volume(fuel_label)

    return CarDetails(
        id=auto.get("autoId"),
        title=src.get("title"),
        brand=src.get("markName"),
        model=src.get("modelName"),
        price_usd=src.get("USD"),
        price_uah=src.get("UAH"),
        price_eur=src.get("EUR"),
        year=auto.get("year"),
        mileage_km=_thousands_km(auto.get("raceInt")),
        fuel=fuel_label,
        fuel_id=auto.get("fuelId"),
        engine_volume_l=engine_volume_l,
        engine_volume_class=nominal_volume_class(engine_volume_l),
        power_hp=parse_power_hp(auto.get("modificationName")),
        gearbox=auto.get("gearboxName"),
        gearbox_id=auto.get("gearBoxId"),
        gearbox_class=canonical_gearbox(auto.get("gearboxName")),
        drive=auto.get("driveName"),
        drive_id=auto.get("driveId"),
        body_id=auto.get("bodyId"),
        body_name=src.get("subCategoryName"),
        generation=auto.get("generationName"),
        modification=auto.get("modificationName"),
        color=_dig(raw, "color", "name"),
        city=_dig(raw, "stateData", "name"),
        region=_dig(raw, "stateData", "regionName"),
        vin=(src.get("VIN") or None),
        phone=_dig(raw, "userPhoneData", "phone"),
        url=listing_url(src.get("linkToView")),
        condition=_condition(src),
        risk=_risk(src),
        verification=_verification(src),
        seller=_seller(src),
        photo=_photo(src),
        is_sold=auto.get("isSold"),
        sold_date=(src.get("soldDate") or None),
        is_leasing=_opt_bool(src.get("isLeasing")),
        listed_date=src.get("addDate"),
        updated_date=src.get("updateDate"),
        price_negotiable=src.get("auctionPossible"),
        exchange_possible=src.get("exchangePossible"),
        description=auto.get("description"),
    )


def _shape_similar_car(entry: Any) -> SimilarCar:
    entry = entry if isinstance(entry, dict) else {}
    fuel_label = _dig(entry, "fuel", "name")
    return SimilarCar(
        id=entry.get("id"),
        title=entry.get("title"),
        year=entry.get("year"),
        price_usd=_dig(entry, "price", "all", "USD", "value"),
        price_uah=_dig(entry, "price", "all", "UAH", "value"),
        mileage_km=_thousands_km(entry.get("raceInt")),
        fuel=fuel_label,
        engine_volume_l=parse_engine_volume(fuel_label),
        gearbox=_dig(entry, "gearbox", "name"),
        city=_dig(entry, "location", "city", "name"),
        url=listing_url(entry.get("uri")),
    )


def _cohort_range(
    cohort: dict[str, Any] | None, key: str, cast: Callable[[Any], float]
) -> tuple[float | None, float | None]:
    """Extract a numeric ``{gte, lte}`` bound from the resolved cohort, if present."""
    block = cohort.get(key) if isinstance(cohort, dict) else None
    if not isinstance(block, dict):
        return None, None

    def _num(value: Any) -> float | None:
        try:
            return cast(value)
        except (TypeError, ValueError):
            return None

    return _num(block.get("gte")), _num(block.get("lte"))


def _within(value: float | None, lo: float | None, hi: float | None) -> bool:
    """True unless ``value`` is known and falls outside a present bound (unknown = ok)."""
    if value is None:
        return True
    if lo is not None and value < lo:
        return False
    return not (hi is not None and value > hi)


def _avg_price_block(statistic_data: list[StatisticDatum]) -> StatisticDatum | None:
    """Return RIA's headline ``avgPrice`` block from the statistic data, if any."""
    for datum in statistic_data:
        if datum.type == "avgPrice" or (datum.id or "").startswith("avgPrice"):
            return datum
    return None


# Below this many comparable listings the sample is too thin to trust as a fair
# value, regardless of how the headline lines up.
_MIN_RELIABLE_SAMPLE = 5

# Cohort keys that narrow to a specific engine/trim. AUTO.RIA's AI headline is
# model-level and does not reliably honour these, so when one is requested and the
# headline falls outside its own comps we demote the result.
_NARROWING_COHORT_KEYS = ("engineVolume", "modificationId", "generationId")


def _has_narrowing_filter(cohort: dict[str, Any] | None) -> bool:
    return cohort is not None and any(k in cohort for k in _NARROWING_COHORT_KEYS)


def shape_average_price(
    raw: Any, *, cohort: dict[str, Any] | None = None, period: int | None = None
) -> AveragePriceResult:
    """Flatten a ``/auto/ai-avarage-price/`` response and annotate its reliability.

    The headline ``avg_price_*`` is RIA's model-level AI estimate, surfaced verbatim;
    it is only weakly sensitive to tight cohort filters. The upstream ``similar_cars``
    can themselves leak the cohort, so each comp is flagged ``in_cohort`` against the
    requested year/volume bounds and ``cohort_estimate_usd`` is the median of the
    in-cohort comps only (``in_cohort_count`` reports how many qualified). The API
    exposes no population distribution, so we also add the full sample's USD spread and
    a ``price_consistency`` flag that trips when the headline sits outside that spread.
    ``status`` is demoted to ``insufficient_sample`` when fewer than
    ``_MIN_RELIABLE_SAMPLE`` comps are in-cohort or when a narrowing cohort was queried
    yet the headline ignored it. ``cohort``/``period`` echo what was actually queried.
    """
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

    avg_block = _avg_price_block(statistic_data)
    avg_price_usd = avg_block.price_usd if avg_block else None
    avg_price_uah = avg_block.price_uah if avg_block else None

    sample_usd = [p for c in similar_cars if (p := price_to_int(c.price_usd)) is not None]
    sample_min = min(sample_usd) if sample_usd else None
    sample_max = max(sample_usd) if sample_usd else None
    sample_median = round(statistics.median(sample_usd)) if sample_usd else None

    # Cohort fidelity: upstream comps can leak the requested cohort, so flag each comp
    # against the year/volume bounds and base the cohort estimate only on the matches.
    year_lo, year_hi = _cohort_range(cohort, "year", int)
    vol_lo, vol_hi = _cohort_range(cohort, "engineVolume", float)
    for car in similar_cars:
        car.in_cohort = _within(car.year, year_lo, year_hi) and _within(
            car.engine_volume_l, vol_lo, vol_hi
        )
    cohort_usd = [
        p for c in similar_cars if c.in_cohort and (p := price_to_int(c.price_usd)) is not None
    ]
    in_cohort_count = sum(1 for c in similar_cars if c.in_cohort)
    cohort_estimate = round(statistics.median(cohort_usd)) if cohort_usd else None

    price_consistency: str | None = None
    if avg_price_usd is not None and sample_min is not None and sample_max is not None:
        if avg_price_usd < sample_min:
            price_consistency = "avg_below_sample"
        elif avg_price_usd > sample_max:
            price_consistency = "avg_above_sample"
        else:
            price_consistency = "ok"

    sample_count = len(similar_cars)
    if not statistic_data and not similar_cars:
        status = "no_data"
    elif avg_price_usd is None and avg_price_uah is None:
        status = "insufficient_sample"  # comparable listings but no average estimate
    elif in_cohort_count < _MIN_RELIABLE_SAMPLE:
        status = "insufficient_sample"  # too few in-cohort comps to trust as a fair value
    elif _has_narrowing_filter(cohort) and price_consistency in {
        "avg_above_sample",
        "avg_below_sample",
    }:
        # A tight engine/trim cohort was asked for, but the model-level headline
        # sits outside its own comps — it did not honour the cohort.
        status = "insufficient_sample"
    else:
        status = "ok"

    return AveragePriceResult(
        avg_price_usd=avg_price_usd,
        avg_price_uah=avg_price_uah,
        cohort_estimate_usd=cohort_estimate,
        sample_count=sample_count,
        in_cohort_count=in_cohort_count,
        sample_min_usd=sample_min,
        sample_median_usd=sample_median,
        sample_max_usd=sample_max,
        price_consistency=price_consistency,
        cohort=cohort,
        period=period,
        status=status,
        similar_cars=similar_cars,
        statistic_data=statistic_data,
    )


def shape_statistic(
    raw: Any, *, cohort: dict[str, Any] | None = None, period: int | None = None
) -> StatisticSeries:
    """Flatten a ``/auto/statistic-avarage-price/`` response.

    ``cohort``/``period`` echo what was queried; ``status`` is ``no_data`` when
    the series came back empty so the agent can widen or inform the user.
    """
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
    period_selector = raw.get("periodSelectorData") if isinstance(raw, dict) else None
    return StatisticSeries(
        graph_data=graph_data,
        period_selector=period_selector if isinstance(period_selector, dict) else None,
        notice=notice if isinstance(notice, list) else [],
        cohort=cohort,
        period=period,
        status="ok" if graph_data else "no_data",
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
