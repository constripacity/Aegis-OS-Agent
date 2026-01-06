"""Intent parsing and routing."""



import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Dict

from ..config.schema import AppConfig
from .bus import EventBus, ClipboardEvent, NotificationEvent
from .summarizer import Summarizer

LOGGER = logging.getLogger(__name__)


def _fuzzy_score(text: str, keyword: str) -> float:
    return SequenceMatcher(None, text, keyword).ratio() * 100


@dataclass
class Intent:
    """Structured representation of a requested action."""

    name: str
    params: dict[str, object]
    confidence: float = 1.0


class IntentRouter:
    """Route intents to action executor functions."""

    def __init__(self, bus: EventBus, executor: "ActionExecutor", config: AppConfig) -> None:
        self.bus = bus
        self.executor = executor
        self.config = config
        self.summarizer = Summarizer(config)
        self._handlers: Dict[str, Callable[[Intent], None]] = {
            "summarize_clipboard": self._handle_summarize_clipboard,
            "organize_desktop_now": lambda intent: self.executor.organize_directory("desktop"),
            "organize_downloads_now": lambda intent: self.executor.organize_directory("downloads"),
            "rename_last_file": lambda intent: self.executor.rename_last_file(intent.params),
            "find_in_vault": lambda intent: self.executor.search_vault(intent.params.get("query", "")),
            "pause_watchers": lambda intent: self.executor.pause_watchers(int(intent.params.get("minutes", 30))),
            "wipe_vault": lambda intent: self.executor.wipe_vault(),
        }
        self.bus.subscribe("clipboard", self._on_clipboard)

    def _handle_summarize_clipboard(self, intent: Intent) -> None:
        latest = self.executor.clipboard_snapshot()
        if not latest:
            self.bus.publish(NotificationEvent("Clipboard is empty"))
            return
        summary = self.summarizer.summarize_text(latest)
        self.bus.publish(NotificationEvent(summary, level="success"))

    def dispatch(self, intent: Intent) -> None:
        handler = self._handlers.get(intent.name)
        if handler:
            LOGGER.debug("Dispatching intent %s", intent)
            handler(intent)
        else:  # pragma: no cover
            LOGGER.warning("No handler for intent %s", intent.name)
            self.bus.publish(NotificationEvent(f"Unknown intent: {intent.name}", level="warning"))

    def _on_clipboard(self, event: ClipboardEvent) -> None:
        LOGGER.debug("Received clipboard event: %s", event.content[:50])
        self.executor.record_clipboard(event.content)

    def parse(self, text: str) -> Intent:
        text_lower = text.lower().strip()
        heuristics = {
            "summarize_clipboard": ["summarize", "tl;dr"],
            "organize_desktop_now": ["clean desktop", "organize desktop"],
            "organize_downloads_now": ["clean downloads", "organize downloads"],
            "rename_last_file": ["rename", "retitle"],
            "find_in_vault": ["find", "search"],
            "pause_watchers": ["pause", "snooze"],
            "wipe_vault": ["wipe vault", "clear history"],
        }
        for intent_name, keywords in list(heuristics.items()):
            for keyword in keywords:
                score = _fuzzy_score(text_lower, keyword)
                if score >= 80:
                    LOGGER.debug("Matched intent %s with score %s", intent_name, score)
                    return Intent(name=intent_name, params={}, confidence=score / 100)

        match = re.search(r"pause .*?(\d+)", text_lower)
        if match:
            minutes = int(match.group(1))
            return Intent(name="pause_watchers", params={"minutes": minutes}, confidence=0.8)

        if text_lower.startswith("summarize"):
            return Intent(name="summarize_clipboard", params={}, confidence=0.6)

        return Intent(name="summarize_clipboard", params={}, confidence=0.2)


__all__ = ["Intent", "IntentRouter"]

