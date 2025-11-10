"""Tkinter command palette for Aegis."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Callable

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
        self._ready = threading.Event()
        self._root: tk.Tk | None = None
        self._entry: tk.Entry | None = None
        self._reveal: Callable[[], None] | None = None

    def run(self) -> None:
        LOGGER.info("Launching command palette")
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._create_window, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2)

    def show(self) -> None:
        if not self._thread or not self._thread.is_alive():
            self.run()
        if self._ready.wait(timeout=2) and self._root and self._reveal:
            self._root.after(0, self._reveal)

    def _create_window(self) -> None:
        root = tk.Tk()
        root.withdraw()
        root.title("Aegis Command Palette")
        root.geometry("420x220")
        self._root = root
        entry = tk.Entry(root, font=("Segoe UI", 14))
        entry.pack(fill=tk.X, padx=10, pady=20)
        self._entry = entry
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
            root.withdraw()

        entry.bind("<Return>", on_enter)
        root.bind("<Escape>", lambda _event: root.withdraw())
        root.protocol("WM_DELETE_WINDOW", root.withdraw)

        def reveal() -> None:
            root.deiconify()
            root.lift()
            root.attributes("-topmost", True)
            root.after(200, lambda: root.attributes("-topmost", False))
            entry.delete(0, tk.END)
            entry.focus_set()

        self._reveal = reveal
        self._ready.set()
        root.mainloop()


__all__ = ["CommandPalette"]

