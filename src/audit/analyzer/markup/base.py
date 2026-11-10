"""Rules and data classes for the page code check (``pipeline='markup'``).

The page code check reads the rendered page code (DOM) after the rule check
(axe) and reports patterns axe-core does not: each rule is one question about
the page code with a yes-or-no answer, asked in the browser
(``audit.analyzer.markup.probe``). Findings persist through the same
``upsert_*`` path as the focus and keyboard checks, with a
``pipeline='markup'`` discriminator.

Every rule's metadata lives in :data:`RULES`, and ``audit.web.issues`` reads
its review lane, confidence and evidence wording from there, so a rule's
"How sure" is decided in one place. The guidance card for each rule is
``markup_rules[<rule_id>]`` in ``audit/rules/audit_report.yaml``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

PIPELINE = "markup"

# Results kept per rule per page. A page with more is a template problem; the
# first 50 show it, and the rest are the same fix.
MAX_RESULTS_PER_RULE = 50
# Element code (HTML) kept per occurrence, the same cap as the rule check's.
MAX_SNIPPET_CHARS = 4000

ReviewLane = Literal["likely_barrier", "expert_review", "informational"]
EvidenceConfidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class MarkupRule:
    """One question the page code check asks, and how sure its answer is.

    ``criterion_sc`` is None for a best practice that no WCAG criterion
    requires; the issue then shows Best practice. ``evidence_summary`` is
    shown on the Issues page under "How sure", so it follows
    docs/plain-language.md.
    """

    rule_id: str
    title: str
    criterion_sc: str | None
    wcag_scs: str | None
    wcag_level: Literal["A", "AA", "AAA"] | None
    impact: Literal["critical", "serious", "moderate", "minor"]
    help_url: str
    review_lane: ReviewLane
    evidence_confidence: EvidenceConfidence
    evidence_summary: str
    max_results: int = MAX_RESULTS_PER_RULE


# Filled in by each rule as it is added; ``probe._RULE_JS`` holds the code
# that asks each rule's question, under the same id.
RULES: dict[str, MarkupRule] = {}


def rule_for(rule_id: str) -> MarkupRule | None:
    """The rule's metadata, or None for a rule id this version does not know."""
    return RULES.get(rule_id)


@dataclass(frozen=True)
class MarkupFinding:
    """One element the page code check flagged, as an occurrence.

    ``target_selector`` is stored for the page inspector, which outlines the
    element with it; the interface shows the element code (HTML) instead.
    """

    rule_id: str
    target_selector: str
    html_snippet: str
    failure_summary: str

    @property
    def rule(self) -> MarkupRule:
        return RULES[self.rule_id]

    @property
    def target_hash(self) -> str:
        """Dedupe key, stable across rescans of the same page and element."""
        h = hashlib.sha256()
        for part in (self.rule_id, self.target_selector, self.html_snippet[:200]):
            h.update(part.encode("utf-8", errors="replace"))
            h.update(b"\x00")
        return h.hexdigest()

    def to_repo_kwargs(self) -> dict[str, Any]:
        """Kwargs for ``repo.upsert_markup_finding``, the row format the other
        browser checks use."""
        rule = self.rule
        return {
            "rule_id": self.rule_id,
            "wcag_sc": rule.criterion_sc,
            "wcag_scs": rule.wcag_scs,
            "wcag_level": rule.wcag_level,
            "impact": rule.impact,
            "help": rule.title,
            "help_url": rule.help_url,
            "target_selector": self.target_selector,
            "failure_summary": self.failure_summary,
            "html_snippet": self.html_snippet[:MAX_SNIPPET_CHARS],
            "target_hash": self.target_hash,
            "pipeline": PIPELINE,
            "criterion_sc": rule.criterion_sc,
        }
