# Contributing to Aegis OS Agent

First off, thank you for your interest in improving Aegis! This document outlines the workflow for proposing changes.

## Code of Conduct

Be respectful and collaborative. Follow the [Python Community Code of Conduct](https://www.python.org/psf/codeofconduct/).

## Getting Started

1. Fork the repository and create a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-optional.txt  # optional extras
   ```
3. Run the test suite to ensure everything works locally:
   ```bash
   pytest
   ```

## Branching & Commits

- Create a feature branch from `main` using the pattern `feature/<topic>` or `fix/<issue>`.
- Commit messages should follow the imperative style: `Add vault wipe command`.
- Keep commits focused. Separate formatting-only changes from functional ones when possible.

## Development Workflow

1. Implement your changes with type hints, docstrings, and logging.
2. Update or add tests under `tests/`.
3. Run the quality gates:
   ```bash
   ruff check .
   mypy aegis tests
   pytest
   ```
4. Update documentation if behavior changes (README, SAFETY, demo walkthrough, etc.).
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

