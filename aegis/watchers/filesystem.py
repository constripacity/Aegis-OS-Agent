"""Folder watching.

The previous implementation ran ``root.glob("*")`` once per second, forever, and
diffed the resulting set. On a Downloads folder with thousands of files that is a
full directory listing every second for as long as the agent is running — the
single largest source of idle CPU in the application.

This version uses ``watchdog`` (kernel notifications: FSEvents on macOS,
ReadDirectoryChangesW on Windows, inotify on Linux) when it is installed, and
falls back to polling with a **much longer interval and stat-based change
detection** when it is not. Either way, a file is only announced once it has
stopped changing size, so half-written downloads are not acted on mid-flight.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

from ..config.schema import AppConfig
from ..core.bus import EventBus, FileSystemEvent
from ..core.utils import ensure_directory

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - depends on the host
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    HAVE_WATCHDOG = True
except ImportError:  # pragma: no cover
    FileSystemEventHandler = object  # type: ignore[assignment,misc]
    Observer = None  # type: ignore[assignment]
    HAVE_WATCHDOG = False

#: A file must be this many seconds old, and unchanged in size, before it is
#: announced. Browsers write downloads incrementally.
SETTLE_SECONDS = 1.5

#: Polling fallback interval. The old value was 1.0s; anything a user drops in a
#: folder can wait five seconds, and this is 5x less work.
POLL_INTERVAL = 5.0

IGNORED_SUFFIXES = (".part", ".crdownload", ".download", ".tmp", ".partial", ".!ut", ".opdownload")


class DirectoryWatcher:
    """Watch one directory and publish a :class:`FileSystemEvent` per new file."""

    def __init__(self, root: Path, bus: EventBus, config: AppConfig, label: str) -> None:
        self.root = Path(root).expanduser()
        self.bus = bus
        self.config = config
        self.label = label
        ensure_directory(self.root)

        self._known: set[Path] = set()
        self._pending: dict[Path, tuple[float, int]] = {}
        self._announced: set[Path] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # watchdog's Observer type is only importable when watchdog is present.
        self._observer: Any | None = None
        self._lock = threading.Lock()
        self._prime()

    # -- lifecycle -----------------------------------------------------
    def _prime(self) -> None:
        """Record what is already there so existing files are not announced."""
        try:
            self._known = {p for p in self.root.iterdir() if p.is_file()}
        except OSError as exc:  # pragma: no cover
            LOGGER.warning("Could not read %s: %s", self.root, exc)
            self._known = set()

    @property
    def backend(self) -> str:
        return "watchdog" if self._observer is not None else "polling"

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        if HAVE_WATCHDOG and Observer is not None:
            try:
                self._observer = Observer()
                self._observer.schedule(_Handler(self), str(self.root), recursive=False)
                self._observer.start()
                LOGGER.info("Watching %s via watchdog", self.root)
            except Exception as exc:  # pragma: no cover - platform limits
                LOGGER.warning("watchdog could not watch %s (%s); polling instead", self.root, exc)
                self._observer = None
        else:
            LOGGER.info(
                "watchdog is not installed; polling %s every %.0fs. "
                "Install it with: pip install 'aegis-os-agent[watch]'",
                self.root,
                POLL_INTERVAL,
            )

        # The settle loop runs in both modes: watchdog tells us a file appeared,
        # this decides when it has finished being written.
        self._thread = threading.Thread(
            target=self._run, name=f"aegis-watch-{self.label}", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:  # pragma: no cover
                LOGGER.debug("Observer did not stop cleanly")
            self._observer = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        LOGGER.info("Stopped watching %s", self.root)

    # -- work ----------------------------------------------------------
    def _run(self) -> None:
        polling = self._observer is None
        while not self._stop.is_set():
            if polling:
                self.scan_once()
            self._flush_settled()
            self._stop.wait(POLL_INTERVAL if polling else SETTLE_SECONDS / 2)

    def note(self, path: Path) -> None:
        """Register a candidate. Called by watchdog and by the polling scan."""
        if path.name.lower().endswith(IGNORED_SUFFIXES) or path.name.startswith("."):
            return
        try:
            if path.is_symlink() or not path.is_file():
                return
            size = path.stat().st_size
        except OSError:
            return
        with self._lock:
            if path in self._announced:
                return
            self._pending[path] = (time.monotonic(), size)

    def _flush_settled(self) -> None:
        """Announce files that have stopped growing."""
        now = time.monotonic()
        ready: list[Path] = []
        with self._lock:
            for path, (first_seen, last_size) in list(self._pending.items()):
                try:
                    size = path.stat().st_size
                except OSError:
                    self._pending.pop(path, None)
                    continue
                if size != last_size:
                    self._pending[path] = (now, size)
                    continue
                if now - first_seen >= SETTLE_SECONDS:
                    ready.append(path)
                    self._pending.pop(path, None)
                    self._announced.add(path)
                    self._known.add(path)
        for path in ready:
            self.bus.publish(FileSystemEvent(str(path), event_type="created", label=self.label))

    def scan_once(self) -> None:
        """One polling pass. Also used directly by tests."""
        try:
            current = {p for p in self.root.iterdir() if p.is_file()}
        except OSError as exc:  # pragma: no cover
            LOGGER.debug("Could not list %s: %s", self.root, exc)
            return
        for path in current - self._known:
            self.note(path)
        # Files that disappeared should not be remembered forever.
        with self._lock:
            self._announced &= current
        self._known &= current

    def publish(self, path: Path, event_type: str = "created") -> None:
        """Announce *path* immediately, bypassing the settle delay (tests, CLI)."""
        with self._lock:
            self._known.add(path)
            self._announced.add(path)
        self.bus.publish(FileSystemEvent(str(path), event_type=event_type, label=self.label))


class _Handler(FileSystemEventHandler):  # pragma: no cover - needs watchdog + a real FS
    """Adapts watchdog callbacks to :meth:`DirectoryWatcher.note`."""

    def __init__(self, watcher: DirectoryWatcher) -> None:
        self._watcher = watcher

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._watcher.note(Path(event.src_path))

    def on_moved(self, event) -> None:
        if not event.is_directory:
            self._watcher.note(Path(event.dest_path))

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self._watcher.note(Path(event.src_path))


__all__ = ["DirectoryWatcher", "HAVE_WATCHDOG", "POLL_INTERVAL", "SETTLE_SECONDS"]
