"""Tkinter command palette for Aegis."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox

from ..config.schema import AppConfig
from ..core.bus import EventBus
from ..core.intents import IntentRouter

LOGGER = logging.getLogger(__name__)


class CommandPalette:
    """Minimal command palette window."""

    def __init__(self, bus: EventBus, router: IntentRouter, config: AppConfig) -> None:
        self.bus = bus
        self.router = router
        self.config = config
        self._thread: threading.Thread | None = None

    def run(self) -> None:
        LOGGER.info("Launching command palette")
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._create_window, daemon=True)
        self._thread.start()

    def _create_window(self) -> None:
        root = tk.Tk()
        root.title("Aegis Command Palette")
        root.geometry("400x200")
        entry = tk.Entry(root, font=("Segoe UI", 14))
        entry.pack(fill=tk.X, padx=10, pady=20)
        result_box = tk.Listbox(root)
        result_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        commands = [
            "summarize clipboard",
            "clean desktop",
            "clean downloads",
            "rename last file",
            "find in vault",
            "pause watchers 30",
            "wipe vault",
        ]
        for cmd in commands:
            result_box.insert(tk.END, cmd)

        def on_enter(event: tk.Event) -> None:
            text = entry.get() or result_box.get(tk.ACTIVE)
            if not text:
                return
            intent = self.router.parse(text)
            self.router.dispatch(intent)
            messagebox.showinfo("Aegis", f"Executed: {intent.name}")

        entry.bind("<Return>", on_enter)
        root.mainloop()


__all__ = ["CommandPalette"]

