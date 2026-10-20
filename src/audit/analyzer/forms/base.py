"""Form error check (WCAG SC 3.3.1 Error Identification): results and rules.

SC 3.3.1 (Level A): "If an input error is automatically detected, the item
that is in error is identified and the error is described to the user in
text." The probe (``probe.py``) submits each form once, empty, with every
request that could change anything blocked, and records what the page did.
This module turns that record into an outcome. It is pure, so every rule
can be unit-tested without a browser.

The order of concerns is safety, then precision, then speed, then recall:

* **Safety** is decided before anything is clicked (``skip_reason``): sign-in,
  payment, destructive, CAPTCHA and search forms are never submitted.
* **Precision**: a failure is reported only on strong evidence that the form
  detected an error. A field newly marked ``aria-invalid="true"``, a field
  that turns an error colour (red or orange), or a field that gains an error
  class, and no new visible text describing it. A page that merely changes
  is not evidence: SC 3.3.1 applies only "if an input error is automatically
  detected", so a form that shows nothing may simply not validate, which is
  not a failure.
* A request the guard blocked means the page tried to send the form. Any
  error the server would have returned is unknown, and any message shown
  after the block may be the page reacting to the block itself, so the
  outcome is "not checked", never a pass or a fail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Outcome = Literal[
    "fail",  # an error was detected but not identified or described in text
    "pass",  # every field marked in error is described in text
    "native",  # only the browser's own message (required, type=email ...)
    "not_applicable",  # the form showed no sign of detecting an error
    "not_checked",  # the page tried to send the form; the answer is unknown
    "skipped",  # never submitted, for safety or because it does not apply
]

# Words in a form's submit control or heading that mean submitting it, even
# empty, is not ours to do. Narrower than Click-Through's blocked labels on
# purpose: "Submit", "Send", "Save" and "Subscribe" are the controls this
# check exists to press, and the network guard keeps an empty submit from
# reaching the server. These are the forms where even an attempt is wrong.
SENSITIVE_WORDS = (
    "delete",
    "remove",
    "pay",
    "payment",
    "purchase",
    "buy",
    "checkout",
    "check out",
    "place order",
    "donate",
    "transfer",
    "withdraw",
    "unsubscribe",
    "cancel subscription",
    "close account",
    "deactivate",
    "revoke",
    "sign out",
    "log out",
    "logout",
    "sign in",
    "log in",
    "login",
    "reset password",
    "change password",
)

# Text that reads as an error message. Used only for text that is not tied to
# a field by aria-describedby or aria-errormessage and not inside a field's
# own group; tied text counts whatever it says, so a message in another
# language still counts when it is linked.
_ERROR_WORDS = re.compile(
    r"\b(required|require[sd]?|error|errors|invalid|missing|mandatory|must|"
    r"please (enter|provide|fill|select|choose|complete|correct|check)|"
    r"enter (a|an|your|the)|select (a|an|your|the)|choose (a|an|your|the)|"
    r"can(?:no|')t be (blank|empty)|cannot be (blank|empty)|is not valid|"
    r"not a valid|incorrect|too (short|long)|at least|empty|fix|problem)\b",
    re.IGNORECASE,
)


def looks_like_error(text: str) -> bool:
    return bool(_ERROR_WORDS.search(text))


@dataclass(frozen=True)
class FieldState:
    """One field before or after the submit attempt."""

    key: int
    label: str
    aria_invalid: bool
    # True when a colour on the field, its wrapper or its label became an
    # error colour (red or orange) since the attempt started.
    error_colour: bool = False
    error_class: bool = False


@dataclass(frozen=True)
class Message:
    """Text that appeared (or became visible) after the attempt started."""

    text: str
    # Field keys this text belongs to: linked by aria-describedby or
    # aria-errormessage, or inside the field's own group.
    fields: tuple[int, ...] = ()
    # Inside role=alert, role=status or an aria-live region.
    announced: bool = False
    # Shown before the first blocked request, so the page's own validation
    # produced it rather than a reaction to the block.
    before_request: bool = True
    # Shown in an error colour (red or orange).
    error_colour: bool = False
    # Linked to a field by aria-describedby or aria-errormessage, rather than
    # only placed beside it.
    linked: bool = False


@dataclass(frozen=True)
class Attempt:
    """Everything the probe saw for one form."""

    fields: tuple[FieldState, ...]
    marked: tuple[int, ...]  # fields newly in error (aria-invalid, colour, class)
    messages: tuple[Message, ...]
    native_invalid: tuple[int, ...]  # fields the browser's own validation stopped
    blocked_request: bool


@dataclass
class FormResult:
    """The check's answer for one form, with what it is based on."""

    outcome: Outcome
    reason: str
    form: str  # a short description: its heading, label or submit control
    selector: str = ""
    frame_url: str = ""
    fields_in_error: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


