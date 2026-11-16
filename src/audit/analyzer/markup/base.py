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


RULE_PLACEHOLDER_ONLY = "markup-placeholder-only"
RULE_LABEL_FOR_MISSING = "markup-label-for-missing"
RULE_TITLE_REPEATS_TEXT = "markup-title-repeats-text"
RULE_STYLED_AS_HEADING = "markup-styled-as-heading"
# Results kept per page for the heading guess, fewer than the other rules':
# it is a guess, and a page with more is one template to look at.
MAX_STYLED_HEADINGS = 20

# Each rule, by id; ``probe._RULE_JS`` holds the code that asks each rule's
# question, under the same id.
RULES: dict[str, MarkupRule] = {
    # WCAG 3.3.2, and 1.3.1: a field whose only name is its placeholder. axe's
    # ``label`` rule accepts a placeholder as the field's name, so axe never
    # reports it. W3C WAI forms tutorial, "Instructions"
    # (https://www.w3.org/WAI/tutorials/forms/instructions/), paraphrased:
    # placeholder text is not a replacement for a label. Mostly sure: whether
    # the field has a label, aria-label, aria-labelledby text or title is a
    # fact of the page code, and the placeholder disappears when typing
    # starts.
    RULE_PLACEHOLDER_ONLY: MarkupRule(
        rule_id=RULE_PLACEHOLDER_ONLY,
        title="Field is named only by its placeholder text",
        criterion_sc="3.3.2",
        wcag_scs="3.3.2,1.3.1",
        wcag_level="A",
        impact="serious",
        help_url="https://www.w3.org/WAI/WCAG22/Understanding/labels-or-instructions.html",
        review_lane="likely_barrier",
        evidence_confidence="high",
        evidence_summary=(
            "The page code check read the field's code (HTML). Its only name is its "
            "placeholder text, which disappears when someone types. Check it on the page."
        ),
    ),
    # WCAG 1.3.1: a <label for> whose for value names no element, or one a
    # label cannot name, so the label is tied to nothing. axe reports the
    # field the label leaves unnamed (its ``label`` rule), never the label, so
    # this is the label's own occurrence and the fix points at it. Mostly
    # sure: the browser's own ``label.control`` is null.
    RULE_LABEL_FOR_MISSING: MarkupRule(
        rule_id=RULE_LABEL_FOR_MISSING,
        title="Label is tied to no field",
        criterion_sc="1.3.1",
        wcag_scs="1.3.1",
        wcag_level="A",
        impact="moderate",
        help_url="https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html",
        review_lane="likely_barrier",
        evidence_confidence="high",
        evidence_summary=(
            "The page code check read the label's code (HTML). Its for value points at "
            "no field, so the browser ties the label to nothing. Check it on the page."
        ),
    ),
    # Best practice, no WCAG criterion: a title that says exactly what the
    # control's own visible text says. Some screen readers read both, so the
    # name is heard twice. Low impact and nothing to fix for conformance, so
    # For information: a record of tidy-up work, not a problem to report.
    RULE_TITLE_REPEATS_TEXT: MarkupRule(
        rule_id=RULE_TITLE_REPEATS_TEXT,
        title="Title repeats the text it is on",
        criterion_sc=None,
        wcag_scs=None,
        wcag_level=None,
        impact="minor",
        help_url="https://www.w3.org/TR/html-aam-1.0/",
        review_lane="informational",
        evidence_confidence="high",
        evidence_summary=(
            "The page code check read the element's code (HTML). Its title says the "
            "same as its visible text. No WCAG criterion requires a fix."
        ),
    ),
    # WCAG 1.3.1, failure F2 (using changes in text presentation to convey
    # information without using the appropriate markup): a short line that is
    # bold or large and comes before more content, but is not a heading. It is
    # a guess, because bold text is also used for emphasis, labels and
    # notes, so Not sure, low confidence, and at most MAX_STYLED_HEADINGS a
    # page.
    RULE_STYLED_AS_HEADING: MarkupRule(
        rule_id=RULE_STYLED_AS_HEADING,
        title="Text may look like a heading but is not marked as one",
        criterion_sc="1.3.1",
        wcag_scs="1.3.1",
        wcag_level="A",
        impact="moderate",
        help_url="https://www.w3.org/WAI/WCAG22/Techniques/failures/F2",
        review_lane="expert_review",
        evidence_confidence="low",
        evidence_summary=(
            "A guess from the text's style in the page code (HTML): short, bold or "
            "large, on its own line, and followed by more content. A person decides "
            "whether it is a heading."
        ),
        max_results=MAX_STYLED_HEADINGS,
    ),
}


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
