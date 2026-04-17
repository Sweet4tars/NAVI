from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..config import Settings
from ..schemas import GuideNote, SourceEvidence, SourceStatus
from ..utils import absolute_url, clean_text
from .base import SourceCheck
from .browser import BrowserSessionManager


LOGIN_HINTS = (
    "\u8bf7\u767b\u5f55\u540e\u67e5\u770b\u66f4\u591a",
    "\u8bf7\u901a\u8fc7\u9a8c\u8bc1",
    "\u626b\u7801\u767b\u5f55",
)
POI_SUFFIXES = (
    "\u53e4\u9547",
    "\u516c\u56ed",
    "\u535a\u7269\u9986",
    "\u5bfa",
    "\u8857",
    "\u6e56",
    "\u5c71",
    "\u56ed",
    "\u4e50\u56ed",
    "\u666f\u533a",
    "\u7801\u5934",
    "\u6e7f\u5730",
)
POI_EXCLUDES = (
    "\u5e7c\u513f\u56ed",
    "\u5c0f\u5b66",
    "\u4e2d\u5b66",
    "\u533b\u9662",
    "\u516c\u53f8",
    "\u529e\u516c\u5ba4",
    "\u5199\u5b57\u697c",
    "\u5355\u4f4d",
)
TIP_HINTS = (
    "\u5efa\u8bae",
    "\u63a8\u8350",
    "\u907f\u5751",
    "\u6ce8\u610f",
    "\u9002\u5408",
    "\u522b\u4f4f",
    "\u4e00\u5b9a\u8981",
)


class XiaohongshuConnector:
    name = "xiaohongshu"
    base_url = "https://www.xiaohongshu.com"

    def __init__(self, settings: Settings, browser_manager: BrowserSessionManager):
        self.settings = settings
        self.browser_manager = browser_manager

    def _search_url(self, keyword: str) -> str:
        return (
            "https://www.xiaohongshu.com/search_result"
            f"?keyword={quote(keyword)}&source=web_search_result_notes&type=51"
        )

    def check_login_status(self, keyword: str) -> SourceStatus:
        detail = "Public access available."
        state = "ready"
        try:
            with self.browser_manager.open_page(self._search_url(keyword)) as (page, profile):
                text = clean_text(page.locator("body").inner_text(timeout=4000))
                if any(token in text for token in LOGIN_HINTS):
                    state = "awaiting_login"
                    detail = f"{profile.browser_name} profile is not logged in to Xiaohongshu."
                else:
                    detail = f"Using {profile.browser_name} profile."
        except Exception as exc:
            state = "failed"
            detail = f"Browser launch failed: {exc}"
        return SourceCheck(source=self.name, state=state, detail=detail, checked_at=datetime.now().replace(microsecond=0)).to_status()

    def collect(self, keyword: str) -> tuple[list[GuideNote], list[SourceEvidence], list[str]]:
        warnings: list[str] = []
        try:
            with self.browser_manager.open_page(self._search_url(keyword)) as (page, _profile):
                page.wait_for_timeout(1800)
                html = page.content()
        except Exception as exc:
            return [], [], [f"\u5c0f\u7ea2\u4e66\u6293\u53d6\u5931\u8d25: {exc}"]
        notes = self.parse_search_results(html)
        if not notes:
            warnings.append("\u5c0f\u7ea2\u4e66\u7ed3\u679c\u4e3a\u7a7a\uff0c\u5df2\u8df3\u8fc7\u653b\u7565\u52a0\u6743\u3002")
        evidences = [
            SourceEvidence(
                source=self.name,
                title=note.title,
                url=note.url,
                captured_at=datetime.now().replace(microsecond=0),
                excerpt=note.excerpt[:120],
            )
            for note in notes[:5]
        ]
        return notes[: self.settings.xiaohongshu_result_limit], evidences, warnings

    def parse_search_results(self, html: str) -> list[GuideNote]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("section, div.note-item, div[data-testid*='note'], article")
        results: list[GuideNote] = []
        seen: set[str] = set()
        for card in cards:
            title = clean_text(" ".join(node.get_text(" ", strip=True) for node in card.select("h1, h2, h3, a, span")[:6]))
            if len(title) < 6:
                continue
            link = card.find("a", href=True)
            href = absolute_url(self.base_url, link["href"]) if link else self.base_url
            if href in seen:
                continue
            text = clean_text(card.get_text(" ", strip=True))
            if not text:
                continue
            results.append(
                GuideNote(
                    title=title[:80],
                    url=href,
                    excerpt=text[:220],
                    pois=self._extract_pois(text)[:6],
                    tips=self._extract_tips(text)[:4],
                )
            )
            seen.add(href)
        return results[:20]

    def _extract_pois(self, text: str) -> list[str]:
        suffixes = "|".join(POI_SUFFIXES)
        patterns = re.findall(rf"([\u4e00-\u9fa5A-Za-z]{{2,16}}(?:{suffixes}))", text)
        unique: list[str] = []
        for item in patterns:
            item = self._normalize_poi(item)
            if any(blocked in item for blocked in POI_EXCLUDES):
                continue
            if item not in unique:
                unique.append(item)
        return unique

    def _normalize_poi(self, value: str) -> str:
        trimmed = re.sub(r"^(?:\u5728|\u53bb|\u5230)?", "", value)
        trimmed = re.sub(r"^[\u4e00-\u9fa5A-Za-z]{0,6}\u8fb9\u7684", "", trimmed)
        trimmed = re.sub(r"^[\u4e00-\u9fa5A-Za-z]{0,6}\u9644\u8fd1\u7684", "", trimmed)
        return trimmed or value

    def _extract_tips(self, text: str) -> list[str]:
        fragments = re.split(r"[\u3002\uff01!\uff1f?\n]", text)
        tips = [clean_text(fragment) for fragment in fragments if any(token in fragment for token in TIP_HINTS)]
        return [tip[:80] for tip in tips if tip][:4]
