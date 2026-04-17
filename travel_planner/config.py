from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent


@dataclass(slots=True)
class Settings:
    app_name: str = "Travel Planner Agent"
    data_dir: Path = PROJECT_ROOT / ".data"
    db_path: Path = PROJECT_ROOT / ".data" / "travel_planner.db"
    browser_profile_dir: Path = PROJECT_ROOT / ".data" / "browser-profile"
    browser_timeout_ms: int = int(os.getenv("TRAVEL_PLANNER_BROWSER_TIMEOUT_MS", "12000"))
    browser_headless: bool = os.getenv("TRAVEL_PLANNER_BROWSER_HEADLESS", "false").lower() == "true"
    default_city_region: str = "中国"
    amap_api_key: str = os.getenv("AMAP_API_KEY", "").strip()
    xiaohongshu_result_limit: int = int(os.getenv("TRAVEL_PLANNER_XHS_LIMIT", "12"))
    hotel_result_limit: int = int(os.getenv("TRAVEL_PLANNER_HOTEL_LIMIT", "5"))
    rail_result_limit: int = int(os.getenv("TRAVEL_PLANNER_RAIL_LIMIT", "6"))
    fixture_mode: bool = os.getenv("TRAVEL_PLANNER_FIXTURE_MODE", "false").lower() == "true"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.browser_profile_dir.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
