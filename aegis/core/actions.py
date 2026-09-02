"""The executor: everything Aegis can actually do.

The rule that shapes this module: **nothing that changes a file happens without
a plan the user has seen.** ``preview_*`` methods build a
:class:`~aegis.core.plan.Plan` and change nothing; ``apply_last_plan`` executes
the plan that was last previewed and journals every step; ``undo_last`` reverses
it. Automatic quarantine is the one exception — it triggers on a watcher event
rather than a command — and it is journalled and reversible for exactly that
reason.
"""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..config.schema import AppConfig
from .bus import EventBus, FileSystemEvent, NotificationEvent
from .classifiers import classify_file, classify_text
from .heuristics import clean_tracking_url
from .journal import ActionJournal, ActionKind, JournalError, UndoReport
from .notifier import Notifier
from .organizer import FileFacts, Organizer, default_rules
from .plan import ExecutionReport, Plan, PlannedAction, execute, resolve_conflicts
from .quarantine import Quarantine
from .renamer import Renamer
from .safety import SafeRoots, UnsafePathError, default_roots, unique_destination
from .secrets import classify_secret, redact
from .summarizer import Summarizer
from .utils import day_folder, ensure_directory, hash_text, sanitize_filename
from .vault import ClipboardVault

LOGGER = logging.getLogger(__name__)

#: Files larger than this are hashed by a cheap prefix first when looking for
#: duplicates, so a folder of 4 GB videos does not take minutes to survey.
DUPLICATE_PREFIX_BYTES = 64 * 1024


