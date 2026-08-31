"""Data classes for the live-page interaction probe.

Every other analyzer pipeline in this package invents its own rule
vocabulary and persists through a dedicated ``upsert_*`` helper with its own
``pipeline`` discriminator. This one deliberately does not.

What the interaction probe produces *is* an axe violation — the same rules,
against the same DOM, read by the same engine. The only new fact it
contributes is **which control had to be operated** before the violating
markup existed. So its findings ride the ordinary
``repo.upsert_axe_violation`` path with ``pipeline='axe'``, and the existing
``UNIQUE (page_id, rule_id, target_hash)`` constraint does the deduplication
for free: a violation that was already on the page at load produces an
identical ``(rule_id, target_selector, html_snippet)`` triple in every state
a click reveals, collides, and updates in place instead of being reported
once per click.

That is the whole reason this pipeline is cheap to add. Giving revealed
findings their own table or their own ``pipeline`` value would have put them
outside that unique key and reintroduced the duplicate reporting it already
prevents.
"""

from __future__ import annotations

from dataclasses import dataclass

from audit.analyzer.axe import AxeViolation


@dataclass(frozen=True)
class RevealedViolation:
    """One axe violation that was not present when the page finished loading.

    ``revealed_by`` is the accessible name of the control that was operated,
    truncated by the probe. It is written to ``page_a11y_findings.revealed_by``
    so an auditor can reproduce the state by hand; it is intentionally *not*
    part of ``target_hash``, because two different controls that reveal the
    same defective markup are one defect, not two.
    """

    violation: AxeViolation
    revealed_by: str

    @property
    def target_hash(self) -> str:
        """Delegate to the wrapped violation — screenshots key on this."""
        return self.violation.target_hash

    @property
    def target_selector(self) -> str:
        """Delegate too, so the screenshot pass treats every finding type
        the same way without knowing which pipeline produced it."""
        return self.violation.target_selector
