from __future__ import annotations

from urllib.parse import urljoin

from .config import Settings


def normalize_public_base_url(url: str) -> str:
    return str(url or "").strip().rstrip("/")


def get_public_base_url(settings: Settings) -> str:
    explicit = normalize_public_base_url(settings.public_base_url)
    if explicit:
        return explicit
    if settings.public_base_url_path.exists():
        return normalize_public_base_url(settings.public_base_url_path.read_text(encoding="utf-8"))
    return ""


def set_public_base_url(settings: Settings, url: str) -> str:
    normalized = normalize_public_base_url(url)
    if not normalized:
        raise ValueError("public base url cannot be empty")
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)
    settings.public_base_url_path.write_text(normalized + "\n", encoding="utf-8")
    return normalized


def clear_public_base_url(settings: Settings) -> None:
    if settings.public_base_url_path.exists():
        settings.public_base_url_path.unlink()


def build_external_url(base_url: str, path: str) -> str:
    normalized = normalize_public_base_url(base_url)
    if not normalized:
        return str(path)
    return urljoin(normalized + "/", str(path).lstrip("/"))
