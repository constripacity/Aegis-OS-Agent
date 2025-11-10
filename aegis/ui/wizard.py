"""First-run Tkinter wizard for configuring Aegis."""

from __future__ import annotations

import getpass
import logging
from pathlib import Path

from ..config.schema import AppConfig, ClipboardVaultSettings, WatcherSettings
from ..core.utils import ensure_directory

LOGGER = logging.getLogger(__name__)


class FirstRunWizard:
    """Collect first-run settings using Tkinter with CLI fallback."""

    def __init__(self, default_config: AppConfig, config_path: Path) -> None:
        self.default_config = default_config
        self.config_path = config_path
        ensure_directory(self.config_path.parent)

    def run(self) -> AppConfig:
        try:
            return self._run_tk()
        except Exception as exc:  # pragma: no cover - GUI fallback path
            LOGGER.warning("Tkinter wizard failed (%s); falling back to CLI prompts", exc)
            return self._run_cli()

    # Tkinter ---------------------------------------------------------------
    def _run_tk(self) -> AppConfig:
        import tkinter as tk
        from tkinter import filedialog, messagebox

        root = tk.Tk()
        root.title("Welcome to Aegis")
        root.geometry("520x420")

        entries: dict[str, tk.Variable] = {}

        def add_entry(label: str, default: str) -> None:
            tk.Label(root, text=label).pack(anchor=tk.W, padx=12, pady=4)
            var = tk.StringVar(value=default)
            frame = tk.Frame(root)
            frame.pack(fill=tk.X, padx=12)
            entry = tk.Entry(frame, textvariable=var)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            button = tk.Button(
                frame,
                text="Browse",
                command=lambda: var.set(filedialog.askdirectory(initialdir=default) or default),
            )
            button.pack(side=tk.RIGHT, padx=6)
            entries[label] = var

        add_entry("Desktop folder", self.default_config.desktop_path)
        add_entry("Downloads folder", self.default_config.downloads_path)
        add_entry("Archive root", self.default_config.archive_root)
        add_entry("Reports root", self.default_config.reports_root)
        add_entry("Quarantine folder", self.default_config.quarantine_root)

        watchers_desktop = tk.BooleanVar(value=self.default_config.watchers.desktop)
        watchers_downloads = tk.BooleanVar(value=self.default_config.watchers.downloads)
        tk.Checkbutton(root, text="Watch Desktop", variable=watchers_desktop).pack(anchor=tk.W, padx=12, pady=2)
        tk.Checkbutton(root, text="Watch Downloads", variable=watchers_downloads).pack(anchor=tk.W, padx=12, pady=2)

        tk.Label(root, text="Command palette hotkey").pack(anchor=tk.W, padx=12, pady=6)
        hotkey_var = tk.StringVar(value=self.default_config.hotkey)
        tk.Entry(root, textvariable=hotkey_var).pack(fill=tk.X, padx=12)

        tk.Label(root, text="Clipboard vault (optional)").pack(anchor=tk.W, padx=12, pady=6)
        vault_enabled = tk.BooleanVar(value=self.default_config.clipboard_vault.enabled)
        tk.Checkbutton(root, text="Enable encrypted clipboard history", variable=vault_enabled).pack(anchor=tk.W, padx=12)
        tk.Label(root, text="Vault passphrase").pack(anchor=tk.W, padx=12, pady=2)
        vault_pass = tk.StringVar(value="" if not self.default_config.clipboard_vault.enabled else "")
        tk.Entry(root, show="*", textvariable=vault_pass).pack(fill=tk.X, padx=12)

        result: dict[str, str] = {}
        state: dict[str, object] = {}

        def on_submit() -> None:
            for label, var in entries.items():
                path = Path(var.get()).expanduser()
                ensure_directory(path)
                result[label] = str(path)
            passphrase = vault_pass.get()
            if vault_enabled.get() and not passphrase:
                messagebox.showerror("Aegis", "Enter a vault passphrase or disable the vault")
                return
            state["desktop"] = watchers_desktop.get()
            state["downloads"] = watchers_downloads.get()
            state["hotkey"] = hotkey_var.get()
            state["vault_enabled"] = vault_enabled.get()
            root.destroy()
            if vault_enabled.get() and passphrase:
                self._persist_passphrase(passphrase)

        tk.Button(root, text="Save", command=on_submit).pack(pady=16)
        root.mainloop()

        for folder in [desktop, downloads, archive, reports, quarantine]:
            ensure_directory(Path(folder).expanduser())
        config = self.default_config
        if not result:
            self._write_config(config)
            return config

        config.desktop_path = result.get("Desktop folder", config.desktop_path)
        config.downloads_path = result.get("Downloads folder", config.downloads_path)
        config.archive_root = result.get("Archive root", config.archive_root)
        config.reports_root = result.get("Reports root", config.reports_root)
        config.quarantine_root = result.get("Quarantine folder", config.quarantine_root)
        config.watchers = WatcherSettings(
            desktop=bool(state.get("desktop", config.watchers.desktop)),
            downloads=bool(state.get("downloads", config.watchers.downloads)),
        )
        config.hotkey = str(state.get("hotkey", config.hotkey))
        config.clipboard_vault = ClipboardVaultSettings(
            enabled=bool(state.get("vault_enabled", config.clipboard_vault.enabled)),
            max_items=config.clipboard_vault.max_items,
        )
        self._write_config(config)
        return config

    # CLI fallback ---------------------------------------------------------
    def _run_cli(self) -> AppConfig:
        print("Aegis first-run setup (headless mode)")
        desktop = self._prompt("Desktop folder", self.default_config.desktop_path)
        downloads = self._prompt("Downloads folder", self.default_config.downloads_path)
        archive = self._prompt("Archive root", self.default_config.archive_root)
        reports = self._prompt("Reports root", self.default_config.reports_root)
        quarantine = self._prompt("Quarantine folder", self.default_config.quarantine_root)
        hotkey = self._prompt("Command palette hotkey", self.default_config.hotkey)
        vault_enabled_str = self._prompt("Enable clipboard vault? [y/N]", "n")
        vault_enabled = vault_enabled_str.strip().lower().startswith("y")
        passphrase = ""
        if vault_enabled:
            passphrase = getpass.getpass("Vault passphrase (leave blank to set later): ")
            if passphrase:
                self._persist_passphrase(passphrase)
        config = self.default_config
        config.desktop_path = desktop
        config.downloads_path = downloads
        config.archive_root = archive
        config.reports_root = reports
        config.quarantine_root = quarantine
        config.hotkey = hotkey
        config.watchers = WatcherSettings(desktop=True, downloads=True)
        config.clipboard_vault = ClipboardVaultSettings(enabled=vault_enabled, max_items=config.clipboard_vault.max_items)
        self._write_config(config)
        return config

    def _prompt(self, label: str, default: str) -> str:
        value = input(f"{label} [{default}]: ")
        return value.strip() or default

    def _write_config(self, config: AppConfig) -> None:
        ensure_directory(self.config_path.parent)
        self.config_path.write_text(config.json(indent=2), encoding="utf-8")
        LOGGER.info("Configuration written to %s", self.config_path)

    def _persist_passphrase(self, passphrase: str) -> None:
        try:
            import keyring  # type: ignore

            keyring.set_password("aegis", "vault", passphrase)
            LOGGER.info("Stored vault passphrase in system keyring")
        except Exception:  # pragma: no cover
            LOGGER.warning("Keyring unavailable; prompt will appear on next launch")


__all__ = ["FirstRunWizard"]
