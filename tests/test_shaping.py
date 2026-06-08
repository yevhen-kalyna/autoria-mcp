"""Pure shaping/URL helpers and the raw->model shapers (no network)."""

from __future__ import annotations

from autoria_mcp.shaping import (
    AUTO_RIA,
    keep_used_autos,
    listing_url,
    nominal_volume_class,
    parse_engine_volume,
    parse_power_hp,
    shape_average_price,
    shape_car_details,
    shape_search,
    shape_statistic,
    shape_vin,
)
from tests.conftest import load_fixture


def test_listing_url_prefixes_relative_slug() -> None:
    assert listing_url("/auto_bmw_3_series_36756951.html") == (
        f"{AUTO_RIA}/auto_bmw_3_series_36756951.html"
    )
    assert listing_url(None) is None
    assert listing_url("") is None
    # An already-absolute URL is returned unchanged.
    assert listing_url("https://auto.ria.com/x.html") == "https://auto.ria.com/x.html"


def test_keep_used_autos_drops_offer_of_the_day() -> None:
    data = [
        {"id": "1", "type": "UsedAuto"},
        {"id": "100500", "type": "OfferOfTheDay"},
        {"id": "2", "type": "UsedAuto"},
    ]
    assert keep_used_autos(data) == ["1", "2"]
    assert keep_used_autos(None) == []


def test_shape_search_filters_and_builds_url() -> None:
    raw = load_fixture("search")
    result = shape_search(raw, page=0, page_size=10)
    assert result.count == 19679
    assert "100500" not in result.ids
    assert result.ids == ["39728975", "39837585", "39963555"]
    assert all(isinstance(i, str) for i in result.ids)
    assert result.page == 0
    assert result.page_size == 10


def test_shape_car_details_flattens_and_masks() -> None:
    details = shape_car_details(load_fixture("info"))
    assert details.id == 36756951
    assert details.brand == "BMW"
    assert details.model == "3 Series"
    assert details.price_usd == 32999
    assert details.year == 2019
    assert details.mileage_km == 140000  # raceInt 140 (thousands) -> km
    assert details.gearbox == "Автомат"
    assert details.city == "Одеса"
    assert details.region == "Одеська"
    assert details.color == "Чорний"
    assert details.vin == "WBA5V7100KFH19523"
    # Phone is always masked upstream; we pass it through unchanged.
    assert details.phone == "(xxx) xxx xx xx"
    assert details.url == f"{AUTO_RIA}/auto_bmw_3_series_36756951.html"


def test_shape_car_details_labels_and_structured_fields() -> None:
    """B + E: ids carry human labels; displacement/power are lifted from text."""
    details = shape_car_details(load_fixture("info"))
    # B: every dictionary attribute is returned as both id and label.
    assert details.body_id == 3
    assert details.body_name == "Седан"
    assert (details.fuel_id, details.fuel) == (2, "Дизель, 2 л.")
    assert (details.gearbox_id, details.gearbox) == (2, "Автомат")
    assert details.gearbox_class == "automatic"  # I: canonical taxonomy
    assert (details.drive_id, details.drive) == (1, "Повний")
    # E: structured engine volume (measured + nominal class) and power.
    assert details.engine_volume_l == 2.0
    assert details.engine_volume_class == 2.0
    assert details.power_hp == 190


def test_shape_car_details_surfaces_provenance() -> None:
    """J: condition, risk, verification, seller, photo, and flags are surfaced."""
    details = shape_car_details(load_fixture("info"))
    assert details.condition is not None and details.condition.id == 1  # undamaged
    assert details.risk is not None
    assert details.risk.damaged is False and details.risk.under_credit is False
    assert details.verification is not None
    assert details.verification.has_history_report is True
    assert details.verification.inspection_verified is False
    assert details.seller is not None
    assert details.seller.type == "Компания" and details.seller.verified is True
    assert details.photo is not None and details.photo.b is not None and details.photo.count == 125
    assert details.is_sold is False
    assert details.is_leasing is False  # isLeasing: 0
    assert details.price_negotiable is False  # auctionPossible: false ("Торг")
    assert details.exchange_possible is True  # exchangePossible: true ("Обмін")
    assert details.listed_date == "2024-07-05 11:36:06"
    assert details.description and "ДТП" in details.description


