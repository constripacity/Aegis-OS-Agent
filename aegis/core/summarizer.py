"""Summarization helpers with Ollama fallback."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import urllib.request

from ..config.schema import AppConfig
from .heuristics import summarize_text

LOGGER = logging.getLogger(__name__)


@dataclass
class SummaryResult:
    text: str
    source: str


class Summarizer:
    """Summarize text using Ollama or heuristics."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def summarize_text(self, text: str) -> str:
        if self.config.use_ollama:
            try:
                return self._summarize_with_ollama(text)
            except Exception as exc:  # pragma: no cover - fallback path
                LOGGER.warning("Ollama summarization failed: %s", exc)
        return summarize_text(text)

    def _summarize_with_ollama(self, text: str) -> str:
        payload = json.dumps(
            {
                "model": "llama3",
                "prompt": (
                    "You are a summarizer. Provide a neutral summary in 200 characters or less.\n"
                    f"Text: {text}"
                ),
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url=self.config.ollama_url.rstrip("/") + "/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            summary = data.get("response") or data.get("summary") or ""
            return summary.strip()[:200]

__all__ = ["Summarizer", "SummaryResult"]

