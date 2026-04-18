from __future__ import annotations

import copy
import threading
from datetime import datetime
from typing import Callable

from .case_studies import get_case_study
from .config import Settings, load_settings
from .connectors import HotelConnector, MapConnector, RailConnector, XiaohongshuConnector
from .connectors.browser import BrowserSessionManager
from .database import JobRepository
from .planner import TripPlanner
from .schemas import (
    GuideNote,
    HotelCandidate,
    JobRecord,
    PoiCandidate,
    SourceEvidence,
    SourceStatus,
    TransportOption,
    TripPlanResult,
    TripRequest,
    TripShareCreateResponse,
    TripShareLink,
    TripShareSnapshot,
)


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

    def create_share(self, job_id: str) -> TripShareCreateResponse:
        job = self.repository.get_job(job_id)
        if not job.result:
            raise KeyError(job_id)
        self.repository.revoke_share_links_for_job(job_id)
        payload = self.build_share_payload(job)
        title = payload.get("title") or f"{job.request.origin} -> {job.request.destination} 行程分享"
        snapshot = self.repository.create_share_snapshot(job_id, title, payload)
        link = self.repository.create_share_link(snapshot.snapshot_id)
        return TripShareCreateResponse(
            token=link.token,
            snapshot_id=snapshot.snapshot_id,
            share_url=f"/share/{link.token}",
            excel_url=f"/share/{link.token}.xlsx",
            pdf_url=f"/share/{link.token}.pdf",
        )

    def get_share(self, token: str) -> tuple[TripShareLink, TripShareSnapshot]:
        link, snapshot = self.repository.get_share_by_token(token)
        self.repository.touch_share_access(token)
        return link, snapshot

    def revoke_share(self, token: str) -> None:
        self.repository.revoke_share_link(token)

    def export_share_payload(self, token: str) -> dict:
        _, snapshot = self.get_share(token)
        return snapshot.payload

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

    def build_share_payload(self, job: JobRecord) -> dict:
        assert job.result is not None
        result = job.result
        request = job.request
        destination = request.destination
        origin = request.origin
        route_nodes = [origin, destination]
        route_legs = self._build_share_route_legs(request, result.transport_options)
        stay_recommendations = self._build_share_stays(destination, result.hotel_candidates, result.pois)
        days = self._build_share_days(destination, result)
        case = get_case_study("yunnan-roadtrip-yibin-loop")
        return {
            "id": job.job_id,
            "title": f"{origin} -> {destination} {request.days} 天行程分享",
            "subtitle": "动态规划结果分享页",
            "date_range": f"{request.start_date.isoformat()} ~ {request.end_date.isoformat() if request.end_date else request.start_date.isoformat()}",
            "travelers": f"{request.travelers.adults} 成人，{request.travelers.children} 儿童" if request.travelers.children else f"{request.travelers.adults} 人",
            "transport_mode": "自驾" if request.transport_mode == "drive" else "铁路",
            "budget_target": f"酒店预算 ¥{request.hotel_budget_min or 0:.0f}-{request.hotel_budget_max or 0:.0f}/晚" if request.hotel_budget_max else "预算未指定",
            "summary": result.summary,
            "route_nodes": route_nodes,
            "route_legs": route_legs,
            "stay_recommendations": stay_recommendations,
            "days": days,
            "budget": {
                "hotel_total": f"约 ¥{result.budget_estimate.hotel_total:.0f}",
                "car_total": f"约 ¥{result.budget_estimate.rail_or_drive_total:.0f}",
                "meal_total": f"约 ¥{result.budget_estimate.daily_food_and_misc_total:.0f}",
                "grand_total": f"约 ¥{result.budget_estimate.grand_total:.0f}",
            },
            "warnings": result.warnings or ["当前分享页来自动态规划结果，餐饮与区位信息可能少于案例页。"],
            "route_map": self._build_share_route_map(route_nodes),
            "share_summary": {
                "city_count": len(route_nodes) - 1,
                "day_count": len(days),
                "total_km": sum(self._extract_distance_km(leg["distance"]) for leg in route_legs),
                "hardest_legs": sorted(route_legs, key=lambda item: self._leg_rank(item["intensity"]), reverse=True)[:2],
                "start": origin,
                "end": destination,
            },
            "floating_city_cards": self._build_share_floating_city_cards(stay_recommendations, days),
            "theme_hint": case.get("subtitle", ""),
        }

    def _build_share_route_legs(self, request: TripRequest, transport_options: list[TransportOption]) -> list[dict]:
        if transport_options:
            option = transport_options[0]
            distance_tag = next((tag for tag in option.tags if "km" in tag.lower()), f"约 {max(option.duration_minutes // 1, 0)} 分钟")
            return [
                {
                    "from": request.origin,
                    "to": request.destination,
                    "distance": distance_tag if "km" in distance_tag.lower() else "距离待补",
                    "drive_time": f"约 {max(option.duration_minutes // 60, 0)}h {option.duration_minutes % 60}m" if option.duration_minutes else "时长待补",
                    "intensity": self._transport_intensity(option.duration_minutes),
                    "note": option.label,
                }
            ]
        return [
            {
                "from": request.origin,
                "to": request.destination,
                "distance": "距离待补",
                "drive_time": "时长待补",
                "intensity": "中",
                "note": "当前无结构化交通结果，按动态规划摘要生成分享页。",
            }
        ]

    def _build_share_stays(self, destination: str, hotels: list[HotelCandidate], pois: list[PoiCandidate]) -> list[dict]:
        if not hotels:
            return [
                {
                    "city": destination,
                    "priority_zone": f"{destination}核心区",
                    "secondary_zone": f"{destination}次选片区",
                    "zone_reason": "当前没有抓到可用酒店结果，分享页先保留目的地核心区作为落脚建议。",
                    "student_fit": "中",
                    "hotel_candidates": [],
                    "nearby_tags": ["位置待确认", "酒店待补"],
                    "zone_map": self._fallback_zone_map(destination),
                    "zone_geo": self._fallback_zone_geo(destination),
                    "route_index": 0,
                    "anchor": destination.lower(),
                }
            ]
        primary = hotels[0]
        secondary = hotels[1] if len(hotels) > 1 else hotels[0]
        mapped_hotels = [
            {
                "name": hotel.name,
                "type": "酒店" if hotel.candidate_kind == "hotel" else "片区建议",
                "price": f"约 ¥{hotel.nightly_price:.0f}/晚" if hotel.nightly_price else "价格待补",
                "reason": hotel.why_selected or "动态规划结果里的候选住宿。",
                "source_url": hotel.booking_url or "",
            }
            for hotel in hotels[:4]
        ]
        tags = []
        if primary.parking:
            tags.append("停车友好")
        if primary.breakfast_included:
            tags.append("早餐友好")
        if pois:
            tags.append("靠近玩法区域")
        if not tags:
            tags = ["动态推荐", "位置优先"]
        zone_geo = self._build_dynamic_zone_geo(destination, primary.district or destination, secondary.district or destination)
        return [
            {
                "city": destination,
                "priority_zone": primary.district or f"{destination}核心区",
                "secondary_zone": secondary.district or f"{destination}次选片区",
                "zone_reason": f"优先按动态结果里的高分/高适配住宿片区组织；当前首选片区是 {primary.district or destination}。",
                "student_fit": "中高" if any(h.nightly_price <= 300 for h in hotels[:2]) else "中",
                "hotel_candidates": mapped_hotels,
                "nearby_tags": tags[:3],
                "zone_map": self._fallback_zone_map(destination, primary.district or destination, secondary.district or destination),
                "zone_geo": zone_geo,
                "route_index": 0,
                "anchor": destination.lower(),
            }
        ]

    def _build_share_days(self, destination: str, result: TripPlanResult) -> list[dict]:
        meals = self._build_dynamic_meals(destination, result)
        built = []
        for day in result.daily_itinerary:
            built.append(
                {
                    "day_index": day.day_index,
                    "date": day.date.isoformat(),
                    "title": day.theme,
                    "intensity": self._timeline_intensity(day),
                    "base_city": destination,
                    "priority_zone": day.lodging or f"{destination}落脚点",
                    "schedule": [day.morning, day.afternoon, day.evening],
                    "hotel_candidates": [],
                    "meals": meals if meals else [{"slot": "在地推荐", "candidates": []}],
                    "city_anchor": destination.lower(),
                    "default_expanded": False,
                }
            )
        return built

    def _build_share_route_map(self, route_nodes: list[str]) -> dict:
        coords = [self.hotels._resolve_city_coords(city) for city in route_nodes]
        width = 480
        height = 360
        padding = 38
        lats = [coord[0] for coord in coords]
        lngs = [coord[1] for coord in coords]
        min_lng, max_lng = min(lngs), max(lngs)
        min_lat, max_lat = min(lats), max(lats)
        lng_span = max(max_lng - min_lng, 0.1)
        lat_span = max(max_lat - min_lat, 0.1)
        nodes = []
        for index, city in enumerate(route_nodes):
            lat, lng = self.hotels._resolve_city_coords(city)
            x = padding + ((lng - min_lng) / lng_span) * (width - padding * 2)
            y = padding + ((max_lat - lat) / lat_span) * (height - padding * 2)
            label = city
            if index == 0:
                label = f"{city}·出发"
            elif index == len(route_nodes) - 1:
                label = f"{city}·抵达"
            nodes.append({"name": city, "label": label, "x": round(x, 1), "y": round(y, 1), "is_terminal": index in {0, len(route_nodes) - 1}})
        polyline = " ".join(f"{node['x']},{node['y']}" for node in nodes)
        segments = []
        for index in range(len(nodes) - 1):
            start = nodes[index]
            end = nodes[index + 1]
            segments.append(
                {
                    "index": index,
                    "from": start["name"],
                    "to": end["name"],
                    "points": f"{start['x']},{start['y']} {end['x']},{end['y']}",
                }
            )
        geo_nodes = []
        for index, city in enumerate(route_nodes):
            lat, lng = self.hotels._resolve_city_coords(city)
            label = city if index not in {0, len(route_nodes) - 1} else (f"{city}·出发" if index == 0 else f"{city}·抵达")
            geo_nodes.append({"name": city, "label": label, "lng": lng, "lat": lat, "is_terminal": index in {0, len(route_nodes) - 1}})
        return {"width": width, "height": height, "nodes": nodes, "polyline": polyline, "segments": segments, "geo_nodes": geo_nodes}

    def _fallback_zone_map(self, city: str, primary_label: str | None = None, secondary_label: str | None = None) -> dict:
        return {
            "width": 220,
            "height": 140,
            "primary": {"x": 72, "y": 62, "label": primary_label or "优先住区"},
            "secondary": {"x": 152, "y": 84, "label": secondary_label or "次选住区"},
            "poi": {"x": 160, "y": 48, "label": "核心点"},
            "food": {"x": 116, "y": 104, "label": "餐饮"},
            "parking": {"x": 66, "y": 92, "label": "停车"},
        }

    def _fallback_zone_geo(self, city: str, primary_label: str | None = None, secondary_label: str | None = None) -> dict:
        lat, lng = self.hotels._resolve_city_coords(city)
        return {
            "center": [lng, lat],
            "markers": [
                {"kind": "primary", "label": primary_label or "优先住区", "lng": lng - 0.012, "lat": lat + 0.008},
                {"kind": "secondary", "label": secondary_label or "次选住区", "lng": lng + 0.012, "lat": lat - 0.008},
                {"kind": "poi", "label": "核心点", "lng": lng + 0.015, "lat": lat + 0.014},
                {"kind": "food", "label": "餐饮", "lng": lng, "lat": lat - 0.012},
                {"kind": "parking", "label": "停车", "lng": lng - 0.016, "lat": lat - 0.004},
            ],
        }

    @staticmethod
    def _build_share_floating_city_cards(stays: list[dict], days: list[dict]) -> list[dict]:
        cards = []
        for stay in stays:
            preview_meals = next(
                (
                    meal["candidates"][:2]
                    for day in days
                    if day["base_city"] == stay["city"]
                    for meal in day["meals"]
                    if meal["candidates"]
                ),
                [],
            )
            cards.append(
                {
                    "city": stay["city"],
                    "anchor": stay["anchor"],
                    "priority_zone": stay["priority_zone"],
                    "student_fit": stay["student_fit"],
                    "nearby_tags": stay["nearby_tags"][:3],
                    "zone_geo": stay["zone_geo"],
                    "hotel_preview": stay["hotel_candidates"][:2],
                    "meal_preview": preview_meals,
                    "route_index": stay.get("route_index", 0),
                }
            )
        return cards

    def _build_dynamic_zone_geo(self, city: str, primary_zone: str, secondary_zone: str) -> dict:
        if not self.settings.amap_api_key:
            return self._fallback_zone_geo(city, primary_zone, secondary_zone)
        primary_result = self.map.search_places(primary_zone, city, limit=1)
        secondary_result = self.map.search_places(secondary_zone, city, limit=1)
        poi_result = self.map.search_places(f"{city} 景点", city, limit=1)
        food_result = self.map.search_places(f"{primary_zone} 美食", city, limit=1) or self.map.search_places(f"{city} 美食", city, limit=1)
        parking_result = self.map.search_places(f"{primary_zone} 停车场", city, limit=1) or self.map.search_places(f"{city} 停车场", city, limit=1)
        if not primary_result:
            return self._fallback_zone_geo(city, primary_zone, secondary_zone)
        center = [primary_result[0]["lng"], primary_result[0]["lat"]]
        markers = [
            {"kind": "primary", "label": primary_zone, "lng": primary_result[0]["lng"], "lat": primary_result[0]["lat"]},
            {"kind": "secondary", "label": secondary_zone, "lng": (secondary_result[0]["lng"] if secondary_result else center[0] + 0.01), "lat": (secondary_result[0]["lat"] if secondary_result else center[1] - 0.01)},
            {"kind": "poi", "label": poi_result[0]["name"] if poi_result else "核心点", "lng": (poi_result[0]["lng"] if poi_result else center[0] + 0.012), "lat": (poi_result[0]["lat"] if poi_result else center[1] + 0.01)},
            {"kind": "food", "label": food_result[0]["name"] if food_result else "餐饮", "lng": (food_result[0]["lng"] if food_result else center[0]), "lat": (food_result[0]["lat"] if food_result else center[1] - 0.012)},
            {"kind": "parking", "label": parking_result[0]["name"] if parking_result else "停车", "lng": (parking_result[0]["lng"] if parking_result else center[0] - 0.012), "lat": (parking_result[0]["lat"] if parking_result else center[1] - 0.006)},
        ]
        return {"center": center, "markers": markers}

    def _build_dynamic_meals(self, destination: str, result: TripPlanResult) -> list[dict]:
        meals = []
        if self.settings.amap_api_key:
            breakfast = self.map.search_places(f"{destination} 早餐", destination, limit=2)
            lunch = self.map.search_places(f"{destination} 特色菜", destination, limit=2)
            dinner = self.map.search_places(f"{destination} 火锅", destination, limit=2) or self.map.search_places(f"{destination} 晚餐", destination, limit=2)
            slot_specs = [("早餐", breakfast), ("午餐", lunch), ("晚餐", dinner)]
            for slot, places in slot_specs:
                if not places:
                    continue
                meals.append(
                    {
                        "slot": slot,
                        "candidates": [
                            {
                                "name": place["name"],
                                "source": "高德地点搜索",
                                "reason": f"{place['district']} / {place['type'] or '在地推荐'}",
                                "url": place["url"],
                            }
                            for place in places[:2]
                        ],
                    }
                )
        if meals:
            return meals
        guide_candidates = [
            {
                "name": note.title,
                "source": note.source,
                "reason": note.excerpt[:120] if note.excerpt else "攻略推荐",
                "url": note.url,
            }
            for note in result.guide_notes[:4]
        ]
        source_candidates = [
            {
                "name": evidence.title,
                "source": evidence.source,
                "reason": evidence.excerpt[:120] if evidence.excerpt else "来源证据",
                "url": evidence.url,
            }
            for evidence in result.source_evidence[:4]
        ]
        fallback = []
        if guide_candidates:
            fallback.append({"slot": "攻略推荐", "candidates": guide_candidates[:2]})
        if source_candidates:
            fallback.append({"slot": "来源推荐", "candidates": source_candidates[:2]})
        return fallback

    @staticmethod
    def _extract_distance_km(text: str) -> int:
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else 0

    @staticmethod
    def _leg_rank(intensity: str) -> int:
        return {"低": 0, "中": 1, "中高": 2, "高": 3}.get(intensity, 0)

    @staticmethod
    def _transport_intensity(duration_minutes: int) -> str:
        if duration_minutes >= 420:
            return "高"
        if duration_minutes >= 270:
            return "中高"
        if duration_minutes >= 120:
            return "中"
        return "低"

    @staticmethod
    def _timeline_intensity(day) -> str:
        text = f"{day.morning} {day.afternoon} {day.evening}"
        long_drive_tokens = ("出发", "返程", "前往", "转场", "跨区")
        if any(token in text for token in long_drive_tokens):
            if "返程" in text or "前往" in text:
                return "中高"
            return "中"
        return "低"
