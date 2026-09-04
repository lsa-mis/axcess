"""Click controls on a rendered page and re-run axe on what appears.

Most of a modern page does not exist when ``load`` fires. Menus are closed,
dialogs unopened, tabs unswitched, "add another row" rows unadded. A
load-time axe pass cannot see any of it, so the defects in those states are
invisible to every other pipeline here.

This probe operates the page's controls one at a time and re-runs axe
whenever a click actually changed the DOM. It is deliberately conservative:
it never clicks anything whose accessible name matches a destructive word,
it queues navigation for the crawler, and it is bounded on four
independent axes (total clicks, repeats of one structural shape, recursion
depth and elapsed time) so a calendar with 365 day cells cannot turn one page into an
afternoon.

**Only new markup is reported.** The caller passes the load-state
violations as ``baseline``; every hash seen is remembered as exploration
proceeds. A violation on the site header is found once, at load, and never
again — not once per click, and not once per revealed state. That filtering
happens here rather than being left to the database's unique constraint so
the crawl does not pay for hundreds of redundant upserts per page.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from audit.analyzer.axe import AxeAnalyzer, AxeViolation, Level
from audit.analyzer.interaction.base import InteractionResult, RevealedViolation
from audit.analyzer.interaction.safety import exploration_guard, safe_url
from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Locator, Page

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
    "subscribe",
    "subscription",
    "purchase",
    "buy now",
    "checkout",
    "check out",
    "pay",
    "buy",
    "add to cart",
    "book now",
    "reserve now",
    "place bid",
    "redeem",
    "enroll",
    "register",
    "sign up",
    "signup",
    "create account",
    "authorize",
    "revoke",
    "disconnect",
    "install",
    "accept invitation",
    "agree",
    "pay now",
    "payment",
    "place order",
    "donate",
    "transfer",
    "withdraw",
    "upload",
    "download",
    "submit",
    "save",
    "send",
    "publish",
    "invite",
    "reset password",
    "change password",
    "confirm",
    "approve",
    "accept all",
    "grant access",
    "connect account",
    "start trial",
    "upgrade",
)

# Native and explicitly semantic controls, including controls implemented as
# placeholder anchors. Real links remain the crawler's responsibility.
_CANDIDATE_SELECTOR = (
    'button, input[type="button"], input[type="checkbox"], input[type="radio"], '
    '[role="button"], [role="tab"], [role="menuitem"], [role="menuitemcheckbox"], '
    '[role="menuitemradio"], [role="treeitem"], [role="option"], '
    '[role="switch"], [role="checkbox"], [role="radio"], '
    "details > summary, [aria-expanded], [aria-haspopup], [onclick], [tabindex]"
)

# Keep identity separate from the repeat-sampling shape. A broad selector such
# as button.card must never be passed to .first(): that re-clicks card one
# while claiming to have tested every card. Paths also distinguish equal names.
_DESCRIBE_JS = r"""
(el) => {
  const esc = s => CSS.escape(s);
  const style = getComputedStyle(el);
  if (!el.getClientRects().length || style.visibility !== 'visible' ||
      el.closest('[inert], [aria-hidden="true"]') || el.matches(':disabled') ||
      el.getAttribute('aria-disabled') === 'true') return null;
  const anchor = el.closest('a');
  if (anchor && (anchor.hasAttribute('download') ||
      !['', '#'].includes(anchor.getAttribute('href') || ''))) return null;
  const tag = el.tagName.toLowerCase();
  const role = el.getAttribute('role') || '';
  // Focusable widget containers and focus targets are not themselves
  // actions. Custom menu entries often have tabindex but no valid ARIA
  // role (precisely one of the defects the auditor must still reach).
  if (['listbox', 'menu', 'menubar', 'tablist', 'tree', 'grid'].includes(role)) return null;
  if (el.hasAttribute('tabindex') && !el.matches(
      'button, input[type="button"], input[type="checkbox"], input[type="radio"], ' +
      '[role="button"], [role="tab"], [role="menuitem"], [role="menuitemcheckbox"], ' +
      '[role="menuitemradio"], [role="treeitem"], [role="option"], [role="switch"], ' +
      '[role="checkbox"], [role="radio"], summary, [aria-expanded], [aria-haspopup], [onclick]'
  )) {
    if (['input', 'textarea', 'select'].includes(tag) || el.isContentEditable) return null;
    if (style.cursor !== 'pointer' && !el.parentElement?.closest(
        '[role="listbox"], [role="menu"], [role="menubar"], [role="tree"]')) return null;
  }
  if (tag === 'select' || ['file', 'submit', 'reset', 'password', 'hidden'].includes(el.type)) {
    // A plain button outside a form has type=submit but cannot submit anything.
    if (!(tag === 'button' && !el.form && el.type === 'submit')) return null;
  }
  const labelled = (el.getAttribute('aria-labelledby') || '').split(/\s+/)
    .map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
  const label = (labelled || el.getAttribute('aria-label') ||
      Array.from(el.labels || []).map(l => l.textContent).join(' ') ||
      el.textContent || el.getAttribute('value') || el.getAttribute('title') || '')
    .replace(/\s+/g, ' ').trim();
  let node = el;
  const parts = [];
  while (node && node.nodeType === 1) {
    if (node.id && document.querySelectorAll('#' + esc(node.id)).length === 1) {
      parts.unshift('#' + esc(node.id)); break;
    }
    let index = 1;
    for (let prev = node.previousElementSibling; prev; prev = prev.previousElementSibling)
      if (prev.tagName === node.tagName) index++;
    parts.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + index + ')');
    node = node.parentElement;
  }
  const classes = typeof el.className === 'string' ?
    el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2) : [];
  return {
    selector: parts.join(' > '), tag, label: label.slice(0, 300),
    safetyLabel: [label, el.getAttribute('title'), el.getAttribute('name'),
      el.id, el.getAttribute('formaction')].filter(Boolean).join(' ').slice(0, 4000),
    shape: tag + (el.id ? '#' + el.id : '.' + classes.join('.')),
    isGlobal: !!el.closest('header, nav, footer, [role="banner"], [role="navigation"]'),
    fresh: !el.__axcessSeen,
  };
}
"""
_COLLECT_JS = (
    "(sel) => Array.from(document.querySelectorAll(sel)).slice(0, 2000).map("
    + _DESCRIBE_JS
    + ").filter(Boolean)"
)
_MARK_JS = (
    "(sel) => { for (const el of document.querySelectorAll(sel)) { if (("
    + _DESCRIBE_JS
    + ")(el)) el.__axcessSeen = true; } }"
)
_RESET_MARKS_JS = (
    "(sel) => { for (const el of document.querySelectorAll(sel)) delete el.__axcessSeen; }"
)

# A modal covers the page. Until it is closed, a click aimed at anything
# underneath lands on the overlay instead, so a sweep that keeps going past
# an open modal reports controls it never actually operated.
#
# Modality is read from the two declarations that define it: aria-modal, and
# a native <dialog> opened with showModal(). A role="dialog" without either
# is NOT modal — it sits in the page like any other panel and blocks nothing,
# so halting on one would throw away the rest of a page for no reason. (A
# dialog that behaves modally without declaring it is its own defect, and one
# this check will not see.) Identity is a JS expando rather than an
# attribute: attributes serialize into the stored HTML and change its hash.
_OPEN_DIALOGS_JS = r"""
() => {
  const out = [];
  const nodes = document.querySelectorAll(
    'dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]');
  for (const el of nodes) {
    const style = getComputedStyle(el);
    if (!el.getClientRects().length || style.visibility === 'hidden' ||
        style.display === 'none' || el.closest('[inert]')) continue;
    let modal = el.getAttribute('aria-modal') === 'true';
    if (!modal && el.tagName === 'DIALOG') {
      try { modal = el.matches(':modal'); } catch (e) { modal = false; }
    }
    if (!modal) continue;
    if (!el.__axcessDialog) {
      el.__axcessDialog = 'dlg' + Math.random().toString(36).slice(2, 10);
    }
    let node = el;
    const parts = [];
    while (node && node.nodeType === 1) {
      if (node.id && document.querySelectorAll('#' + CSS.escape(node.id)).length === 1) {
        parts.unshift('#' + CSS.escape(node.id)); break;
      }
      let index = 1;
      for (let prev = node.previousElementSibling; prev; prev = prev.previousElementSibling)
        if (prev.tagName === node.tagName) index++;
      parts.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + index + ')');
      node = node.parentElement;
    }
    out.push({
      id: el.__axcessDialog,
      selector: parts.join(' > '),
      label: (el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 120),
      snippet: el.outerHTML.slice(0, 400),
    });
  }
  return out;
}
"""

# Only unambiguously dismissive names. "OK", "Done" and "Continue" are left
# out on purpose: on a confirmation dialog those are the button that performs
# the action, and pressing one to tidy up the DOM is exactly the consequential
# click the rest of this module exists to avoid.
# The three glyphs are the real close-button characters, not the letter x.
_CLOSE_WORDS = (
    "close",
    "cancel",
    "dismiss",
    "no thanks",
    "not now",
    "go back",
    "×",  # noqa: RUF001 - MULTIPLICATION SIGN, the usual close glyph
    "✕",
    "✖",
)
_CLOSE_CONTROL_JS = (
    r"""
