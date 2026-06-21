"""Playwright-driven keyboard-trap probe (SC 2.1.2).

What it does
============

The probe runs three checks against an already-loaded Playwright page:

1. **Tab-walk** — focus the body, press Tab in a loop, record
   ``document.activeElement`` after each press. If the same element
   stays focused across several consecutive Tab presses, focus is
   stuck — a trap.

2. **Modal-Esc** — find every open ``<dialog>`` and every
   ``[role="dialog"][aria-modal="true"]``. Focus the first focusable
   inside, press Escape, check whether focus left the dialog subtree.
   If not, the modal traps focus.

3. **Iframe sanity** — iframes without ``tabindex="-1"`` and without a
   ``title`` are a common trap source. This is a heuristic, not a hard
   trap, so it's recorded with ``impact='serious'`` instead of
   ``'critical'``.

What it does NOT detect
=======================

* Traps that only appear after user interaction (clicking to mount a
  modal we never see).
* Traps inside shadow DOM that doesn't delegate focus.
* Pages behind login.
* Traps that only manifest with screen-reader virtual cursors.

These limits are surfaced in the Issues view via the existing
scope-honesty banner pattern.

Safety
======

Every check is wrapped in a try/except that logs and returns ``[]``.
A bad page must never crash the crawl. We also bound the work: at
most ``max_focusable * 2`` Tab presses, at most ``max_modals``
dialog checks. A page with 800 focusable controls won't make us
press Tab 1600 times in production — the cap is configurable from
the orchestrator via :attr:`max_focusable`.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from audit.analyzer.keyboard.base import (
    RULE_IFRAME,
    RULE_NO_ESCAPE,
    RULE_STUCK,
    KeyboardTrap,
)

if TYPE_CHECKING:
    from playwright.async_api import Page

log = logging.getLogger(__name__)


# --- Tunables. Exposed as constants so tests can monkey-patch and the
# orchestrator can override via construction. ---

# How many Tab presses count as "stuck on this element" before flagging.
# K=4 means: same element focused after Tab pressed 4 consecutive
# times. A real focus cycle should rotate within the page's focusable
# count; staying glued for 4 presses is overwhelming evidence the Tab
# handler swallowed every keypress.
DEFAULT_STUCK_THRESHOLD = 4

# Hard cap on Tab presses per page. focusable_count * 2 + slack covers
# any well-behaved page; the extra slack accounts for elements that
# move focus into iframes / sub-documents we walk through.
DEFAULT_MAX_FOCUSABLE = 50

# Hard cap on modals to probe per page. A page with 20 modals is
# pathological; checking the first 5 covers the realistic case.
DEFAULT_MAX_MODALS = 5

# How many chars of the element's outerHTML we keep on the finding for
# rendering / debugging.
_SNIPPET_CHARS = 240


@dataclass
class KeyboardProbe:
    """Reusable probe. Construct once per crawl, call :meth:`run` per page."""

    max_focusable: int = DEFAULT_MAX_FOCUSABLE
    stuck_threshold: int = DEFAULT_STUCK_THRESHOLD
    max_modals: int = DEFAULT_MAX_MODALS

    async def run(self, page: Page) -> list[KeyboardTrap]:
        """Probe ``page`` for keyboard traps. Returns a (possibly empty) list.

        Safe to call from inside ``JsFetcher.fetch`` — operates on the
        live page before the context closes. Never raises; any failure
        logs at WARNING and returns the findings collected so far.
        """
        findings: list[KeyboardTrap] = []
        try:
            findings.extend(await self._probe_tab_walk(page))
        except Exception as exc:
            log.warning("keyboard.tab_walk_failed: %s", exc)
        try:
            findings.extend(await self._probe_modal_escape(page))
        except Exception as exc:
            log.warning("keyboard.modal_escape_failed: %s", exc)
        try:
            findings.extend(await self._probe_iframe_sanity(page))
        except Exception as exc:
            log.warning("keyboard.iframe_sanity_failed: %s", exc)
        return findings

    # -----------------------------------------------------------------
    # Check 1 — Tab walk.
    # -----------------------------------------------------------------

    async def _probe_tab_walk(self, page: Page) -> list[KeyboardTrap]:
        """Walk Tab from body; flag focus that cannot leave an element.

        Identity is exact, not heuristic: an in-page WeakMap hands every
        distinct focused element a stable integer id, so two different
        elements can never collide. (The first version of this probe
        keyed on an outerHTML prefix; dogfooding it against the tracker
        app produced false positives on nav links that share one long
        class string. Exact identity removes that whole failure class.)

        Two trap shapes are detected:
          stuck:     the same element id repeats for stuck_threshold
                     consecutive presses (a keydown handler swallows Tab)
          ping-pong: a full sliding window of recent presses contains
                     at most two distinct ids and never reaches body
                     (focus bounces inside a tiny cluster and cannot
                     leave, the classic two-element modal loop)
        """
        # Move focus to a deterministic starting point. Without this,
        # the walk starts wherever the page's autofocus landed, which
        # makes test results non-deterministic.
        # Some pages reject focus on body (e.g. designMode). The probe
        # still works — Playwright's keyboard.press routes to whatever
        # element is currently focused. Suppression is deliberate.
        with contextlib.suppress(Exception):
            await page.evaluate("() => { try { document.body.focus(); } catch (e) {} }")

        # Walk up to `max_focusable * 2 + 4` Tab presses; enough
        # headroom even for chrome that injects pseudo-focusable
        # elements (scrollbars, etc.).
        max_tabs = self.max_focusable * 2 + 4
        window: list[int] = []  # sliding window of recent element ids
        window_size = max(10, self.stuck_threshold * 2)
        last_id: int | None = None
        stuck_count = 0
        for _ in range(max_tabs):
            try:
                await page.keyboard.press("Tab")
            except Exception as exc:
                log.warning("keyboard.tab_press_failed: %s", exc)
                break
            sig = await self._active_element_signature(page)
            if sig is None:
                # The page detached / navigated away. Stop cleanly.
                break
            el_id = int(sig["el_id"])

            # Body focus (id 0) means "no element is trapped" — either
            # the page has no focusable controls or Tab wrapped through
            # the document. Reset all trap state.
            if el_id == 0:
                stuck_count = 0
                window.clear()
                last_id = None
                continue

            # Shape 1: stuck on one element across consecutive presses.
            if last_id is not None and el_id == last_id:
                stuck_count += 1
                if stuck_count >= self.stuck_threshold:
                    return [
                        KeyboardTrap(
                            rule_id=RULE_STUCK,
                            impact="critical",
                            target_selector=str(sig.get("selector", "(unknown)")),
                            failure_summary=(
                                "Focus stayed on this element after "
                                f"{self.stuck_threshold + 1} consecutive Tab key "
                                "presses. Standard keyboard navigation cannot move "
                                "focus past it."
                            ),
                            html_snippet=str(sig.get("html", ""))[:_SNIPPET_CHARS],
                        )
                    ]
            else:
                stuck_count = 0
            last_id = el_id

            # Shape 2: ping-pong inside a tiny cluster, never reaching
            # body. A healthy page cycles through many distinct ids.
            window.append(el_id)
            if len(window) > window_size:
                window.pop(0)
            if len(window) == window_size and len(set(window)) <= 2:
                return [
                    KeyboardTrap(
                        rule_id=RULE_STUCK,
                        impact="critical",
                        target_selector=str(sig.get("selector", "(unknown)")),
                        failure_summary=(
                            f"Across {window_size} consecutive Tab presses, focus "
                            "stayed inside a cluster of at most two elements and "
                            "never returned to the page. Keyboard users cannot "
                            "leave this component."
                        ),
                        html_snippet=str(sig.get("html", ""))[:_SNIPPET_CHARS],
                    )
                ]

        return []

    # -----------------------------------------------------------------
    # Check 2 — Modal escape.
    # -----------------------------------------------------------------

    async def _probe_modal_escape(self, page: Page) -> list[KeyboardTrap]:
        """For each open dialog, focus inside and press Esc — verify exit."""
        try:
            modals = await page.evaluate(
                # Arrow functions don't have `arguments`, so we
                # destructure the argument explicitly. Playwright
                # passes the second arg of `page.evaluate` as the
                # first (and only) argument to this function.
                """
                (maxModals) => {
                  const out = [];
                  const sel = (
                    'dialog[open], ' +
                    '[role="dialog"][aria-modal="true"], ' +
                    '[aria-modal="true"][role="alertdialog"]'
                  );
                  const list = document.querySelectorAll(sel);
                  for (let i = 0; i < list.length; i++) {
                    const el = list[i];
                    const inside = el.querySelectorAll(
                      'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
                    );
                    if (!inside.length) continue;
                    // Stamp a marker so we can find this element again
                    // post-Escape without keeping a JS handle alive.
                    const mark = 'kbprobe-modal-' + i;
                    el.setAttribute('data-kbprobe-mark', mark);
                    out.push({ mark: mark, snippet: el.outerHTML.slice(0, 240) });
                    if (out.length >= maxModals) break;
                  }
                  return out;
                }
                """,
                self.max_modals,
            )
        except Exception as exc:
            log.warning("keyboard.modal_enumerate_failed: %s", exc)
            return []

        if not modals:
            return []

        findings: list[KeyboardTrap] = []
        for modal in modals:
            mark: str = modal["mark"]
            snippet: str = modal.get("snippet", "")
            try:
                # Move focus into the modal's first focusable element.
                # Playwright's locator API is the safe path — query
                # selectors via the live frame.
                focused = await page.evaluate(
                    f"""
                    () => {{
                      const el = document.querySelector('[data-kbprobe-mark="{mark}"]');
                      if (!el) return false;
                      const first = el.querySelector(
                        'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
                      );
                      if (!first) return false;
                      first.focus();
                      return document.activeElement === first;
                    }}
                    """
                )
                if not focused:
                    # Couldn't put focus inside; can't probe Escape
                    # reliably. Skip — not the same as a known trap.
                    continue

                await page.keyboard.press("Escape")

                # After Escape, where is focus? Walk up the DOM from
                # activeElement; if the marked modal is an ancestor,
                # focus is still trapped inside.
                still_inside = await page.evaluate(
                    f"""
                    () => {{
                      const ae = document.activeElement;
                      if (!ae) return false;
                      let cur = ae;
                      while (cur) {{
                        if (cur.getAttribute &&
                            cur.getAttribute('data-kbprobe-mark') === '{mark}') {{
                          return true;
                        }}
                        cur = cur.parentElement;
                      }}
                      return false;
                    }}
                    """
                )
                if still_inside:
                    findings.append(
                        KeyboardTrap(
                            rule_id=RULE_NO_ESCAPE,
                            impact="critical",
                            target_selector=f"[data-kbprobe-mark='{mark}']",
                            failure_summary=(
                                "Focus did not leave this modal after pressing Escape. "
                                "Modals must release focus on Escape so keyboard users can exit."
                            ),
                            html_snippet=snippet[:_SNIPPET_CHARS],
                        )
                    )
            except Exception as exc:
                log.warning("keyboard.modal_escape_check_failed: %s", exc)
                continue

        # Clean up our markers so we don't leak DOM artifacts into the
        # caller's HTML hash / saved HTML. Suppression is deliberate;
        # marker cleanup is best-effort, never blocking.
        with contextlib.suppress(Exception):
            await page.evaluate(
                """
                () => {
                  document.querySelectorAll('[data-kbprobe-mark]').forEach(el => {
                    el.removeAttribute('data-kbprobe-mark');
                  });
                }
                """
            )

        return findings

    # -----------------------------------------------------------------
    # Check 3 — Iframe heuristic.
    # -----------------------------------------------------------------

    async def _probe_iframe_sanity(self, page: Page) -> list[KeyboardTrap]:
        """Flag iframes that are likely to trap focus (missing title + no tabindex)."""
        try:
            raw = await page.evaluate(
                """
                () => {
                  const out = [];
                  const list = document.querySelectorAll('iframe');
                  for (let i = 0; i < list.length && out.length < 8; i++) {
                    const f = list[i];
                    const title = (f.getAttribute('title') || '').trim();
                    const ti = f.getAttribute('tabindex');
                    const hasContent = !!(f.src || f.srcdoc);
                    // Heuristic: iframe with content that's reachable by Tab
                    // (tabindex !== '-1') and no title is the canonical
                    // "user gets stuck in the embedded doc" shape.
                    if (hasContent && title === '' && ti !== '-1') {
                      out.push({
                        selector: 'iframe' + (f.id ? '#' + f.id : ''),
                        snippet: f.outerHTML.slice(0, 240),
                      });
                    }
                  }
                  return out;
                }
                """
            )
        except Exception as exc:
            log.warning("keyboard.iframe_scan_failed: %s", exc)
            return []

        return [
            KeyboardTrap(
                rule_id=RULE_IFRAME,
                # Heuristic, not a confirmed trap; impact serious rather
                # than critical so it doesn't outrank the confirmed cases.
                impact="serious",
                target_selector=item.get("selector", "iframe"),
                failure_summary=(
                    "Iframe is reachable by Tab but has no title. Keyboard users can land "
                    "inside but cannot tell what they entered, and if the embedded document "
                    'traps focus, they cannot escape. Add title="..." and ensure the '
                    "embedded document is itself keyboard-accessible."
                ),
                html_snippet=item.get("snippet", "")[:_SNIPPET_CHARS],
            )
            for item in (raw or [])
        ]

    # -----------------------------------------------------------------
    # Helpers.
    # -----------------------------------------------------------------

    async def _active_element_signature(self, page: Page) -> dict[str, str] | None:
        """Return an exact identity record for document.activeElement.

        Identity comes from an in-page WeakMap that hands every distinct
        focused element a stable integer id for the lifetime of the
        page. Two different elements can never share an id, no matter
        how similar their markup is. (The first version keyed on an
        outerHTML prefix and false-positived on nav links that share a
        long class string; dogfooding caught it.)

        Returns ``None`` if the page has detached (navigation away,
        crash). Returns a dict with:

          * ``el_id``: "0" for body or no focus, otherwise a stable
            positive integer unique to this element.
          * ``selector``: best-effort CSS selector for reporting.
          * ``html``: outerHTML prefix for the finding's snippet.
        """
        try:
            raw: object = await page.evaluate(
                """
                () => {
                  const ae = document.activeElement;
                  if (!ae || ae === document.body) {
                    return { el_id: 0, selector: 'body', html: '' };
                  }
                  if (!window.__kbprobe_ids) {
                    window.__kbprobe_ids = { map: new WeakMap(), next: 1 };
                  }
                  const reg = window.__kbprobe_ids;
                  if (!reg.map.has(ae)) {
                    reg.map.set(ae, reg.next);
                    reg.next += 1;
                  }
                  const tag = ae.tagName.toLowerCase();
                  const id = ae.id ? '#' + ae.id : '';
                  // Try to build something selector-ish for reporting.
                  let sel = tag + id;
                  if (!id && ae.className && typeof ae.className === 'string') {
                    const cls = ae.className.trim().split(/\\s+/).slice(0, 2).join('.');
                    if (cls) sel = tag + '.' + cls;
                  }
                  const html = (ae.outerHTML || '').slice(0, 240);
                  return { el_id: reg.map.get(ae), selector: sel, html: html };
                }
                """
            )
        except Exception as exc:
            log.debug("keyboard.active_element_failed: %s", exc)
            return None
        # `page.evaluate` is typed as Any in Playwright's stubs; we
        # know our JS returns either a 3-key object or undefined.
        # Narrow it through a runtime shape check so the function's
        # declared return type is sound.
        if isinstance(raw, dict) and "el_id" in raw:
            return {
                "el_id": str(raw.get("el_id", 0)),
                "selector": str(raw.get("selector", "(unknown)")),
                "html": str(raw.get("html", "")),
            }
        return None
