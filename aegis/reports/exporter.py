"""Activity report exporter."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from ..config.schema import AppConfig
from ..core.utils import ensure_directory

LOGGER = logging.getLogger(__name__)


def _report_template() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Aegis Activity Report</title>
<style>
body { font-family: Arial, sans-serif; margin: 2rem; }
h1 { color: #2f855a; }
table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
th, td { border: 1px solid #ddd; padding: 0.5rem; }
th { background: #f0f4f8; }
</style>
</head>
<body>
<h1>Aegis Activity Report</h1>
<p>Generated at {{ generated_at }}</p>
<table>
<thead><tr><th>Event</th><th>Details</th></tr></thead>
<tbody>
{% for item in items %}
<tr><td>{{ item.event }}</td><td>{{ item.details }}</td></tr>
{% endfor %}
</tbody>
</table>
</body>
</html>
"""


class ReportExporter:
    """Create JSON and HTML activity reports."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.reports_root = Path(config.reports_root).expanduser()
        ensure_directory(self.reports_root)

    def export_latest(self, include_html: bool = False) -> str:
        data = self._gather_data()
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        json_path = self.reports_root / f"report-{timestamp}.json"
        json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        summary = f"Report written to {json_path}"
        if include_html:
            html_path = json_path.with_suffix(".html")
            html_path.write_text(self._render_html(data), encoding="utf-8")
            summary += f" and {html_path}"
        return summary

    def _gather_data(self) -> Dict[str, Any]:
        items = [{"event": "archive", "details": "No events captured in offline demo"}]
        quarantine_dir = self.reports_root / "quarantine"
        if quarantine_dir.exists():
            for report in sorted(quarantine_dir.glob("quarantine-*.json"))[-5:]:
                try:
                    payload = json.loads(report.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                details = (
                    f"{Path(payload.get('quarantined_path', '')).name} → {payload.get('reason', 'unknown')}"
                )
                items.append({"event": "quarantine", "details": details})
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "items": items,
        }

    def _render_html(self, data: Dict[str, Any]) -> str:
        template = _report_template()
        return template.replace("{{ generated_at }}", data["generated_at"]).replace(
            "{% for item in items %}\n<tr><td>{{ item.event }}</td><td>{{ item.details }}</td></tr>\n{% endfor %}",
            "\n".join(
                f"<tr><td>{item['event']}</td><td>{item['details']}</td></tr>" for item in data.get("items", [])
            ),
        )


__all__ = ["ReportExporter"]

