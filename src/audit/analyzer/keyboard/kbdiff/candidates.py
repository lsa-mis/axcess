"""Cheap candidate generation: which elements are worth the expensive oracle?

The differential in :mod:`differential` costs roughly a second per probe because
it opens fresh contexts and waits for state to settle. Running it on every
element of a real page is not affordable, so production use needs a cheap filter
in front of it. That filter's recall becomes the ceiling on the whole pipeline.

This module exists to make that ceiling measurable, which is the gap in the
upstream study. Their headline (100% recall) was computed by handing the oracle
the ground-truth element list — 60 ids read straight out of the answer key. That
measures how good the oracle is *once you already know where to look*. It does
not measure what a tool can find on a page it has never seen. Those are
different numbers and only the second one describes a usable scanner.

So the harness scores two modes:

* ``oracle`` — targets supplied, comparable to upstream's published figures.
* ``end_to_end`` — targets discovered by :func:`collect_candidates` first, which
  is what a real scan would do.

One deliberate departure: we do **not** subtract the tab order from the
candidate set. Every generator upstream scored reported ``candidates - T``,
which by construction throws away elements that are focusable but do nothing
when you press a key — their p10/p54 blind spot, invisible to all seven of their
generators simultaneously. Reachability and actionability are separate
questions, and the oracle is what answers the second one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from playwright.async_api import Page

# Class-name fragments that suggest an author intended something to be clicked.
# Lexical signals are weak on their own — upstream measured this family at 71%
# precision, the worst of anything they scored — but they carry recall no
# structural signal does, so they earn their place behind the oracle.
CLICKABLE_LEXICON = (
    "btn",
    "button",
    "click",
    "card",
    "tile",
    "toggle",
    "menu",
    "nav-item",
    "dropdown",
    "accordion",
    "tab",
    "close",
    "expand",
    "collapse",
    "select",
)

# Elements that are keyboard-operable by default. Present in the candidate set
# anyway: a native control can still be broken (a <button> with a click handler
# inside a `pointer-events:none` wrapper, say), and excluding them here would
# reintroduce exactly the structural blind spot described in the docstring.
NATIVE_INTERACTIVE = ("a", "button", "input", "select", "textarea", "summary", "details")

_COLLECT_JS = """
(lexicon) => {
  const out = [];
  const seen = new Set();

  const record = (el, root, signals) => {
    if (!signals.length || seen.has(el)) return;
    seen.add(el);
    const probe = el.getAttribute && el.getAttribute('data-probe');
    const rect = el.getBoundingClientRect();
    out.push({
      probe: probe || null,
      tag: el.tagName.toLowerCase(),
      signals,
      width: rect.width,
      height: rect.height,
      html: (el.outerHTML || '').slice(0, 200),
    });
  };

  const scan = (root) => {
    let els;
    try { els = root.querySelectorAll('*'); } catch (e) { return; }
    for (const el of els) {
      const signals = [];

      // D2: the inline attribute. Almost nothing has it, but what does is certain.
      if (el.hasAttribute && el.hasAttribute('onclick')) signals.push('onclick-attr');

      // D2b: the handler *property*. Upstream's key correction to their own
      // survey - React 19 assigns el.onclick directly, so this three-line check
      // finds React handlers at 100% precision and makes a version-fragile
      // fiber-props adapter unnecessary.
      try { if (typeof el.onclick === 'function') signals.push('onclick-prop'); } catch (e) {}

      // D4: the CSS affordance. Cheap, high recall, poor precision alone.
      try {
        const cs = getComputedStyle(el);
        if (cs.cursor === 'pointer') signals.push('cursor-pointer');
      } catch (e) {}

      // D4: the lexical signal.
      try {
        const raw = el.className;
        const cls = (raw && typeof raw === 'string') ? raw.toLowerCase() : '';
        if (cls && lexicon.some(w => cls.includes(w))) signals.push('class-lexicon');
      } catch (e) {}

      // Explicit interactive semantics without native semantics.
      const role = el.getAttribute && el.getAttribute('role');
      const interactiveRoles = ['button', 'link', 'menuitem', 'tab', 'checkbox', 'switch'];
      if (role && interactiveRoles.includes(role)) {
        signals.push('aria-role');
      }
      if (el.hasAttribute && el.hasAttribute('tabindex')) signals.push('tabindex');

      record(el, root, signals);

      if (el.shadowRoot) scan(el.shadowRoot);
    }
  };

  scan(document);
  return out;
}
"""


@dataclass(frozen=True)
class Candidate:
    """One element the cheap pass thinks might be operable, and why."""

    probe_id: str | None
    tag: str
    signals: tuple[str, ...]
    html: str

    @property
    def is_probe(self) -> bool:
        return self.probe_id is not None


async def collect_candidates(page: Page) -> list[Candidate]:
    """Run every cheap generator in one pass and return the union.

    The union, not a vote: each signal has different blind spots, and the
    expensive oracle behind them is what removes the false positives. Filtering
    hard here would trade recall we cannot recover for time we can afford.
    """
    raw: list[dict[str, Any]] = await page.evaluate(_COLLECT_JS, list(CLICKABLE_LEXICON))
    return [
        Candidate(
            probe_id=item.get("probe"),
            tag=str(item.get("tag", "")),
            signals=tuple(item.get("signals", ())),
            html=str(item.get("html", "")),
        )
        for item in raw
    ]


def candidate_probe_ids(candidates: list[Candidate]) -> set[str]:
    """The probe ids the cheap pass surfaced.

    Used to compute end-to-end recall: a probe the generator never proposed can
    never be confirmed by the oracle, however good the oracle is.
    """
    return {c.probe_id for c in candidates if c.probe_id is not None}
