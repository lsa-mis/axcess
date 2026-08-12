"""Data classes for the visual (VLM) analyzers.

Mirrors the focus/responsive probe shape so findings persist through the
same ``upsert_*`` path with a ``pipeline='visual'`` discriminator.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

RULE_MEANINGFUL_SEQUENCE = "visual-meaningful-sequence"  # SC 1.3.2
RULE_MOTION_NO_PAUSE = "visual-motion-no-pause"  # SC 2.2.2
RULE_AUTOPLAY_AUDIO_NO_CONTROL = "visual-autoplay-audio-no-control"  # SC 1.4.2

HELP_URLS = {
    "1.3.2": "https://www.w3.org/WAI/WCAG22/Understanding/meaningful-sequence.html",
    "1.4.2": "https://www.w3.org/WAI/WCAG22/Understanding/audio-control.html",
    "2.2.2": "https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html",
}


@dataclass(frozen=True)
class VisualFinding:
    """One VLM-detected visual failure on a page."""

    rule_id: str
    target_selector: str
    failure_summary: str
    html_snippet: str
    help: str
    criterion_sc: str = "1.3.2"
    wcag_level: str = "A"
    impact: str = "serious"

    @property
    def help_url(self) -> str:
        return HELP_URLS.get(self.criterion_sc, "https://www.w3.org/WAI/WCAG22/Understanding/")

    @property
    def target_hash(self) -> str:
        h = hashlib.sha256()
        h.update(self.rule_id.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(self.target_selector.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(self.html_snippet[:200].encode("utf-8", errors="replace"))
        return h.hexdigest()

    def to_repo_kwargs(self) -> dict[str, Any]:
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
            "pipeline": "visual",
            "criterion_sc": self.criterion_sc,
        }
