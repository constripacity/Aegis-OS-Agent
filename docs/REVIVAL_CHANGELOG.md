# Revival changelog — 0.1.3 → 0.2.0

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



Date: 2026-09-02 Base commit: `cc2f885` (v0.1.3). Version in `pyproject.toml`: `0.1.3` → `0.2.0`

The engineering record of the revival: what changed, in which file and symbol, and why.
`CHANGELOG.md` carries the release-facing summary of the same work; this document says *why* each
change was made and what was run to confirm it. Where the two differ in detail, the differences are
listed under "Corrections to the release changelog", and this document is the more precise of the
two.

Findings cited as F1–F14 are in [REVIVAL_AUDIT.md](REVIVAL_AUDIT.md).

## Security

### The vault has one cipher and no fallback

`aegis/core/vault.py` — `ClipboardVault._initialize`, new `VaultUnavailable`.

v0.1.3 fell back to a repeating-key XOR when `cryptography` was missing and announced it as `"Using
lightweight XOR fallback for clipboard vault"` (F2). A 32-byte key XORed cyclically across every
record is one known plaintext away from total compromise, and the documentation sold it as a
protection tier. There is now one implementation — Fernet, keyed by PBKDF2-HMAC-SHA256 — and no
second path. When `cryptography` cannot be imported, or no passphrase is available, `_initialize`
raises `VaultUnavailable` with an actionable message and the vault stays shut:

```python
raise VaultUnavailable(
    "the 'cryptography' package is not installed. The vault stores "
    "clipboard history, which routinely contains passwords and tokens, "
    "so it will not run without vetted encryption. ..."
)
```

`ActionExecutor.__init__` publishes the reason on the bus instead of failing silently, and `aegis
status` prints it. `cryptography>=42.0` moved from `requirements-optional.txt` into the required
dependencies, so the supported install has a working vault rather than a degraded one.

Why this shape: vault-unavailable is a state the user can see and fix. Vault-available-but-weak is a
state they cannot detect and will trust.

### The plaintext preview column is gone, and existing vaults are migrated

`aegis/core/vault.py` — schema v2, `_migrate_legacy_rows`, `_blind_index`.

v0.1.3 wrote `preview = content[:120]` into an unencrypted column and searched it with `WHERE
preview LIKE ?` (F1) — verified by reading the database file as raw bytes, where a copied password
was present in full.

The v2 schema has no `preview`. The only plaintext columns are the row id, a timestamp, a coarse
type label and a blind index. `_migrate_legacy_rows` detects a v1 table, warns that anything copied
while it was in use should be rotated, and runs `ALTER TABLE entries DROP COLUMN preview`. Search
still works without decrypting: `_blind_index` HMACs each lowercased token under a key split from
the master material (`master[:32]` encrypts, `master[32:]` keys the index), so equality search is a
`LIKE` over hashes and the index cannot be reversed into the tokens. Splitting the key matters — one
key for both would let an index hit confirm a guess about the ciphertext.

`_load_salt` generates 32 bytes instead of 16 and rejects a short existing salt. The database, its
directory and the salt file are chmodded 0600 / 0700 / 0600 via `_harden`.

### Credentials are excluded before they are encrypted

New `aegis/core/secrets.py` — `classify_secret`, `redact`, `shannon_entropy`.

Encrypting a secret still stores the secret. `ClipboardVault.store` now runs
`classify_secret(content)` first and writes nothing if the content matches a private-key block; an
AWS/GitHub/Slack/Google/OpenAI/Stripe key shape; a JWT; a URL with an embedded password; an
assignment line (`password: …`); a one-time code; a Luhn-valid card number; a long high-entropy
opaque blob; or a generated-password shape (16–128 chars, ≥3 character classes, entropy ≥3.8, not a
path or URL). `_looks_like_a_path_or_url` and the entropy floors keep git SHAs, filenames and
hostnames out of the match set. The bias is deliberate: a false positive costs one un-saved
clipboard entry, a false negative writes a production key to disk.

`redact()` is now also called in two places that previously wrote clipboard content verbatim:

- `ActionExecutor._save_code_snippet` — v0.1.3 wrote the raw snippet to `~/Aegis/Snippets/<date>/`,
  so `API_KEY = 'sk-live-…'` landed in a plaintext file regardless of any vault setting. The file is
  now redacted and chmodded 0600.
