"""Isolate suspicious archives, reversibly and within bounds.

Changes from the previous implementation:

* archive inspection is **bounded** — member count, nesting, declared
  uncompressed size and compression ratio all have ceilings, so a decompression
  bomb dropped in Downloads cannot exhaust the machine that is inspecting it;
* member names that escape the extraction folder (``../``, absolute paths,
  drive letters) are detected, which is the actual reason to be wary of an
  archive rather than merely noting it contains an ``.exe``;
* quarantined files are **renamed so the operating system has no handler for
  them**, and lose their execute bits, so a stored copy cannot be run by a
  double-click;
* every isolation is written to the shared :class:`~aegis.core.journal.ActionJournal`,
  so ``aegis undo`` reverses a quarantine exactly like it reverses a move.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import uuid
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from ..config.schema import AppConfig
from .journal import ActionJournal, ActionKind, hash_file, new_batch_id
from .safety import SafeRoots, UnsafePathError
from .utils import ensure_directory

LOGGER = logging.getLogger(__name__)

NEUTRALISED_SUFFIX = ".quarantined"

#: Bounds for archive inspection. Reading a hostile archive is itself a risk.
MAX_MEMBERS = 5_000
MAX_TOTAL_UNCOMPRESSED = 512 * 1024 * 1024
MAX_RATIO = 200.0

EXECUTABLE_SUFFIXES = {
    ".exe", ".com", ".scr", ".pif", ".cpl", ".msi", ".msp", ".dll", ".bat",
    ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".hta", ".jar",
    ".sh", ".command", ".app", ".apk", ".lnk", ".reg", ".scf",
}
LURE_SUFFIXES = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt", ".png", ".jpg", ".jpeg"}
BIDI_CHARS = set("‪‫‬‭‮⁦⁧⁨⁩")


@dataclass
class QuarantineRecord:
    original_path: str
    quarantined_path: str
    created_at: str
    reason: str
    source: str
    sha256: str
    indicators: list[str] = field(default_factory=list)
    batch_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _member_escapes(name: str) -> bool:
    normalised = name.replace("\\", "/")
    if normalised.startswith("/") or name.startswith("\\\\"):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", name):
        return True
    depth = 0
    for part in (p for p in normalised.split("/") if p not in ("", ".")):
        depth += -1 if part == ".." else 1
        if depth < 0:
            return True
    return False


class Quarantine:
    """Move suspicious files somewhere they cannot be opened by accident."""

    def __init__(
        self,
        config: AppConfig,
        journal: ActionJournal | None = None,
        roots: SafeRoots | None = None,
    ) -> None:
        self.config = config
        self.root = Path(config.quarantine_root).expanduser()
        ensure_directory(self.root)
        self._harden(self.root, 0o700)
        self.reports_root = Path(config.reports_root).expanduser() / "quarantine"
        ensure_directory(self.reports_root)
        self.journal = journal
        self.safe_roots = roots

    # -- inspection ----------------------------------------------------
    def inspect_archive(self, path: Path) -> list[str]:
        """Return human-readable indicators. Reads metadata only; never extracts."""
        path = Path(path)
        if not path.is_file():
            return []
        suffix = path.suffix.lower()
        if suffix in {".rar", ".7z"}:
            return [f"{suffix[1:].upper()} archives cannot be inspected without extra tools"]
        if suffix not in {".zip", ".jar", ".apk", ".docx", ".xlsx", ".pptx"}:
            return []

        indicators: list[str] = []
        try:
            with zipfile.ZipFile(path) as archive:
                try:
                    infolist = archive.infolist()
                except Exception as exc:  # pragma: no cover - hostile directory
                    return [f"archive index is malformed ({exc})"]

                if len(infolist) > MAX_MEMBERS:
                    indicators.append(
                        f"{len(infolist):,} entries (only the first {MAX_MEMBERS:,} inspected)"
                    )
                    infolist = infolist[:MAX_MEMBERS]

                total = 0
                for info in infolist:
                    name = info.filename
                    total += info.file_size

                    if _member_escapes(name):
                        indicators.append(f"entry unpacks outside the folder: {name}")
                        continue
                    if any(char in name for char in BIDI_CHARS):
                        indicators.append(f"entry name hides its real extension: {name!r}")
                        continue
                    if info.flag_bits & 0x1:
                        indicators.append(f"password-protected entry, cannot inspect: {name}")
                        continue

                    lowered = name.lower()
                    suffixes = Path(lowered).suffixes[-2:]
                    if (
                        len(suffixes) == 2
                        and suffixes[-1] in EXECUTABLE_SUFFIXES
                        and suffixes[-2] in LURE_SUFFIXES
                    ):
                        indicators.append(f"disguised with a double extension: {name}")
                    elif Path(lowered).suffix in EXECUTABLE_SUFFIXES:
                        indicators.append(f"contains a runnable file: {name}")

                    if info.compress_size > 512 and info.file_size > 8 * 1024 * 1024:
                        ratio = info.file_size / max(info.compress_size, 1)
                        if ratio > MAX_RATIO:
                            indicators.append(
                                f"entry expands {ratio:,.0f}x when unpacked: {name}"
                            )

                if total > MAX_TOTAL_UNCOMPRESSED:
                    indicators.append(
                        f"unpacks to about {total / (1024 * 1024):,.0f} MB in total"
                    )
        except zipfile.BadZipFile:
            return ["archive is damaged or is not really an archive"]
        except OSError as exc:  # pragma: no cover
            LOGGER.warning("Could not inspect %s: %s", path, exc)
            return [f"could not be read: {exc}"]

        # Cap the report itself; a hostile archive can produce thousands.
        return indicators[:40]

    # -- isolation -----------------------------------------------------
    def isolate(
        self,
        path: Path,
        reason: str,
        source: str,
        indicators: list[str] | None = None,
        *,
        batch_id: str | None = None,
    ) -> QuarantineRecord:
        path = Path(path)
        if self.safe_roots is not None:
            path = self.safe_roots.check_source(path)
        elif path.is_symlink():
            raise UnsafePathError(f"{path} is a symbolic link; refusing to quarantine it")

        digest = hash_file(path)
        size = path.stat().st_size
        destination = self._reserve_destination(path.name, digest)
        batch = batch_id or new_batch_id()

        LOGGER.info("Quarantining %s -> %s", path, destination.name)
        temp = self.root / f".incoming-{uuid.uuid4().hex}"
        try:
            try:
                os.replace(path, temp)
            except OSError:
                shutil.copy2(path, temp)
                if hash_file(temp) != digest:
                    temp.unlink(missing_ok=True)
                    raise RuntimeError(
                        f"copy of {path} into quarantine did not verify; original kept"
                    ) from None
                path.unlink()
            os.replace(temp, destination)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

        self._neutralise(destination)

        record = QuarantineRecord(
            original_path=str(path),
            quarantined_path=str(destination),
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            reason=reason,
            source=source,
            sha256=digest,
            indicators=list(indicators or []),
            batch_id=batch,
        )
        if self.journal is not None:
            self.journal.record(
                kind=ActionKind.QUARANTINE,
                source=path,
                destination=destination,
                sha256=digest,
                size=size,
                reason=f"quarantine: {reason}",
                trigger=source,
                batch_id=batch,
                extra={"indicators": record.indicators[:10]},
            )
        self._write_report(record)
        return record

    def _reserve_destination(self, name: str, digest: str) -> Path:
        """Collision-proof and inert.

        The content hash makes collisions impossible in practice, and the
        trailing suffix means the operating system has no handler for the file,
        so a stored copy cannot be launched by a double-click.
        """
        safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip() or "file"
        return self.root / f"{safe[:120]}.{digest[:12]}{NEUTRALISED_SUFFIX}"

    @staticmethod
    def _neutralise(path: Path) -> None:
        try:
            mode = path.stat().st_mode
            path.chmod(
                mode
                & ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH
                & ~stat.S_IWGRP & ~stat.S_IWOTH
                & ~stat.S_IRGRP & ~stat.S_IROTH
            )
        except OSError as exc:  # pragma: no cover - platform dependent
            LOGGER.debug("Could not restrict permissions on %s: %s", path, exc)

    @staticmethod
    def _harden(path: Path, mode: int) -> None:
        try:
            path.chmod(mode)
        except OSError as exc:  # pragma: no cover
            LOGGER.debug("Could not set permissions on %s: %s", path, exc)

    # -- reporting -----------------------------------------------------
    def _write_report(self, record: QuarantineRecord) -> None:
        import json

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        base = self.reports_root / f"quarantine-{stamp}-{record.sha256[:8]}"
        base.with_suffix(".json").write_text(
            json.dumps(record.to_dict(), indent=2), encoding="utf-8"
        )
        base.with_suffix(".html").write_text(self._render_html(record), encoding="utf-8")

    def _render_html(self, record: QuarantineRecord) -> str:
        if record.indicators:
            items = "".join(f"<li>{escape(i)}</li>" for i in record.indicators)
            indicators = f"<ul>{items}</ul>"
        else:
            indicators = "<p>None recorded.</p>"
        undo = (
            f"<code>aegis undo {escape(record.batch_id[:8])}</code>"
            if record.batch_id
            else "<em>not journalled</em>"
        )
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Aegis quarantine report</title>
<style>
 body{{font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
   margin:2rem auto;max-width:56rem;padding:0 1rem;color:#16191d}}
 h1{{color:#b45309;font-size:1.4rem}}
 table{{border-collapse:collapse;width:100%;margin:1rem 0}}
 th,td{{border:1px solid #e3e7ec;padding:.5rem .7rem;text-align:left;vertical-align:top}}
 th{{background:#fef3c7;width:12rem}}
 code{{font-family:ui-monospace,Menlo,monospace;font-size:.9em;word-break:break-all}}
 .note{{background:#f6f7f9;border-radius:8px;padding:.8rem 1rem;font-size:.92rem}}
</style></head><body>
<h1>File moved to quarantine</h1>
<p class="note"><strong>Nothing was deleted.</strong> The file was moved and renamed so
that opening it by accident is not possible. To put it back, run {undo}</p>
<table>
  <tr><th>Original location</th><td><code>{escape(record.original_path)}</code></td></tr>
  <tr><th>Now stored as</th><td><code>{escape(record.quarantined_path)}</code></td></tr>
  <tr><th>When</th><td>{escape(record.created_at)}</td></tr>
  <tr><th>Why</th><td>{escape(record.reason)}</td></tr>
  <tr><th>Noticed by</th><td>{escape(record.source)}</td></tr>
  <tr><th>SHA-256</th><td><code>{escape(record.sha256)}</code></td></tr>
  <tr><th>What was found</th><td>{indicators}</td></tr>
</table>
<p class="note">These are structural indicators from a static inspection, not an
antivirus verdict. Aegis never opened, extracted or ran this file.</p>
</body></html>
"""


__all__ = ["Quarantine", "QuarantineRecord", "NEUTRALISED_SUFFIX"]
