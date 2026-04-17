from travel_planner.planner import TripPlanner
from travel_planner.schemas import GuideNote, HotelCandidate, PoiCandidate, TransportOption, Travelers, TripRequest


def test_planner_scores_hotels_and_builds_itinerary():
    planner = TripPlanner()
    request = TripRequest(
        origin="上海",
        destination="苏州",
        start_date="2026-05-01",
        days=3,
        travelers=Travelers(adults=2),
        transport_mode="rail",
        hotel_budget_max=600,
        must_go=["拙政园"],
    )
    result = planner.build_plan(
        request=request,
        notes=[GuideNote(title="苏州攻略", url="https://example.com", excerpt="建议住在姑苏区", pois=["拙政园"], tips=["建议早起"])],
        poi_candidates=[PoiCandidate(name="拙政园", district="姑苏区"), PoiCandidate(name="平江路", district="姑苏区")],
        hotel_candidates=[
            HotelCandidate(source="ctrip", name="平江酒店", district="姑苏区", nightly_price=520, breakfast_included=True, free_cancel=True),
            HotelCandidate(source="meituan", name="湖景酒店", district="工业园区", nightly_price=380, parking=True),
        ],
        transport_options=[TransportOption(source="12306", mode="rail", label="G7001", duration_minutes=38, price_snapshot=39.5)],
        warnings=[],
        source_evidence=[],
    )
    assert result.hotel_candidates[0].score is not None
    assert len(result.daily_itinerary) == 3
    assert "G7001" in result.summary