- `Summarizer._ollama` — below.

### PBKDF2 iterations 390,000 → 600,000

`aegis/core/vault.py` — `PBKDF2_ITERATIONS`. v0.1.3 used `390000`, and `docs/hardening.md` said
390k; those agreed (F3), and the number was never the problem. 600,000 is current OWASP guidance for
PBKDF2-HMAC-SHA256 — a routine refresh, recorded here so nobody reads the old documentation as
having been wrong about this.

### One external process, and it refuses files

`aegis/core/utils.py` — `open_path`. v0.1.3 handed any path to `os.startfile` / `open` / `xdg-open`
(F13), all of which resolve a *handler*, so a `.desktop`, `.command` or `.lnk` file means execution.
`open_path` now reveals directories only, returns `False` with a logged reason otherwise, passes an
argv list with `shell=False`, and returns a bool the caller can act on.

A CI job enforces the invariant repository-wide: the build fails if `os.system`, `os.popen`,
`shell=True`, `eval(` or `exec(` appears anywhere in `aegis/`, or if `subprocess` is imported by any
file other than `aegis/core/utils.py`.

### Model output is display text and nothing else

`aegis/core/summarizer.py` — `PROMPT_TEMPLATE`, `_sanitize_model_output`.

Untrusted text is delimited by `<<<BEGIN UNTRUSTED TEXT>>>` markers with an instruction to treat it
as data, capped at `MAX_INPUT_CHARS = 8_000`, and passed through `redact()` before it leaves the
machine. What comes back is stripped of control characters, whitespace-collapsed, capped at
`MAX_OUTPUT_CHARS = 400`, and returned as a string — never parsed as a command, used as a path, or
given to a shell. That is the structural half of the owner's first constraint. The other half is the
parser: `COMMANDS` is a closed table, `IntentRouter._handlers` maps those names to Python callables,
and nothing else can be produced by parsing. A language model cannot introduce an action, only fail
to match an existing one.

## Added

### A safety model: plan → authorise → execute → journal → undo

**`aegis/core/safety.py`** — `SafeRoots`, `UnsafePathError`, `unique_destination`, `default_roots`.
The single choke point every filesystem operation passes through. `check()` resolves *before*
testing containment, so `..` and absolute paths in untrusted input cannot escape; `check_source()`
refuses symlinks outright, because moving one either breaks it or silently acts on a file elsewhere;
`check_destination()` refuses an existing target, so nothing is overwritten. v0.1.3 had no
equivalent (F7).

**`aegis/core/plan.py`** — `Plan`, `PlannedAction`, `execute`, `resolve_conflicts`,
`ExecutionReport`. A `Plan` is a pure value: building one reads directory metadata and touches
nothing, so it can be printed, diffed, saved and discarded. `Plan.render()` is the dry-run diff the
user reads. `execute()` raises `PermissionError` on a plan that was never `authorize()`d, and
re-validates every action against `SafeRoots` at execution time rather than trusting the snapshot —
a plan is a photograph of a filesystem that may have moved on. `_move` falls back to
copy-verify-remove across filesystems and refuses to delete the source if the copy does not
hash-match.

**`aegis/core/journal.py`** — `ActionJournal`, `ActionRecord`, `ActionKind`, `BatchSummary`,
`UndoReport`. Append-only JSONL, fsynced per line, readable with `tail` or `jq` without this
program. Each record carries source, destination, SHA-256 and size — enough to reverse itself.
`undo_batch` works newest-first within a batch and verifies the recorded hash before restoring, so a
file edited after the move is reported and skipped rather than clobbered; `--force` is the explicit
override.

**`aegis/core/organizer.py`** — `Organizer`, `FileFacts`, `Rule`, `default_rules`. An ordered
declarative ruleset evaluated against metadata only (never file contents), producing a `Plan`.
Defaults are conservative: sort by kind and age into subdirectories of the folder being organised;
skip anything modified in the last day; skip `.DS_Store` / `desktop.ini` / `Thumbs.db`; skip `.part`
/ `.crdownload` / `.tmp` / `.partial`; never delete. Rules are idempotent — a second run over a
tidied folder proposes nothing.

