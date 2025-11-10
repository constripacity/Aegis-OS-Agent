"""Utility helpers for the Aegis agent."""

from __future__ import annotations

import hashlib
import logging
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


__all__ = ["ensure_directory", "hash_text", "timestamp_folder"]

