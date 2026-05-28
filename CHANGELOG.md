# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-05-29
### Fixed
- Repaired extensive textual merge contamination that left the package unimportable and the CLI unable to start. All resolutions are HEAD-only and preserve the richer post-merge API.
  - `aegis/config/schema.py`: removed duplicate keyword arguments inside `AppConfig.from_dict` that produced `SyntaxError: keyword argument repeated`. Also removed an unreachable `return` after `config_dir()` and a duplicate `config_data` assignment.
  - `aegis/core/quarantine.py`: collapsed duplicate `import` lines, duplicate `class Quarantine:` headers, and two stacked `isolate()` methods. The new `isolate(path, reason, source, indicators)` returning `QuarantineRecord` is preserved.
  - `aegis/core/vault.py`: removed two stacked `_initialize()` methods (the old version was missing return values) and a duplicated empty-body `search()` guard that produced `IndentationError`.
  - `aegis/core/actions.py`: deduplicated two import blocks and triplicate `__init__` field assignments; collapsed a duplicate `record_clipboard` tail that re-stored raw `content` after the new processed/URL-cleaned path already ran.
  - `aegis/main.py`: removed duplicate `from .config.schema` import, a duplicate `settings_window` assignment that overwrote the new `_on_config_updated`-wired version with the legacy `IntentRouter` version, and a duplicate `load_config(config_path)` call that discarded the wizard's result.
  - `aegis/core/utils.py`: removed duplicate `__all__` that pruned the public surface to 3 names.
  - `aegis/ui/__init__.py`: removed duplicate `__all__` and updated to reference current modules.
  - `aegis/ui/settings.py`: rewritten cleanly — file had two `__init__` signatures, two `_render` bodies, and a 23-line block of module-level orphan code from the old `_render`.
  - `aegis/ui/palette.py`: rewritten cleanly — two stacked `_create_window` methods, mixed-together handler closures, and a duplicate `on_enter` + `root.mainloop()` at module scope.
  - `aegis/reports/exporter.py`: deduplicated imports, removed a duplicate `timestamp = datetime.utcnow().isoformat()` that produced filenames with `:` (invalid on Windows), and merged two `_render_html` implementations.
- `tests/test_conflict_markers.py` flagged itself due to literal conflict-marker strings in its `CONFLICT_MARKERS` tuple; switched to character repetition so the marker text doesn't appear in the source.

### Added
- `aegis.config.schema.is_config_complete(data)` — checks whether a config dict has every required path key (used by the first-run wizard's `should_run`).
- `aegis.config.schema.save_config(config, path)` — writes a config to disk and creates parent directories.
- `AppConfig.tray_enabled` field (default `True`) so the wizard can persist tray-icon preference.
- `aegis/__main__.py` so the CLI is reachable via `python -m aegis`.

### Removed
- Legacy `aegis/ui/wizard.py` (superseded by `aegis/ui/first_run.py` with `WizardAutomation`, `should_run`, vault-passphrase handling, and step-based Tk UI).
- Legacy `aegis/ui/hotkey.py` and `aegis/ui/tray.py` (superseded by `aegis/ui/system.py` which exports both `HotkeyManager` and `TrayController`).

### Verified
- `pytest`: 17/17 pass.
- `python -m aegis --help` enumerates `run`, `headless`, `palette`, `report`, `dump-config`.
- Headless `Application` constructs, subscribes filesystem/notification/clipboard listeners, and stops cleanly.

## [0.1.2] - 2024-06-03
### Added
- Automatic saving of code snippets from clipboard events into dated folders under the configured snippets directory.
- URL cleaner that strips common tracking parameters before summaries or vault storage.
- Clipboard vault pruning to enforce the configured history size.

### Fixed
- Activity reports now escape HTML content and list recent quarantine and snippet activity reliably across platforms.

## [0.1.1] - 2024-06-02
### Added
- First-run configuration wizard with keyring-backed vault passphrase storage and CLI fallback.
- Cross-platform tray icon and global hotkey manager (pystray/pynput optional dependencies).
- Quarantine reports with SHA-256 hashes and HTML/JSON output plus automated archive inspection heuristics.
- GitHub Actions release pipeline that builds platform bundles and uploads tagged release artifacts.
- Packaging and hardening documentation covering PyInstaller builds, signing guidance, and privacy controls.

### Changed
- Settings window now writes to the OS config directory and updates runtime hotkeys immediately.
- Command palette can be invoked repeatedly via the global hotkey without spawning new windows.
- Report exporter surfaces recent quarantine events in generated summaries.

### Fixed
- Clipboard vault exposes its storage location for integrations and closes cleanly on shutdown.
- First-run wizard correctly persists user-selected folders and skips undefined variables when saving.
- Activity report filenames are sanitized for Windows compatibility and vault shortcuts validate the destination before opening.

## [0.1.0] - 2024-06-01
### Added
- Initial release of Aegis OS Agent with clipboard monitoring, filesystem organization, command palette, and reporting.
- Optional Ollama integration with safe fallbacks.
- Encrypted clipboard vault with wipe controls.
- GitHub Actions CI, documentation, and packaging assets.