Together these replace `ActionExecutor.organize_directory`, which moved every file out of Desktop
and Downloads with no filter, preview, journal or undo (F7 — verified: a scratch Desktop of five
files including `.hidden` went to empty in one call).

### A command line that works without a desktop

`aegis/main.py` gains `plan`, `apply`, `undo`, `history`, `large`, `duplicates`, `find`, `status`,
`do` and `setup`, and renames `dump_config` to `dump-config`: 15 commands, all functional with no
GUI toolkit installed.

`plan` and `apply` are separate processes, so the plan is persisted between them. `_save_pending` /
`_load_pending` write `pending-plan.json` beside the journal, and `_load_pending` re-validates on
read — a plan whose sources have moved is skipped rather than acted on.

### Quarantine that is bounded, neutralising and reversible

`aegis/core/quarantine.py`, rewritten. v0.1.3 flagged an archive if it contained an executable
extension, and did nothing else.

- `inspect_archive` is bounded — `MAX_MEMBERS = 5_000`, `MAX_TOTAL_UNCOMPRESSED = 512 MiB`,
  `MAX_RATIO = 200.0`. Reading a hostile archive is itself a risk; a decompression bomb in Downloads
  should not exhaust the machine inspecting it.
- `_member_escapes` detects members whose paths leave the extraction folder (`../`, absolute paths,
  drive letters) — the actual reason to distrust an archive, and the one v0.1.3 never checked.
  Right-to-left override characters and executable-behind-a-lure-extension patterns are flagged too.
- `isolate` renames the stored copy with a `.quarantined` suffix and clears the execute bits, so a
  double-click in the quarantine folder does nothing.
- `isolate` writes to the shared `ActionJournal`, so `aegis undo <batch>` reverses a quarantine
  exactly as it reverses a move. Quarantine is the one action that fires without a user command,
  which is precisely why it needed to become reversible.

### Palette logic that can be tested without a display

New `aegis/ui/palette_model.py` — `default_suggestions`, `filter_suggestions`, `needs_confirmation`,
`confirmation_text`, `render_result`, with no Tk import. `aegis/ui/palette.py` is now widgets and
wiring only.

`needs_confirmation(intent)` returns `intent.is_destructive`, and `confirmation_text` spells out the
consequence — for `wipe_vault`, "This cannot be undone — the vault has no journal." v0.1.3's palette
dispatched `wipe vault` on one keypress with no prompt.

The split exists because of a hard constraint: this project's development environment has no
tkinter, so anything left inside a Tk module is untestable here. Moving the decisions out is what
made 165 tests possible.

### Tests, examples and documentation

- New: `test_cli.py` (21), `test_executor.py` (18), `test_intents.py` (43),
  `test_plan_and_journal.py` (20), `test_repo_hygiene.py` (8), `test_secrets.py` (23),
  `test_summarizer_and_watchers.py` (14); `test_vault.py` grew from 1 test to 14. Total 17 → 165.
- `tests/test_repo_hygiene.py` also tests the *documentation*: every `aegis <subcommand>` in every
  Markdown file must be a registered command, every `aegis do "<phrase>"` must parse, every
  requirements file a document tells you to install must exist, and every relative link must
  resolve. Each has a floor assertion (`assert checked >= N`) so a filter that quietly stops
  matching fails rather than passing. This is the regression test for F14.
- `examples/demo.py` — the whole model (plan, apply, history, undo, quarantine, secret exclusion,
  refusal of an unknown phrase) in a throwaway directory, run by CI.
- `SECURITY.md`, `docs/SAFETY.md`, `docs/ARCHITECTURE.md`.

### CI that tests the things that broke

`.github/workflows/ci.yml`:

- a **CLI-without-tkinter** job that stubs `sys.modules['tkinter'] = None` and asserts `aegis
  --help` exits 0 — the regression guard for F8;
- a **minimal-install** job that installs with no extras and runs a real plan/apply/undo cycle,
  asserting the file is gone after apply and back after undo;
- a **security-invariants** job running the vault, secrets and safety-model tests plus the
  shell/eval grep above;
- `python examples/demo.py` as a build step.

## Changed

### The desktop UI is imported lazily

`aegis/main.py` — `_load_ui`, `_first_run_wizard`, `UIUnavailable`.

