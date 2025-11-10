from __future__ import annotations

import json
from pathlib import Path

from aegis.reports.quarantine import build_report, write_quarantine_reports


def test_quarantine_report_generation(tmp_path: Path) -> None:
    payload = tmp_path / "sample.bin"
    payload.write_bytes(b"binary-data")
    report = build_report(payload, reason="suspicious archive", source="downloads", indicators=["payload.exe"], rule_id="archive_heuristic")
    json_path, html_path = write_quarantine_reports(report, tmp_path / "reports")
    assert json_path.exists()
    assert html_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["reason"] == "suspicious archive"
    assert data["rule_id"] == "archive_heuristic"
    assert "sha256" in data
    html = html_path.read_text(encoding="utf-8")
    assert "Quarantine Report" in html
    assert "payload.exe" in html
