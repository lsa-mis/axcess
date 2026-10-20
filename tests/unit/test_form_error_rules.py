"""The form error check's decision rules (WCAG SC 3.3.1), without a browser.

The browser half is measured on labelled pages in
tests/integration/test_form_error_identification.py; these pin the rules
those numbers rest on, one at a time.
"""

from __future__ import annotations

from audit.analyzer.forms.base import Attempt, FieldState, Message, classify, skip_reason
from audit.analyzer.forms.probe import _is_error_colour

NAME = FieldState(0, "Name", aria_invalid=False)
EMAIL = FieldState(1, "Email address", aria_invalid=False)


def _attempt(**kw: object) -> Attempt:
    base: dict[str, object] = {
        "fields": (NAME, EMAIL),
        "marked": (),
        "messages": (),
        "native_invalid": (),
        "blocked_request": False,
    }
    base.update(kw)
    return Attempt(**base)  # type: ignore[arg-type]


def test_safety_comes_before_everything() -> None:
    def skip(**kw: object) -> str | None:
        args = {
            "has_password": False,
            "has_card": False,
            "has_captcha": False,
            "is_search": False,
            "has_submit": True,
            "words": "Send message",
        }
        args.update(kw)
        return skip_reason(**args)  # type: ignore[arg-type]

    assert skip() is None
    assert skip(has_password=True) and skip(has_card=True) and skip(has_captcha=True)
    assert skip(is_search=True) and skip(has_submit=False)
    assert skip(words="Delete account") and skip(words="Donate") and skip(words="Pay now")
    # The words this check exists to press are not refused.
    assert skip(words="Submit") is None and skip(words="Subscribe") is None


def test_marked_fields_with_no_text_fail() -> None:
    outcome, _, undescribed = classify(_attempt(marked=(0, 1)))
    assert outcome == "fail" and undescribed == [0, 1]


def test_no_reaction_is_not_a_failure() -> None:
    assert classify(_attempt())[0] == "not_applicable"


def test_a_blocked_request_means_not_checked() -> None:
    late = Message("Something went wrong. Please try again.", announced=True, before_request=False)
    assert classify(_attempt(blocked_request=True, messages=(late,)))[0] == "not_checked"


def test_the_browser_message_describes_its_own_fields() -> None:
    assert classify(_attempt(marked=(0,), native_invalid=(0, 1)))[0] == "native"


def test_linked_text_counts_in_any_language() -> None:
    linked = Message("Este campo es obligatorio", fields=(0,), linked=True)
    assert classify(_attempt(fields=(NAME,), marked=(0,), messages=(linked,)))[0] == "pass"


def test_a_symbol_is_not_a_description() -> None:
    bang = Message("!", fields=(0,), error_colour=True)
    assert classify(_attempt(fields=(NAME,), marked=(0,), messages=(bang,)))[0] == "fail"


def test_success_wording_without_corroboration_is_not_an_error() -> None:
    thanks = Message("Thanks! Please check your inbox to confirm.")
    assert classify(_attempt(messages=(thanks,)))[0] == "not_applicable"


def test_a_summary_names_a_field_by_a_distinctive_word() -> None:
    summary = Message("2 errors: Name - required; Email - required", announced=True)
    assert classify(_attempt(marked=(0, 1), messages=(summary,)))[0] == "pass"


def test_a_generic_message_fails_when_fields_are_only_coloured() -> None:
    generic = Message("Please correct the errors below.", announced=True)
    outcome, _, undescribed = classify(_attempt(marked=(0, 1), messages=(generic,)))
    assert outcome == "fail" and undescribed == [0, 1]


def test_error_colours() -> None:
    for red in ("rgb(198, 40, 40)", "rgb(255, 214, 214)", "rgb(239, 68, 68)", "rgb(255, 152, 0)"):
        assert _is_error_colour(red), red
    for other in (
        "rgb(46, 125, 50)",
        "rgb(29, 95, 191)",
        "rgb(255, 245, 157)",
        "rgb(118, 118, 118)",
        "rgba(198, 40, 40, 0.1)",
        "rgb(245, 245, 220)",
    ):
        assert not _is_error_colour(other), other