v0.1.3 imported the Tk widgets at module scope, and two of those modules `import tkinter` at module
scope, so the whole CLI failed at import on any machine without tkinter — not only `run` and
`palette`, but `headless`, `report` and `dump-config` (F8, verified). The Tk imports now happen
inside `_load_ui`, which raises `UIUnavailable` with per-platform install instructions, caught in
`run` and printed as a one-line error. The first-run wizard no longer ambushes the user: it runs
only for subcommands that need a configured agent (`run`, `headless`, `palette`, `setup`) and only
when `sys.stdin.isatty()`. Non-interactive invocations get a message pointing at `aegis setup`.

### `aegis run` and `aegis headless` stay running

`aegis/main.py` — `Application.wait`, `Application.request_shutdown`.

`start()` returns as soon as its daemon threads are spawned, and v0.1.3 fell straight into `finally:
app.stop()` (F9). Verified: `aegis headless` at v0.1.3 returned after 2.00 s having started and
stopped every service. `wait()` blocks on a `threading.Event`. `_quit`, which runs on the tray's own
thread, now calls `request_shutdown()` instead of raising `SystemExit`, which that thread would have
swallowed.

### The scheduler proposes instead of acting

`aegis/core/scheduler.py` — `run_archive_job`, `auto_apply`.

v0.1.3's `_run` called `_archive_job()` *before* its first sleep, so the daily archive fired the
instant the process started. Verified: a scratch Desktop with three files aged 400 days was emptied
within two seconds of `aegis headless`, with no preview, journal or undo (F10). The scheduler now
builds a plan and, if it is non-empty, publishes a notification saying how many files are ready and
how to review them. Files move only when a person runs `aegis apply`. `auto_apply=False` is the
default; when a user turns it on, every move still goes through `execute()` and the journal, so it
stays undoable.

Against what the release changelog implies: at v0.1.3 the scheduler called
`ActionExecutor.archive_old_files`, and that method existed. The defect was its behaviour and its
timing, not a missing symbol.

### The intent parser refuses instead of guessing

`aegis/core/intents.py`, rewritten around `COMMANDS`, `parse` and `_phrase_score`. Three defects,
all verified by replaying the old parser (F5, F6):

1. Unrecognised input fell through to `Intent(name="summarize_clipboard", …, confidence=0.2)` and
   was dispatched. `delete everything`, `help`, `list downloads older than 30d` and the empty string
   all summarised the clipboard.
2. Matching compared the *whole input* against each keyword with `SequenceMatcher`, so `organize
   desktop` scored 1.0 while `clean up my desktop please` scored about 0.5 and matched nothing.
3. That same comparison made `open vault` score exactly 0.80 against `wipe vault`, at a threshold of
   `>= 80`. The README listed `open vault` as an example palette command, so the documentation
   instructed users to delete their clipboard history.

Now: pass 1 scores *contained phrases*, weighting specificity and position over raw length, with
`GENERIC_PHRASES` requiring bare nouns like `vault` and `clipboard` to be the whole request or its
first word. Pass 2 is a fuzzy pass over leading word-windows, for typos rather than new intentions
(`FUZZY_THRESHOLD = 0.80`). Below that, `parse` returns `Intent("unknown", …)` and `dispatch`
refuses it with suggestions. `SUGGEST_THRESHOLD = 0.65` exists because an earlier revision of this
parser answered `make me a sandwich` with "Did you mean: summarize_clipboard, resume_watchers,
pause_watchers?" — three commands whose only claim was sharing the letters in "me" and "a". The
value sits in the measured gap: typos of real phrases score 0.92–0.93, unrelated text tops out
around 0.46–0.50.

### The Ollama request sets `stream: false`

`aegis/core/summarizer.py` — `_ollama`. v0.1.3's payload held only `model` and `prompt`; Ollama
streams by default, so the daemon replied with newline-delimited JSON and the single
`json.loads(response.read())` always raised (F11). Verified against a local stub reproducing the
default shape: `JSONDecodeError: Extra data: line 2 column 1 (char 55)`. Every call fell into
`except Exception` and used the heuristic, so a feature advertised in three documents was dead code
that failed silently.

