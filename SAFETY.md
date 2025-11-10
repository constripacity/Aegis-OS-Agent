# Safety Guidelines

Aegis OS Agent is designed to help you organize files and clipboard data while keeping privacy and safety front and center. This document explains the guardrails in place and how to operate the software responsibly.

## Core Principles

1. **Offline by default** – The application never makes outbound network requests. Optional AI features talk only to `http://localhost:11434`, the default Ollama endpoint.
2. **No execution of untrusted inputs** – Organizing means moving, copying, renaming, or archiving files. The agent never executes, opens, or shells out to files discovered on your system.
3. **Privacy by design** – Clipboard history is opt-in, encrypted, and erasable. No telemetry is collected.

## Clipboard Vault

- Disabled until you opt in via CLI flag or Settings UI.
- When enabled, you are prompted for a passphrase. If an OS keyring is available, the derived key is stored securely; otherwise the passphrase is kept in memory only.
- Data is encrypted with AES-Fernet when the optional cryptography backend is installed; otherwise a lightweight XOR cipher fallback keeps entries unreadable to casual inspection.
- Use the **Wipe Vault Now** button in Settings or run `aegis palette` and issue the `wipe vault` command to purge history instantly.

## Filesystem Operations

- Desktop and Downloads folders are monitored for new or aging items. Only safe operations are executed:
  - Move to archive directories.
  - Copy into quarantine or snippet folders.
  - Rename using deterministic, collision-safe logic.
- Automatic deletion is explicitly disallowed. When a user requests deletion through the palette, the application moves the file to the OS trash.
- Suspicious archives (e.g., a ZIP containing executable files) are relocated to a read-only quarantine folder for manual inspection.

## Quarantine

- Disabled by default. Enable it in Settings if you want flagged archives isolated.
- Files moved to quarantine have their permissions restricted to read-only where supported.
- The agent never extracts or executes quarantined files.
- Every quarantine action emits JSON and HTML reports with file hashes in `~/Aegis/Reports/quarantine/`; see [docs/hardening.md](docs/hardening.md) for validation tips.
- Report filenames use UTC timestamps without punctuation so they are valid on Windows, macOS, and Linux alike.

## Optional AI Integrations

- Ollama support is behind the `--use-ollama` flag. When enabled, the agent sends prompts to the configured local endpoint. If the server is unreachable, heuristics take over automatically.
- No remote APIs are ever contacted.

## Notifications & Logging

- Notifications summarize actions (e.g., "12 files archived"). Sensitive clipboard content is never shown verbatim.
- Logs live under the user config directory and rotate automatically. You may delete them at any time. Activity reports land in
  `~/Aegis/Reports/` (configurable) with both JSON and HTML variants that avoid platform-restricted characters in their names.

## Best Practices

- Review archive and quarantine folders periodically.
- Keep your passphrase private and wipe the vault before sharing machines.
- Test new automation rules with non-critical files first.
- Keep Ollama models updated to receive local security improvements.

## Known Limitations

- Clipboard polling relies on OS clipboard APIs; if another program holds an exclusive lock, updates may be missed until released.
- Notification backends vary by OS and may fall back to console logging in headless environments.
- The heuristic classifier may mislabel very unusual files. Use the reports to audit and adjust rules.

If you discover a safety issue, please open an issue or email the maintainers with detailed reproduction steps.

