"""Shared fixtures.

Every test runs against a temporary home: ``XDG_DATA_HOME`` and
``XDG_CONFIG_HOME`` are redirected so the real clipboard vault and the real
config are never touched, and the vault passphrase comes from the environment
rather than the OS keyring.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.config.schema import (  # noqa: E402
    AppConfig,
    ClipboardVaultSettings,
    SchedulerSettings,
    WatcherSettings,
)
from aegis.core.bus import EventBus  # noqa: E402
from aegis.core.notifier import Notifier  # noqa: E402

MANAGED_DIRS = ("Desktop", "Downloads", "Archive", "Reports", "Snippets", "Quarantine")


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path) -> Generator[None, None, None]:
    previous = {
        key: os.environ.get(key)
        for key in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "AEGIS_VAULT_PASSPHRASE")
    }
    os.environ["XDG_DATA_HOME"] = str(tmp_path / "data")
    os.environ["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    os.environ["AEGIS_VAULT_PASSPHRASE"] = "test-passphrase"
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture()
def app_config(tmp_path: Path) -> AppConfig:
    paths = {name: tmp_path / name for name in MANAGED_DIRS}
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        desktop_path=str(paths["Desktop"]),
        downloads_path=str(paths["Downloads"]),
        archive_root=str(paths["Archive"]),
        reports_root=str(paths["Reports"]),
        snippets_root=str(paths["Snippets"]),
        quarantine_root=str(paths["Quarantine"]),
        use_ollama=False,
        clipboard_poll_interval=0.2,
        clipboard_vault=ClipboardVaultSettings(enabled=True, max_items=50),
        watchers=WatcherSettings(desktop=True, downloads=True),
        scheduler=SchedulerSettings(archive_days=30, zip_monthly=False),
        hotkey="alt+space",
    )


@pytest.fixture()
def bus() -> EventBus:
    return EventBus()


@pytest.fixture()
def notifications(bus: EventBus) -> list:
    """Collect every notification the system publishes."""
    collected: list = []
    bus.subscribe("notification", lambda event: collected.append(event.message))
    return collected


@pytest.fixture()
def executor(bus: EventBus, app_config: AppConfig, notifications: list):
    from aegis.core.actions import ActionExecutor

    instance = ActionExecutor(bus, Notifier(), app_config)
    yield instance
    instance.close()


@pytest.fixture()
def router(bus: EventBus, executor, app_config: AppConfig):
    from aegis.core.intents import IntentRouter

    return IntentRouter(bus, executor, app_config)


def make_zip(entries, compress=None) -> bytes:
    """Build an in-memory ZIP. Payloads are inert text."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress or zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buf.getvalue()


def age_file(path: Path, days: float) -> None:
    """Backdate a file's mtime so age-based rules can be tested."""
    import time

    when = time.time() - days * 86400
    os.utime(path, (when, when))
