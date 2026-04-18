from __future__ import annotations

import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import Settings
from ..schemas import GuideNote, PoiCandidate, TripRequest


class MapConnector:
    name = "amap"

    def __init__(self, settings: Settings):
        self.settings = settings

    def collect_pois(self, request: TripRequest, notes: list[GuideNote]) -> tuple[list[PoiCandidate], list[str]]:
        pois: list[PoiCandidate] = []
        warnings: list[str] = []
        names = request.must_go[:]
        for note in notes:
            names.extend(note.pois)
        if not names:
            names = [f"{request.destination}老城区", f"{request.destination}博物馆", f"{request.destination}步行街"]
        unique: list[str] = []
        for name in names:
            cleaned = name.strip()
            if cleaned and cleaned not in unique:
                unique.append(cleaned)
        if self.settings.amap_api_key:
            for name in unique[:8]:
                poi = self._search_poi(name, request.destination)
                if poi:
                    pois.append(poi)
        if not pois:
            pois = [self._heuristic_poi(name, request.destination, index) for index, name in enumerate(unique[:8])]
            if not self.settings.amap_api_key:
                warnings.append("未配置高德 Key，已使用启发式 POI。")
        return pois, warnings

    def estimate_drive(self, request: TripRequest) -> tuple[list[dict[str, float | int]], list[str]]:
        if self.settings.amap_api_key:
            try:
                result = self._driving_route(request.origin, request.destination)
                if result:
                    return [result], []
            except Exception as exc:
                return [], [f"地图自驾路线查询失败: {exc}"]
        text = f"{request.origin}-{request.destination}"
        pseudo_distance = max(len(re.sub(r"\s+", "", text)) * 36, 120)
        duration_minutes = int(pseudo_distance * 0.95)
        toll = round(pseudo_distance * 0.42, 2)
        fuel = round(pseudo_distance * 7.5 / 100 * 8.2, 2)
        return [
            {
                "distance_km": pseudo_distance,
                "duration_minutes": duration_minutes,
                "toll_fee": toll,
                "fuel_fee": fuel,
            }
        ], ["未配置高德 Key，已使用启发式自驾成本。"]

    def search_places(self, keyword: str, city: str = "", *, limit: int = 5) -> list[dict]:
        if not self.settings.amap_api_key:
            return []
        params = urlencode(
            {
                "key": self.settings.amap_api_key,
                "keywords": keyword,
                "city": city,
                "citylimit": "true" if city else "false",
                "offset": str(limit),
                "extensions": "base",
            }
        )
        request = Request(f"https://restapi.amap.com/v3/place/text?{params}", headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        places: list[dict] = []
        for poi in payload.get("pois") or []:
            location = poi.get("location", "")
            lng = 0.0
            lat = 0.0
            if "," in location:
                lng_text, lat_text = location.split(",", 1)
                lng = float(lng_text)
                lat = float(lat_text)
            name = poi.get("name") or keyword
            places.append(
                {
                    "name": name,
                    "address": poi.get("address", ""),
                    "district": poi.get("adname") or city,
                    "type": poi.get("type", ""),
                    "lng": lng,
                    "lat": lat,
                    "url": self._amap_marker_url(name, lng, lat),
                }
            )
        return places

    def geocode_keyword(self, keyword: str, city: str = "") -> tuple[float, float] | None:
        results = self.search_places(keyword, city, limit=1)
        if not results:
            return None
        return results[0]["lat"], results[0]["lng"]

    def _search_poi(self, keyword: str, city: str) -> PoiCandidate | None:
        params = urlencode(
            {
                "key": self.settings.amap_api_key,
                "keywords": keyword,
                "city": city,
                "citylimit": "true",
                "offset": "1",
                "extensions": "base",
            }
        )
        request = Request(f"https://restapi.amap.com/v3/place/text?{params}", headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        pois = payload.get("pois") or []
        if not pois:
            return None
        poi = pois[0]
        category = poi.get("type", "景点").split(";")[0]
        district = poi.get("adname") or city
        return PoiCandidate(
            name=poi.get("name", keyword),
            district=district,
            category=category,
            reason="来自地图搜索",
            estimated_visit_minutes=120 if "博物馆" in category else 90,
        )

    def _driving_route(self, origin: str, destination: str) -> dict[str, float | int] | None:
        params = urlencode(
            {
                "key": self.settings.amap_api_key,
                "origin": origin,
                "destination": destination,
                "strategy": "0",
            }
        )
        request = Request(f"https://restapi.amap.com/v3/direction/driving?{params}", headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        paths = payload.get("route", {}).get("paths") or []
        if not paths:
            return None
        best = paths[0]
        distance_km = round(int(best.get("distance", 0)) / 1000, 1)
        duration_minutes = int(int(best.get("duration", 0)) / 60)
        toll = round(float(best.get("tolls", 0)), 2)
        fuel = round(distance_km * 7.5 / 100 * 8.2, 2)
        return {
            "distance_km": distance_km,
            "duration_minutes": duration_minutes,
            "toll_fee": toll,
            "fuel_fee": fuel,
        }

    def _heuristic_poi(self, name: str, city: str, index: int) -> PoiCandidate:
        category = "历史街区" if index % 3 == 0 else "自然风景" if index % 3 == 1 else "博物馆"
        return PoiCandidate(
            name=name,
            district=f"{city}核心片区",
            category=category,
            reason="来自攻略关键词",
            estimated_visit_minutes=120 if "街" in name or "古镇" in name else 90,
        )

    @staticmethod
    def _amap_marker_url(name: str, lng: float, lat: float) -> str:
        return f"https://uri.amap.com/marker?position={lng:.6f},{lat:.6f}&name={name}"
