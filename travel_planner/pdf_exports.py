from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


def render_url_pdf(url: str, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2200})
        page.goto(url, wait_until="networkidle", timeout=90000)
        page.pdf(
            path=str(output),
            format="A4",
            print_background=True,
            margin={"top": "12mm", "right": "10mm", "bottom": "12mm", "left": "10mm"},
            scale=0.86,
        )
        browser.close()
    return output
