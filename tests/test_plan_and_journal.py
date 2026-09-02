"""The safety model: plan → preview → authorize → execute → journal → undo."""
from __future__ import annotations

from pathlib import Path

import pytest

from aegis.core.journal import ActionJournal, ActionKind, JournalError
from aegis.core.organizer import Organizer
from aegis.core.plan import Plan, PlannedAction, execute
from aegis.core.safety import SafeRoots, unique_destination
from tests.conftest import age_file


@pytest.fixture()
def downloads(app_config) -> Path:
    root = Path(app_config.downloads_path)
    for name in ("report.pdf", "song.mp3", "notes.md", "setup.dmg"):
        path = root / name
        path.write_text(f"contents of {name}")
        age_file(path, 5)
    old = root / "budget.xlsx"
    old.write_text("old spreadsheet")
    age_file(old, 90)
    fresh = root / "just-arrived.pdf"
    fresh.write_text("brand new")
    return root


@pytest.fixture()
def roots(app_config) -> SafeRoots:
    from aegis.core.safety import default_roots

    return default_roots(app_config)


@pytest.fixture()
def journal(app_config, roots) -> ActionJournal:
    return ActionJournal(Path(app_config.reports_root), roots)


# -- planning ---------------------------------------------------------------
def test_planning_changes_nothing(downloads):
    before = sorted(p.name for p in downloads.iterdir())
    plan = Organizer().plan(downloads)
    assert plan.actions
    assert sorted(p.name for p in downloads.iterdir()) == before


def test_recent_files_are_left_alone(downloads):
    plan = Organizer().plan(downloads)
    moved = {a.source.name for a in plan.actions}
    assert "just-arrived.pdf" not in moved


def test_hidden_and_partial_downloads_are_skipped(downloads):
    (downloads / ".DS_Store").write_text("junk")
    (downloads / "big.iso.crdownload").write_text("half a file")
    age_file(downloads / ".DS_Store", 5)
    age_file(downloads / "big.iso.crdownload", 5)
    plan = Organizer().plan(downloads)
    moved = {a.source.name for a in plan.actions}
    assert ".DS_Store" not in moved
    assert "big.iso.crdownload" not in moved
    reasons = {Path(p).name: why for p, why in plan.skipped}
    assert "in-progress" in reasons["big.iso.crdownload"]


def test_render_states_that_nothing_has_happened(downloads):
    rendered = Organizer().plan(downloads).render()
    assert "Nothing has been changed yet" in rendered
    assert "report.pdf" in rendered


def test_plan_is_serialisable(downloads):
    data = Organizer().plan(downloads).to_dict()
    assert data["actions"]
    assert {"kind", "source", "destination", "rule", "reason"} <= set(data["actions"][0])


# -- authorisation ----------------------------------------------------------
def test_unauthorised_plans_are_refused(downloads, journal, roots):
    plan = Organizer().plan(downloads)
    with pytest.raises(PermissionError, match="not been authorised"):
        execute(plan, journal, roots)
    assert (downloads / "report.pdf").exists()


def test_dry_run_execute_moves_nothing(downloads, journal, roots):
    plan = Organizer().plan(downloads)
    report = execute(plan.authorize(), journal, roots, dry_run=True)
    assert report.completed
    assert (downloads / "report.pdf").exists()
    assert not journal.records()


# -- execution and undo -----------------------------------------------------
def test_execute_then_undo_restores_everything(downloads, journal, roots):
    before = {p.name: p.read_text() for p in downloads.iterdir() if p.is_file()}
    plan = Organizer().plan(downloads)
    report = execute(plan.authorize(), journal, roots)
    assert report.ok
    assert not (downloads / "report.pdf").exists()

    undo = journal.undo_batch(report.batch_id)
    assert undo.ok
    after = {p.name: p.read_text() for p in downloads.iterdir() if p.is_file()}
    assert after == before


def test_every_change_is_journalled(downloads, journal, roots):
    plan = Organizer().plan(downloads)
    report = execute(plan.authorize(), journal, roots)
    records = journal.records()
    assert len(records) == len(report.completed)
    for record in records:
        assert record.sha256 and record.source and record.destination
        assert record.reason and record.trigger
        assert record.is_reversible


def test_journal_is_plain_jsonl(downloads, journal, roots):
    import json

    execute(Organizer().plan(downloads).authorize(), journal, roots)
    lines = journal.path.read_text().strip().splitlines()
    assert lines
    for line in lines:
        json.loads(line)