def skip_reason(
    *,
    has_password: bool,
    has_card: bool,
    has_captcha: bool,
    is_search: bool,
    has_submit: bool,
    words: str,
) -> str | None:
    """Why a form must not be submitted, or None. Decided before any click."""
    if has_password:
        return "sign-in or account form (has a password field)"
    if has_card:
        return "payment form (has card fields)"
    if has_captcha:
        return "form with a CAPTCHA"
    if is_search:
        return "search form (an empty search is not an input error)"
    lowered = re.sub(r"\s+", " ", words).casefold()
    for word in SENSITIVE_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lowered):
            return f'sensitive action ("{word}")'
    if not has_submit:
        return "no submit control to press"
    return None


def classify(attempt: Attempt) -> tuple[Outcome, str, list[int]]:
    """Outcome, reason, and the keys of fields in error that lack text."""
    errors = [m for m in attempt.messages if _is_error_message(m, attempt)]
    trusted = [m for m in errors if m.before_request]

    if attempt.blocked_request and not trusted:
        return "not_checked", "the page tried to send the form; server-side errors are unknown", []
    errors = trusted if attempt.blocked_request else errors

    # A field the browser's own validation stopped is described by the
    # browser's message, even when the page also colours it (:user-invalid).
    native = set(attempt.native_invalid)
    undescribed = [
        key for key in attempt.marked if key not in native and not _described(key, errors, attempt)
    ]
    if not errors:
        if undescribed:
            return (
                "fail",
                "fields were marked in error, but no text describes the error",
                undescribed,
            )
        if native:
            return "native", "the browser's own message describes the error", []
        return "not_applicable", "no sign that the form detected an error", []
    if undescribed:
        return (
            "fail",
            "an error message appeared, but it does not identify every field in error",
            undescribed,
        )
    if not attempt.marked and not native and not _identifies_something(errors, attempt):
        return "fail", "an error message appeared, but it does not say which field is in error", []
    return "pass", "the error is identified and described in text", []


def _is_error_message(message: Message, attempt: Attempt) -> bool:
    """Whether new text is the page describing an error.

    Text linked to a field (aria-describedby, aria-errormessage) counts
    whatever it says, so a message in another language still counts. Text
    only placed beside a field needs error wording or the field marked in
    error. Other text needs error
    wording and something that corroborates it: a field marked in error, an
    announcement (role=alert, a live region, an alert() dialog) or an error
    colour. Error words alone were not enough: success and hint text use them
    too ("Please check your inbox", "No further action is required", "Enter
    your street address"), and the decoy cases written after the first
    version turned exactly those into false failures.
    """
    # A description is words: a lone "!" or "*" beside a field describes
    # nothing (SC 3.3.1 asks for the error to be described in text).
    if not _WORD.search(message.text):
        return False
    if message.linked:
        return True
    # Beside a field: its words, or the field itself being marked, say it is an
    # error, not "Looks good" or "Available".
    if message.fields and (
        looks_like_error(message.text) or set(message.fields) & set(attempt.marked)
    ):
        return True
    corroborated = bool(attempt.marked) or message.announced or message.error_colour
    if looks_like_error(message.text) and corroborated:
        return True
    # Announced text with a field marked in error is the page describing it.
    return message.announced and bool(attempt.marked)


_WORD = re.compile(r"[^\W\d_]{2,}")
# Label words too common to name a field on their own.
_COMMON = {
    "your",
    "please",
    "enter",
    "select",
    "choose",
    "field",
    "this",
    "with",
    "from",
    "address",
    "number",
}


def _names(label: str, text: str) -> bool:
    """Whether ``text`` names the field labelled ``label``.

    The whole label, or one of its distinctive words: a summary often says
    "Email" for a field labelled "Email address", and requiring the whole
    label turned a correct summary into a false failure.
    """
    label = re.sub(r"[*:]", " ", label).casefold().strip()
    text = text.casefold()
    if len(label) >= 3 and label in text:
        return True
    words = [w for w in re.findall(r"[^\W\d_]+", label) if len(w) >= 4 and w not in _COMMON]
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)


def _described(key: int, errors: list[Message], attempt: Attempt) -> bool:
    if any(key in m.fields for m in errors):
        return True
    label = next((f.label for f in attempt.fields if f.key == key), "")
    if any(_names(label, m.text) for m in errors):
        return True
    # A form with one field: any error message can only be about it.
    return len(attempt.fields) == 1 and bool(errors)


def _identifies_something(errors: list[Message], attempt: Attempt) -> bool:
    if len(attempt.fields) == 1:
        return True
    if any(m.fields for m in errors):
        return True
    return any(_names(f.label, m.text) for m in errors for f in attempt.fields)
