# Revival audit — Aegis OS Agent v0.1.3

> **Re-measured after the final round of fixes.** The transcripts below were
> produced part-way through the revival. Three further defects were then fixed
> — `aegis do "open vault"` resolving to `wipe_vault` through the fuzzy pass,
> the CLI running destructive intents with no confirmation, and `ollama_url`
> reaching `urlopen` unvalidated — each with regression tests. Re-measured at
> the shipped tree:
>
> - `pytest -q` — **170 passed**
> - `ruff check aegis tests examples scripts` — clean
> - `mypy aegis` — clean, 38 source files, no suppressed codes
> - `python examples/demo.py` — exit 0
>
> Test count 17 → **170**. Everything else in this document stands, including
> its "Not verified" section.



Date: 2026-09-02 Audited commit: `cc2f885` (released as v0.1.3) Environment: Linux, CPython 3.11.15,
pytest 9.0.3, ruff 0.15.11, mypy 1.20.2

## What this is

The record of what the code at v0.1.3 actually did, written before and during the work released as
v0.2.0. It exists because this project's whole value proposition is trustworthiness — it moves the
user's files and can hold the user's clipboard history — and because the documentation shipped at
v0.1.3 described a program that did not exist.

Two constraints from the owner framed the audit:

1. Arbitrary language-model output must never directly execute shell commands or destructive
   filesystem operations. Actions need structured validation.
2. The clipboard vault must not have a misleading weak "secure encryption" fallback.
   Vault-unavailable is preferable to clipboard history silently stored under home-grown encryption.

Everything below is quoted from the source at that commit, or produced by running it. What could not
be executed here is listed in its own section.

## How the audit was produced

All revival work is uncommitted, so both states are directly addressable: `git show HEAD:<path>` is
the original v0.1.3 file; the file on disk is current. A clean checkout was made with `git worktree
add /tmp/ag-head HEAD` and all baseline tool runs and behavioural experiments were performed inside
it (removed afterwards with `git worktree remove /tmp/ag-head --force`), with `XDG_DATA_HOME` and
`XDG_CONFIG_HOME` pointed at fresh temporary directories so nothing touched a real user profile.
Behavioural findings came from driving the v0.1.3 code: constructing an `ActionExecutor` against a
scratch config, invoking the Click CLI through `click.testing.CliRunner`, reading the vault's SQLite
file as raw bytes, and serving a local HTTP stub reproducing Ollama's default response shape. The
README, `SAFETY.md` and `docs/hardening.md` were read but not trusted; every claim was checked
against the Python.

## What worked at HEAD

This was not a broken repository, and the revival kept most of it.

- **The package imported and the tests passed** — 17 tests, 2.25 s, no failures.
- **`ruff check aegis tests` and `mypy aegis` both reported clean.** What those commands were
  configured to check is a separate finding (F12); the code held no errors under the configuration
  in force.
- **The event bus (`aegis/core/bus.py`) is genuinely good** — a small `RLock`-guarded pub/sub,
  frozen `slots=True` event dataclasses, and a `publish` that isolates subscriber exceptions; it
  survived almost unchanged.
- **The configuration layer (`aegis/config/schema.py`) is dependency-free and careful** —
  `from_dict` validators clamping `max_items` and `archive_days` to sane minimums, explicit
  nested-dict merging in `load_config`, `is_config_complete` for wizard gating. Only `Dict`→`dict`
  modernisation and one new field were needed.
- **Quarantine worked as documented.** `_write_report` wrote JSON and HTML side by side with
  punctuation-free UTC timestamps (valid on Windows), `_render_html` ran user-controlled strings
  through `html.escape`, and `inspect_archive` read `namelist()` only — so the "never executes
  untrusted input" claim held for the archive path.
- **URL tracker stripping worked**, including `keep_blank_values=True` so a bare `?q=` is not
  silently altered; notification backends degraded quietly when `notify2` / `pync` / `win10toast`
  were absent; and the first-run wizard had a real non-Tk path (`_run_cli`, `WizardAutomation`) —
  the only part of the UI layer testable without a display.

## What was broken

### F1 — The vault stored a plaintext copy of every entry

`git show HEAD:aegis/core/vault.py` — a plaintext column in the schema, filled by `store()` with the
raw start of the entry and queried directly by `search()`:

