"""Filename generation utilities."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from .heuristics import generate_filename

LOGGER = logging.getLogger(__name__)


class Renamer:
    """Generate descriptive filenames using deterministic heuristics."""

    def __init__(self, config: "AppConfig") -> None:
        self.config = config

    def rename(self, path: Path, keywords: Iterable[str] | None = None) -> Path:
        if not path.exists():
            raise FileNotFoundError(path)
        keywords = list(keywords or [])
        new_name = generate_filename(path, keywords)
        target = path.with_name(new_name)
        counter = 1
        base, suffix = target.stem, target.suffix
        while target.exists():
            target = path.with_name(f"{base}-{counter}{suffix}")
            counter += 1
        LOGGER.debug("Renaming %s to %s", path, target)
        path.rename(target)
        return target


__all__ = ["Renamer"]

