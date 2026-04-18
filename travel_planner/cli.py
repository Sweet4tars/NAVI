from __future__ import annotations

import argparse
import json
import sys

import uvicorn

from .debug_tools import capture_qunar_session, capture_qunar_session_attached, replay_captured_request
from .debug_tools.browser_launch import launch_manual_managed_chromium
from .tunnel import cloudflared_status, start_cloudflared_tunnel, stop_cloudflared_tunnel
from .main import create_app
from .schemas import Travelers, TripRequest
from .service import PlanningService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Travel Planner Agent CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="Start the FastAPI web server.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8091)

    plan = subparsers.add_parser("plan", help="Run a synchronous planning job and print JSON.")
    plan.add_argument("--origin", required=True)
    plan.add_argument("--destination", required=True)
    plan.add_argument("--start-date", required=True)
    plan.add_argument("--end-date")
    plan.add_argument("--days", type=int)
    plan.add_argument("--adults", type=int, default=2)
    plan.add_argument("--children", type=int, default=0)
    plan.add_argument("--transport-mode", choices=["rail", "drive"], required=True)
    plan.add_argument("--hotel-budget-min", type=float)
    plan.add_argument("--hotel-budget-max", type=float)
    plan.add_argument("--hotel-star-level", type=int)
    plan.add_argument("--pace", choices=["slow", "balanced", "dense"], default="balanced")
    plan.add_argument("--must-go", default="")
    plan.add_argument("--avoid", default="")
    plan.add_argument("--hotel-preferences", default="")
    plan.add_argument("--parking-required", action="store_true")

    qunar_capture = subparsers.add_parser("qunar-capture", help="Open a visible browser and capture Qunar hotel requests.")
    qunar_capture.add_argument("--start-url", default="https://hotel.qunar.com/global/")
    qunar_capture.add_argument("--output-dir")
    qunar_capture.add_argument("--profile-dir")
    qunar_capture.add_argument("--duration-seconds", type=int)
    qunar_capture.add_argument("--headless", action="store_true")
    qunar_capture.add_argument("--city")
    qunar_capture.add_argument("--keyword")

    qunar_replay = subparsers.add_parser("qunar-replay", help="Replay a captured Qunar request by URL substring match.")
    qunar_replay.add_argument("--capture-file", required=True)
    qunar_replay.add_argument("--match", required=True)
    qunar_replay.add_argument("--request-ordinal", type=int, default=0)
    qunar_replay.add_argument("--output-file")

    qunar_open_manual = subparsers.add_parser("qunar-open-manual", help="Open a manual managed Chromium window for Qunar capture.")
    qunar_open_manual.add_argument("--chrome-path", required=True)
    qunar_open_manual.add_argument("--profile-dir", required=True)
    qunar_open_manual.add_argument("--url", default="https://hotel.qunar.com/global/")
    qunar_open_manual.add_argument("--remote-debugging-port", type=int, default=9222)

    qunar_capture_attach = subparsers.add_parser("qunar-capture-attach", help="Attach capture to an already opened manual browser via CDP.")
    qunar_capture_attach.add_argument("--cdp-endpoint", default="http://127.0.0.1:9222")
    qunar_capture_attach.add_argument("--output-dir")
    qunar_capture_attach.add_argument("--duration-seconds", type=int)

    cloudflared_start = subparsers.add_parser("cloudflared-start", help="Start a detached cloudflared quick tunnel for the local share server.")
    cloudflared_start.add_argument("--target-url", default="http://127.0.0.1:8091")
    cloudflared_start.add_argument("--binary", default="")
    cloudflared_start.add_argument("--timeout-seconds", type=int, default=25)

    subparsers.add_parser("cloudflared-stop", help="Stop the detached cloudflared tunnel and clear the saved public URL.")
    subparsers.add_parser("cloudflared-status", help="Print the current cloudflared tunnel status and saved public URL.")
    return parser


def run_plan(args: argparse.Namespace) -> int:
    service = PlanningService()
    request = TripRequest(
        origin=args.origin,
        destination=args.destination,
        start_date=args.start_date,
        end_date=args.end_date,
        days=args.days,
        travelers=Travelers(adults=args.adults, children=args.children),
        transport_mode=args.transport_mode,
        hotel_budget_min=args.hotel_budget_min,
        hotel_budget_max=args.hotel_budget_max,
        hotel_star_level=args.hotel_star_level,
        pace=args.pace,
        must_go=args.must_go,
        avoid=args.avoid,
        hotel_preferences=args.hotel_preferences,
        parking_required=args.parking_required,
    )
    result, status, warnings, source_states = service.run_sync(request, persist_sources=True)
    payload = {
        "status": status,
        "warnings": warnings,
        "source_statuses": {key: value.model_dump(mode="json") for key, value in source_states.items()},
        "result": result.model_dump(mode="json"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def run_qunar_capture(args: argparse.Namespace) -> int:
    result = capture_qunar_session(
        start_url=args.start_url,
        output_dir=args.output_dir,
        profile_dir=args.profile_dir,
        duration_seconds=args.duration_seconds,
        headless=args.headless,
        city=args.city,
        keyword=args.keyword,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_qunar_replay(args: argparse.Namespace) -> int:
    result = replay_captured_request(
        capture_file=args.capture_file,
        match=args.match,
        request_ordinal=args.request_ordinal,
        output_file=args.output_file,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_qunar_open_manual(args: argparse.Namespace) -> int:
    result = launch_manual_managed_chromium(
        chrome_path=args.chrome_path,
        profile_dir=args.profile_dir,
        url=args.url,
        remote_debugging_port=args.remote_debugging_port,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_qunar_capture_attach(args: argparse.Namespace) -> int:
    result = capture_qunar_session_attached(
        cdp_endpoint=args.cdp_endpoint,
        output_dir=args.output_dir,
        duration_seconds=args.duration_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_cloudflared_start(args: argparse.Namespace) -> int:
    result = start_cloudflared_tunnel(
        target_url=args.target_url,
        binary=args.binary,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_cloudflared_stop(_: argparse.Namespace) -> int:
    print(json.dumps(stop_cloudflared_tunnel(), ensure_ascii=False, indent=2))
    return 0


def run_cloudflared_status(_: argparse.Namespace) -> int:
    print(json.dumps(cloudflared_status(), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "serve":
        uvicorn.run(create_app(), host=args.host, port=args.port)
        return 0
    if args.command == "plan":
        return run_plan(args)
    if args.command == "qunar-capture":
        return run_qunar_capture(args)
    if args.command == "qunar-replay":
        return run_qunar_replay(args)
    if args.command == "qunar-open-manual":
        return run_qunar_open_manual(args)
    if args.command == "qunar-capture-attach":
        return run_qunar_capture_attach(args)
    if args.command == "cloudflared-start":
        return run_cloudflared_start(args)
    if args.command == "cloudflared-stop":
        return run_cloudflared_stop(args)
    if args.command == "cloudflared-status":
        return run_cloudflared_status(args)
    parser.error("Unsupported command")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
