"""Pydantic v2 models for AUTO.RIA API payloads.

The shared :class:`AutoRiaModel` base plus the dictionary shape ship from Phase 2.
Phase 4 adds the compact, agent-readable *response* models that the curated and
paid tools return (search, car details, average price, statistics, VIN params).

Design rule (from the project brief): RIA responses carry undocumented fields,
nulls, and mixed UK/RU/EN labels. Models therefore *ignore* extras rather than
reject them, so an upstream schema change never breaks parsing. The response
models below are deliberately *flat*: the deep nested extraction (e.g. pulling
``autoData.year`` or ``color.name``) lives in :mod:`autoria_mcp.shaping`, which
builds the flat dict each model validates.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AutoRiaModel(BaseModel):
    """Base model for every AUTO.RIA payload.

    - ``extra="allow"`` keeps undocumented fields instead of dropping/raising.
    - ``populate_by_name`` lets us alias ria's snake/camel keys to clean names.
    - ``str_strip_whitespace`` normalizes the frequently padded label strings.
    """

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class DictionaryItem(AutoRiaModel):
    """A single entry in an AUTO.RIA dictionary endpoint.

    The wire shape is ``{"name": "...", "value": <id>}`` (``value`` is the numeric
    id RIA uses in ``<option>`` dropdowns). We alias it to a clean ``id``. Some
    dictionaries (e.g. body styles) add ``parentId`` to express grouping.
    """

    id: int = Field(alias="value")
    name: str
    parent_id: int | None = Field(default=None, alias="parentId")


def parse_dictionary(raw: Any) -> list[DictionaryItem]:
    """Parse a dictionary response into a flat list of :class:`DictionaryItem`.

    Handles both the flat endpoints (``[{name, value}, ...]``) and the
    heterogeneous ``_group`` endpoints, whose arrays mix flat items with nested
    sub-arrays of items. Nested sub-arrays are flattened in place; unparsable
    entries are skipped rather than raising, matching the package's
    tolerate-upstream-drift policy.
    """
    items: list[DictionaryItem] = []
    if not isinstance(raw, list):
        return items
    for entry in raw:
        if isinstance(entry, list):
            items.extend(parse_dictionary(entry))
        elif isinstance(entry, dict):
            try:
                items.append(DictionaryItem.model_validate(entry))
            except ValueError:
                continue
    return items


# ---------------------------------------------------------------------------
# Response models — compact, agent-readable shapes returned by the tools.
# All fields are defaulted so a missing/null upstream field never raises; the
# nested extraction that fills them lives in ``autoria_mcp.shaping``.
# ---------------------------------------------------------------------------


class SearchResult(AutoRiaModel):
    """Result of ``search_used_cars``: the total match ``count`` plus the ids.

    Per the project's 1-request rule (and the Public API, which returns only ids
    + a count), search returns ids — not enriched listings. The canonical
    per-listing auto.ria.com URL comes from ``get_car_details``.
    """

    count: int = 0
    page: int = 0
    page_size: int = 0
    ids: list[str] = Field(default_factory=list)


class Condition(AutoRiaModel):
    """Seller-declared technical condition (``technicalCondition``).

    ``id`` is a 1–4 severity enum: 1 fully undamaged, 2 professionally repaired,
    3 unrepaired damage, 4 not running / for parts. ``id >= 2`` is a damage flag.
    Note: ``CarDetails.condition`` is ``None`` when the seller did **not** declare
    a condition — treat that as "unknown", not as "undamaged" (which is ``id == 1``).
    """

    id: int | None = None
    title: str | None = None
    note: str | None = None


class RiskFlags(AutoRiaModel):
    """AUTO.RIA's ``autoInfoBar`` red-flag booleans — the key due-diligence block."""

    damaged: bool | None = None
    for_parts: bool | None = None
    confiscated: bool | None = None
    under_credit: bool | None = None
    imported: bool | None = None
    needs_customs: bool | None = None


class VinVerification(AutoRiaModel):
    """Whether AUTO.RIA has any VIN/inspection verification on the listing."""

    vin_shown: bool | None = None
    has_history_report: bool | None = None
    inspection_verified: bool | None = None
    technical_checked: bool | None = None


class SellerInfo(AutoRiaModel):
    """Seller trust signal. ``type`` is ``"private"`` when no dealer is attached."""

    type: str | None = None
    name: str | None = None
    verified: bool | None = None
    reliable: bool | None = None


class PhotoLinks(AutoRiaModel):
    """A representative photo of the listing at AUTO.RIA's published sizes."""

    count: int | None = None
    b: str | None = None
    f: str | None = None
    m: str | None = None
    sx: str | None = None


