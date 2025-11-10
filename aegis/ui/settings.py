"""Tkinter settings panel."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from ..config.schema import AppConfig
from ..core.intents import IntentRouter

LOGGER = logging.getLogger(__name__)


class SettingsWindow:
    """Simple settings dialog for toggling modules."""

    def __init__(self, config: AppConfig, router: IntentRouter) -> None:
        self.config = config
        self.router = router
        self._thread: threading.Thread | None = None

    def show(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._render, daemon=True)
        self._thread.start()

    def _render(self) -> None:
        root = tk.Tk()
        root.title("Aegis Settings")
        root.geometry("360x320")

        vault_var = tk.BooleanVar(value=self.config.clipboard_vault.enabled)
        tk.Checkbutton(root, text="Enable clipboard vault", variable=vault_var).pack(anchor=tk.W, padx=10, pady=10)

        ollama_var = tk.BooleanVar(value=self.config.use_ollama)
        tk.Checkbutton(root, text="Use Ollama", variable=ollama_var).pack(anchor=tk.W, padx=10, pady=10)

        hotkey_var = tk.StringVar(value=self.config.hotkey)
        tk.Label(root, text="Command palette hotkey").pack(anchor=tk.W, padx=10)
        tk.Entry(root, textvariable=hotkey_var).pack(fill=tk.X, padx=10, pady=5)

        def save() -> None:
            self.config.clipboard_vault.enabled = vault_var.get()
            self.config.use_ollama = bool(ollama_var.get())
            self.config.hotkey = hotkey_var.get()
            config_path = Path("aegis-config.json")
            config_path.write_text(self.config.json(indent=2), encoding="utf-8")
            messagebox.showinfo("Aegis", f"Configuration written to {config_path}")

        tk.Button(root, text="Save", command=save).pack(pady=20)
        root.mainloop()


__all__ = ["SettingsWindow"]

