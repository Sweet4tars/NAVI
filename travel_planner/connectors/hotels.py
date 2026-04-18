from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote, urlparse, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from ..config import Settings
from ..schemas import HotelCandidate, SourceEvidence, SourceStatus, TripRequest
from ..utils import absolute_url, clean_text, extract_first_price, extract_rating
from .base import SourceCheck
from .browser import BrowserSessionManager


FREE_CANCEL = "\u514d\u8d39\u53d6\u6d88"
BREAKFAST = "\u542b\u65e9\u9910"
NEAR_METRO = "\u8fd1\u5730\u94c1"
FAMILY = "\u4eb2\u5b50"
PARKING = "\u505c\u8f66"
RIVER_VIEW = "\u6c5f\u666f"
HIGH_SCORE = "\u9ad8\u5206"
HOTEL_TAG_PATTERN = re.compile(
    rf"({FREE_CANCEL}|{BREAKFAST}|{NEAR_METRO}|{FAMILY}|{PARKING}|{RIVER_VIEW}|{HIGH_SCORE})"
)
BRAND_SPLIT_PATTERN = re.compile(r"[\u00b7\u3001/ ]+")
FLIGGY_CAPTCHA_HINTS = ("\u9a8c\u8bc1\u7801\u62e6\u622a", "\u8bf7\u62d6\u52a8\u4e0b\u65b9\u6ed1\u5757\u5b8c\u6210\u9a8c\u8bc1", "\u901a\u8fc7\u9a8c\u8bc1\u4ee5\u786e\u4fdd\u6b63\u5e38\u8bbf\u95ee")
CTRIP_FEATURE_HINTS = (
    "\u514d\u8d39\u505c\u8f66",
    "\u4eb2\u5b50\u9152\u5e97",
    "\u4eb2\u5b50\u4e3b\u9898\u623f",
    "\u5065\u8eab\u5ba4",
    "\u6d17\u8863\u623f",
    "\u673a\u5668\u4eba\u670d\u52a1",
    "\u5ba4\u5185\u6cf3\u6c60",
    "\u666f\u89c2\u9910\u5385",
    "\u897f\u6e56\u6e56\u666f",
    "\u9876\u697c\u9732\u53f0",
    "\u4e0b\u5348\u8336",
    "\u4f1a\u8bae\u5385",
)

CITY_ALIASES: dict[str, dict[str, str | tuple[float, float]]] = {
    "beijing": {"zh": "\u5317\u4eac", "slug": "beijing", "coords": (39.9042, 116.4074)},
    "shanghai": {"zh": "\u4e0a\u6d77", "slug": "shanghai", "coords": (31.2304, 121.4737)},
    "guangzhou": {"zh": "\u5e7f\u5dde", "slug": "guangzhou", "coords": (23.1291, 113.2644)},
    "shenzhen": {"zh": "\u6df1\u5733", "slug": "shenzhen", "coords": (22.5431, 114.0579)},
    "hangzhou": {"zh": "\u676d\u5dde", "slug": "hangzhou", "coords": (30.2741, 120.1551)},
    "suzhou": {"zh": "\u82cf\u5dde", "slug": "suzhou", "coords": (31.2989, 120.5853)},
    "nanjing": {"zh": "\u5357\u4eac", "slug": "nanjing", "coords": (32.0603, 118.7969)},
    "chengdu": {"zh": "\u6210\u90fd", "slug": "chengdu", "coords": (30.5728, 104.0668)},
    "yibin": {"zh": "\u5b9c\u5bbe", "slug": "yibin", "coords": (28.7513, 104.6417)},
    "xichang": {"zh": "\u897f\u660c", "slug": "xichang", "coords": (27.8945, 102.2644)},
    "wuhan": {"zh": "\u6b66\u6c49", "slug": "wuhan", "coords": (30.5928, 114.3055)},
    "xian": {"zh": "\u897f\u5b89", "slug": "xian", "coords": (34.3416, 108.9398)},
    "chongqing": {"zh": "\u91cd\u5e86", "slug": "chongqing", "coords": (29.5630, 106.5516)},
    "tianjin": {"zh": "\u5929\u6d25", "slug": "tianjin", "coords": (39.3434, 117.3616)},
    "qingdao": {"zh": "\u9752\u5c9b", "slug": "qingdao", "coords": (36.0671, 120.3826)},
    "xiamen": {"zh": "\u53a6\u95e8", "slug": "xiamen", "coords": (24.4798, 118.0894)},
    "kunming": {"zh": "\u6606\u660e", "slug": "kunming", "coords": (25.0389, 102.7183)},
    "dali": {"zh": "\u5927\u7406", "slug": "dali", "coords": (25.6075, 100.2676)},
    "dali_baizu": {"zh": "\u5927\u7406\u767d\u65cf\u81ea\u6cbb\u5dde", "slug": "dali", "coords": (25.6075, 100.2676)},
    "lijiang": {"zh": "\u4e3d\u6c5f", "slug": "lijiang", "coords": (26.8550, 100.2278)},
    "panzhihua": {"zh": "\u6500\u679d\u82b1", "slug": "panzhihua", "coords": (26.5823, 101.7185)},
    "zhaotong": {"zh": "\u662d\u901a", "slug": "zhaotong", "coords": (27.3383, 103.7172)},
    "yuxi": {"zh": "\u7389\u6eaa", "slug": "yuxi", "coords": (24.3505, 102.5439)},
    "jianshui": {"zh": "\u5efa\u6c34", "slug": "jianshui", "coords": (23.6369, 102.8269)},
    "mile": {"zh": "\u5f25\u52d2", "slug": "mile", "coords": (24.4051, 103.4147)},
    "haikou": {"zh": "\u6d77\u53e3", "slug": "haikou", "coords": (20.0440, 110.1999)},
    "sanya": {"zh": "\u4e09\u4e9a", "slug": "sanya", "coords": (18.2528, 109.5119)},
}

