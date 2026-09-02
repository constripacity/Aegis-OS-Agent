# A ten-minute walkthrough

Every command below was run against the real CLI, and every console block is
pasted from its output. Nothing here is aspirational: `tests/test_repo_hygiene.py`
fails the build if a command in this file is not registered, if a phrase in an
`aegis do "…"` example does not parse, or if a link here points at a file that
is not in the tree.

Aegis never touches a file until you have seen the plan and said yes.

## 0. Try it without pointing it at anything you care about

```bash
python examples/demo.py
```

This builds a realistic messy Downloads folder in a temporary directory, then
walks the whole model — plan, apply, history, undo, and a quarantined archive —
printing what happens at each step. The directory is deleted when the script
exits; pass `--keep` to leave it behind. Your own files are never involved.

When you want to point Aegis at real folders, run the wizard:

```bash
aegis setup
```

It asks which folders Aegis may touch and writes them to a config file. Nothing
outside those roots can ever be planned, previewed, or executed — see
[`../docs/SAFETY.md`](../docs/SAFETY.md). To keep a throwaway configuration
somewhere else, put it in a file and pass `--config`:

```bash
aegis --config ~/aegis-scratch.json plan downloads
```

## 1. See what it would do

```bash
aegis plan downloads
```

```
Organize /tmp/wt/Downloads
==========================

By kind  (3)
      move  album.mp3
            → /tmp/wt/Downloads/Audio/album.mp3
      move  meeting-notes.md
            → /tmp/wt/Downloads/Documents/meeting-notes.md
      move  quarterly-report.pdf
            → /tmp/wt/Downloads/Documents/quarterly-report.pdf

Installers  (1)
      move  Setup-1.4.2.dmg
            → /tmp/wt/Downloads/Installers/Setup-1.4.2.dmg

Old files  (2)
      move  data-export.csv
            → /tmp/wt/Downloads/Archive/2026-07/data-export.csv
      move  invoice-2026-03.pdf
            → /tmp/wt/Downloads/Archive/2026-05/invoice-2026-03.pdf

Screenshots  (1)
      move  Screenshot 2026-06-14 at 09.22.png
            → /tmp/wt/Downloads/Screenshots/2026-08/Screenshot 2026-06-14 at 09.22.png

Left alone (3):
    .DS_Store: operating system file
    half-a-movie.mkv.crdownload: looks like an in-progress download
    just-downloaded.zip: no rule matched

7 change(s), 4.8 KB. Nothing has been changed yet.

Apply it with:  aegis apply
```

`plan` writes nothing, so it is safe to run repeatedly against anything. The
"Left alone" section matters as much as the moves: a tool that silently ignores
three files is one you cannot audit.

Add `--json` to get the same plan as data, and `--recursive` to look in
subfolders.

## 2. Run it

```bash
aegis apply
```

`apply` re-reads the plan you were just shown, prints it again, and asks. Add
`--yes` in a script. Aegis re-checks every path immediately before touching it —
a plan that was correct thirty seconds ago is not assumed to be correct now —
then records the batch to an append-only journal with a hash of each file moved.

```
Applied 7 change(s). Batch e3ca3c3f.
  Undo with:  aegis undo e3ca3c3f
```

## 3. Change your mind

```bash
aegis history
```

```
e3ca3c3f  2026-09-02T02:37:14+00:00  7 changes (move) — Organize /tmp/wt/Downloads · screenshot, filed by month [reversible]

Undo any of them with:  aegis undo <id>
```

```bash
aegis undo e3ca3c3f
```

```
Undid 7 change(s) from batch e3ca3c3f.
  ✓ Screenshot 2026-06-14 at 09.22.png → /tmp/wt/Downloads/Screenshot 2026-06-14 at 09.22.png
  ✓ Setup-1.4.2.dmg → /tmp/wt/Downloads/Setup-1.4.2.dmg
  ✓ album.mp3 → /tmp/wt/Downloads/album.mp3
  ✓ data-export.csv → /tmp/wt/Downloads/data-export.csv
  ✓ invoice-2026-03.pdf → /tmp/wt/Downloads/invoice-2026-03.pdf
  ✓ meeting-notes.md → /tmp/wt/Downloads/meeting-notes.md
  ✓ quarterly-report.pdf → /tmp/wt/Downloads/quarterly-report.pdf
```

`undo` verifies each file still hashes to what the journal recorded before
putting it back. If you edited a file after the move, Aegis refuses to restore
that one and says which, rather than silently overwriting your work.

## 4. The rest of the CLI

```bash
aegis large downloads --limit 5   # biggest files, so you can find the 4 GB one
aegis duplicates downloads        # identical contents, grouped, deletes nothing
aegis status                      # what is watched, and whether the vault is open
aegis report --html               # JSON + HTML summary under ~/Aegis/Reports/
aegis dump-config                 # the effective configuration, as JSON
```

## 5. Plain English

`do` runs the same parser the command palette uses. It resolves your text to a
command from a fixed table and refuses anything it cannot match — free text
never reaches an executor.

```bash
aegis do "tidy up downloads"
aegis do "what did you do"
aegis do "archive old"
aegis do "find invoice"
```

When it does not know, it says so rather than guessing:

```
$ aegis do "make me a sandwich"
I don't understand 'make me a sandwich'.
Run 'aegis do help' for the full list.
```

A near-miss is different from nonsense: `shwo history` and `orgnize downloads`
both resolve, because they are typos of phrases in the table. "Make me a
sandwich" is not, so no suggestion is offered — an unusable suggestion is worse
than none.

`aegis do help` prints the whole command surface. Destructive intents (`apply
plan`, `undo`) always confirm before acting.

## 6. Clipboard history (optional, off by default)

The vault stays disabled until you turn it on, and it needs a passphrase:

```bash
export AEGIS_VAULT_PASSPHRASE="a passphrase you chose"
aegis do "find invoice"
```

Two things worth knowing before you enable it:

- Anything that looks like a credential — API keys, tokens, card numbers,
  private keys, generated passwords — is **never stored**, not stored-encrypted.
  See `aegis/core/secrets.py`.
- If `cryptography` is not installed, the vault does not open. There is no
  weaker fallback cipher. Aegis would rather have no clipboard history than
  pretend to protect it.

## 7. Run it continuously

```bash
aegis run          # tray icon, global hotkey, watchers
aegis headless     # watchers only, for a login item or a service
```

Both keep running until you quit from the tray or press Ctrl-C. Watchers only
ever *propose*: they post a notification saying a plan is ready. Nothing is
applied without you.

If the desktop UI cannot load — no Tk, no display — `aegis run` says so and
exits rather than half-starting. `aegis headless` works regardless.

## What is not exercised here

`aegis run` and `aegis palette` need a desktop session, so the tray icon, the
global hotkey, and the palette window are not covered by the test suite;
`aegis/ui/palette_model.py` holds the logic and is tested, the widgets are not.
The Ollama summariser is tested against a stub, not a live daemon.
