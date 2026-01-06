"""Clipboard watcher implementation."""



import logging
import threading
import time
from typing import Optional

try:  # pragma: no cover - optional dependency
    import pyperclip
except ImportError:  # pragma: no cover - fallback
    pyperclip = None  # type: ignore

from ..config.schema import AppConfig
from ..core.bus import ClipboardEvent, EventBus

LOGGER = logging.getLogger(__name__)


class ClipboardWatcher:
    """Poll the OS clipboard for changes and publish events."""

    def __init__(self, bus: EventBus, config: AppConfig) -> None:
        self.bus = bus
        self.config = config
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_value: Optional[str] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        if pyperclip is None:
            LOGGER.warning("pyperclip is not available; clipboard polling disabled")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        LOGGER.info("Clipboard watcher started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
        LOGGER.info("Clipboard watcher stopped")

    def _run(self) -> None:
        interval = self.config.clipboard_poll_interval
        while not self._stop_event.is_set():
            try:
                if pyperclip is None:
                    return
                value = pyperclip.paste()
                self.process_value(value)
            except Exception:  # pragma: no cover
                LOGGER.debug("Clipboard unavailable")
            time.sleep(interval)

    def process_value(self, value: str) -> None:
        if value and value != self._last_value:
            self._last_value = value
            self.bus.publish(ClipboardEvent(value))


__all__ = ["ClipboardWatcher"]

