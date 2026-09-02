"""Clipboard vault.

Three of these tests are regressions for defects that were verified by reading
the raw database file: a plaintext preview column, a repeating-key XOR fallback
presented as encryption, and a SQLite connection unusable from the watcher
thread it was actually called from.
"""
from __future__ import annotations

import sqlite3
import stat
import threading

import pytest

from aegis.core import vault as vault_module
from aegis.core.vault import ClipboardVault
from tests._platform import requires_posix_perms


@pytest.fixture()
def vault(app_config):
    instance = ClipboardVault(app_config)
    yield instance
    instance.close()


def test_vault_starts_with_a_passphrase(vault):
    assert vault.enabled
    assert vault.unavailable_reason is None


def test_nothing_readable_is_written_to_disk(vault):
    """Regression: the old schema stored content[:120] in a plaintext column."""
    vault.store("my meeting notes about the quarterly review with Dana")
    raw = vault.db_path.read_bytes()
    for fragment in (b"meeting notes", b"quarterly review", b"Dana"):
        assert fragment not in raw, fragment


@requires_posix_perms
def test_database_is_not_world_readable(vault):
    vault.store("something")
    mode = vault.db_path.stat().st_mode
    assert not mode & stat.S_IROTH
    assert not mode & stat.S_IRGRP
    assert not vault.db_path.parent.stat().st_mode & stat.S_IROTH


def test_store_works_from_another_thread(vault):
    """Regression: every real capture raised sqlite3.ProgrammingError, because
    the connection was made on the main thread and used from the watcher."""
    outcome = {}

    def worker():
        try:
            outcome["stored"] = vault.store("copied from a watcher thread")
        except sqlite3.ProgrammingError as exc:  # pragma: no cover - the old bug
            outcome["error"] = str(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert outcome.get("stored") is True, outcome


def test_search_finds_entries_without_storing_plaintext(vault):
    vault.store("the postgres connection is flaky on staging")
    vault.store("remember to buy milk")
    results = vault.search("postgres")
    assert len(results) == 1
    assert "postgres" in results[0].content
    assert not vault.search("kubernetes")


def test_search_requires_every_token(vault):
    vault.store("alpha beta gamma")
    vault.store("alpha delta")
    assert len(vault.search("alpha")) == 2
    assert len(vault.search("alpha beta")) == 1


def test_blind_index_does_not_leak_the_query(vault):
    vault.store("mysupersecretproject planning notes")
    raw = vault.db_path.read_bytes()
    assert b"mysupersecretproject" not in raw


def test_credentials_are_refused_not_encrypted(vault):
    assert vault.store("ghp_" "1234567890abcdefghijklmnopqrstuvwxyzAB") is False
    assert vault.count() == 0
    assert b"ghp_" not in vault.db_path.read_bytes()


def test_pruning_keeps_only_max_items(app_config):
    app_config.clipboard_vault.max_items = 5
    instance = ClipboardVault(app_config)
    try:
        for index in range(25):
            instance.store(f"entry number {index}")
        assert instance.count() == 5
        newest = instance.recent(1)[0]
        assert "24" in newest.content
    finally:
        instance.close()


def test_wipe_removes_everything(vault):
    for index in range(5):
        vault.store(f"note {index}")
    assert vault.wipe() == 5
    assert vault.count() == 0


def test_without_cryptography_the_vault_refuses_to_run(app_config, monkeypatch):
    """Regression: it used to fall back to repeating-key XOR and log that as a
    'lightweight backend'."""
    monkeypatch.setattr(vault_module, "HAVE_CRYPTOGRAPHY", False)
    instance = ClipboardVault(app_config)
    try:
        assert instance.enabled is False
        assert "cryptography" in (instance.unavailable_reason or "")
        assert instance.store("secret data") is False
        assert not instance.db_path.exists() or instance.count() == 0
    finally:
        instance.close()


def test_without_a_passphrase_the_vault_refuses_to_run(app_config, monkeypatch):
    monkeypatch.delenv("AEGIS_VAULT_PASSPHRASE", raising=False)
    monkeypatch.setattr(ClipboardVault, "_load_passphrase", lambda self: None)
    instance = ClipboardVault(app_config)
    try:
        assert instance.enabled is False
        assert "passphrase" in (instance.unavailable_reason or "")
    finally:
        instance.close()


def test_a_legacy_plaintext_preview_column_is_removed(app_config):
    """An existing v1 vault must not keep carrying its plaintext column."""
    instance = ClipboardVault(app_config)
    db_path = instance.db_path
    instance.close()

    connection = sqlite3.connect(db_path)
    connection.execute("DROP TABLE entries")
    connection.execute(
        "CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT,"
        " entry_type TEXT, preview TEXT NOT NULL, payload BLOB NOT NULL)"
    )
    connection.execute(
        "INSERT INTO entries (created_at, entry_type, preview, payload)"
        " VALUES ('2026-01-01', 'text', 'hunter2', X'00')"
    )
    connection.commit()
    connection.close()

    migrated = ClipboardVault(app_config)
    try:
        columns = {
            row[1]
            for row in migrated._connection.execute("PRAGMA table_info(entries)").fetchall()
        }
        assert "preview" not in columns
        # Regression: the migration must also add the columns store() writes, or
        # an upgraded v0.1.x vault reports enabled yet raises OperationalError on
        # every store(). The columns and a working round-trip both matter.
        assert {"blind_index", "schema_ver"} <= columns
        assert migrated.store("a fresh secret after upgrade") is True
        assert any(
            "a fresh secret after upgrade" in entry.content
            for entry in migrated.search("fresh secret")
        )
    finally:
        migrated.close()


def test_disabled_in_config_means_no_database_activity(app_config):
    app_config.clipboard_vault.enabled = False
    instance = ClipboardVault(app_config)
    try:
        assert instance.enabled is False
        assert instance.store("anything") is False
        assert instance.search("anything") == []
    finally:
        instance.close()
