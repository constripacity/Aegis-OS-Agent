"""Filesystem boundary enforcement.

Aegis moves, renames and quarantines files on behalf of the user. Every one of
those operations takes a path that ultimately came from a config file, a
watcher, a command palette string, or a language model. This module is the
single choke point where those paths are checked before anything touches disk.

The rules:

* an operation may only touch paths inside an explicitly allowed root;
* symlinks are never followed out of a root, and are never moved as if they were
  their targets;
* a destination is never silently overwritten;
* ``..`` and absolute paths in untrusted input cannot escape, because resolution
  happens *before* the containment check, not after.
"""
from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


class UnsafePathError(RuntimeError):
    """A requested path is outside the allowed roots, or is otherwise unsafe."""


@dataclass(frozen=True)
class SafeRoots:
    """The set of directories Aegis is permitted to act inside."""

    roots: tuple[Path, ...]

    @classmethod
    def from_paths(cls, paths: Iterable[Path | str]) -> SafeRoots:
        resolved: list[Path] = []
        for path in paths:
            candidate = Path(path).expanduser()
            try:
                resolved.append(candidate.resolve())
            except OSError:  # pragma: no cover - unresolvable root
                continue
        return cls(tuple(dict.fromkeys(resolved)))

    def contains(self, path: Path) -> bool:
        try:
            resolved = Path(path).expanduser().resolve()
        except OSError:
            return False
        return any(_is_within(resolved, root) for root in self.roots)

    def check(self, path: Path, *, what: str = "path") -> Path:
        """Resolve *path* and confirm it is inside an allowed root."""
        try:
            resolved = Path(path).expanduser().resolve()
        except OSError as exc:
            raise UnsafePathError(f"{what} {path} could not be resolved: {exc}") from exc
        if not any(_is_within(resolved, root) for root in self.roots):
            allowed = ", ".join(str(r) for r in self.roots) or "(none configured)"
            raise UnsafePathError(
                f"{what} {resolved} is outside the folders Aegis is allowed to touch "
                f"({allowed})"
            )
        return resolved

    def check_source(self, path: Path) -> Path:
        """Check a file Aegis is about to read, move or rename."""
        candidate = Path(path).expanduser()
        if candidate.is_symlink():
            raise UnsafePathError(
                f"{candidate} is a symbolic link. Aegis does not move links, because "
                "moving one either breaks it or silently acts on a file somewhere else."
            )
        resolved = self.check(candidate, what="source")
        if not resolved.exists():
            raise UnsafePathError(f"source {resolved} does not exist")
        if not resolved.is_file():
            raise UnsafePathError(f"source {resolved} is not a regular file")
        return resolved

    def check_destination(self, path: Path, *, allow_existing: bool = False) -> Path:
        """Check a path Aegis is about to write to."""
        candidate = Path(path).expanduser()
        parent = candidate.parent
        # Resolve the parent (which must exist or be creatable inside a root)
        # rather than the leaf, which does not exist yet.
        probe = parent
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        self.check(probe, what="destination folder")
        anchor = self.check(probe, what="destination folder")
        resolved = (anchor / os.path.relpath(candidate, probe)).resolve()
        if not any(_is_within(resolved, root) for root in self.roots):
            raise UnsafePathError(f"destination {resolved} is outside the allowed folders")
        if resolved.exists() and not allow_existing:
            raise UnsafePathError(
                f"destination {resolved} already exists; Aegis never overwrites"
            )
        return resolved


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def unique_destination(destination: Path) -> Path:
    """Return *destination*, or the first free ``name-1``, ``name-2`` variant."""
    if not destination.exists():
        return destination
    stem, suffix, parent = destination.stem, destination.suffix, destination.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
        if counter > 10_000:  # pragma: no cover - pathological directory
            raise UnsafePathError(f"could not find a free name near {destination}")


def default_roots(config) -> SafeRoots:
    """The roots implied by a configuration."""
    return SafeRoots.from_paths(
        [
            config.desktop_path,
            config.downloads_path,
            config.archive_root,
            config.reports_root,
            config.snippets_root,
            config.quarantine_root,
        ]
    )


__all__ = [
    "SafeRoots",
    "UnsafePathError",
    "unique_destination",
    "default_roots",
]
