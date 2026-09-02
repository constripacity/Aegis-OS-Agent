# Contributing to Aegis OS Agent

First off, thank you for your interest in improving Aegis! This document outlines the workflow for proposing changes.

## Code of Conduct

Be respectful and collaborative. Follow the [Python Community Code of Conduct](https://www.python.org/psf/codeofconduct/).

## Getting Started

1. Fork the repository and create a virtual environment.
2. Install the project and its development tools:
   ```bash
   pip install -e ".[dev]"          # tests, ruff, mypy
   pip install -e ".[dev,desktop]"  # ...plus clipboard, tray, hotkey, notifications
   ```
   Extras are declared in `pyproject.toml`. There is no `requirements-optional.txt`.
   The desktop window needs `tkinter`, which ships with CPython but is packaged
   separately on Debian and Ubuntu: `sudo apt install python3-tk`.
3. Run the test suite to ensure everything works locally:
   ```bash
   pytest
   ```
   All tests must pass without a desktop session; the ones that need Tk skip
   themselves.

## Branching & Commits

- Create a feature branch from `main` using the pattern `feature/<topic>` or `fix/<issue>`.
- Commit messages should follow the imperative style: `Add vault wipe command`.
- Keep commits focused. Separate formatting-only changes from functional ones when possible.

## Development Workflow

1. Implement your changes with type hints, docstrings, and logging.
2. Update or add tests under `tests/`.
3. Run the quality gates:
   ```bash
   ruff check aegis tests
   mypy aegis
   pytest
   ```
   All three must be clean. Do not add `# type: ignore` or `noqa` to get there —
   if a rule is genuinely wrong for this codebase, change the configuration in
   `pyproject.toml` in its own commit and say why.
4. Update documentation if behaviour changes (`README.md`, `docs/SAFETY.md`,
   `examples/demo_walkthrough.md`). `tests/test_repo_hygiene.py` checks that the
   docs do not describe commands or files that no longer exist, so a stale doc
   fails the build.
5. Submit a pull request describing the motivation, approach, and testing.

## Pull Request Checklist

- [ ] Tests pass locally.
- [ ] Added/updated unit tests.
- [ ] Updated documentation if needed.
- [ ] Ensured no secrets or personal data are committed.
- [ ] Confirmed offline-only behavior (no unexpected network calls).

## Issue Reporting

Include as much detail as possible:
- OS and Python version.
- Steps to reproduce.
- Expected vs. actual behavior.
- Relevant log snippets (redact sensitive data).

Thank you for helping make Aegis better for everyone!

