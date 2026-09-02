"""Everything the command palette decides, with no Tk import.

Split out so it can be unit tested on a machine with no display — which is the
case in CI, in containers, and in this project's own development environment.
:mod:`aegis.ui.palette` is widgets and wiring only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.intents import COMMANDS, Intent, parse

#: What the palette lists before anything is typed. One example phrase per
#: command, in the order a new user is most likely to want them.
SUGGESTED_ORDER = [
    "preview_organize",
    "apply_organize",
    "undo_last",
    "show_history",
    "archive_old",
    "large_downloads",
    "find_duplicates",
    "find_in_vault",
    "summarize_clipboard",
    "show_clipboard",
    "pause_watchers",
    "resume_watchers",
    "vault_status",
    "wipe_vault",
    "help",
]


@dataclass(frozen=True)
class Suggestion:
    phrase: str
    summary: str
    destructive: bool

    def label(self) -> str:
        marker = "  ⚠ asks first" if self.destructive else ""
        return f"{self.phrase}  —  {self.summary}{marker}"


def default_suggestions() -> list[Suggestion]:
    out: list[Suggestion] = []
    for name in SUGGESTED_ORDER:
        command = COMMANDS.get(name)
        if command is None:  # pragma: no cover - guards a rename
            continue
        out.append(Suggestion(command.phrases[0], command.summary, command.destructive))
    return out


def filter_suggestions(query: str) -> list[Suggestion]:
    """Live filter as the user types. Substring first, then the parser's guess."""
    cleaned = query.strip().lower()
    everything = default_suggestions()
    if not cleaned:
        return everything

    matches = [
        s for s in everything
        if cleaned in s.phrase.lower() or cleaned in s.summary.lower()
    ]
    if matches:
        return matches

    intent = parse(cleaned)
    if intent.is_understood:
        command = COMMANDS[intent.name]
        return [Suggestion(command.phrases[0], command.summary, command.destructive)]
    return []


def needs_confirmation(intent: Intent) -> bool:
    """Whether running *intent* should ask first.

    Destructive commands typed into a palette are one keystroke from happening.
    The previous palette dispatched "wipe vault" immediately.
    """
    return intent.is_destructive


def confirmation_text(intent: Intent) -> str:
    command = COMMANDS.get(intent.name)
    summary = command.summary if command else intent.name
    if intent.name == "wipe_vault":
        return (
            "Delete all saved clipboard history?\n\n"
            "This cannot be undone — the vault has no journal."
        )
    if intent.name == "undo_last":
        return "Reverse the most recent batch of changes?"
    return f"{summary}?\n\nThis changes files. Every change is journalled and can be undone."


def render_result(result: Any) -> str:
    """Turn whatever an intent handler returned into text for the results pane."""
    if result is None:
        return "Done."
    if hasattr(result, "render"):          # a Plan
        return result.render(limit=20)
    if hasattr(result, "describe"):        # an ExecutionReport or UndoReport
        return result.describe()
    if isinstance(result, list):
        if not result:
            return "Nothing to show."
        return "\n".join(str(item) for item in result)
    return str(result)


__all__ = [
    "Suggestion",
    "default_suggestions",
    "filter_suggestions",
    "needs_confirmation",
    "confirmation_text",
    "render_result",
]
