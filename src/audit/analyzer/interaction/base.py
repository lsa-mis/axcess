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


@dataclass(frozen=True)
class InteractionResult:
    """What one page's interaction pass produced.

    Returned rather than recorded on the probe. The probe is built once per
    crawl and used by every worker, so a count kept on it is shared mutable
    state: with two workers one page's pass reset the field before another
    read it, and a scan whose log showed 2,637 state-changing clicks
    recorded 2,585. A return value cannot be raced.
    """

    findings: tuple[RevealedViolation, ...] = ()
    #: Clicks that actually changed the DOM — states a load-time pass cannot
    #: reach, counted whether or not they held a defect.
    states: int = 0
    urls: tuple[str, ...] = ()
    #: False when exploration could not start with its required safety guard.
    evaluated: bool = True
    #: Distinct controls this page exposed, counting the ones a click
    #: revealed. Discovery is not coverage: a control can be found and then
    #: refused, capped, or never reached, so it is reported separately from
    #: ``clicks_succeeded`` rather than folded into one "controls" number.
    controls_discovered: int = 0
    #: Controls the probe chose to operate, whether or not the click landed.
    clicks_attempted: int = 0
    #: Clicks Playwright actually dispatched. An attempt that timed out or
    #: hit a detached node is not an interaction the report may claim. This
    #: counts replays too, so it can exceed ``controls_operated``.
    clicks_succeeded: int = 0
    #: Distinct controls whose click was dispatched at least once. This, not
    #: the click count, is the numerator of "operated N of M controls":
    #: reopening a menu to reach its next sibling is a second click on the
    #: same control, not a second control.
    controls_operated: int = 0
    #: Distinct controls refused because their label matched a blocked action.
    blocked_controls: int = 0
    #: Which bounds stopped exploration: any of ``clicks``, ``time``,
    #: ``depth``, ``repeated_controls``, ``dialog_not_dismissed``. Empty
    #: means the page was swept to exhaustion within every configured bound.
    limits: tuple[str, ...] = ()
    #: Dialogs a click opened, and how many would not close again. A stuck
    #: dialog ends the page: its overlay covers every remaining control, so
    #: clicking on regardless would record coverage that never happened.
    dialogs_opened: int = 0
    dialogs_stuck: int = 0
    #: Bounded, reproducible note about the first stuck dialog: which dialog,
    #: which control opened it, and what dismissal was tried.
    detail: str = ""
