"""Background scheduling.

The previous scheduler called ``executor.archive_old_files(...)`` once a day and
**moved files with no notice and no way back**. That is the single most alarming
thing a background agent can do, and it is the behaviour this project needed to
stop doing before anything else.

The scheduler now *proposes*. Once a day it builds a plan, and if the plan is
non-empty it publishes a notification telling the user how many files are ready
and how to review them. Files move only when a person runs ``aegis apply``.

``auto_apply`` exists for people who have decided they want the old behaviour,
is off by default, and even then every move goes through the journal so it can
be undone.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from ..config.schema import AppConfig
from .actions import ActionExecutor
from .bus import EventBus, NotificationEvent
from .plan import execute

LOGGER = logging.getLogger(__name__)

#: How often the archive job runs, in seconds.
DAILY = 24 * 60 * 60

#: How long the loop sleeps between stop checks, so shutdown is responsive.
TICK = 30.0


class SchedulerService:
    """Runs the daily archive proposal on a background thread."""

    def __init__(
        self,
        config: AppConfig,
        bus: EventBus,
        executor: ActionExecutor,
        *,
        interval_seconds: float = DAILY,
        auto_apply: bool = False,
    ) -> None:
        self.config = config
        self.bus = bus
        self.executor = executor
        self.interval_seconds = interval_seconds
        self.auto_apply = auto_apply
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_run: datetime | None = None

    # -- lifecycle -----------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="aegis-scheduler", daemon=True)
        self._thread.start()
        LOGGER.info(
            "Scheduler started (archive proposals every %.0f hours, auto-apply=%s)",
            self.interval_seconds / 3600,
            self.auto_apply,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=TICK + 1)
            self._thread = None
        LOGGER.info("Scheduler stopped")

    @property
    def last_run(self) -> datetime | None:
        return self._last_run

    # -- work ----------------------------------------------------------
    def _run(self) -> None:
        elapsed = self.interval_seconds  # run once on start
        while not self._stop.is_set():
            if elapsed >= self.interval_seconds:
                try:
                    self.run_archive_job()
                except Exception:  # pragma: no cover - a job must not kill the thread
                    LOGGER.exception("Archive job failed")
                elapsed = 0.0
            if self._stop.wait(TICK):
                return
            elapsed += TICK

    def run_archive_job(self) -> int:
        """Build the archive plan. Returns how many files it proposes to move."""
        self._last_run = datetime.now(timezone.utc)
        days = self.config.scheduler.archive_days
        plan = self.executor.preview_archive_old(days)
        if not plan:
            LOGGER.debug("Nothing older than %s days to archive", days)
            return 0

        if not self.auto_apply:
            self.bus.publish(
                NotificationEvent(
                    f"{len(plan)} file(s) have not been touched in {days} days. "
                    "Review with 'aegis plan', then 'aegis apply'. Nothing has moved.",
                    level="info",
                )
            )
            return len(plan)

        report = execute(plan.authorize(), self.executor.journal, self.executor.safe_roots)
        self.bus.publish(
            NotificationEvent(
                f"Archived {len(report.completed)} file(s) automatically. "
                f"Undo with: aegis undo {report.batch_id[:8]}",
                level="success" if report.ok else "warning",
            )
        )
        return len(report.completed)


__all__ = ["SchedulerService", "DAILY"]
