"""Quarantine utilities for suspicious files."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from ..config.schema import AppConfig
from .utils import ensure_directory

LOGGER = logging.getLogger(__name__)


@dataclass
class QuarantineRecord:
    """Metadata describing a quarantined file."""

    original_path: str
    quarantined_path: str
    created_at: str
    reason: str
    source: str
    sha256: str
    indicators: list[str]


class Quarantine:
    """Move suspicious files into a read-only quarantine folder with reporting."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.root = Path(config.quarantine_root).expanduser()
        ensure_directory(self.root)
        self.reports_root = Path(config.reports_root).expanduser() / "quarantine"
        ensure_directory(self.reports_root)

    def inspect_archive(self, path: Path) -> list[str]:
        suffix = path.suffix.lower()
        if suffix in {".rar", ".7z"}:
            return ["archive format not inspectable"]
        if suffix != ".zip":
            return []
        indicators: list[str] = []
        try:
            with ZipFile(path) as archive:
                for name in archive.namelist():
                    lowered = Path(name).suffix.lower()
                    if lowered in {".exe", ".bat", ".cmd", ".msi", ".vbs", ".ps1", ".sh"}:
                        LOGGER.info("Archive %s flagged due to %s", path, name)
                        indicators.append(name)
        except Exception as exc:  # pragma: no cover - corrupt archive
            LOGGER.warning("Failed to inspect archive %s: %s", path, exc)
        return indicators

    def isolate(self, path: Path, reason: str, source: str, indicators: list[str] | None = None) -> QuarantineRecord:
        destination = self._reserve_destination(path.name)
        LOGGER.info("Quarantining %s", path)
        shutil.move(str(path), destination)
        try:
            destination.chmod(0o444)
        except Exception:  # pragma: no cover - platform specific
            LOGGER.debug("Failed to set read-only permissions for %s", destination)
        record = QuarantineRecord(
            original_path=str(path),
            quarantined_path=str(destination),
            created_at=datetime.utcnow().isoformat(),
            reason=reason,
            source=source,
            sha256=self._hash_file(destination),
            indicators=list(indicators or []),
        )
        self._write_report(record)
        return record

    def _reserve_destination(self, name: str) -> Path:
        destination = self.root / name
        counter = 1
        while destination.exists():
            destination = self.root / f"{Path(name).stem}-{counter}{Path(name).suffix}"
            counter += 1
        return destination

    def _hash_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_report(self, record: QuarantineRecord) -> None:
        filename = f"quarantine-{datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json"
        json_path = self.reports_root / filename
        json_path.write_text(json.dumps(record.__dict__, indent=2), encoding="utf-8")
        html_path = json_path.with_suffix(".html")
        html = self._render_html(record)
        html_path.write_text(html, encoding="utf-8")

    def _render_html(self, record: QuarantineRecord) -> str:
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Aegis Quarantine Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2rem; }}
h1 {{ color: #b45309; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
th {{ background: #fef3c7; }}
</style>
</head>
<body>
<h1>Quarantine Report</h1>
<table>
  <tr><th>Original Path</th><td>{record.original_path}</td></tr>
  <tr><th>Quarantine Path</th><td>{record.quarantined_path}</td></tr>
  <tr><th>Detected</th><td>{record.created_at}</td></tr>
  <tr><th>Reason</th><td>{record.reason}</td></tr>
  <tr><th>Source</th><td>{record.source}</td></tr>
  <tr><th>SHA-256</th><td>{record.sha256}</td></tr>
  <tr><th>Indicators</th><td>{', '.join(record.indicators) if record.indicators else 'None detected'}</td></tr>
</table>
</body>
</html>
"""


__all__ = ["Quarantine", "QuarantineRecord"]
