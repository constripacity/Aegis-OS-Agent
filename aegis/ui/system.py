"""System integrations: tray icon and global hotkeys."""



import logging
from typing import Callable, Optional

LOGGER = logging.getLogger(__name__)


def _normalise_hotkey(hotkey: str) -> str:
    parts = [token.strip().lower() for token in hotkey.split("+")]
    mapped = []
    modifiers = {
        "alt": "<alt>",
        "option": "<alt>",
        "ctrl": "<ctrl>",
        "control": "<ctrl>",
        "shift": "<shift>",
        "cmd": "<cmd>",
        "command": "<cmd>",
    }
    for part in parts[:-1]:
        mapped.append(modifiers.get(part, f"<{part}>"))
    if parts:
        mapped.append(parts[-1])
    return "+".join(mapped)


class HotkeyManager:
    """Register a cross-platform global hotkey when dependencies are available."""

    def __init__(self, hotkey: str, callback: Callable[[], None]) -> None:
        self._raw_hotkey = hotkey
        self._callback = callback
        self._listener: Optional["GlobalHotKeys"] = None

    def start(self) -> None:
        try:
            from pynput import keyboard
        except Exception:  # pragma: no cover - optional dependency
            LOGGER.info("pynput not installed; global hotkey disabled")
            return
        normalised = _normalise_hotkey(self._raw_hotkey)
        LOGGER.info("Registering global hotkey %s", normalised)
        self._listener = keyboard.GlobalHotKeys({normalised: self._callback})
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def update(self, hotkey: str) -> None:
        self.stop()
        self._raw_hotkey = hotkey
        self.start()


class TrayController:
    """System tray icon with quick actions when pystray is available."""

    def __init__(
        self,
        show_palette: Callable[[], None],
        show_settings: Callable[[], None],
        toggle_watchers: Callable[[], None],
        open_vault: Callable[[], None],
        quit_app: Callable[[], None],
    ) -> None:
        self._show_palette = show_palette
        self._show_settings = show_settings
        self._toggle_watchers = toggle_watchers
        self._open_vault = open_vault
        self._quit_app = quit_app
        self._icon: Optional["Icon"] = None

    def start(self) -> None:
        try:
            import pystray
            from PIL import Image, ImageDraw
        except Exception:  # pragma: no cover - optional dependency
            LOGGER.info("pystray/Pillow not installed; tray icon disabled")
            return

        def _create_image() -> "Image.Image":
            image = Image.new("RGB", (64, 64), "#0f766e")
            draw = ImageDraw.Draw(image)
            draw.rectangle((16, 16, 48, 48), fill="#ffffff")
            draw.text((20, 20), "A", fill="#0f766e")
            return image

        menu = pystray.Menu(
            pystray.MenuItem("Open Palette", lambda: self._invoke(self._show_palette)),
            pystray.MenuItem("Open Settings", lambda: self._invoke(self._show_settings)),
            pystray.MenuItem("Toggle Watchers", lambda: self._invoke(self._toggle_watchers)),
            pystray.MenuItem("Open Vault Folder", lambda: self._invoke(self._open_vault)),
            pystray.MenuItem("Quit", lambda: self._invoke(self._quit_app)),
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


__all__ = ["HotkeyManager", "TrayController"]
