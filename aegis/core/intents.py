"""Turn a typed command into a structured intent — or into an honest "I don't know".

The previous parser had a defect worth stating plainly: **every unrecognised
input fell through to ``summarize_clipboard``** at confidence 0.2. Typing
"delete everything" summarised your clipboard. Typing "wipe the vault now"
summarised your clipboard. It also matched by comparing the *whole input string*
against each keyword with ``SequenceMatcher``, so "organize desktop" scored 1.0
while "clean up my desktop please" scored about 0.5 and matched nothing.

The parser here:

* matches on **phrases contained in the input**, not whole-string similarity;
* extracts real parameters (a search query, a number of minutes, a folder);
* returns an explicit ``unknown`` intent with suggestions when nothing matches,
  because doing the wrong thing confidently is worse than doing nothing;
* never produces a shell command. An intent is a name plus validated parameters,
  and the dispatcher maps names to Python functions. Free text never reaches a
  shell, and neither does anything a language model produces.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from ..config.schema import AppConfig
from .bus import ClipboardEvent, EventBus, NotificationEvent

if TYPE_CHECKING:  # pragma: no cover
    from .actions import ActionExecutor

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Intent:
    """A validated request. ``name`` is always one of :data:`COMMANDS`."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    suggestions: tuple[str, ...] = ()

    @property
    def is_understood(self) -> bool:
        return self.name != "unknown"

    @property
    def is_destructive(self) -> bool:
        return COMMANDS[self.name].destructive if self.name in COMMANDS else False


@dataclass(frozen=True)
class Command:
    """One thing Aegis can be asked to do."""

    name: str
    summary: str
    phrases: tuple[str, ...]
    #: Whether running this changes files or deletes data. Destructive commands
    #: always produce a plan the user must approve; they never run straight off
    #: a typed phrase.
    destructive: bool = False
    extract: Callable[[str], dict[str, Any]] | None = None


def _extract_query(text: str) -> dict[str, Any]:
    """Pull the search term out of 'find X in my clipboard' style input."""
    cleaned = re.sub(
        r"^\s*(?:please\s+)?(?:find|search(?:\s+for)?|look\s+up|lookup)\s+", "", text, flags=re.I
    )
    cleaned = re.sub(
        r"\s+(?:in|from)\s+(?:my\s+)?(?:the\s+)?(?:clipboard|vault|history)\s*$", "", cleaned,
        flags=re.I,
    )
    return {"query": cleaned.strip().strip("\"'")}


def _extract_minutes(text: str) -> dict[str, Any]:
    match = re.search(r"(\d+)\s*(m|min|mins|minute|minutes|h|hr|hour|hours)?\b", text, re.I)
    if not match:
        return {"minutes": 30}
    value = int(match.group(1))
    unit = (match.group(2) or "m").lower()
    minutes = value * 60 if unit.startswith("h") else value
    return {"minutes": max(1, min(minutes, 24 * 60))}


def _extract_days(text: str) -> dict[str, Any]:
    match = re.search(r"(\d+)\s*(?:d|day|days|w|week|weeks|month|months)?\b", text, re.I)
    if not match:
        return {"days": 30}
    value = int(match.group(1))
    word = match.group(0).lower()
    if "week" in word or re.search(r"\d+\s*w\b", word):
        value *= 7
    elif "month" in word:
        value *= 30
    return {"days": max(1, min(value, 3650))}


def _extract_folder(text: str) -> dict[str, Any]:
    lowered = text.lower()
    if "download" in lowered:
        return {"folder": "downloads"}
    if "desktop" in lowered:
        return {"folder": "desktop"}
    return {}


