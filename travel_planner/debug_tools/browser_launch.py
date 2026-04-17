from __future__ import annotations

from pathlib import Path
import subprocess


def launch_manual_managed_chromium(*, chrome_path: str | Path, profile_dir: str | Path, url: str, remote_debugging_port: int = 9222) -> dict:
    chrome = Path(chrome_path)
    profile = Path(profile_dir)
    if not chrome.exists():
        raise FileNotFoundError(f"Chrome executable not found: {chrome}")
    profile.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [
            str(chrome),
            f"--user-data-dir={profile}",
            f"--remote-debugging-port={remote_debugging_port}",
            "--new-window",
            url,
        ],
        cwd=str(profile.parent),
    )
    return {
        "pid": process.pid,
        "chrome_path": str(chrome),
        "profile_dir": str(profile),
        "remote_debugging_port": remote_debugging_port,
        "url": url,
    }
