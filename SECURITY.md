# Security policy

## Reporting a vulnerability

Open a [GitHub security advisory](https://github.com/constripacity/Aegis-OS-Agent/security/advisories/new)
for anything that lets Aegis read, move, or delete something the operator did
not authorise, or that exposes clipboard contents. Please do not open a public
issue first.

Include the OS, the Python version, the command or phrase you ran, and what
Aegis did instead of what you expected. A failing test is the most useful
possible report.

There is no bounty programme and no guaranteed response time. This is a
single-maintainer project; a realistic expectation is a first reply within a
week or two.

## What is in scope

Aegis moves files and can store clipboard history. The interesting failures are:

- **Escaping the safe roots.** Any plan that touches a path outside the
  configured roots (`aegis/core/safety.py`) is a bug, including via symlink,
  `..`, or a race between planning and execution.
- **Executing anything.** Aegis must never run, open, or shell out to a file it
  discovered. If you find a path that does, that is the highest-severity report.
- **Vault contents at rest.** Recovering clipboard entries or search terms from
  `vault.sqlite` without the passphrase.
- **Undo corrupting data.** `undo` restoring the wrong bytes to a path, or
  overwriting a file the operator changed after the batch ran.
- **Secret leakage.** A credential reaching the vault, a log, a report, or a
  notification despite the exclusion rules in `aegis/core/secrets.py`.

## What is out of scope

- An attacker who already has your user account. Aegis holds no privileges you
  do not; it is not a sandbox and does not claim to be one.
- The optional Ollama integration sending prompt text to the local endpoint you
  configured. That is what enabling it does.
- Unsigned release binaries triggering Gatekeeper or SmartScreen. See
  [`docs/packaging.md`](docs/packaging.md) — they are unsigned, and the docs say so.

## The threat model

[`docs/SAFETY.md`](docs/SAFETY.md) is the single authoritative description of
what Aegis protects, what it does not, and where the boundaries are. It is the
document to read before trusting this with a folder.
