from travel_planner.schemas import Travelers, TripRequest


def test_trip_request_derives_end_date_and_nights():
    request = TripRequest(
        origin="上海",
        destination="苏州",
        start_date="2026-05-01",
        days=3,
        travelers=Travelers(adults=2, children=1),
        transport_mode="rail",
    )
    assert request.end_date.isoformat() == "2026-05-03"
    assert request.days == 3
    assert request.nights == 2


def test_trip_request_rejects_invalid_budget_range():
    try:
        TripRequest(
            origin="上海",
            destination="苏州",
            start_date="2026-05-01",
            days=2,
            travelers=Travelers(adults=2),
            transport_mode="drive",
            hotel_budget_min=500,
            hotel_budget_max=300,
        )
    except ValueError as exc:
        assert "hotel_budget_min" in str(exc)
    else:
        raise AssertionError("expected budget validation error")
