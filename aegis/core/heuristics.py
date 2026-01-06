"""Deterministic heuristics supporting offline operation."""



import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .utils import hash_text, sanitize_filename

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "mc_eid",
    "msclkid",
}


def summarize_text(text: str, max_chars: int = 200) -> str:
    """Return a compact summary using simple sentence scoring."""

    sentences = [segment.strip() for segment in _split_sentences(text) if segment.strip()]
    if not sentences:
        return text.strip()[:max_chars]
    scored = sorted(((score_sentence(sentence), sentence) for sentence in sentences), reverse=True)
    top = [sentence for _, sentence in scored[:3]]
    summary = " ".join(top)
    return summary[:max_chars]


def score_sentence(sentence: str) -> float:
    words = [word.strip(".,;:!?") for word in sentence.split() if word.strip()]
    if not words:
        return 0.0
    unique = len(set(words))
    return unique / len(words)


def _split_sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+|\n+", text)


def clean_tracking_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        return url.strip()
    filtered = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    new_query = urlencode(filtered, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


LANGUAGE_HINTS = {
    "python": [r"def ", r"class ", r"import ", r"self"],
    "javascript": [r"function ", r"=>", r"const ", r"let "],
    "typescript": [r"interface ", r"type ", r"import ", r": string"],
    "c": [r"#include", r"int main"],
    "bash": [r"#!/bin/bash", r"#!/usr/bin/env bash", r"echo "],
}


def detect_code_language(text: str) -> str:
    lowered = text.lower()
    for language, patterns in list(LANGUAGE_HINTS.items()):
        if any(pattern.lower() in lowered for pattern in patterns):
            return language
    if lowered.strip().startswith("<html"):
        return "html"
    return "text"


SECRET_PATTERN = re.compile(r"^[A-Za-z0-9+/=_-]{32,}$")


def prepare_code_snippet(content: str) -> str:
    """Normalise code snippets and redact obvious secrets."""

    cleaned_lines = [line.rstrip() for line in content.splitlines()]
    redacted_lines = []
    for line in cleaned_lines:
        tokens = line.split()
        redacted_tokens = ["[redacted]" if SECRET_PATTERN.match(token) else token for token in tokens]
        redacted_lines.append(" ".join(redacted_tokens))
    return "\n".join(redacted_lines).strip()


def generate_filename(path: Path, keywords: Sequence[str]) -> str:
    """Produce a deterministic filename derived from keywords and the original name."""

    base_tokens = _tokenize_keywords(list(keywords) + [path.stem])
    timestamp = datetime.utcnow().strftime("%Y%m%d")
    important = base_tokens[:4] or ["file"]
    base = "_".join(sanitize_filename(token) for token in important if token)
    digest = hash_text(path.name, length=6)
    return f"{base}_{timestamp}_{digest}{path.suffix.lower()}"


def _tokenize_keywords(keywords: Iterable[str]) -> list[str]:
    tokens: list[str] = []
    for keyword in keywords:
        for piece in re.split(r"[^A-Za-z0-9]+", keyword):
            if piece:
                lower = piece.lower()
                if lower not in tokens:
                    tokens.append(lower)
    return tokens


__all__ = [
    "summarize_text",
    "clean_tracking_url",
    "detect_code_language",
    "prepare_code_snippet",
    "generate_filename",
]