Also here: the model name moved to `AppConfig.ollama_model` (default `llama3.2`) instead of a
hardcoded `"llama3"`; exception handling narrowed from bare `Exception` to
`URLError`/`OSError`/`TimeoutError` and `ValueError`/`KeyError`, with different log messages so "the
daemon is not running" reads differently from "the daemon said something unusable"; and the timeout
went from 5 s to 20 s, which is realistic for local inference. The heuristic path was rewritten too.
`_heuristic` scores by `_information_density` (distinct content words per word, with a mild length
preference) and returns the chosen sentences **in their original order**; v0.1.3 returned them
sorted by score, producing summaries with the sentences shuffled.

### The filesystem watcher waits for files to settle

`aegis/watchers/filesystem.py` — `_pending`, `_flush_settled`. v0.1.3 published a `FileSystemEvent`
the moment a path appeared in a directory glob, so a 4 GB download was inspected and potentially
organised while still being written. A file must now be unchanged in size for a settle interval
before it is announced; `publish_now` bypasses that for tests and direct CLI use.

### Types were fixed rather than suppressed

`pyproject.toml`, `aegis/core/bus.py`, `aegis/core/intents.py`.

v0.1.3 disabled four mypy error codes project-wide — `disable_error_code = ["arg-type",
"call-overload", "dict-item", "attr-defined"]` — with a comment claiming the event bus and intent
router "could not be typed" (F12). Verified: deleting that line surfaces 10 errors in 3 files.

`disable_error_code` is gone. `EventBus.subscribe` carries `@overload`s keyed on
`Literal["clipboard"]` / `Literal["filesystem"]` / `Literal["notification"]`, so a handler
registered for one name is checked against that event class. `IntentRouter._handlers` is typed
`dict[str, Callable[[Intent], Any]]` and `dispatch` returns `Any`, which is the honest signature for
a table whose handlers return plans, reports, lists and strings. `no_implicit_optional`,
`warn_unused_ignores`, `warn_redundant_casts` and `warn_unused_configs` are on, and the four `#
type: ignore` comments they flagged as unnecessary (in `notifier.py` and `clipboard.py`) were
removed. Ruff is configured where ruff actually reads it: `[tool.ruff]` and `[tool.ruff.lint]` in
`pyproject.toml`. v0.1.3's rules lived in a `[ruff]` section of `setup.cfg`, which ruff has never
read, so `ruff check` had been running its default rule set. Modernisation followed:
`typing.Dict`/`List`/`Optional` → builtin generics and `X | None` across `schema.py`, `bus.py`,
`heuristics.py`, `renamer.py`, `clipboard.py` and `build_artifacts.py`.

### Dependencies re-sorted by what is actually required

Three required dependencies — `click`, `platformdirs`, `cryptography` — and the command line works
with those and nothing else, which the `minimal-install` CI job proves. `pyperclip` moved out of the
required set into a `clipboard` extra; folder features do not need it. New extras: `clipboard`,
`watch`, `tray`, `notify`, `keyring`, `desktop` (an aggregate), `bundle`, `dev`. The `vision` extra
(`pytesseract`, `opencv-python`) was dropped — no code in `aegis/` has ever imported either.

### Smaller changes

- `aegis/core/utils.py` gains `human_size`. An intermediate revision of `aegis large` formatted
  every row as `{n / 1024**2:.1f} MB`, so a folder of documents printed as rows of `0.0 MB` — a
  listing sorted by a number it would not show you. Introduced and fixed inside this revival; v0.1.3
  had no `large`.
- `AppConfig.ollama_model` added, defaulted in `defaults.json`.
- `.gitignore`: tool caches, and — more importantly — `*.sqlite`, `*.salt`, `actions.jsonl` and
  `pending-plan.json`, so a developer cannot commit a real vault or action journal.
- `.github/workflows/ci.yml`: Python matrix 3.10/3.11 → 3.10/3.12, lint scope widened from `ruff
  check .` to `ruff check aegis tests examples scripts`, type checking narrowed from `mypy aegis
  tests` to `mypy aegis`.

## Removed

