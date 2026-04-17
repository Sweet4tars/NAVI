from pathlib import Path

from travel_planner.debug_tools.qunar_capture import _build_cookie_header, find_capture_candidates


def test_find_capture_candidates_prefers_list_like_payloads():
    events = [
        {
            "id": 1,
            "kind": "response",
            "url": "https://hotel.qunar.com/city/getCityUrl?cityUrl=hangzhou",
            "resource_type": "xhr",
            "status": 200,
            "response_body_preview": '{"ret": true, "data": {"newCityUrl": ""}}',
        },
        {
            "id": 2,
            "kind": "response",
            "url": "https://api.example.com/hotel/list",
            "resource_type": "fetch",
            "status": 200,
            "response_body_preview": '{"hotelName":"杭州友好饭店","priceInfo":{"price":"598"},"jumpDetailURL":"/html5/hotel/hoteldetail/346313.html"}',
        },
    ]
    ranked = find_capture_candidates(events)
    assert ranked[0]["id"] == 2
    assert ranked[0]["score"] > ranked[1]["score"]


def test_build_cookie_header_matches_domain_suffix():
    cookies = [
        {"name": "QN1", "value": "abc", "domain": ".qunar.com"},
        {"name": "OTHER", "value": "123", "domain": ".example.com"},
    ]
    header = _build_cookie_header(cookies, "https://hotel.qunar.com/global/")
    assert header == "QN1=abc"
