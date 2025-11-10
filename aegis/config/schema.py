"""Configuration schema and loading utilities without external dependencies."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from platformdirs import PlatformDirs

LOGGER = logging.getLogger(__name__)


@dataclass
class ClipboardVaultSettings:
    enabled: bool = False
    max_items: int = 100

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClipboardVaultSettings":
        max_items = int(data.get("max_items", 100))
        if max_items < 1:
            max_items = 1
        return cls(enabled=bool(data.get("enabled", False)), max_items=max_items)


@dataclass
class SchedulerSettings:
    archive_days: int = 30
    zip_monthly: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SchedulerSettings":
        archive_days = int(data.get("archive_days", 30))
        if archive_days < 1:
            archive_days = 1
        return cls(archive_days=archive_days, zip_monthly=bool(data.get("zip_monthly", False)))


@dataclass
class WatcherSettings:
    desktop: bool = True
    downloads: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WatcherSettings":
        return cls(
            desktop=bool(data.get("desktop", True)),
            downloads=bool(data.get("downloads", True)),
        )


@dataclass
class AppConfig:
    desktop_path: str
    downloads_path: str
    archive_root: str
    reports_root: str
    snippets_root: str
    quarantine_root: str
    use_ollama: bool = False
    ollama_url: str = "http://localhost:11434"
    clipboard_poll_interval: float = 0.5
    clipboard_vault: ClipboardVaultSettings = field(default_factory=ClipboardVaultSettings)
    watchers: WatcherSettings = field(default_factory=WatcherSettings)
    scheduler: SchedulerSettings = field(default_factory=SchedulerSettings)
    hotkey: str = "alt+space"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        def _expand(value: str) -> str:
            return str(Path(value).expanduser())

        clipboard_vault = ClipboardVaultSettings.from_dict(data.get("clipboard_vault", {}))
        watchers = WatcherSettings.from_dict(data.get("watchers", {}))
        scheduler = SchedulerSettings.from_dict(data.get("scheduler", {}))
        poll_interval = float(data.get("clipboard_poll_interval", 0.5))
        if poll_interval <= 0:
            poll_interval = 0.5
        return cls(
            desktop_path=_expand(data["desktop_path"]),
            downloads_path=_expand(data["downloads_path"]),
            archive_root=_expand(data["archive_root"]),
            reports_root=_expand(data["reports_root"]),
            snippets_root=_expand(data["snippets_root"]),
            quarantine_root=_expand(data["quarantine_root"]),
            use_ollama=bool(data.get("use_ollama", False)),
            ollama_url=str(data.get("ollama_url", "http://localhost:11434")),
            clipboard_poll_interval=poll_interval,
            clipboard_vault=clipboard_vault,
            watchers=watchers,
            scheduler=scheduler,
            hotkey=str(data.get("hotkey", "alt+space")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "desktop_path": self.desktop_path,
            "downloads_path": self.downloads_path,
            "archive_root": self.archive_root,
            "reports_root": self.reports_root,
            "snippets_root": self.snippets_root,
            "quarantine_root": self.quarantine_root,
            "use_ollama": self.use_ollama,
            "ollama_url": self.ollama_url,
            "clipboard_poll_interval": self.clipboard_poll_interval,
            "clipboard_vault": self.clipboard_vault.__dict__,
            "watchers": self.watchers.__dict__,
            "scheduler": self.scheduler.__dict__,
            "hotkey": self.hotkey,
        }

    def json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def defaults_path() -> Path:
    return Path(__file__).with_name("defaults.json")


def config_dir() -> Path:
    dirs = PlatformDirs(appname="Aegis", appauthor="Aegis")
    path = Path(dirs.user_config_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config(user_config: Path | None = None) -> AppConfig:
    defaults = json.loads(defaults_path().read_text(encoding="utf-8"))
    config_data: Dict[str, Any] = dict(defaults)
    path = user_config or config_dir() / "config.json"
    if path.exists():
        try:
            user_data = json.loads(path.read_text(encoding="utf-8"))
            merged = {**defaults, **user_data}
            # nested dicts need merging explicitly
            for key in ["clipboard_vault", "watchers", "scheduler"]:
                if key in user_data:
                    merged[key] = {**defaults.get(key, {}), **user_data.get(key, {})}
            config_data = merged
        except json.JSONDecodeError as exc:  # pragma: no cover
            LOGGER.error("Invalid JSON in %s: %s", path, exc)
    return AppConfig.from_dict(config_data)


__all__ = [
    "AppConfig",
    "ClipboardVaultSettings",
    "SchedulerSettings",
    "WatcherSettings",
    "load_config",
    "config_dir",
    "defaults_path",
]