def test_shape_car_details_flags_a_wreck() -> None:
    """The damage signal that was invisible before is now front-and-centre."""
    details = shape_car_details(load_fixture("info_damaged"))
    assert details.condition is not None and details.condition.id == 3  # unrepaired damage
    assert details.risk is not None
    assert details.risk.damaged is True
    assert details.risk.under_credit is True
    assert details.risk.imported is True
    assert details.risk.needs_customs is True
    assert details.verification is not None and details.verification.has_history_report is False
    assert details.seller is not None and details.seller.type == "private"  # no dealer
    assert details.is_leasing is True  # isLeasing: 1


def test_shape_car_details_private_seller_normalizes_blanks() -> None:
    """RIA sends a dealer object with empty strings for private sellers -> 'private'."""
    details = shape_car_details(
        {"markName": "BMW", "dealer": {"type": "", "name": "  ", "verified": False}}
    )
    assert details.seller is not None
    assert details.seller.type == "private"  # not a bare ""
    assert details.seller.name is None


def test_shape_car_details_tolerates_nulls() -> None:
    details = shape_car_details({"markName": "BMW"})
    assert details.brand == "BMW"
    assert details.year is None
    assert details.url is None
    assert details.vin is None
    assert details.body_name is None
    assert details.engine_volume_l is None
    assert details.power_hp is None


def test_parse_engine_volume_handles_formatting() -> None:
    assert parse_engine_volume("Дизель, 2 л.") == 2.0
    assert parse_engine_volume("Бензин, 1.97 л.") == 1.97
    assert parse_engine_volume("Бензин, 3,99 л.") == 3.99  # comma decimal
    assert parse_engine_volume("Електро") is None
    assert parse_engine_volume(None) is None


def test_nominal_volume_class_rounds_to_buyer_figure() -> None:
    assert nominal_volume_class(1.97) == 2.0
    assert nominal_volume_class(1.56) == 1.6
    assert nominal_volume_class(1.46) == 1.5
    assert nominal_volume_class(None) is None


def test_parse_power_hp_extracts_horsepower() -> None:
    assert parse_power_hp("320d Steptronic (190 к.с.) xDrive") == 190
    assert parse_power_hp("4.0 TFSI S tronic (450 к.с.)") == 450
    assert parse_power_hp("no power here") is None
    assert parse_power_hp(None) is None


def test_shape_average_price() -> None:
    result = shape_average_price(load_fixture("ai_average_price_params"))
    assert len(result.similar_cars) == 1
    car = result.similar_cars[0]
    assert car.id == 34731946
    assert car.price_usd == "7 650"
    assert car.mileage_km == 233000
    assert car.city == "Рівне"
    assert car.url == f"{AUTO_RIA}/auto_renault_megane_34731946.html"
    assert result.statistic_data[0].price_usd == 7415


def test_shape_average_price_reliability_metadata() -> None:
    """G + ISSUE-9: surface sample size/spread and flag avg-vs-comps inconsistency."""
    result = shape_average_price(
        load_fixture("ai_average_price_params"), cohort={"brandId": "62"}, period=365
    )
    assert result.avg_price_usd == 7415  # AUTO.RIA's AI headline
    assert result.sample_count == 1
    assert result.sample_min_usd == result.sample_median_usd == result.sample_max_usd == 7650
    # Headline ($7,415) sits below the only comp it cites ($7,650) — the exact
    # contradiction agents otherwise present as authoritative.
    assert result.price_consistency == "avg_below_sample"
    assert result.cohort == {"brandId": "62"}
    assert result.period == 365
    assert result.status == "ok"


def test_shape_average_price_empty_is_no_data() -> None:
    """ISSUE-10: an empty result is explicitly labelled, not silently blank."""
    result = shape_average_price({"similarCars": [], "statisticData": []})
    assert result.status == "no_data"
    assert result.sample_count == 0
    assert result.avg_price_usd is None
    assert result.price_consistency is None


def test_shape_statistic() -> None:
    series = shape_statistic(load_fixture("statistic"))
    assert len(series.graph_data) == 3
    assert series.graph_data[0].date == "06.25"
    assert series.graph_data[0].adv_cnt == 4665
    assert series.graph_data[0].price_usd == 4160
    assert series.period_selector is not None
    assert series.notice[0]["noticeType"] == "success"


def test_shape_vin() -> None:
    params = shape_vin(load_fixture("vin_params"))
    assert params.search_type == "VIN"
    assert len(params.chips) == 9
    assert params.chips[1].entity == "brandId"
    assert params.chips[1].name == "Skoda"
    assert params.link is not None
    assert "auto.ria.com" in params.link["url"]
