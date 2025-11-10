"""First-run configuration wizard for desktop users."""

from __future__ import annotations

import getpass
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..config.paths import ensure_parent, get_config_path
from ..config.schema import AppConfig, ClipboardVaultSettings, WatcherSettings
from ..core.utils import ensure_directory

LOGGER = logging.getLogger(__name__)


@dataclass
class WizardAutomation:
    """Values used for non-interactive wizard execution (tests/CI)."""

    desktop_path: str
    downloads_path: str
    archive_root: str
    quarantine_root: str
    reports_root: Optional[str] = None
    snippets_root: Optional[str] = None
    hotkey: str = "alt+space"
    tray_enabled: bool = True
    watch_desktop: bool = True
    watch_downloads: bool = True
    vault_enabled: bool = False
    vault_passphrase: str = ""
    use_ollama: bool = False
    ollama_url: str = "http://localhost:11434"


class FirstRunWizard:
    """Collect onboarding preferences via Tkinter or CLI fallback."""

    def __init__(self, defaults: AppConfig, config_path: Path | None = None) -> None:
        self.defaults = defaults
        self.config_path = config_path or get_config_path()
        ensure_parent(self.config_path)

    # ------------------------------------------------------------------ API
    def run(self, automation: WizardAutomation | None = None) -> AppConfig:
        """Run the wizard, falling back to CLI when Tk is unavailable."""

        if automation:
            return self._apply_automation(automation)
        try:
            return self._run_tk()
        except Exception as exc:  # pragma: no cover - UI fallback path
            LOGGER.warning("Tkinter wizard unavailable (%s); using CLI prompts", exc)
            return self._run_cli()

    # ----------------------------------------------------------------- Utils
    def _apply_automation(self, automation: WizardAutomation) -> AppConfig:
        LOGGER.debug("Applying automated wizard configuration")
        config = AppConfig.from_dict(self.defaults.to_dict())
        config.desktop_path = automation.desktop_path
        config.downloads_path = automation.downloads_path
        config.archive_root = automation.archive_root
        config.quarantine_root = automation.quarantine_root
        config.reports_root = automation.reports_root or self.defaults.reports_root
        config.snippets_root = automation.snippets_root or self.defaults.snippets_root
        config.hotkey = automation.hotkey
        config.tray_enabled = automation.tray_enabled
        config.watchers = WatcherSettings(
            desktop=automation.watch_desktop,
            downloads=automation.watch_downloads,
        )
        config.clipboard_vault = ClipboardVaultSettings(
            enabled=automation.vault_enabled,
            max_items=self.defaults.clipboard_vault.max_items,
        )
        config.use_ollama = automation.use_ollama
        config.ollama_url = automation.ollama_url
        self._write_config(config)
        if automation.vault_enabled and automation.vault_passphrase:
            self._persist_passphrase(automation.vault_passphrase)
        return config

    def _collect_paths(self, selections: Dict[str, str]) -> None:
        for key, value in selections.items():
            path = Path(value).expanduser()
            ensure_directory(path)
            selections[key] = str(path)

    def _write_config(self, config: AppConfig) -> None:
        ensure_parent(self.config_path)
        payload = config.json(indent=2)
        self.config_path.write_text(payload, encoding="utf-8")
        LOGGER.info("Configuration saved to %s", self.config_path)

    def _persist_passphrase(self, passphrase: str) -> None:
        if not passphrase:
            return
        try:  # pragma: no cover - optional dependency
            import importlib

            keyring = importlib.import_module("keyring")
            keyring.set_password("aegis", "vault", passphrase)
            LOGGER.info("Stored vault passphrase in system keyring")
        except Exception:
            LOGGER.warning("Keyring unavailable; fall back to AEGIS_VAULT_PASSPHRASE env")
            os.environ.setdefault("AEGIS_VAULT_PASSPHRASE", passphrase)

    # ----------------------------------------------------------- Tk wizard
    def _run_tk(self) -> AppConfig:  # pragma: no cover - requires GUI
        import tkinter as tk
        from tkinter import filedialog, messagebox

        root = tk.Tk()
        root.title("Welcome to Aegis")
        root.geometry("520x420")

        config = AppConfig.from_dict(self.defaults.to_dict())

        selections: Dict[str, Any] = {
            "desktop_path": self.defaults.desktop_path,
            "downloads_path": self.defaults.downloads_path,
            "archive_root": self.defaults.archive_root,
            "quarantine_root": self.defaults.quarantine_root,
            "reports_root": self.defaults.reports_root,
            "snippets_root": self.defaults.snippets_root,
        }

        watch_desktop = tk.BooleanVar(value=self.defaults.watchers.desktop)
        watch_downloads = tk.BooleanVar(value=self.defaults.watchers.downloads)
        tray_enabled = tk.BooleanVar(value=self.defaults.tray_enabled)
        hotkey_var = tk.StringVar(value=self.defaults.hotkey)
        vault_enabled = tk.BooleanVar(value=self.defaults.clipboard_vault.enabled)
        passphrase_var = tk.StringVar(value="")
        passphrase_confirm = tk.StringVar(value="")
        use_ollama = tk.BooleanVar(value=self.defaults.use_ollama)
        ollama_url = tk.StringVar(value=self.defaults.ollama_url)

        frames: list[tk.Frame] = []
        current_index = tk.IntVar(value=0)

        def show_frame(index: int) -> None:
            for idx, frame in enumerate(frames):
                frame.pack_forget()
                if idx == index:
                    frame.pack(fill=tk.BOTH, expand=True)
            current_index.set(index)

        container = tk.Frame(root)
        container.pack(fill=tk.BOTH, expand=True)

        # Step 1: watch folders
        step1 = tk.Frame(container)
        tk.Label(step1, text="Choose folders to watch", font=("TkDefaultFont", 12, "bold")).pack(
            anchor=tk.W, padx=12, pady=12
        )

        def add_path_field(label: str, key: str, default: str) -> None:
            frame = tk.Frame(step1)
            frame.pack(fill=tk.X, padx=12, pady=4)
            tk.Label(frame, text=label, width=16, anchor=tk.W).pack(side=tk.LEFT)
            var = tk.StringVar(value=default)
            entry = tk.Entry(frame, textvariable=var)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

            def choose() -> None:
                chosen = filedialog.askdirectory(initialdir=default) or default
                var.set(chosen)

            tk.Button(frame, text="Browse", command=choose).pack(side=tk.RIGHT)
            selections[key] = var

        add_path_field("Desktop", "desktop_path", self.defaults.desktop_path)
        add_path_field("Downloads", "downloads_path", self.defaults.downloads_path)
        tk.Checkbutton(step1, text="Watch Desktop", variable=watch_desktop).pack(anchor=tk.W, padx=16)
        tk.Checkbutton(step1, text="Watch Downloads", variable=watch_downloads).pack(anchor=tk.W, padx=16)
        frames.append(step1)

        # Step 2: archive/quarantine/report roots
        step2 = tk.Frame(container)
        tk.Label(step2, text="Archive and Quarantine", font=("TkDefaultFont", 12, "bold")).pack(
            anchor=tk.W, padx=12, pady=12
        )
        add_path_field("Archive", "archive_root", self.defaults.archive_root)
        add_path_field("Quarantine", "quarantine_root", self.defaults.quarantine_root)
        add_path_field("Reports", "reports_root", self.defaults.reports_root)
        add_path_field("Snippets", "snippets_root", self.defaults.snippets_root)
        frames.append(step2)

        # Step 3: hotkey and tray
        step3 = tk.Frame(container)
        tk.Label(step3, text="Hotkey and Tray", font=("TkDefaultFont", 12, "bold")).pack(
            anchor=tk.W, padx=12, pady=12
        )
        tk.Label(step3, text="Command palette hotkey").pack(anchor=tk.W, padx=12, pady=4)
        tk.Entry(step3, textvariable=hotkey_var).pack(fill=tk.X, padx=12)
        tk.Checkbutton(step3, text="Enable system tray", variable=tray_enabled).pack(
            anchor=tk.W, padx=12, pady=8
        )
        frames.append(step3)

        # Step 4: vault and Ollama
        step4 = tk.Frame(container)
        tk.Label(step4, text="Clipboard Vault & AI", font=("TkDefaultFont", 12, "bold")).pack(
            anchor=tk.W, padx=12, pady=12
        )
        tk.Checkbutton(step4, text="Enable encrypted clipboard vault", variable=vault_enabled).pack(
            anchor=tk.W, padx=12
        )
        tk.Label(step4, text="Vault passphrase").pack(anchor=tk.W, padx=12, pady=2)
        tk.Entry(step4, show="*", textvariable=passphrase_var).pack(fill=tk.X, padx=12)
        tk.Label(step4, text="Confirm passphrase").pack(anchor=tk.W, padx=12, pady=2)
        tk.Entry(step4, show="*", textvariable=passphrase_confirm).pack(fill=tk.X, padx=12)
        tk.Checkbutton(step4, text="Use Ollama (requires local server)", variable=use_ollama).pack(
            anchor=tk.W, padx=12, pady=8
        )
        tk.Label(step4, text="Ollama URL").pack(anchor=tk.W, padx=12, pady=2)
        tk.Entry(step4, textvariable=ollama_url).pack(fill=tk.X, padx=12)
        frames.append(step4)

        # Navigation buttons
        nav = tk.Frame(root)
        nav.pack(fill=tk.X, padx=12, pady=12)

        def next_step() -> None:
            idx = current_index.get()
            if idx < len(frames) - 1:
                show_frame(idx + 1)
            else:
                if not validate():
                    return
                root.destroy()

        def prev_step() -> None:
            idx = current_index.get()
            if idx > 0:
                show_frame(idx - 1)

        tk.Button(nav, text="Back", command=prev_step).pack(side=tk.LEFT)
        tk.Button(nav, text="Next", command=next_step).pack(side=tk.RIGHT)

        def validate() -> bool:
            values: Dict[str, str] = {}
            for key, var in selections.items():
                if isinstance(var, str):
                    values[key] = var
                else:
                    values[key] = var.get()
            try:
                self._collect_paths(values)
            except Exception as exc:
                messagebox.showerror("Aegis", f"Invalid path: {exc}")
                return False
            if vault_enabled.get():
                if not passphrase_var.get():
                    messagebox.showerror("Aegis", "Enter a vault passphrase or disable the vault")
                    return False
                if passphrase_var.get() != passphrase_confirm.get():
                    messagebox.showerror("Aegis", "Passphrases do not match")
                    return False
            config.desktop_path = values["desktop_path"]
            config.downloads_path = values["downloads_path"]
            config.archive_root = values["archive_root"]
            config.quarantine_root = values["quarantine_root"]
            config.reports_root = values["reports_root"]
            config.snippets_root = values["snippets_root"]
            config.watchers = WatcherSettings(
                desktop=bool(watch_desktop.get()),
                downloads=bool(watch_downloads.get()),
            )
            config.hotkey = hotkey_var.get().strip() or self.defaults.hotkey
            config.tray_enabled = bool(tray_enabled.get())
            config.clipboard_vault = ClipboardVaultSettings(
                enabled=bool(vault_enabled.get()),
                max_items=self.defaults.clipboard_vault.max_items,
            )
            config.use_ollama = bool(use_ollama.get())
            config.ollama_url = ollama_url.get().strip() or self.defaults.ollama_url
            self._write_config(config)
            if vault_enabled.get():
                self._persist_passphrase(passphrase_var.get())
            messagebox.showinfo("Aegis", f"Settings saved to {self.config_path}")
            return True

        show_frame(0)
        root.mainloop()
        return config

    # -------------------------------------------------------------- CLI path
    def _run_cli(self) -> AppConfig:
        config = AppConfig.from_dict(self.defaults.to_dict())

        def prompt(label: str, default: str) -> str:
            value = input(f"{label} [{default}]: ")
            return value.strip() or default

        selections = {
            "desktop_path": prompt("Desktop folder", self.defaults.desktop_path),
            "downloads_path": prompt("Downloads folder", self.defaults.downloads_path),
            "archive_root": prompt("Archive folder", self.defaults.archive_root),
            "quarantine_root": prompt("Quarantine folder", self.defaults.quarantine_root),
            "reports_root": prompt("Reports folder", self.defaults.reports_root),
            "snippets_root": prompt("Snippets folder", self.defaults.snippets_root),
        }
        self._collect_paths(selections)
        config.desktop_path = selections["desktop_path"]
        config.downloads_path = selections["downloads_path"]
        config.archive_root = selections["archive_root"]
        config.quarantine_root = selections["quarantine_root"]
        config.reports_root = selections["reports_root"]
        config.snippets_root = selections["snippets_root"]
        watch_desktop = prompt("Watch Desktop? [Y/n]", "y").lower().startswith("y")
        watch_downloads = prompt("Watch Downloads? [Y/n]", "y").lower().startswith("y")
        config.watchers = WatcherSettings(desktop=watch_desktop, downloads=watch_downloads)
        config.hotkey = prompt("Command palette hotkey", self.defaults.hotkey)
        config.tray_enabled = prompt("Enable tray icon? [Y/n]", "y").lower().startswith("y")
        vault_enabled = prompt("Enable clipboard vault? [y/N]", "n").lower().startswith("y")
        passphrase = ""
        if vault_enabled:
            passphrase = getpass.getpass("Vault passphrase (leave blank to cancel vault): ")
            confirm = getpass.getpass("Confirm passphrase: ")
            if not passphrase or passphrase != confirm:
                LOGGER.warning("Passphrase mismatch; disabling vault")
                vault_enabled = False
        config.clipboard_vault = ClipboardVaultSettings(
            enabled=vault_enabled,
            max_items=self.defaults.clipboard_vault.max_items,
        )
        ollama_enabled = prompt("Use Ollama? [y/N]", "n").lower().startswith("y")
        config.use_ollama = ollama_enabled
        if ollama_enabled:
            config.ollama_url = prompt("Ollama URL", self.defaults.ollama_url)
        self._write_config(config)
        if vault_enabled and passphrase:
            self._persist_passphrase(passphrase)
        return config


__all__ = ["FirstRunWizard", "WizardAutomation"]

