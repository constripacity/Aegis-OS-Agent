"""Rule-based file organisation that produces plans, never side effects.

The previous ``organize_directory()`` moved **every file** out of Desktop and
Downloads into a timestamped archive folder, immediately, with no preview and no
undo. That is not organisation, it is a bulk relocation, and it is the reason a
tool like this is scary to install.

This module instead evaluates a small, ordered, declarative ruleset against
directory metadata and returns a :class:`~aegis.core.plan.Plan`. The default
rules are deliberately conservative: they sort by kind and age into
subdirectories of the folder being organised, they never touch anything modified
in the last day, and they never delete.
"""
from __future__ import annotations

import fnmatch
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .journal import ActionKind
from .plan import Plan, PlannedAction, resolve_conflicts

LOGGER = logging.getLogger(__name__)

#: Files Aegis leaves alone no matter what any rule says. These are either the
#: operating system's business or a sign that something else is mid-write.
ALWAYS_SKIP = (
    ".ds_store",
    "desktop.ini",
    "thumbs.db",
    ".localized",
)
SKIP_SUFFIXES = (".part", ".crdownload", ".download", ".tmp", ".partial", ".!ut")

#: Extension → category. Anything unlisted is "other" and, by default, untouched.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "Images": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".bmp", ".tiff", ".svg"),
    "Documents": (".pdf", ".docx", ".doc", ".odt", ".rtf", ".txt", ".md", ".pages", ".epub"),
    "Spreadsheets": (".xlsx", ".xls", ".csv", ".tsv", ".ods", ".numbers"),
    "Presentations": (".pptx", ".ppt", ".odp", ".key"),
    "Archives": (".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tgz"),
    "Audio": (".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".aiff"),
    "Video": (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"),
    "Installers": (".dmg", ".pkg", ".msi", ".exe", ".deb", ".rpm", ".appimage"),
    "Code": (".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".rb", ".sh"),
}

_EXTENSION_TO_CATEGORY = {
    ext: category for category, exts in CATEGORIES.items() for ext in exts
}

SCREENSHOT_PATTERNS = (
    "screenshot*",
    "screen shot*",
    "capture d*",           # French
    "bildschirmfoto*",      # German
    "captura de pantalla*",  # Spanish
    "cleanshot*",
    "*.screenshot.png",
)


@dataclass(frozen=True)
class FileFacts:
    """Everything a rule may look at. Metadata only — file contents are not read."""

    path: Path
    name: str
    suffix: str
    size: int
    modified: datetime
    age_days: float
    category: str

    @classmethod
    def of(cls, path: Path, *, now: datetime | None = None) -> FileFacts:
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        reference = now or datetime.now(timezone.utc)
        suffix = path.suffix.lower()
        return cls(
            path=path,
            name=path.name,
            suffix=suffix,
            size=stat.st_size,
            modified=modified,
            age_days=(reference - modified).total_seconds() / 86400,
            category=_EXTENSION_TO_CATEGORY.get(suffix, "Other"),
        )


@dataclass
class Rule:
    """One ordered rule: a match predicate and a destination.

    ``destination`` receives the facts and the folder being organised, and
    returns a full path. Rules are pure functions of metadata; a rule that needs
    to read a file's contents does not belong here.
    """

    name: str
    match: Callable[[FileFacts], bool]
    destination: Callable[[FileFacts, Path], Path]
    reason: str
    enabled: bool = True


def _is_screenshot(facts: FileFacts) -> bool:
    lowered = facts.name.lower()
    return facts.category == "Images" and any(
        fnmatch.fnmatch(lowered, pattern) for pattern in SCREENSHOT_PATTERNS
    )


def default_rules(*, min_age_days: float = 1.0, archive_after_days: float = 30.0) -> list[Rule]:
    """A conservative default ruleset.

    Nothing modified within ``min_age_days`` is touched, because a file that
    arrived five minutes ago is probably being worked on. Nothing is deleted, and
    everything stays inside the folder being organised.
    """

    def old_enough(facts: FileFacts) -> bool:
        return facts.age_days >= min_age_days

    return [
        Rule(
            name="Screenshots",
            match=lambda f: old_enough(f) and _is_screenshot(f),
            destination=lambda f, root: (
                root / "Screenshots" / f.modified.strftime("%Y-%m") / f.name
            ),
            reason="screenshot, filed by month",
        ),
        Rule(
            name="Installers",
            match=lambda f: old_enough(f) and f.category == "Installers",
            destination=lambda f, root: root / "Installers" / f.name,
            reason="installer package",
        ),
        Rule(
            name="Old files",
            match=lambda f: f.age_days >= archive_after_days and f.category != "Other",
            destination=lambda f, root: (
                root / "Archive" / f.modified.strftime("%Y-%m") / f.name
            ),
            reason=f"not modified in {int(archive_after_days)} days",
        ),
        Rule(
            name="By kind",
            match=lambda f: old_enough(f) and f.category != "Other",
            destination=lambda f, root: root / f.category / f.name,
            reason="sorted by file type",
        ),
    ]


class Organizer:
    """Builds plans. Never moves anything itself."""

    def __init__(self, rules: Sequence[Rule] | None = None) -> None:
        self.rules: list[Rule] = list(rules) if rules is not None else default_rules()

    def plan(
        self,
        directory: Path,
        *,
        recursive: bool = False,
        now: datetime | None = None,
        trigger: str = "manual",
        limit: int = 5000,
    ) -> Plan:
        directory = Path(directory).expanduser()
        plan = Plan(
            title=f"Organize {directory}",
            trigger=trigger,
        )
        if not directory.is_dir():
            plan.skipped.append((directory, "not a directory"))
            return plan

        # Destination subdirectories this ruleset creates. Files already inside
        # one have been organised before and must not be shuffled again — the
        # second run of a naive organiser is what buries a file three levels deep.
        managed = {"Screenshots", "Installers", "Archive", *CATEGORIES.keys()}

        entries = self._iter_entries(directory, recursive=recursive, limit=limit)
        for path in entries:
            relative_parts = set(path.relative_to(directory).parts[:-1])
            if relative_parts & managed:
                continue
            skip_reason = self._skip_reason(path)
            if skip_reason:
                plan.skipped.append((path, skip_reason))
                continue
            try:
                facts = FileFacts.of(path, now=now)
            except OSError as exc:
                plan.skipped.append((path, f"could not read: {exc}"))
                continue

            for rule in self.rules:
                if not rule.enabled or not rule.match(facts):
                    continue
                destination = rule.destination(facts, directory)
                if destination == facts.path:
                    break
                plan.actions.append(
                    PlannedAction(
                        kind=ActionKind.MOVE,
                        source=facts.path,
                        destination=destination,
                        rule=rule.name,
                        reason=rule.reason,
                        size=facts.size,
                    )
                )
                break
            else:
                plan.skipped.append((path, "no rule matched"))

        return resolve_conflicts(plan)

    def _iter_entries(self, directory: Path, *, recursive: bool, limit: int) -> list[Path]:
        found: list[Path] = []
        iterator: Iterable[Path] = directory.rglob("*") if recursive else directory.iterdir()
        for path in iterator:
            if len(found) >= limit:
                LOGGER.warning("Stopping at %s entries in %s", limit, directory)
                break
            if path.is_symlink() or not path.is_file():
                continue
            found.append(path)
        return sorted(found)

    @staticmethod
    def _skip_reason(path: Path) -> str | None:
        lowered = path.name.lower()
        if lowered in ALWAYS_SKIP:
            return "operating system file"
        if lowered.startswith("."):
            return "hidden file"
        if lowered.endswith(SKIP_SUFFIXES):
            return "looks like an in-progress download"
        return None


__all__ = [
    "Organizer",
    "Rule",
    "FileFacts",
    "default_rules",
    "CATEGORIES",
    "ALWAYS_SKIP",
]
