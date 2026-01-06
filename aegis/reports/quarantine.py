"""Quarantine reporting helpers."""



from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from typing import Iterable

from importlib import resources

from .. import __version__
from ..core.hash import sha256_file
from ..core.utils import ensure_directory

__all__ = ["QuarantineReport", "build_report", "write_quarantine_reports", "render_html"]


@dataclass(slots=True)
class QuarantineReport:
    """Metadata describing a quarantined file."""

    timestamp: str
    filename: str
    quarantined_path: str
    size: int
    sha256: str
    source: str
    reason: str
    rule_id: str
    action: str
    indicators: list[str]
    version: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["indicators"] = list(self.indicators)
        return payload


def build_report(
    quarantined_path: Path,
    reason: str,
    source: str,
    indicators: Iterable[str] | None = None,
    rule_id: str = "heuristic",
    action: str = "moved_to_quarantine",
) -> QuarantineReport:
    """Build a :class:`QuarantineReport` for ``quarantined_path``."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    resolved = quarantined_path.expanduser().resolve()
    indicator_list = list(indicators or [])
    try:
        size = resolved.stat().st_size
    except FileNotFoundError:
        size = 0
    digest = sha256_file(resolved) if resolved.exists() else ""
    return QuarantineReport(
        timestamp=timestamp,
        filename=resolved.name,
        quarantined_path=str(resolved),
        size=size,
        sha256=digest,
        source=str(source),
        reason=str(reason),
        rule_id=str(rule_id),
        action=action,
        indicators=indicator_list,
        version=__version__,
    )


def write_quarantine_reports(report: QuarantineReport, reports_root: Path) -> tuple[Path, Path]:
    """Persist a report to JSON and HTML under ``reports_root``."""

    ensure_directory(reports_root)
    base_name = report.timestamp
    json_path = _resolve_unique_path(reports_root, base_name, ".json")
    html_path = _resolve_unique_path(reports_root, base_name, ".html")
    json_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
    return json_path, html_path


def render_html(report: QuarantineReport) -> str:
    template = _load_template()
    indicator_items = report.indicators or ["No additional indicators"]
    indicator_list = "\n".join(
        f"      <li>{escape(item)}</li>" for item in indicator_items
    )
    replacements = {
        "timestamp": escape(report.timestamp),
        "filename": escape(report.filename),
        "quarantined_path": escape(report.quarantined_path),
        "source": escape(report.source),
        "reason": escape(report.reason),
        "rule_id": escape(report.rule_id),
        "action": escape(report.action),
        "size": str(report.size),
        "sha256": escape(report.sha256 or "unknown"),
        "version": escape(report.version),
        "indicator_list": indicator_list,
    }
    rendered = template
    for key, value in list(replacements.items()):
        rendered = rendered.replace(f"{{{key}}}", value)
    return rendered


def _load_template() -> str:
    with resources.files("aegis.reports.templates").joinpath("quarantine.html").open(
        "r", encoding="utf-8"
    ) as handle:
        return handle.read()


def _resolve_unique_path(root: Path, base: str, suffix: str) -> Path:
    candidate = root / f"{base}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = root / f"{base}-{counter}{suffix}"
        counter += 1
    return candidate
