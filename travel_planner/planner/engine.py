from __future__ import annotations

from datetime import timedelta

from ..schemas import BudgetEstimate, DailyPlan, GuideNote, HotelCandidate, PoiCandidate, TransportOption, TripPlanResult, TripRequest
from ..utils import clamp


class TripPlanner:
    def score_hotels(self, request: TripRequest, hotels: list[HotelCandidate], poi_candidates: list[PoiCandidate]) -> list[HotelCandidate]:
        if not hotels:
            return []
        target_budget = request.hotel_budget_max or max(hotel.nightly_price for hotel in hotels)
        core_districts = {poi.district for poi in poi_candidates if poi.district}
        for hotel in hotels:
            budget_score = 1 - abs(hotel.nightly_price - target_budget) / max(target_budget, 1)
            location_score = 0.95 if hotel.district in core_districts else 0.7 if hotel.district else 0.55
            amenity_score = 0.0
            if hotel.breakfast_included:
                amenity_score += 0.4
            if hotel.free_cancel:
                amenity_score += 0.3
            if request.parking_required and hotel.parking:
                amenity_score += 0.3
            elif not request.parking_required:
                amenity_score += 0.2
            experience_score = min((hotel.rating or 4.2) / 5, 1.0)
            hotel.score = round(
                clamp(
                    budget_score * 0.35
                    + location_score * 0.30
                    + amenity_score * 0.15
                    + experience_score * 0.20,
                    0,
                    1,
                )
                * 100,
                1,
            )
            hotel.why_selected = self._describe_hotel_reason(hotel, request)
        return sorted(hotels, key=lambda item: (-(item.score or 0), item.nightly_price))

    def build_plan(
        self,
        request: TripRequest,
        notes: list[GuideNote],
        poi_candidates: list[PoiCandidate],
        hotel_candidates: list[HotelCandidate],
        transport_options: list[TransportOption],
        warnings: list[str],
        source_evidence,
    ) -> TripPlanResult:
        scored_hotels = self.score_hotels(request, hotel_candidates, poi_candidates)
        display_hotels = self._select_display_hotels(scored_hotels, limit=3)
        itinerary = self._make_itinerary(request, poi_candidates, scored_hotels, transport_options)
        budget = self._build_budget(request, display_hotels, transport_options)
        summary = self._build_summary(request, display_hotels, transport_options, notes, warnings)
        return TripPlanResult(
            summary=summary,
            daily_itinerary=itinerary,
            transport_options=transport_options[:6],
            hotel_candidates=display_hotels,
            budget_estimate=budget,
            source_evidence=source_evidence,
            warnings=warnings,
            guide_notes=notes[:6],
            pois=poi_candidates[:8],
        )

    def _make_itinerary(
        self,
        request: TripRequest,
        poi_candidates: list[PoiCandidate],
        hotels: list[HotelCandidate],
        transport_options: list[TransportOption],
    ) -> list[DailyPlan]:
        dates = [request.start_date + timedelta(days=offset) for offset in range(request.days or 1)]
        top_hotel = hotels[0].name if hotels else "\u5f85\u5b9a\u9152\u5e97"
        transport = transport_options[0].label if transport_options else ("\u81ea\u9a7e" if request.transport_mode == "drive" else "\u5f85\u8865\u4ea4\u901a")
        queue = poi_candidates[:]
        itinerary: list[DailyPlan] = []
        for index, trip_date in enumerate(dates, start=1):
            if index == 1:
                first_poi = queue.pop(0).name if queue else f"{request.destination}\u8001\u57ce\u533a"
                morning = f"\u4ece{request.origin}\u51fa\u53d1\uff0c\u4e58\u5750{transport}\u524d\u5f80{request.destination}\uff0c\u62b5\u8fbe\u540e\u529e\u7406\u5165\u4f4f\u3002"
                afternoon = f"\u8f7b\u91cf\u901b {first_poi}\uff0c\u4f18\u5148\u719f\u6089\u7247\u533a\u548c\u4ea4\u901a\u52a8\u7ebf\u3002"
                evening = "\u5728\u9152\u5e97\u5468\u8fb9\u5b89\u6392\u665a\u9910\u4e0e\u6563\u6b65\uff0c\u907f\u514d\u9996\u65e5\u8de8\u533a\u79fb\u52a8\u8d85\u8fc7 90 \u5206\u949f\u3002"
                theme = "\u5230\u8fbe\u4e0e\u6696\u573a"
            elif index == len(dates):
                last_poi = queue.pop(0).name if queue else f"{request.destination}\u57ce\u5e02\u6b65\u884c\u8857"
                morning = f"\u5728\u9152\u5e97\u9644\u8fd1\u6216 {last_poi} \u5b89\u6392\u6536\u5c3e\u6d3b\u52a8\uff0c\u65b9\u4fbf\u56de\u7a0b\u3002"
                afternoon = f"\u9884\u7559\u6253\u5305\u4e0e\u8fd4\u7a0b\u65f6\u95f4\uff0c\u6309 {transport} \u8282\u70b9\u8fd4\u56de{request.origin}\u3002"
                evening = "\u82e5\u8fd4\u7a0b\u8f83\u665a\uff0c\u53ef\u8865\u4e00\u987f\u672c\u5730\u7279\u8272\u9910\u540e\u7ed3\u675f\u884c\u7a0b\u3002"
                theme = "\u6536\u675f\u4e0e\u8fd4\u7a0b"
            else:
                first = queue.pop(0).name if queue else f"{request.destination}\u6587\u5316\u5730\u6807"
                second = queue.pop(0).name if queue else f"{request.destination}\u81ea\u7136\u666f\u89c2"
                morning = f"\u4e0a\u5348\u6e38\u73a9 {first}\uff0c\u4f18\u5148\u5b89\u6392\u70ed\u95e8\u666f\u70b9\u3002"
                afternoon = f"\u4e0b\u5348\u8f6c\u573a\u81f3 {second}\uff0c\u4fdd\u6301\u5355\u6b21\u8de8\u533a\u79fb\u52a8\u5728 90 \u5206\u949f\u5185\u3002"
                evening = "\u56de\u5230\u6838\u5fc3\u7247\u533a\u7528\u9910\uff0c\u9884\u7559\u81ea\u7531\u6d3b\u52a8\u4e0e\u4f11\u606f\u65f6\u95f4\u3002"
                theme = "\u6838\u5fc3\u6e38\u89c8"
            itinerary.append(
                DailyPlan(
                    day_index=index,
                    date=trip_date,
                    theme=theme,
                    morning=morning,
                    afternoon=afternoon,
                    evening=evening,
                    lodging=top_hotel,
                )
            )
        return itinerary

    def _build_budget(self, request: TripRequest, hotels: list[HotelCandidate], transport: list[TransportOption]) -> BudgetEstimate:
        priced_hotel = next((hotel for hotel in hotels if hotel.candidate_kind == "hotel"), None)
        hotel_total = (priced_hotel.nightly_price * request.nights) if priced_hotel else 0
        if request.transport_mode == "rail":
            travel_total = (transport[0].price_snapshot or 0) * request.travelers.adults if transport else 0
        else:
            travel_total = transport[0].price_snapshot or 0 if transport else 0
        daily_misc = (request.days or 1) * (180 * request.travelers.adults + 90 * request.travelers.children)
        return BudgetEstimate(
            rail_or_drive_total=round(travel_total, 2),
            hotel_total=round(hotel_total, 2),
            daily_food_and_misc_total=round(daily_misc, 2),
        )

    def _build_summary(
        self,
        request: TripRequest,
        hotels: list[HotelCandidate],
        transport: list[TransportOption],
        notes: list[GuideNote],
        warnings: list[str],
    ) -> str:
        preferred_hotel = next((hotel for hotel in hotels if hotel.candidate_kind == "hotel"), hotels[0] if hotels else None)
        hotel_line = preferred_hotel.name if preferred_hotel else "\u9152\u5e97\u5f85\u8865"
        transport_line = transport[0].label if transport else ("\u81ea\u9a7e\u65b9\u6848" if request.transport_mode == "drive" else "\u4ea4\u901a\u5f85\u8865")
        note_line = notes[0].title if notes else "\u672a\u6293\u5230\u653b\u7565\uff0c\u6309 POI \u89c4\u5219\u751f\u6210"
        suffix = "\uff1b\u90e8\u5206\u6570\u636e\u6e90\u9700\u8981\u4f60\u8865\u767b\u5f55\u540e\u53ef\u518d\u6b21\u5237\u65b0" if warnings else ""
        return (
            f"{request.origin} \u5230 {request.destination} \u7684 {request.days} \u5929\u884c\u7a0b\u5df2\u751f\u6210\u3002"
            f"\u4f18\u5148\u4ea4\u901a\u4e3a {transport_line}\uff0c\u4f4f\u5bbf\u5efa\u8bae\u9996\u9009 {hotel_line}\uff0c\u653b\u7565\u4fa7\u91cd\u70b9\u53c2\u8003\u201c{note_line}\u201d{suffix}\u3002"
        )

    def _describe_hotel_reason(self, hotel: HotelCandidate, request: TripRequest) -> str:
        reasons = [f"\u00a5{hotel.nightly_price:.0f}/\u665a"]
        if hotel.district:
            reasons.append(f"\u4f4d\u4e8e{hotel.district}")
        if hotel.candidate_kind == "strategy":
            reasons.append("\u4f4f\u5bbf\u7b56\u7565\u5efa\u8bae")
        if hotel.candidate_kind == "region_hint":
            reasons.append("\u70ed\u95e8\u7247\u533a\u63d0\u793a")
        if "price-hidden" in hotel.tags:
            reasons.append("\u767b\u5f55\u540e\u53ef\u80fd\u770b\u5230\u66f4\u4f4e\u4ef7")
        elif hotel.price_confidence == "estimated":
            reasons.append("\u4ef7\u683c\u4e3a\u4f30\u7b97")
        if hotel.breakfast_included:
            reasons.append("\u542b\u65e9\u9910")
        if hotel.free_cancel:
            reasons.append("\u53ef\u514d\u8d39\u53d6\u6d88")
        if request.parking_required and hotel.parking:
            reasons.append("\u652f\u6301\u505c\u8f66")
        return "\uff0c".join(reasons)

    def _select_display_hotels(self, hotels: list[HotelCandidate], limit: int) -> list[HotelCandidate]:
        if len(hotels) <= limit:
            return hotels[:limit]
        def priority(hotel: HotelCandidate) -> tuple[int, float]:
            kind_rank = {
                "hotel": 0,
                "strategy": 1,
                "region_hint": 2,
            }.get(hotel.candidate_kind, 3)
            source_rank = {
                "ctrip": 0,
                "fliggy": 1,
                "meituan": 2,
                "qunar": 3,
            }.get(hotel.source, 9)
            return (kind_rank, source_rank, -(hotel.score or 0))

        ranked = sorted(hotels, key=priority)
        selected: list[HotelCandidate] = []
        seen_sources: set[str] = set()

        for hotel in ranked:
            if hotel.source in seen_sources:
                continue
            selected.append(hotel)
            seen_sources.add(hotel.source)
            if len(selected) == limit:
                return selected

        for hotel in ranked:
            if hotel in selected:
                continue
            selected.append(hotel)
            if len(selected) == limit:
                break
        return selected
