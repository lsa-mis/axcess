"""Set T: the real tab order, by dispatching real Tab presses.

There is no way to compute this statically. ``tabindex`` reorders the sequence,
``display:none`` and ``inert`` remove elements from it, shadow roots and
same-origin frames splice their own sequences in, and browsers disagree at the
edges. The only trustworthy method is to press Tab and see where focus lands,
which is what this does.

Two distinctions upstream's survey confirmed and this preserves:

* ``el.focus()`` tests **focusability**, which is not membership of the tab
  order. A ``tabindex="-1"`` element is focusable by script and is never a tab
  stop. We never call ``focus()`` to establish reachability.
* A traversal that hits its cap has **not** shown the element is unreachable.
  Upstream treated the cap as a negative; :class:`TabOrder` reports it as
  ``capped`` so the caller can score those probes ``UNKNOWN``.
"""

from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Page

from audit.logging import get_logger

log = get_logger(__name__)

# Enough to cross a large page's controls without letting a focus trap spin
# forever. Reported when hit, never silently swallowed.
DEFAULT_MAX_TABS = 300

# Marks a focused element that carries no ``data-probe``. It still occupies a
# position in the sequence, so it advances the counter; there is just nothing to
# record against it. A real probe id can never collide with this because the
# prefix is not valid in the fixture id scheme.
#
# The marker embeds the element's document-order index, which makes it unique.
# Tag name alone is not: a page with two plain ``<a>`` elements in a row would
# produce two identical markers, the cycle check below would read that as
# "focus is back where it started", and the walk would stop after two presses.
# Every probe past that point would then look unreachable, which manufactures
# false violations out of an instrumentation bug.
UNNAMED = "#el:"

# Reads the probe id of whatever is focused, descending through open shadow
# roots. A closed root cannot be reached from script by design; those probes
# resolve through CDP elsewhere and are reported, not hidden.
_ACTIVE_PROBE_JS = """
() => {
  let el = document.activeElement;
  let guard = 0;
  while (el && el.shadowRoot && el.shadowRoot.activeElement && guard++ < 50) {
    el = el.shadowRoot.activeElement;
  }
  if (!el) return null;
  const id = el.getAttribute && el.getAttribute('data-probe');
  if (id) return id;
  // Document-order index makes the marker unique per element, so the caller's
  // cycle check compares positions rather than merely tag names.
  let index = -1;
  try {
    const all = (el.ownerDocument || document).querySelectorAll('*');
    for (let i = 0; i < all.length; i++) {
      if (all[i] === el) { index = i; break; }
    }
  } catch (e) {}
  const tag = el.tagName ? el.tagName.toLowerCase() : 'unknown';
  return '#el:' + tag + ':' + index;
}
"""


@dataclass(frozen=True)
class TabOrder:
    """Where each probe sits in the tab sequence, and whether we ran out of room.

    ``index`` maps a probe id to the number of Tab presses needed to reach it
    from a blurred start. ``capped`` is true when the walk stopped at the cap
    rather than completing a cycle, which makes every *absent* probe
    inconclusive rather than unreachable.
    """

    index: dict[str, int]
    capped: bool
    presses: int

    def position(self, probe_id: str) -> int | None:
        return self.index.get(probe_id)

    def contains(self, probe_id: str) -> bool:
        return probe_id in self.index

    def reachability_is_certain(self, probe_id: str) -> bool:
        """Whether "not in the tab order" is a fact rather than a budget limit.

        If the probe was found, its position is certain either way. If it was
        not found and the walk was capped, we simply did not look far enough.
        """
        return self.contains(probe_id) or not self.capped


async def compute_tab_order(page: Page, *, max_tabs: int = DEFAULT_MAX_TABS) -> TabOrder:
    """Walk the page with real Tab presses and record where each probe lands.

    **The page must be freshly navigated and must not have been focused yet.**
    This is a hard precondition, not a nicety, and there is no way to restore it
    from script. Chromium tracks a *sequential focus navigation starting point*
    that survives ``blur()``, so a second walk on the same page resumes
    mid-sequence and returns different positions. Every reset we tried is worse
    than none:

    ===========================  ==========================================
    reset                        result
    ===========================  ==========================================
    ``blur()`` only              unstable; positions drift on every walk
    focus ``body``/``<html>``    stable, but ``tabindex="5"`` sorts *last*
    fresh page (what we do)      stable and spec-correct
    ===========================  ==========================================

    Focusing an ancestor makes Chromium treat that node as the starting point,
    so positive-``tabindex`` elements ahead of it in the tab sequence get
    skipped to the end — silently inverting the one ordering rule this function
    exists to observe. :meth:`DifferentialRunner.tab_order` satisfies the
    precondition by opening a new context and page for every walk.

    Stops early on a completed cycle: once focus returns to the first stop we
    recorded, tabbing further only repeats itself.
    """

    index: dict[str, int] = {}
    sequence: list[str] = []
    capped = True
    presses = 0

    for step in range(1, max_tabs + 1):
        await page.keyboard.press("Tab")
        presses = step
        marker = await _active_marker(page)
        if marker is None:
            # Focus left the document (browser chrome). The sequence has wrapped.
            capped = False
            break

        if not marker.startswith(UNNAMED) and marker not in index:
            index[marker] = step
        sequence.append(marker)

        # A completed cycle: focus is back on the first stop we saw.
        if len(sequence) > 1 and sequence[-1] == sequence[0]:
            capped = False
            break
    else:
        log.info("kbdiff.taborder.capped", presses=presses, found=len(index))

    return TabOrder(index=index, capped=capped, presses=presses)


async def _active_marker(page: Page) -> str | None:
    """The focused probe id, looking inside same-origin frames too.

    Playwright sends the key to the focused frame, but ``document.activeElement``
    in the top document reports the *iframe element*, not what is focused inside
    it. Upstream lost an entire iframe probe to exactly this. When the top
    document reports an iframe, we ask that frame directly.
    """
    try:
        marker: str | None = await page.evaluate(_ACTIVE_PROBE_JS)
    except Exception as exc:
        log.info("kbdiff.taborder.active_failed", error=str(exc)[:120])
        return None

    if marker is not None and marker.startswith(f"{UNNAMED}iframe:"):
        for frame in page.frames:
            if frame is page.main_frame:
                continue
            try:
                inner: str | None = await frame.evaluate(_ACTIVE_PROBE_JS)
            except Exception as exc:
                # Cross-origin or detached frame: not ours to read, keep walking.
                log.debug("kbdiff.taborder.frame_skipped", error=str(exc)[:120])
                continue
            if inner and not inner.startswith(UNNAMED):
                return inner
    return marker
