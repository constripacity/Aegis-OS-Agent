from __future__ import annotations

from aegis.core.actions import ActionExecutor
from aegis.core.bus import EventBus
from aegis.core.intents import IntentRouter
from aegis.core.notifier import Notifier


class DummyNotifier(Notifier):
    def notify(self, message: str, title: str = "Aegis", level: str = "info") -> None:  # pragma: no cover - simple override
        self.last = (message, level)


def test_intent_parsing(app_config) -> None:
    bus = EventBus()
    notifier = DummyNotifier()
    executor = ActionExecutor(bus, notifier, app_config)
    router = IntentRouter(bus, executor, app_config)

    intent = router.parse("summarize clipboard now")
    assert intent.name == "summarize_clipboard"
    assert intent.confidence > 0.5

    pause_intent = router.parse("please pause watchers for 15 minutes")
    assert pause_intent.name == "pause_watchers"
    assert pause_intent.params["minutes"] == 15