- **`SAFETY.md`** (root) and **`docs/hardening.md`**. Both described the XOR fallback as a
  protection tier. `docs/hardening.md` additionally documented an `AEGIS_DISABLE_LOGGING` variable,
  file logging under `~/Aegis/Reports/logs/`, an `--archive-days` flag, read-only quarantine
  *folders*, and an outbound-address check that aborts on non-local hosts — none of which existed
  anywhere in the code (F14, each verified by grep). `docs/SAFETY.md` replaces both as the single
  threat-model document; `SECURITY.md` covers reporting.
- **`ActionExecutor.organize_directory` and `ActionExecutor.archive_old_files`** — unconditional
  bulk moves with no plan, journal or undo. Replaced by `preview_organize` / `preview_archive_old` /
  `apply_last_plan`.
- **`ClipboardVault._xor_key`**, both XOR branches, and the `preview` column.
- **`setup.cfg`** — a stale `version = 0.1.0` against `pyproject.toml`'s `0.1.3`, a second `[mypy]`
  section conflicting with the one in `pyproject.toml`, a `[flake8]` section for a linter the
  project does not use, and a `[ruff]` section ruff never reads. Everything real moved into
  `pyproject.toml`.
- **`requirements-optional.txt`**, with its references in `.github/workflows/release.yml`,
  `CONTRIBUTING.md` and `docs/packaging.md`. Extras belong in `pyproject.toml`, where `pip install
  -e ".[desktop]"` resolves them. This file *did* exist at v0.1.3 — see the corrections below.
- **`examples/media/README.md`**, a directory whose only content was a README for a demo GIF that
  was gitignored and never recorded.
- **Tests whose subjects no longer exist**: `test_actions.py` (tested `organize_directory`),
  `test_quarantine.py`, `test_watchers.py`, `test_watchers_e2e.py` (superseded by `test_executor.py`
  and `test_summarizer_and_watchers.py`), and `test_conflict_markers.py` (folded into
  `test_repo_hygiene.py` with a corrected pattern — the old one tested for a bare row of `=`, which
  flags any Markdown heading underline).

## Verification

Run 2026-09-02 on Linux, CPython 3.11.15, from `/root/revival/Aegis-OS-Agent`, with `XDG_DATA_HOME`
and `XDG_CONFIG_HOME` set to fresh temporary directories. Tool versions: pytest 9.0.3, ruff 0.15.11,
mypy 1.20.2.

```
$ pytest -q
165 passed in 58.54s

$ ruff check aegis tests examples scripts
All checks passed!

$ mypy aegis
Success: no issues found in 38 source files

$ python examples/demo.py
… exit code 0
Nothing outside /tmp/aegis-demo-9j5exg9j was touched.
```

The demo exercised, in order: an 11-file scratch Downloads folder; a plan that moved nothing;
`apply` moving 8 files as batch `3325317b`; `history` listing that batch as reversible; `undo`
restoring all 8 to their original paths; an archive containing `../../autorun.sh` being quarantined
and then un-quarantined by `aegis undo`; a GitHub token refused by the vault while an ordinary note
was stored (vault count 1); and `delete everything` answered with "I don't understand". Checked by
hand against scratch directories:

```
$ python -m aegis --help
exit 0 — lists apply, do, dump-config, duplicates, find, headless, history,
large, palette, plan, report, run, setup, status, undo
```

on a machine where `python -c "import tkinter"` raises `ModuleNotFoundError`.

```
$ aegis --config <scratch> plan downloads
3 change(s), 1.5 KB. Nothing has been changed yet.
$ aegis --config <scratch> apply --yes
Applied 3 change(s). Batch 2a611f30.
$ aegis --config <scratch> history
2a611f30  2026-09-02T03:43:16+00:00  3 changes (move) — … [reversible]
$ aegis --config <scratch> undo
Undid 3 change(s) from batch 2a611f30.
```

All three files were verified back at their original paths.

Targeted behavioural checks:

- Vault, cross-thread: `store()` from a second thread succeeds. The same call at v0.1.3 raised
  `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`.
- Vault, secret exclusion: a GitHub-token-shaped string is refused and `count()` stays at 0.
- Summariser against a local non-streaming stub: the request body contains `"stream": false`, and an
  `AKIA…` key in the input does **not** appear in the prompt sent to the model.
- Parser: `delete everything` → `unknown` (0.0); `clean up my desktop please` → `preview_organize`
  folder=desktop (0.95); `orgnize downloads` → `preview_organize` folder=downloads (0.93); `shwo
  history` → `show_history` (0.85); `make me a sandwich` → `unknown` with no suggestions.