CITY_INDEX: dict[str, dict[str, str | tuple[float, float]]] = {}
for record in CITY_ALIASES.values():
    slug = str(record["slug"]).lower()
    zh = str(record["zh"]).lower()
    CITY_INDEX[slug] = record
    CITY_INDEX[zh] = record
    CITY_INDEX[zh.replace("\u5e02", "")] = record


@dataclass(slots=True)
class HotelSiteSpec:
    source: str
    base_url: str
    search_url_template: str
    blocked_keywords: tuple[str, ...]
    card_selectors: tuple[str, ...]
    name_selectors: tuple[str, ...]
    price_selectors: tuple[str, ...]
    district_selectors: tuple[str, ...]
    rating_selectors: tuple[str, ...]


SITE_SPECS: dict[str, HotelSiteSpec] = {
    "meituan": HotelSiteSpec(
        source="meituan",
        base_url="https://guide.meituan.com",
        search_url_template="https://guide.meituan.com/stay/{city_slug}",
        blocked_keywords=("404 This page could not be found",),
        card_selectors=(),
        name_selectors=(),
        price_selectors=(),
        district_selectors=(),
        rating_selectors=(),
    ),
    "ctrip": HotelSiteSpec(
        source="ctrip",
        base_url="https://m.ctrip.com",
        search_url_template="https://m.ctrip.com/webapp/hotel/searchlist/{lat}/{lng}/",
        blocked_keywords=("\u8bf7\u5b8c\u6210\u9a8c\u8bc1", "\u5b89\u5168\u9a8c\u8bc1", "\u9891\u7e41\u64cd\u4f5c"),
        card_selectors=("a[href*='/html5/hotel/hoteldetail/']",),
        name_selectors=(),
        price_selectors=(),
        district_selectors=(),
        rating_selectors=(),
    ),
    "qunar": HotelSiteSpec(
        source="qunar",
        base_url="https://hotel.qunar.com",
        search_url_template="https://hotel.qunar.com/global/",
        blocked_keywords=("\u8bf7\u7a0d\u540e\u91cd\u8bd5", "\u9a8c\u8bc1"),
        card_selectors=("div.hotel-item", "li.hotel", "article", "div[data-hotel-id]"),
        name_selectors=("h3", "h2", ".hotel-name", "[class*='name']"),
        price_selectors=(".price", "[class*='price']", "[data-price]"),
        district_selectors=(".location", "[class*='addr']", "[class*='district']"),
        rating_selectors=(".score", "[class*='score']", "[class*='rating']"),
    ),
    "fliggy": HotelSiteSpec(
        source="fliggy",
        base_url="https://hotel.fliggy.com",
        search_url_template="https://hotel.fliggy.com/",
        blocked_keywords=("\u8bf7\u901a\u8fc7\u9a8c\u8bc1", "\u767b\u5f55\u540e\u67e5\u770b\u66f4\u591a"),
        card_selectors=("div.hotel-item", "li.hotel-item", "article", "div.card"),
        name_selectors=("h3", "h2", ".hotel-name", "[class*='name']"),
        price_selectors=(".price", "[class*='price']", "[data-price]"),
        district_selectors=(".location", "[class*='addr']", "[class*='district']"),
        rating_selectors=(".score", "[class*='score']", "[class*='rating']"),
    ),
}


