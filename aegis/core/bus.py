"""Simple event bus for the Aegis agent."""



import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from threading import RLock
from typing import Any, Literal, Protocol, overload

LOGGER = logging.getLogger(__name__)


class Event(Protocol):
    """Marker protocol for events."""

    @property
    def name(self) -> str:
        """Return the event name."""


#: A handler for one specific event type. The bus routes by name, and each
#: name carries exactly one event class, so handlers are naturally
#: heterogeneous; the overloads on ``subscribe`` recover per-name type safety.
Callback = Callable[[Any], None]


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
        self._subscribers: defaultdict[str, list[Callback]] = defaultdict(list)
        self._lock = RLock()

    # v0.1.3 disabled mypy's `arg-type` code project-wide with a comment saying
    # the bus "could not be typed". These overloads type it: a handler
    # registered for "clipboard" is checked as taking a ClipboardEvent.
    @overload
    def subscribe(
        self, event_name: Literal["clipboard"], callback: Callable[["ClipboardEvent"], None]
    ) -> None: ...

    @overload
    def subscribe(
        self, event_name: Literal["filesystem"], callback: Callable[["FileSystemEvent"], None]
    ) -> None: ...

    @overload
    def subscribe(
        self,
        event_name: Literal["notification"],
        callback: Callable[["NotificationEvent"], None],
    ) -> None: ...

    @overload
    def subscribe(self, event_name: str, callback: Callback) -> None: ...

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

