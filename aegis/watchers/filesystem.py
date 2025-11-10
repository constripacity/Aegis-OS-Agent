"""Filesystem watcher for Desktop and Downloads using polling."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional, Set

from ..config.schema import AppConfig
from ..core.bus import EventBus, FileSystemEvent
from ..core.utils import ensure_directory

LOGGER = logging.getLogger(__name__)


class DirectoryWatcher:
    """Watch a directory for new files and publish events."""

    def __init__(self, root: Path, bus: EventBus, config: AppConfig, label: str) -> None:
        self.root = root
        self.bus = bus
        self.config = config
        self.label = label
        ensure_directory(self.root)
        self._known_files: Set[Path] = set(self.root.glob("*"))
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        LOGGER.info("Started watcher for %s", self.root)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
            LOGGER.info("Stopped watcher for %s", self.root)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.scan_once()
            time.sleep(1.0)

    def publish(self, path: Path, event_type: str) -> None:
        self._known_files.add(path)
        self.bus.publish(FileSystemEvent(str(path), event_type=event_type, label=self.label))

    def scan_once(self) -> None:
        current = set(self.root.glob("*"))
        new_files = current - self._known_files
        for path in new_files:
            if path.is_file():
                self.publish(path, "created")
        self._known_files = current


__all__ = ["DirectoryWatcher"]

