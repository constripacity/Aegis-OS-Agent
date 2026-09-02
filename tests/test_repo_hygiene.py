"""Repository hygiene: no unresolved merge markers, no committed secrets."""
from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

#: A real conflict has an opening marker *and* a closing marker, both at the
#: start of a line, followed by a space or end-of-line. Testing for a bare row
#: of "=" (as the previous version did) flags any Markdown heading underline or
#: ASCII box, which is why this test failed on a perfectly good README.
OPEN_MARKER = re.compile(r"^<{7}(?: |$)", re.MULTILINE)
CLOSE_MARKER = re.compile(r"^>{7}(?: |$)", re.MULTILINE)

#: Patterns that must never appear in a tracked file.
SECRET_PATTERNS = [
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{20,}\b")),
]

#: Files whose whole point is to contain example credential *shapes*.
SECRET_ALLOWLIST = {
    Path("aegis/core/secrets.py"),
    Path("tests/test_secrets.py"),
    Path("tests/test_vault.py"),
    Path("tests/test_executor.py"),
    Path("examples/demo.py"),
    Path("tests/test_summarizer_and_watchers.py"),
    Path("docs/SAFETY.md"),
    Path("README.md"),
    Path("CHANGELOG.md"),
}

TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".cfg", ".json", ".yml", ".yaml", ".sh",
    ".ps1", ".html", ".css", ".spec", "",
}


def _tracked_files() -> Iterable[Path]:
    output = subprocess.check_output(["git", "ls-files"], text=True)
    for line in output.splitlines():
        line = line.strip()
        if line:
            yield Path(line)


def _text_files() -> Iterable[tuple[Path, str]]:
    for path in _tracked_files():
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            yield path, path.read_text(encoding="utf-8", errors="ignore")
        except OSError:  # pragma: no cover
            continue


def test_no_unresolved_merge_markers() -> None:
    offenders = [
        str(path)
        for path, contents in _text_files()
        if OPEN_MARKER.search(contents) and CLOSE_MARKER.search(contents)
    ]
    assert not offenders, f"merge markers in: {', '.join(offenders)}"


def test_no_committed_credentials() -> None:
    offenders: list[str] = []
    for path, contents in _text_files():
        if path in SECRET_ALLOWLIST:
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(contents):
                offenders.append(f"{path}: {label}")
    assert not offenders, "credentials in tracked files: " + "; ".join(offenders)


def test_no_env_files_are_tracked() -> None:
    tracked = {p.name for p in _tracked_files()}
    assert ".env" not in tracked
    assert not any(name.endswith(".bak") for name in tracked)