#: The complete command surface. Anything not here cannot be produced by the
#: parser, which is what keeps free text from reaching an executor it should not.
COMMANDS: dict[str, Command] = {
    cmd.name: cmd
    for cmd in [
        Command(
            "preview_organize",
            "Show what tidying a folder would change, without changing anything",
            (
                "preview cleanup", "preview organize", "what would you clean",
                "dry run", "plan cleanup", "plan organize", "show cleanup",
                "organize", "organise", "clean up", "cleanup", "tidy",
            ),
            extract=_extract_folder,
        ),
        Command(
            "apply_organize",
            "Apply the tidying plan you were just shown",
            ("apply plan", "apply cleanup", "do it", "confirm cleanup", "yes organize"),
            destructive=True,
            extract=_extract_folder,
        ),
        Command(
            "undo_last",
            "Reverse the most recent batch of changes",
            ("undo", "undo last", "revert", "put it back", "undo last action"),
            destructive=True,
        ),
        Command(
            "show_history",
            "List what Aegis has changed and what can still be undone",
            ("history", "what did you do", "show history", "recent changes", "activity"),
        ),
        Command(
            "archive_old",
            "Preview archiving files older than a number of days",
            ("archive old", "archive files older", "clean old files", "archive screenshots"),
            extract=_extract_days,
        ),
        Command(
            "find_in_vault",
            "Search saved clipboard history",
            ("find", "search", "look up", "lookup", "search clipboard"),
            extract=_extract_query,
        ),
        Command(
            "summarize_clipboard",
            "Summarise what is currently on the clipboard",
            ("summarize", "summarise", "tldr", "tl;dr", "sum up clipboard"),
        ),
        Command(
            "show_clipboard",
            "Show what is currently on the clipboard",
            ("show clipboard", "what is on my clipboard", "clipboard"),
        ),
        Command(
            "pause_watchers",
            "Stop watching folders and the clipboard for a while",
            ("pause", "snooze", "stop watching", "pause watchers"),
            extract=_extract_minutes,
        ),
        Command(
            "resume_watchers",
            "Start watching again",
            ("resume", "start watching", "unpause", "resume watchers"),
        ),
        Command(
            "large_downloads",
            "List the biggest files in Downloads",
            ("large downloads", "big files", "biggest downloads", "show large files"),
        ),
        Command(
            "find_duplicates",
            "Find files with identical contents",
            ("duplicates", "find duplicates", "duplicate files", "dupes"),
        ),
        Command(
            "wipe_vault",
            "Delete all saved clipboard history",
            (
                "wipe vault", "wipe the vault", "clear the vault", "empty the vault",
                "clear clipboard history", "empty vault", "forget clipboard",
                "delete clipboard history",
            ),
            destructive=True,
        ),
        Command(
            "vault_status",
            "Show whether the clipboard vault is running and how much it holds",
            ("vault status", "is the vault on", "vault"),  # bare "vault" is generic
        ),
        Command(
            "help",
            "List everything Aegis can do",
            ("help", "commands", "what can you do", "?"),
        ),
    ]
}

#: Minimum similarity for the fuzzy pass, which only runs when no phrase is
#: contained in the input. High enough that a typo matches and a new idea does not.
FUZZY_THRESHOLD = 0.80

#: Below this similarity a command is not a plausible thing the user meant, so
#: it is not offered as a suggestion. Without a floor, ``do "make me a
#: sandwich"`` answered "Did you mean: summarize_clipboard, resume_watchers,
#: pause_watchers?" — three commands whose only claim was sharing the letters
#: in "me" and "a". A wrong suggestion is worse than none: it sends the reader
#: to read the help for a command that was never going to help.
#:
#: The value sits in the gap the ratios actually leave. Measured against this
#: command table, a typo of a real phrase scores high ("shwo history" → 0.92,
#: "orgnize downloads" → 0.93) while unrelated text tops out much lower
#: ("make me a sandwich" → 0.46, "delete everything" → 0.50, "buy milk" →
#: 0.47). Anything from 0.55 to 0.79 separates them; 0.65 is the middle of
#: that gap, and stays below FUZZY_THRESHOLD so a near-miss that did not
#: auto-match is still offered as a suggestion.
SUGGEST_THRESHOLD = 0.65

#: Bare nouns that are also substrings of longer, more specific requests.
#: "vault" must not win against "wipe the vault", and "clipboard" must not win
#: against "find X in the clipboard", so these only match a whole input.
GENERIC_PHRASES = frozenset(
    {"vault", "clipboard", "organize", "organise", "find", "search",
     "pause", "resume", "undo", "help", "?", "duplicates", "cleanup", "tidy"}
)


def parse(text: str) -> Intent:
    """Parse *text* into an :class:`Intent`. Never guesses silently."""
    cleaned = (text or "").strip()
    if not cleaned:
        return Intent("unknown", {"input": ""}, 0.0, suggestions=_top_suggestions(""))

    lowered = cleaned.lower()

    # Pass 1: contained phrases, scored so that specificity and position beat
    # raw length. "clean up my desktop please" contains "clean up", so it
    # matches; whole-string similarity (what the old parser used) would not.
    best: tuple[int, Command, str] | None = None
    for command in COMMANDS.values():
        for phrase in command.phrases:
            score = _phrase_score(lowered, phrase)
            if score is None:
                continue
            if best is None or score > best[0]:
                best = (score, command, phrase)
    if best is not None:
        _, command, phrase = best
        confidence = 0.95 if len(phrase.split()) > 1 else 0.85
        return Intent(command.name, _params_for(command, cleaned), confidence)

    # Pass 2: fuzzy, to catch typos rather than new intentions. Each phrase is
    # compared against every leading word-window of the input, so a misspelled
    # first word ("orgnize downloads") is matched on the word that was
    # misspelled instead of on the words that happened to survive.
    #
    # Destructive commands are deliberately excluded from this pass. "open
    # vault" scored 0.80 against "wipe vault" — one letter apart — and the
    # parser resolved a request to *open* the clipboard history into a request
    # to *delete* it. Typo tolerance is a convenience; it is not worth buying
    # at the price of silently destroying data, so anything destructive must be
    # asked for in words the table actually contains.
    words = lowered.split()
    windows = [" ".join(words[:n]) for n in range(1, min(len(words), 5) + 1)]
    scored: list[tuple[float, Command]] = []
    for command in COMMANDS.values():
        if command.destructive:
            continue
        similarity = max(
            SequenceMatcher(None, window, phrase).ratio()
            for phrase in command.phrases
            for window in windows
        )
        scored.append((similarity, command))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if scored and scored[0][0] >= FUZZY_THRESHOLD:
        similarity, command = scored[0]
        return Intent(command.name, _params_for(command, cleaned), round(similarity, 2))

    plausible = tuple(
        command.name for similarity, command in scored[:3] if similarity >= SUGGEST_THRESHOLD
    )
    return Intent("unknown", {"input": cleaned}, 0.0, suggestions=plausible)


