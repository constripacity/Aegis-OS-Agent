"""Heuristic classifiers for clipboard and filesystem content."""

from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path

from .heuristics import clean_tracking_url, detect_code_language

URL_REGEX = re.compile(r"https?://[\w\-./?=&%]+", re.IGNORECASE)


@dataclass
class Classification:
    label: str
    details: dict[str, str]


def classify_text(text: str) -> Classification:
    """Classify clipboard text heuristically."""

    if URL_REGEX.search(text):
        return Classification(label="url", details={"clean": clean_tracking_url(text)})
    lang = detect_code_language(text)
    if lang != "text":
        return Classification(label="code", details={"language": lang})
    if len(text.split()) <= 6:
        return Classification(label="short_text", details={})
    return Classification(label="text", details={})


def classify_file(path: Path) -> Classification:
    mime, _ = mimetypes.guess_type(path.name)
    if path.suffix.lower() in {".zip", ".rar", ".7z"}:
        return Classification(label="archive", details={"mime": mime or "application/zip"})
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        return Classification(label="image", details={"mime": mime or "image/png"})
    if path.suffix.lower() in {".pdf"}:
        return Classification(label="document", details={"mime": mime or "application/pdf"})
    return Classification(label="file", details={"mime": mime or "application/octet-stream"})


__all__ = ["Classification", "classify_text", "classify_file", "detect_code_language"]