```
                preview TEXT NOT NULL,                                     # schema
        preview = content[:120].replace("\n", " ")                          # store()
            "SELECT payload FROM entries WHERE preview LIKE ? ORDER BY ..." # search()
```

Any copied secret shorter than 120 characters — nearly all passwords, API keys, TOTP codes and
recovery phrases — was written to disk in full, in the clear, in a file created with the process
umask. The Fernet payload beside it was irrelevant. **Verified** — storing
`hunter2-my-actual-password`, then reading the database file as bytes:

```
plaintext 'hunter2' present in raw db file: True
preview column row: [('hunter2-my-actual-password',)]
```

The most serious finding here. A feature sold as "encrypted clipboard history" wrote the sensitive
part of every entry unencrypted.

### F2 — The vault fell back to repeating-key XOR and called it encryption

Same file, when `cryptography` was not importable:

```
        else:
            self._xor_key = key_material
            LOGGER.info("Using lightweight XOR fallback for clipboard vault")
        ...
        encrypted = bytes(b ^ self._xor_key[i % len(self._xor_key)] for i, b in enumerate(data))
```

A 32-byte key XORed cyclically is a Vigenère cipher whose keystream is reused across every record in
the database. One known or guessed plaintext — a URL, a git command, a file path — recovers the
keystream and therefore every other entry. **Verified** with a standalone reconstruction: from one
known 20-byte plaintext the keystream falls out, and a second entry decrypts without the passphrase.
`SAFETY.md` sold this as a protection tier — "a lightweight XOR cipher fallback keeps entries
unreadable to casual inspection" — and the README as "AES-Fernet when available, with a local XOR
fallback". This is exactly the misleading weak fallback the owner ruled out.

### F3 — The PBKDF2 claim was accurate; the sentence around it was not

The iteration count actually used at HEAD and the count claimed in `docs/hardening.md` agree, and
the audit should say so plainly.

Code (`vault.py`, `_derive_key`):

```
        digest = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 390000, dklen=32)
```

Documentation (`docs/hardening.md`):

> Encryption uses AES-Fernet when the `cryptography` package is installed;
> otherwise a per-user XOR cipher derived from PBKDF2 (SHA-256, 390k iterations).

390,000 in both, and 390,000 was reasonable guidance for PBKDF2-HMAC-SHA256 as of
2023. The defect is the claim built on top of it: KDF strength is irrelevant when
the cipher it feeds leaks its keystream to a single known plaintext (F2). A strong KDF in front of a
broken cipher yields a broken cipher with a slow start.

The release changelog lists this 390,000 figure among claims that were "not true"; it was true, and
the correction is recorded in REVIVAL_CHANGELOG.md. v0.2.0 raises it to 600,000 (current OWASP
guidance) as a separate, smaller improvement.

### F4 — The vault had never worked in the running application

```
        self._connection = sqlite3.connect(self.db_path)
```

`sqlite3.connect` defaults to `check_same_thread=True`, so the connection belongs to the thread that
built `ActionExecutor` — the main thread. Clipboard entries arrive from `ClipboardWatcher._run`, a
`threading.Thread`, via `EventBus.publish` → `IntentRouter._on_clipboard` → `record_clipboard` →
`vault.store`. **Verified** — calling `store()` from a second thread:

```
ProgrammingError: SQLite objects created in a thread can only be used in that
same thread.
```

The user never saw it, because `EventBus.publish` swallows subscriber exceptions. In normal
operation the vault silently recorded nothing; the v0.1.3 suite passed only because
`tests/test_vault.py` called `store()` on the main thread. Between F1 and F4 the vault was
simultaneously useless and unsafe: nothing stored when running, plaintext stored when tested.

### F5 — Unrecognised input executed a default action

`git show HEAD:aegis/core/intents.py`, last line of `IntentRouter.parse`:

```
        return Intent(name="summarize_clipboard", params={}, confidence=0.2)
```

There was no "unknown". Every unrecognised string, the empty string included, produced a real
dispatchable intent, and `dispatch` ran it because the handler exists. The `confidence=0.2` was
recorded and never consulted. **Verified** by replaying the v0.1.3 parser:

every one of `delete everything`, `list downloads older than 30d`, `rename last file intelligently`,
`clean up my desktop please`, `organize my downloads folder`, `help` and the empty string returned
`summarize_clipboard` by fall-through. For a file organiser the fourth and fifth are the point: the
two most natural ways to ask it to tidy a folder both did nothing but summarise the clipboard.

### F6 — Whole-string fuzzy matching turned a documented command into a destructive one

```
def _fuzzy_score(text: str, keyword: str) -> float:
    return SequenceMatcher(None, text, keyword).ratio() * 100
        ...
                score = _fuzzy_score(text_lower, keyword)
                if score >= 80:
```

The comparison is the *entire input* against a keyword, so match quality tracked input length rather
than meaning — producing both F5's false negatives and false positives.

The worst false positive is in the project's own README, which lists `open vault` under "Command
Palette / Example commands". `SequenceMatcher(None, "open vault", "wipe vault").ratio()` is exactly
`0.8`, and the threshold is `>= 80`. **Verified**: at v0.1.3 `open vault` parses to `wipe_vault` at
confidence 0.80, dispatched with no confirmation via `"wipe_vault": lambda intent:
self.executor.wipe_vault()`. The README told users to type a phrase that deleted their clipboard
history. `wipe vaults` scored 0.95 and `clear historyy` 0.96 — a destructive command one typo away
in every direction.

### F7 — `organize_directory` moved everything, with no containment, journal or undo

`git show HEAD:aegis/core/actions.py`:

```
        for path in root.iterdir():
            if path.is_file():
                destination = archive_root / path.name
                ...
                shutil.move(str(path), destination)
```

No rule, filter, age check, dry run, confirmation or record. "Organise" meant "move every file out
of this folder into a timestamped archive". **Verified** — a scratch Desktop, one call to
`organize_directory("desktop")`:

```
before: ['.hidden', 'in-progress.txt', 'photo.png', 'tax-return-2025.pdf', 'thesis-final.docx']
after : []
moved : 5
```

Searching the tree for the three things that would make this recoverable returns nothing. **No
undo** — `ActionExecutor` has no `undo`/`undo_last`. **No journal** — no append-only record of moves
exists anywhere in `aegis/`; the only artefacts are quarantine reports. **No path containment** —
sources come from `root.iterdir()`, destinations from `expanduser()`, neither is checked against an
approved root, symlinks are unhandled, and `shutil.move` follows them as their targets;
`aegis/core/safety.py` did not exist. This is the largest gap between what the project claimed to be
and what it was.

### F8 — The CLI could not start without tkinter

`git show HEAD:aegis/main.py`, module scope:

```
from .ui.palette import CommandPalette          # plus SettingsWindow, HotkeyManager,
from .ui.settings import SettingsWindow         # TrayController and FirstRunWizard
```

`aegis/ui/palette.py` and `aegis/ui/settings.py` both `import tkinter as tk` at module scope, and
tkinter is not in a default Linux CPython install (Debian/Ubuntu ship `python3-tk` separately) nor
in most containers. **Verified:**

```
$ python -m aegis --help
  File "/tmp/ag-head/aegis/main.py", line 20, in <module>
    from .ui.palette import CommandPalette
  File "/tmp/ag-head/aegis/ui/palette.py", line 7, in <module>
    import tkinter as tk
ModuleNotFoundError: No module named 'tkinter'
```

Not only `run` and `palette` — `headless`, `report` and `dump-config` were all unreachable, because
the failure is at import. A headless mode that needs a GUI toolkit to import is not a headless mode.
A smaller defect sits in the same file: the group callback ran the interactive wizard whenever no
config existed, for every subcommand, terminal or not:

```
    if not config_exists:
        wizard = FirstRunWizard(config, target_path)
        config = wizard.run()
```

### F9 — `run` and `headless` started every service and stopped it in the same breath

```
        app.start(headless=False)
    except KeyboardInterrupt:  # pragma: no cover - manual exit
        ...
    finally:
        app.stop()
```

`start()` returns as soon as its background threads exist: `palette.run()` starts a thread,
`hotkey.start()` calls `listener.start()`, `tray.start()` calls `run_detached()`. Nothing waits, so
control falls into `finally: app.stop()`.

**Verified** by stubbing `tkinter` so the module could be imported at all:

```
`aegis headless` at HEAD returned after 2.00s, exit=0
```

