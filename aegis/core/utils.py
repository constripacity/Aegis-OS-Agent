"""Utility helpers for the Aegis agent."""



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


def human_size(num: int) -> str:
    """Format a byte count the way a person reads it.

    `aegis large` used to print every size as ``{n / 1024**2:.1f} MB``, so a
    folder of ordinary documents came out as eleven rows of ``0.0 MB`` — a
    listing sorted by a number it refused to show you.
    """
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1024
    return f"{num} B"  # pragma: no cover - unreachable; the loop always returns


def open_path(path: Path) -> bool:
    """Reveal a **directory** in the platform file manager.

    This is the only place in Aegis that starts another process, and it is
    deliberately narrow:

    * it opens directories only. Handing an arbitrary *file* to ``open`` or
      ``xdg-open`` means the operating system picks a handler for it, which for
      a ``.desktop`` or ``.command`` file means execution. Aegis never needs
      that, so it is refused;
    * the command is an argv list with ``shell=False``, so nothing in the path
      can be interpreted;
    * the caller's path must already have come from configuration, not from a
      watcher or a language model.

    Returns True if a handler was launched.
    """
    path = path.expanduser()
    if not path.exists():
        LOGGER.warning("Cannot open missing path: %s", path)
        return False
    if not path.is_dir():
        LOGGER.warning(
            "Refusing to open %s: Aegis only reveals folders, never hands a file "
            "to the system's default handler.",
            path,
        )
        return False

    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", "--", str(path)], check=False, shell=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False, shell=False)
    except OSError as exc:  # pragma: no cover - platform dependent
        LOGGER.warning("Could not open %s: %s", path, exc)
        return False
    return True


__all__ = [
    "ensure_directory",
    "hash_text",
    "timestamp_folder",
    "day_folder",
    "sanitize_filename",
    "human_size",
    "open_path",
]

