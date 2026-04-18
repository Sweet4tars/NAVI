from datetime import datetime

from fastapi.testclient import TestClient

from travel_planner.case_studies import get_case_study
from travel_planner.main import create_app
from travel_planner.schemas import JobRecord, SourceStatus, Travelers, TripRequest, TripShareCreateResponse, TripShareLink, TripShareSnapshot


class FakeService:
    def __init__(self):
        self.case = get_case_study("yunnan-roadtrip-yibin-loop")
        self.revoked_tokens: list[str] = []

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

    def create_share(self, job_id: str):
        return TripShareCreateResponse(
            token="share-token-1",
            snapshot_id="snapshot-1",
            share_url="/share/share-token-1",
            excel_url="/share/share-token-1.xlsx",
            pdf_url="/share/share-token-1.pdf",
        )

    def get_share(self, token: str):
        return (
            TripShareLink(
                token=token,
                snapshot_id="snapshot-1",
                created_at=datetime(2026, 4, 16, 12, 0, 0),
            ),
            TripShareSnapshot(
                snapshot_id="snapshot-1",
                job_id="job-1",
                title=self.case["title"],
                payload=self.case,
                created_at=datetime(2026, 4, 16, 12, 0, 0),
            ),
        )

    def export_share_payload(self, token: str):
        return self.case

    def revoke_share(self, token: str):
        self.revoked_tokens.append(token)


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


def test_create_share_endpoint():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.post("/api/trips/job-1/share", json={"visibility": "token"})
    assert response.status_code == 200
    assert response.json()["share_url"] == "/share/share-token-1"
    assert response.json()["pdf_url"] == "/share/share-token-1.pdf"
    assert response.json()["local_share_url"] == "http://testserver/share/share-token-1"


def test_revoke_share_endpoint():
    app = create_app()
    fake = FakeService()
    app.state.service = fake
    client = TestClient(app)
    response = client.delete("/api/shares/share-token-1")
    assert response.status_code == 200
    assert response.json()["revoked"] is True
    assert fake.revoked_tokens == ["share-token-1"]


def test_public_base_url_endpoint(monkeypatch):
    import travel_planner.main as main_module

    app = create_app()
    app.state.service = FakeService()
    monkeypatch.setattr(main_module, "get_public_base_url", lambda settings: "")
    client = TestClient(app)
    response = client.get("/api/share/public-base-url")
    assert response.status_code == 200
    assert response.json()["public_base_url"] is None


def test_index_page_renders():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Open Source Travel Agent" in response.text
    assert "prepublish_check.py" in response.text


def test_case_study_visual_page_renders():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.get("/case-studies/yunnan-roadtrip")
    assert response.status_code == 200
    assert "宜宾集合" in response.text
    assert "city-accordion" in response.text
    assert "share-stage-map-shell" in response.text


def test_case_study_share_page_renders():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.get("/share/case-studies/yunnan-roadtrip")
    assert response.status_code == 200
    assert "Readonly Share" in response.text
    assert "city-amap" in response.text
    assert "share-summary-card" in response.text


def test_case_study_share_excel_downloads():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.get("/share/case-studies/yunnan-roadtrip.xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_generic_case_routes_work():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.get("/case-studies/yunnan-roadtrip-yibin-loop")
    assert response.status_code == 200
    excel = client.get("/share/case-studies/yunnan-roadtrip-yibin-loop.xlsx")
    assert excel.status_code == 200


def test_unknown_case_route_returns_404():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.get("/share/case-studies/not-found.xlsx")
    assert response.status_code == 404


def test_dynamic_share_page_renders():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.get("/share/share-token-1")
    assert response.status_code == 200
    assert "share-stage-map-shell" in response.text
    assert "city-accordion" in response.text


def test_dynamic_share_excel_downloads():
    app = create_app()
    app.state.service = FakeService()
    client = TestClient(app)
    response = client.get("/share/share-token-1.xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def test_dynamic_share_pdf_downloads(monkeypatch, tmp_path):
    app = create_app()
    app.state.service = FakeService()
    pdf_file = tmp_path / "share.pdf"

    def fake_render(url, output_path):
        pdf_file.write_bytes(b"%PDF-1.4 fake")
        return pdf_file

    monkeypatch.setattr("travel_planner.main.render_url_pdf", fake_render)
    client = TestClient(app)
    response = client.get("/share/share-token-1.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
