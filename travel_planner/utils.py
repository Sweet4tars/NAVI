from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Iterable
from urllib.parse import urljoin


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def split_keywords(value: str | Iterable[str]) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，/、\n]+", value) if item.strip()]
    return [clean_text(str(item)) for item in value if clean_text(str(item))]


def extract_first_price(text: str) -> float | None:
    match = re.search(r"(?<!\d)(\d{2,5}(?:\.\d{1,2})?)(?!\d)", text.replace(",", ""))
    return float(match.group(1)) if match else None


def extract_rating(text: str) -> float | None:
    match = re.search(r"([1-5](?:\.\d)?)\s*(?:分|/5|点评)", text)
    return float(match.group(1)) if match else None


def duration_to_minutes(value: str) -> int:
    if not value:
        return 0
    match = re.search(r"(?:(\d+):)?(\d{1,2})", value)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        return hours * 60 + minutes
    hour_match = re.search(r"(\d+)\s*小时", value)
    minute_match = re.search(r"(\d+)\s*分", value)
    if hour_match:
        return int(hour_match.group(1)) * 60 + int(minute_match.group(1) or 0)
    return 0


def absolute_url(base: str, href: str) -> str:
    return urljoin(base, href or "")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def logistic(value: float) -> float:
    return 1 / (1 + math.exp(-value))
