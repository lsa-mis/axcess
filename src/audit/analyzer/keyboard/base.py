"""Data classes for the keyboard-trap probe.

Mirrors the shape used by the semantic analyzers
(``audit.analyzer.semantic.base``) so the orchestrator can persist
keyboard findings into ``page_a11y_findings`` with the same
``to_repo_kwargs()`` contract, no per-pipeline branching in the
persistence layer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

# Rule ids, kept narrow so the audit-report YAML can pin per-rule
# remediation copy without globbing.
RULE_STUCK = "keyboard-trap-stuck"  # focus glued to one element
RULE_NO_ESCAPE = "keyboard-trap-modal-no-escape"  # legacy; no longer emitted
RULE_IFRAME = "keyboard-trap-iframe"  # legacy; no longer emitted

# WCAG SC + level. We expose them as constants so callers don't
# hardcode them (they appear in IssueRow rendering, exports, etc.).
SC = "2.1.2"
LEVEL = "A"

# Documentation pointer. WCAG 2.2 publishes the canonical
# "Understanding" page per criterion; this one is stable across
# revisions and is what an editor / developer would search for.
HELP_URL = "https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap.html"


@dataclass(frozen=True)
class KeyboardTrap:
    """One suspected keyboard trap on one page.

    Shape mirrors :class:`audit.analyzer.semantic.base.SemanticFinding`
    and :class:`audit.analyzer.axe.AxeViolation` so the persistence
    layer (``_persist_axe`` style) can write all three pipelines into
    the same ``page_a11y_findings`` table without branching.
    """

    rule_id: str
    impact: str  # always 'critical', keyboard traps fully block users
    target_selector: str
    failure_summary: str
    html_snippet: str
    # The three fields below are stable across every KeyboardTrap
    # because they're determined by the SC, not the per-finding data;
    # we still carry them on the row so the audit report can pull them
    # via the same accessor as semantic/axe findings.
    criterion_sc: str = SC
    wcag_level: str = LEVEL
    help: str = (
        "Keyboard users must be able to move focus away from any element using only the keyboard."
    )
    help_url: str = HELP_URL

    @property
    def target_hash(self) -> str:
        """Dedupe key for the (page, rule, target) tuple.

        Same approach as the axe pipeline, a sha256 over the rule
        id + selector + (a slice of) the HTML snippet. Stable across
        rescans of the same page; differs from one trap to another on
        the same page (different selectors).
        """
        h = hashlib.sha256()
        h.update(self.rule_id.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(self.target_selector.encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(self.html_snippet[:200].encode("utf-8", errors="replace"))
        return h.hexdigest()

    def to_repo_kwargs(self) -> dict[str, Any]:
        """Match the kwargs accepted by ``repo.upsert_axe_violation``.

        Mirrors :meth:`SemanticFinding.to_repo_kwargs`, the orchestrator
        calls ``upsert_axe_violation(**finding.to_repo_kwargs())`` and
        the same row format works for axe, semantic, and keyboard.
        """
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
            "pipeline": "keyboard",
            "criterion_sc": self.criterion_sc,
        }