The two seconds are the `join(timeout=1)` calls in `stop()`. The agent had never run as an agent.

### F10 — The scheduler emptied folders on startup, unprompted

`git show HEAD:aegis/core/scheduler.py`:

```
    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._archive_job()
            # sleep until next 24h cycle
```

The job runs first and sleeps second, so it fires the instant the process starts. On whether it
called a method that exists: it did.
`self.executor.archive_old_files(self.config.scheduler.archive_days)` was a real method and a real
field at v0.1.3. That was not the problem. The problem is what the method did — F7's loop with an
mtime filter, across both Desktop and Downloads — combined with when it ran. **Verified** — a
scratch Desktop of three files last modified 400 days ago, through the same two-second `aegis
headless` invocation as F9:

```
Desktop before `aegis headless`: ['notes.md', 'tax-return-2024.pdf', 'wedding-photos.zip']
Desktop after  `aegis headless`: []
Archive now contains: ['2026-09/notes.md', '2026-09/tax-return-2024.pdf', '2026-09/wedding-photos.zip']
```

Two seconds after start, with no preview, confirmation, journal or undo, the Desktop was empty. F8
limited the blast radius to Windows and macOS users; design did not. A related dead setting:
`SchedulerSettings.zip_monthly` is stored in config and offered in the settings window as "Zip
monthly archives", but no code in `aegis/` reads it — nothing has ever been zipped.

### F11 — The Ollama integration could never have worked

`git show HEAD:aegis/core/summarizer.py`:

```
        payload = json.dumps(
            {"model": "llama3", "prompt": ("You are a summarizer. ...\n" f"Text: {text}")}
        ).encode("utf-8")
```

There is no `"stream"` key. Ollama's `/api/generate` streams by default, returning newline-delimited
JSON, while the response handling assumes one object
(`json.loads(response.read().decode("utf-8"))`). **Verified** against a local stub replying the way
the default does:

```
HEAD _summarize_with_ollama raised JSONDecodeError: Extra data: line 2 column 1 (char 55)
Ollama summarization failed: Extra data: line 2 column 1 (char 55)
HEAD summarize_text falls back to: 'Invoice for November. Please pay.'
```

Every call raised, was caught by `except Exception`, and fell back to heuristics with a
`LOGGER.warning`. A feature advertised in the README, `SAFETY.md` and `docs/hardening.md` was dead
code failing silently, and nobody could notice because the fallback always returned something
plausible. Three further problems in the same method, latent only because of the above. **Untrusted
text was interpolated straight into the prompt** (`f"Text: {text}"`) with no delimiting and no
instruction to treat it as data — clipboard content is attacker-influenced in exactly the scenario
this tool exists for. **No redaction**: a copied API key would have gone to the model verbatim. And
**`config.ollama_url` was used unvalidated**, though `docs/hardening.md` claimed "Any attempt to
reach non-local addresses raises a warning in the logs (`WARNING` level) and aborts" — no such check
exists anywhere in the tree, so a config pointing at a remote host would have exfiltrated clipboard
text while the "offline contract" section still said it could not.

### F12 — The type checker and linter were configured not to look

`git show HEAD:pyproject.toml`:

```
disable_error_code = ["arg-type", "call-overload", "dict-item", "attr-defined"]
```

The comment beside it called this noise from a "known design choice". **Verified** by deleting that
line and re-running the same mypy on the same code: **10 errors in 3 files**, including
`aegis/core/intents.py:47: Argument 1 to "search_vault" ... has incompatible type "object"; expected
"str"` and four `dict-item` errors showing the handler table's declared type was a fiction.
`attr-defined` is the code that catches calls to methods that do not exist — the class of bug the
scheduler was suspected of.

Linting was weaker. `setup.cfg` carried a `[ruff]` section selecting `E, F, I, UP, B, S, DTZ` at
line length 100 and ignoring `S101, S311`. ruff does not read `setup.cfg`; it reads `[tool.ruff]` in
`pyproject.toml` or a `ruff.toml`, and neither existed. The configuration was inert, so `ruff check`
ran the default rule set (E4, E7, E9, F) at the default line length. **Verified**: running the
ruleset `setup.cfg` intended produces **111 errors** — 11 × `DTZ003` (naive `datetime.utcnow()`), 2
× `S310` (unvalidated `urlopen`), `S105`/`S106` (hardcoded password strings), `S608` (SQL built by
string formatting — the vault's `NOT IN (…)` prune), 3 × `S607` (partial executable paths in
`subprocess.run`); several map directly onto findings above. `setup.cfg` also held a second,
conflicting `[mypy]` section and `version = 0.1.0` against `pyproject.toml`'s `0.1.3`.

