"""Helpers for resolving OS-specific configuration paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = [
    "get_config_directory",
    "get_config_path",
    "ensure_parent",
]


def get_config_directory() -> Path:
    """Return the platform-specific configuration directory."""

    home = Path.home()
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "Aegis"
        return home / "AppData" / "Roaming" / "Aegis"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Aegis"
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / "aegis"
    return home / ".config" / "aegis"


def get_config_path() -> Path:
    """Return the canonical configuration file path."""

    directory = get_config_directory()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "config.json"


def ensure_parent(path: Path) -> None:
    """Ensure the parent directory of ``path`` exists."""

    path.parent.mkdir(parents=True, exist_ok=True)

