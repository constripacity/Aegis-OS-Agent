from __future__ import annotations

import json
from pathlib import Path

from aegis.config.schema import AppConfig
from aegis.ui.first_run import FirstRunWizard, WizardAutomation


def test_first_run_automation(tmp_path: Path, app_config: AppConfig) -> None:
    config_path = tmp_path / "config.json"
    wizard = FirstRunWizard(app_config, config_path)
    automation = WizardAutomation(
        desktop_path=app_config.desktop_path,
        downloads_path=app_config.downloads_path,
        archive_root=app_config.archive_root,
        quarantine_root=app_config.quarantine_root,
        reports_root=app_config.reports_root,
        snippets_root=app_config.snippets_root,
        hotkey="ctrl+shift+space",
        tray_enabled=False,
        watch_desktop=True,
        watch_downloads=False,
        vault_enabled=True,
        vault_passphrase="unit-test-passphrase",
        use_ollama=True,
        ollama_url="http://localhost:11434",
    )
    config = wizard.run(automation)
    assert config_path.exists()
    assert config.tray_enabled is False
    assert config.watchers.desktop is True
    assert config.watchers.downloads is False
    assert config.clipboard_vault.enabled is True
    assert config.hotkey == "ctrl+shift+space"
    assert config.use_ollama is True


def test_first_run_should_run(tmp_path: Path, app_config: AppConfig) -> None:
    config_path = tmp_path / "config.json"
    # Missing file -> should run
    assert FirstRunWizard.should_run(config_path) is True
    # Write partial config missing keys
    config_path.write_text("{}", encoding="utf-8")
    assert FirstRunWizard.should_run(config_path) is True
    # Required keys present but empty should re-trigger wizard
    minimal = app_config.to_dict()
    minimal["desktop_path"] = ""
    config_path.write_text(json.dumps(minimal), encoding="utf-8")
    assert FirstRunWizard.should_run(config_path) is True
    # Valid config triggers skip
    config = app_config
    config_path.write_text(config.json(), encoding="utf-8")
    assert FirstRunWizard.should_run(config_path) is False
