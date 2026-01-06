

import os
import sys
from pathlib import Path
from typing import Generator

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.config.schema import AppConfig, ClipboardVaultSettings, SchedulerSettings, WatcherSettings


@pytest.fixture(autouse=True)
def _set_env(tmp_path: Path) -> Generator[None, None, None]:
    data_home = tmp_path / "data"
    config_home = tmp_path / "config"
    os.environ["XDG_DATA_HOME"] = str(data_home)
    os.environ["XDG_CONFIG_HOME"] = str(config_home)
    os.environ["AEGIS_VAULT_PASSPHRASE"] = "test-passphrase"
    yield
    for key in ["XDG_DATA_HOME", "XDG_CONFIG_HOME", "AEGIS_VAULT_PASSPHRASE"]:
        os.environ.pop(key, None)


@pytest.fixture()
def app_config(tmp_path: Path) -> AppConfig:
    desktop = tmp_path / "Desktop"
    downloads = tmp_path / "Downloads"
    archive = tmp_path / "Archive"
    reports = tmp_path / "Reports"
    snippets = tmp_path / "Snippets"
    quarantine = tmp_path / "Quarantine"
    for path in [desktop, downloads, archive, reports, snippets, quarantine]:
        path.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        desktop_path=str(desktop),
        downloads_path=str(downloads),
        archive_root=str(archive),
        reports_root=str(reports),
        snippets_root=str(snippets),
        quarantine_root=str(quarantine),
        use_ollama=False,
        ollama_url="http://localhost:11434",
        clipboard_poll_interval=0.2,
        clipboard_vault=ClipboardVaultSettings(enabled=True, max_items=50),
        watchers=WatcherSettings(desktop=True, downloads=True),
        scheduler=SchedulerSettings(archive_days=7, zip_monthly=False),
        hotkey="alt+space",
    )

