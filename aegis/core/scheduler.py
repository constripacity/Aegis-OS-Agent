"""Scheduling support for recurring tasks."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from ..config.schema import AppConfig
from .bus import EventBus, NotificationEvent
from .actions import ActionExecutor

LOGGER = logging.getLogger(__name__)


class SchedulerService:
    """Manage background jobs using a lightweight thread."""

    def __init__(self, config: AppConfig, bus: EventBus, executor: ActionExecutor) -> None:
        self.config = config
        self.bus = bus
        self.executor = executor
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        LOGGER.info("Scheduler started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
            LOGGER.info("Scheduler stopped")
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._archive_job()
            # sleep until next 24h cycle
            for _ in range(24 * 60):
                if self._stop_event.is_set():
                    return
                time.sleep(60)

    def _archive_job(self) -> None:
        LOGGER.debug("Running archive job at %s", datetime.utcnow())
        result = self.executor.archive_old_files(self.config.scheduler.archive_days)
        if result.moved_files:
            message = f"Archived {len(result.moved_files)} items to {result.archive_root}"
            self.bus.publish(NotificationEvent(message=message))


__all__ = ["SchedulerService"]

