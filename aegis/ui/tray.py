"""System tray integration using optional dependencies."""

from __future__ import annotations

import logging
from typing import Callable, Optional

LOGGER = logging.getLogger(__name__)


class TrayController:
    """Display a system tray icon with quick actions when possible."""

    def __init__(
        self,
        show_palette: Callable[[], None],
        show_settings: Callable[[], None],
        pause_watchers: Callable[[], None],
        resume_watchers: Callable[[], None],
        open_vault: Callable[[], None],
        quit_app: Callable[[], None],
    ) -> None:
        self._show_palette = show_palette
        self._show_settings = show_settings
        self._pause = pause_watchers
        self._resume = resume_watchers
        self._open_vault = open_vault
        self._quit = quit_app
        self._icon: Optional["Icon"] = None

    def start(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:  # pragma: no cover - optional dependencies
            LOGGER.info("pystray/Pillow not available; tray disabled")
            return

        def _create_image() -> "Image.Image":
            image = Image.new("RGB", (64, 64), "#0f766e")
            draw = ImageDraw.Draw(image)
            draw.rectangle((16, 16, 48, 48), fill="#f8fafc")
            draw.text((24, 20), "A", fill="#0f766e")
            return image

        menu = pystray.Menu(
            pystray.MenuItem("Open Command Palette", lambda: self._invoke(self._show_palette)),
            pystray.MenuItem("Open Settings", lambda: self._invoke(self._show_settings)),
            pystray.MenuItem("Pause Watchers", lambda: self._invoke(self._pause)),
            pystray.MenuItem("Resume Watchers", lambda: self._invoke(self._resume)),
            pystray.MenuItem("Open Vault Folder", lambda: self._invoke(self._open_vault)),
            pystray.MenuItem("Quit", lambda: self._invoke(self._quit)),
        )

        self._icon = pystray.Icon("aegis", _create_image(), "Aegis", menu)
        self._icon.run_detached()

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
            self._icon = None

    def _invoke(self, func: Callable[[], None]) -> None:
        try:
            func()
        except Exception as exc:  # pragma: no cover - defensive log
            LOGGER.exception("Tray action failed: %s", exc)


__all__ = ["TrayController"]

