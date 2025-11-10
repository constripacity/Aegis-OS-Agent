# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

