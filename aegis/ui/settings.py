"""Tkinter settings window with persistence."""
"""Tkinter settings panel."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Callable

from ..config.schema import AppConfig, config_dir
from ..core.utils import ensure_directory
from pathlib import Path
from tkinter import messagebox

from ..config.schema import AppConfig
from ..core.intents import IntentRouter

LOGGER = logging.getLogger(__name__)


class SettingsWindow:
    """Simple settings dialog for toggling modules and hotkeys."""

    def __init__(self, config: AppConfig, on_save: Callable[[AppConfig], None]) -> None:
        self.config = config
        self._on_save = on_save
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
        root.geometry("420x380")

        vault_var = tk.BooleanVar(value=self.config.clipboard_vault.enabled)
        tk.Checkbutton(root, text="Enable clipboard vault", variable=vault_var).pack(anchor=tk.W, padx=12, pady=6)

        max_items_var = tk.StringVar(value=str(self.config.clipboard_vault.max_items))
        tk.Label(root, text="Vault size (items)").pack(anchor=tk.W, padx=12)
        max_items_entry = tk.Entry(root, textvariable=max_items_var)
        max_items_entry.pack(fill=tk.X, padx=12, pady=2)

        ollama_var = tk.BooleanVar(value=self.config.use_ollama)
        tk.Checkbutton(root, text="Use Ollama for intents/summaries", variable=ollama_var).pack(anchor=tk.W, padx=12, pady=6)

        def toggle_vault(*_args: object) -> None:
            state = tk.NORMAL if vault_var.get() else tk.DISABLED
            max_items_entry.configure(state=state)

        vault_var.trace_add("write", toggle_vault)
        toggle_vault()

        hotkey_var = tk.StringVar(value=self.config.hotkey)
        tk.Label(root, text="Command palette hotkey").pack(anchor=tk.W, padx=12)
        tk.Entry(root, textvariable=hotkey_var).pack(fill=tk.X, padx=12, pady=2)

        watcher_desktop = tk.BooleanVar(value=self.config.watchers.desktop)
        watcher_downloads = tk.BooleanVar(value=self.config.watchers.downloads)
        tk.Checkbutton(root, text="Watch Desktop", variable=watcher_desktop).pack(anchor=tk.W, padx=12, pady=2)
        tk.Checkbutton(root, text="Watch Downloads", variable=watcher_downloads).pack(anchor=tk.W, padx=12, pady=2)

        archive_days = tk.StringVar(value=str(self.config.scheduler.archive_days))
        tk.Label(root, text="Archive after N days").pack(anchor=tk.W, padx=12)
        tk.Entry(root, textvariable=archive_days).pack(fill=tk.X, padx=12, pady=2)

        zip_monthly = tk.BooleanVar(value=self.config.scheduler.zip_monthly)
        tk.Checkbutton(root, text="Zip monthly archives", variable=zip_monthly).pack(anchor=tk.W, padx=12, pady=6)

        def save() -> None:
            try:
                max_items = max(1, int(max_items_var.get()))
                archive_days_int = max(1, int(archive_days.get()))
            except ValueError:
                messagebox.showerror("Aegis", "Numeric fields must contain integers")
                return
            self.config.clipboard_vault.enabled = vault_var.get()
            self.config.clipboard_vault.max_items = max_items
            self.config.use_ollama = bool(ollama_var.get())
            self.config.hotkey = hotkey_var.get()
            self.config.watchers.desktop = bool(watcher_desktop.get())
            self.config.watchers.downloads = bool(watcher_downloads.get())
            self.config.scheduler.archive_days = archive_days_int
            self.config.scheduler.zip_monthly = bool(zip_monthly.get())
            config_path = config_dir() / "config.json"
            ensure_directory(config_path.parent)
            config_path.write_text(self.config.json(indent=2), encoding="utf-8")
            LOGGER.info("Settings saved to %s", config_path)
            self._on_save(self.config)
            messagebox.showinfo("Aegis", f"Settings saved to {config_path}")
            root.destroy()

        tk.Button(root, text="Save", command=save).pack(pady=16)
        try:
            root.mainloop()
        finally:
            try:
                root.destroy()
            except Exception:
                LOGGER.debug("Settings window already closed")
            self._thread = None


__all__ = ["SettingsWindow"]
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

