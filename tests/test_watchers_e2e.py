from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from aegis.core.actions import ActionExecutor
from aegis.core.bus import EventBus
from aegis.core.notifier import Notifier
from aegis.watchers.filesystem import DirectoryWatcher


class MemoryNotifier(Notifier):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def notify(self, message: str, title: str = "Aegis", level: str = "info") -> None:  # pragma: no cover - simple capture
        self.messages.append(message)


def test_watchers_quarantine_and_rename(app_config) -> None:
    bus = EventBus()
    notifier = MemoryNotifier()
    executor = ActionExecutor(bus, notifier, app_config)

    downloads_watcher = DirectoryWatcher(Path(app_config.downloads_path), bus, app_config, label="downloads")
    suspicious = Path(app_config.downloads_path) / "danger.zip"
    with ZipFile(suspicious, "w") as archive:
        archive.writestr("payload.exe", b"binary")
    downloads_watcher.scan_once()

    quarantine_dir = Path(app_config.quarantine_root)
    reports_dir = Path(app_config.reports_root) / "quarantine"
    quarantined = list(quarantine_dir.glob("danger*.zip"))
    assert quarantined
    assert list(reports_dir.glob("*.json"))
    assert list(reports_dir.glob("*.html"))

    desktop_watcher = DirectoryWatcher(Path(app_config.desktop_path), bus, app_config, label="desktop")
    document = Path(app_config.desktop_path) / "notes.txt"
    document.write_text("hello", encoding="utf-8")
    desktop_watcher.scan_once()
    renamed = executor.rename_last_file({"style": "summary"})
    assert renamed is not None
    assert renamed.exists()
    assert "summary" in renamed.name
