#!/usr/bin/env python3
"""A self-contained demo of the whole safety model, in a throwaway folder.

    python examples/demo.py

Creates a realistic messy Downloads folder in a temporary directory, then walks
through PLAN → APPLY → HISTORY → UNDO and prints what happens at each step.
Your real files are never touched: everything happens under a directory that is
deleted when the script exits, unless you pass ``--keep``.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aegis.config.schema import AppConfig, ClipboardVaultSettings  # noqa: E402
from aegis.core.actions import ActionExecutor  # noqa: E402
from aegis.core.bus import EventBus, FileSystemEvent  # noqa: E402
from aegis.core.intents import IntentRouter  # noqa: E402
from aegis.core.notifier import Notifier  # noqa: E402

DAY = 86400

FILES = {
    "Screenshot 2026-06-14 at 09.22.png": 12,
    "quarterly-report.pdf": 9,
    "invoice-2026-03.pdf": 95,
    "album.mp3": 20,
    "Setup-1.4.2.dmg": 30,
    "meeting-notes.md": 4,
    "data-export.csv": 60,
    "just-downloaded.zip": 0,
    "half-a-movie.mkv.crdownload": 2,
    ".DS_Store": 40,
}


def banner(text: str) -> None:
    print(f"\n\033[1m{'─' * 4} {text} {'─' * max(0, 68 - len(text))}\033[0m")


def build_workspace(root: Path) -> Path:
    downloads = root / "Downloads"
    for name in ("Desktop", "Downloads", "Archive", "Reports", "Snippets", "Quarantine"):
        (root / name).mkdir(parents=True, exist_ok=True)
    for name, age_days in FILES.items():
        path = downloads / name
        path.write_text(f"pretend contents of {name}\n" * 20)
        when = time.time() - age_days * DAY
        os.utime(path, (when, when))

    suspicious = downloads / "assignment-submission.zip"
    with zipfile.ZipFile(suspicious, "w") as archive:
        archive.writestr("essay.txt", b"a perfectly ordinary essay")
        archive.writestr("../../autorun.sh", b'echo "this would land outside the folder"')
    when = time.time() - 3 * DAY
    os.utime(suspicious, (when, when))
    return downloads


def main() -> int:
    # The banners use box-drawing/arrow characters; make them survive a legacy
    # Windows console (cp1252) instead of raising UnicodeEncodeError mid-demo.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep", action="store_true", help="do not delete the demo folder")
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="aegis-demo-"))
    os.environ["XDG_DATA_HOME"] = str(root / ".data")
    os.environ["AEGIS_VAULT_PASSPHRASE"] = "demo-passphrase"

    downloads = build_workspace(root)
    config = AppConfig(
        desktop_path=str(root / "Desktop"),
        downloads_path=str(downloads),
        archive_root=str(root / "Archive"),
        reports_root=str(root / "Reports"),
        snippets_root=str(root / "Snippets"),
        quarantine_root=str(root / "Quarantine"),
        clipboard_vault=ClipboardVaultSettings(enabled=True, max_items=50),
    )

    messages: list[str] = []
    bus = EventBus()
    bus.subscribe("notification", lambda event: messages.append(event.message))
    executor = ActionExecutor(bus, Notifier(), config)
    router = IntentRouter(bus, executor, config)

    try:
        print(f"Demo workspace: {root}")
        banner("A messy Downloads folder")
        for path in sorted(downloads.iterdir()):
            age = (time.time() - path.stat().st_mtime) / DAY
            print(f"   {path.name:<42} {age:5.0f} days old")

        banner('1. "clean up my downloads"  —  a plan, nothing else')
        plan = router.run("clean up my downloads")
        print(plan.render(limit=4))
        print(f"\n   Files still where they were: {len(list(downloads.iterdir()))}")

        banner('2. "do it"  —  applied and journalled')
        report = router.run("do it")
        print("  ", report.describe().replace("\n", "\n   "))
        print("\n   Downloads now looks like:")
        for path in sorted(downloads.rglob("*")):
            if path.is_file():
                print(f"      {path.relative_to(downloads)}")

        banner('3. "show me the history"')
        for line in router.run("show me the history"):
            print("  ", line)

        banner('4. "undo"  —  everything back exactly where it was')
        print("  ", router.run("undo").describe().replace("\n", "\n   "))

        banner("5. A suspicious archive arrives")
        suspicious = downloads / "assignment-submission.zip"
        messages.clear()
        bus.publish(FileSystemEvent(str(suspicious), event_type="created", label="downloads"))
        for message in messages:
            print("  ", message)
        stored = list(Path(config.quarantine_root).glob("*.quarantined"))
        print(f"\n   In quarantine: {[p.name for p in stored]}")
        print("   Renamed so a double-click does nothing, and the execute bit is cleared.")
        batch = executor.journal.last_batch()
        print("  ", executor.undo(batch.batch_id).describe().replace("\n", "\n   "))

        banner("6. The clipboard never stores a credential")
        for content, label in [
            ("ghp_" "1234567890abcdefghijklmnopqrstuvwxyzAB", "a GitHub token"),
            ("the release is on Thursday, tell Dana", "an ordinary note"),
        ]:
            messages.clear()
            executor.record_clipboard(content)
            outcome = messages[-1] if messages else "stored"
            print(f"   {label:<20} → {outcome}")
        print(f"   Entries in the encrypted vault: {executor.vault.count()}")

        banner('7. "delete everything"  —  refused, not guessed at')
        print("  ", router.run("delete everything"))

        print(f"\n\033[1mNothing outside {root} was touched.\033[0m")
        return 0
    finally:
        executor.close()
        if args.keep:
            print(f"Demo folder kept at {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
