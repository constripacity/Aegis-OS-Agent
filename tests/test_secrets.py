"""Secret exclusion. A false negative here writes a credential to disk."""
from __future__ import annotations

import pytest

from aegis.core.secrets import classify_secret, redact, shannon_entropy


@pytest.mark.parametrize(
    "content,kind",
    [
        ("ghp_" "1234567890abcdefghijklmnopqrstuvwxyzAB", "github_token"),
        ("AKIAIOSFODNN7EXAMPLE", "aws_access_key"),
        ("sk-" "live-abcdefghijklmnopqrstuvwxyz012345", "openai_key"),
        ("xoxb-" "123456789012-abcdefghijklmnop", "slack_token"),
        ("-----BEGIN RSA PRIVATE " "KEY-----\nMIIE", "private_key"),
        ("password = supersecret123", "assigned_secret"),
        ("api_key: abcdef123456", "assigned_secret"),
        ("postgres://user:pa55w0rd@db.internal:5432/app", "connection_string"),
        ("4111 1111 1111 1111", "card_number"),
    ],
)
def test_credentials_are_recognised(content, kind):
    verdict = classify_secret(content)
    assert verdict, content
    assert verdict.kind == kind


@pytest.mark.parametrize(
    "content",
    [
        "correct horse battery staple",
        "Meeting on Thursday at 10am with Dana about the forecast.",
        "def hello():\n    return 'world'",
        "https://example.com/some/normal/page?q=1",
        "a3f5c9e1b7d2486092c4ffab13de77015c9a2b4e",  # a git SHA
        "/Users/me/Documents/report-final-v2.docx",
        "C:\\Users\\me\\file.txt",
        "screenshot-2026-09-02.png",
        "my_variable_name_2024",
        "4111 1111 1111 1112",  # fails the Luhn check
    ],
)
def test_ordinary_content_is_not_flagged(content):
    assert not classify_secret(content), content


def test_verdict_reason_never_contains_the_secret():
    verdict = classify_secret("ghp_" "1234567890abcdefghijklmnopqrstuvwxyzAB")
    assert "ghp_" not in (verdict.reason or "")


def test_redaction_keeps_surrounding_code_readable():
    source = (
        "import requests\n"
        "API_KEY = 'sk-" "live-abcdefghijklmnopqrstuvwxyz012345'\n"
        "def fetch(url):\n"
        "    return requests.get(url)\n"
    )
    cleaned = redact(source)
    assert "sk-live" not in cleaned
    assert "[redacted]" in cleaned
    assert "import requests" in cleaned
    assert "def fetch(url):" in cleaned


def test_redaction_is_idempotent():
    once = redact("token = ghp_" "1234567890abcdefghijklmnopqrstuvwxyzAB")
    assert redact(once) == once


def test_entropy_separates_random_from_language():
    assert shannon_entropy("aaaaaaaaaa") < 1.0
    assert shannon_entropy("the quick brown fox") < 4.5
    assert shannon_entropy("Xk9mPq2Zw7Lr4Vn8Bt6Yc3Hd5Jf1Gs0") > 4.0
