"""Recognise content that should never be recorded.

The most popular clipboard manager on macOS has 21k stars and **no encryption at
all**. It wins on trust by never capturing password-manager content in the first
place. That is the right instinct: "we encrypt everything we took from you" is a
weaker promise than "we never took it".

So Aegis excludes first and encrypts second. This module is the exclusion half.
It is deliberately conservative — a false positive costs one un-saved clipboard
entry, a false negative writes someone's production key to disk.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from re import Pattern

#: (name, pattern, human explanation). Order matters only for reporting.
SECRET_PATTERNS: list[tuple[str, Pattern[str], str]] = [
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "a private key block",
    ),
    (
        "aws_access_key",
        re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b"),
        "an AWS access key id",
    ),
    (
        "github_token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
        "a GitHub token",
    ),
    (
        "slack_token",
        re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
        "a Slack token",
    ),
    (
        "google_api_key",
        re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
        "a Google API key",
    ),
    (
        "openai_key",
        re.compile(r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9_\-]{20,}\b"),
        "an API key in the sk- format",
    ),
    (
        "stripe_key",
        re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}\b"),
        "a Stripe key",
    ),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"),
        "a JSON web token",
    ),
    (
        "connection_string",
        re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:[^\s:/@]+@[^\s/]+", re.IGNORECASE),
        "a URL containing a password",
    ),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(?:pass(?:wo?rd)?|passphrase|secret|api[_\-]?key|token|"
            r"auth|credential|private[_\-]?key)\b\s*[:=]\s*\S{6,}"
        ),
        "a line that assigns a password or key",
    ),
    (
        "otp_code",
        re.compile(r"(?i)\b(?:one[- ]time|verification|security)\s+code\b.{0,20}?\b\d{4,8}\b"),
        "a one-time verification code",
    ),
    (
        "card_number",
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        "something shaped like a payment card number",
    ),
]

#: Very high-entropy standalone blobs. Checked separately because the test is
#: statistical, not structural, and it needs a length floor to avoid firing on
#: ordinary base64-looking identifiers.
_OPAQUE_BLOB = re.compile(r"^[A-Za-z0-9+/=_\-]{40,}$")


@dataclass(frozen=True)
class SecretVerdict:
    """Whether content looks secret, and a description safe to log."""

    is_secret: bool
    kind: str | None = None
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.is_secret


def _luhn_ok(digits: str) -> bool:
    total, alternate = 0, False
    for char in reversed(digits):
        value = ord(char) - 48
        if alternate:
            value *= 2
            if value > 9:
                value -= 9
        total += value
        alternate = not alternate
    return total % 10 == 0


def shannon_entropy(text: str) -> float:
    """Bits per character. ~4.0+ suggests random rather than language."""
    if not text:
        return 0.0
    from collections import Counter
    from math import log2

    counts = Counter(text)
    length = len(text)
    return -sum((n / length) * log2(n / length) for n in counts.values())


def classify_secret(content: str) -> SecretVerdict:
    """Return a verdict for *content*. Never includes the content in the reason."""
    if not content or not content.strip():
        return SecretVerdict(False)

    stripped = content.strip()

    for name, pattern, description in SECRET_PATTERNS:
        match = pattern.search(content)
        if not match:
            continue
        if name == "card_number":
            digits = re.sub(r"\D", "", match.group(0))
            if not (13 <= len(digits) <= 19 and _luhn_ok(digits)):
                continue
        return SecretVerdict(True, name, f"looks like {description}")

    single_token = "\n" not in stripped and " " not in stripped

    # A long single token of base64/hex alphabet with no words in it is what an
    # API key or session token looks like. The length and entropy floors keep it
    # off git SHAs (40 hex chars, entropy ~4.0) and ordinary identifiers.
    if (
        single_token
        and len(stripped) >= 40
        and _OPAQUE_BLOB.match(stripped)
        and shannon_entropy(stripped) >= 4.2
    ):
        return SecretVerdict(True, "opaque_blob", "is a long high-entropy string with no words")

    # A generated password: no spaces, mixed character classes, high entropy.
    # Symbols are what distinguishes this from the base64 case above.
    if single_token and 16 <= len(stripped) <= 128 and _class_count(stripped) >= 3:
        if shannon_entropy(stripped) >= 3.8 and not _looks_like_a_path_or_url(stripped):
            return SecretVerdict(
                True, "generated_password", "looks like a randomly generated password"
            )

    return SecretVerdict(False)


def _class_count(text: str) -> int:
    """How many of {lower, upper, digit, symbol} appear in *text*."""
    return sum(
        (
            any(c.islower() for c in text),
            any(c.isupper() for c in text),
            any(c.isdigit() for c in text),
            any(not c.isalnum() for c in text),
        )
    )


def _looks_like_a_path_or_url(text: str) -> bool:
    """Filenames, paths and URLs also mix character classes; they are not secrets."""
    if "://" in text or text.startswith(("/", "~", ".", "\\")):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", text):
        return True
    # A dotted name with a short final segment is a filename or a hostname.
    return bool(re.match(r"^[\w.\-]+\.[A-Za-z]{2,6}$", text))


def redact(content: str, placeholder: str = "[redacted]") -> str:
    """Replace anything secret-shaped, keeping the surrounding text readable.

    Used before a snippet is written to disk or handed to a language model.
    """
    result = content
    for name, pattern, _ in SECRET_PATTERNS:
        if name == "card_number":
            def _card(match: re.Match[str]) -> str:
                digits = re.sub(r"\D", "", match.group(0))
                if 13 <= len(digits) <= 19 and _luhn_ok(digits):
                    return placeholder
                return match.group(0)

            result = pattern.sub(_card, result)
        elif name == "assigned_secret":
            result = pattern.sub(
                lambda m: re.split(r"[:=]", m.group(0), maxsplit=1)[0] + "= " + placeholder,
                result,
            )
        else:
            result = pattern.sub(placeholder, result)

    redacted_tokens = []
    for token in result.split(" "):
        if (
            len(token) >= 40
            and _OPAQUE_BLOB.match(token)
            and shannon_entropy(token) >= 4.2
        ):
            redacted_tokens.append(placeholder)
        else:
            redacted_tokens.append(token)
    return " ".join(redacted_tokens)


__all__ = ["SecretVerdict", "classify_secret", "redact", "shannon_entropy", "SECRET_PATTERNS"]
