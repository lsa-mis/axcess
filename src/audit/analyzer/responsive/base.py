"""Data classes for the responsive/zoom probe.

Mirrors the keyboard package (``audit.analyzer.keyboard.base``) so the
orchestrator persists responsive findings through the same
``upsert_axe_violation(**finding.to_repo_kwargs())`` path with zero
per-pipeline branching. Unlike the keyboard probe (one SC), this probe
spans three success criteria, so the SC/level/help fields are set per
finding by the probe rather than fixed at the class level.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

# Rule ids — narrow, grep-able, and prefixed so `issues.py` can route
# the pipeline label the same way it does for `keyboard-trap-*`.
RULE_REFLOW = "responsive-reflow-overflow"          # SC 1.4.10 at 320px
RULE_TEXT_CLIPPED = "responsive-text-clipped"        # SC 1.4.4 zoom proxy
RULE_SPACING_CLIPPED = "responsive-text-spacing-clipped"  # SC 1.4.12

# Canonical WCAG "Understanding" pages per criterion.
HELP_URLS = {
    "1.4.4": "https://www.w3.org/WAI/WCAG21/Understanding/resize-text.html",
    "1.4.10": "https://www.w3.org/WAI/WCAG21/Understanding/reflow.html",
    "1.4.12": "https://www.w3.org/WAI/WCAG21/Understanding/text-spacing.html",
}


@dataclass(frozen=True)
class ResponsiveFinding:
    """One responsive/zoom/spacing failure on one page element.

    Shape mirrors :class:`KeyboardTrap` so the persistence layer writes
    all dynamic-probe pipelines into ``page_a11y_findings`` uniformly.
    """

    rule_id: str
    criterion_sc: str  # "1.4.4" | "1.4.10" | "1.4.12"
    impact: str  # serious for all three — barriers with partial workarounds
    target_selector: str
    failure_summary: str
    html_snippet: str
    help: str
    wcag_level: str = "AA"

    @property
    def help_url(self) -> str:
        return HELP_URLS.get(self.criterion_sc, "https://www.w3.org/WAI/WCAG21/Understanding/")

    @property
    def target_hash(self) -> str:
        """Dedupe key — stable across rescans of the same page+element."""
        h = hashlib.sha256()
        h.update(self.rule_id.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(self.target_selector.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(self.html_snippet[:200].encode("utf-8", errors="replace"))
        return h.hexdigest()

    def to_repo_kwargs(self) -> dict[str, Any]:
        """Kwargs for ``repo.upsert_axe_violation`` — same row format as
        the axe / semantic / keyboard pipelines."""
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
            "pipeline": "responsive",
            "criterion_sc": self.criterion_sc,
        }
