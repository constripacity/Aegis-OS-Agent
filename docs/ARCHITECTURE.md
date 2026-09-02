# Architecture

```
aegis/
├─ core/
│  ├─ safety.py       SafeRoots — the one place a path is checked before disk I/O
│  ├─ plan.py         Plan / PlannedAction / execute — the authorisation gate
│  ├─ organizer.py    Declarative rules → a Plan. Pure function of metadata.
│  ├─ journal.py      Append-only JSONL of every change, plus undo
│  ├─ quarantine.py   Bounded archive inspection and reversible isolation
│  ├─ vault.py        Encrypted clipboard store with a keyed blind index
│  ├─ secrets.py      What must never be recorded
│  ├─ intents.py      Phrase → structured Intent (a fixed command table)
│  ├─ actions.py      ActionExecutor — the only object that owns all of the above
│  ├─ summarizer.py   Ollama (optional) + a deterministic extractive fallback
│  ├─ scheduler.py    Daily job that proposes, never acts
│  └─ bus.py          Typed pub/sub between watchers and the executor
├─ watchers/
│  ├─ filesystem.py   watchdog with a polling fallback and settle detection
│  └─ clipboard.py    Polling clipboard reader
├─ ui/
│  ├─ palette_model.py  Every palette decision — no Tk import, unit tested
│  ├─ palette.py        Widgets and wiring only
│  ├─ settings.py, first_run.py, system.py
└─ main.py           click CLI. Imports the UI lazily.
```

## The one-way flow

```
watcher / CLI / palette
        │
        ▼
   Intent  (a name from a fixed table + validated params — never a command)
        │
        ▼
ActionExecutor.preview_*  ─────▶  Plan   (pure; reads metadata, writes nothing)
        │                           │
        │                    plan.render()  ──▶  a human reads it
        │                           │
        │                    plan.authorize()   ← the only way past this line
        ▼                           ▼
                             plan.execute() ──▶ SafeRoots re-check ──▶ move
                                                        │
                                                        ▼
                                                 ActionJournal (JSONL, fsync'd)
                                                        │
                                                        ▼
                                                  journal.undo_batch()
```

Two invariants make this hold:

1. **`execute()` is the only function in the codebase that moves a user file**,
   and it raises on an unauthorised plan.
2. **`SafeRoots` is the only place a path becomes an I/O operation.** Sources and
   destinations are resolved before containment is checked.

## Why the UI is split in two

`palette_model.py` and `gui`-adjacent logic contain no `import tkinter`. Every
decision about what to show, what to filter, and what to confirm lives there and
is unit tested on a machine with no display. That split exists because the CI and
development environments for this project frequently have no `tkinter` at all —
and because `main.py` importing the UI at module scope once made the *entire CLI*
fail on such machines.

## Threading

- The clipboard and folder watchers each own a daemon thread and publish to the
  event bus.
- `EventBus.publish` calls subscribers synchronously on the publishing thread, so
  the executor's handlers run on the watcher thread. Everything they touch is
  therefore thread-safe by construction: the vault holds a single connection
  opened with `check_same_thread=False` behind an `RLock`.
- The Tk palette runs its own `mainloop` on its own thread; widgets are only
  touched from there.

`tests/test_vault.py::test_store_works_from_another_thread` exists because this
was broken: the vault's connection was created on the main thread and used from
the watcher, so every real clipboard capture raised `sqlite3.ProgrammingError`
and the event bus swallowed it.

## Adding a command

1. Add a `Command` to `COMMANDS` in `core/intents.py` with its phrases, a
   one-line summary, and `destructive=True` if it changes anything.
2. Register a handler in `IntentRouter._handlers`.
3. If it changes files, it **must** return a `Plan`. Do not add a handler that
   moves something directly; that is the design this project exists to fix.
4. Add a `@cli.command()` in `main.py` if it deserves a flag surface.
5. Add tests: one for the phrasings that should reach it, and one asserting a
   nearby phrase does *not*.

## Adding an organiser rule

Rules in `core/organizer.py` are `(name, match, destination, reason)` where
`match` and `destination` are pure functions of `FileFacts`. A rule that needs to
read file *contents* does not belong there — planning must stay cheap and
side-effect free.

Every rule needs a case in `tests/test_plan_and_journal.py`, including one
asserting that organising twice does not reshuffle: the second run of a naive
organiser is what buries a file three levels deep.
