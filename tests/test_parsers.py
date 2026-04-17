from pathlib import Path

from travel_planner.config import load_settings
from travel_planner.connectors.browser import BrowserSessionManager
from travel_planner.connectors.hotels import HotelConnector, SITE_SPECS
from travel_planner.connectors.xiaohongshu import XiaohongshuConnector
from travel_planner.schemas import TripRequest


FIXTURES = Path(__file__).parent / "fixtures"


def test_xiaohongshu_parser_extracts_notes():
    settings = load_settings()
    connector = XiaohongshuConnector(settings, BrowserSessionManager(settings))
    notes = connector.parse_search_results((FIXTURES / "xiaohongshu_search.html").read_text(encoding="utf-8"))
    assert len(notes) >= 2
    assert "拙政园" in notes[0].excerpt
    assert "拙政园" in notes[0].pois


def test_xiaohongshu_poi_filter_skips_non_travel_places():
    settings = load_settings()
    connector = XiaohongshuConnector(settings, BrowserSessionManager(settings))
    pois = connector._extract_pois("西湖边的市民公园适合散步，但幼儿园和公司园区不算景点。")
    assert "市民公园" in pois
    assert all("幼儿园" not in poi for poi in pois)


def test_hotel_parsers_extract_per_site_cards():
    settings = load_settings()
    connector = HotelConnector(settings, BrowserSessionManager(settings))
    for source, fixture in {
        "qunar": "hotel_qunar.html",
        "fliggy": "hotel_fliggy.html",
    }.items():
        hotels = connector.parse_listing_html(
            SITE_SPECS[source],
            (FIXTURES / fixture).read_text(encoding="utf-8"),
        )
        assert hotels
        assert hotels[0].nightly_price > 0
        assert hotels[0].name


def test_ctrip_mobile_parser_extracts_hotels():
    settings = load_settings()
    connector = HotelConnector(settings, BrowserSessionManager(settings))
    request = TripRequest(
        origin="Suzhou",
        destination="Hangzhou",
        start_date="2026-05-01",
        days=2,
        travelers={"adults": 2, "children": 0},
        transport_mode="drive",
        hotel_budget_max=1200,
    )
    hotels = connector.parse_ctrip_mobile_html(
        (FIXTURES / "hotel_ctrip_mobile.html").read_text(encoding="utf-8"),
        request,
    )
    assert hotels
    assert "杭州" in hotels[0].name
    assert hotels[0].parking is True
    assert hotels[0].district
    assert hotels[0].name == "宇优溪上度假酒店(杭州西溪湿地店)"


def test_ctrip_next_data_parser_extracts_structured_price_and_district():
    settings = load_settings()
    connector = HotelConnector(settings, BrowserSessionManager(settings))
    request = TripRequest(
        origin="Suzhou",
        destination="Hangzhou",
        start_date="2026-05-01",
        days=2,
        travelers={"adults": 2, "children": 0},
        transport_mode="drive",
        hotel_budget_max=1200,
    )
    hotels = connector.parse_ctrip_mobile_html(
        (FIXTURES / "hotel_ctrip_next_data.html").read_text(encoding="utf-8"),
        request,
    )
    assert len(hotels) == 1
    assert hotels[0].name == "杭州友好饭店(西湖店)"
    assert hotels[0].district == "西湖湖滨商圈"
    assert hotels[0].nightly_price == 598
    assert hotels[0].parking is True


def test_meituan_guide_parser_extracts_price_tiers():
    settings = load_settings()
    connector = HotelConnector(settings, BrowserSessionManager(settings))
    request = TripRequest(
        origin="Suzhou",
        destination="Hangzhou",
        start_date="2026-05-01",
        days=2,
        travelers={"adults": 2, "children": 0},
        transport_mode="drive",
        hotel_budget_max=1200,
    )
    hotels = connector.parse_meituan_guide_html(
        (FIXTURES / "hotel_meituan_guide.html").read_text(encoding="utf-8"),
        request,
    )
    assert len(hotels) >= 2
    assert "Hangzhou" in hotels[0].name or "杭州" in hotels[0].name
    assert hotels[0].nightly_price > 0
    assert any(hotel.nightly_price == 360 for hotel in hotels)


def test_fliggy_city_suggest_parser_extracts_city_code():
    settings = load_settings()
    connector = HotelConnector(settings, BrowserSessionManager(settings))
    payload = {
        "msg": "Success",
        "result": [
            {
                "cityCode": 330100,
                "displayName": "杭州市",
                "suggestName": "杭州市,浙江省",
            }
        ],
    }
    city = connector.parse_fliggy_city_suggest_data(payload, "Hangzhou")
    assert city is not None
    assert city["cityCode"] == 330100


def test_qunar_city_suggest_parser_builds_region_candidates():
    settings = load_settings()
    connector = HotelConnector(settings, BrowserSessionManager(settings))
    request = TripRequest(
        origin="Suzhou",
        destination="Hangzhou",
        start_date="2026-05-01",
        days=2,
        travelers={"adults": 2, "children": 0},
        transport_mode="drive",
        hotel_budget_max=700,
    )
    payload = {
        "ret": True,
        "data": [
            {
                "cityName": "杭州",
                "hotWord": [
                    {"qname": "西湖风景名胜区", "suggestType": "poi"},
                    {"qname": "武林广场", "suggestType": "poi"},
                ],
            }
        ],
    }
    hotels = connector.parse_qunar_city_suggest_data(payload, request)
    assert len(hotels) == 2
    assert hotels[0].source == "qunar"
    assert "西湖风景名胜区" in hotels[0].name


def test_fliggy_result_text_parser_extracts_recommendations():
    settings = load_settings()
    connector = HotelConnector(settings, BrowserSessionManager(settings))
    request = TripRequest(
        origin="Suzhou",
        destination="Hangzhou",
        start_date="2026-05-01",
        days=2,
        travelers={"adults": 2, "children": 0},
        transport_mode="drive",
        hotel_budget_max=700,
    )
    text = (
        "搜索 我的订单 飞猪国际 国内酒店推荐 "
        "杭州萧山国际机场凯悦嘉轩酒店 ¥598 "
        "杭州萧山万枫酒店 ¥520 "
        "7天酒店杭州萧山机场西大门店 ¥352 "
        "位置 不限 商圈 行政区"
    )
    hotels = connector.parse_fliggy_result_text(text, request)
    assert len(hotels) == 3
    assert hotels[0].source == "fliggy"
    assert hotels[0].nightly_price == 598


def test_hotel_parser_filters_wrong_city_results():
    settings = load_settings()
    connector = HotelConnector(settings, BrowserSessionManager(settings))
    request = TripRequest(
        origin="Shanghai",
        destination="Suzhou",
        start_date="2026-05-01",
        days=2,
        travelers={"adults": 2, "children": 0},
        transport_mode="drive",
    )
    html = """
    <html><body>
      <a href="/html5/hotel/hoteldetail/1.html">
        上海外滩璞硯酒店 4.8 超棒 黄浦区 外滩 CNY 3888 免费停车
      </a>
      <a href="/html5/hotel/hoteldetail/2.html">
        苏州平江府酒店 4.6 很好 姑苏区 平江路 CNY 588 免费停车
      </a>
    </body></html>
    """
    hotels = connector.parse_ctrip_mobile_html(html, request)
    assert len(hotels) == 1
    assert "苏州" in hotels[0].name
