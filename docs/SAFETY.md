# Threat model and boundaries

Aegis moves files on your behalf and reads your clipboard. That is a lot of
trust for a program to ask for. This document states exactly what it will and
will not do, so the claim can be checked rather than believed.

## What Aegis is trusted with

| Resource | Access | Bounded by |
| --- | --- | --- |
| Desktop and Downloads | read, move, rename | `SafeRoots` allowlist |
| Archive / Reports / Snippets / Quarantine | read, write | `SafeRoots` allowlist |
| The system clipboard | read | opt-in, credential-excluded |
| Everything else on the filesystem | **none** | refused at `safety.py` |
| The network | one optional request to localhost Ollama | off by default |

`aegis status` prints the exact folders in force on your machine.

## Hard guarantees

These are enforced in code and covered by tests. A change that breaks one is a
release blocker, not a regression.

1. **Nothing is deleted.** No code path in this repository calls `unlink`,
   `rmtree` or `remove` on a user file except (a) after a verified cross-device
   copy, where the copy's hash has already matched, and (b) `aegis` wiping its
   own vault when you ask it to.
2. **Nothing is overwritten.** `SafeRoots.check_destination` refuses an existing
   path; `unique_destination` finds a free name and the plan records that it did.
3. **Nothing moves without an authorised plan.** `plan.execute()` raises
   `PermissionError` on a plan that was never `authorize()`d.
4. **Nothing happens outside the allowed roots.** Every source and destination
   is resolved (`..` collapsed, symlinks followed) *before* containment is
   checked, so a crafted relative path cannot escape.
5. **Symlinks are never moved.** Moving a link either breaks it or silently
   operates on a file somewhere else. Both are refused.
6. **Every change is reversible.** Move, rename and quarantine all write a
   journal record with the content hash; `undo` verifies that hash before
   restoring, and refuses if the file changed.

## Resource bounds

Hostile input tries to exhaust the machine inspecting it. Archive inspection is
capped in `aegis/core/quarantine.py`:

| Bound | Value | Guards against |
| --- | --- | --- |
| `MAX_MEMBERS` | 5,000 | central-directory floods |
| `MAX_TOTAL_UNCOMPRESSED` | 512 MB | decompression bombs |
| `MAX_RATIO` | 200:1 | per-entry bomb ratio |
| indicator list | 40 entries | report and memory blowup |

Archives are **never extracted**. Only the central directory is read, so a
traversal path can never be written to disk in the first place.

## The clipboard

Opt-in, off by default, and exclusion-first.

**Never stored, in any form:** private keys, AWS/GitHub/Slack/Google/Stripe/OpenAI
key formats, JWTs, connection strings containing a password, lines assigning a
password or key, one-time codes, card numbers passing a Luhn check, long
high-entropy blobs, and generated-password-shaped strings. See
`aegis/core/secrets.py`; the list is a plain table you can read and extend.

**Everything else** is encrypted with Fernet (AES-128-CBC + HMAC-SHA256), keyed
by PBKDF2-HMAC-SHA256 at 600,000 iterations over a 32-byte random salt. The
derived material is split: half encrypts, half keys the blind index, so an index
hit cannot confirm a guess about the ciphertext.

**There is no fallback cipher.** Without `cryptography`, the vault refuses to
start. v0.1.3 silently fell back to repeating-key XOR and logged it as a
"lightweight backend"; that is now impossible.

**Known limits, stated plainly:**

- The passphrase lives in your OS keyring or an environment variable. An
  attacker who is already running as you can read both. This protects the vault
  at rest — a stolen backup, a shared disk, a synced folder — not against local
  code execution.
- The blind index leaks which entries share tokens, and how many distinct tokens
  an entry has. It does not leak the tokens.
- Detection is heuristic. A password with no digits and no symbols
  (`correcthorsebatterystaple`) is indistinguishable from a sentence, and will
  be stored. Encryption is the second line of defence for exactly this case.

## Local language models

Ollama is optional, off by default, and constrained on every side:

- **Nothing it returns can move a file.** Only the rules engine produces plans,
  and only you authorise them. The model is used for summarising text.
- **Input is delimited and marked as data**, and secrets are redacted before it
  is sent.
- **Output is sanitised**: control characters stripped, whitespace collapsed,
  length capped at 400 characters, and used only as display text.
- **It is never given a shell, a path, or a file handle.**

Prompt injection therefore has one available outcome: a misleading summary
appears in a notification. That is a real annoyance and not a route to your
files.

## Command parsing

`aegis do "<phrase>"` produces an `Intent` — a name from a fixed table plus
validated parameters. It cannot produce a command string, a path, or a shell
invocation. An unrecognised phrase returns `unknown` with suggestions; it never
falls through to *some other command*, which is what the previous parser did.

## What Aegis does not defend against

Being honest about the edges:

- **A compromised account.** Anything running as you can read the vault
  passphrase from the keyring and the journal from disk.
- **Malware.** Archive inspection is a handful of structural heuristics. It
  catches a booby-trapped ZIP; it is not a scanner and does not claim to be.
- **Filesystem races.** Actions are re-validated immediately before execution,
  but a sufficiently determined local attacker can win a TOCTOU race between the
  check and the move.
- **Data loss from outside Aegis.** Undo reverses Aegis's own changes. It is not
  a backup.

## Reporting a vulnerability

Please open a private security advisory rather than a public issue. A flaw in
the boundary checks or the vault is a real risk to anyone running this.
