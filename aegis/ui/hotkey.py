"""Cross-platform global hotkey registration."""

from __future__ import annotations

import logging
from typing import Callable, Optional

LOGGER = logging.getLogger(__name__)


def _normalise_hotkey(hotkey: str) -> str:
    parts = [token.strip().lower() for token in hotkey.replace("+", "+").split("+") if token.strip()]
    if not parts:
        return "alt+space"
    modifiers_map = {
        "alt": "<alt>",
        "option": "<alt>",
        "ctrl": "<ctrl>",
        "control": "<ctrl>",
        "shift": "<shift>",
        "cmd": "<cmd>",
        "command": "<cmd>",
        "win": "<cmd>",
    }
    *mods, key = parts
    mapped = [modifiers_map.get(mod, f"<{mod}>") for mod in mods]
    mapped.append(key)
    return "+".join(mapped)


class HotkeyManager:
    """Register a global hotkey when optional dependencies are present."""

    def __init__(self, hotkey: str, callback: Callable[[], None]) -> None:
        self._raw_hotkey = hotkey
        self._callback = callback
        self._listener: Optional["GlobalHotKeys"] = None

    def start(self) -> None:
        try:
            from pynput import keyboard
        except Exception:  # pragma: no cover - optional dependency
            LOGGER.info("pynput not available; global hotkey disabled")
            return
        normalised = _normalise_hotkey(self._raw_hotkey)
        LOGGER.info("Registering global hotkey %s", normalised)
        self._listener = keyboard.GlobalHotKeys({normalised: self._safe_callback})
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def update(self, hotkey: str) -> None:
        self.stop()
        self._raw_hotkey = hotkey
        self.start()

    def _safe_callback(self) -> None:
        try:
            self._callback()
        except Exception as exc:  # pragma: no cover - defensive log
            LOGGER.exception("Hotkey callback failed: %s", exc)


__all__ = ["HotkeyManager"]