class ActionExecutor:
    """Executes intents. Owns the vault, the journal, quarantine and planning."""

    def __init__(self, bus: EventBus, notifier: Notifier, config: AppConfig) -> None:
        self.bus = bus
        self.notifier = notifier
        self.config = config

        self.safe_roots: SafeRoots = default_roots(config)
        self.journal = ActionJournal(Path(config.reports_root).expanduser(), self.safe_roots)
        self.renamer = Renamer(config)
        self.summarizer = Summarizer(config)
        self.vault = ClipboardVault(config)
        self.organizer = Organizer(default_rules(archive_after_days=config.scheduler.archive_days))
        self.quarantine = Quarantine(config, journal=self.journal, roots=self.safe_roots)

        self.snippets_root = Path(config.snippets_root).expanduser()
        ensure_directory(self.snippets_root)

        self._clipboard_history: deque[str] = deque(maxlen=max(1, config.clipboard_vault.max_items))
        self._last_file: Path | None = None
        self._last_plan: Plan | None = None
        self._watcher_paused_until: datetime | None = None

        self.bus.subscribe("filesystem", self._on_filesystem_event)
        self.bus.subscribe("notification", self._on_notification_event)

        if config.clipboard_vault.enabled and not self.vault.enabled:
            self.bus.publish(
                NotificationEvent(
                    f"Clipboard vault is off: {self.vault.unavailable_reason}", level="warning"
                )
            )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _on_filesystem_event(self, event: FileSystemEvent) -> None:
        if not self.watchers_active():
            return
        path = Path(event.path)
        self._last_file = path
        if classify_file(path).label != "archive":
            return

        indicators = self.quarantine.inspect_archive(path)
        if not indicators:
            return
        try:
            record = self.quarantine.isolate(
                path, reason="suspicious archive", source=event.label, indicators=indicators
            )
        except (UnsafePathError, OSError, RuntimeError) as exc:
            LOGGER.warning("Could not quarantine %s: %s", path, exc)
            self.bus.publish(
                NotificationEvent(f"Could not quarantine {path.name}: {exc}", level="warning")
            )
            return

        summary = "; ".join(indicators[:2])
        if len(indicators) > 2:
            summary += f" (+{len(indicators) - 2} more)"
        self.bus.publish(
            NotificationEvent(
                f"Quarantined {path.name}: {summary}. "
                f"Undo with: aegis undo {record.batch_id[:8]}",
                level="warning",
            )
        )

    def _on_notification_event(self, event: NotificationEvent) -> None:
        self.notifier.notify(event.message, level=event.level)

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------
    def record_clipboard(self, content: str) -> None:
        if not content or not content.strip():
            return

        classification = classify_text(content)
        verdict = classify_secret(content)
        if verdict:
            # Two different situations share one signal, and they deserve
            # different answers:
            #
            #   * the clipboard *is* the credential (you copied a password) —
            #     store nothing at all;
            #   * the clipboard is a config file or a code snippet that happens
            #     to contain one — keep the useful part, redact the credential.
            #
            # Excluding is stronger than encrypting, so when in doubt we exclude.
            redacted = redact(content)
            keeps_substance = (
                classification.label == "code"
                and len(redacted.replace("[redacted]", "").strip()) >= 40
            )
            if not keeps_substance:
                LOGGER.info("Clipboard entry ignored: it %s", verdict.reason)
                self.bus.publish(
                    NotificationEvent(
                        f"Ignored a clipboard entry that {verdict.reason}. "
                        "Nothing was saved.",
                        level="info",
                    )
                )
                return
            LOGGER.info("Clipboard entry redacted before saving: it %s", verdict.reason)
            self.bus.publish(
                NotificationEvent(
                    f"Saved a snippet with the credential removed — it {verdict.reason}.",
                    level="info",
                )
            )
            content = redacted
        processed = content.rstrip() if classification.label == "code" else content.strip()

        if classification.label == "url":
            cleaned = self._clean_url(processed)
            if cleaned != processed:
                processed = cleaned
                self.bus.publish(
                    NotificationEvent("Removed tracking parameters from the copied link")
                )

        self._clipboard_history.appendleft(processed)

        if classification.label == "code":
            snippet = self._save_code_snippet(processed, classification.details.get("language"))
            if snippet:
                self.bus.publish(
                    NotificationEvent(f"Saved snippet to {snippet.name}", level="success")
                )

        if self.config.clipboard_vault.enabled:
            self.vault.store(processed, entry_type=classification.label)

    def clipboard_snapshot(self) -> str | None:
        return self._clipboard_history[0] if self._clipboard_history else None

    def summarize_clipboard(self) -> str:
        latest = self.clipboard_snapshot()
        if not latest:
            message = "The clipboard is empty."
            self.bus.publish(NotificationEvent(message))
            return message
        result = self.summarizer.summarize(latest)
        self.bus.publish(NotificationEvent(result.text, level="success"))
        return result.text

    def search_vault(self, query: str) -> list[str]:
        if not query.strip():
            message = "Say what to look for, for example: find postgres"
            self.bus.publish(NotificationEvent(message, level="warning"))
            return []
        if not self.vault.enabled:
            reason = self.vault.unavailable_reason or "the clipboard vault is turned off"
            self.bus.publish(NotificationEvent(f"Cannot search: {reason}", level="warning"))
            return []
        entries = self.vault.search(query)
        self.bus.publish(
            NotificationEvent(
                f"{len(entries)} clipboard "
                f"{'entry' if len(entries) == 1 else 'entries'} matched"
            )
        )
        return [entry.content for entry in entries]

    def vault_status(self) -> str:
        if not self.config.clipboard_vault.enabled:
            status = "Clipboard vault: turned off in your configuration."
        elif not self.vault.enabled:
            status = f"Clipboard vault: unavailable — {self.vault.unavailable_reason}"
        else:
            status = (
                f"Clipboard vault: on, {self.vault.count()} entries, encrypted at "
                f"{self.vault.location}. Credentials are never stored."
            )
        self.bus.publish(NotificationEvent(status))
        return status

    def wipe_vault(self) -> int:
        removed = self.vault.wipe()
        self.bus.publish(
            NotificationEvent(f"Cleared {removed} clipboard entries", level="success")
        )
        return removed

    def _save_code_snippet(self, content: str, language: str | None) -> Path | None:
        """Write a code snippet to disk, with secrets redacted.

        The previous implementation wrote clipboard content verbatim. A copied
        snippet containing ``API_KEY = 'sk-live-…'`` therefore landed in a
        plaintext file on disk regardless of any vault setting. ``redact()``
        existed in this codebase already and was never called.
        """
        safe = redact(content)
        folder = self.snippets_root / day_folder()
        ensure_directory(folder)
        token = sanitize_filename((language or "snippet").lower())
        extension = {
            "python": ".py", "javascript": ".js", "typescript": ".ts",
            "c": ".c", "bash": ".sh", "html": ".html",
        }.get((language or "").lower(), ".txt")
        path = unique_destination(folder / f"{token}_{hash_text(safe, length=6)}{extension}")
        try:
            path.write_text(safe, encoding="utf-8")
            path.chmod(0o600)
        except OSError as exc:
            LOGGER.warning("Could not write snippet: %s", exc)
            return None
        if safe != content:
            LOGGER.info("Redacted secret-shaped content before writing %s", path.name)
        return path

    @staticmethod
    def _clean_url(url: str) -> str:
        return clean_tracking_url(url)

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------
    def preview_organize(self, folder: str = "downloads") -> Plan:
        """Build and show a plan. Changes nothing."""
        root = self._folder_path(folder)
        plan = self.organizer.plan(root, trigger=f"palette:{folder}")
        self._last_plan = plan
        self.bus.publish(
            NotificationEvent(
                f"{len(plan)} change(s) proposed for {root.name}. Nothing has moved yet."
                if plan
                else f"{root.name} is already tidy — nothing to do."
            )
        )
        return plan

    def preview_archive_old(self, days: int) -> Plan:
        """Plan moving anything older than *days* into the archive root."""
        archive_root = Path(self.config.archive_root).expanduser()
        cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, days))
        plan = Plan(title=f"Archive files older than {days} days", trigger="palette:archive")

        for label in ("desktop", "downloads"):
            root = self._folder_path(label)
            if not root.is_dir():
                continue
            for path in sorted(root.iterdir()):
                if path.is_symlink() or not path.is_file() or path.name.startswith("."):
                    continue
                try:
                    facts = FileFacts.of(path)
                except OSError as exc:
                    plan.skipped.append((path, f"could not read: {exc}"))
                    continue
                if facts.modified >= cutoff:
                    plan.skipped.append((path, f"modified {facts.age_days:.0f} days ago"))
                    continue
                plan.actions.append(
                    PlannedAction(
                        kind=ActionKind.MOVE,
                        source=path,
                        destination=archive_root / facts.modified.strftime("%Y-%m") / path.name,
                        rule=f"Older than {days} days",
                        reason=f"last modified {facts.age_days:.0f} days ago",
                        size=facts.size,
                    )
                )
        plan = resolve_conflicts(plan)
        self._last_plan = plan
        self.bus.publish(
            NotificationEvent(f"{len(plan)} file(s) would be archived. Nothing has moved yet.")
        )
        return plan

    def apply_last_plan(self) -> ExecutionReport | None:
        """Execute the plan most recently previewed."""
        if self._last_plan is None:
            self.bus.publish(
                NotificationEvent(
                    "There is no plan to apply. Run a preview first.", level="warning"
                )
            )
            return None
        if not self._last_plan:
            self.bus.publish(NotificationEvent("The last plan had nothing in it."))
            return None

        report = execute(self._last_plan.authorize(), self.journal, self.safe_roots)
        self._last_plan = None
        level = "success" if report.ok else "warning"
        self.bus.publish(
            NotificationEvent(
                f"Applied {len(report.completed)} change(s). "
                f"Undo with: aegis undo {report.batch_id[:8]}",
                level=level,
            )
        )
        return report

    @property
    def last_plan(self) -> Plan | None:
        return self._last_plan

    # ------------------------------------------------------------------
    # History and undo
    # ------------------------------------------------------------------
    def history(self, limit: int = 20) -> list[str]:
        batches = self.journal.batches()[:limit]
        if not batches:
            self.bus.publish(NotificationEvent("Aegis has not changed anything yet."))
            return []
        lines = [batch.describe() for batch in batches]
        self.bus.publish(NotificationEvent(f"{len(batches)} batch(es) in the action journal"))
        return lines

    def undo_last(self) -> UndoReport | None:
        batch = self.journal.last_batch()
        if batch is None:
            self.bus.publish(NotificationEvent("There is nothing to undo.", level="warning"))
            return None
        return self.undo(batch.batch_id)

    def undo(self, batch_id: str, *, force: bool = False) -> UndoReport | None:
        try:
            report = self.journal.undo_batch(batch_id, force=force)
        except JournalError as exc:
            self.bus.publish(NotificationEvent(str(exc), level="warning"))
            return None
        self.bus.publish(
            NotificationEvent(
                f"Restored {len(report.restored)} file(s)",
                level="success" if report.ok else "warning",
            )
        )
        return report

    # ------------------------------------------------------------------
    # Read-only surveys
    # ------------------------------------------------------------------
    def large_files(self, folder: str = "downloads", limit: int = 15) -> list[tuple[Path, int]]:
        root = self._folder_path(folder)
        found: list[tuple[Path, int]] = []
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    found.append((path, path.stat().st_size))
                except OSError:
                    continue
        found.sort(key=lambda pair: pair[1], reverse=True)
        return found[:limit]

    def find_duplicates(self, folder: str = "downloads") -> list[list[Path]]:
        """Group files with identical contents.

        Sized first, then a cheap prefix hash, then a full hash only for the
        candidates that survive — so a folder of large videos is not fully read.
        """
        root = self._folder_path(folder)
        if not root.is_dir():
            return []

        by_size: dict[int, list[Path]] = defaultdict(list)
        for path in root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                by_size[path.stat().st_size].append(path)
            except OSError:
                continue

        groups: list[list[Path]] = []
        for size, paths in by_size.items():
            if len(paths) < 2 or size == 0:
                continue
            by_prefix: dict[str, list[Path]] = defaultdict(list)
            for path in paths:
                try:
                    with path.open("rb") as handle:
                        prefix = hashlib.sha256(handle.read(DUPLICATE_PREFIX_BYTES)).hexdigest()
                except OSError:
                    continue
                by_prefix[prefix].append(path)
            for candidates in by_prefix.values():
                if len(candidates) < 2:
                    continue
                by_full: dict[str, list[Path]] = defaultdict(list)
                for path in candidates:
                    try:
                        by_full[_full_hash(path)].append(path)
                    except OSError:
                        continue
                groups.extend(group for group in by_full.values() if len(group) > 1)
        groups.sort(key=lambda group: -group[0].stat().st_size)
        return groups

    # ------------------------------------------------------------------
    # Watchers
    # ------------------------------------------------------------------
    def pause_watchers(self, minutes: int) -> None:
        self._watcher_paused_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        self.bus.publish(
            NotificationEvent(f"Watchers paused for {minutes} minute(s)", level="info")
        )

    def resume_watchers(self) -> None:
        self._watcher_paused_until = None
        self.bus.publish(NotificationEvent("Watchers resumed", level="info"))

    def watchers_active(self) -> bool:
        if self._watcher_paused_until is None:
            return True
        if datetime.now(timezone.utc) > self._watcher_paused_until:
            self._watcher_paused_until = None
            return True
        return False

    def register_file_event(self, path: Path) -> None:
        self._last_file = path

    def rename_last_file(self, params: dict[str, Any]) -> Path | None:
        """Rename the most recent file, via a plan so it can be undone."""
        if not self._last_file or not self._last_file.exists():
            return None
        keywords: list[str] = []
        style = params.get("style")
        if isinstance(style, str):
            keywords.append(style)
        keywords.append(classify_file(self._last_file).label)
        return self.renamer.rename(self._last_file, keywords)

    # ------------------------------------------------------------------
    def _folder_path(self, label: str) -> Path:
        attribute = {"desktop": "desktop_path", "downloads": "downloads_path"}.get(label)
        if attribute is None:
            raise ValueError(
                f"Unknown folder {label!r}. Aegis manages 'desktop' and 'downloads'."
            )
        return Path(getattr(self.config, attribute)).expanduser()

    def close(self) -> None:
        self.vault.close()


def _full_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["ActionExecutor"]
