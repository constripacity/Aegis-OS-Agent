"""Intent parsing.

The headline regression: the previous parser routed *every* unrecognised input
to ``summarize_clipboard`` at confidence 0.2. Typing "delete everything"
summarised your clipboard.
"""
from __future__ import annotations

import pytest

from aegis.core.intents import COMMANDS, help_text, parse


@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("organize desktop", "preview_organize"),
        ("clean up my desktop please", "preview_organize"),
        ("tidy my downloads", "preview_organize"),
        ("preview cleanup of downloads", "preview_organize"),
        ("do it", "apply_organize"),
        ("undo", "undo_last"),
        ("undo last action", "undo_last"),
        ("show me the history", "show_history"),
        ("what did you do", "show_history"),
        ("wipe the vault now", "wipe_vault"),
        ("clear clipboard history", "wipe_vault"),
        ("find postgres", "find_in_vault"),
        ("find my api notes in the clipboard", "find_in_vault"),
        ("pause for 45 minutes", "pause_watchers"),
        ("archive files older than 90 days", "archive_old"),
        ("duplicates", "find_duplicates"),
        ("large downloads", "large_downloads"),
        ("help", "help"),
        ("summarize", "summarize_clipboard"),
    ],
)
def test_realistic_phrasings_reach_the_right_command(phrase, expected):
    assert parse(phrase).name == expected, phrase


@pytest.mark.parametrize(
    "phrase", ["what is the weather", "delete everything", "make me a sandwich", ""]
)
def test_unknown_input_is_reported_as_unknown(phrase):
    """Regression: these all used to silently summarise the clipboard."""
    intent = parse(phrase)
    assert intent.name == "unknown"
    assert not intent.is_understood
    assert intent.confidence == 0.0


def test_unknown_input_says_so_without_guessing():
    """"what is the weather" is not a near-miss for anything Aegis does, so the
    honest answer is "I don't understand", not a shortlist assembled from
    whichever commands happened to share letters with it."""
    intent = parse("what is the weather")
    assert intent.name == "unknown"
    assert intent.suggestions == ()


def test_typos_still_match():
    assert parse("orgnize downloads").name == "preview_organize"
    assert parse("summarise").name == "summarize_clipboard"


@pytest.mark.parametrize(
    "phrase,key,value",
    [
        ("pause for 45 minutes", "minutes", 45),
        ("pause 2 hours", "minutes", 120),
        ("snooze", "minutes", 30),
        ("archive files older than 90 days", "days", 90),
        ("archive old files after 3 weeks", "days", 21),
    ],
)
def test_parameters_are_extracted(phrase, key, value):
    assert parse(phrase).params.get(key) == value


def test_pause_duration_is_clamped():
    assert parse("pause for 99999 minutes").params["minutes"] <= 24 * 60


@pytest.mark.parametrize(
    "phrase,query",
    [
        ("find postgres", "postgres"),
        ("search for the deploy key", "the deploy key"),
        ("find my api notes in the clipboard", "my api notes"),
    ],
)
def test_search_query_is_extracted(phrase, query):
    assert parse(phrase).params["query"] == query


def test_folder_is_extracted():
    assert parse("clean up my downloads").params["folder"] == "downloads"
    assert parse("organize desktop").params["folder"] == "desktop"


def test_destructive_commands_are_marked():
    assert parse("undo").is_destructive
    assert parse("wipe the vault").is_destructive
    assert not parse("show me the history").is_destructive
    assert not parse("organize desktop").is_destructive


def test_help_lists_every_command():
    text = help_text()
    for name in COMMANDS:
        if name == "help":
            continue
        assert name in text


def test_no_intent_ever_yields_a_shell_command():
    """An intent is a name plus validated parameters, never a command string."""
    for phrase in ("organize desktop; rm -rf /", "find $(whoami)", "undo && echo hi"):
        intent = parse(phrase)
        assert intent.name in COMMANDS or intent.name == "unknown"
        for value in intent.params.values():
            assert not isinstance(value, (list, tuple))


# -- palette presentation model ---------------------------------------------
def test_palette_suggestions_come_from_the_real_command_table():
    from aegis.ui.palette_model import default_suggestions

    suggestions = default_suggestions()
    assert suggestions
    phrases = {s.phrase for s in suggestions}
    for suggestion in suggestions:
        # Every listed phrase must actually parse to a real command; the old
        # hard-coded list had drifted out of date.
        assert parse(suggestion.phrase).is_understood, suggestion.phrase
    assert "wipe vault" in phrases


def test_palette_filters_as_you_type():
    from aegis.ui.palette_model import filter_suggestions

    assert len(filter_suggestions("")) > 5
    assert all("undo" in s.phrase or "undo" in s.summary.lower()
               for s in filter_suggestions("undo"))
    assert filter_suggestions("orgnize downloads")  # falls back to the parser
    assert filter_suggestions("zzzzz not a command") == []


def test_palette_asks_before_anything_destructive():
    from aegis.ui.palette_model import confirmation_text, needs_confirmation

    assert needs_confirmation(parse("wipe vault"))
    assert needs_confirmation(parse("undo"))
    assert not needs_confirmation(parse("show me the history"))
    assert "cannot be undone" in confirmation_text(parse("wipe vault"))


def test_palette_renders_every_result_shape():
    from aegis.core.plan import Plan
    from aegis.ui.palette_model import render_result

    assert render_result(None) == "Done."
    assert "Nothing to show" in render_result([])
    assert render_result(["a", "b"]) == "a\nb"
    assert "Nothing has been changed yet" in render_result(Plan(title="t")) or render_result(
        Plan(title="t")
    ).endswith("nothing to do.")


def test_nonsense_gets_no_suggestions_but_a_typo_does():
    """A suggestion the user cannot use is worse than none. The floor has to
    hold in both directions: silent on nonsense, helpful on a near-miss."""
    for nonsense in ("make me a sandwich", "buy milk", "delete everything", "book a flight"):
        intent = parse(nonsense)
        assert intent.name == "unknown", nonsense
        assert intent.suggestions == (), f"{nonsense} → {intent.suggestions}"

    for typo, expected in (
        ("shwo history", "show_history"),
        ("orgnize downloads", "preview_organize"),
    ):
        intent = parse(typo)
        assert intent.name == expected, f"{typo} → {intent.name}"


def test_a_destructive_command_is_never_reached_by_a_typo():
    """`open vault` scored 0.80 against `wipe vault` — one letter apart — so the
    parser turned a request to *open* the clipboard history into a request to
    *delete* it, and the CLI ran it without asking.

    The rule now: a destructive command must be asked for in words the table
    actually contains. Typo tolerance is a convenience; it is not worth buying
    at the price of silently destroying data.
    """
    intent = parse("open vault")
    assert intent.name != "wipe_vault"
    assert not intent.is_destructive

    # None of these contain a destructive phrase, so none may resolve to one,
    # however close the edit distance.
    for near_miss in ("open vault", "wype vault", "clear the valut", "undu", "unod last"):
        parsed = parse(near_miss)
        assert not parsed.is_destructive, f"{near_miss} -> {parsed.name}"

    # Typing the phrase itself, or the phrase plus a stray character, still
    # resolves — the user did say the words. The CLI asks before running it.
    assert parse("wipe vault").name == "wipe_vault"
    assert parse("wipe vaultt").name == "wipe_vault"
    assert parse("delete clipboard history").name == "wipe_vault"
    assert parse("undo").name == "undo_last"