def test_undo_refuses_when_the_file_changed(downloads, journal, roots):
    plan = Organizer().plan(downloads)
    report = execute(plan.authorize(), journal, roots)
    moved = Path(journal.records()[0].destination)
    moved.write_text("someone edited this after it moved")
    undo = journal.undo_batch(report.batch_id)
    assert any("has changed" in reason for _, reason in undo.skipped)
    assert moved.exists()


def test_undo_with_force_overrides_the_hash_check(downloads, journal, roots):
    plan = Organizer().plan(downloads)
    report = execute(plan.authorize(), journal, roots)
    moved = Path(journal.records()[0].destination)
    moved.write_text("edited")
    undo = journal.undo_batch(report.batch_id, force=True)
    assert undo.restored


def test_undoing_twice_is_refused(downloads, journal, roots):
    report = execute(Organizer().plan(downloads).authorize(), journal, roots)
    journal.undo_batch(report.batch_id)
    with pytest.raises(JournalError, match="no reversible actions"):
        journal.undo_batch(report.batch_id)


def test_batches_are_grouped_and_newest_first(downloads, journal, roots):
    execute(Organizer().plan(downloads).authorize(), journal, roots)
    (downloads / "second.mp3").write_text("later")
    age_file(downloads / "second.mp3", 5)
    execute(Organizer().plan(downloads).authorize(), journal, roots)
    batches = journal.batches()
    assert len(batches) == 2
    assert batches[0].timestamp >= batches[1].timestamp
    assert journal.last_batch() is not None


def test_organising_twice_does_not_reshuffle(downloads, journal, roots):
    execute(Organizer().plan(downloads).authorize(), journal, roots)
    assert len(Organizer().plan(downloads)) == 0


def test_name_collisions_get_a_free_destination(app_config, journal, roots):
    root = Path(app_config.downloads_path)
    (root / "Documents").mkdir()
    (root / "Documents" / "notes.md").write_text("already here")
    incoming = root / "notes.md"
    incoming.write_text("newly arrived")
    age_file(incoming, 5)

    plan = Organizer().plan(root)
    action = next(a for a in plan.actions if a.source.name == "notes.md")
    assert action.destination.name != "notes.md"
    assert action.warnings

    execute(plan.authorize(), journal, roots)
    assert (root / "Documents" / "notes.md").read_text() == "already here"


# -- boundaries -------------------------------------------------------------
def test_execution_refuses_a_source_outside_the_allowed_roots(tmp_path, journal, roots):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    victim = outside / "important.txt"
    victim.write_text("do not touch")

    plan = Plan(title="hostile")
    plan.actions.append(
        PlannedAction(
            kind=ActionKind.MOVE,
            source=victim,
            destination=Path(str(roots.roots[0])) / "stolen.txt",
            rule="hostile",
            reason="should never run",
        )
    )
    report = execute(plan.authorize(), journal, roots)
    assert not report.ok
    assert victim.exists()
    assert "outside" in report.failed[0][1]


def test_execution_refuses_a_destination_outside_the_allowed_roots(
    downloads, journal, roots, tmp_path
):
    plan = Plan(title="hostile")
    plan.actions.append(
        PlannedAction(
            kind=ActionKind.MOVE,
            source=downloads / "report.pdf",
            destination=tmp_path / "escaped" / "report.pdf",
            rule="hostile",
            reason="should never run",
        )
    )
    report = execute(plan.authorize(), journal, roots)
    assert not report.ok
    assert (downloads / "report.pdf").exists()


def test_symlinks_are_never_moved(downloads, journal, roots):
    target = downloads / "report.pdf"
    link = downloads / "shortcut.pdf"
    link.symlink_to(target)
    plan = Plan(title="link")
    plan.actions.append(
        PlannedAction(
            kind=ActionKind.MOVE,
            source=link,
            destination=downloads / "Documents" / "shortcut.pdf",
            rule="link",
            reason="",
        )
    )
    report = execute(plan.authorize(), journal, roots)
    assert not report.ok
    assert "symbolic link" in report.failed[0][1]


def test_unique_destination_never_collides(tmp_path):
    original = tmp_path / "file.txt"
    original.write_text("a")
    first = unique_destination(original)
    assert first.name == "file-1.txt"
    first.write_text("b")
    assert unique_destination(original).name == "file-2.txt"