### F13 — `open_path` handed arbitrary paths to the OS handler

`git show HEAD:aegis/core/utils.py`:

```
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)
```

All three resolve a *handler* for whatever they are given, so a `.desktop`, `.command`, `.bat` or
`.lnk` file means executing it, and the function never checks that its argument is a directory. It
was called only with the vault's parent directory, so this was a loaded gun rather than a fired one
— but the README's promise that "Files are only moved, copied, or renamed – never executed" rested
on call-site discipline, not on the function.

### F14 — Documentation described a program that did not exist

Checked line by line against the code. Beyond F2, F3 and F11: From `docs/hardening.md`, each checked
by grep: "Set `AEGIS_DISABLE_LOGGING=1` to silence disk logging entirely" — **that string appears
nowhere in the tree**. "Logs remain local under `~/Aegis/Reports/logs/`" — **there is no
`FileHandler` or `RotatingFileHandler` anywhere in `aegis/`**; logging is
`logging.basicConfig(level=logging.INFO)` to stderr, and `SAFETY.md` repeats the claim twice in
consecutive paragraphs, one duplicated verbatim. "the scheduler exposes the `--archive-days` flag" —
**no such flag exists on any command**. "Quarantine folders are set to read-only where the OS
permits" — **only the file is chmodded** (`destination.chmod(0o444)`); the folder is untouched.
"Wipe instantly … or via CLI `aegis report --html` to verify deletion" — `report` exports an
activity report and never inspects the vault.

Documented commands that do not exist: `README.md` shows `aegis run --use-ollama
--ollama-url=http://localhost:11434`, but **`run` has no `--ollama-url` option**;
`examples/demo_walkthrough.md` shows `aegis headless --use-ollama`, but **`headless` takes no
options at all**. Both would have exited with "no such option", had the CLI been importable (F8).
That walkthrough's step 3 also tells the reader to run `clean desktop` — which moved every file off
the Desktop with no undo (F7) — and calls the result "with safe renames", though nothing is renamed.
`README.md` additionally carried a stray unbalanced code fence, two duplicated sentences from the
v0.1.3 merge repair, and a broken link labelled `docs/packaging.md` pointing at
`examples/demo_walkthrough.md`.

Drift of this size is not cosmetic here. The encryption claim in particular is the first thing a
security-minded reader checks; getting it wrong costs more than the words are worth.

## What could not be checked, and why

- **No Tk widget has ever been rendered.** This machine has no tkinter, so nothing in
  `aegis/ui/palette.py`, `aegis/ui/settings.py`, the `_run_tk` branch of `aegis/ui/first_run.py`, or
  their widget-construction paths has been executed, at HEAD or now; findings there are read from
  source. Where a running interpreter was needed to reach non-UI code (F9, F10), `tkinter` was
  replaced with a stub — proving the control flow in `main.py` and `scheduler.py` and nothing about
  the widgets.
- **The tray icon and global hotkey were not exercised.** `pystray`, `pynput` and `Pillow` are
  absent, and `TrayController.start` / `HotkeyManager.start` swallow the ImportError and log at
  INFO, so their real behaviour is untested in both trees.
- **No network.** PyPI returns 403 through this environment's proxy, so no dependency could be
  installed to check a version-specific claim, and no live Ollama daemon exists. F11 was produced
  against a local `http.server` stub reproducing the documented default streaming shape, not against
  `ollama serve`. `pyinstaller` likewise cannot be installed, so the build was never attempted:
  `aegis.spec` and `scripts/build_artifacts.py` were reviewed as text.
- **Windows and macOS are unverified.** Everything ran on Linux: the `os.startfile` branch of
  `open_path`, the `win10toast` / `pync` backends, the `hdiutil` step in
  `scripts/build_artifacts.py`, and the filename constraints the quarantine reporter is written to
  satisfy were read, not run.
