"""Simple event bus for the Aegis agent."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from threading import RLock
from typing import Callable, DefaultDict, Iterable, Protocol

LOGGER = logging.getLogger(__name__)


class Event(Protocol):
    """Marker protocol for events."""

    @property
    def name(self) -> str:
        """Return the event name."""


Callback = Callable[[Event], None]


@dataclass(slots=True)
class ClipboardEvent:
    """Event emitted when clipboard content changes."""

    content: str

    @property
    def name(self) -> str:
        return "clipboard"


@dataclass(slots=True)
class FileSystemEvent:
    """Event emitted when filesystem watcher observes a change."""

    path: str
    event_type: str
    label: str

    @property
    def name(self) -> str:
        return "filesystem"


@dataclass(slots=True)
class NotificationEvent:
    """Event emitted when a notification should be displayed."""

    message: str
    level: str = "info"

    @property
    def name(self) -> str:
        return "notification"


class EventBus:
    """A lightweight thread-safe pub/sub bus."""

    def __init__(self) -> None:
        self._subscribers: DefaultDict[str, list[Callback]] = defaultdict(list)
        self._lock = RLock()

    def subscribe(self, event_name: str, callback: Callback) -> None:
        """Subscribe to a named event."""

        with self._lock:
            LOGGER.debug("Subscribing %s to %s", callback, event_name)
            self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callback) -> None:
        """Unsubscribe from an event."""

        with self._lock:
            if event_name in self._subscribers:
                LOGGER.debug("Unsubscribing %s from %s", callback, event_name)
                self._subscribers[event_name] = [
                    cb for cb in self._subscribers[event_name] if cb != callback
                ]

    def publish(self, event: Event) -> None:
        """Publish an event to subscribers."""

        callbacks: Iterable[Callback]
        with self._lock:
            callbacks = list(self._subscribers.get(event.name, []))
        for callback in callbacks:
            try:
                callback(event)
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.exception("Error handling event %s in %s: %s", event, callback, exc)


__all__ = [
    "ClipboardEvent",
    "FileSystemEvent",
    "NotificationEvent",
    "EventBus",
]

