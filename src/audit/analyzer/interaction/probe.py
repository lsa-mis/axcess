"""Click controls on a rendered page and re-run axe on what appears.

Most of a modern page does not exist when ``load`` fires. Menus are closed,
dialogs unopened, tabs unswitched, "add another row" rows unadded. A
load-time axe pass cannot see any of it, so the defects in those states are
invisible to every other pipeline here.

This probe operates the page's controls one at a time and re-runs axe
whenever a click actually changed the DOM. It is deliberately conservative:
it never clicks anything whose accessible name matches a destructive word,
it reverts any click that navigates away, and it is bounded on three
independent axes (total clicks, repeats of one structural shape, recursion
depth) so a calendar with 365 day cells cannot turn one page into an
afternoon.

**Only new markup is reported.** The caller passes the load-state
violations as ``baseline``; every hash seen is remembered as exploration
proceeds. A violation on the site header is found once, at load, and never
again — not once per click, and not once per revealed state. That filtering
happens here rather than being left to the database's unique constraint so
the crawl does not pay for hundreds of redundant upserts per page.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from audit.analyzer.axe import AxeAnalyzer, AxeViolation, Level
from audit.analyzer.interaction.base import RevealedViolation
from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Page

log = get_logger(__name__)

# Never operate a control whose accessible name contains one of these. The
# probe runs against real sites, sometimes authenticated ones: clicking
# "Delete account" because it happened to be a <button> is not an acceptable
# failure mode. Matched case-insensitively as a substring, so "Sign out of
# all devices" is caught by "sign out".
DEFAULT_BLOCKED_LABELS: tuple[str, ...] = (
    "sign out",
    "signout",
    "log out",
    "logout",
    "delete",
    "remove",
    "unsubscribe",
    "deactivate",
    "close account",
    "cancel subscription",
)

# Enumerate operable controls and describe each one well enough to find it
# again after the DOM moves.
#
# `select` is excluded on purpose: clicking one opens a native OS dropdown
# that is not in the DOM, cannot be read by axe, and can block the click
# call until it times out. Anything inside an <a> is excluded because links
# are the crawler's job — this probe must not trigger navigation it then has
# to undo.
_CANDIDATE_SELECTOR = (
    'button, [role="button"], [role="tab"], [role="menuitem"], '
    '[role="switch"], [role="checkbox"], [role="radio"], '
    "details > summary, [aria-expanded], [aria-haspopup], [onclick]"
)

# `fresh` answers "did this control become operable since the last mark?".
# It is the whole basis of scoped recursion: after a click, the only controls
# worth descending into are the ones that were not there (or not operable)
# before it. The mark is a JS property on the element, not an attribute, so
# it never appears in innerHTML — invisible to both the DOM hash and axe.
_COLLECT_JS = """
(sel) => {
  const out = [];
  const candidates = document.querySelectorAll(sel);
  const esc = (s) => (window.CSS && CSS.escape ? CSS.escape(s) : s);
  for (const el of candidates) {
    if (el.closest('a')) continue;
    if (el.offsetParent === null) continue;
    const tag = el.tagName.toLowerCase();
    if (tag === 'td' || tag === 'tr' || tag === 'th') continue;
    const id = el.id ? '#' + esc(el.id) : '';
    let classes = '';
    if (!id && el.className && typeof el.className === 'string') {
      const parts = el.className.trim().split(/\\s+/).slice(0, 2).filter(Boolean);
      if (parts.length) classes = '.' + parts.map(esc).join('.');
    }
    const label = (el.getAttribute('aria-label') || el.textContent || '')
      .replace(/\\s+/g, ' ').trim().slice(0, 60);
    const isGlobal = !!el.closest(
      'header, nav, footer, [role="banner"], [role="navigation"], [role="contentinfo"]'
    );
    out.push({
      selector: tag + (id || classes), tag: tag, label: label,
      isGlobal: isGlobal, fresh: !el.__axcessSeen,
    });
  }
  return out;
}
"""

# Mark every currently-operable control as already-seen. Called immediately
# before a click so that whatever the click reveals stands out as unmarked.
_MARK_JS = """
(sel) => {
  let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    if (el.offsetParent !== null) { el.__axcessSeen = true; n++; }
  }
  return n;
}
"""

# Cheap 32-bit rolling hash of the rendered body. Only ever compared against
# another hash taken the same way moments earlier on the same page, so
# collision resistance is irrelevant and speed is not.
_DOM_HASH_JS = """
() => {
  const s = document.body ? document.body.innerHTML : '';
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return h;
}
"""

_DIGITS = re.compile(r"\d+")


def _signature(selector: str) -> str:
    """Collapse digits so structurally identical controls share one shape.

    ``day-cell-1`` … ``day-cell-365`` all become ``day-cell-#``, which is what
    lets the repeat cap treat a whole calendar as one group instead of 365
    separate controls that each look novel.
    """
    return _DIGITS.sub("#", selector.lower())


@dataclass
class _Budget:
    """Caps shared across the whole interaction tree for one page load."""

    remaining: int
    signature_counts: dict[str, int] = field(default_factory=dict)
    seen_keys: set[str] = field(default_factory=set)
    seen_hashes: set[str] = field(default_factory=set)


@dataclass
class InteractionProbe:
    """Re-runs ``axe`` against DOM states reached by operating controls.

    Construct one per crawl and reuse it across pages: it holds no per-page
    state, and the :class:`AxeAnalyzer` it wraps is the same instance the
    load-state pass uses, so axe is injected once per page either way.
    """

    axe: AxeAnalyzer
    level: Level = "AA"
    # Total clicks per page load, across the whole recursion. The dominant
    # cost is one axe pass per state that actually changed, so this is
    # effectively a per-page time budget.
    max_clicks: int = 40
    # How many controls sharing one structural shape to sample.
    max_repeated: int = 3
    # How deep to follow "clicking this revealed more things to click".
    # 2 covers menu -> submenu; beyond that the yield drops sharply.
    max_depth: int = 2
    # Time for a revealed state to settle (animations, async content).
    settle_ms: int = 400
    blocked_labels: tuple[str, ...] = DEFAULT_BLOCKED_LABELS

    async def run(
        self, page: Page, *, baseline: Sequence[AxeViolation] = ()
    ) -> list[RevealedViolation]:
        """Return violations reachable only by operating the page.

        ``baseline`` is the load-state axe result for this page. Anything in
        it is already recorded against the page, so it is seeded into the
        seen set and never reported again no matter how many states it
        survives into. Passing nothing is allowed but means the first
        revealed state re-reports the whole page.
        """
        budget = _Budget(
            remaining=self.max_clicks,
            seen_hashes={v.target_hash for v in baseline},
        )
        found: list[RevealedViolation] = []
        try:
            await self._explore(page, budget, found, pinned=page.url, depth=0, fresh_only=False)
        except Exception as exc:
            # A probe is evidence-gathering, not a gate. Whatever we managed
            # to reach before something went wrong is still valid evidence.
            log.warning("interaction.aborted", error=str(exc)[:200])
        if found:
            log.info(
                "interaction.revealed",
                violations=len(found),
                clicks_used=self.max_clicks - budget.remaining,
            )
        return found

    async def _explore(
        self,
        page: Page,
        budget: _Budget,
        found: list[RevealedViolation],
        *,
        pinned: str,
        depth: int,
        fresh_only: bool,
    ) -> None:
        """Sweep controls and operate the ones this probe has not touched.

        ``fresh_only`` is what makes depth mean nesting rather than breadth.
        A nested sweep runs with it set, so it considers only controls that
        became operable as a result of the click that opened it — not the
        whole document. Without it, the first control that changed anything
        pulled every other control on the page down into its subtree: an
        instrumented run of the stress fixture spent 11 of 12 clicks at
        depth 1 on buttons that had been sitting in the markup all along,
        which exhausted the depth budget before any genuine
        menu -> submenu -> item chain could be reached.
        """
        if depth >= self.max_depth or budget.remaining <= 0:
            return

        # Exactly one pass per level. Mark-and-diff makes a second pass not
        # just redundant but wrong: every control operable at this level is
        # already in `controls`, and anything that becomes operable later did
        # so because a click revealed it — which makes it the nested sweep's
        # business, one level down. Re-reading the document here would hand
        # those revealed controls back to *this* level, and that is precisely
        # how the depth limit came to mean nothing. A five-level chain was
        # walked all the way to level three under ``max_depth=1``, because
        # each extra pass picked up the next level's button and clicked it at
        # depth 0. Termination no longer rests on a progress counter: the
        # control list is finite and the recursion is bounded by max_depth.
        try:
            controls: list[dict[str, Any]] = await page.evaluate(_COLLECT_JS, _CANDIDATE_SELECTOR)
        except Exception:
            return  # navigated or detached mid-sweep
        if fresh_only:
            controls = [c for c in controls if c["fresh"]]

        for control in controls:
            if budget.remaining <= 0:
                break
            if self._is_blocked(control["label"]):
                continue

            key = self._interaction_key(control, pinned)
            if key in budget.seen_keys:
                continue

            signature = _signature(control["selector"])
            shape = f"{'GLOBAL' if control['isGlobal'] else pinned}|{signature}"
            if budget.signature_counts.get(shape, 0) >= self.max_repeated:
                continue

            # Claim the control BEFORE operating it. _operate recurses into a
            # nested sweep of whatever the click reveals; if the claim landed
            # afterwards that sweep would still see this control as untouched
            # and click it again. An end-to-end run caught exactly that: one
            # "Add another guest" button pressed three times, three inputs
            # appended, one defect reported as three findings.
            budget.seen_keys.add(key)
            budget.signature_counts[shape] = budget.signature_counts.get(shape, 0) + 1

            await self._operate(page, budget, found, control, pinned=pinned, depth=depth)

    def _is_blocked(self, label: str) -> bool:
        lowered = label.lower()
        return any(word in lowered for word in self.blocked_labels)

    def _interaction_key(self, control: dict[str, Any], pinned: str) -> str:
        """Identity for "have I already operated this control?".

        Controls inside a header/nav/footer are keyed globally, without the
        page URL, so the site-wide menu button is operated once per crawl
        rather than once per page — the single biggest saving on a large
        site with a persistent navigation bar.

        Recursion depth is deliberately NOT part of this key. It was, and
        that let one control be operated once per level: an end-to-end run
        clicked "Add another guest" three times, appended three inputs,
        and reported one defect as three findings with three different
        positional selectors. The question this key answers is whether we
        have touched a control at all, which does not depend on how we
        arrived at it.
        """
        if control["isGlobal"]:
            return f"GLOBAL|{control['tag']}|{control['label']}"
        return f"{pinned}|{control['tag']}|{control['label']}"

    async def _operate(
        self,
        page: Page,
        budget: _Budget,
        found: list[RevealedViolation],
        control: dict[str, Any],
        *,
        pinned: str,
        depth: int,
    ) -> bool:
        """Click one control; record anything new it revealed.

        Returns whether the click actually happened, so the caller only
        spends budget and dedupe slots on controls it really operated.
        """
        selector = control["selector"]
        label = control["label"] or f"<{control['tag']}>"
        try:
            locator = page.locator(selector).first
            if not await locator.is_visible(timeout=1000):
                return False

            # Everything operable right now is "old". Whatever the click
            # makes operable will be the only unmarked set afterwards, which
            # is exactly what the nested sweep descends into.
            await page.evaluate(_MARK_JS, _CANDIDATE_SELECTOR)

            before_hash = await page.evaluate(_DOM_HASH_JS)
            budget.remaining -= 1
            await locator.click(timeout=3000)
            await page.wait_for_timeout(self.settle_ms)

            # A click that navigated is out of this probe's remit: the page
            # it landed on belongs to the crawl frontier, which owns scope,
            # robots, and rate limiting. Undo it and carry on where we were.
            if page.url != pinned:
                await self._restore(page, pinned)
                return True

            after_hash = await page.evaluate(_DOM_HASH_JS)
            if before_hash == after_hash:
                return True  # inert control; spent, but nothing to scan

            await self._collect(page, budget, found, label)

            # Whatever this click opened may itself contain controls. Only
            # those: fresh_only keeps the descent inside what appeared.
            await self._explore(
                page, budget, found, pinned=pinned, depth=depth + 1, fresh_only=True
            )

            # Close the state we opened so the next sibling is reachable.
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(150)
            return True

        except Exception as exc:
            log.debug("interaction.click_failed", label=label[:40], error=str(exc)[:120])
            # If the failure left the browser somewhere else, get back.
            if page.url != pinned:
                await self._restore(page, pinned)
            return True

    async def _collect(
        self,
        page: Page,
        budget: _Budget,
        found: list[RevealedViolation],
        label: str,
    ) -> None:
        """Run axe on the current state and keep only unseen violations."""
        try:
            violations = await self.axe.run(page, self.level)
        except Exception as exc:
            log.debug("interaction.axe_failed", error=str(exc)[:120])
            return
        for violation in violations:
            digest = violation.target_hash
            if digest in budget.seen_hashes:
                continue
            budget.seen_hashes.add(digest)
            found.append(RevealedViolation(violation=violation, revealed_by=label))

    async def _restore(self, page: Page, pinned: str) -> None:
        """Return the browser to the page we are probing.

        Best-effort by design: if we cannot get back, the next sweep's
        control collection simply finds nothing familiar and the probe
        winds down. Failing to restore must never fail the page fetch,
        which has already produced its load-state evidence.
        """
        with contextlib.suppress(Exception):
            await page.go_back(timeout=5000, wait_until="domcontentloaded")
        if page.url != pinned:
            with contextlib.suppress(Exception):
                await page.goto(pinned, timeout=10000, wait_until="domcontentloaded")
