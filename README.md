<h1 align="center">Aegis</h1>

<p align="center">
  <strong>A local-first agent that tidies your files — and shows you exactly what it will do before it does it.</strong>
</p>

<p align="center">
  Plan → apply → undo · every change journalled · nothing leaves your machine
</p>

<p align="center">
  <a href="#60-second-tour">60-second tour</a> ·
  <a href="#the-safety-model">Safety model</a> ·
  <a href="#the-clipboard-vault">Clipboard</a> ·
  <a href="#commands">Commands</a> ·
  <a href="docs/SAFETY.md">Threat model</a>
</p>

---

```console
$ aegis plan downloads

Organize ~/Downloads
====================

Screenshots  (1)
      move  Screenshot 2026-06-14 at 09.22.png
            → ~/Downloads/Screenshots/2026-06/Screenshot 2026-06-14 at 09.22.png
Installers  (1)
      move  Setup-1.4.2.dmg  →  ~/Downloads/Installers/Setup-1.4.2.dmg
Old files  (2)
      move  invoice-2026-03.pdf  →  ~/Downloads/Archive/2026-05/invoice-2026-03.pdf
      move  data-export.csv      →  ~/Downloads/Archive/2026-07/data-export.csv
By kind  (4)
      move  quarterly-report.pdf  →  ~/Downloads/Documents/quarterly-report.pdf
      …

Left alone (3):
    .DS_Store: operating system file
    half-a-movie.mkv.crdownload: looks like an in-progress download
    just-downloaded.zip: no rule matched

8 change(s), 412.7 MB. Nothing has been changed yet.

Apply it with:  aegis apply
```

```console
$ aegis apply
Apply these 8 change(s)? [y/N]: y
Applied 8 change(s). Batch d336c777.
  Undo with:  aegis undo d336c777

$ aegis undo
Undid 8 change(s) from batch d336c777.
  ✓ Screenshot 2026-06-14 at 09.22.png → ~/Downloads/Screenshot 2026-06-14 at 09.22.png
  ✓ Setup-1.4.2.dmg → ~/Downloads/Setup-1.4.2.dmg
  …
```

> **To record the demo GIF:** `python examples/demo.py --keep` prints exactly the
> sequence above in a throwaway folder. Capture it and drop the result at
> `docs/demo.gif`.

## Why this exists

`organize` (3.1k ★) is the reference file-automation tool and has had no release
since November 2024. `llama-fs` (5.7k ★) and `Local-File-Organizer` (3.2k ★) are
~9k stars of demonstrated demand for AI file organisation, and both are
abandoned — one never shipped a release at all. The only actively maintained
Hazel alternative is macOS-only.

None of them can show you a diff and then take it back.

| | `organize` | `llama-fs` | Hazel | **Aegis** |
| --- | --- | --- | --- | --- |
| Dry run before acting | `organize sim` | review step | — | **`aegis plan`** |
| **Undo after acting** | — | — | — | **`aegis undo`** |
| Change journal | — | — | — | **JSONL, greppable** |
| Cross-platform | ✓ | ✓ | macOS only | ✓ |
| Maintained | last release Nov 2024 | no releases ever | commercial | ✓ |

## 60-second tour

```bash
git clone https://github.com/constripacity/Aegis-OS-Agent
cd Aegis-OS-Agent
pip install -e .

python examples/demo.py     # the whole thing, in a throwaway folder
```

The demo builds a realistic messy Downloads folder in `/tmp`, then walks through
plan → apply → history → undo, quarantines a booby-trapped archive and undoes
that too, and shows the clipboard vault refusing to store a token. **Your real
files are never touched** — the folder is deleted when it exits.

Then, for real:

```bash
aegis status                 # what is configured, and is the vault actually working
aegis plan downloads         # show me what you would do
aegis apply                  # do it, after I confirm
aegis undo                   # actually, put it back
```

## The safety model

Every filesystem change goes through the same six steps. There is no path
around them.

```
  PLAN ──▶ PREVIEW ──▶ AUTHORIZE ──▶ EXECUTE ──▶ JOURNAL ──▶ UNDO
   │          │            │            │           │          │
 reads    you see a   you confirm   moves are    appended    reversed in
metadata   full diff  (or --yes)     verified    to JSONL   reverse order
   │          │            │            │           │          │
 no I/O    no I/O      no I/O       hash before   fsync'd    hash checked
                                    and after              before restoring
```

- **`execute()` refuses a plan that was never authorised.** Not a convention — a
  `PermissionError`.
- **Every action is re-validated at execution time.** A plan is a snapshot; the
  filesystem may have moved on, and acting on a stale plan is how an automated
  tool destroys something.
- **Nothing is ever deleted.** Not by organising, not by quarantine, not by the
  scheduler. `aegis duplicates` finds copies and tells you about them; removing
  them is your job.
- **Nothing is overwritten.** A colliding destination gets a free name and the
  plan says so.
- **Undo verifies before it acts.** If you edited a file after Aegis moved it,
  undo refuses that file and tells you, rather than clobbering your edit.
- **Every path is checked against an allowlist** before anything touches disk,
  and symlinks are never moved. See [`aegis/core/safety.py`](aegis/core/safety.py).

The journal is plain JSONL next to your reports folder:

