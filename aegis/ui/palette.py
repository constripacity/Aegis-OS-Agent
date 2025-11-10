"""Tkinter command palette for Aegis."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import Callable
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
        self._ready = threading.Event()
        self._root: tk.Tk | None = None
        self._entry: tk.Entry | None = None
        self._status: tk.Label | None = None
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
        entry.pack(fill=tk.X, padx=10, pady=12)
        self._entry = entry
        result_box = tk.Listbox(root, activestyle="none")
        result_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        status = tk.Label(root, text="", anchor="w")
        status.pack(fill=tk.X, padx=10, pady=(0, 10))
        self._status = status

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
        if commands:
            result_box.selection_set(0)
            result_box.activate(0)

        def execute(selected: str) -> None:
            intent = self.router.parse(selected)
            self.router.dispatch(intent)
            if self._status is not None:
                self._status.config(text=f"Executed: {intent.name}")
            root.withdraw()

        def on_enter(event: tk.Event) -> None:
            current = entry.get() or result_box.get(tk.ACTIVE)
            if not current:
                return
            execute(current)

        def on_double_click(_event: tk.Event) -> None:
            selection = result_box.get(tk.ACTIVE)
            if selection:
                execute(selection)

        def on_down(event: tk.Event) -> None:
            if result_box.size() == 0:
                return
            current = result_box.curselection()[0] if result_box.curselection() else 0
            next_index = min(current + 1, result_box.size() - 1)
            result_box.selection_clear(0, tk.END)
            result_box.selection_set(next_index)
            result_box.activate(next_index)
            result_box.see(next_index)
            if event.widget == entry:
                return "break"

        def on_up(event: tk.Event) -> None:
            if result_box.size() == 0:
                return
            current = result_box.curselection()[0] if result_box.curselection() else 0
            next_index = max(current - 1, 0)
            result_box.selection_clear(0, tk.END)
            result_box.selection_set(next_index)
            result_box.activate(next_index)
            result_box.see(next_index)
            if event.widget == entry:
                return "break"

        entry.bind("<Return>", on_enter)
        entry.bind("<Down>", on_down)
        entry.bind("<Up>", on_up)
        result_box.bind("<Double-Button-1>", on_double_click)
        result_box.bind("<Return>", on_enter)
        root.bind("<Escape>", lambda _event: root.withdraw())
        root.protocol("WM_DELETE_WINDOW", root.withdraw)

        def reveal() -> None:
            root.deiconify()
            root.lift()
            root.attributes("-topmost", True)
            root.after(200, lambda: root.attributes("-topmost", False))
            entry.delete(0, tk.END)
            entry.focus_set()
            result_box.selection_clear(0, tk.END)
            if result_box.size():
                result_box.selection_set(0)
                result_box.activate(0)

        self._reveal = reveal
        self._ready.set()

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

