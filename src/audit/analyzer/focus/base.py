"""Data classes for the live-page focus probe.

Mirrors ``audit.analyzer.responsive.base`` so findings persist through the
same ``upsert_*`` path with a ``pipeline='focus'`` discriminator and no
per-pipeline branching elsewhere.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

# Rule id — grep-able + prefixed so issues.py routes the pipeline the same
# way it does for keyboard-trap-* / responsive-*.
RULE_FOCUS_OBSCURED = "focus-not-obscured"  # SC 2.4.11

SC = "2.4.11"
HELP_URL = "https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html"


@dataclass(frozen=True)
class FocusFinding:
    """One focusable element that gets hidden behind a sticky/fixed overlay."""

    rule_id: str
    target_selector: str
    failure_summary: str
    html_snippet: str
    help: str
    criterion_sc: str = SC
    wcag_level: str = "AA"
    impact: str = "serious"

    @property
    def help_url(self) -> str:
        return HELP_URL

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
        """Kwargs for ``repo.upsert_focus_finding`` — same row format as the
        axe / semantic / keyboard / responsive pipelines."""
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
            "pipeline": "focus",
            "criterion_sc": self.criterion_sc,
        }
