from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TRACKED_BINARY_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".p12",
    ".pem",
    ".key",
    ".crt",
    ".har",
    ".trace",
    ".zip",
    ".xlsx",
    ".xls",
}
TEXT_SUFFIX_ALLOWLIST = {
    ".md",
    ".py",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".jsonl",
    ".ini",
    ".cfg",
    ".txt",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".csv",
    ".svg",
}

WINDOWS_LOCAL_PATH_RE = re.compile(
    r"(?i)\b[A-Z]:(?:\\|/)(?:Users|Documents and Settings|code|work|home|Desktop|Downloads)(?:\\|/)[^\s\"'<>]+"
)
UNIX_LOCAL_PATH_RE = re.compile(r"(?<!<)/(?:Users|home)/[^\s\"'<>/]+(?:/[^\s\"'<>]+)+")
PRIVATE_IP_RE = re.compile(
    r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})\b"
)
TUNNEL_HOST_RE = re.compile(
    r"\b(?:[a-z0-9-]+\.)+(?:trycloudflare\.com|loca\.lt|ngrok-free\.app|ngrok\.io)\b",
    re.IGNORECASE,
)

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("amap_key", re.compile(r"AMAP_(?:API_KEY|JS_API_KEY|SECURITY_JS_CODE)\s*[:=]\s*[\"']?[A-Za-z0-9._-]{8,}")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("github_pat", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
)


@dataclass(slots=True)
class Finding:
    path: Path
    kind: str
    message: str
    line_no: int | None = None
    line: str = ""


def _repo_root(path: str | Path | None = None) -> Path:
    return Path(path).resolve() if path else REPO_ROOT


def list_tracked_files(root: Path) -> list[Path]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except Exception:
        return [
            path
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts
        ]
    return [root / Path(item.decode("utf-8")) for item in completed.stdout.split(b"\x00") if item]


def is_binary_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIX_ALLOWLIST:
        return False
    if path.suffix.lower() in TRACKED_BINARY_SUFFIXES:
        return True
    try:
        chunk = path.read_bytes()[:2048]
    except OSError:
        return False
    return b"\x00" in chunk


def _iter_text_findings(path: Path, root: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        findings.append(Finding(path.relative_to(root), "encoding", "File is not valid UTF-8 text."))
        return findings
    for idx, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue

        if PRIVATE_IP_RE.search(raw_line) and "<LAN-IP>" not in raw_line:
            findings.append(
                Finding(path.relative_to(root), "private_ip", "Private LAN IP found in tracked text.", idx, stripped)
            )
        if WINDOWS_LOCAL_PATH_RE.search(raw_line) or UNIX_LOCAL_PATH_RE.search(raw_line):
            findings.append(
                Finding(path.relative_to(root), "local_path", "Local absolute filesystem path found.", idx, stripped)
            )
        if TUNNEL_HOST_RE.search(raw_line):
            findings.append(
                Finding(path.relative_to(root), "public_tunnel", "Temporary public tunnel host found.", idx, stripped)
            )
        for kind, pattern in SECRET_PATTERNS:
            if pattern.search(raw_line):
                findings.append(
                    Finding(path.relative_to(root), kind, "Potential secret detected in tracked text.", idx, stripped)
                )
    return findings


def scan_paths(paths: list[Path], root: Path | None = None) -> list[Finding]:
    repo_root = _repo_root(root)
    findings: list[Finding] = []
    for path in paths:
        resolved = path.resolve()
        if not resolved.exists():
            continue
        rel = resolved.relative_to(repo_root)
        if is_binary_file(resolved):
            if resolved.suffix.lower() in TRACKED_BINARY_SUFFIXES:
                findings.append(Finding(rel, "tracked_binary", "Tracked binary or export artifact should not be published."))
            continue
        findings.extend(_iter_text_findings(resolved, repo_root))
    return findings


def scan_repository(root: Path | None = None) -> list[Finding]:
    repo_root = _repo_root(root)
    return scan_paths(list_tracked_files(repo_root), repo_root)


def _format_finding(finding: Finding) -> str:
    location = str(finding.path)
    if finding.line_no is not None:
        location += f":{finding.line_no}"
    suffix = f" | {finding.line}" if finding.line else ""
    return f"[{finding.kind}] {location} - {finding.message}{suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check tracked files for secrets and local machine leakage before publishing.")
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root to scan.")
    args = parser.parse_args(argv)
    root = _repo_root(args.root)
    findings = scan_repository(root)
    if not findings:
        print(f"Publish check passed. Scanned {len(list_tracked_files(root))} tracked files.")
        return 0
    print("Publish check failed. Resolve the following findings before pushing:\n")
    for finding in findings:
        print(_format_finding(finding))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
