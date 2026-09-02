"""Tkinter command palette.

Two behavioural changes from the previous version:

* the suggestion list is generated from the real command table and filters as
  you type, instead of a hard-coded list that had drifted out of date
  ("clean desktop", "rename last file" were no longer commands at all);
* destructive commands ask before running. Typing "wipe vault" and pressing
  Enter used to delete the clipboard history immediately.

All the decisions live in :mod:`aegis.ui.palette_model`, which is unit tested.
"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, scrolledtext

from ..config.schema import AppConfig
from ..core.bus import EventBus
from ..core.intents import IntentRouter
from .palette_model import (
    confirmation_text,
    filter_suggestions,
    needs_confirmation,
    render_result,
)

LOGGER = logging.getLogger(__name__)


class CommandPalette:
    """Minimal command palette window with persistent root and reveal support."""

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
        root.geometry("620x460")
        root.minsize(520, 380)
        self._root = root

        entry = tk.Entry(root, font=("Segoe UI", 14))
        entry.pack(fill=tk.X, padx=10, pady=12)
        self._entry = entry

        result_box = tk.Listbox(root, activestyle="none", height=8)
        result_box.pack(fill=tk.X, padx=10)

        output = scrolledtext.ScrolledText(root, height=10, wrap="word", state="disabled")
        output.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        suggestions: list = []

        def show_output(text: str) -> None:
            output.configure(state="normal")
            output.delete("1.0", tk.END)
            output.insert("1.0", text)
            output.configure(state="disabled")

        def refresh(_event: tk.Event | None = None) -> None:
            suggestions.clear()
            suggestions.extend(filter_suggestions(entry.get()))
            result_box.delete(0, tk.END)
            for suggestion in suggestions:
                result_box.insert(tk.END, suggestion.label())
            if result_box.size():
                result_box.selection_clear(0, tk.END)
                result_box.selection_set(0)
                result_box.activate(0)

        refresh()

        status = tk.Label(
            root,
            text="Type a command, or pick one. Anything that changes files shows a plan first.",
            anchor="w",
            wraplength=580,
            justify="left",
        )
        status.pack(fill=tk.X, padx=10, pady=(0, 10))
        self._status = status

        def execute(selected: str) -> None:
            intent = self.router.parse(selected)
            if not intent.is_understood:
                hint = (
                    f"Did you mean: {', '.join(intent.suggestions)}?\n"
                    if intent.suggestions
                    else ""
                )
                show_output(
                    f"I don't understand {selected!r}.\n\n"
                    + hint
                    + "Type 'help' to see everything Aegis can do."
                )
                if self._status is not None:
                    self._status.config(text="Not understood — nothing was done.")
                return

            if needs_confirmation(intent) and not messagebox.askyesno(
                "Confirm", confirmation_text(intent), parent=root
            ):
                if self._status is not None:
                    self._status.config(text="Cancelled. Nothing was changed.")
                return

            show_output(render_result(self.router.dispatch(intent)))
            if self._status is not None:
                self._status.config(text=f"Ran: {intent.name}")

        def _phrase_at(index: int) -> str:
            return suggestions[index].phrase if 0 <= index < len(suggestions) else ""

        def on_enter(_event: tk.Event) -> None:
            typed = entry.get().strip()
            if typed:
                execute(typed)
                return
            selection = result_box.curselection()
            phrase = _phrase_at(selection[0] if selection else 0)
            if phrase:
                execute(phrase)

        def on_double_click(_event: tk.Event) -> None:
            selection = result_box.curselection()
            phrase = _phrase_at(selection[0] if selection else 0)
            if phrase:
                execute(phrase)

        def on_down(event: tk.Event) -> str | None:
            if result_box.size() == 0:
                return None
            current = result_box.curselection()[0] if result_box.curselection() else 0
            next_index = min(current + 1, result_box.size() - 1)
            result_box.selection_clear(0, tk.END)
            result_box.selection_set(next_index)
            result_box.activate(next_index)
            result_box.see(next_index)
            if event.widget == entry:
                return "break"
            return None

        def on_up(event: tk.Event) -> str | None:
            if result_box.size() == 0:
                return None
            current = result_box.curselection()[0] if result_box.curselection() else 0
            next_index = max(current - 1, 0)
            result_box.selection_clear(0, tk.END)
            result_box.selection_set(next_index)
            result_box.activate(next_index)
            result_box.see(next_index)
            if event.widget == entry:
                return "break"
            return None

        entry.bind("<KeyRelease>", refresh)
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
            refresh()

        self._reveal = reveal
        self._ready.set()
        root.mainloop()


__all__ = ["CommandPalette"]