class HotelConnector:
    def __init__(self, settings: Settings, browser_manager: BrowserSessionManager):
        self.settings = settings
        self.browser_manager = browser_manager
        self._qunar_route_cache: dict[str, bool] = {}

    def hotel_sources(self) -> list[str]:
        return ["meituan", "ctrip", "fliggy"]

    def check_login_status(self, source: str, request: TripRequest) -> SourceStatus:
        spec = SITE_SPECS[source]
        state = "ready"
        detail = "Public results look accessible."
        try:
            with self.browser_manager.open_page(self._search_url(spec, request)) as (page, profile):
                current_url = page.url.lower()
                title = clean_text(page.title())
                text = clean_text(page.locator("body").inner_text(timeout=4000))
                if source == "fliggy" and ("login.taobao.com" in current_url or title == "\u767b\u5f55"):
                    state = "awaiting_login"
                    detail = f"{source} requires Taobao or Fliggy login in {profile.browser_name}."
                elif source == "fliggy" and (title == "\u9a8c\u8bc1\u7801\u62e6\u622a" or any(token in text for token in FLIGGY_CAPTCHA_HINTS)):
                    state = "awaiting_login"
                    detail = f"{source} requires a fresh slider verification in {profile.browser_name}."
                elif any(token in text for token in spec.blocked_keywords):
                    state = "awaiting_login"
                    detail = f"{source} requires login or verification in {profile.browser_name}."
                else:
                    detail = f"Using {profile.browser_name} profile."
        except Exception as exc:
            state = "failed"
            detail = f"{source} browser check failed: {exc}"
        return SourceCheck(source=source, state=state, detail=detail, checked_at=datetime.now().replace(microsecond=0)).to_status()

    def collect(self, request: TripRequest) -> tuple[list[HotelCandidate], list[SourceEvidence], dict[str, SourceStatus], list[str]]:
        statuses: dict[str, SourceStatus] = {}
        warnings: list[str] = []
        hotels: list[HotelCandidate] = []
        evidence: list[SourceEvidence] = []

        for source in self.hotel_sources():
            site_hotels, site_evidence, status, site_warnings = self.collect_source(source, request)
            statuses[source] = status
            hotels.extend(site_hotels)
            evidence.extend(site_evidence)
            warnings.extend(site_warnings)

        return self._deduplicate(hotels), evidence[:12], statuses, warnings

    def collect_source(self, source: str, request: TripRequest) -> tuple[list[HotelCandidate], list[SourceEvidence], SourceStatus, list[str]]:
        spec = SITE_SPECS[source]
        warnings: list[str] = []
        status = self.check_login_status(source, request)
        if status.state == "failed":
            return [], [], status, [f"{source} status check failed and was skipped."]
        if status.state == "awaiting_login":
            return [], [], status, [f"{source} needs one-time login before collection."]
        if source == "qunar" and not self._is_qunar_real_list_available(request.destination):
            status = SourceStatus(
                source=status.source,
                state=status.state,
                detail=f"{status.detail} Domestic hotel list route is unavailable; using region hints fallback.",
                checked_at=status.checked_at,
            )
            hotels = self.parse_qunar_city_suggest_data(self.fetch_qunar_city_suggestions(request.destination), request)
            evidence = [
                SourceEvidence(
                    source="qunar",
                    title=hotel.name,
                    url=hotel.booking_url,
                    captured_at=datetime.now().replace(microsecond=0),
                    excerpt=hotel.why_selected[:120],
                )
                for hotel in hotels[:2]
            ]
            return hotels, evidence, status, ["qunar domestic hotel list route currently redirects to homepage; using region_hint fallback."]
        try:
            hotels, evidence = self._collect_site(spec, request)
        except Exception as exc:
            return [], [], status, [f"{source} collection failed: {exc}"]
        if not hotels:
            warnings.append(f"{source} returned no parseable hotel entries.")
        return hotels, evidence, status, warnings

    def _is_qunar_real_list_available(self, city: str) -> bool:
        city_slug = self._resolve_city_slug(city)
        if city_slug in self._qunar_route_cache:
            return self._qunar_route_cache[city_slug]
        url = f"https://hotel.qunar.com/city/{city_slug}/?fromDate=2026-05-01&toDate=2026-05-02"
        try:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            opener = urllib.request.build_opener(NoRedirect)
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://hotel.qunar.com/global/"})
            response = opener.open(request, timeout=15)
            final_url = response.geturl()
            alive = "hotel.qunar.com" in final_url and "/city/" in final_url
        except urllib.error.HTTPError as exc:
            location = exc.headers.get("Location", "")
            alive = not ("/cn/" in location or "www.qunar.com" in location)
        except Exception:
            alive = False
        self._qunar_route_cache[city_slug] = alive
        return alive

    def _collect_site(self, spec: HotelSiteSpec, request: TripRequest) -> tuple[list[HotelCandidate], list[SourceEvidence]]:
        search_url = self._search_url(spec, request)
        with self.browser_manager.open_page(search_url, wait_until="domcontentloaded") as (page, _profile):
            page.wait_for_timeout(1200)
            html = page.content()
            body_text = clean_text(page.locator("body").inner_text(timeout=5000))
            title = clean_text(page.title())

        if spec.source == "ctrip":
            hotels = self.parse_ctrip_mobile_html(html, request)
        elif spec.source == "meituan":
            hotels = self.parse_meituan_guide_html(html, request)
        elif spec.source == "qunar":
            hotels = self.parse_qunar_city_suggest_data(self.fetch_qunar_city_suggestions(request.destination), request)
        elif spec.source == "fliggy":
            if title == "\u9a8c\u8bc1\u7801\u62e6\u622a" or any(token in body_text for token in FLIGGY_CAPTCHA_HINTS):
                raise RuntimeError("fliggy verification is required before hotel results can be collected.")
            hotels = self.parse_fliggy_result_text(body_text, request, booking_url=search_url)
        else:
            hotels = self.parse_listing_html(spec, html, request)

        evidence = [
            SourceEvidence(
                source=spec.source,
                title=hotel.name,
                url=hotel.booking_url or search_url,
                captured_at=datetime.now().replace(microsecond=0),
                excerpt=f"{hotel.district} \u00a5{hotel.nightly_price:.0f}" if hotel.nightly_price else hotel.why_selected[:120],
            )
            for hotel in hotels[:2]
        ]
        return hotels[: self.settings.hotel_result_limit], evidence

    def parse_fliggy_result_text(self, text: str, request: TripRequest, *, booking_url: str = "") -> list[HotelCandidate]:
        section = text
        if "\u56fd\u5185\u9152\u5e97\u63a8\u8350" in text:
            section = text.split("\u56fd\u5185\u9152\u5e97\u63a8\u8350", 1)[1]
        if "\u4f4d\u7f6e" in section:
            section = section.split("\u4f4d\u7f6e", 1)[0]
        pairs = re.findall(r"(.+?)\s*[¥￥](\d{2,5})", section)
        hotels: list[HotelCandidate] = []
        seen: set[str] = set()
        for raw_name, raw_price in pairs:
            name = clean_text(raw_name)
            if len(name) < 3 or name in seen:
                continue
            if not any(keyword in name for keyword in ("\u9152\u5e97", "\u5ba2\u6808", "\u6c11\u5bbf", "\u5ea6\u5047", "\u516c\u5bd3", "\u5bbe\u9986")):
                continue
            price = float(raw_price)
            hotel = HotelCandidate(
                source="fliggy",
                name=name[:80],
                district=request.destination,
                nightly_price=price,
                candidate_kind="hotel",
                price_confidence="observed",
                tags=["fliggy-recommend"],
                booking_url=booking_url,
                why_selected=f"\u00a5{price:.0f}/\u665a\uff0c\u6765\u81ea\u98de\u732a\u7ed3\u679c\u9875\u9996\u5c4f\u63a8\u8350",
            )
            if self._looks_relevant(hotel, name, request):
                hotels.append(hotel)
                seen.add(name)
        return hotels

    def parse_ctrip_mobile_html(self, html: str, request: TripRequest) -> list[HotelCandidate]:
        next_data_hotels = self._parse_ctrip_next_data(html, request)
        if next_data_hotels:
            return next_data_hotels
        soup = BeautifulSoup(html, "html.parser")
        hotels: list[HotelCandidate] = []
        for anchor in soup.select("a[href*='/html5/hotel/hoteldetail/']"):
            href = anchor.get("href", "")
            anchor_name = self._extract_ctrip_anchor_name(clean_text(anchor.get_text(" ", strip=True)))
            if len(anchor_name) < 3:
                continue
            card_text = self._extract_ctrip_card_text(anchor)
            parts = self._split_ctrip_card_text(card_text, request)
            if not parts:
                continue
            parts["name"] = anchor_name[:80]
            hotel = HotelCandidate(
                source="ctrip",
                name=parts["name"][:80],
                district=parts["district"][:40],
                nightly_price=parts["price"],
                candidate_kind="hotel",
                price_confidence="hidden" if "price-hidden" in parts["tags"] else "observed",
                rating=parts["rating"],
                tags=parts["tags"][:6],
                breakfast_included=BREAKFAST in parts["full_text"],
                free_cancel=FREE_CANCEL in parts["full_text"],
                parking=PARKING in parts["full_text"],
                booking_url=absolute_url("https://m.ctrip.com", href),
            )
            if self._looks_relevant(hotel, parts["full_text"], request):
                hotels.append(hotel)
        return hotels

    def _parse_ctrip_next_data(self, html: str, request: TripRequest) -> list[HotelCandidate]:
        soup = BeautifulSoup(html, "html.parser")
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return []
        try:
            payload = json.loads(script.string)
        except Exception:
            return []
        candidates = self._collect_ctrip_cards_from_json(payload)
        hotels: list[HotelCandidate] = []
        for item in candidates:
            base_ui = item.get("baseUIInfo") or {}
            base_info = item.get("baseInfo") or {}
            price_info = item.get("priceInfo") or {}
            jump_info = item.get("jumpDetailInfo") or {}
            name = clean_text(((base_ui.get("name") or {}).get("hotelName")) or "")
            if len(name) < 3:
                continue
            score = extract_rating(str(((base_ui.get("commentInfo") or {}).get("score")) or "")) or (
                float((base_ui.get("commentInfo") or {}).get("score")) if str((base_ui.get("commentInfo") or {}).get("score", "")).replace(".", "", 1).isdigit() else None
            )
            distance_info = base_ui.get("distanceAndPosition") or {}
            district = clean_text(distance_info.get("position") or distance_info.get("distanceAndPosition") or distance_info.get("distance") or "")
            if "·" in district:
                district = clean_text(district.split("·", 1)[0])
            price = self._extract_ctrip_price_from_json(price_info, request)
            tags = self._extract_ctrip_tags_from_json(item, price_info)
            booking_url = self._normalize_ctrip_jump_url(jump_info.get("jumpDetailURL") or "", base_info.get("hotelId"))
            hotel = HotelCandidate(
                source="ctrip",
                name=name[:80],
                district=district[:40],
                nightly_price=price,
                candidate_kind="hotel",
                price_confidence="hidden" if "price-hidden" in tags else "observed",
                rating=score,
                tags=tags[:6],
                breakfast_included=BREAKFAST in tags,
                free_cancel=FREE_CANCEL in tags,
                parking=any(PARKING in tag for tag in tags),
                booking_url=booking_url,
            )
            full_text = " ".join(
                filter(
                    None,
                    [
                        name,
                        district,
                        clean_text(((base_ui.get("oneSentenceSellPoint") or {}).get("sellingPointSentence")) or ""),
                        " ".join(tags),
                    ],
                )
            )
            if self._looks_relevant(hotel, full_text, request):
                hotels.append(hotel)
        return hotels

    def _collect_ctrip_cards_from_json(self, node) -> list[dict]:
        matches: list[dict] = []
        if isinstance(node, dict):
            if {"baseUIInfo", "baseInfo", "priceInfo"}.issubset(node.keys()):
                matches.append(node)
            for value in node.values():
                matches.extend(self._collect_ctrip_cards_from_json(value))
        elif isinstance(node, list):
            for item in node:
                matches.extend(self._collect_ctrip_cards_from_json(item))
        return matches

    def _extract_ctrip_price_from_json(self, price_info: dict, request: TripRequest) -> float:
        for key in ("price", "salePrice", "discountPrice", "displayPrice"):
            value = price_info.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                match = re.search(r"\d+(?:\.\d+)?", value)
                if match:
                    return float(match.group(0))
        return float(request.hotel_budget_max or 600.0)

    def _extract_ctrip_tags_from_json(self, item: dict, price_info: dict) -> list[str]:
        tags: list[str] = []
        tag_info = item.get("tagInfo") or {}
        for key in ("serviceTagList", "basicTagList", "sceneTagList"):
            for tag in tag_info.get(key) or []:
                title = clean_text(str(tag.get("title") or ""))
                if title and title not in tags:
                    tags.append(title)
        sell_point = clean_text((((item.get("baseUIInfo") or {}).get("oneSentenceSellPoint") or {}).get("sellingPointSentence")) or "")
        for feature in CTRIP_FEATURE_HINTS:
            if feature in sell_point and feature not in tags:
                tags.append(feature)
        price_value = str(price_info.get("price", ""))
        if price_value.strip() in {"?", "", "null", "None"} and "price-hidden" not in tags:
            tags.append("price-hidden")
        return tags

    def _normalize_ctrip_jump_url(self, jump_url: str, hotel_id) -> str:
        cleaned = clean_text(str(jump_url or ""))
        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            return cleaned
        if cleaned.startswith("/"):
            return absolute_url("https://m.ctrip.com", cleaned)
        if hotel_id:
            return f"https://m.ctrip.com/html5/hotel/hoteldetail/{hotel_id}.html"
        return ""

    def _extract_ctrip_card_text(self, anchor) -> str:
        node = anchor
        for _ in range(4):
            if getattr(node, "parent", None) is None:
                break
            node = node.parent
        return clean_text(node.get_text(" ", strip=True))

    def _extract_ctrip_anchor_name(self, text: str) -> str:
        suffixes = (
            "\u5ea6\u5047\u9152\u5e97",
            "\u9152\u5e97\u5f0f\u516c\u5bd3",
            "\u9152\u5e97",
            "\u996d\u5e97",
            "\u5bbe\u9986",
            "\u6c11\u5bbf",
            "\u5ba2\u6808",
            "\u516c\u5bd3",
        )
        for suffix in suffixes:
            match = re.search(rf"^(.*?{re.escape(suffix)}(?:\([^)]*\))?)", text)
            if match:
                return clean_text(match.group(1))
        return text.split(" ", 1)[0]

    def parse_meituan_guide_html(self, html: str, request: TripRequest) -> list[HotelCandidate]:
        text = clean_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
        destination_label = self._city_display_name(request.destination)
        patterns = [
            ("\u7ecf\u6d4e\u578b 100-220元/晚", "\u4e2d\u6863\u8fde\u9501 220-500元/晚", "\u7ecf\u6d4e\u578b"),
            ("\u4e2d\u6863\u8fde\u9501 220-500元/晚", "\u897f\u6e56\u666f\u89c2\u9ad8\u6863\u9152\u5e97 600-3000元/晚", "\u4e2d\u6863\u8fde\u9501"),
            ("\u897f\u6e56\u666f\u89c2\u9ad8\u6863\u9152\u5e97 600-3000元/晚", f"{destination_label} 各区住宿特点", "\u897f\u6e56\u666f\u89c2\u9ad8\u6863\u9152\u5e97"),
        ]
        hotels: list[HotelCandidate] = []
        for start_marker, next_marker, tier_name in patterns:
            section = self._slice_text(text, start_marker, next_marker)
            if not section:
                continue
            price_match = re.search(r"(\d+)-(\d+)元/晚", section)
            if not price_match:
                continue
            low, high = int(price_match.group(1)), int(price_match.group(2))
            scenario_match = re.search(r"适合：([^ ]+)", section)
            scenario = clean_text((scenario_match.group(1) if scenario_match else "").replace("·", "/"))
            district = self._extract_meituan_district(section, request)
            note_match = re.search(r"💡\s*([^💡]+)$", section)
            note = clean_text(note_match.group(1) if note_match else "")
            brand_candidates = self._extract_meituan_brands(section, note)
            brands = brand_candidates[:3]
            brands_label = "/".join(brands) if brands else tier_name
            hotels.append(
                HotelCandidate(
                    source="meituan",
                    name=f"{destination_label} {tier_name} ({brands_label})",
                    district=district[:40],
                    nightly_price=round((low + high) / 2, 1),
                    candidate_kind="strategy",
                    price_confidence="estimated",
                    tags=[tier_name, scenario] + brands[:2],
                    booking_url=self._search_url(SITE_SPECS["meituan"], request),
                    why_selected=note[:120],
                )
            )
        return hotels

    def _slice_text(self, text: str, start_marker: str, end_marker: str) -> str:
        start = self._find_structured_marker(text, start_marker)
        if start == -1:
            return ""
        end = self._find_structured_marker(text, end_marker, start + len(start_marker))
        if end == -1:
            end = len(text)
        return clean_text(text[start:end])

    def _find_structured_marker(self, text: str, marker: str, start_pos: int = 0) -> int:
        candidates = [match.start() for match in re.finditer(re.escape(marker), text[start_pos:])]
        if not candidates:
            return -1
        absolute = [start_pos + item for item in candidates]
        for idx in absolute:
            tail = text[idx : idx + len(marker) + 120]
            if re.search(r"\d+-\d+元/晚", tail):
                return idx
        return absolute[0]

    def _city_display_name(self, city: str) -> str:
        record = CITY_INDEX.get(clean_text(city).lower())
        if record:
            return str(record["zh"])
        return city

    def _extract_meituan_brands(self, section: str, note: str) -> list[str]:
        known_brands = [
            "\u6c49\u5ead",
            "\u5982\u5bb6",
            "7\u5929",
            "\u683c\u6797\u8c6a\u6cf0",
            "\u5168\u5b63\u9152\u5e97",
            "\u4e9a\u6735\u9152\u5e97",
            "\u6854\u5b50\u6c34\u6676",
            "\u4e07\u6021\u9152\u5e97",
            "\u676d\u5dde\u56db\u5b63\u9152\u5e97",
            "\u541b\u60a6\u9152\u5e97",
            "\u897f\u6eaa\u60a6\u6995\u5e84",
        ]
        found = [brand for brand in known_brands if brand in section]
        if found:
            return found
        raw = note.split("（")[0].split("(")[0]
        return [item for item in BRAND_SPLIT_PATTERN.split(raw) if item][:3]

    def _extract_meituan_district(self, section: str, request: TripRequest) -> str:
        match = re.search(r"([\u4e00-\u9fa5]{2,12}(?:区|广场|新城|周边|景区|商圈|西湖边|湖滨商圈))", section)
        if match:
            return clean_text(match.group(1))
        return self._city_display_name(request.destination)

    def parse_listing_html(self, spec: HotelSiteSpec, html: str, request: TripRequest | None = None) -> list[HotelCandidate]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(",".join(spec.card_selectors)) if spec.card_selectors else []
        if not cards:
            cards = [node for node in soup.find_all(["div", "article", "li"]) if "price" in node.get_text(" ", strip=True).lower()]
        hotels: list[HotelCandidate] = []
        for card in cards:
            text = clean_text(card.get_text(" ", strip=True))
            if len(text) < 8:
                continue
            name = self._first_text(card, spec.name_selectors) or self._fallback_name(text)
            price_text = self._first_text(card, spec.price_selectors) or text
            nightly_price = extract_first_price(price_text)
            if not name or nightly_price is None:
                continue
            district = self._first_text(card, spec.district_selectors) or self._extract_district(text)
            rating_text = self._first_text(card, spec.rating_selectors) or text
            rating = extract_rating(rating_text)
            tags = [tag for tag in HOTEL_TAG_PATTERN.findall(text) if tag]
            link = card.find("a", href=True)
            hotel = HotelCandidate(
                source=spec.source,
                name=name[:80],
                district=district[:40],
                nightly_price=nightly_price,
                candidate_kind="hotel",
                price_confidence="observed",
                rating=rating,
                tags=tags[:6],
                breakfast_included=BREAKFAST in text,
                free_cancel="\u53d6\u6d88" in text,
                parking=PARKING in text,
                booking_url=absolute_url(spec.base_url, link["href"] if link else ""),
            )
            if request and not self._looks_relevant(hotel, text, request):
                continue
            hotels.append(hotel)
        return hotels

    def _deduplicate(self, hotels: list[HotelCandidate]) -> list[HotelCandidate]:
        deduped: dict[str, HotelCandidate] = {}
        for hotel in hotels:
            key = f"{hotel.name.lower()}::{hotel.district.lower()}"
            existing = deduped.get(key)
            if existing is None or hotel.nightly_price < existing.nightly_price:
                deduped[key] = hotel
        return sorted(deduped.values(), key=lambda item: (item.nightly_price, -(item.rating or 0)))

    def _search_url(self, spec: HotelSiteSpec, request: TripRequest) -> str:
        if spec.source == "ctrip":
            lat, lng = self._resolve_city_coords(request.destination)
            return spec.search_url_template.format(lat=lat, lng=lng)
        if spec.source == "meituan":
            return spec.search_url_template.format(city_slug=self._resolve_city_slug(request.destination))
        if spec.source == "fliggy":
            return self._build_fliggy_search_url(request)
        if spec.source == "qunar":
            return spec.search_url_template
        city_slug = quote(request.destination)
        return spec.search_url_template.format(
            city=city_slug,
            checkin=request.start_date.isoformat(),
            checkout=request.end_date.isoformat() if request.end_date else request.start_date.isoformat(),
        )

    def _build_fliggy_search_url(self, request: TripRequest) -> str:
        city_info = self.fetch_fliggy_city_info(request.destination)
        if not city_info:
            return SITE_SPECS["fliggy"].search_url_template
        return (
            "https://hotel.fliggy.com/hotel_list3.htm"
            "?spm=181.11358650.hotelModule.domesticSearch"
            f"&city={city_info['cityCode']}"
            f"&cityName={quote(city_info['cityName'])}"
            f"&checkIn={request.start_date.isoformat()}"
            f"&checkOut={request.end_date.isoformat() if request.end_date else request.start_date.isoformat()}"
            "&keywords="
        )

    def fetch_fliggy_city_info(self, city: str) -> dict | None:
        callback = "cb"
        url = f"https://hotel.alitrip.com/ajax/CitySuggest.do?t=0&q={quote(city)}&callback={callback}"
        payload = self._fetch_jsonp(
            url,
            referer="https://www.fliggy.com/jiudian/",
            callback=callback,
        )
        return self.parse_fliggy_city_suggest_data(payload, city)

    def parse_fliggy_city_suggest_data(self, payload: dict, city: str) -> dict | None:
        results = payload.get("result") or []
        target = clean_text(city)
        for item in results:
            display = clean_text(str(item.get("displayName", "")))
            suggest = clean_text(str(item.get("suggestName", "")))
            if target and (target in display or target in suggest):
                return {"cityCode": item.get("cityCode") or item.get("id"), "cityName": item.get("displayName") or target}
        if results:
            first = results[0]
            return {"cityCode": first.get("cityCode") or first.get("id"), "cityName": first.get("displayName") or target}
        return None

    def fetch_qunar_city_suggestions(self, city: str) -> dict:
        url = f"https://hotel.qunar.com/city/getCitySuggestV4?isChina=true&q={quote(city)}&src=h_hotelnode"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://hotel.qunar.com/global/"})
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def parse_qunar_city_suggest_data(self, payload: dict, request: TripRequest) -> list[HotelCandidate]:
        data = payload.get("data") or []
        if not data:
            return []
        primary = data[0]
        city_name = primary.get("cityName") or request.destination
        hot_words = primary.get("hotWord") or []
        hotels: list[HotelCandidate] = []
        for word in hot_words[:3]:
            area = clean_text(word.get("qname") or word.get("dname") or "")
            if not area:
                continue
            hotels.append(
                HotelCandidate(
                    source="qunar",
                    name=f"{city_name} \u70ed\u95e8\u7247\u533a\u00b7{area}",
                    district=str(city_name),
                    nightly_price=float(request.hotel_budget_max or 500),
                    candidate_kind="region_hint",
                    price_confidence="estimated",
                    tags=["qunar-hotword", word.get("suggestType") or "poi"],
                    booking_url="https://hotel.qunar.com/global/",
                    why_selected="\u6765\u81ea\u53bb\u54ea\u513f\u70ed\u641c\u5730\u6807\uff0c\u53ef\u4f5c\u4e3a\u9152\u5e97\u68c0\u7d22\u7247\u533a\u3002",
                )
            )
        return hotels

    def _fetch_jsonp(self, url: str, *, referer: str, callback: str = "cb") -> dict:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": referer})
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="ignore")
        match = re.search(rf"{re.escape(callback)}\((.*)\)", body, re.S)
        if not match:
            raise ValueError("JSONP payload not found.")
        return json.loads(match.group(1))

    def _resolve_city_slug(self, city: str) -> str:
        record = CITY_INDEX.get(clean_text(city).lower())
        if record:
            return str(record["slug"])
        return clean_text(city).lower().replace(" ", "")

    def _resolve_city_coords(self, city: str) -> tuple[float, float]:
        record = CITY_INDEX.get(clean_text(city).lower())
        if record:
            coords = record["coords"]
            return float(coords[0]), float(coords[1])  # type: ignore[index]
        if self.settings.amap_api_key:
            geocoded = self._geocode_city(city)
            if geocoded:
                return geocoded
        return 31.2304, 121.4737

    def _geocode_city(self, city: str) -> tuple[float, float] | None:
        params = f"key={self.settings.amap_api_key}&address={quote(city)}"
        request = Request(f"https://restapi.amap.com/v3/geocode/geo?{params}", headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        geocodes = payload.get("geocodes") or []
        if not geocodes:
            return None
        location = geocodes[0].get("location", "")
        if "," not in location:
            return None
        lng, lat = location.split(",", 1)
        return float(lat), float(lng)

    def _split_ctrip_card_text(self, text: str, request: TripRequest) -> dict | None:
        tokens = [token for token in text.split(" ") if token]
        if not tokens:
            return None
        name = tokens[0]
        rating = None
        district = ""
        tags: list[str] = []
        location_block = self._extract_ctrip_location_block(text)
        for idx, token in enumerate(tokens[1:], start=1):
            if rating is None and re.fullmatch(r"[1-5]\.\d", token):
                rating = float(token)
            if "\u8fd1" in token or "\u5730\u94c1\u7ad9" in token or "\u6e7f\u5730" in token or "\u5e7f\u573a" in token:
                tags.append(token)
            if "\u00b7" in token and not district:
                district = token.replace("\u00b7", " ")
            if token in {FREE_CANCEL, BREAKFAST, FAMILY, PARKING, RIVER_VIEW}:
                tags.append(token)
        for feature in CTRIP_FEATURE_HINTS:
            if feature in text and feature not in tags:
                tags.append(feature)
        if location_block:
            district = self._extract_ctrip_district(location_block) or district
        price = self._extract_ctrip_price(text)
        if not district:
            district = self._extract_district(text)
        if price <= 0:
            price = float(self._price_ceiling_from_budget_hint(text) or request.hotel_budget_max or 600.0)
            tags.append("price-hidden")
        return {"name": name, "price": price, "rating": rating, "district": district, "tags": tags, "full_text": text}

    def _extract_ctrip_location_block(self, text: str) -> str:
        match = re.search(r"(?:收藏)\s+(.+?)(?:登录看低价|热卖！低价房仅剩\d+间|上拉加载更多|立即登录|[¥￥]|CNY)", text)
        return clean_text(match.group(1)) if match else ""

    def _extract_ctrip_district(self, block: str) -> str:
        if "·" in block:
            district = clean_text(block.split("·", 1)[0])
            if district and not district.startswith("近"):
                return district
        match = re.search(r"([\u4e00-\u9fa5]{2,16}(?:商圈|景区|广场|市区|新区|湖区))", block)
        return clean_text(match.group(1)) if match else ""

    def _extract_ctrip_price(self, text: str) -> float:
        patterns = [
            r"(?:CNY|RMB|¥|￥)\s*(\d{2,5}(?:\.\d{1,2})?)",
            r"(\d{2,5}(?:\.\d{1,2})?)\s*元(?:/晚)?",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return float(match.group(1))
        return 0.0

    def _price_ceiling_from_budget_hint(self, text: str) -> float:
        match = re.search(r"(\d{2,5})-(\d{2,5})元/晚", text)
        if match:
            low, high = float(match.group(1)), float(match.group(2))
            return (low + high) / 2
        return 0.0


    def _looks_relevant(self, hotel: HotelCandidate, raw_text: str, request: TripRequest) -> bool:
        destination_hints = self._city_hints(request.destination)
        origin_hints = self._city_hints(request.origin)
        haystack = f"{hotel.name} {hotel.district} {raw_text}".lower()
        destination_label = self._city_display_name(request.destination).lower()
        origin_label = self._city_display_name(request.origin).lower()

        if request.origin != request.destination:
            if origin_label and hotel.name.lower().startswith(origin_label) and not hotel.name.lower().startswith(destination_label):
                return False

        if any(hint in haystack for hint in destination_hints):
            pass
        elif any(hint in haystack for hint in origin_hints) and request.origin != request.destination:
            return False

        ceiling = self._price_ceiling(request)
        if hotel.nightly_price > ceiling:
            return False
        if len(hotel.name) < 3:
            return False
        return True

    def _price_ceiling(self, request: TripRequest) -> float:
        if request.hotel_budget_max:
            return max(request.hotel_budget_max * 2.5, 1800)
        if request.hotel_star_level and request.hotel_star_level >= 5:
            return 8000
        return 5000

    def _city_hints(self, city: str) -> set[str]:
        normalized = clean_text(city).lower()
        hints = {normalized, normalized.replace("\u5e02", ""), normalized.replace(" ", "")}
        record = CITY_INDEX.get(normalized)
        if record:
            hints.add(str(record["zh"]).lower())
            hints.add(str(record["slug"]).lower())
        return {hint for hint in hints if hint}

    def _first_text(self, card, selectors: tuple[str, ...]) -> str:
        for selector in selectors:
            node = card.select_one(selector)
            if node:
                text = clean_text(node.get_text(" ", strip=True))
                if text:
                    return text
        return ""

    def _extract_district(self, text: str) -> str:
        match = re.search(r"([\u4e00-\u9fa5]{2,10}(?:\u533a|\u9547|\u666f\u533a|\u8857\u9053))", text)
        return match.group(1) if match else ""

    def _fallback_name(self, text: str) -> str:
        chunks = [chunk for chunk in re.split(r"[\u00a5¥\d]", text) if chunk.strip()]
        for chunk in chunks:
            cleaned = clean_text(chunk)
            if 2 <= len(cleaned) <= 40:
                return cleaned
        return ""
