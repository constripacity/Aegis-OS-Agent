"""Utility helpers for the Aegis agent."""

from __future__ import annotations

import hashlib
import logging
import hashlib
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def ensure_directory(path: Path) -> None:
    """Ensure a directory exists."""

    if not path.exists():
        LOGGER.debug("Creating directory %s", path)
        path.mkdir(parents=True, exist_ok=True)


def hash_text(text: str, length: int = 8) -> str:
    """Return a deterministic short hash for a piece of text."""

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:length]


def timestamp_folder(now: datetime | None = None) -> str:
    """Return YYYY-MM formatted folder name."""

    now = now or datetime.utcnow()
    return f"{now.year:04d}-{now.month:02d}"


def day_folder(now: datetime | None = None) -> str:
    """Return YYYY-MM-DD formatted folder name."""

    now = now or datetime.utcnow()
    return now.strftime("%Y-%m-%d")


def sanitize_filename(name: str) -> str:
    """Return a filesystem-safe filename component."""

    invalid = set('<>:"/\\|?*')
    sanitized = "".join("_" if ch in invalid else ch for ch in name)
    sanitized = sanitized.strip() or "item"
    return sanitized


def open_path(path: Path) -> None:
    """Open a file or directory with the platform default handler."""

    path = path.expanduser()
    if not path.exists():
        LOGGER.warning("Cannot open missing path: %s", path)
        return
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


__all__ = [
    "ensure_directory",
    "hash_text",
    "timestamp_folder",
    "day_folder",
    "sanitize_filename",
    "open_path",
]