```console
$ jq -r '[.timestamp, .kind, .source] | @tsv' ~/Aegis/Reports/actions.jsonl | tail -3
2026-09-02T01:33:26+00:00  move  /Users/you/Downloads/album.mp3
2026-09-02T01:33:26+00:00  move  /Users/you/Downloads/invoice-2026-03.pdf
2026-09-02T01:33:26+00:00  move  /Users/you/Downloads/Setup-1.4.2.dmg
```

You do not need Aegis to read it, and you do not need Aegis to reverse it.

## The clipboard vault

Optional, off by default, and built around one idea: **excluding a credential is
a stronger promise than encrypting it.**

- Content that looks like a credential — API keys, tokens, private keys,
  connection strings with passwords, card numbers that pass Luhn, generated
  passwords — is **not stored at all**. It never reaches the database.
- Everything else is encrypted with AES via Fernet, keyed by PBKDF2-HMAC-SHA256
  at 600,000 iterations from a passphrase in your OS keyring.
- Search works over encrypted rows using a keyed **blind index**: each token is
  HMAC'd, so equality search works and the index cannot be reversed into your
  clipboard.
- **There is no fallback cipher.** Without `cryptography`, the vault refuses to
  start and says so. Home-grown obfuscation presented as encryption is worse
  than none, because you believe it.
- The database is `0600` inside a `0700` directory.

```console
$ aegis status
Clipboard vault: on, 412 entries, encrypted at ~/.local/share/Aegis/vault.sqlite.
                 Credentials are never stored.
```

## Commands

| | |
| --- | --- |
| `aegis plan [downloads\|desktop]` | Show what tidying would change. Changes nothing. |
| `aegis apply [--yes]` | Apply the last plan, after confirmation |
| `aegis undo [batch]` | Reverse a batch of changes |
| `aegis history` | Everything Aegis has changed, and what is still reversible |
| `aegis duplicates [folder]` | Files with identical contents. Deletes nothing. |
| `aegis large [folder]` | Biggest files first |
| `aegis find <words>` | Search saved clipboard history |
| `aegis status` | Configuration, journal location, vault health |
| `aegis do "<phrase>"` | The same commands, written the way you'd say them |
| `aegis run` / `aegis headless` | Start the agent with / without a window |

`aegis do` parses phrases into **structured intents** — a command name plus
validated parameters. Free text never becomes a shell command, and neither does
anything a language model produces. What it does not understand, it says so:

```console
$ aegis do "delete everything"
I don't understand 'delete everything'.
Run 'aegis do help' for the full list.
```

A typo of a real phrase still resolves (`shwo history`, `orgnize downloads`),
but text that resembles nothing in the table gets no suggestion at all — a
shortlist assembled from whichever commands happened to share letters with your
sentence is worse than admitting the parser does not know.

## Watching folders

When enabled, Aegis watches Desktop and Downloads with kernel notifications
(`watchdog`; FSEvents / ReadDirectoryChangesW / inotify), falling back to a
5-second poll if it is not installed. A file is only acted on once it has
**stopped changing size**, so half-written downloads are left alone.

Archives that arrive are inspected statically — never extracted — for entries
that unpack outside the folder, disguised executables, decompression-bomb
ratios and password protection. Anything flagged is moved to quarantine,
renamed so a double-click does nothing, stripped of its execute bits, and
**journalled like everything else**, so `aegis undo` reverses it.

The daily scheduler **proposes** and never acts. It tells you how many files are
ready to archive; you run `aegis apply`.

## Privacy

Nothing leaves your machine. There is no telemetry and no update check. The only
network code in the project is an optional request to **your own** Ollama
instance on localhost, off by default, and:

- untrusted text is delimited and marked as data in the prompt;
- credentials are redacted before the text is sent;
- the reply is treated as **a string to display** — never a command, a path, or
  an action. Control characters are stripped and length is capped.
- the model can never cause a file to move. Only the rules engine plans, and
  only you authorise.

Core functionality does not require a model at all; the built-in extractive
summariser is the default, not a consolation prize.

## Install

```bash
pip install -e .                  # CLI: plan, apply, undo, history, duplicates
pip install -e ".[desktop]"       # + clipboard, tray icon, hotkey, notifications
pip install -e ".[dev]"           # + tests, lint, type checking
```

The window needs `tkinter`, which ships with CPython. On Debian/Ubuntu:
`sudo apt install python3-tk`. **The command line works without it** — that was
a bug, and now there is a test for it.

For the clipboard vault, set a passphrase once:

```bash
python -c "import keyring; keyring.set_password('aegis','vault','<your passphrase>')"
# or, without a keyring:
export AEGIS_VAULT_PASSPHRASE='<your passphrase>'
```

## Development

```bash
pip install -e ".[dev]"
pytest -q              # 151 tests
ruff check aegis tests
mypy aegis
python examples/demo.py
```

`mypy` runs with no suppressed error codes. If a change needs one, the type is
wrong — fix the type. See the note in `pyproject.toml` about the four codes that
used to be disabled.

Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
Threat model and boundaries: [`docs/SAFETY.md`](docs/SAFETY.md).

## What Aegis is not

- **Not an autonomous shell agent.** It has a fixed command table. It cannot run
  arbitrary commands, and no model output is ever executed.
- **Not antivirus.** Archive inspection is a handful of structural heuristics,
  stated as such. It finds a booby-trapped ZIP; it will not find malware.
- **Not a backup tool.** Undo reverses Aegis's own changes. It is not a time
  machine for your filesystem.
- **Not a cloud service.** There is no account and no sync.

## License

MIT — see [LICENSE](LICENSE).
