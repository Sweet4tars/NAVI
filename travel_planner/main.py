from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .case_exports import export_case_study_excel
from .case_studies import get_case_study, list_case_study_ids
from .config import PACKAGE_ROOT, load_settings
from .pdf_exports import render_url_pdf
from .share_public import build_external_url, get_public_base_url
from .schemas import TripRequest, TripShareCreateRequest, Travelers
from .service import PlanningService


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title=settings.app_name)
    app.state.service = PlanningService(settings=settings)
    app.mount("/static", StaticFiles(directory=str(PACKAGE_ROOT / "static")), name="static")
    templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))

    def service(request: Request) -> PlanningService:
        return request.app.state.service

    def case_excel_file(case_id: str, filename: str) -> Path:
        if case_id not in list_case_study_ids():
            raise HTTPException(status_code=404, detail="case study not found")
        export_dir = settings.data_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        output_path = export_dir / filename
        export_case_study_excel(case_id, output_path)
        return output_path

    def case_filename(case_id: str) -> str:
        if case_id == "yunnan-roadtrip-yibin-loop":
            return "yunnan-roadtrip-yibin-assembly-2026-04-30_to_2026-05-05.xlsx"
        return f"{case_id}.xlsx"

    def local_base_url(request: Request) -> str:
        return str(request.base_url).rstrip("/")

    def enrich_share_response(request: Request, share_payload: dict) -> dict:
        payload = dict(share_payload)
        local_base = local_base_url(request)
        public_base = get_public_base_url(settings)
        payload["local_share_url"] = build_external_url(local_base, payload["share_url"])
        payload["local_excel_url"] = build_external_url(local_base, payload["excel_url"])
        payload["local_pdf_url"] = build_external_url(local_base, payload["pdf_url"])
        payload["public_base_url"] = public_base or None
        if public_base:
            payload["public_share_url"] = build_external_url(public_base, payload["share_url"])
            payload["public_excel_url"] = build_external_url(public_base, payload["excel_url"])
            payload["public_pdf_url"] = build_external_url(public_base, payload["pdf_url"])
        return payload

    def render_case_page(request: Request, case_id: str, *, share_mode: bool) -> HTMLResponse:
        if case_id not in list_case_study_ids():
            raise HTTPException(status_code=404, detail="case study not found")
        case = get_case_study(case_id)
        public_slug = "yunnan-roadtrip" if case_id == "yunnan-roadtrip-yibin-loop" else case_id
        return templates.TemplateResponse(
            request,
            "case_study_yunnan.html",
            {
                "request": request,
                "title": f"{case['title']} · 分享页" if share_mode else case["title"],
                "case": case,
                "share_mode": share_mode,
                "share_href": f"/share/case-studies/{public_slug}",
                "excel_href": f"/share/case-studies/{public_slug}.xlsx" if share_mode else f"/case-studies/{public_slug}.xlsx",
                "amap_js_api_key": settings.amap_js_api_key,
                "amap_security_js_code": settings.amap_security_js_code,
                "has_amap_frontend_map": bool(settings.amap_js_api_key),
                "public_base_url": get_public_base_url(settings),
            },
        )

    def render_share_payload(request: Request, payload: dict, *, share_mode: bool, share_href: str, excel_href: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "case_study_yunnan.html",
            {
                "request": request,
                "title": payload["title"],
                "case": payload,
                "share_mode": share_mode,
                "share_href": share_href,
                "excel_href": excel_href,
                "amap_js_api_key": settings.amap_js_api_key,
                "amap_security_js_code": settings.amap_security_js_code,
                "has_amap_frontend_map": bool(settings.amap_js_api_key),
                "public_base_url": get_public_base_url(settings),
            },
        )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(request, "index.html", {"request": request, "today": datetime.now().date().isoformat()})

    @app.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: str):
        return templates.TemplateResponse(request, "job.html", {"request": request, "job_id": job_id})

    @app.get("/results/{job_id}", response_class=HTMLResponse)
    def result_page(request: Request, job_id: str):
        job = service(request).get_job(job_id)
        return templates.TemplateResponse(
            request,
            "result.html",
            {"request": request, "job": job, "public_base_url": get_public_base_url(settings)},
        )

    @app.get("/case-studies/yunnan-roadtrip", response_class=HTMLResponse)
    def case_study_yunnan(request: Request):
        return render_case_page(request, "yunnan-roadtrip-yibin-loop", share_mode=False)

    @app.get("/case-studies/yunnan-roadtrip.xlsx")
    def case_study_yunnan_excel():
        output_path = case_excel_file(
            "yunnan-roadtrip-yibin-loop",
            "yunnan-roadtrip-yibin-assembly-2026-04-30_to_2026-05-05.xlsx",
        )
        return FileResponse(
            path=output_path,
            filename=output_path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/case-studies/{case_id}.xlsx")
    def case_study_excel(case_id: str):
        output_path = case_excel_file(case_id, case_filename(case_id))
        return FileResponse(
            path=output_path,
            filename=output_path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/case-studies/{case_id}", response_class=HTMLResponse)
    def case_study_page(request: Request, case_id: str):
        return render_case_page(request, case_id, share_mode=False)

    @app.get("/share/case-studies/yunnan-roadtrip", response_class=HTMLResponse)
    def share_case_study_yunnan(request: Request):
        return render_case_page(request, "yunnan-roadtrip-yibin-loop", share_mode=True)

    @app.get("/share/case-studies/yunnan-roadtrip.xlsx")
    def share_case_study_yunnan_excel():
        output_path = case_excel_file(
            "yunnan-roadtrip-yibin-loop",
            "yunnan-roadtrip-yibin-assembly-2026-04-30_to_2026-05-05.xlsx",
        )
        return FileResponse(
            path=output_path,
            filename=output_path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/share/case-studies/{case_id}.xlsx")
    def share_case_study_excel(case_id: str):
        output_path = case_excel_file(case_id, case_filename(case_id))
        return FileResponse(
            path=output_path,
            filename=output_path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/share/case-studies/{case_id}", response_class=HTMLResponse)
    def share_case_study_page(request: Request, case_id: str):
        return render_case_page(request, case_id, share_mode=True)

    @app.post("/api/trips/{job_id}/share")
    def create_trip_share(request: Request, job_id: str, payload: TripShareCreateRequest):
        del payload  # token-only for now
        try:
            share = service(request).create_share(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job result not found") from exc
        return enrich_share_response(request, share.model_dump(mode="json"))

    @app.delete("/api/shares/{token}")
    def revoke_trip_share(request: Request, token: str):
        try:
            service(request).revoke_share(token)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="share not found") from exc
        return {"token": token, "revoked": True}

    @app.get("/api/share/public-base-url")
    def share_public_base_url():
        return {"public_base_url": get_public_base_url(settings) or None}

    @app.get("/share/{token}.xlsx")
    def share_snapshot_excel(request: Request, token: str):
        try:
            payload = service(request).export_share_payload(token)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="share not found") from exc
        export_dir = settings.data_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        output_path = export_dir / f"share-{token}.xlsx"
        from .case_exports import export_share_payload_excel
        export_share_payload_excel(payload, output_path)
        return FileResponse(
            path=output_path,
            filename=output_path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/share/{token}.pdf")
    def share_snapshot_pdf(request: Request, token: str):
        try:
            service(request).get_share(token)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="share not found") from exc
        export_dir = settings.data_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        output_path = export_dir / f"share-{token}.pdf"
        share_url = str(request.url_for("share_snapshot_page", token=token))
        output_path = render_url_pdf(share_url, output_path)
        return FileResponse(path=output_path, filename=output_path.name, media_type="application/pdf")

    @app.get("/share/{token}", response_class=HTMLResponse)
    def share_snapshot_page(request: Request, token: str):
        try:
            _, snapshot = service(request).get_share(token)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="share not found") from exc
        return render_share_payload(
            request,
            snapshot.payload,
            share_mode=True,
            share_href=f"/share/{token}",
            excel_href=f"/share/{token}.xlsx",
        )

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
