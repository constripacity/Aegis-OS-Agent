"""Quarantine utilities for suspicious files."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from ..config.schema import AppConfig
from .utils import ensure_directory

LOGGER = logging.getLogger(__name__)


class Quarantine:
    """Move suspicious files into a read-only quarantine folder."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.root = Path(config.quarantine_root).expanduser()
        ensure_directory(self.root)

    def isolate(self, path: Path) -> Path:
        destination = self.root / path.name
        counter = 1
        while destination.exists():
            destination = self.root / f"{path.stem}-{counter}{path.suffix}"
            counter += 1
        LOGGER.info("Quarantining %s", path)
        shutil.move(str(path), destination)
        try:
            destination.chmod(0o444)
        except Exception:  # pragma: no cover - platform specific
            LOGGER.debug("Failed to set read-only permissions for %s", destination)
        return destination


__all__ = ["Quarantine"]

