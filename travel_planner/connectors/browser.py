from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import re

from ..config import Settings

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None


@dataclass(slots=True)
class BrowserProfile:
    browser_name: str
    channel: str | None
    user_data_dir: Path


class BrowserSessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _candidate_profiles(self) -> list[BrowserProfile]:
        local = Path(os.getenv("LOCALAPPDATA", ""))
        candidates = [
            BrowserProfile("Edge", "msedge", local / "Microsoft" / "Edge" / "User Data"),
            BrowserProfile("Managed Chromium", None, self.settings.browser_profile_dir),
            BrowserProfile("Chrome", "chrome", local / "Google" / "Chrome" / "User Data"),
        ]
        return [candidate for candidate in candidates if candidate.user_data_dir.exists()]

    @contextmanager
    def open_page(self, url: str, *, wait_until: str = "domcontentloaded"):
        if sync_playwright is None:
            raise RuntimeError("playwright is not installed in the current environment.")
        errors: list[str] = []
        with sync_playwright() as playwright:
            for profile in self._candidate_profiles():
                kwargs = {
                    "headless": self.settings.browser_headless,
                    "viewport": {"width": 1440, "height": 1024},
                    "ignore_https_errors": True,
                }
                if profile.channel:
                    kwargs["channel"] = profile.channel
                try:
                    context = playwright.chromium.launch_persistent_context(str(profile.user_data_dir), **kwargs)
                    try:
                        page = context.pages[0] if context.pages else context.new_page()
                        page.goto(url, wait_until=wait_until, timeout=self.settings.browser_timeout_ms)
                        yield page, profile
                        return
                    finally:
                        context.close()
                except Exception as exc:
                    errors.append(self._format_exception(profile.browser_name, exc))
                    continue
        raise RuntimeError(" ; ".join(errors) if errors else "No browser profile available.")

    def _format_exception(self, browser_name: str, exc: Exception) -> str:
        text = re.sub(r"\s+", " ", str(exc)).strip()
        text = text.split("Browser logs:")[0].strip()
        text = text.split("Call log:")[0].strip()
        if "Target page, context or browser has been closed" in text:
            text = "browser closed during launch or navigation"
        if "exitCode=21" in text:
            text = "profile appears unavailable or already in use"
        if "Timeout" in text and "exceeded" in text:
            text = "navigation timed out"
        return f"{browser_name}: {text}"
