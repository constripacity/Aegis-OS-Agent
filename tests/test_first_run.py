from __future__ import annotations

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
