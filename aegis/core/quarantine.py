"""Quarantine utilities for suspicious files."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from ..config.schema import AppConfig
from .utils import ensure_directory
from ..reports.quarantine import build_report, write_quarantine_reports, QuarantineReport

LOGGER = logging.getLogger(__name__)


@dataclass
class QuarantineRecord:
    """Metadata describing a quarantined file."""

    original_path: str
    quarantined_path: str
    reason: str
    source: str
    indicators: list[str]
    rule_id: str
    report_json: str
    report_html: str


class Quarantine:
    """Move suspicious files into a read-only quarantine folder with reporting."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.root = Path(config.quarantine_root).expanduser()
        ensure_directory(self.root)
        self.reports_root = Path(config.reports_root).expanduser() / "quarantine"
        ensure_directory(self.reports_root)

    def inspect_archive(self, path: Path) -> list[str]:
        if not path.exists():
            return []
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

    def isolate(
        self,
        path: Path,
        reason: str,
        source: str,
        indicators: list[str] | None = None,
        rule_id: str = "heuristic",
    ) -> QuarantineRecord:
        destination = self._reserve_destination(path.name)
        LOGGER.info("Quarantining %s", path)
        shutil.move(str(path), destination)
        try:
            destination.chmod(0o444)
        except Exception:  # pragma: no cover - platform specific
            LOGGER.debug("Failed to set read-only permissions for %s", destination)
        report = build_report(destination, reason, source, indicators or [], rule_id)
        json_path, html_path = write_quarantine_reports(report, self.reports_root)
        record = QuarantineRecord(
            original_path=str(path),
            quarantined_path=str(destination),
            reason=reason,
            source=source,
            indicators=list(indicators or []),
            rule_id=rule_id,
            report_json=str(json_path),
            report_html=str(html_path),
        )
        return record

    def _reserve_destination(self, name: str) -> Path:
        destination = self.root / name
        counter = 1
        while destination.exists():
            destination = self.root / f"{Path(name).stem}-{counter}{Path(name).suffix}"
            counter += 1
        return destination

__all__ = ["Quarantine", "QuarantineRecord", "QuarantineReport"]
