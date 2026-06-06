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
    """Result of ``search_used_cars``: ids + a set-level attribution URL.

    Per the project's 1-request rule, search returns only ids (not enriched
    listings). The canonical per-listing URL comes from ``get_car_details``;
    ``search_url`` is the auto.ria.com web search that reproduces this query and
    satisfies the API's mandatory attribution-link condition.
    """

    count: int = 0
    page: int = 0
    page_size: int = 0
    ids: list[str] = Field(default_factory=list)
    search_url: str = ""


class CarDetails(AutoRiaModel):
    """Compact detail for a single advert (``get_car_details``).

    The phone is always masked upstream; the VIN is present only if the seller
    revealed it. ``url`` is the canonical auto.ria.com listing link.
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
    fuel: str | None = None
    gearbox: str | None = None
    drive: str | None = None
    body_id: int | None = None
    generation: str | None = None
    modification: str | None = None
    color: str | None = None
    city: str | None = None
    region: str | None = None
    vin: str | None = None
    phone: str | None = None
    url: str | None = None


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
    """Point-in-time average price plus the comparable listings it derives from."""

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
