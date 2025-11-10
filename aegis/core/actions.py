"""Safe file and clipboard actions."""

from __future__ import annotations

import logging
import shutil
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..config.schema import AppConfig
from .bus import EventBus, FileSystemEvent, NotificationEvent
from .classifiers import classify_file, classify_text
from .renamer import Renamer
from .summarizer import Summarizer
from .heuristics import clean_tracking_url, prepare_code_snippet
from .utils import ensure_directory, timestamp_folder, day_folder, hash_text, sanitize_filename
from .quarantine import Quarantine
from .vault import ClipboardVault

LOGGER = logging.getLogger(__name__)


@dataclass
class ArchiveResult:
    archive_root: Path
    moved_files: list[Path]


class ActionExecutor:
    """Execute intents with safety guarantees."""

    def __init__(self, bus: EventBus, notifier: "Notifier", config: AppConfig) -> None:
        self.bus = bus
        self.notifier = notifier
        self.config = config
        self.renamer = Renamer(config)
        self.summarizer = Summarizer(config)
        self.vault = ClipboardVault(config)
        self.snippets_root = Path(config.snippets_root).expanduser()
        ensure_directory(self.snippets_root)
        self._clipboard_history: deque[str] = deque(maxlen=config.clipboard_vault.max_items)
        self._last_file: Optional[Path] = None
        self._watcher_paused_until: Optional[datetime] = None
        self.quarantine = Quarantine(config)
        self.bus.subscribe("filesystem", self._on_filesystem_event)
        self.bus.subscribe("notification", self._on_notification_event)

    # Event handlers -------------------------------------------------------
    def _on_filesystem_event(self, event: FileSystemEvent) -> None:
        if not self.watchers_active():
            LOGGER.debug("Ignoring filesystem event while watchers paused")
            return
        path = Path(event.path)
        self._last_file = path
        classification = classify_file(path)
        if classification.label == "archive":
            indicators = self.quarantine.inspect_archive(path)
            if indicators:
                record = self.quarantine.isolate(
                    path,
                    reason="suspicious archive",
                    source=event.label,
                    indicators=indicators,
                    rule_id="archive_heuristic",
                )
                summary = ", ".join(indicators[:3])
                if len(indicators) > 3:
                    summary += ", …"
                self.bus.publish(
                    NotificationEvent(
                        f"Quarantined {Path(record.quarantined_path).name}: {summary}",
                        level="warning",
                    )
                )
                return

    def _on_notification_event(self, event: NotificationEvent) -> None:
        self.notifier.notify(event.message, level=event.level)

    # Clipboard ------------------------------------------------------------
    def record_clipboard(self, content: str) -> None:
        if not content or not content.strip():
            return
        classification = classify_text(content)
        processed = content.rstrip()
        if classification.label != "code":
            processed = processed.strip()
        if classification.label == "url":
            cleaned = clean_tracking_url(classification.details.get("clean", processed))
            if cleaned != processed:
                processed = cleaned
                self.bus.publish(NotificationEvent("Cleaned tracking parameters from URL", level="info"))
        LOGGER.debug("Recording clipboard content of length %s", len(processed))
        self._clipboard_history.appendleft(processed)
        if classification.label == "code":
            snippet_path = self._save_code_snippet(processed, classification.details.get("language"))
            if snippet_path:
                self.bus.publish(NotificationEvent(f"Saved snippet to {snippet_path.name}", level="success"))
        if self.config.clipboard_vault.enabled:
            self.vault.store(processed)

    def clipboard_snapshot(self) -> Optional[str]:
        return self._clipboard_history[0] if self._clipboard_history else None

    def summarize_clipboard(self) -> Optional[str]:
        latest = self.clipboard_snapshot()
        if latest:
            return self.summarizer.summarize_text(latest)
        return None

    def search_vault(self, query: str) -> list[str]:
        if not self.config.clipboard_vault.enabled:
            return []
        return self.vault.search(query)

    def wipe_vault(self) -> None:
        self.vault.wipe()
        self.bus.publish(NotificationEvent("Clipboard vault wiped", level="success"))

    def _save_code_snippet(self, content: str, language: Optional[str]) -> Optional[Path]:
        folder = self.snippets_root / day_folder()
        ensure_directory(folder)
        normalised = prepare_code_snippet(content)
        language_token = sanitize_filename((language or "snippet").lower())
        stem = f"{language_token}_{hash_text(normalised, length=6)}"
        extension_map = {"python": ".py", "javascript": ".js", "typescript": ".ts", "c": ".c"}
        suffix = extension_map.get((language or "").lower(), ".txt")
        path = folder / f"{stem}{suffix}"
        counter = 1
        while path.exists():
            path = folder / f"{stem}-{counter}{suffix}"
            counter += 1
        fenced = normalised
        if not normalised.startswith("```"):
            fenced = f"```{language or ''}\n{normalised}\n```".strip() + "\n"
        path.write_text(fenced, encoding="utf-8")
        return path

    # Files ----------------------------------------------------------------
    def register_file_event(self, path: Path) -> None:
        self._last_file = path

    def organize_directory(self, label: str) -> ArchiveResult:
        if label not in {"desktop", "downloads"}:
            raise ValueError(f"Unknown label {label}")
        root = Path(getattr(self.config, f"{label}_path")).expanduser()
        archive_root = Path(self.config.archive_root).expanduser() / timestamp_folder()
        ensure_directory(archive_root)
        moved: list[Path] = []
        if not root.exists():
            return ArchiveResult(archive_root, moved)
        for path in root.iterdir():
            if path.is_file():
                destination = archive_root / path.name
                counter = 1
                while destination.exists():
                    destination = archive_root / f"{path.stem}-{counter}{path.suffix}"
                    counter += 1
                LOGGER.info("Archiving %s to %s", path, destination)
                shutil.move(str(path), destination)
                moved.append(destination)
                self.bus.publish(
                    FileSystemEvent(str(destination), event_type="archived", label=label)
                )
        if moved:
            self.bus.publish(
                NotificationEvent(f"Moved {len(moved)} {label} items to archive", level="info")
            )
        return ArchiveResult(archive_root=archive_root, moved_files=moved)

    def rename_last_file(self, params: dict[str, object]) -> Optional[Path]:
        if not self._last_file or not self._last_file.exists():
            return None
        keywords = []
        if "style" in params and isinstance(params["style"], str):
            keywords.append(params["style"])
        classification = classify_file(self._last_file)
        keywords.append(classification.label)
        renamed = self.renamer.rename(self._last_file, keywords)
        self.bus.publish(
            NotificationEvent(f"Renamed file to {renamed.name}", level="success")
        )
        return renamed

    def archive_old_files(self, age_days: int) -> ArchiveResult:
        cutoff = datetime.utcnow() - timedelta(days=age_days)
        archive_root = Path(self.config.archive_root).expanduser() / timestamp_folder()
        ensure_directory(archive_root)
        moved: list[Path] = []
        for label in ("desktop", "downloads"):
            root = Path(getattr(self.config, f"{label}_path")).expanduser()
            if not root.exists():
                continue
            for path in root.iterdir():
                if path.is_file() and datetime.utcfromtimestamp(path.stat().st_mtime) < cutoff:
                    destination = archive_root / path.name
                    counter = 1
                    while destination.exists():
                        destination = archive_root / f"{path.stem}-{counter}{path.suffix}"
                        counter += 1
                    LOGGER.info("Auto-archiving %s", path)
                    shutil.move(str(path), destination)
                    moved.append(destination)
        if moved:
            self.bus.publish(
                NotificationEvent(f"Archived {len(moved)} files to {archive_root}")
            )
        return ArchiveResult(archive_root=archive_root, moved_files=moved)

    # Watchers -------------------------------------------------------------
    def pause_watchers(self, minutes: int) -> None:
        self._watcher_paused_until = datetime.utcnow() + timedelta(minutes=minutes)
        self.bus.publish(NotificationEvent(f"Watchers paused for {minutes} minutes", level="info"))

    def watchers_active(self) -> bool:
        if not self._watcher_paused_until:
            return True
        if datetime.utcnow() > self._watcher_paused_until:
            self._watcher_paused_until = None
            return True
        return False

    def resume_watchers(self) -> None:
        self._watcher_paused_until = None
        self.bus.publish(NotificationEvent("Watchers resumed", level="info"))


__all__ = ["ActionExecutor", "ArchiveResult"]

