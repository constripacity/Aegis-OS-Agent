# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-09-02

A rewrite of the safety model, the clipboard vault and the intent parser.
Every claim in this entry was verified by running the thing it describes; the
one place that was not is named explicitly at the end.

### Security

- **The vault no longer has a fallback cipher.** v0.1.3 fell back to
  repeating-key XOR when `cryptography` was missing, logged
  `"Using lightweight XOR fallback"`, and described it in `SAFETY.md` as
  keeping entries "unreadable to casual inspection". The key was stretched with
  PBKDF2 first, which made the number impressive and the cipher no better.
  There is now one implementation — Fernet, with the key derived by
  PBKDF2-HMAC-SHA256 at 600,000 iterations — and if it cannot be loaded the
  vault raises `VaultUnavailable` and stays shut. No clipboard history is
  better than clipboard history behind something that reads as protection and
  is not.
- **The vault had never worked in the running app.** Its SQLite connection was
  created on one thread and used from the clipboard watcher's, so every real
  capture raised `ProgrammingError: SQLite objects created in a thread can only
  be used in that same thread`. It is now opened with `check_same_thread=False`
  behind an `RLock`, and there is a test that writes from another thread.
- **A destructive command can no longer be reached by a typo.** `open vault`
  scored 0.80 against `wipe vault` — one letter apart — so asking to *open* the
  clipboard history resolved to *deleting* it. The fuzzy pass now skips
  destructive commands entirely: they must be asked for in words the command
  table contains.
- **`aegis do` asks before anything destructive.** The palette confirmed;
  the CLI did not, so `aegis do "wipe vault"` deleted the history without a
  word. `--yes` skips the prompt for scripts.
- **The model endpoint is checked before any text is sent to it.**
  `ollama_url` went from the config file straight into `urlopen`, and the body
  of that request is the user's clipboard, so `file:///etc/passwd` and a
  hostname on someone else's machine were both supported configurations. Only
  `http`/`https` to a loopback address is allowed, unless
  `ollama_allow_remote` is set — which the error message spells out means the
  clipboard leaves the computer.
- **Credentials are excluded, not encrypted.** `aegis/core/secrets.py`
  classifies API keys, tokens, private keys, card numbers (Luhn-checked) and
  generated-looking passwords, and the watcher drops them before the vault sees
  them. Storing a secret encrypted still stores the secret.
- **Search no longer requires decrypting the table.** Each token gets a keyed
  HMAC blind index under a key derived separately from the encryption key, so
  `find` is a lookup rather than a full scan-and-decrypt.
- **The plaintext `preview` column is gone.** Migration drops it from existing
  vaults on first open; the vault file and its directory are created 0600/0700.
- **Nothing executes what it finds.** `open_path` is the only call that starts
  another process, it reveals directories and refuses files (handing a
  `.desktop` file to `xdg-open` means running it), and CI fails the build if
  `subprocess`, `eval`, `exec` or `shell=True` appears anywhere else in
  `aegis/`.

### Added

- **A real safety model: plan, authorise, execute, journal, undo.**
  `core/plan.py` refuses to execute a plan that was never authorised;
  `core/safety.py` checks containment after normalisation, so a symlink or `..`
  cannot leave the configured roots; `core/journal.py` is an append-only JSONL
  log with a hash per file, and `undo_batch` verifies each hash before restoring
  — a file you edited after the move is reported, not overwritten.
- `aegis plan` / `apply` / `undo` / `history` / `large` / `duplicates` /
  `status` / `do`, all working without a desktop session.
- `core/organizer.py`: rules that are idempotent — a second run over an
  already-tidied folder proposes nothing.
- `core/intents.py`: a fixed command table with phrase scoring and a fuzzy pass
  for typos. Free text cannot reach an executor; unknown input is refused.
- `examples/demo.py`: the whole model in a throwaway directory, run by CI.
- `SECURITY.md`, `docs/SAFETY.md`, `docs/ARCHITECTURE.md`.

### Changed

- The desktop UI is imported lazily. `aegis --help` used to crash on any
  machine without tkinter, because `main.py` imported the Tk widgets at module
  scope.
- `aegis run` and `aegis headless` now stay running. They called `start()`,
  which returns as soon as its daemon threads are spawned, then fell into
  `finally: app.stop()` — so the agent started every service and tore it down
  in the same breath. `Application.wait()` is the missing half, and quitting
  from the tray signals it rather than raising on the tray's own thread.
- `aegis large` prints readable sizes. It formatted every file as
  `{bytes / 1024**2:.1f} MB`, so a folder of documents came out as rows of
  `0.0 MB` — a listing sorted by a number it would not show you.
- `aegis do` no longer invents suggestions. "make me a sandwich" used to answer
  "Did you mean: summarize_clipboard, resume_watchers, pause_watchers?" — three
  commands whose only claim was sharing the letters in "me" and "a". A typo of
  a real phrase still resolves.
- `Summarizer`'s Ollama path had never worked: the request omitted
  `"stream": false`, so the daemon replied with a stream of JSON objects that
  the single-object parse could not read.
- `SchedulerService` proposes; it never acts. It was calling
  `archive_old_files`, a method that no longer existed.
- The filesystem watcher waits for a file to stop changing before reacting, so
  a 4 GB download is not organised mid-write.

### Removed

- `SAFETY.md` and `docs/hardening.md` from the repository root and docs. Both
  described the XOR fallback as a security feature; `docs/hardening.md` also
  claimed an `AEGIS_DISABLE_LOGGING` environment variable, a "stub updater" and
  read-only quarantine folders, none of which existed, and `SAFETY.md` said
  deleting a file "moves the file to the OS trash", which it does not.
  `docs/SAFETY.md` is now the single threat-model document, and `SECURITY.md`
  at the root points at it.
- `requirements-optional.txt` references from `CONTRIBUTING.md`,
  `docs/packaging.md` and `.github/workflows/release.yml` — the file does not
  exist, so the release workflow had never produced an artifact. Extras live in
  `pyproject.toml`.
- `examples/media/`, a folder whose only content was a README for a GIF that
  was gitignored and never recorded.

### Verified

Run on Linux, Python 3.11, at the commit this entry describes:

- `pytest -q` — 170 passed.
- `ruff check aegis tests examples scripts` — clean.
- `mypy aegis` — clean across 38 files, with no suppressed error codes. The
  four codes v0.1.3 disabled were re-enabled and the underlying types fixed.
- `python examples/demo.py` — completes end to end.
- The CLI was exercised by hand against a scratch folder: plan, apply, history,
  undo, large, duplicates, status, and `do` with both a known and an unknown
  phrase.

**Not verified:** anything that needs a desktop session. `aegis/ui/palette.py`,
`ui/settings.py`, `ui/first_run.py` and `ui/system.py` import tkinter, which was
not available on the machine this work was done on, so the palette window, the
tray icon and the global hotkey have not been run. `ui/palette_model.py` holds
the logic and is tested; the widgets are not. The Ollama integration is tested
against a stub, not a live daemon.

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

