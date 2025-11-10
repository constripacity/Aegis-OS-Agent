"""Intent parsing and routing."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Dict, TYPE_CHECKING

from ..config.schema import AppConfig
from .bus import EventBus, ClipboardEvent, NotificationEvent
from .summarizer import Summarizer

if TYPE_CHECKING:  # pragma: no cover - circular import guard
    from .actions import ActionExecutor

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
            "organize_desktop_now": self._handle_organize_desktop,
            "organize_downloads_now": self._handle_organize_downloads,
            "rename_last_file": self._handle_rename_last_file,
            "find_in_vault": self._handle_find_in_vault,
            "pause_watchers": self._handle_pause_watchers,
            "wipe_vault": self._handle_wipe_vault,
        }
        self.bus.subscribe("clipboard", self._handle_clipboard_event)

    def _handle_summarize_clipboard(self, intent: Intent) -> None:
        latest = self.executor.clipboard_snapshot()
        if not latest:
            self.bus.publish(NotificationEvent("Clipboard is empty"))
            return
        summary = self.summarizer.summarize_text(latest)
        self.bus.publish(NotificationEvent(summary, level="success"))

    def _handle_organize_desktop(self, _intent: Intent) -> None:
        self.executor.organize_directory("desktop")

    def _handle_organize_downloads(self, _intent: Intent) -> None:
        self.executor.organize_directory("downloads")

    def _handle_rename_last_file(self, intent: Intent) -> None:
        self.executor.rename_last_file(intent.params)

    def _handle_find_in_vault(self, intent: Intent) -> None:
        query = str(intent.params.get("query", "")) if intent.params else ""
        results = self.executor.search_vault(query)
        if not results:
            self.bus.publish(NotificationEvent("No vault entries match your search", level="info"))
            return
        top = results[0][:200].replace("\n", " ")
        message = f"Found {len(results)} entries. Latest: {top}" if len(results) > 1 else top
        self.bus.publish(NotificationEvent(message, level="info"))

    def _handle_pause_watchers(self, intent: Intent) -> None:
        raw_minutes = intent.params.get("minutes") if intent.params else None
        minutes = self._coerce_minutes(raw_minutes)
        self.executor.pause_watchers(minutes)

    def _handle_wipe_vault(self, _intent: Intent) -> None:
        self.executor.wipe_vault()

    @staticmethod
    def _coerce_minutes(value: object | None) -> int:
        if isinstance(value, (int, float)):
            return max(1, int(value))
        if isinstance(value, str):
            try:
                return max(1, int(value))
            except ValueError:
                return 30
        if value is None:
            return 30
        return 30

    def dispatch(self, intent: Intent) -> None:
        handler = self._handlers.get(intent.name)
        if handler:
            LOGGER.debug("Dispatching intent %s", intent)
            handler(intent)
        else:  # pragma: no cover
            LOGGER.warning("No handler for intent %s", intent.name)
            self.bus.publish(NotificationEvent(f"Unknown intent: {intent.name}", level="warning"))

    def _handle_clipboard_event(self, event: object) -> None:
        if not isinstance(event, ClipboardEvent):
            return
        self._on_clipboard(event)

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
        for intent_name, keywords in heuristics.items():
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