class CarDetails(AutoRiaModel):
    """Compact detail for a single advert (``get_car_details``).

    Dictionary attributes are returned as both an id and a human label so the
    agent never has to reverse an opaque integer (``body_id``/``body_name``,
    ``fuel_id``/``fuel``). Engine displacement and power, which RIA only carries
    inside free-text labels, are lifted into structured numbers (``engine_volume_l``,
    ``engine_volume_class``, ``power_hp``) with the raw labels kept alongside.

    The phone is always masked upstream; the VIN is present only if the seller
    revealed it. ``url`` is the canonical auto.ria.com listing link. ``mileage_km``
    and the prices are **seller-declared and unverified**.
    """

    id: int | None = None
    title: str | None = None
    brand: str | None = None
    model: str | None = None
    price_usd: int | None = None
    price_uah: int | None = None
    price_eur: int | None = None
    year: int | None = None
    mileage_km: int | None = None
    # Display label only — merges type + volume inconsistently ("Дизель, 1.56 л."
    # / "Дизель"). For logic use `fuel_id` and `engine_volume_l`/`engine_volume_class`,
    # never this string.
    fuel: str | None = None
    fuel_id: int | None = None
    engine_volume_l: float | None = None
    engine_volume_class: float | None = None
    power_hp: int | None = None
    gearbox: str | None = None
    gearbox_id: int | None = None
    gearbox_class: str | None = None  # canonical: manual / automatic / cvt
    drive: str | None = None
    drive_id: int | None = None
    body_id: int | None = None
    body_name: str | None = None
    generation: str | None = None
    modification: str | None = None
    color: str | None = None
    city: str | None = None
    region: str | None = None
    vin: str | None = None
    phone: str | None = None
    url: str | None = None
    # Provenance / due-diligence (seller-declared unless verification says otherwise).
    condition: Condition | None = None
    risk: RiskFlags | None = None
    verification: VinVerification | None = None
    seller: SellerInfo | None = None
    photo: PhotoLinks | None = None
    is_sold: bool | None = None
    sold_date: str | None = None
    is_leasing: bool | None = None
    listed_date: str | None = None
    updated_date: str | None = None
    price_negotiable: bool | None = None  # "Торг"
    exchange_possible: bool | None = None  # "Обмін"
    description: str | None = None


class SimilarCar(AutoRiaModel):
    """One comparable listing in an average-price response."""

    id: int | None = None
    title: str | None = None
    year: int | None = None
    price_usd: str | None = None
    price_uah: str | None = None
    mileage_km: int | None = None
    fuel: str | None = None
    gearbox: str | None = None
    city: str | None = None
    url: str | None = None


class StatisticDatum(AutoRiaModel):
    """A single average-price statistic block (e.g. ``avgPriceBlock``)."""

    id: str | None = None
    name: str | None = None
    type: str | None = None
    price_uah: int | None = None
    price_usd: int | None = None


class AveragePriceResult(AutoRiaModel):
    """Point-in-time average price plus the comparable listings it derives from.

    The headline ``avg_price_*`` is **AUTO.RIA's own model-level AI estimate**, not
    a figure we recompute — and it is only weakly sensitive to tight cohort filters
    (``engine_volume``/``modification``), so it should not be read as an
    engine-precise fair value. For that, prefer ``cohort_estimate_usd`` (the median
    of the comparable listings). To make reliability legible (the API exposes no
    population distribution — only a small ``similar_cars`` sample), we add the
    sample size, the sample's own USD spread, and a ``price_consistency`` flag that
    trips when the headline falls outside the spread of the very comps it cites.
    ``status`` is ``insufficient_sample`` when the sample is too thin (< 5 comps) or
    when a tight cohort was requested yet the headline ignored it. ``cohort`` echoes
    the resolved filters.
    """

    avg_price_usd: int | None = None
    avg_price_uah: int | None = None
    # Median of the comparable listings — the cohort-appropriate figure to prefer
    # over the model-level ``avg_price_usd`` headline when a tight cohort was queried.
    cohort_estimate_usd: int | None = None
    sample_count: int = 0
    sample_min_usd: int | None = None
    sample_median_usd: int | None = None
    sample_max_usd: int | None = None
    # "ok" | "avg_below_sample" | "avg_above_sample" | None (not computable)
    price_consistency: str | None = None
    cohort: dict[str, Any] | None = None
    period: int | None = None
    status: str = "ok"  # "ok" | "no_data" | "insufficient_sample"
    quota: dict[str, int] | None = None
    similar_cars: list[SimilarCar] = Field(default_factory=list)
    statistic_data: list[StatisticDatum] = Field(default_factory=list)


class GraphPoint(AutoRiaModel):
    """One month of the average-price time series.

    ``date`` is RIA's ``"MM.YY"`` form (e.g. ``"06.25"``), not ISO; ``adv_cnt``
    is the (undocumented) advert count behind that month's average.
    """

    date: str | None = None
    adv_cnt: int | None = None
    price_uah: int | None = None
    price_usd: int | None = None


class StatisticSeries(AutoRiaModel):
    """Average price over time (``get_average_price_over_periods``)."""

    graph_data: list[GraphPoint] = Field(default_factory=list)
    period_selector: dict[str, Any] | None = None
    notice: list[dict[str, Any]] = Field(default_factory=list)
    cohort: dict[str, Any] | None = None
    period: int | None = None
    status: str = "ok"  # "ok" | "no_data"
    quota: dict[str, int] | None = None


class VinChip(AutoRiaModel):
    """A single decoded attribute ("chip") from a VIN/plate/id lookup."""

    entity: str | None = None
    id: str | None = None
    name: str | None = None


class VinParams(AutoRiaModel):
    """Decoded car parameters for ``get_params_by_vin`` (omniId in → chips out)."""

    chips: list[VinChip] = Field(default_factory=list)
    link: dict[str, Any] | None = None
    search_type: str | None = None
    notice: list[dict[str, Any]] = Field(default_factory=list)