For comparison, the same commands at base commit `cc2f885`, in `git worktree add /tmp/ag-head HEAD`:

```
$ pytest -q                     17 passed in 2.25s
$ ruff check aegis tests        All checks passed!
$ mypy aegis                    Success: no issues found in 32 source files
$ python -m aegis --help        ModuleNotFoundError: No module named 'tkinter'
```

The two clean results there are a property of the configuration, not the code: re-running with the
ruleset `setup.cfg` intended gives **111 ruff errors**, and deleting the `disable_error_code` line
gives **10 mypy errors in 3 files**. Both are zero in the current tree under configurations that are
actually read.

## Not verified

Stated as gaps, not as passes.

- **Every Tk widget.** This machine has no tkinter. `aegis/ui/palette.py`, `aegis/ui/settings.py`,
  `aegis/ui/system.py` and the `_run_tk` branch of `aegis/ui/first_run.py` have never been executed
  — that includes the palette window, the wizard's graphical path, and the destructive-command
  confirmation dialog, whose *decision logic* is tested in `aegis/ui/palette_model.py` but whose
  *dialog* has never been rendered.
- **The tray icon and the global hotkey.** `pystray`, `pynput` and `Pillow` are not installed, and
  `TrayController.start` / `HotkeyManager.start` swallow the ImportError and log at INFO, so their
  real behaviour is untested. Hotkey normalisation (`_normalise_hotkey`) has never been handed to
  `pynput`.
- **Ollama against a live daemon.** All summariser testing used a local `http.server` stub
  reproducing the documented request/response shapes. No `ollama serve` was contacted, no model
  pulled, and the network is unavailable (PyPI returns 403 through this environment's proxy).
- **The PyInstaller build.** `pyinstaller` is not installed and cannot be installed here.
  `aegis.spec` and `scripts/build_artifacts.py` were reviewed as text; `python
  scripts/build_artifacts.py` has not been run on any platform, and the release workflow has not
  been exercised.
- **Windows and macOS.** Everything ran on Linux. Unverified there: the `os.startfile` branch of
  `open_path`; the `win10toast` / `pync` notification backends; `hdiutil` DMG creation; whether
  `ALTER TABLE … DROP COLUMN` behaves identically on the SQLite builds those platforms ship; and
  whether the 0600/0700 chmods in the vault mean anything on NTFS.
- **Real clipboard capture.** `pyperclip` is not installed, so `ClipboardWatcher.start()` returns
  immediately with a warning. Clipboard paths were driven by calling `process_value` and publishing
  events directly.
- **The CI workflow itself.** `.github/workflows/ci.yml` has not run. It was written against the
  commands verified locally above, but no GitHub Actions job has executed it.

## Corrections to the release changelog

`CHANGELOG.md`'s `[0.2.0]` entry is accurate about the shape of the work. Three details are
imprecise, and the engineering record should not inherit them.

1. **PBKDF2 iterations.** The entry lists "claimed PBKDF2 at 390,000 iterations" among documentation
   claims that were "not true". The claim was true: `vault.py` called `hashlib.pbkdf2_hmac("sha256",
   …, salt, 390000, dklen=32)` and `docs/hardening.md` said 390k. What was untrue is the framing —
   that a PBKDF2-derived key feeding a repeating-key XOR constitutes encryption. The move to 600,000
   is a routine refresh, not the correction of a false claim.
2. **`SchedulerService`.** The entry says it "was calling `archive_old_files`, a method that no
   longer existed". At v0.1.3 that method existed and worked; it would only have become a missing
   symbol *after* this revival removed it. The real v0.1.3 defect is that the job ran immediately on
   startup and moved files with no preview, journal or undo — verified by a Desktop emptied two
   seconds after `aegis headless`.
3. **`requirements-optional.txt`.** The entry reasons that the file "does not exist, so the release
   workflow had never produced an artifact". The file was tracked at v0.1.3, and the release
   workflow step that installed it would have resolved. It does not exist *now* because this revival
   deleted it and consolidated extras into `pyproject.toml`, removing the workflow line in the same
   change. Whether the release workflow ever produced an artifact is unverified either way — see
   "Not verified".
