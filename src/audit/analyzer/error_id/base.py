"""Data classes for the live-page error-identification probe (SC 3.3.1).

Mirrors ``audit.analyzer.focus.base`` so findings persist through the same
``upsert_*`` path with a ``pipeline='error_id'`` discriminator and no
per-pipeline branching elsewhere.

SC 3.3.1 (Error Identification) is only observable *after* a form tries to
validate: a required field that is empty on load is not yet an error. The
probe therefore triggers each form's client-side validation without ever
submitting (see ``probe.py``), then asks a purely structural question — when
an error state exists, is it identified in text and associated with the field
a screen-reader user is on? That structural question is what these rule ids
name.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

# Rule ids — grep-able and prefixed so issues.py routes the pipeline the same
# way it does for keyboard-trap-* / focus-* / responsive-*.
# An invalid control with no error text anywhere a user could read.
RULE_NOT_IDENTIFIED = "error-not-identified-in-text"
# An error message is shown visually but is not programmatically tied to the
# field (no aria-invalid / aria-describedby / aria-errormessage), so assistive
# technology never announces it.
RULE_NOT_ASSOCIATED = "error-not-programmatically-associated"

SC = "3.3.1"
LEVEL = "A"
HELP_URL = "https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html"


@dataclass(frozen=True)
class ErrorIdentificationFinding:
    """One SC 3.3.1 error-identification failure on one form control.

    Shape mirrors :class:`audit.analyzer.focus.base.FocusFinding` /
    :class:`audit.analyzer.keyboard.base.KeyboardTrap` so the persistence
    layer writes it into ``page_a11y_findings`` with no branching.
    """

    rule_id: str
    target_selector: str
    failure_summary: str
    html_snippet: str
    help: str
    criterion_sc: str = SC
    wcag_level: str = LEVEL
    impact: str = "serious"
    help_url: str = HELP_URL

    @property
    def target_hash(self) -> str:
        """Dedupe key, stable across rescans of the same page + control."""
        h = hashlib.sha256()
        h.update(self.rule_id.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(self.target_selector.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(self.html_snippet[:200].encode("utf-8", errors="replace"))
        return h.hexdigest()

    def to_repo_kwargs(self) -> dict[str, Any]:
        """Kwargs for ``repo.upsert_error_id_finding`` — same row format as the
        axe / semantic / keyboard / focus pipelines."""
        return {
            "rule_id": self.rule_id,
            "wcag_sc": self.criterion_sc,
            "wcag_scs": self.criterion_sc,
            "wcag_level": self.wcag_level,
            "impact": self.impact,
            "help": self.help,
            "help_url": self.help_url,
            "target_selector": self.target_selector,
            "failure_summary": self.failure_summary,
            "html_snippet": self.html_snippet,
            "target_hash": self.target_hash,
            "pipeline": "error_id",
            "criterion_sc": self.criterion_sc,
        }
