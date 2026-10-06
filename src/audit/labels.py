"""User-facing names for features and issue categories, in one place.

Stored data, API fields, and code keep their stable internal keys
(``interaction``, ``dom_state_count``, ``page_dom_states``,
``likely_barrier``, ...). What a reader sees is looked up here, so the web
API, the exports, and the CLI cannot drift into different names for the same
thing. The React client mirrors these in ``frontend/src/lib/labels.ts``; keep
the two in step.

"Click-Through" is the one name for the feature that operates a page's
controls (menus, tabs, dialogs, disclosures) and re-checks the content they
reveal. What it reaches is a "page state opened by clicking", in the term
docs/plain-language.md sets for how a page looked at one moment. Earlier copy
called these "DOM states", "interaction states", "click-through DOM state
discovery", "Click-Through states" and "views opened by clicking"; none of
those should reach a reader. src/audit/web/frontend/src/lib/labels.ts mirrors
these words.
"""

from __future__ import annotations

from typing import Literal

# --------------------------------------------------------------------------
# Click-Through.
# --------------------------------------------------------------------------

CLICK_THROUGH = "Click-Through"
# A page state reached by operating a control, in words that need no
# glossary. Lower case, for use mid-sentence; a heading or a table column
# uses CLICK_THROUGH_STATES_LABEL.
CLICK_THROUGH_STATE = "page state opened by clicking"
CLICK_THROUGH_STATES = "page states opened by clicking"
CLICK_THROUGH_STATES_LABEL = "Page states opened by clicking"


def click_through_states(count: int) -> str:
    """``"1 page state opened by clicking"`` / ``"3 page states opened by clicking"``."""
    return f"{count} {CLICK_THROUGH_STATE if count == 1 else CLICK_THROUGH_STATES}"


# --------------------------------------------------------------------------
# Finding types: which family of checks produced an issue's evidence.
# --------------------------------------------------------------------------

FindingType = Literal["wcag", "click_through", "alt_text"]
FINDING_TYPES: tuple[FindingType, ...] = ("wcag", "click_through", "alt_text")

FINDING_TYPE_LABELS: dict[FindingType, str] = {
    "wcag": "WCAG",
    "click_through": CLICK_THROUGH,
    "alt_text": "Alt Text",
}

FINDING_TYPE_HELP: dict[FindingType, str] = {
    "wcag": (
        "Found at page load, by a rule check (axe or Alfa), a browser check such "
        "as the keyboard check, or the AI review."
    ),
    "click_through": (
        "Found only in a page state opened by clicking a control, such as a menu, "
        "tab, or dialog. Use that control first to see it."
    ),
    "alt_text": (
        "Found by the image text check: text in an image, and whether its alt text "
        "(what a screen reader reads) says the same."
    ),
}

# --------------------------------------------------------------------------
# Review lanes: how much confidence an issue's evidence carries.
# --------------------------------------------------------------------------

ReviewLane = Literal["likely_barrier", "expert_review", "informational"]
REVIEW_LANES: tuple[ReviewLane, ...] = ("likely_barrier", "expert_review", "informational")

REVIEW_LANE_LABELS: dict[ReviewLane, str] = {
    "likely_barrier": "Mostly sure",
    "expert_review": "Not sure",
    "informational": "For information",
}

REVIEW_LANE_HELP: dict[ReviewLane, str] = {
    "likely_barrier": (
        "A rule check (axe or Alfa) failed a fixed rule, which gives the same result every "
        "time. Check it on the page, fix it, test the fix, then scan again to see if it is "
        "still found."
    ),
    "expert_review": (
        "A possible problem from a check that cannot be sure, such as the AI review or a "
        "rule check that cannot tell. A person must decide if it is a real problem before "
        "you report it."
    ),
    "informational": (
        "Recorded for context, not a problem to fix, such as an image whose alt text "
        "already says the same words."
    ),
}
