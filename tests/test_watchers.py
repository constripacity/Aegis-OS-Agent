

from pathlib import Path

from aegis.core.bus import EventBus
from aegis.watchers.clipboard import ClipboardWatcher
from aegis.watchers.filesystem import DirectoryWatcher


def test_clipboard_watcher_publishes_events(app_config) -> None:
    bus = EventBus()
    watcher = ClipboardWatcher(bus, app_config)
    events: list[str] = []
    bus.subscribe("clipboard", lambda event: events.append(event.content))
    watcher.process_value("hello")
    assert events == ["hello"]


def test_directory_watcher_scan(tmp_path, app_config) -> None:
    bus = EventBus()
    events: list[str] = []
    bus.subscribe("filesystem", lambda event: events.append(event.path))
    root = Path(app_config.desktop_path)
    watcher = DirectoryWatcher(root, bus, app_config, label="desktop")
    new_file = root / "test.txt"
    new_file.write_text("hi", encoding="utf-8")
    watcher.scan_once()
    assert events == [str(new_file)]

