from datetime import datetime

from fastapi.testclient import TestClient

from travel_planner.main import create_app
from travel_planner.schemas import JobRecord, SourceStatus, Travelers, TripRequest


class FakeService:
    def submit_job(self, request: TripRequest):
        return JobRecord(
            job_id="job-1",
            status="completed",
            request=request,
            created_at=datetime(2026, 4, 16, 12, 0, 0),
            updated_at=datetime(2026, 4, 16, 12, 0, 1),
            progress=100,
        )

    def get_job(self, job_id: str):
        return JobRecord(
            job_id=job_id,
            status="completed",
            request=TripRequest(
                origin="上海",
                destination="苏州",
                start_date="2026-05-01",
                days=3,
                travelers=Travelers(adults=2),
                transport_mode="rail",
            ),
            created_at=datetime(2026, 4, 16, 12, 0, 0),
            updated_at=datetime(2026, 4, 16, 12, 0, 1),
            progress=100,
        )

    def list_source_statuses(self):
        return [
            SourceStatus(
                source="xiaohongshu",
                state="ready",
                detail="ok",
                checked_at=datetime(2026, 4, 16, 12, 0, 0),
            )
        ]

    def recheck_source(self, source: str):
        return SourceStatus(
            source=source,
            state="ready",
            detail="ok",
            checked_at=datetime(2026, 4, 16, 12, 0, 0),
        )

    def resume_job(self, job_id: str):
        return JobRecord(
            job_id=job_id,
            status="collecting",
            request=TripRequest(
                origin="Shanghai",
                destination="Suzhou",
                start_date="2026-05-01",
                days=3,
                travelers=Travelers(adults=2),
                transport_mode="rail",
            ),
            created_at=datetime(2026, 4, 16, 12, 0, 0),
            updated_at=datetime(2026, 4, 16, 12, 0, 2),
            progress=0,
        )

    def recheck_job_source(self, job_id: str, source: str):
        return {
            "job_id": job_id,
            "source": source,
            "status": {
                "source": source,
                "state": "ready",
                "detail": "ok",
                "checked_at": "2026-04-16T12:00:00",
            },
            "resumed": True,
            "job_status": "collecting",
        }


def test_api_plan_submission():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.post(
        "/api/trips/plan",
        json={
            "origin": "上海",
            "destination": "苏州",
            "start_date": "2026-05-01",
            "days": 3,
            "travelers": {"adults": 2, "children": 0},
            "transport_mode": "rail",
        },
    )
    assert response.status_code == 200
    assert response.json()["job_id"] == "job-1"


def test_source_status_endpoint():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.get("/api/sources/status")
    assert response.status_code == 200
    assert response.json()["sources"][0]["source"] == "xiaohongshu"


def test_resume_job_endpoint():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.post("/api/jobs/job-1/resume")
    assert response.status_code == 200
    assert response.json()["status"] == "collecting"


def test_job_source_recheck_endpoint():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.post("/api/jobs/job-1/sources/fliggy/recheck")
    assert response.status_code == 200
    assert response.json()["resumed"] is True
    assert response.json()["source"] == "fliggy"


def test_index_page_renders():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Domestic Trip Planner" in response.text
