# Aegis OS Agent

**Aegis** is an offline-first desktop copilot for Windows, macOS, and Linux. It keeps watch over your clipboard and cluttered folders, gives you a command palette that understands natural language, and helps you summarize, rename, classify, and archive files without sending a single byte to the cloud.

## Why Aegis?

* 🛡️ **Offline and private** – All intelligence runs locally. Ollama support is optional and limited to `http://localhost:11434`.
* 🗂️ **Desktop & Downloads organizer** – Keep important files close, archive the rest, never delete automatically.
* 📋 **Clipboard copilot** – Summaries, cleaned URLs with tracker stripping, smart code handling, and encrypted history on demand.
* ⚡ **Command palette** – Summon actions with `Alt+Space` (configurable) and let intents route to the right modules.
* 🔔 **Actionable notifications** – See what moved, summarized, or quarantined at a glance.
* 📊 **Reports** – Export JSON/HTML digests that explain what happened and how much time you saved.

## Feature Highlights

- Clipboard watcher with heuristics for text, URLs, code, and file paths.
- Automatically captures code snippets into dated folders inside `~/Aegis/Snippets/`.
- Optional encrypted clipboard vault (AES-Fernet when available, with a local XOR fallback) and keyring integration.
- Filesystem watcher for Desktop and Downloads using polling with safe move/rename helpers.
- AI-assisted intents, summaries, and renames via Ollama (if running) with deterministic fallbacks.
- Tkinter command palette, settings panels, and first-run wizard for cross-platform onboarding.
- Global hotkey and tray controls (pynput/pystray optional, degrade gracefully when unavailable).
- Nightly organizer jobs powered by a lightweight scheduler thread, configurable retention windows.
- Quarantine flow for suspicious archives, never executes or shells out to untrusted inputs.
- Deterministic heuristics for summaries, renames, and URL cleaning ensure the agent stays useful without Ollama.
- Modular Python package with typed APIs, logging, and event-driven architecture.

## Quickstart

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\\Scripts\\activate`
pip install -r requirements.txt
```

> **Tip:** `pyperclip` ships with the base requirements so clipboard monitoring works out of the box. If you prefer a
> different backend (e.g., `xclip` on Linux), install it before launching Aegis.

Optional extras (OCR, UI niceties):

```bash
pip install -r requirements-optional.txt
```

### 2. Run without Ollama

> 🎬 Want a visual walkthrough? Record a quick GIF using the steps in
> [examples/media/README.md](examples/media/README.md) and save it as `examples/media/demo.gif`.
> The GIF stays untracked (see `.gitignore`), so keep it local or host it externally when sharing.

```bash
aegis run --no-clipboard-vault
```

This starts the filesystem and clipboard watchers, tray menu, and command palette with pure heuristic intelligence. The first
launch presents a guided wizard so you can confirm watch folders and archive locations before anything moves automatically.

### 3. Run with Ollama

1. Install [Ollama](https://ollama.ai) locally and run `ollama serve`.
2. Pull a compatible model (e.g., `ollama pull llama3`).
3. Start Aegis with Ollama intents and summaries enabled:

```bash
aegis run --use-ollama --ollama-url=http://localhost:11434
```

### 4. Build a desktop bundle

```bash
python scripts/build_artifacts.py
```

This auto-detects your OS and produces a ready-to-share binary in `dist/release/`. Review [docs/packaging.md](docs/packaging.md) for signing hints, AppImage notes, and troubleshooting.

## Command Palette

Default hotkey: **Alt+Space** (editable in Settings).

Example commands:

- `summarize clipboard`
- `clean desktop`
- `list downloads older than 30d`
- `open vault`
- `pause watchers 30m`
- `rename last file intelligently`

## Configuration

Configuration is validated and loaded from the OS-specific config directory:

| OS      | Path                                               |
|---------|----------------------------------------------------|
| Linux   | `~/.config/aegis/config.json`                       |
| macOS   | `~/Library/Application Support/Aegis/config.json`  |
| Windows | `%APPDATA%\Aegis\config.json`                      |

On the first launch Aegis walks you through a Tkinter wizard to choose Desktop/Downloads paths, archive locations, hotkeys, and a clipboard vault passphrase. Defaults live in [`aegis/config/defaults.json`](aegis/config/defaults.json). Override via CLI flags or the Settings UI.

## Safety & Privacy

- Clipboard history is disabled by default and requires a passphrase.
- History is stored locally with AES-Fernet encryption when available (falling back to a local XOR cipher) and can be wiped instantly.
- Files are only moved, copied, or renamed – never executed.
- Optional quarantine folder for suspicious archives; contents are read-only.
- No telemetry, no network calls except the optional Ollama endpoint you configure.

See [SAFETY.md](SAFETY.md) and [docs/hardening.md](docs/hardening.md) for detailed guidance.

## Development

```bash
pip install -r requirements.txt
pip install -r requirements-optional.txt  # if you want OCR/vision extras
pre-commit run --all-files  # optional if you install hooks
pytest
```

### Coding Standards

- Python 3.10+
- Type hints everywhere (`from __future__ import annotations` recommended)
- Logging via the built-in `logging` module
- Lint with Ruff, type-check with mypy (configured in `setup.cfg`)

### Project Layout

```
aegis/
  core/           # event bus, intents, actions, AI helpers
  watchers/       # clipboard & filesystem monitors
  ui/             # Tkinter command palette & settings dialogs
  reports/        # activity export utilities
```

## Testing & CI

Continuous integration runs on GitHub Actions for Ubuntu, macOS, and Windows using Python 3.10 and 3.11. The workflow installs dependencies, runs Ruff, Mypy, and pytest. Tagged releases trigger the cross-platform packaging pipeline in [`.github/workflows/release.yml`](.github/workflows/release.yml), publishing PyInstaller bundles and SHA-256 sums automatically.

## FAQ

**Does it work offline?** Yes. If Ollama is not running, the heuristics kick in. No other network calls are ever made.

**Can I disable the clipboard vault?** Yes. Pass `--no-clipboard-vault` or toggle it in Settings.

**Does it delete files?** Never automatically. It moves them to Archive or Quarantine. Manual delete commands prompt for confirmation.

**What about screenshots or OCR?** Optional OCR support is behind a feature flag and requires Tesseract installed locally.

**Is there telemetry?** No. Logs stay on your machine.

## Known Limitations

- Tkinter UI styling depends on the OS theme; advanced effects require optional dependencies.
- Clipboard polling may miss extremely rapid updates (<250ms).
- Ollama latency depends on the model you select; fallback heuristics remain available.
- Some notification backends fall back to console logging when desktop APIs are unavailable.

## License

Aegis is released under the MIT License. See [LICENSE](LICENSE).

