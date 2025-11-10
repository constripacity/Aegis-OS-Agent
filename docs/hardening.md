# Hardening & Privacy Reference

Aegis is designed for offline-first operation with a focus on user control. This guide summarises the defensive measures already in place and the knobs available to tighten them further.

## Clipboard vault

- Encryption uses AES-Fernet when the `cryptography` package is installed; otherwise a per-user XOR cipher derived from PBKDF2 (SHA-256, 390k iterations).
- The vault database lives in the OS-specific data directory:
  - Linux: `${XDG_DATA_HOME:-~/.local/share}/Aegis/vault.sqlite`
  - macOS: `~/Library/Application Support/Aegis/vault.sqlite`
  - Windows: `%APPDATA%/Aegis/vault.sqlite`
- Provide the passphrase through the first-run wizard, the OS keyring, or the `AEGIS_VAULT_PASSPHRASE` environment variable.
- Wipe instantly from the command palette (`wipe vault`) or via CLI `aegis report --html` to verify deletion.

## Quarantine process

- Archives flagged as suspicious (contains executables/scripts) are moved to `~/Aegis/Quarantine` (configurable).
- Files are never executed or extracted. The quarantine report records:
  - Timestamp
  - Original path
  - SHA-256 hash
  - Detection reason and source watcher
- Reports are produced as JSON + HTML at `~/Aegis/Reports/quarantine/`.
- Quarantine folders are set to read-only where the OS permits.

## Logging & telemetry

- No network calls except optional Ollama inference to `http://localhost:11434` when explicitly enabled.
- Logs remain local under `~/Aegis/Reports/logs/` (create the directory to enable file logging). Delete the folder to purge history.
- Set `AEGIS_DISABLE_LOGGING=1` to silence disk logging entirely.

## Configuration hygiene

- Settings live in the OS config path (`~/.config/Aegis/config.json` on Linux, `%APPDATA%/Aegis/config.json` on Windows, `~/Library/Application Support/Aegis/config.json` on macOS).
- The first-run wizard validates folder selections and refuses to overwrite non-empty directories without confirmation.
- Rotate archive/quarantine directories regularly; the scheduler exposes the `--archive-days` flag, and settings UI mirrors it.

## Offline contract

- Codebase contains no HTTP clients other than the Ollama optional integration and a stub updater disabled by default.
- Any attempt to reach non-local addresses raises a warning in the logs (`WARNING` level) and aborts.

## Recommended OS-level policies

- Run the agent as a regular user; never grant admin rights.
- Enable full-disk encryption (BitLocker/FileVault/LUKS) to protect archive/vault data at rest.
- Keep Python runtime patched; the CI matrix (Windows/macOS/Linux on Python 3.10/3.11) helps surface regressions early.
