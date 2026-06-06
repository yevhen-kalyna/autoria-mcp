"""Pure shaping/URL helpers and the raw->model shapers (no network)."""

from __future__ import annotations

from autoria_mcp.shaping import (
    AUTO_RIA,
    keep_used_autos,
    listing_url,
    shape_average_price,
    shape_car_details,
    shape_search,
    shape_statistic,
    shape_vin,
    web_search_url,
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


def test_web_search_url_uses_web_vocabulary() -> None:
    url = web_search_url({"category_id": 1, "marka_id": 9, "model_id": 3219, "state_id": 1})
    assert url.startswith(f"{AUTO_RIA}/uk/search/?")
    assert "categories.main.id=1" in url
    assert "brand.id[0]=9" in url
    assert "model.id[0]=3219" in url
    assert "region.id[0]=1" in url


def test_web_search_url_omits_absent_dimensions() -> None:
    url = web_search_url({"category_id": 1})
    assert "categories.main.id=1" in url
    assert "brand.id[0]" not in url


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
    result = shape_search(raw, page=0, page_size=10, search_url="https://x")
    assert result.count == 19679
    assert "100500" not in result.ids
    assert result.ids == ["39728975", "39837585", "39963555"]
    assert all(isinstance(i, str) for i in result.ids)
    assert result.page == 0
    assert result.page_size == 10
    assert result.search_url == "https://x"


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


def test_shape_car_details_tolerates_nulls() -> None:
    details = shape_car_details({"markName": "BMW"})
    assert details.brand == "BMW"
    assert details.year is None
    assert details.url is None
    assert details.vin is None


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
