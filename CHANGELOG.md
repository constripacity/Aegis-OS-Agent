# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2024-06-05
### Added
- Guard clause that reruns the first-run wizard only when the config is missing or incomplete, preventing repeated prompts for returning users.
- Automated test coverage for the wizard detection logic to ensure upgrades keep honoring existing installs.

### Changed
- Centralized configuration persistence through ``save_config`` so every entry point writes identical JSON payloads and logging.
- CLI startup now defers to the wizard helper, reducing merge conflicts between defaults and user settings across platforms.

## [0.1.3] - 2024-06-04
### Added
- Deterministic heuristics for summaries, URL cleaning, and smart renaming so offline mode matches the Ollama experience.
- Quarantine reports now use timestamp-safe filenames, include rule identifiers, and ship with an HTML template for quick review.
- First-run automation helpers and tests covering the onboarding wizard, quarantine reports, and filesystem/clipboard flows end-to-end.

### Changed
- Configuration paths are resolved via explicit helpers (`~/.config/aegis`, `%APPDATA%/Aegis`, `~/Library/Application Support/Aegis`) with a Tkinter wizard to populate them on first launch.
- Tray and hotkey managers live in dedicated modules with runtime toggles from the Settings UI.
- Release workflow builds PyInstaller bundles for Windows, macOS, and Linux on tag pushes and publishes SHA-256 sums automatically.

### Fixed
- Clipboard snippet exports redact obvious secrets and wrap content in fenced code blocks.
- Quarantine isolation avoids duplicate filenames and surfaces the generated report paths via notifications.
- Tests cover watcher quarantine flows, ensuring suspicious archives create JSON/HTML reports reliably across platforms.

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

