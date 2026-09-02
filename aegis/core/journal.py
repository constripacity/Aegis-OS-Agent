"""Append-only journal of everything Aegis changes, with undo.

An agent that moves your files earns trust exactly once: the first time you
change your mind and it puts everything back. Before this module, Aegis had no
record of what it had done and no way to reverse it — ``organize_directory()``
moved every file out of Desktop and Downloads with no preview, no confirmation
and no undo.

The journal is a JSONL file. Append-only means a crash mid-write costs at most
the last line, and the file can be read by ``tail`` or ``jq`` without this
program. Each record carries enough to reverse itself: source, destination,
content hash, and the operation kind.

Undo is applied in reverse order within a batch, and each step is verified
against the recorded hash before it is reversed, so a file the user edited in
the meantime is never silently clobbered.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .safety import SafeRoots, UnsafePathError

LOGGER = logging.getLogger(__name__)

CHUNK = 1024 * 1024
JOURNAL_NAME = "actions.jsonl"


class ActionKind(str, Enum):
    MOVE = "move"
    RENAME = "rename"
    QUARANTINE = "quarantine"
    UNDO = "undo"


class JournalError(RuntimeError):
    """An action could not be recorded, applied or reversed safely."""


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class ActionRecord:
    """One completed change, and everything needed to reverse it."""

    action_id: str
    batch_id: str
    kind: str
    source: str
    destination: str
    sha256: str
    size: int
    timestamp: str
    reason: str
    trigger: str
    undone_at: str | None = None
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionRecord:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    @property
    def is_reversible(self) -> bool:
        return self.undone_at is None and self.kind in {
            ActionKind.MOVE.value,
            ActionKind.RENAME.value,
            ActionKind.QUARANTINE.value,
        }


@dataclass(frozen=True)
class BatchSummary:
    batch_id: str
    timestamp: str
    reason: str
    trigger: str
    action_count: int
    reversible: int
    kinds: list[str]

    def describe(self) -> str:
        state = "reversible" if self.reversible else "already undone"
        return (
            f"{self.batch_id[:8]}  {self.timestamp}  {self.action_count} "
            f"{'change' if self.action_count == 1 else 'changes'} "
            f"({', '.join(self.kinds)}) — {self.reason} [{state}]"
        )


class ActionJournal:
    """Reads and writes the action log, and performs undo."""

    def __init__(self, root: Path, roots: SafeRoots) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / JOURNAL_NAME
        self.safe_roots = roots

    # -- writing -------------------------------------------------------
    def record(
        self,
        *,
        kind: ActionKind,
        source: Path,
        destination: Path,
        sha256: str,
        size: int,
        reason: str,
        trigger: str,
        batch_id: str,
        extra: dict[str, Any] | None = None,
    ) -> ActionRecord:
        record = ActionRecord(
            action_id=uuid.uuid4().hex,
            batch_id=batch_id,
            kind=kind.value,
            source=str(source),
            destination=str(destination),
            sha256=sha256,
            size=size,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            reason=reason,
            trigger=trigger,
            extra=dict(extra or {}),
        )
        self._append(record)
        return record

    def _append(self, record: ActionRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.to_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    # -- reading -------------------------------------------------------
    def _iter_raw(self) -> Iterator[ActionRecord]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield ActionRecord.from_dict(json.loads(line))
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    LOGGER.warning("Skipping malformed journal line %s: %s", line_number, exc)

    def records(self) -> list[ActionRecord]:
        """Latest state of every action, replaying the append-only log."""
        latest: dict[str, ActionRecord] = {}
        for record in self._iter_raw():
            existing = latest.get(record.action_id)
            if existing is None or record.undone_at:
                latest[record.action_id] = record
        return sorted(latest.values(), key=lambda r: r.timestamp)

    def batches(self) -> list[BatchSummary]:
        """Actions grouped by the batch that produced them, newest first."""
        groups: dict[str, list[ActionRecord]] = {}
        for record in self.records():
            groups.setdefault(record.batch_id, []).append(record)
        summaries = [
            BatchSummary(
                batch_id=batch_id,
                timestamp=items[0].timestamp,
                reason=items[0].reason,
                trigger=items[0].trigger,
                action_count=len(items),
                reversible=sum(1 for r in items if r.is_reversible),
                kinds=sorted({r.kind for r in items}),
            )
            for batch_id, items in groups.items()
        ]
        return sorted(summaries, key=lambda s: s.timestamp, reverse=True)

    def last_batch(self) -> BatchSummary | None:
        reversible = [b for b in self.batches() if b.reversible]
        return reversible[0] if reversible else None

    # -- undo ----------------------------------------------------------
    def undo_batch(self, batch_id: str, *, force: bool = False) -> UndoReport:
        """Reverse every reversible action in a batch, newest first."""
        matching = [
            r for r in self.records() if r.batch_id.startswith(batch_id) and r.is_reversible
        ]
        if not matching:
            raise JournalError(
                f"no reversible actions found for batch {batch_id!r}. "
                "Run 'aegis history' to see what can be undone."
            )
        matching.sort(key=lambda r: r.timestamp, reverse=True)

        restored: list[ActionRecord] = []
        skipped: list[tuple[ActionRecord, str]] = []
        for record in matching:
            try:
                self._reverse(record, force=force)
            except (JournalError, UnsafePathError, OSError) as exc:
                skipped.append((record, str(exc)))
                LOGGER.warning("Could not undo %s: %s", record.action_id[:8], exc)
                continue
            record.undone_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._append(record)
            restored.append(record)

        return UndoReport(batch_id=matching[0].batch_id, restored=restored, skipped=skipped)

    def _reverse(self, record: ActionRecord, *, force: bool) -> None:
        destination = Path(record.destination)
        source = Path(record.source)

        if not destination.exists():
            raise JournalError(f"{destination} is no longer there")

        current = hash_file(destination)
        if current != record.sha256 and not force:
            raise JournalError(
                f"{destination.name} has changed since Aegis moved it "
                f"(expected {record.sha256[:12]}, found {current[:12]}). "
                "Re-run with --force if you are sure."
            )

        if source.exists() and not force:
            raise JournalError(
                f"something already exists at the original location {source}; "
                "not overwriting it"
            )

        # The destination must be inside a root Aegis controls. The source is
        # where the file came from, which by construction was also inside one.
        self.safe_roots.check(destination, what="journalled destination")
        restore_anchor = source.parent if source.parent.exists() else source
        self.safe_roots.check(restore_anchor, what="restore target")

        source.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(destination, source)
        except OSError:
            shutil.copy2(destination, source)
            if hash_file(source) != record.sha256 and not force:
                source.unlink(missing_ok=True)
                raise JournalError(
                    f"copy of {destination.name} back to {source} did not verify; "
                    "the quarantined copy has been left in place"
                ) from None
            destination.unlink()
        LOGGER.info("Undid %s: %s -> %s", record.kind, destination, source)


@dataclass(frozen=True)
class UndoReport:
    batch_id: str
    restored: list[ActionRecord]
    skipped: list[tuple]

    def describe(self) -> str:
        lines = [f"Undid {len(self.restored)} change(s) from batch {self.batch_id[:8]}."]
        for record in self.restored:
            lines.append(f"  ✓ {Path(record.destination).name} → {record.source}")
        for record, reason in self.skipped:
            lines.append(f"  ! {Path(record.destination).name}: {reason}")
        return "\n".join(lines)

    @property
    def ok(self) -> bool:
        return not self.skipped


def new_batch_id() -> str:
    return uuid.uuid4().hex


__all__ = [
    "ActionJournal",
    "ActionRecord",
    "ActionKind",
    "BatchSummary",
    "UndoReport",
    "JournalError",
    "hash_file",
    "new_batch_id",
]