(args) => {
  const [id, words] = args;
  let dialog = null;
  for (const el of document.querySelectorAll('*')) {
    if (el.__axcessDialog === id) { dialog = el; break; }
  }
  if (!dialog) return null;
  const describe = """
    + _DESCRIBE_JS
    + r""";
  for (const el of dialog.querySelectorAll('button, [role="button"], [aria-label], a')) {
    const info = describe(el);
    if (!info) continue;
    const name = (info.label || el.getAttribute('aria-label') || '')
      .replace(/\s+/g, ' ').trim().toLowerCase();
    if (!name || name.length > 40) continue;
    if (!words.some(word => name === word || name.includes(word))) continue;
    return info;
  }
  return null;
}
"""
)

DEFAULT_MAX_CLICKS = 100
DEFAULT_MAX_REPEATED = 20
DEFAULT_MAX_DEPTH = 5
DEFAULT_TIMEOUT_S = 120.0

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
    # Clicks that actually changed the DOM. Each one is a state of the page
    # that a load-time pass cannot reach, whether or not it contained a
    # defect — which makes it the honest measure of what interaction added
    # to a scan's coverage.
    states_found: int = 0
    clicks_succeeded: int = 0
    # Distinct controls, keyed like ``seen_keys``. A blocked control can be
    # met in more than one sweep and a control can be clicked more than once
    # when a menu has to be reopened, so both are sets: counters here would
    # report more controls than the page has.
    operated_keys: set[str] = field(default_factory=set)
    blocked_keys: set[str] = field(default_factory=set)
    #: Dialogs a click opened, and the count that would not close again.
    dialogs_opened: int = 0
    dialogs_stuck: int = 0
    #: Set once a dialog refuses to close. Everything under it is
    #: unreachable, so the page's sweep stops rather than clicking an
    #: overlay and recording the result as coverage.
    halted: bool = False
    #: Reproduction detail for the first stuck dialog, bounded for storage.
    detail: str = ""
    limits: set[str] = field(default_factory=set)
    urls: set[str] = field(default_factory=set)
    # Every control this page exposed, including the ones a click revealed
    # and the ones that were then refused or capped. Keyed the same way as
    # ``seen_keys`` so a control found again in a later sweep is one control,
    # which is what makes "operated N of M" a ratio rather than two
    # unrelated numbers.
    discovered_keys: set[str] = field(default_factory=set)


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
    max_clicks: int = DEFAULT_MAX_CLICKS
    # How many controls sharing one structural shape to sample.
    max_repeated: int = DEFAULT_MAX_REPEATED
    # How deep to follow "clicking this revealed more things to click".
    max_depth: int = DEFAULT_MAX_DEPTH
    timeout_s: float = DEFAULT_TIMEOUT_S
    # Time for a revealed state to settle (animations, async content).
    settle_ms: int = 400
    blocked_labels: tuple[str, ...] = DEFAULT_BLOCKED_LABELS

    async def run(self, page: Page, *, baseline: Sequence[AxeViolation] = ()) -> InteractionResult:
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
        evaluated = False
        try:
            async with exploration_guard(page, budget.urls, self.blocked_labels):
                async with asyncio.timeout(self.timeout_s):
                    await page.evaluate(_RESET_MARKS_JS, _CANDIDATE_SELECTOR)
                    evaluated = True
                    await self._explore(
                        page, budget, found, pinned=page.url, depth=0, fresh_only=False
                    )
        except TimeoutError:
            budget.limits.add("time")
            log.info("interaction.limited", reason="time_limit")
        except Exception as exc:
            # A probe is evidence-gathering, not a gate. Whatever we managed
            # to reach before something went wrong is still valid evidence.
            log.warning("interaction.aborted", error_type=type(exc).__name__)
        if budget.remaining <= 0:
            budget.limits.add("clicks")
        log.info(
            "interaction.coverage",
            controls_discovered=len(budget.discovered_keys),
            clicks_attempted=self.max_clicks - budget.remaining,
            clicks_succeeded=budget.clicks_succeeded,
            controls_operated=len(budget.operated_keys),
            states=budget.states_found,
            blocked_controls=len(budget.blocked_keys),
            dialogs_opened=budget.dialogs_opened,
            dialogs_stuck=budget.dialogs_stuck,
            limits=sorted(budget.limits),
        )
        if found:
            log.info(
                "interaction.revealed",
                violations=len(found),
                clicks_used=self.max_clicks - budget.remaining,
            )
        return InteractionResult(
            findings=tuple(found),
            states=budget.states_found,
            urls=tuple(sorted(budget.urls)),
            evaluated=evaluated,
            controls_discovered=len(budget.discovered_keys),
            clicks_attempted=self.max_clicks - budget.remaining,
            clicks_succeeded=budget.clicks_succeeded,
            controls_operated=len(budget.operated_keys),
            blocked_controls=len(budget.blocked_keys),
            limits=tuple(sorted(budget.limits)),
            dialogs_opened=budget.dialogs_opened,
            dialogs_stuck=budget.dialogs_stuck,
            detail=budget.detail,
        )

    async def _explore(
        self,
        page: Page,
        budget: _Budget,
        found: list[RevealedViolation],
        *,
        pinned: str,
        depth: int,
        fresh_only: bool,
        path: tuple[dict[str, Any], ...] = (),
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
        if budget.remaining <= 0 or budget.halted:
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
        # Count what this level exposed before any bound is applied. A
        # control that the depth cap, the repeat cap or the label filter
        # stops us reaching is still a control the page has and this scan
        # did not exercise; hiding it would make coverage look complete.
        for control in controls:
            budget.discovered_keys.add(self._interaction_key(control, pinned))
        if depth >= self.max_depth:
            if controls:
                budget.limits.add("depth")
            return

        for control in controls:
            if budget.remaining <= 0 or budget.halted:
                break
            if self._is_blocked(control.get("safetyLabel", control["label"])):
                budget.blocked_keys.add(self._interaction_key(control, pinned))
                log.info(
                    "interaction.refused",
                    control=str(control["label"])[:60],
                    reason="blocked_label",
                )
                continue

            key = self._interaction_key(control, pinned)
            if key in budget.seen_keys:
                continue

            signature = _signature(control.get("shape", control["selector"]))
            shape = f"{'GLOBAL' if control['isGlobal'] else pinned}|{signature}"
            if budget.signature_counts.get(shape, 0) >= self.max_repeated:
                budget.limits.add("repeated_controls")
                continue

            # Claim the control BEFORE operating it. _operate recurses into a
            # nested sweep of whatever the click reveals; if the claim landed
            # afterwards that sweep would still see this control as untouched
            # and click it again. An end-to-end run caught exactly that: one
            # "Add another guest" button pressed three times, three inputs
            # appended, one defect reported as three findings.
            budget.seen_keys.add(key)
            budget.signature_counts[shape] = budget.signature_counts.get(shape, 0) + 1

            await self._operate(page, budget, found, control, pinned=pinned, depth=depth, path=path)

    async def _resolve_control(self, page: Page, control: dict[str, Any]) -> Locator | None:
        """Resolve the same action again after a framework replaces its menu.

        Prefer the exact DOM location. A recreated portal can get a new ID;
        then require one unambiguous match by tag, label and structural shape.
        Never fall back to the first button or an arbitrary duplicate name.
        """
        locator = page.locator(control["selector"])
        count = await locator.count()
        if count:
            if count != 1 or not await locator.is_visible():
                return None
            current = await locator.evaluate(_DESCRIBE_JS)
            if current and current["label"] == control["label"]:
                return None if self._is_blocked(current["safetyLabel"]) else locator
            return None
        controls = await page.evaluate(_COLLECT_JS, _CANDIDATE_SELECTOR)
        matches = [
            item
            for item in controls
            if item["tag"] == control["tag"]
            and item["label"] == control["label"]
            and _signature(item["shape"]) == _signature(control["shape"])
            and not self._is_blocked(item["safetyLabel"])
        ]
        if len(matches) != 1:
            return None
        return page.locator(matches[0]["selector"])

    async def _reopen_path(
        self,
        page: Page,
        budget: _Budget,
        control: dict[str, Any],
        path: tuple[dict[str, Any], ...],
        *,
        pinned: str,
    ) -> Locator | None:
        """Replay only missing ancestors, charging every replay to the budget."""
        for index, ancestor in enumerate(path):
            next_control = path[index + 1] if index + 1 < len(path) else control
            if await self._resolve_control(page, next_control) is not None:
                continue
            if budget.remaining <= 0:
                return None
            opener = await self._resolve_control(page, ancestor)
            if opener is None:
                return None
            budget.remaining -= 1
            await opener.click(timeout=3000)
            budget.clicks_succeeded += 1
            await page.wait_for_timeout(self.settle_ms)
            if page.url != pinned:
                if safe_url(page.url, self.blocked_labels) and len(budget.urls) < 1000:
                    budget.urls.add(page.url)
                await self._restore(page, pinned)
                return None
            log.info("interaction.reopened", control=ancestor["label"][:60], depth=index)
        return await self._resolve_control(page, control)

    def _is_blocked(self, label: str) -> bool:
        lowered = re.sub(r"[-_]+", " ", label).casefold()
        return any(
            re.sub(r"[-_]+", " ", word).casefold() in lowered for word in self.blocked_labels
        )

    def _interaction_key(self, control: dict[str, Any], pinned: str) -> str:
        """Distinct DOM locations remain distinct even when names match.

        The budget is per page run, including navigation controls. Nothing is
        deduplicated across pages: the same menu can expose different content.
        """
        scope = "GLOBAL" if control["isGlobal"] else pinned
        return f"{scope}|{control['selector']}|{control['label']}"

    async def _operate(
        self,
        page: Page,
        budget: _Budget,
        found: list[RevealedViolation],
        control: dict[str, Any],
        *,
        pinned: str,
        depth: int,
        path: tuple[dict[str, Any], ...] = (),
    ) -> bool:
        """Click one control; record anything new it revealed.

        Each candidate is attempted once; failed attempts remain bounded.
        """
        selector = control["selector"]
        label = control["label"] or f"<{control['tag']}>"
        try:
            locator = await self._resolve_control(page, control)
            if locator is None and path:
                locator = await self._reopen_path(page, budget, control, path, pinned=pinned)
            if locator is None or budget.remaining <= 0:
                log.info("interaction.unreachable", control=label[:60], depth=depth)
                return False

            # Everything operable right now is "old". Whatever the click
            # makes operable will be the only unmarked set afterwards, which
            # is exactly what the nested sweep descends into.
            await page.evaluate(_MARK_JS, _CANDIDATE_SELECTOR)

            before_hash = await page.evaluate(_DOM_HASH_JS)
            before_dialogs = {item["id"] for item in await self._open_dialogs(page)}
            budget.remaining -= 1
            await locator.click(timeout=3000)
            budget.clicks_succeeded += 1
            budget.operated_keys.add(self._interaction_key(control, pinned))
            with contextlib.suppress(Exception):
                await page.wait_for_function(
                    "before => (" + _DOM_HASH_JS + ")() !== before",
                    arg=before_hash,
                    timeout=max(1000, self.settle_ms),
                )
            await page.wait_for_timeout(self.settle_ms)

            # A click that navigated is out of this probe's remit: the page
            # it landed on belongs to the crawl frontier, which owns scope,
            # robots, and rate limiting. Undo it and carry on where we were.
            if page.url != pinned:
                if safe_url(page.url, self.blocked_labels) and len(budget.urls) < 1000:
                    budget.urls.add(page.url)
                log.info(
                    "interaction.clicked",
                    control=label[:60],
                    selector=selector[:80],
                    depth=depth,
                    outcome="navigated",
                )
                await self._restore(page, pinned)
                return True

            after_hash = await page.evaluate(_DOM_HASH_JS)
            if before_hash == after_hash:
                log.info(
                    "interaction.clicked",
                    control=label[:60],
                    selector=selector[:80],
                    depth=depth,
                    outcome="no_dom_change",
                )
                return True  # inert control; spent, but nothing to scan

            budget.states_found += 1
            # Recorded here rather than after the nested sweep: exploring a
            # dialog can click its own close control, and a dialog that
            # closed itself is still a dialog this click opened.
            opened = [
                item for item in await self._open_dialogs(page) if item["id"] not in before_dialogs
            ]
            budget.dialogs_opened += len(opened)
            # Links can be created by menus/dialogs after the load-time
            # snapshot. Keep them for the crawler's normal scope checks.
            links = await page.locator("a[href]").evaluate_all(
                "nodes => nodes.slice(0, 1000).map(n => n.href).filter(u => u.length <= 2048)"
            )
            for url in links:
                if (
                    isinstance(url, str)
                    and safe_url(url, self.blocked_labels)
                    and len(budget.urls) < 1000
                ):
                    budget.urls.add(url)
            before_found = len(found)
            await self._collect(page, budget, found, label)
            log.info(
                "interaction.clicked",
                control=label[:60],
                selector=selector[:80],
                depth=depth,
                outcome="dom_changed",
                new_violations=len(found) - before_found,
            )

            # Whatever this click opened may itself contain controls. Only
            # those: fresh_only keeps the descent inside what appeared.
            await self._explore(
                page,
                budget,
                found,
                pinned=pinned,
                depth=depth + 1,
                fresh_only=True,
                path=(*path, control),
            )

            # A dialog is not a menu. Whatever depth opened it, it has to be
            # closed before the next control is touched, because its overlay
            # sits over every one of them. Verified, not assumed: an
            # unverified Escape is how a sweep ends up reporting clicks that
            # only ever hit an overlay. Dialogs the nested sweep already
            # closed need nothing further.
            still_open = {item["id"] for item in await self._open_dialogs(page)}
            for dialog in [item for item in opened if item["id"] in still_open]:
                if not await self._dismiss_dialog(page, budget, dialog, opener=label, depth=depth):
                    return True

            # Close the state we opened so the next sibling is reachable.
            # Escaping every nested click can close the ancestor menu and
            # hide all its remaining siblings. Unwind at the root only, and
            # not when a dialog was already dismissed above.
            if depth == 0 and not opened:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(150)
            return True

        except Exception as exc:
            log.debug("interaction.click_failed", label=label[:40], error_type=type(exc).__name__)
            # If the failure left the browser somewhere else, get back.
            if page.url != pinned:
                await self._restore(page, pinned)
            return True

    async def _open_dialogs(self, page: Page) -> list[dict[str, Any]]:
        try:
            dialogs: list[dict[str, Any]] = await page.evaluate(_OPEN_DIALOGS_JS)
        except Exception:
            return []
        return dialogs

    async def _dismiss_dialog(
        self,
        page: Page,
        budget: _Budget,
        dialog: dict[str, Any],
        *,
        opener: str,
        depth: int,
    ) -> bool:
        """Close a dialog this click opened, and verify that it actually went.

        Escape first, then the dialog's own close control if it has one whose
        name is unambiguously a dismissal. Returns False when the dialog is
        still there afterwards, which ends the page: a modal overlays
        everything, so the clicks that would follow it land on the overlay
        and any coverage recorded for them would be a fiction.
        """
        attempts: list[str] = []

        async def still_open() -> bool:
            await page.wait_for_timeout(self.settle_ms)
            return any(item["id"] == dialog["id"] for item in await self._open_dialogs(page))

        with contextlib.suppress(Exception):
            await page.keyboard.press("Escape")
            attempts.append("Escape")
            if not await still_open():
                return True

        control = None
        with contextlib.suppress(Exception):
            control = await page.evaluate(_CLOSE_CONTROL_JS, [dialog["id"], list(_CLOSE_WORDS)])
        if control and not self._is_blocked(control.get("safetyLabel", control["label"])):
            name = str(control["label"])[:40]
            with contextlib.suppress(Exception):
                if budget.remaining > 0:
                    budget.remaining -= 1
                    await page.locator(control["selector"]).click(timeout=3000)
                    # A dismissal is housekeeping, not coverage: it counts as
                    # a dispatched click but never as another control
                    # operated, so "operated N of M" cannot exceed M.
                    budget.clicks_succeeded += 1
                    attempts.append(f'"{name}"')
                    if not await still_open():
                        return True

        budget.dialogs_stuck += 1
        budget.halted = True
        budget.limits.add("dialog_not_dismissed")
        named = dialog["label"] or dialog["selector"]
        tried = ", ".join(attempts) or "no safe dismissal control"
        if not budget.detail:
            budget.detail = (
                f'Dialog "{named}" opened by "{opener[:40]}" did not close '
                f"(tried {tried}); page exploration stopped."
            )[:200]
        log.warning(
            "interaction.dialog_stuck",
            dialog=str(named)[:60],
            opener=opener[:60],
            attempted=attempts,
            depth=depth,
        )
        return False

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
            log.debug("interaction.axe_failed", error_type=type(exc).__name__)
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
