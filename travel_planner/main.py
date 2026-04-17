from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import PACKAGE_ROOT, load_settings
from .schemas import TripRequest, Travelers
from .service import PlanningService


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title=settings.app_name)
    app.state.service = PlanningService(settings=settings)
    app.mount("/static", StaticFiles(directory=str(PACKAGE_ROOT / "static")), name="static")
    templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))

    def service(request: Request) -> PlanningService:
        return request.app.state.service

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(request, "index.html", {"request": request, "today": datetime.now().date().isoformat()})

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: str):
        return templates.TemplateResponse(request, "job.html", {"request": request, "job_id": job_id})

    @app.get("/results/{job_id}", response_class=HTMLResponse)
    def result_page(request: Request, job_id: str):
        job = service(request).get_job(job_id)
        return templates.TemplateResponse(request, "result.html", {"request": request, "job": job})

    @app.post("/plan", response_class=HTMLResponse)
    def create_plan_from_form(
        request: Request,
        origin: str = Form(...),
        destination: str = Form(...),
        start_date: str = Form(...),
        end_date: str | None = Form(None),
        days: int | None = Form(None),
        adults: int = Form(2),
        children: int = Form(0),
        transport_mode: str = Form(...),
        hotel_budget_min: float | None = Form(None),
        hotel_budget_max: float | None = Form(None),
        hotel_star_level: int | None = Form(None),
        pace: str = Form("balanced"),
        must_go: str = Form(""),
        avoid: str = Form(""),
        hotel_preferences: str = Form(""),
        parking_required: bool = Form(False),
    ):
        payload = TripRequest(
            origin=origin,
            destination=destination,
            start_date=start_date,
            end_date=end_date or None,
            days=days,
            travelers=Travelers(adults=adults, children=children),
            transport_mode=transport_mode,
            hotel_budget_min=hotel_budget_min,
            hotel_budget_max=hotel_budget_max,
            hotel_star_level=hotel_star_level,
            pace=pace,
            must_go=must_go,
            avoid=avoid,
            hotel_preferences=hotel_preferences,
            parking_required=parking_required,
        )
        job = service(request).submit_job(payload)
        return RedirectResponse(url=f"/jobs/{job.job_id}", status_code=303)

    @app.post("/api/trips/plan")
    def create_plan(request: Request, payload: TripRequest):
        job = service(request).submit_job(payload)
        return {"job_id": job.job_id, "status": job.status}

    @app.get("/api/jobs/{job_id}")
    def get_job(request: Request, job_id: str):
        try:
            job = service(request).get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return job.model_dump(mode="json")

    @app.get("/api/trips/{job_id}")
    def get_result(request: Request, job_id: str):
        try:
            job = service(request).get_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return {"job_id": job.job_id, "status": job.status, "result": job.result.model_dump(mode="json") if job.result else None}

    @app.get("/api/sources/status")
    def get_source_status(request: Request):
        return {"sources": [status.model_dump(mode="json") for status in service(request).list_source_statuses()]}

    @app.post("/api/sources/{source}/recheck")
    def recheck_source(request: Request, source: str):
        try:
            status = service(request).recheck_source(source)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="source not found") from exc
        return status.model_dump(mode="json")

    @app.post("/api/jobs/{job_id}/resume")
    def resume_job(request: Request, job_id: str):
        try:
            job = service(request).resume_job(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        return {"job_id": job.job_id, "status": job.status, "progress": job.progress}

    @app.post("/api/jobs/{job_id}/sources/{source}/recheck")
    def recheck_job_source(request: Request, job_id: str, source: str):
        try:
            payload = service(request).recheck_job_source(job_id, source)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job or source not found") from exc
        return payload

    return app


app = create_app()