def _phrase_score(lowered: str, phrase: str) -> int | None:
    """How strongly *phrase* matches *lowered*, or ``None`` for no match.

    Position and specificity are weighted above raw length, because the longest
    substring is frequently the wrong answer: "find my notes in the clipboard"
    contains "clipboard" (9 chars) and "find" (4), and it means find.
    """
    if phrase in GENERIC_PHRASES:
        # A bare noun or verb only counts as the whole request, or as the word
        # the request opens with. "find" leading means find; "clipboard" buried
        # in the middle of a sentence does not mean show-clipboard.
        stripped = lowered.strip(" ?.!")
        if stripped == phrase:
            return 160 + len(phrase)
        if stripped.startswith(phrase + " "):
            return 100 + len(phrase)
        return None
    if phrase not in lowered:
        return None
    score = len(phrase) + 10 * len(phrase.split())
    if lowered.startswith(phrase):
        score += 60
    return score


def _params_for(command: Command, text: str) -> dict[str, Any]:
    return dict(command.extract(text)) if command.extract else {}


def _top_suggestions(_text: str) -> tuple[str, ...]:
    return ("help", "preview_organize", "show_history")


def describe(name: str) -> str:
    """The one-line description of a command, for confirmation prompts."""
    command = COMMANDS.get(name)
    return command.summary if command else name


def help_text() -> str:
    lines = ["Aegis understands these commands:", ""]
    for command in COMMANDS.values():
        if command.name == "help":
            continue
        marker = " (asks first)" if command.destructive else ""
        lines.append(f"  {command.name:<20} {command.summary}{marker}")
        lines.append(f"  {'':<20} try: \"{command.phrases[0]}\"")
    lines.append("")
    lines.append("Anything that changes files shows you a plan before it does anything.")
    return "\n".join(lines)


class IntentRouter:
    """Maps parsed intents to executor methods. No intent reaches a shell."""

    def __init__(self, bus: EventBus, executor: ActionExecutor, config: AppConfig) -> None:
        self.bus = bus
        self.executor = executor
        self.config = config
        self._handlers: dict[str, Callable[[Intent], Any]] = {
            "preview_organize": lambda i: self.executor.preview_organize(
                i.params.get("folder", "downloads")
            ),
            "apply_organize": lambda i: self.executor.apply_last_plan(),
            "undo_last": lambda i: self.executor.undo_last(),
            "show_history": lambda i: self.executor.history(),
            "archive_old": lambda i: self.executor.preview_archive_old(
                int(i.params.get("days", 30))
            ),
            "find_in_vault": lambda i: self.executor.search_vault(str(i.params.get("query", ""))),
            "summarize_clipboard": lambda i: self.executor.summarize_clipboard(),
            "show_clipboard": lambda i: self.executor.clipboard_snapshot(),
            "pause_watchers": lambda i: self.executor.pause_watchers(
                int(i.params.get("minutes", 30))
            ),
            "resume_watchers": lambda i: self.executor.resume_watchers(),
            "large_downloads": lambda i: self.executor.large_files("downloads"),
            "find_duplicates": lambda i: self.executor.find_duplicates(),
            "wipe_vault": lambda i: self.executor.wipe_vault(),
            "vault_status": lambda i: self.executor.vault_status(),
            "help": lambda i: help_text(),
        }
        self.bus.subscribe("clipboard", self._on_clipboard)

    def parse(self, text: str) -> Intent:
        return parse(text)

    def dispatch(self, intent: Intent) -> Any:
        if not intent.is_understood:
            hint = ", ".join(intent.suggestions[:3])
            message = f"I don't understand {intent.params.get('input', '')!r}."
            if hint:
                message += f" Did you mean: {hint}? Type 'help' for the full list."
            self.bus.publish(NotificationEvent(message, level="warning"))
            return message

        handler = self._handlers.get(intent.name)
        if handler is None:  # pragma: no cover - COMMANDS and handlers are kept in sync
            LOGGER.error("No handler registered for intent %s", intent.name)
            return None
        LOGGER.debug("Dispatching %s with %s", intent.name, intent.params)
        return handler(intent)

    def run(self, text: str) -> Any:
        return self.dispatch(self.parse(text))

    def _on_clipboard(self, event: ClipboardEvent) -> None:
        self.executor.record_clipboard(event.content)


__all__ = ["Intent", "IntentRouter", "COMMANDS", "parse", "describe", "help_text"]
