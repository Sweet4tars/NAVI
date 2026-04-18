from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .config import Settings, load_settings
from .share_public import clear_public_base_url, get_public_base_url, set_public_base_url


TRYCLOUDFLARE_PATTERN = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com", re.IGNORECASE)


def find_cloudflared_binary(settings: Settings, explicit_binary: str = "") -> str:
    candidates: list[str] = []
    for candidate in (explicit_binary, settings.cloudflared_binary, shutil.which("cloudflared") or ""):
        if candidate:
            candidates.append(candidate)
    if os.name == "nt":
        candidates.extend(
            [
                r"C:\Program Files\cloudflared\cloudflared.exe",
                r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
            ]
        )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return str(path)
    raise FileNotFoundError(
        "cloudflared executable not found. Set TRAVEL_PLANNER_CLOUDFLARED_BIN or install cloudflared."
    )


def _read_pid(settings: Settings) -> int | None:
    if not settings.cloudflared_pid_path.exists():
        return None
    content = settings.cloudflared_pid_path.read_text(encoding="utf-8").strip()
    return int(content) if content.isdigit() else None


def cloudflared_status(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or load_settings()
    return {
        "pid": _read_pid(settings),
        "public_url": get_public_base_url(settings) or None,
        "log_file": str(settings.cloudflared_log_path),
        "pid_file": str(settings.cloudflared_pid_path),
    }


def stop_cloudflared_tunnel(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or load_settings()
    pid = _read_pid(settings)
    stopped = False
    error = ""
    if pid is not None:
        try:
            if os.name == "nt":
                completed = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                stopped = completed.returncode == 0
                if completed.returncode != 0:
                    error = (completed.stderr or completed.stdout).strip()
            else:
                os.kill(pid, 15)
                stopped = True
        except Exception as exc:
            error = str(exc)
    if settings.cloudflared_pid_path.exists():
        settings.cloudflared_pid_path.unlink()
    clear_public_base_url(settings)
    return {
        "stopped": stopped,
        "pid": pid,
        "error": error,
        "public_url_cleared": True,
    }


def start_cloudflared_tunnel(
    *,
    target_url: str,
    settings: Settings | None = None,
    binary: str = "",
    timeout_seconds: int = 25,
) -> dict[str, object]:
    settings = settings or load_settings()
    stop_cloudflared_tunnel(settings)
    binary_path = find_cloudflared_binary(settings, binary)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    settings.cloudflared_log_path.write_text("", encoding="utf-8")

    command = [binary_path, "tunnel", "--url", target_url, "--no-autoupdate"]
    log_handle = settings.cloudflared_log_path.open("a", encoding="utf-8")
    kwargs: dict[str, object] = {
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "cwd": str(settings.data_dir),
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    log_handle.close()
    settings.cloudflared_pid_path.write_text(str(process.pid), encoding="utf-8")

    public_url = ""
    deadline = time.time() + max(timeout_seconds, 5)
    while time.time() < deadline:
        if process.poll() is not None:
            break
        if settings.cloudflared_log_path.exists():
            content = settings.cloudflared_log_path.read_text(encoding="utf-8", errors="ignore")
            match = TRYCLOUDFLARE_PATTERN.search(content)
            if match:
                public_url = match.group(0)
                break
        time.sleep(0.5)

    if not public_url:
        tail = ""
        if settings.cloudflared_log_path.exists():
            content = settings.cloudflared_log_path.read_text(encoding="utf-8", errors="ignore")
            tail = "\n".join(content.splitlines()[-12:])
        raise RuntimeError(f"cloudflared tunnel started but public url was not detected.\n{tail}".strip())

    set_public_base_url(settings, public_url)
    return {
        "pid": process.pid,
        "target_url": target_url,
        "public_url": public_url,
        "log_file": str(settings.cloudflared_log_path),
        "pid_file": str(settings.cloudflared_pid_path),
        "command": command,
    }
