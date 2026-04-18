from pathlib import Path

from travel_planner.publish_check import scan_paths


def test_publish_check_ignores_placeholder_and_localhost(tmp_path: Path):
    sample = tmp_path / "README.md"
    sample.write_text(
        "# Demo\n\ncd <repo-root>\nOpen http://127.0.0.1:8091 to preview.\n",
        encoding="utf-8",
    )
    findings = scan_paths([sample], root=tmp_path)
    assert findings == []


def test_publish_check_detects_private_lan_ip(tmp_path: Path):
    sample = tmp_path / "notes.md"
    sample.write_text("Share URL: http://192.168.1.23:8091/share/demo\n", encoding="utf-8")
    findings = scan_paths([sample], root=tmp_path)
    assert any(item.kind == "private_ip" for item in findings)


def test_publish_check_detects_local_absolute_path(tmp_path: Path):
    sample = tmp_path / "notes.md"
    sample.write_text(r"Debug path: D:\code\travel-planner-agent\.data\travel_planner.db" + "\n", encoding="utf-8")
    findings = scan_paths([sample], root=tmp_path)
    assert any(item.kind == "local_path" for item in findings)


def test_publish_check_detects_potential_secret(tmp_path: Path):
    sample = tmp_path / "env.md"
    sample.write_text('AMAP_API_KEY="abcdEFGH12345678"\n', encoding="utf-8")
    findings = scan_paths([sample], root=tmp_path)
    assert any(item.kind == "amap_key" for item in findings)


def test_publish_check_detects_tracked_binary_exports(tmp_path: Path):
    sample = tmp_path / "trip.xlsx"
    sample.write_bytes(b"PK\x03\x04demo")
    findings = scan_paths([sample], root=tmp_path)
    assert any(item.kind == "tracked_binary" for item in findings)


def test_publish_check_allows_generic_tunnel_vendor_name(tmp_path: Path):
    sample = tmp_path / "docs.md"
    sample.write_text("默认走 trycloudflare.com 的快速隧道。\n", encoding="utf-8")
    findings = scan_paths([sample], root=tmp_path)
    assert findings == []
