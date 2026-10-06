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
    "wcag": "At page load",
    "click_through": "After clicking",
    "alt_text": "In an image",
}

FINDING_TYPE_HELP: dict[FindingType, str] = {
    "wcag": (
        "Found when the page first loads. It can come from a rule check, a browser check "
        "(such as the keyboard check), or the AI review."
    ),
    "click_through": (
        "Found only after Axcess clicked something that opens more of the page, such as a "
        "menu, a tab, or a pop-up window (dialog). To see the problem yourself, click the "
        "same thing. Axcess never clicks links."
    ),
    "alt_text": (
        "Found by the image text check. It looks at words inside an image and compares them "
        "to the image's text description (alt text), which a screen reader reads aloud."
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
        "A rule check (axe or Alfa) failed. These checks follow fixed rules, so they give "
        "the same result every time. Look at the issue on the page, fix it, test the fix, "
        "then scan again to see if it is still found."
    ),
    "expert_review": (
        "Axcess found a possible problem, but it cannot be certain. This happens with "
        "checks such as the AI review, the browser checks, or a rule check that cannot "
        "decide. A person must decide whether it is a real problem before you report it."
    ),
    "informational": (
        "Recorded for context. This is not a problem to fix. For example, an image whose "
        "text description (alt text) already matches the words in the image."
    ),
}