- **Real clipboard behaviour is unverified.** `pyperclip` is absent, so `ClipboardWatcher.start()`
  returns immediately with a warning; clipboard paths were driven by calling `process_value` and
  publishing events directly. Concurrency was likewise demonstrated rather than exhausted — F4
  reproduces one cross-thread failure, and the audit does not claim to have found every race.

## Baseline measurements

`XDG_DATA_HOME` and `XDG_CONFIG_HOME` were set to fresh temporary directories for every run.

### HEAD (v0.1.3), in `git worktree add /tmp/ag-head HEAD`

| command | result |
| --- | --- |
| `pytest -q` | **17 passed in 2.25s** |
| `ruff check aegis tests` | **All checks passed!** (exit 0) |
| `mypy aegis` | **Success: no issues found in 32 source files** (exit 0) |
| `python -m aegis --help` | **ModuleNotFoundError: No module named 'tkinter'** |

The two clean results need F12's qualification to be read honestly:

| diagnostic re-run | result |
| --- | --- |
| ruff with the ruleset `setup.cfg` intended but ruff never read (`--select E,F,I,UP,B,S,DTZ --ignore S101,S311 --line-length 100`) | **111 errors**, 56 auto-fixable |
| `mypy aegis` with `disable_error_code` deleted from `pyproject.toml` | **10 errors in 3 files** |

Size at HEAD: 32 Python files / 2,964 lines under `aegis/`, 11 test files / 409 lines under
`tests/`.

### Current tree (v0.2.0), in `/root/revival/Aegis-OS-Agent`

| command | result |
| --- | --- |
| `pytest -q` | **165 passed in 58.54s** |
| `ruff check aegis tests examples scripts` | **All checks passed!** (exit 0) |
| `mypy aegis` | **Success: no issues found in 38 source files** (exit 0) |
| `python examples/demo.py` | **exit 0**, runs to completion |
| `python -m aegis --help` | **exit 0**, lists 15 commands |

These configurations are the ones actually in force: `[tool.ruff.lint] select = ["E", "F", "B", "I",
"UP"]` in `pyproject.toml` (which ruff reads), and a `[tool.mypy]` section with **no
`disable_error_code`** — the four suppressed codes are enabled and the underlying types were fixed
rather than re-suppressed.

Size now: 38 Python files / 6,041 lines under `aegis/`, 11 test files / 1,774 lines under `tests/`.
Tests 17 → 165: `test_intents.py` 43, `test_secrets.py` 23, `test_cli.py` 21,
`test_plan_and_journal.py` 20, `test_executor.py` 18, `test_summarizer_and_watchers.py` 14,
`test_vault.py` 14, `test_repo_hygiene.py` 8, `test_first_run.py` 2, `test_quarantine_report.py` 1,
`test_renamer.py` 1.

Each finding above was re-checked against the current tree and no longer reproduces; the
per-behaviour evidence is in the Verification section of REVIVAL_CHANGELOG.md.

## Residual risks the revival did not close

1. **`open vault` still resolves to `wipe_vault`.** The fuzzy pass scores `SequenceMatcher("open
   vault", "wipe vault") = 0.8` against a `FUZZY_THRESHOLD` of `0.80`. The palette mitigates it —
   `needs_confirmation` returns True for destructive intents — but the CLI does not: `aegis do "open
   vault"` dispatches `wipe_vault` and prints the number of deleted entries, with no prompt
   (**verified against a scratch vault**). The phrase is gone from the documentation, so this is
   latent rather than advertised, but `aegis do` should gate destructive intents as the palette
   does.
2. **`ollama_url` is still unvalidated.** Nothing checks the configured host is local before
   clipboard-derived text is POSTed to it. Redaction reduces the damage; it does not make the
   offline contract true by construction.
3. **`aegis/core/utils.py` still uses naive `datetime.utcnow()`** in `timestamp_folder` and
   `day_folder`; the current ruff selection omits `DTZ`, so it is unflagged. And
   **`SchedulerSettings.zip_monthly` remains a setting nothing reads**, still offered in the Tk
   settings window.
4. **The UI layer remains unexecuted.** The logic moved to `aegis/ui/palette_model.py` and is
   tested; the widgets in `aegis/ui/palette.py` are not, and the confirmation dialog that mitigates
   risk 1 has never been rendered.
