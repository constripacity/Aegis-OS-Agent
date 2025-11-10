from pathlib import Path
from zipfile import ZipFile

from aegis.core.quarantine import Quarantine


def test_quarantine_creates_reports(app_config, tmp_path):
    app_config.quarantine_root = str(tmp_path / "Quarantine")
    app_config.reports_root = str(tmp_path / "Reports")
    archive = tmp_path / "payload.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("malware.exe", "echo bad")
    quarantine = Quarantine(app_config)
    indicators = quarantine.inspect_archive(archive)
    record = quarantine.isolate(archive, reason="contains executable", source="desktop", indicators=indicators, rule_id="archive_heuristic")
    assert Path(record.quarantined_path).exists()
    report_dir = Path(app_config.reports_root) / "quarantine"
    json_reports = list(report_dir.glob("*.json"))
    html_reports = list(report_dir.glob("*.html"))
    assert json_reports and html_reports
    payload = Path(record.report_json).read_text(encoding="utf-8")
    assert "malware.exe" in payload
    assert any("malware.exe" in html.read_text(encoding="utf-8") for html in html_reports)


def test_is_suspicious_archive_detects_executables(app_config, tmp_path):
    archive = tmp_path / "test.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("run.bat", "@echo off")
    quarantine = Quarantine(app_config)
    indicators = quarantine.inspect_archive(archive)
    assert indicators
    assert any(name.endswith("run.bat") for name in indicators)
