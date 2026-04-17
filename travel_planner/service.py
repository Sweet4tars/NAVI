from __future__ import annotations

import copy
import threading
from datetime import datetime
from typing import Callable

from .config import Settings, load_settings
from .connectors import HotelConnector, MapConnector, RailConnector, XiaohongshuConnector
from .connectors.browser import BrowserSessionManager
from .database import JobRepository
from .planner import TripPlanner
from .schemas import GuideNote, HotelCandidate, JobRecord, PoiCandidate, SourceEvidence, SourceStatus, TransportOption, TripPlanResult, TripRequest


ProgressCallback = Callable[[int, dict[str, SourceStatus] | None, list[str] | None], None]
CheckpointCallback = Callable[[dict], None]


class PlanningService:
    def __init__(self, settings: Settings | None = None, repository: JobRepository | None = None):
        self.settings = settings or load_settings()
        self.repository = repository or JobRepository(self.settings.db_path)
        self.browser_manager = BrowserSessionManager(self.settings)
        self.xiaohongshu = XiaohongshuConnector(self.settings, self.browser_manager)
        self.rail = RailConnector(self.settings)
        self.map = MapConnector(self.settings)
        self.hotels = HotelConnector(self.settings, self.browser_manager)
        self.planner = TripPlanner()

    def submit_job(self, request: TripRequest) -> JobRecord:
        job = self.repository.create_job(request)
        thread = threading.Thread(target=self._run_job, args=(job.job_id,), daemon=True)
        thread.start()
        return job

    def resume_job(self, job_id: str) -> JobRecord:
        job = self.repository.get_job(job_id)
        if job.status == "collecting":
            return job
        self.repository.update_job(
            job_id,
            status="collecting",
            progress=0,
            warnings=job.warnings,
            source_statuses=job.source_statuses,
            error="",
        )
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.repository.get_job(job_id)

    def _run_job(self, job_id: str) -> None:
        job = self.repository.get_job(job_id)

        def emit(
            progress: int,
            source_states: dict[str, SourceStatus] | None = None,
            warnings: list[str] | None = None,
            checkpoint: dict | None = None,
        ) -> None:
            self.repository.update_job(
                job_id,
                status="collecting",
                progress=progress,
                source_statuses=source_states,
                warnings=warnings,
                checkpoint=checkpoint,
            )

        try:
            emit(5, checkpoint=job.checkpoint)
            result, status, warnings, source_states = self.run_sync(
                job.request,
                persist_sources=True,
                progress_callback=lambda progress, source_states=None, warnings=None: emit(progress, source_states, warnings),
                checkpoint=job.checkpoint,
                checkpoint_callback=lambda checkpoint: self.repository.update_job(job_id, checkpoint=checkpoint),
            )
            self.repository.update_job(
                job_id,
                status=status,
                progress=100,
                result=result,
                warnings=warnings,
                source_statuses=source_states,
                checkpoint={},
            )
        except Exception as exc:
            self.repository.update_job(job_id, status="failed", progress=100, error=str(exc))

    def run_sync(
        self,
        request: TripRequest,
        *,
        persist_sources: bool = False,
        progress_callback: ProgressCallback | None = None,
        checkpoint: dict | None = None,
        checkpoint_callback: CheckpointCallback | None = None,
    ) -> tuple[TripPlanResult, str, list[str], dict[str, SourceStatus]]:
        checkpoint = copy.deepcopy(checkpoint or {})
        checkpoint.setdefault("sources", {})
        warnings: list[str] = []
        source_states: dict[str, SourceStatus] = {}

        notes = []
        note_evidence = []
        xhs_key = "xiaohongshu"
        xhs_checkpoint = checkpoint["sources"].get(xhs_key, {})
        if xhs_checkpoint.get("completed"):
            notes = self._restore_models(xhs_checkpoint.get("notes", []), GuideNote)
            note_evidence = self._restore_models(xhs_checkpoint.get("evidence", []), SourceEvidence)
            note_warnings = list(xhs_checkpoint.get("warnings", []))
            warnings.extend(note_warnings)
            xhs_status = SourceStatus.model_validate(xhs_checkpoint["status"])
        else:
            xhs_status = self.xiaohongshu.check_login_status(f"{request.destination} travel guide")
            note_warnings = []
            if xhs_status.state == "ready":
                notes, note_evidence, note_warnings = self.xiaohongshu.collect(f"{request.destination} {request.days} day itinerary")
                warnings.extend(note_warnings)
            else:
                warnings.append("Xiaohongshu needs a one-time browser login before guide scraping can continue.")
            checkpoint["sources"][xhs_key] = {
                "completed": xhs_status.state == "ready",
                "status": xhs_status.model_dump(mode="json"),
                "notes": self._dump_models(notes),
                "evidence": self._dump_models(note_evidence),
                "warnings": note_warnings if xhs_status.state == "ready" else [warnings[-1]],
            }
            self._persist_checkpoint(checkpoint_callback, checkpoint)
        source_states[xhs_status.source] = xhs_status
        self._emit(progress_callback, 30, source_states, warnings)

        hotel_candidates: list[HotelCandidate] = []
        hotel_evidence: list[SourceEvidence] = []
        for source in self.hotels.hotel_sources():
            source_checkpoint = checkpoint["sources"].get(source, {})
            if source_checkpoint.get("completed"):
                hotel_candidates.extend(self._restore_models(source_checkpoint.get("candidates", []), HotelCandidate))
                hotel_evidence.extend(self._restore_models(source_checkpoint.get("evidence", []), SourceEvidence))
                warnings.extend(source_checkpoint.get("warnings", []))
                source_states[source] = SourceStatus.model_validate(source_checkpoint["status"])
                continue
            source_hotels, source_evidence, source_status, source_warnings = self.hotels.collect_source(source, request)
            hotel_candidates.extend(source_hotels)
            hotel_evidence.extend(source_evidence)
            warnings.extend(source_warnings)
            source_states[source] = source_status
            checkpoint["sources"][source] = {
                "completed": source_status.state == "ready",
                "status": source_status.model_dump(mode="json"),
                "candidates": self._dump_models(source_hotels),
                "evidence": self._dump_models(source_evidence),
                "warnings": source_warnings,
            }
            self._persist_checkpoint(checkpoint_callback, checkpoint)
        self._emit(progress_callback, 55, source_states, warnings)

        transport_options: list[TransportOption] = []
        transport_evidence = []
        transport_checkpoint = checkpoint.get("transport", {})
        if transport_checkpoint.get("completed"):
            transport_options = self._restore_models(transport_checkpoint.get("options", []), TransportOption)
            transport_evidence = self._restore_models(transport_checkpoint.get("evidence", []), SourceEvidence)
            warnings.extend(transport_checkpoint.get("warnings", []))
        else:
            transport_warnings: list[str] = []
            if request.transport_mode == "rail":
                transport_options, transport_evidence, rail_warnings = self.rail.collect(request)
                transport_warnings.extend(rail_warnings)
                warnings.extend(rail_warnings)
            else:
                drives, drive_warnings = self.map.estimate_drive(request)
                warnings.extend(drive_warnings)
                transport_warnings.extend(drive_warnings)
                for drive in drives:
                    transport_options.append(
                        TransportOption(
                            source="amap" if self.settings.amap_api_key else "heuristic-drive",
                            mode="drive",
                            label=f"Drive {request.origin} -> {request.destination}",
                            duration_minutes=int(drive["duration_minutes"]),
                            price_snapshot=round(float(drive["toll_fee"]) + float(drive["fuel_fee"]), 2),
                            tags=[
                                f"{drive['distance_km']}km",
                                f"Toll CNY {float(drive['toll_fee']):.0f}",
                                f"Fuel CNY {float(drive['fuel_fee']):.0f}",
                            ],
                        )
                    )
            checkpoint["transport"] = {
                "completed": True,
                "options": self._dump_models(transport_options),
                "evidence": self._dump_models(transport_evidence),
                "warnings": transport_warnings,
            }
            self._persist_checkpoint(checkpoint_callback, checkpoint)
        self._emit(progress_callback, 75, source_states, warnings)

        poi_candidates: list[PoiCandidate] = []
        poi_checkpoint = checkpoint.get("poi", {})
        if poi_checkpoint.get("completed"):
            poi_candidates = self._restore_models(poi_checkpoint.get("candidates", []), PoiCandidate)
            warnings.extend(poi_checkpoint.get("warnings", []))
        else:
            poi_candidates, poi_warnings = self.map.collect_pois(request, notes)
            warnings.extend(poi_warnings)
            checkpoint["poi"] = {
                "completed": True,
                "candidates": self._dump_models(poi_candidates),
                "warnings": poi_warnings,
            }
            self._persist_checkpoint(checkpoint_callback, checkpoint)
        self._emit(progress_callback, 88, source_states, warnings)

        result = self.planner.build_plan(
            request=request,
            notes=notes,
            poi_candidates=poi_candidates,
            hotel_candidates=hotel_candidates,
            transport_options=transport_options,
            warnings=warnings,
            source_evidence=note_evidence + hotel_evidence + transport_evidence,
        )
        self._emit(progress_callback, 95, source_states, warnings)

        if persist_sources:
            for status in source_states.values():
                self.repository.upsert_source_status(status)

        final_status = "completed"
        if any(not stage.get("completed") for stage in checkpoint.get("sources", {}).values()):
            final_status = "partial_result"
        if not transport_options and request.transport_mode == "rail":
            final_status = "partial_result"
        return result, final_status, warnings, source_states

    def get_job(self, job_id: str) -> JobRecord:
        return self.repository.get_job(job_id)

    def list_source_statuses(self) -> list[SourceStatus]:
        statuses = self.repository.list_source_statuses()
        if statuses:
            return statuses
        timestamp = datetime.now().replace(microsecond=0)
        return [
            SourceStatus(source="xiaohongshu", state="unknown", detail="Not checked yet.", checked_at=timestamp),
            SourceStatus(source="meituan", state="unknown", detail="Not checked yet.", checked_at=timestamp),
            SourceStatus(source="ctrip", state="unknown", detail="Not checked yet.", checked_at=timestamp),
            SourceStatus(source="fliggy", state="unknown", detail="Not checked yet.", checked_at=timestamp),
        ]

    def recheck_source(self, source: str, request: TripRequest | None = None) -> SourceStatus:
        seed_request = request or TripRequest(
            origin="Shanghai",
            destination="Suzhou",
            start_date=datetime.now().date(),
            days=2,
            travelers={"adults": 2, "children": 0},
            transport_mode="rail",
        )
        if source == "xiaohongshu":
            status = self.xiaohongshu.check_login_status(f"{seed_request.destination} travel guide")
        elif source in {"meituan", "ctrip", "fliggy"}:
            status = self.hotels.check_login_status(source, seed_request)
        else:
            raise KeyError(source)
        self.repository.upsert_source_status(status)
        return status

    def recheck_job_source(self, job_id: str, source: str) -> dict[str, object]:
        job = self.repository.get_job(job_id)
        status = self.recheck_source(source, job.request)
        resumed = False
        if status.state == "ready" and job.status != "collecting":
            self.resume_job(job_id)
            resumed = True
        return {
            "job_id": job_id,
            "source": source,
            "status": status.model_dump(mode="json"),
            "resumed": resumed,
            "job_status": self.repository.get_job(job_id).status,
        }

    @staticmethod
    def _emit(
        callback: ProgressCallback | None,
        progress: int,
        source_states: dict[str, SourceStatus],
        warnings: list[str],
    ) -> None:
        if callback:
            callback(progress, dict(source_states), list(warnings))

    @staticmethod
    def _dump_models(models: list) -> list[dict]:
        return [model.model_dump(mode="json") for model in models]

    @staticmethod
    def _restore_models(items: list[dict], model_cls):
        return [model_cls.model_validate(item) for item in items]

    @staticmethod
    def _persist_checkpoint(callback: CheckpointCallback | None, checkpoint: dict) -> None:
        if callback:
            callback(checkpoint)
