"""Filename generation utilities."""



import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .utils import ensure_directory, hash_text

LOGGER = logging.getLogger(__name__)


class Renamer:
    """Generate descriptive filenames using heuristics or AI."""

    def __init__(self, config: "AppConfig") -> None:
        self.config = config

    def rename(self, path: Path, keywords: Iterable[str] | None = None) -> Path:
        """Return a new safe filename for the given path."""

        if not path.exists():
            raise FileNotFoundError(path)
        keywords = list(keywords or [])
        timestamp = datetime.utcnow().strftime("%Y-%m-%d")
        safe_keywords = [sanitize_token(token) for token in keywords if token]
        base = "_".join([token for token in safe_keywords if token])
        if base:
            base = f"{base}_{timestamp}"
        else:
            base = f"file_{timestamp}"
        base += f"_{hash_text(path.name)}"
        new_name = f"{base}{path.suffix.lower()}"
        target = path.with_name(new_name)
        counter = 1
        while target.exists():
            target = path.with_name(f"{base}-{counter}{path.suffix.lower()}")
            counter += 1
        LOGGER.debug("Renaming %s to %s", path, target)
        path.rename(target)
        return target


def sanitize_token(token: str) -> str:
    return "".join(ch for ch in token.replace(" ", "_") if ch.isalnum() or ch in {"_", "-"}).strip("_-")


__all__ = ["Renamer", "sanitize_token"]

