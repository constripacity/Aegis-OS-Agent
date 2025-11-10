"""Cross-platform notification helper."""

from __future__ import annotations

import logging
import platform

LOGGER = logging.getLogger(__name__)


class Notifier:
    """Dispatch user notifications with graceful fallbacks."""

    def __init__(self) -> None:
        self.system = platform.system().lower()
        self._setup_backends()

    def _setup_backends(self) -> None:
        self._backend = None
        if self.system == "windows":
            try:
                import importlib

                module = importlib.import_module("win10toast_click")
                self._backend = module.ToastNotifier()
            except Exception:  # pragma: no cover - optional
                LOGGER.debug("win10toast not available")
        elif self.system == "darwin":
            try:
                import importlib

                self._backend = importlib.import_module("pync")
            except Exception:  # pragma: no cover
                LOGGER.debug("pync not available")
        elif self.system == "linux":
            try:
                import importlib

                notify2 = importlib.import_module("notify2")
                notify2.init("Aegis")
                self._backend = notify2
            except Exception:  # pragma: no cover
                LOGGER.debug("notify2 not available")

    def notify(self, message: str, title: str = "Aegis", level: str = "info") -> None:
        LOGGER.info("Notification (%s): %s", level, message)
        if not self._backend:
            return
        try:
            if self.system == "windows":
                self._backend.show_toast(title, message, duration=5)
            elif self.system == "darwin":
                self._backend.notify(message, title=title)
            elif self.system == "linux":
                notification = self._backend.Notification(title, message)
                notification.show()
        except Exception:  # pragma: no cover - fallback to logging
            LOGGER.debug("Notification backend failed", exc_info=True)


__all__ = ["Notifier"]

