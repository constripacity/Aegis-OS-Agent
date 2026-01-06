

import os
import time
from pathlib import Path

from aegis.core.actions import ActionExecutor
from aegis.core.bus import EventBus
from aegis.core.notifier import Notifier


class DummyNotifier(Notifier):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def notify(self, message: str, title: str = "Aegis", level: str = "info") -> None:
        self.messages.append(message)


def test_organize_directory_moves_files(app_config) -> None:
    bus = EventBus()
    notifier = DummyNotifier()
    executor = ActionExecutor(bus, notifier, app_config)
    desktop = Path(app_config.desktop_path)
    sample = desktop / "sample.txt"
    sample.write_text("data", encoding="utf-8")
    result = executor.organize_directory("desktop")
    assert result.moved_files
    assert not sample.exists()
    for path in result.moved_files:
        assert path.exists()


def test_rename_last_file(app_config) -> None:
    bus = EventBus()
    notifier = DummyNotifier()
    executor = ActionExecutor(bus, notifier, app_config)
    archive_file = Path(app_config.archive_root) / "file.txt"
    archive_file.write_text("info", encoding="utf-8")
    executor.register_file_event(archive_file)
    renamed = executor.rename_last_file({"style": "title"})
    assert renamed is not None
    assert renamed.exists()
    assert "title" in renamed.name.lower()


def test_archive_old_files(app_config) -> None:
    bus = EventBus()
    notifier = DummyNotifier()
    executor = ActionExecutor(bus, notifier, app_config)
    downloads = Path(app_config.downloads_path)
    old_file = downloads / "old.txt"
    old_file.write_text("old", encoding="utf-8")
    old_time = time.time() - 60 * 60 * 24 * 10
    os.utime(old_file, (old_time, old_time))
    result = executor.archive_old_files(age_days=7)
    assert result.moved_files
    for path in result.moved_files:
        assert path.exists()



def test_record_clipboard_saves_code_snippet(app_config) -> None:
    bus = EventBus()
    notifier = DummyNotifier()
    executor = ActionExecutor(bus, notifier, app_config)
    code = "def greet(name):\n    return f\"Hello {name}!\""
    executor.record_clipboard(code)
    snippets = Path(app_config.snippets_root)
    files = list(snippets.rglob('*.py'))
    assert files, "Expected a snippet file to be created"
    assert files[0].read_text(encoding='utf-8') == code.rstrip()


def test_record_clipboard_cleans_url(app_config) -> None:
    bus = EventBus()
    notifier = DummyNotifier()
    executor = ActionExecutor(bus, notifier, app_config)
    url = "https://example.com/path?utm_source=newsletter&ref=123"
    executor.record_clipboard(url)
    snapshot = executor.clipboard_snapshot()
    assert snapshot == "https://example.com/path?ref=123"
    assert notifier.messages
    assert "Cleaned tracking parameters" in notifier.messages[0]
