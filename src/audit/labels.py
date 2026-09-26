"""User-facing names for features and issue categories, in one place.

Stored data, API fields, and code keep their stable internal keys
(``interaction``, ``dom_state_count``, ``page_dom_states``,
``likely_barrier``, ...). What a reader sees is looked up here, so the web
API, the exports, and the CLI cannot drift into different names for the same
thing. The React client mirrors these in ``frontend/src/lib/labels.ts``; keep
the two in step.

"Click-Through" is the one name for the feature that operates a page's
controls (menus, tabs, dialogs, disclosures) and re-checks the content they
reveal. What it reaches is a "view opened by clicking": plain words anyone
can follow. Earlier copy called these "DOM states", "interaction states",
"click-through DOM state discovery" and "Click-Through states"; none of those
should reach a reader.
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
CLICK_THROUGH_STATE = "view opened by clicking"
CLICK_THROUGH_STATES = "views opened by clicking"
CLICK_THROUGH_STATES_LABEL = "Views opened by clicking"


def click_through_states(count: int) -> str:
    """``"1 view opened by clicking"`` / ``"3 views opened by clicking"``."""
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
        "Checked against WCAG rules in the page as it loaded: axe-core, Alfa, "
        "the browser probes, and the semantic checks."
    ),
    "click_through": (
        "Found only after operating a control (a menu, tab, dialog, or "
        "disclosure). Reproduce it by using the control first."
    ),
    "alt_text": (
        "Image evidence: text found in images and whether the alternative text says the same thing."
    ),
}

# --------------------------------------------------------------------------
# Review lanes: how much confidence an issue's evidence carries.
# --------------------------------------------------------------------------

ReviewLane = Literal["likely_barrier", "expert_review", "informational"]
REVIEW_LANES: tuple[ReviewLane, ...] = ("likely_barrier", "expert_review", "informational")

REVIEW_LANE_LABELS: dict[ReviewLane, str] = {
    "likely_barrier": "Barrier",
    "expert_review": "Needs review",
    "informational": "Informational",
}

REVIEW_LANE_HELP: dict[ReviewLane, str] = {
    "likely_barrier": (
        "A rule failed deterministically, so this is likely to block someone. "
        "Fix it, then rescan to confirm."
    ),
    "expert_review": (
        "A lead from a browser probe, image analysis, or AI-assisted check. "
        "A person must confirm it before it is reported as a barrier."
    ),
    "informational": (
        "Recorded for context, not a problem to fix, such as an image whose "
        "alternative text already matches."
    ),
}
