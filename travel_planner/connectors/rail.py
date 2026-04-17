from __future__ import annotations

import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import Settings
from ..schemas import SourceEvidence, TransportOption, TripRequest
from ..utils import duration_to_minutes


STATION_JS_URL = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"
TICKET_QUERY_URL = "https://kyfw.12306.cn/otn/leftTicket/queryG"
TICKET_PRICE_URL = "https://kyfw.12306.cn/otn/leftTicket/queryTicketPrice"


class RailConnector:
    name = "12306"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.station_cache = settings.data_dir / "station_name.js"
        self._station_by_name: dict[str, str] | None = None
        self._station_by_code: dict[str, str] | None = None

    def collect(self, request: TripRequest) -> tuple[list[TransportOption], list[SourceEvidence], list[str]]:
        warnings: list[str] = []
        try:
            trains = self._search_trains(request)
        except Exception as exc:
            return [], [], [f"12306 查询失败: {exc}"]
        evidences = [
            SourceEvidence(
                source=self.name,
                title=option.label,
                url=option.booking_url,
                captured_at=__import__("datetime").datetime.now().replace(microsecond=0),
                excerpt=f"{option.depart_at}-{option.arrive_at} {option.duration_minutes}分钟",
            )
            for option in trains[:3]
        ]
        if not trains:
            warnings.append("没有查到匹配车次。")
        return trains[: self.settings.rail_result_limit], evidences, warnings

    def _fetch_json(self, url: str) -> dict:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 travel-planner-agent"})
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def _load_station_catalog(self) -> tuple[dict[str, str], dict[str, str]]:
        if self._station_by_name is not None and self._station_by_code is not None:
            return self._station_by_name, self._station_by_code
        if not self.station_cache.exists():
            request = Request(STATION_JS_URL, headers={"User-Agent": "Mozilla/5.0 travel-planner-agent"})
            with urlopen(request, timeout=20) as response:
                self.station_cache.write_bytes(response.read())
        raw = self.station_cache.read_text(encoding="utf-8", errors="ignore")
        entries = re.findall(r"@([^|]+)\|([A-Z]+)\|", raw)
        by_name = {name: code for name, code in entries}
        by_code = {code: name for name, code in entries}
        self._station_by_name, self._station_by_code = by_name, by_code
        return by_name, by_code

    def _resolve_station_code(self, name: str) -> str:
        by_name, _by_code = self._load_station_catalog()
        if name in by_name:
            return by_name[name]
        normalized = name.replace("市", "").replace("站", "")
        candidates = [(station_name, code) for station_name, code in by_name.items() if normalized in station_name]
        if not candidates:
            raise ValueError(f"未找到车站: {name}")
        preferred = sorted(candidates, key=lambda item: len(item[0]))[0]
        return preferred[1]

    def _search_trains(self, trip_request: TripRequest) -> list[TransportOption]:
        from_code = self._resolve_station_code(trip_request.origin)
        to_code = self._resolve_station_code(trip_request.destination)
        params = urlencode(
            {
                "leftTicketDTO.train_date": trip_request.start_date.isoformat(),
                "leftTicketDTO.from_station": from_code,
                "leftTicketDTO.to_station": to_code,
                "purpose_codes": "ADULT",
            }
        )
        payload = self._fetch_json(f"{TICKET_QUERY_URL}?{params}")
        rows = payload.get("data", {}).get("result", [])
        _, station_by_code = self._load_station_catalog()
        options: list[TransportOption] = []
        for row in rows[: self.settings.rail_result_limit * 2]:
            parts = row.split("|")
            if len(parts) < 33:
                continue
            train_no = parts[2]
            train_code = parts[3]
            from_station_no = parts[16]
            to_station_no = parts[17]
            seat_types = parts[35] if len(parts) > 35 else ""
            seats = self._fetch_price_map(train_no, from_code, to_code, from_station_no, to_station_no, seat_types, trip_request.start_date.isoformat())
            best_price = min(seats.values()) if seats else None
            tags = [
                f"出发:{station_by_code.get(parts[6], trip_request.origin)}",
                f"到达:{station_by_code.get(parts[7], trip_request.destination)}",
            ]
            for key, value in seats.items():
                tags.append(f"{key}¥{value:.0f}")
            options.append(
                TransportOption(
                    source=self.name,
                    mode="rail",
                    label=train_code,
                    depart_at=parts[8],
                    arrive_at=parts[9],
                    duration_minutes=duration_to_minutes(parts[10]),
                    price_snapshot=best_price,
                    tags=tags[:6],
                    booking_url="https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc",
                )
            )
        return sorted(options, key=lambda item: (item.duration_minutes, item.price_snapshot or 9999))

    def _fetch_price_map(
        self,
        train_no: str,
        from_code: str,
        to_code: str,
        from_station_no: str,
        to_station_no: str,
        seat_types: str,
        train_date: str,
    ) -> dict[str, float]:
        params = urlencode(
            {
                "train_no": train_no,
                "from_station_no": from_station_no,
                "to_station_no": to_station_no,
                "seat_types": seat_types,
                "train_date": train_date,
                "from_station_telecode": from_code,
                "to_station_telecode": to_code,
            }
        )
        try:
            payload = self._fetch_json(f"{TICKET_PRICE_URL}?{params}")
        except Exception:
            return {}
        data = payload.get("data") or {}
        mapping = {
            "A9": "商务座",
            "P": "特等座",
            "M": "一等座",
            "O": "二等座",
            "A4": "软卧",
            "A3": "硬卧",
            "A1": "硬座",
            "WZ": "无座",
        }
        prices: dict[str, float] = {}
        for seat_code, seat_name in mapping.items():
            price = data.get(seat_code)
            if isinstance(price, str):
                numeric = re.sub(r"[^0-9.]", "", price)
                if numeric:
                    prices[seat_name] = float(numeric)
        return prices
