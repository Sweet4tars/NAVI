from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..config import Settings, load_settings

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None


INTERESTING_RESOURCE_TYPES = {"document", "xhr", "fetch"}
KNOWN_NON_LIST_PATTERNS = (
    "getcitysuggestv4",
    "getcityurl",
    "citytimezone.jsp",
    "hoteldiv.jsp",
    "hotkeywords.jsp",
)
LIST_SIGNAL_PATTERNS = (
    "hotelname",
    "hotelseq",
    "priceinfo",
    "pricedecimal",
    "jumpdetailurl",
    "distanceandposition",
    "commentinfo",
)


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _is_interesting(url: str, resource_type: str) -> bool:
    lowered = url.lower()
    return resource_type in INTERESTING_RESOURCE_TYPES and (
        "qunar" in lowered or "l-hs.qunar.com" in lowered or "hotel" in lowered
    )


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    blocked = {"host", "content-length", "connection"}
    return {key: value for key, value in headers.items() if key.lower() not in blocked}


def _score_event(event: dict) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    url = str(event.get("url", "")).lower()
    body = str(event.get("response_body_preview", "")).lower()
    request_body = str(event.get("post_data", "")).lower()

    if any(pattern in url for pattern in KNOWN_NON_LIST_PATTERNS):
        score -= 40
        reasons.append("known-support-endpoint")
    if "/api/hs/suggestion" in url:
        score += 25
        reasons.append("hotel-suggestion-endpoint")
    if "/cn/" in url or "/city/" in url or "hotelcn" in url:
        score += 20
        reasons.append("hotel-route-shape")
    if "search" in url or "list" in url or "hotel" in url:
        score += 12
        reasons.append("search-or-list-token")
    if any(signal in body for signal in LIST_SIGNAL_PATTERNS):
        score += 40
        reasons.append("list-payload-signals")
    if any(signal in request_body for signal in ("cityurl", "fromdate", "todate", "q=")):
        score += 10
        reasons.append("search-parameter-shape")
    if "www.qunar.com" in body and "Moved Permanently" in body:
        score -= 30
        reasons.append("homepage-redirect")
    if event.get("status") == 200:
        score += 5
        reasons.append("http-200")
    return score, reasons


def find_capture_candidates(events: list[dict]) -> list[dict]:
    ranked: list[dict] = []
    for event in events:
        if event.get("kind") != "response":
            continue
        score, reasons = _score_event(event)
        ranked.append(
            {
                "id": event["id"],
                "url": event["url"],
                "resource_type": event["resource_type"],
                "status": event.get("status"),
                "score": score,
                "reasons": reasons,
            }
        )
    return sorted(ranked, key=lambda item: (-item["score"], item["id"]))


def _capture_storage(page) -> dict:
    return page.evaluate(
        """
() => ({
  localStorage: Object.fromEntries(Object.entries(localStorage)),
  sessionStorage: Object.fromEntries(Object.entries(sessionStorage)),
  cookie: document.cookie
})
"""
    )