def test_gitignore_covers_the_obvious_hazards() -> None:
    ignored = Path(".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "__pycache__", ".venv", "*.bak", "dist/", "build/"):
        assert pattern in ignored, f"{pattern} is not in .gitignore"


# ---------------------------------------------------------------------------
# Documentation that describes things which do not exist
#
# Before this revision the repository shipped a root `SAFETY.md` promising "a
# lightweight XOR cipher fallback", a `docs/hardening.md` promising PBKDF2 at
# 390k iterations and an `AEGIS_DISABLE_LOGGING` variable, a walkthrough telling
# you to run `clean desktop` and `aegis headless --use-ollama`, and three files
# telling you to install `requirements-optional.txt`. None of it was true. The
# encryption claim in particular is the first thing a security-minded reader
# checks, so getting it wrong costs more than the words are worth.
#
# Prose cannot be tested, but the *checkable* parts of it can: the commands, the
# phrases, the file paths, and the links. These tests hold that line.
# ---------------------------------------------------------------------------
#: Documents that describe commands and phrases which deliberately do not work.
#:
#: `NEXT_20_COMMITS.md` proposes commands that do not exist yet — that is what a
#: roadmap is — and the revival records quote the exact broken invocations they
#: are reporting, such as `aegis do "open vault"` resolving to `wipe_vault`.
#: Holding an engineering record to "every command here must work" would force
#: it to stop naming the bug.
#:
#: Everything a user actually follows — README, CONTRIBUTING, docs/SAFETY.md,
#: the walkthrough — is still checked, and the vacuity guards below fail if that
#: coverage silently disappears.
ENGINEERING_RECORDS = {
    Path("docs/NEXT_20_COMMITS.md"),
    Path("docs/REVIVAL_AUDIT.md"),
    Path("docs/REVIVAL_CHANGELOG.md"),
    Path("CHANGELOG.md"),
}

FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`([^`\n]+)`")


def _markdown_files() -> Iterable[tuple[Path, str]]:
    """The documentation a user follows, excluding the engineering records."""
    for path, contents in _text_files():
        if path.suffix.lower() == ".md" and path not in ENGINEERING_RECORDS:
            yield path, contents


#: A fragment showing a placeholder rather than a real value.
PLACEHOLDER = re.compile(r"[<>\u2026]")

#: Text that marks the surrounding block as a *demonstration of refusal*. The
#: examples that show Aegis declining an instruction are the most important ones
#: in the documentation, and they necessarily contain phrases that do not parse.
REFUSAL = re.compile(r"don't understand|do not understand", re.IGNORECASE)


def _code_fragments(contents: str) -> Iterable[tuple[str, str]]:
    """Every shell-ish fragment in a document, paired with the block it came
    from: fenced blocks, line by line, plus inline code spans. Prose is
    deliberately excluded — "run aegis on your Downloads folder" is English, not
    a command line."""
    for block in FENCE.findall(contents):
        for line in block.splitlines():
            yield line, block
    for span in INLINE_CODE.findall(contents):
        yield span, span


AEGIS_INVOCATION = re.compile(r"^\s*(?:\$\s*)?aegis\s+(.*)$")
REQUIREMENTS_INSTALL = re.compile(r"pip install\s+(?:--\S+\s+)*-r\s+(\S+)")


def _registered_commands() -> set[str]:
    from aegis.main import cli

    return set(cli.commands)


def test_every_documented_subcommand_exists() -> None:
    commands = _registered_commands()
    offenders: list[str] = []
    checked = 0
    for path, contents in _markdown_files():
        for fragment, _block in _code_fragments(contents):
            match = AEGIS_INVOCATION.match(fragment)
            if not match:
                continue
            if PLACEHOLDER.search(fragment):
                continue
            words = [w for w in match.group(1).split() if not w.startswith("-")]
            # `aegis --help`, or a global option before the subcommand.
            if not words:
                continue
            # Skip the value of a global option: `aegis --config path plan`.
            head = words[0]
            if head not in commands and Path(head).suffix:
                words = words[1:]
                if not words:
                    continue
                head = words[0]
            checked += 1
            if head not in commands:
                offenders.append(f"{path}: 'aegis {head}' is not a command")
    assert not offenders, (
        "documented commands that do not exist: " + "; ".join(sorted(set(offenders)))
    )
    # A filter that quietly stops matching turns this into a test of nothing.
    assert checked >= 15, (
        f"only {checked} documented invocations found; the parser is probably broken"
    )


def test_every_documented_phrase_parses() -> None:
    """`aegis do "clean desktop"` was in the walkthrough for two releases. It has
    never been a phrase the parser knows."""
    from aegis.core.intents import parse

    offenders: list[str] = []
    checked = 0
    for path, contents in _markdown_files():
        for fragment, block in _code_fragments(contents):
            match = re.match(r'^\s*(?:\$\s*)?aegis\s+do\s+"([^"]+)"\s*$', fragment)
            if not match:
                continue
            phrase = match.group(1)
            if PLACEHOLDER.search(phrase) or REFUSAL.search(block):
                continue
            checked += 1
            if parse(phrase).name == "unknown":
                offenders.append(f"{path}: 'aegis do \"{phrase}\"' does not parse")
    assert not offenders, "documented phrases the parser rejects: " + "; ".join(offenders)
    assert checked >= 4, f"only {checked} documented phrases found; the filters are too broad"


def test_no_document_installs_a_requirements_file_that_is_missing() -> None:
    offenders: list[str] = []
    for path, contents in _markdown_files():
        for fragment, _block in _code_fragments(contents):
            for target in REQUIREMENTS_INSTALL.findall(fragment):
                if not Path(target).exists():
                    offenders.append(f"{path}: installs {target}, which is not in the tree")
    assert not offenders, "; ".join(offenders)


RELATIVE_LINK = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")


def test_every_relative_documentation_link_resolves() -> None:
    offenders: list[str] = []
    checked = 0
    for path, contents in _markdown_files():
        for target in RELATIVE_LINK.findall(contents):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            checked += 1
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            if not resolved.exists():
                offenders.append(f"{path} -> {target}")
    assert not offenders, "broken documentation links: " + "; ".join(offenders)
    assert checked >= 5, f"only {checked} relative links found; the pattern is probably wrong"
