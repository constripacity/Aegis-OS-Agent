"""End-to-end executor behaviour, including the clipboard privacy path."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from aegis.core.bus import ClipboardEvent, FileSystemEvent
from tests.conftest import age_file, make_zip


@pytest.fixture()
def downloads(app_config) -> Path:
    root = Path(app_config.downloads_path)
    for name in ("report.pdf", "song.mp3"):
        path = root / name
        path.write_text(f"contents of {name}")
        age_file(path, 5)
    return root


# -- clipboard --------------------------------------------------------------
def test_a_bare_credential_is_never_written_anywhere(executor, notifications, app_config):
    executor.record_clipboard("ghp_" "1234567890abcdefghijklmnopqrstuvwxyzAB")
    assert executor.vault.count() == 0
    assert not list(Path(app_config.snippets_root).rglob("*.py"))
    assert any("Ignored" in message for message in notifications)


def test_code_containing_a_credential_is_saved_redacted(executor, app_config):
    """Regression: `heuristics.prepare_code_snippet` existed and was never
    called, so clipboard code went to disk verbatim, keys included."""
    executor.record_clipboard(
        "import requests\n"
        "API_KEY = 'sk-" "live-abcdefghijklmnopqrstuvwxyz012345'\n"
        "def fetch(url):\n"
        "    return requests.get(url)\n"
    )
    snippets = [p for p in Path(app_config.snippets_root).rglob("*") if p.is_file()]
    assert snippets, "expected a snippet to be written"
    content = snippets[0].read_text()
    assert "sk-live" not in content
    assert "[redacted]" in content
    assert "import requests" in content


def test_snippets_are_not_world_readable(executor, app_config):
    import stat

    executor.record_clipboard("def hello():\n    return 'world'\n" + "x" * 60)
    snippets = [p for p in Path(app_config.snippets_root).rglob("*") if p.is_file()]
    assert snippets
    assert not snippets[0].stat().st_mode & stat.S_IROTH


def test_tracking_parameters_are_stripped(executor, notifications):
    executor.record_clipboard("https://example.com/post?utm_source=x&id=7&fbclid=abc")
    latest = executor.clipboard_snapshot()
    assert "utm_source" not in latest
    assert "fbclid" not in latest
    assert "id=7" in latest


def test_clipboard_capture_from_a_watcher_thread(bus, executor):
    outcome = {}

    def worker():
        try:
            bus.publish(ClipboardEvent("copied on another thread"))
            outcome["ok"] = True
        except Exception as exc:  # pragma: no cover - the old bug
            outcome["error"] = repr(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert outcome.get("ok") is True, outcome


# -- planning through the router -------------------------------------------
def test_natural_language_preview_changes_nothing(router, downloads):
    plan = router.run("clean up my downloads please")
    assert plan.actions
    assert (downloads / "report.pdf").exists()


def test_apply_without_a_preview_is_refused(router, notifications):
    assert router.run("do it") is None
    assert any("no plan" in message.lower() for message in notifications)


def test_preview_then_apply_then_undo(router, downloads):
    router.run("organize downloads")
    report = router.run("do it")
    assert report is not None and report.ok
    assert not (downloads / "report.pdf").exists()

    undo = router.run("undo")
    assert undo is not None and undo.ok
    assert (downloads / "report.pdf").exists()


def test_unknown_command_does_nothing(router, downloads, notifications):
    before = sorted(p.name for p in downloads.iterdir())
    message = router.run("delete everything")
    assert "don't understand" in message
    assert sorted(p.name for p in downloads.iterdir()) == before


# -- quarantine -------------------------------------------------------------
def test_a_traversal_archive_is_quarantined_and_reversible(bus, executor, downloads, notifications):
    archive = downloads / "submission.zip"
    archive.write_bytes(make_zip([("../../autorun.sh", b"echo hi"), ("ok.txt", b"x")]))

    bus.publish(FileSystemEvent(str(archive), event_type="created", label="downloads"))
    assert not archive.exists()
    assert any("Quarantined" in message for message in notifications)

    stored = list(Path(executor.config.quarantine_root).glob("*.quarantined"))
    assert stored, "expected a neutralised copy in quarantine"

    batch = executor.journal.last_batch()
    report = executor.undo(batch.batch_id)
    assert report.ok
    assert archive.exists()


def test_an_ordinary_archive_is_left_alone(bus, executor, downloads):
    archive = downloads / "homework.zip"
    archive.write_bytes(make_zip([("essay.txt", b"my essay"), ("refs.txt", b"sources")]))
    bus.publish(FileSystemEvent(str(archive), event_type="created", label="downloads"))
    assert archive.exists()


def test_quarantined_files_lose_their_execute_bits(bus, executor, downloads):
    import stat

    archive = downloads / "bad.zip"
    archive.write_bytes(make_zip([("installer.exe", b"MZ")]))
    bus.publish(FileSystemEvent(str(archive), event_type="created", label="downloads"))
    stored = list(Path(executor.config.quarantine_root).glob("*.quarantined"))
    assert stored
    mode = stored[0].stat().st_mode
    assert not mode & stat.S_IXUSR
    assert not mode & stat.S_IROTH


def test_paused_watchers_do_not_quarantine(bus, executor, downloads):
    executor.pause_watchers(30)
    archive = downloads / "bad.zip"
    archive.write_bytes(make_zip([("../escape.sh", b"x")]))
    bus.publish(FileSystemEvent(str(archive), event_type="created", label="downloads"))
    assert archive.exists()
    executor.resume_watchers()


def test_archive_inspection_is_bounded(executor, downloads):
    """A hostile archive must not produce an unbounded indicator list."""
    archive = downloads / "flood.zip"
    archive.write_bytes(make_zip([(f"prog{i}.exe", b"MZ") for i in range(3000)]))
    indicators = executor.quarantine.inspect_archive(archive)
    assert 0 < len(indicators) <= 40


# -- surveys ----------------------------------------------------------------
def test_duplicates_are_grouped(executor, downloads):
    (downloads / "a.bin").write_bytes(b"Z" * 40_000)
    (downloads / "b.bin").write_bytes(b"Z" * 40_000)
    (downloads / "c.bin").write_bytes(b"Y" * 40_000)
    groups = executor.find_duplicates()
    names = [sorted(p.name for p in group) for group in groups]
    assert ["a.bin", "b.bin"] in names


def test_large_files_are_sorted_biggest_first(executor, downloads):
    (downloads / "big.bin").write_bytes(b"x" * 90_000)
    (downloads / "small.bin").write_bytes(b"x" * 10)
    rows = executor.large_files(limit=3)
    assert rows[0][0].name == "big.bin"


def test_unknown_folder_is_rejected(executor):
    with pytest.raises(ValueError, match="Unknown folder"):
        executor._folder_path("/etc")


def test_vault_status_is_reported_honestly(executor):
    assert "Clipboard vault" in executor.vault_status()
