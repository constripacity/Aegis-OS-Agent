"""Plans: what Aegis *would* do, computed without doing any of it.

The lifecycle every filesystem change goes through is:

    PLAN  →  PREVIEW  →  AUTHORIZE  →  EXECUTE  →  JOURNAL  →  UNDO

A :class:`Plan` is the first three steps. It is a pure value: building one reads
directory metadata and nothing else, so it is safe to build, print, diff, save
and throw away. Only :func:`execute` touches the filesystem, and it refuses to
run a plan that has not been marked authorised.

This is the shape the popular tools in this space converge on — a visible list
of proposed changes before anything happens — and it is what the previous
``organize_directory()`` lacked entirely: it moved every file out of Desktop and
Downloads immediately, with no preview and no way back.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .journal import ActionJournal, ActionKind, hash_file, new_batch_id
from .safety import SafeRoots, UnsafePathError, unique_destination
from .utils import human_size

LOGGER = logging.getLogger(__name__)


@dataclass
class PlannedAction:
    """One proposed change. Nothing has happened yet."""

    kind: ActionKind
    source: Path
    destination: Path
    rule: str
    reason: str
    size: int = 0
    warnings: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_rename(self) -> bool:
        return self.source.parent == self.destination.parent

    def describe(self) -> str:
        if self.is_rename:
            return f"{self.source.name}  →  {self.destination.name}"
        return f"{self.source.name}  →  {self.destination.parent}{Path().anchor or '/'}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "source": str(self.source),
            "destination": str(self.destination),
            "rule": self.rule,
            "reason": self.reason,
            "size": self.size,
            "warnings": list(self.warnings),
        }


@dataclass
class Plan:
    """A reviewable set of proposed changes."""

    actions: list[PlannedAction] = field(default_factory=list)
    skipped: list[tuple] = field(default_factory=list)  # (path, why)
    title: str = "Plan"
    trigger: str = "manual"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    _authorized: bool = False

    # -- inspection ----------------------------------------------------
    def __len__(self) -> int:
        return len(self.actions)

    def __bool__(self) -> bool:
        return bool(self.actions)

    @property
    def total_bytes(self) -> int:
        return sum(a.size for a in self.actions)

    @property
    def is_authorized(self) -> bool:
        return self._authorized

    def by_rule(self) -> dict[str, list[PlannedAction]]:
        grouped: dict[str, list[PlannedAction]] = {}
        for action in self.actions:
            grouped.setdefault(action.rule, []).append(action)
        return grouped

    def warnings(self) -> list[str]:
        return [w for action in self.actions for w in action.warnings]

    # -- preview -------------------------------------------------------
    def render(self, *, limit: int = 40, width: int = 78) -> str:
        """The dry-run diff. This is what the user reads before deciding."""
        if not self.actions and not self.skipped:
            return f"{self.title}: nothing to do."

        lines = [self.title, "=" * min(len(self.title), width), ""]
        for rule, actions in sorted(self.by_rule().items()):
            lines.append(f"{rule}  ({len(actions)})")
            for action in actions[:limit]:
                arrow = "rename" if action.is_rename else "move"
                lines.append(f"    {arrow:>6}  {action.source.name}")
                lines.append(f"            → {action.destination}")
                for warning in action.warnings:
                    lines.append(f"            ! {warning}")
            if len(actions) > limit:
                lines.append(f"    … and {len(actions) - limit} more")
            lines.append("")

        if self.skipped:
            lines.append(f"Left alone ({len(self.skipped)}):")
            for path, why in self.skipped[:10]:
                lines.append(f"    {Path(path).name}: {why}")
            if len(self.skipped) > 10:
                lines.append(f"    … and {len(self.skipped) - 10} more")
            lines.append("")

        lines.append(
            f"{len(self.actions)} change(s), {human_size(self.total_bytes)}. "
            "Nothing has been changed yet."
        )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "trigger": self.trigger,
            "created_at": self.created_at,
            "actions": [a.to_dict() for a in self.actions],
            "skipped": [{"path": str(p), "reason": r} for p, r in self.skipped],
        }

    # -- authorisation -------------------------------------------------
    def authorize(self) -> Plan:
        """Mark the plan as approved by a human.

        Kept explicit and separate so that no code path can accidentally execute
        a plan the user has not seen. :func:`execute` refuses anything else.
        """
        self._authorized = True
        return self


@dataclass
class ExecutionReport:
    batch_id: str
    completed: list[PlannedAction] = field(default_factory=list)
    failed: list[tuple] = field(default_factory=list)  # (action, error)

    @property
    def ok(self) -> bool:
        return not self.failed

    def describe(self) -> str:
        lines = [f"Applied {len(self.completed)} change(s). Batch {self.batch_id[:8]}."]
        for action, error in self.failed:
            lines.append(f"  ! {action.source.name}: {error}")
        if self.completed:
            lines.append(f"  Undo with:  aegis undo {self.batch_id[:8]}")
        return "\n".join(lines)


def execute(
    plan: Plan,
    journal: ActionJournal,
    roots: SafeRoots,
    *,
    reason: str | None = None,
    dry_run: bool = False,
) -> ExecutionReport:
    """Apply an authorised plan, journalling each change as it succeeds.

    Every action is re-validated at execution time. A plan is a snapshot; the
    filesystem may have moved on since it was built, and acting on a stale plan
    is how an automated tool destroys something.
    """
    if not plan.is_authorized:
        raise PermissionError(
            "this plan has not been authorised. Call plan.authorize() only after a "
            "human has seen plan.render()."
        )

    batch_id = new_batch_id()
    report = ExecutionReport(batch_id=batch_id)
    label = reason or plan.title

    for action in plan.actions:
        try:
            source = roots.check_source(action.source)
            destination = roots.check_destination(action.destination)
        except UnsafePathError as exc:
            report.failed.append((action, str(exc)))
            continue

        if dry_run:
            report.completed.append(action)
            continue

        try:
            digest = hash_file(source)
            size = source.stat().st_size
            destination.parent.mkdir(parents=True, exist_ok=True)
            _move(source, destination)
        except OSError as exc:
            report.failed.append((action, f"{type(exc).__name__}: {exc}"))
            continue

        journal.record(
            kind=action.kind,
            source=source,
            destination=destination,
            sha256=digest,
            size=size,
            reason=f"{label} · {action.reason}",
            trigger=plan.trigger,
            batch_id=batch_id,
            extra={"rule": action.rule},
        )
        report.completed.append(action)

    return report


def _move(source: Path, destination: Path) -> None:
    """Move, falling back to copy-verify-remove across filesystems."""
    import os
    import shutil

    try:
        os.replace(source, destination)
        return
    except OSError:
        pass
    shutil.copy2(source, destination)
    if hash_file(destination) != hash_file(source):  # pragma: no cover - IO race
        destination.unlink(missing_ok=True)
        raise OSError(f"copy of {source} to {destination} did not verify; original kept")
    source.unlink()


def resolve_conflicts(plan: Plan) -> Plan:
    """Give every action a free destination, including within the plan itself."""
    claimed: set[Path] = set()
    for action in plan.actions:
        destination = action.destination
        while destination in claimed or destination.exists():
            destination = unique_destination(
                destination if not destination.exists() else destination
            )
            if destination in claimed:
                destination = destination.with_name(f"{destination.stem}-x{destination.suffix}")
        if destination != action.destination:
            action.warnings.append(
                f"a file named {action.destination.name} was already there; "
                f"using {destination.name}"
            )
            action.destination = destination
        claimed.add(destination)
    return plan


__all__ = ["Plan", "PlannedAction", "ExecutionReport", "execute", "resolve_conflicts"]
