"""The mouse-vs-keyboard differential: does the keyboard reproduce what the mouse did?

This is the oracle. For one probe we perform the mouse action, record the
effect, discard the world, perform a keyboard action, record that effect, and
compare.

What a negative result licenses is narrower than it looks. If the mouse achieved
something and none of the **keys we tried** reproduced it **on the channels we
observe**, that is evidence of a missing keyboard route — not proof that none
exists. A different key, a modifier chord, or an effect on a channel we do not
watch would all be invisible here. Findings are leads for a human reviewer, and
the report states the tried-key set and the observed channels alongside them.

Four departures from upstream's implementation, each fixing a defect we located
in their source and recorded in the shared log:

1. **A fresh browser context per trial.** They called ``page.goto`` twice on one
   page, so ``localStorage`` written by the mouse survived into the keyboard
   run. An idempotent write then produced no observable change on the keyboard
   pass and the probe scored a false violation. Every trial here starts from a
   context with empty storage.
2. **The keyboard baseline is taken one stop short of the target.** They
   snapshotted before the whole Tab walk, so every focus side effect of every
   element walked past was attributed to the probe. Baselining *after* focus
   lands is wrong in the other direction — it hides the target's own
   focus-triggered reveal, and a ``:focus-within`` menu that genuinely works
   gets reported as a defect. Focusing is itself a keyboard action, so the
   measured window covers the final Tab plus the keypress and nothing else.
3. **One key per trial.** They pressed Enter, Space and ArrowDown in sequence
   against one mutable page. A control that opens on Enter and closes on Space
   nets to no change and scores as a false violation. Each key gets its own
   pristine trial.
4. **Effects are compared, not counted.** Their verdict was "mouse changed
   something and keyboard changed nothing", so an unrelated console warning on
   the keyboard pass silently cleared a real defect. We require the keyboard to
   reproduce the *same* effect payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.async_api import BrowserContext, Page

from audit.analyzer.keyboard.kbdiff import channels, coverage
from audit.analyzer.keyboard.kbdiff.model import (
    Effect,
    ModalityResult,
    ProbeOutcome,
    Uncertainty,
    decide,
)
from audit.analyzer.keyboard.kbdiff.taborder import (
    _ACTIVE_PROBE_JS,
    TabOrder,
    compute_tab_order,
)
from audit.logging import get_logger

log = get_logger(__name__)

# Keys a sighted keyboard user would try on something that looks operable.
# Each is an independent trial; see the module docstring.
DEFAULT_KEYS: tuple[str, ...] = ("Enter", "Space", "ArrowDown")

# Time for handlers, transitions and CSS reveals to settle before we read state.
# Generous rather than tight: a missed effect becomes a false violation, which
# is the expensive error here.
SETTLE_MS = 250

# Locates a probe, scrolls it into view, and works out where a real mouse would
# have to land to hit it. Three problems this solves, each of which silently
# corrupts results if ignored:
#
# 1. **Below the fold.** Geometry is viewport-relative, so on a long page most
#    elements sit outside it. Rejecting those as "not rendered" would mark the
#    majority of a realistic page unmeasurable — the fixture corpus never caught
#    this because its pages are short. We scroll first, then measure.
# 2. **The centre point can miss the element.** An inline element that wraps
#    across lines has a bounding box spanning the gap between them, and its
#    centre can land in that gap. Clicking there hits the paragraph, the probe
#    does nothing, and it scores as a passing element. We walk `getClientRects()`
#    and pick a point that actually hit-tests back to the target.
# 3. **A click we could not deliver is not a click that did nothing.** If none
#    of the points we sample hit-tests back to the target, we cannot place a
#    mouse on it, so no mouse trial happened. Upstream inferred "not keyboard
#    reachable" from the resulting absence of effect; we record the failure as
#    a failed measurement and name whatever intercepted, so the reason travels
#    with it. The sampled points are a finite set, so this is evidence that we
#    could not aim, not proof that no user could click.
#
# It also keeps the visibility gate upstream's ``isVisible()`` got most of the
# way to, plus the two cases their study named as an available fix and left
# unimplemented: ``inert`` subtrees and ``pointer-events: none``.
_LOCATE_JS = """
(probeId) => {
  const findDeep = (root, id) => {
    const direct = root.querySelector('[data-probe="' + id + '"]');
    if (direct) return direct;
    const all = root.querySelectorAll('*');
    for (const el of all) {
      if (el.shadowRoot) {
        const hit = findDeep(el.shadowRoot, id);
        if (hit) return hit;
      }
    }
    return null;
  };
  const el = findDeep(document, probeId);
  if (!el) return { found: false };

  const cs = getComputedStyle(el);
  const reasons = [];
  if (cs.display === 'none') reasons.push('display:none');
  if (cs.visibility === 'hidden') reasons.push('visibility:hidden');
  if (el.disabled) reasons.push('disabled');
  if (cs.pointerEvents === 'none') reasons.push('pointer-events:none');
  if (el.closest && el.closest('[inert]')) reasons.push('inert');

  // Bring it into view before measuring. 'instant' matters: a smooth scroll is
  // still animating when we read the box, and we would aim at a stale position.
  try {
    el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
  } catch (e) {
    try { el.scrollIntoView(); } catch (e2) {}
  }

  const rect = el.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) reasons.push('zero-size');

  const vw = window.innerWidth, vh = window.innerHeight;
  const hits = (x, y) => {
    if (x < 0 || y < 0 || x > vw || y > vh) return null;
    const doc = el.getRootNode() === document ? document : el.getRootNode();
    return (doc.elementFromPoint || document.elementFromPoint).call(doc, x, y);
  };
  const isSelf = (at) => !!at && (at === el || el.contains(at));

  // Candidate aim points, in order of preference:
  //   1. the centre of the whole bounding box;
  //   2. the centre of each individual client rect, which is what a wrapped
  //      inline element needs -- its box spans the gap between lines;
  //   3. device-pixel-snapped variants, because a 1x1 target's centre can land
  //      exactly on a boundary and hit-test to the parent instead. Sub-pixel
  //      targets are themselves an accessibility smell and must still measure.
  const points = [];
  const addRect = (r) => {
    if (!r || (r.width === 0 && r.height === 0)) return;
    const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
    points.push([cx, cy]);                                   // the obvious point
    points.push([Math.floor(cx) + 0.5, Math.floor(cy) + 0.5]); // device-pixel centre
    points.push([r.x, r.y]);                                 // the origin
    points.push([r.x + Math.min(r.width, 1) * 0.25,
                 r.y + Math.min(r.height, 1) * 0.25]);       // just inside it
  };
  addRect(rect);
  try {
    for (const r of el.getClientRects()) addRect(r);
  } catch (e) {}

  // A zero-sized control yields no rects at all, so there is no point to aim
  // at. Falling through here dereferenced points[0] and threw, which surfaced
  // as an *instrument error* -- an internal fault indistinguishable from a
  // browser problem -- when the truth is simply that nothing is rendered.
  // Return that cleanly instead.
  if (points.length === 0) {
    if (reasons.indexOf('zero-size') === -1) reasons.push('zero-size');
    return {
      found: true,
      reasons,
      x: null,
      y: null,
      hit_testable: false,
      occluded_by: null,
      in_viewport: false,
      width: rect.width,
      height: rect.height,
      tag: el.tagName.toLowerCase(),
      html: (el.outerHTML || '').slice(0, 400),
    };
  }

  let chosen = null, blocker = null;
  for (const [x, y] of points) {
    const at = hits(x, y);
    if (isSelf(at)) { chosen = [x, y]; break; }
    if (at && !blocker) blocker = at.tagName.toLowerCase();
  }

  const centre = points[0];  // the true bounding-box centre, for reporting
  return {
    found: true,
    reasons,
    x: chosen ? chosen[0] : centre[0],
    y: chosen ? chosen[1] : centre[1],
    // False when every candidate point hit something else. The caller keeps
    // this on the record rather than discovering it as an absent effect.
    hit_testable: !!chosen,
    occluded_by: chosen ? null : blocker,
    in_viewport: centre[0] >= 0 && centre[1] >= 0 && centre[0] <= vw && centre[1] <= vh,
    width: rect.width,
    height: rect.height,
    tag: el.tagName.toLowerCase(),
    html: (el.outerHTML || '').slice(0, 400),
  };
}
"""


@dataclass(frozen=True)
class TrialConfig:
    """Knobs for one differential run, so the harness can ablate them."""

    url: str
    viewport: str
    keys: tuple[str, ...] = DEFAULT_KEYS
    include_hover: bool = True
    settle_ms: int = SETTLE_MS
    max_tabs: int = 300
    # V8 precise coverage costs a CDP round trip per trial and is only needed to
    # evaluate upstream's coverage-based Stage 4. Off by default so runs made
    # before it existed stay directly comparable.
    collect_coverage: bool = False


class DifferentialRunner:
    """Runs differentials for one page, one viewport, in fresh contexts.

    The caller owns the browser; this owns each short-lived context. The
    per-trial context is the whole point (see fix 1 in the module docstring) and
    is also what makes the run order-independent: no trial can contaminate the
    next through storage, cookies or a service worker.
    """

    def __init__(
        self,
        make_context: Any,
        config: TrialConfig,
    ) -> None:
        # ``make_context`` is an async callable returning a fresh BrowserContext
        # with the right viewport and fixture routing already installed. Kept as
        # a callable so the harness controls routing policy, not this module.
        self._make_context = make_context
        self._config = config

    async def _fresh_page(self) -> tuple[BrowserContext, Page, Any]:
        """A new context, instrumented at document-start, on the target URL.

        Returns the CDP session too when coverage is on, so the caller can arm
        the profiler after load and read executed functions after the action.
        """
        context: BrowserContext = await self._make_context()
        await context.add_init_script(channels.INIT_SCRIPT)
        page = await context.new_page()
        cdp = None
        if self._config.collect_coverage:
            cdp = await context.new_cdp_session(page)
        await page.goto(self._config.url, wait_until="load")
        await page.wait_for_timeout(80)
        if cdp is not None:
            await coverage.start(cdp)
            # Discard everything executed up to now: only the action's own
            # functions should count.
            await coverage.take(cdp)
        return context, page, cdp

    async def tab_order(self) -> TabOrder:
        """Set T for this page and viewport, computed in its own context."""
        context, page, _ = await self._fresh_page()
        try:
            return await compute_tab_order(page, max_tabs=self._config.max_tabs)
        finally:
            await context.close()

    async def run_probe(self, probe_id: str, page_name: str, order: TabOrder) -> ProbeOutcome:
        """Measure one probe end to end and return its verdict."""
        mouse = await self._mouse_trial(probe_id)

        keyboard: dict[str, ModalityResult] = {}
        position = order.position(probe_id)
        if position is not None:
            for key in self._config.keys:
                keyboard[key] = await self._key_trial(probe_id, key, position)
        elif order.capped:
            # We never got far enough to try. Not a pass, not a fail.
            keyboard["(none)"] = ModalityResult(
                attempted=False,
                note="probe not reached before the tab cap",
                uncertainty=Uncertainty.TAB_CAP,
            )
        else:
            keyboard["(none)"] = ModalityResult(
                attempted=False,
                note="probe is not in the tab order; no key could be delivered to it",
            )

        return decide(
            probe_id,
            page_name,
            self._config.viewport,
            in_tab_order=position is not None,
            tab_index=position,
            mouse=mouse,
            keyboard_by_key=keyboard,
        )

    async def _mouse_trial(self, probe_id: str) -> ModalityResult:
        """Click the probe with a trusted mouse event and record the effect.

        Uses real pointer input rather than ``element.click()``. A trusted click
        hit-tests: it hits whatever is actually on top at those coordinates, so
        an element hidden under a transparent overlay correctly fails to
        activate. ``element.click()`` bypasses hit-testing entirely and reports
        success on elements no user could operate.
        """
        context, page, cdp = await self._fresh_page()
        try:
            located = await page.evaluate(_LOCATE_JS, probe_id)
            if not located.get("found"):
                return ModalityResult(
                    attempted=False,
                    note="probe id matched no node",
                    uncertainty=Uncertainty.UNRESOLVED,
                )
            reasons = located.get("reasons") or []
            if reasons:
                # Not mouse-operable either, so it cannot be a keyboard defect.
                # Upstream reported three false positives of exactly this shape.
                return ModalityResult(
                    attempted=False,
                    note=f"not mouse-operable: {', '.join(reasons)}",
                    uncertainty=Uncertainty.NOT_RENDERED,
                )

            # The locator has already scrolled the element into view, so an
            # element that is *still* outside the viewport is genuinely
            # off-canvas — the `left: -9999px` visually-hidden pattern, say —
            # rather than merely further down a long page.
            if not located.get("in_viewport"):
                return ModalityResult(
                    attempted=False,
                    note="off-canvas: still outside the viewport after scrolling into view",
                    uncertainty=Uncertainty.NOT_RENDERED,
                )

            if not located.get("hit_testable", True):
                # Every point we sampled hit something else, so we could not
                # deliver a click and no mouse trial took place. That is a
                # failed measurement, not a definite negative: the sample is a
                # handful of points, and a user aiming elsewhere in the box may
                # well reach it. `decide` therefore reports UNKNOWN rather than
                # clearing the probe — but we can still name what intercepted.
                blocker = located.get("occluded_by") or "another element"
                return ModalityResult(
                    attempted=False,
                    note=f"not mouse-operable: occluded by <{blocker}>",
                    uncertainty=Uncertainty.NOT_RENDERED,
                )

            x, y = float(located["x"]), float(located["y"])
            before = await page.evaluate(channels.SNAPSHOT_JS)
            if self._config.include_hover:
                # A trusted click cannot skip the hover: the browser dispatches
                # mousemove to the coordinates first. Doing it explicitly lets a
                # CSS-only :hover reveal settle before the press.
                await page.mouse.move(x, y)
                await page.wait_for_timeout(self._config.settle_ms)
            await page.mouse.click(x, y, delay=20)
            await page.wait_for_timeout(self._config.settle_ms)

            # Read with the pointer still resting on the element, so a pure-CSS
            # hover menu is still open when we look. Parking first loses it.
            after = await page.evaluate(channels.SNAPSHOT_JS)
            executed = await coverage.take(cdp) if cdp is not None else frozenset()
            return ModalityResult(
                attempted=True, effect=channels.diff(before, after), coverage=executed
            )
        except Exception as exc:
            log.info("kbdiff.mouse_trial_failed", probe=probe_id, error=str(exc)[:160])
            return ModalityResult(
                attempted=False,
                note=f"instrument error: {exc!s}"[:200],
                uncertainty=Uncertainty.INSTRUMENT_ERROR,
            )
        finally:
            await context.close()

    async def _key_trial(self, probe_id: str, key: str, position: int) -> ModalityResult:
        """Tab to the probe in a pristine context, then press exactly one key.

        Before the key is delivered, the actually-focused element is checked
        against the requested probe. Set T is measured on a separate page load,
        so any render difference between the two — a late-loading font shifting
        layout, a control appearing asynchronously — puts the walk one stop off,
        and the key lands on the wrong element. Without the check that produces a
        confident verdict about an element we never touched. A mismatch is
        ``UNKNOWN``.

        The baseline is taken **one stop short of the target**, so the recorded
        effect covers focusing the probe *and* pressing the key, and nothing
        else. Getting this window right is delicate in both directions:

        * Baseline before the whole walk (upstream) attributes the focus side
          effects of every element walked past to this probe.
        * Baseline after focus has already landed — which is what this code did
          first — excludes the target's *own* focus effect, and that is not
          noise. Focusing is a keyboard action. A menu that opens on
          ``:focus-within`` is operable from the keyboard, but with the baseline
          taken after focus arrived the panel was already open, the keypress
          changed nothing, and a correctly accessible control was reported as a
          defect.

        Baselining at ``position - 1`` and taking the final Tab as part of the
        measured interaction keeps the target's own focus behaviour in and every
        other element's out.
        """
        context, page, cdp = await self._fresh_page()
        try:
            # No focus reset: this page is freshly navigated, which is the only
            # state from which Tab positions match what Set T recorded. See the
            # table in ``compute_tab_order`` for why every script-side reset is
            # worse than none.
            for _ in range(max(position - 1, 0)):
                await page.keyboard.press("Tab")
            await page.wait_for_timeout(self._config.settle_ms)

            # Baseline one stop short: everything after this is attributable to
            # the target alone.
            before = await page.evaluate(channels.SNAPSHOT_JS)

            if position >= 1:
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(self._config.settle_ms)

            landed = await page.evaluate(_ACTIVE_PROBE_JS)
            if landed != probe_id:
                return ModalityResult(
                    attempted=False,
                    note=(
                        f"tab walk landed on {landed!r}, not {probe_id!r}; "
                        "the page rendered differently from when Set T was measured"
                    ),
                    uncertainty=Uncertainty.UNRESOLVED,
                )

            await page.keyboard.press(key)
            await page.wait_for_timeout(self._config.settle_ms)
            after = await page.evaluate(channels.SNAPSHOT_JS)
            executed = await coverage.take(cdp) if cdp is not None else frozenset()

            return ModalityResult(
                attempted=True, effect=channels.diff(before, after), coverage=executed
            )
        except Exception as exc:
            log.info("kbdiff.key_trial_failed", probe=probe_id, key=key, error=str(exc)[:160])
            return ModalityResult(
                attempted=False,
                note=f"instrument error: {exc!s}"[:200],
                uncertainty=Uncertainty.INSTRUMENT_ERROR,
            )
        finally:
            await context.close()


def effect_signature(effect: Effect) -> str:
    """A stable string for an effect, used to group equivalent behaviours."""
    parts = []
    for channel in sorted(effect.changed):
        payload = "|".join(effect.payloads.get(channel, ()))
        parts.append(f"{channel}={payload}")
    return ";".join(parts)
