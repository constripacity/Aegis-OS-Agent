"""The command line, exercised through click's runner.

The first test here is the important one: the whole CLI used to fail at import
time on any machine without tkinter, because ``main.py`` imported the Tk UI at
module scope.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from aegis.main import cli
from tests.conftest import age_file


@pytest.fixture()
def workspace(app_config, tmp_path) -> Path:
    config_path = tmp_path / "config.json"
    config_path.write_text(app_config.json(indent=2), encoding="utf-8")
    downloads = Path(app_config.downloads_path)
    for name in ("report.pdf", "song.mp3", "notes.md"):
        path = downloads / name
        path.write_text(f"contents of {name}")
        age_file(path, 5)
    return config_path


@pytest.fixture()
def run(workspace):
    runner = CliRunner()

    def invoke(*args, **kwargs):
        return runner.invoke(cli, ["--config", str(workspace), *args], **kwargs)

    return invoke


def test_the_cli_imports_without_tkinter(monkeypatch):
    """Regression: `from .ui.palette import CommandPalette` at module scope made
    `aegis --help` fail on any machine with no GUI toolkit."""
    for name in list(sys.modules):
        if name.startswith("tkinter"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "tkinter", None)
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "plan" in result.output


def test_help_lists_the_safety_workflow():
    result = CliRunner().invoke(cli, ["--help"])
    for command in ("plan", "apply", "undo", "history", "status"):
        assert command in result.output


def test_status_reports_configuration(run):
    result = run("status")
    assert result.exit_code == 0
    assert "Action journal" in result.output
    assert "Clipboard vault" in result.output


def test_plan_changes_nothing(run, app_config):
    result = run("plan", "downloads")
    assert result.exit_code == 0
    assert "Nothing has been changed yet" in result.output
    assert (Path(app_config.downloads_path) / "report.pdf").exists()


def test_plan_json_is_machine_readable(run):
    result = run("plan", "downloads", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["actions"]


def test_apply_without_a_plan_fails_cleanly(run):
    result = run("apply", "--yes")
    assert result.exit_code == 1
    assert "no plan" in result.output.lower()


def test_apply_asks_before_changing_anything(run, app_config):
    run("plan", "downloads")
    result = run("apply", input="n\n")
    assert result.exit_code == 0
    assert "Nothing was changed" in result.output
    assert (Path(app_config.downloads_path) / "report.pdf").exists()


def test_full_plan_apply_history_undo_cycle(run, app_config):
    downloads = Path(app_config.downloads_path)
    before = {p.name: p.read_text() for p in downloads.iterdir() if p.is_file()}

    assert run("plan", "downloads").exit_code == 0
    applied = run("apply", "--yes")
    assert applied.exit_code == 0
    assert "Undo with" in applied.output
    assert not (downloads / "report.pdf").exists()

    history = run("history")
    assert history.exit_code == 0
    assert "reversible" in history.output

    undone = run("undo")
    assert undone.exit_code == 0
    after = {p.name: p.read_text() for p in downloads.iterdir() if p.is_file()}
    assert after == before


def test_undo_with_nothing_to_undo_fails_cleanly(run):
    result = run("undo")
    assert result.exit_code == 1


def test_do_understands_natural_language(run):
    result = run("do", "clean", "up", "my", "downloads")
    assert result.exit_code == 0
    assert "Nothing has been changed yet" in result.output


def test_do_refuses_what_it_does_not_understand(run, app_config):
    downloads = Path(app_config.downloads_path)
    before = sorted(p.name for p in downloads.iterdir())
    result = run("do", "delete", "everything")
    assert result.exit_code == 1
    assert "don't understand" in result.output
    assert sorted(p.name for p in downloads.iterdir()) == before


def test_duplicates_never_deletes(run, app_config):
    downloads = Path(app_config.downloads_path)
    (downloads / "x.bin").write_bytes(b"Z" * 5000)
    (downloads / "y.bin").write_bytes(b"Z" * 5000)
    result = run("duplicates")
    assert result.exit_code == 0
    assert "does not delete" in result.output
    assert (downloads / "x.bin").exists() and (downloads / "y.bin").exists()


def test_large_lists_biggest_first(run, app_config):
    (Path(app_config.downloads_path) / "huge.bin").write_bytes(b"x" * 200_000)
    result = run("large")
    assert result.exit_code == 0
    assert result.output.strip().splitlines()[0].endswith("huge.bin")


def test_dump_config_round_trips(run):
    result = run("dump-config")
    assert result.exit_code == 0
    assert json.loads(result.output)["desktop_path"]


def test_a_stale_plan_skips_files_that_moved(run, app_config):
    run("plan", "downloads")
    (Path(app_config.downloads_path) / "report.pdf").unlink()
    result = run("apply", "--yes")
    assert result.exit_code == 0
    assert "no longer there" in result.output or "Applied" in result.output


def test_large_shows_a_size_you_can_read(run, app_config):
    """`large` printed `{bytes / 1024**2:.1f} MB` for everything, so a folder of
    ordinary documents came out as rows of `0.0 MB` — a listing sorted by a
    number it would not show you."""
    downloads = Path(app_config.downloads_path)
    (downloads / "small.bin").write_bytes(b"x" * 4000)
    (downloads / "big.bin").write_bytes(b"x" * 3_000_000)
    result = run("large")
    assert result.exit_code == 0
    assert "2.9 MB  " in result.output.replace(" ", " ")
    assert "3.9 KB  " in result.output.replace(" ", " ")
    assert "0.0 MB" not in result.output


def test_duplicates_reports_what_deleting_them_would_recover(run, app_config):
    downloads = Path(app_config.downloads_path)
    for name in ("a.bin", "b.bin", "c.bin"):
        (downloads / name).write_bytes(b"Z" * 2_000_000)
    result = run("duplicates")
    assert result.exit_code == 0
    assert "3 copies of 1.9 MB (3.8 MB recoverable)" in result.output


def test_unknown_input_does_not_invent_suggestions(run):
    """`do "make me a sandwich"` used to answer "Did you mean:
    summarize_clipboard, resume_watchers, pause_watchers?" — three commands
    whose only claim was sharing the letters in "me" and "a"."""
    result = run("do", "make", "me", "a", "sandwich")
    assert result.exit_code == 1
    assert "don't understand" in result.output
    assert "Did you mean" not in result.output
    assert "aegis do help" in result.output


def test_a_typo_of_a_real_phrase_is_still_understood(run):
    """The suggestion floor must not cost us the typo tolerance that is the
    whole point of the fuzzy pass."""
    assert run("do", "shwo", "history").exit_code == 0
    assert run("do", "orgnize", "downloads").exit_code == 0


# -- the run loop ----------------------------------------------------------
def test_run_loop_waits_instead_of_exiting_immediately(app_config):
    """Regression, and the worst kind: `aegis run` called `app.start()`, which
    returns as soon as its daemon threads are spawned, then fell straight into
    `finally: app.stop()`. Every service started and was torn down in the same
    breath, so the command that is the product's whole point had never actually
    run. `wait()` is the missing half."""
    import threading
    import time

    from aegis.main import Application

    app = Application(app_config, use_ui=False)
    try:
        finished = threading.Event()

        def waiter() -> None:
            app.wait()
            finished.set()

        thread = threading.Thread(target=waiter, daemon=True)
        thread.start()

        # It must still be waiting: nothing has asked it to stop.
        assert not finished.wait(2.0), "wait() returned with no shutdown request"

        started = time.monotonic()
        app.request_shutdown()
        assert finished.wait(5.0), "wait() did not return after request_shutdown()"
        assert time.monotonic() - started < 5.0
        thread.join(timeout=5.0)
        assert not thread.is_alive()
    finally:
        app.stop()


def test_quit_from_the_tray_signals_rather_than_raising(app_config):
    """`_quit` runs on pystray's own thread. Raising SystemExit there would be
    swallowed by that thread and the main thread would wait forever."""
    from aegis.main import Application

    app = Application(app_config, use_ui=False)
    try:
        app._quit()
        app.wait()  # returns immediately; the event is already set
    finally:
        app.stop()


def test_do_asks_before_anything_destructive(run):
    """The palette asked; the CLI did not. A confirmation that exists in one
    entry point and not the other is not a confirmation."""
    declined = run("do", "wipe", "vault", input="n\n")
    assert declined.exit_code == 0
    assert "cannot be undone" in declined.output
    assert "Nothing was changed" in declined.output

    assert run("do", "wipe", "vault", "--yes").exit_code == 0


def test_do_will_not_wipe_the_vault_because_you_asked_to_open_it(run):
    result = run("do", "open", "vault")
    assert "wipe" not in result.output.lower()