def capture_qunar_session(
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
    profile_dir: str | Path | None = None,
    start_url: str = "https://hotel.qunar.com/global/",
    headless: bool = False,
    duration_seconds: int | None = None,
    city: str | None = None,
    keyword: str | None = None,
) -> dict:
    if sync_playwright is None:
        raise RuntimeError("playwright is not installed in the current environment.")
    settings = settings or load_settings()
    base_dir = Path(output_dir or (settings.data_dir / "qunar-captures"))
    base_dir.mkdir(parents=True, exist_ok=True)
    session_dir = base_dir / f"session-{_now_stamp()}"
    session_dir.mkdir(parents=True, exist_ok=True)
    browser_profile_dir = Path(profile_dir or settings.browser_profile_dir)
    browser_profile_dir.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []
    counter = {"value": 0}
    cdp_indices: dict[str, int] = {}

    def next_id() -> int:
        counter["value"] += 1
        return counter["value"]

    def attach_page(page, playwright_context) -> None:
        cdp = playwright_context.new_cdp_session(page)
        cdp.send("Network.enable")

        def on_cdp_response(params) -> None:
            response = params.get("response", {})
            url = response.get("url", "")
            resource_type = str(params.get("type", "")).lower()
            if resource_type == "script":
                resource_type = "fetch"
            if not _is_interesting(url, resource_type):
                return
            event = {
                "id": next_id(),
                "kind": "response",
                "ts": time.time(),
                "method": "",
                "url": url,
                "resource_type": resource_type,
                "status": response.get("status"),
                "headers": _sanitize_headers(response.get("headers", {})),
                "post_data": "",
                "response_body_preview": "",
                "cdp_request_id": params.get("requestId"),
            }
            events.append(event)
            if params.get("requestId"):
                cdp_indices[params["requestId"]] = len(events) - 1

        def on_cdp_finished(params) -> None:
            request_id = params.get("requestId")
            if not request_id or request_id not in cdp_indices:
                return
            try:
                payload = cdp.send("Network.getResponseBody", {"requestId": request_id})
            except Exception:
                return
            body = payload.get("body", "")
            if payload.get("base64Encoded"):
                try:
                    import base64

                    body = base64.b64decode(body).decode("utf-8", errors="ignore")
                except Exception:
                    body = ""
            events[cdp_indices[request_id]]["response_body_preview"] = str(body)[:20000]

        cdp.on("Network.responseReceived", on_cdp_response)
        cdp.on("Network.loadingFinished", on_cdp_finished)

        def on_request(request) -> None:
            if not _is_interesting(request.url, request.resource_type):
                return
            events.append(
                {
                    "id": next_id(),
                    "kind": "request",
                    "ts": time.time(),
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                    "headers": _sanitize_headers(request.headers),
                    "post_data": request.post_data or "",
                }
            )

        def on_response(response) -> None:
            request = response.request
            if not _is_interesting(request.url, request.resource_type):
                return
            preview = ""
            try:
                content_type = response.headers.get("content-type", "")
                if any(token in content_type.lower() for token in ("json", "javascript", "text", "html")):
                    preview = response.text()[:20000]
            except Exception:
                preview = ""
            events.append(
                {
                    "id": next_id(),
                    "kind": "response",
                    "ts": time.time(),
                    "method": request.method,
                    "url": response.url,
                    "resource_type": request.resource_type,
                    "status": response.status,
                    "headers": _sanitize_headers(response.headers),
                    "post_data": request.post_data or "",
                    "response_body_preview": preview,
                }
            )

        page.on("request", on_request)
        page.on("response", on_response)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(browser_profile_dir),
            headless=headless,
            viewport={"width": 1440, "height": 1024},
            ignore_https_errors=True,
        )
        try:
            for page in context.pages:
                attach_page(page, context)
            context.on("page", lambda page: attach_page(page, context))
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(start_url, wait_until="domcontentloaded", timeout=settings.browser_timeout_ms)
            print(f"Qunar capture started in {'headless' if headless else 'visible'} mode.")
            if city:
                print(f"Running scripted search flow for city={city!r} keyword={keyword!r}")
                script_meta = _run_scripted_search(page, city=city, keyword=keyword)
            else:
                print("Use the opened browser to perform hotel search flow.")
                script_meta = {}

            if duration_seconds is not None:
                print(f"Capturing for {duration_seconds} seconds...")
                page.wait_for_timeout(duration_seconds * 1000)
            else:
                print("Press Enter in this terminal to stop capture.")
                input()

            storage_snapshot = _capture_storage(page)
            payload = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "start_url": start_url,
                "events": events,
                "cookies": context.cookies(),
                "storage": storage_snapshot,
                "candidates": find_capture_candidates(events),
                "script_meta": script_meta,
            }
        finally:
            context.close()

    session_file = session_dir / "session.json"
    session_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    candidates_file = session_dir / "candidates.json"
    candidates_file.write_text(json.dumps(payload["candidates"], ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "session_dir": str(session_dir),
        "session_file": str(session_file),
        "candidates_file": str(candidates_file),
        "profile_dir": str(browser_profile_dir),
        "event_count": len(events),
        "candidate_count": len(payload["candidates"]),
    }


def capture_qunar_session_attached(
    *,
    cdp_endpoint: str,
    output_dir: str | Path | None = None,
    duration_seconds: int | None = None,
) -> dict:
    if sync_playwright is None:
        raise RuntimeError("playwright is not installed in the current environment.")

    settings = load_settings()
    base_dir = Path(output_dir or (settings.data_dir / "qunar-captures"))
    base_dir.mkdir(parents=True, exist_ok=True)
    session_dir = base_dir / f"session-{_now_stamp()}"
    session_dir.mkdir(parents=True, exist_ok=True)

    events: list[dict] = []
    counter = {"value": 0}
    cdp_indices: dict[str, int] = {}

    def next_id() -> int:
        counter["value"] += 1
        return counter["value"]

    def attach_page(page, playwright_context) -> None:
        cdp = playwright_context.new_cdp_session(page)
        cdp.send("Network.enable")

        def on_request(request) -> None:
            if not _is_interesting(request.url, request.resource_type):
                return
            events.append(
                {
                    "id": next_id(),
                    "kind": "request",
                    "ts": time.time(),
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                    "headers": _sanitize_headers(request.headers),
                    "post_data": request.post_data or "",
                }
            )

        def on_cdp_response(params) -> None:
            response = params.get("response", {})
            url = response.get("url", "")
            resource_type = str(params.get("type", "")).lower()
            if resource_type == "script":
                resource_type = "fetch"
            if not _is_interesting(url, resource_type):
                return
            event = {
                "id": next_id(),
                "kind": "response",
                "ts": time.time(),
                "method": "",
                "url": url,
                "resource_type": resource_type,
                "status": response.get("status"),
                "headers": _sanitize_headers(response.get("headers", {})),
                "post_data": "",
                "response_body_preview": "",
                "cdp_request_id": params.get("requestId"),
            }
            events.append(event)
            if params.get("requestId"):
                cdp_indices[params["requestId"]] = len(events) - 1

        def on_cdp_finished(params) -> None:
            request_id = params.get("requestId")
            if not request_id or request_id not in cdp_indices:
                return
            try:
                payload = cdp.send("Network.getResponseBody", {"requestId": request_id})
            except Exception:
                return
            body = payload.get("body", "")
            if payload.get("base64Encoded"):
                try:
                    import base64

                    body = base64.b64decode(body).decode("utf-8", errors="ignore")
                except Exception:
                    body = ""
            events[cdp_indices[request_id]]["response_body_preview"] = str(body)[:20000]

        page.on("request", on_request)
        cdp.on("Network.responseReceived", on_cdp_response)
        cdp.on("Network.loadingFinished", on_cdp_finished)

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_endpoint)
        try:
            contexts = browser.contexts
            if not contexts:
                raise RuntimeError("No browser context found at the CDP endpoint.")
            context = contexts[0]
            pages = context.pages
            if not pages:
                raise RuntimeError("No page found in the attached browser context.")
            for page in pages:
                attach_page(page, context)
            context.on("page", lambda page: attach_page(page, context))

            print("Attached to existing browser via CDP.")
            if duration_seconds is not None:
                print(f"Capturing for {duration_seconds} seconds...")
                pages[0].wait_for_timeout(duration_seconds * 1000)
            else:
                print("Perform the Qunar search manually in the browser, then press Enter here to stop capture.")
                input()

            storage_snapshot = _capture_storage(pages[0])
            payload = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "start_url": pages[0].url,
                "events": events,
                "cookies": context.cookies(),
                "storage": storage_snapshot,
                "candidates": find_capture_candidates(events),
                "attached": True,
                "cdp_endpoint": cdp_endpoint,
            }
        finally:
            browser.close()

    session_file = session_dir / "session.json"
    session_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    candidates_file = session_dir / "candidates.json"
    candidates_file.write_text(json.dumps(payload["candidates"], ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "session_dir": str(session_dir),
        "session_file": str(session_file),
        "candidates_file": str(candidates_file),
        "event_count": len(events),
        "candidate_count": len(payload["candidates"]),
        "attached": True,
    }


def _run_scripted_search(page, *, city: str, keyword: str | None = None) -> dict:
    result: dict[str, object] = {"city": city, "keyword": keyword or ""}
    page.wait_for_timeout(1000)

    city_input = page.locator("form#interForm input").nth(0)
    city_input.click()
    city_input.fill(city)
    page.wait_for_timeout(1200)

    suggestion_rows = page.locator(".popContainer tr.item")
    result["suggestion_count"] = suggestion_rows.count()
    if suggestion_rows.count() > 0:
        suggestion_rows.first.click(timeout=5000)
        page.wait_for_timeout(1200)

    if keyword:
        keyword_input = page.locator("form#interForm input").nth(1)
        keyword_input.fill("")
        page.evaluate(
            """
(value) => {
  const input = document.querySelectorAll('form#interForm input')[1];
  input.focus();
  input.value = value;
  for (const type of ['input', 'change', 'keyup']) {
    input.dispatchEvent(new Event(type, { bubbles: true }));
  }
}
""",
            keyword,
        )
        page.wait_for_timeout(2500)

    popup_url = ""
    try:
        with page.expect_popup(timeout=8000) as popup_info:
            page.locator("div.search-btn").click(force=True)
        popup = popup_info.value
        popup.wait_for_load_state("domcontentloaded", timeout=15000)
        popup.wait_for_timeout(3000)
        popup_url = popup.url
    except Exception as exc:
        result["script_error"] = str(exc)

    result["popup_url"] = popup_url
    result["city_input_after"] = page.locator("form#interForm input").nth(0).input_value()
    return result


def replay_captured_request(
    *,
    capture_file: str | Path,
    match: str,
    request_ordinal: int = 0,
    output_file: str | Path | None = None,
) -> dict:
    payload = json.loads(Path(capture_file).read_text(encoding="utf-8"))
    requests = [event for event in payload.get("events", []) if event.get("kind") == "request" and match.lower() in str(event.get("url", "")).lower()]
    if not requests:
        raise ValueError(f"No captured request matched '{match}'.")
    if request_ordinal >= len(requests):
        raise IndexError("request_ordinal is out of range.")

    request_event = requests[request_ordinal]
    cookie_header = _build_cookie_header(payload.get("cookies", []), request_event["url"])
    headers = dict(request_event.get("headers", {}))
    if cookie_header:
        headers["Cookie"] = cookie_header
    request = Request(
        request_event["url"],
        headers=headers,
        data=(request_event.get("post_data") or "").encode("utf-8") if request_event.get("method") == "POST" else None,
        method=request_event.get("method", "GET"),
    )
    with urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8", errors="ignore")
        result = {
            "url": request_event["url"],
            "status": response.status,
            "headers": dict(response.headers),
            "body_preview": body[:20000],
        }
    if output_file:
        Path(output_file).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _build_cookie_header(cookies: list[dict], url: str) -> str:
    host = urlparse(url).hostname or ""
    pairs = []
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lstrip(".")
        if domain and (host == domain or host.endswith("." + domain)):
            pairs.append(f"{cookie['name']}={cookie['value']}")
    return "; ".join(pairs)
