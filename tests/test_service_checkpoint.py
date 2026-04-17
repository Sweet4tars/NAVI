from pathlib import Path

from travel_planner.database import JobRepository
from travel_planner.schemas import (
    BudgetEstimate,
    DailyPlan,
    GuideNote,
    HotelCandidate,
    PoiCandidate,
    SourceEvidence,
    SourceStatus,
    TransportOption,
    Travelers,
    TripPlanResult,
    TripRequest,
)
from travel_planner.service import PlanningService


class FakeXiaohongshu:
    def __init__(self):
        self.check_count = 0
        self.collect_count = 0

    def check_login_status(self, keyword: str):
        self.check_count += 1
        return SourceStatus(
            source="xiaohongshu",
            state="ready",
            detail="ok",
            checked_at="2026-04-16T12:00:00",
        )

    def collect(self, keyword: str):
        self.collect_count += 1
        return (
            [GuideNote(title="Guide", url="https://example.com/guide", excerpt="guide")],
            [SourceEvidence(source="xiaohongshu", title="Guide", url="https://example.com/guide", captured_at="2026-04-16T12:00:00", excerpt="guide")],
            [],
        )


class FakeHotels:
    def __init__(self):
        self.states = {"meituan": "ready", "fliggy": "awaiting_login"}
        self.calls = {"meituan": 0, "fliggy": 0}

    def hotel_sources(self):
        return ["meituan", "fliggy"]

    def collect_source(self, source: str, request: TripRequest):
        self.calls[source] += 1
        state = self.states[source]
        status = SourceStatus(
            source=source,
            state=state,
            detail=state,
            checked_at="2026-04-16T12:00:00",
        )
        if state != "ready":
            return [], [], status, [f"{source} blocked"]
        return (
            [
                HotelCandidate(
                    source=source,
                    name=f"{source}-hotel",
                    district="district",
                    nightly_price=500,
                    candidate_kind="hotel",
                    price_confidence="observed",
                )
            ],
            [SourceEvidence(source=source, title=f"{source}-hotel", url="https://example.com/hotel", captured_at="2026-04-16T12:00:00", excerpt="hotel")],
            status,
            [],
        )


class FakeRail:
    def collect(self, request: TripRequest):
        return [], [], []


class FakeMap:
    def estimate_drive(self, request: TripRequest):
        return [{"distance_km": 100, "duration_minutes": 120, "toll_fee": 20, "fuel_fee": 40}], []

    def collect_pois(self, request: TripRequest, notes):
        return [PoiCandidate(name="poi", district="district")], []


class FakePlanner:
    def build_plan(self, request, notes, poi_candidates, hotel_candidates, transport_options, warnings, source_evidence):
        return TripPlanResult(
            summary="summary",
            daily_itinerary=[
                DailyPlan(
                    day_index=1,
                    date=request.start_date,
                    theme="theme",
                    morning="morning",
                    afternoon="afternoon",
                    evening="evening",
                    lodging=hotel_candidates[0].name if hotel_candidates else "",
                )
            ],
            transport_options=transport_options,
            hotel_candidates=hotel_candidates,
            budget_estimate=BudgetEstimate(
                rail_or_drive_total=60,
                hotel_total=500,
                daily_food_and_misc_total=200,
            ),
            source_evidence=source_evidence,
            warnings=warnings,
            guide_notes=notes,
            pois=poi_candidates,
        )


def test_run_sync_uses_checkpoint_to_skip_completed_sources(tmp_path: Path):
    repo = JobRepository(tmp_path / "jobs.db")
    service = PlanningService(repository=repo)
    service.xiaohongshu = FakeXiaohongshu()
    service.hotels = FakeHotels()
    service.rail = FakeRail()
    service.map = FakeMap()
    service.planner = FakePlanner()

    request = TripRequest(
        origin="Yibin",
        destination="Kunming",
        start_date="2026-04-30",
        days=2,
        travelers=Travelers(adults=4),
        transport_mode="drive",
        hotel_budget_max=700,
    )

    checkpoint_holder = {}
    result, status, warnings, source_states = service.run_sync(
        request,
        checkpoint_callback=lambda checkpoint: checkpoint_holder.update(checkpoint),
    )
    assert status == "partial_result"
    assert service.xiaohongshu.collect_count == 1
    assert service.hotels.calls["meituan"] == 1
    assert service.hotels.calls["fliggy"] == 1
    assert checkpoint_holder["sources"]["meituan"]["completed"] is True
    assert checkpoint_holder["sources"]["fliggy"]["completed"] is False

    service.hotels.states["fliggy"] = "ready"
    result, status, warnings, source_states = service.run_sync(
        request,
        checkpoint=checkpoint_holder,
        checkpoint_callback=lambda checkpoint: checkpoint_holder.update(checkpoint),
    )
    assert status == "completed"
    assert service.xiaohongshu.collect_count == 1
    assert service.hotels.calls["meituan"] == 1
    assert service.hotels.calls["fliggy"] == 2
