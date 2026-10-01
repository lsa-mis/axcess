"""Keyboard checks on the dialogs Click-Through opens.

A dialog that a click opens exists only in that page state, so no load-time
check can test it. The interaction probe calls these checks at the moment it
has one open, which makes them nearly free: the state is already paid for.

What counts as a dialog: an element the click made visible that is either
declared (``<dialog open>``, ``role="dialog"`` or ``"alertdialog"``,
``aria-modal="true"``) or an undeclared box with ``position: fixed`` of at
least 150 x 60 px (the usual lightbox). Status messages, live regions,
tooltips and banners are left out, and so is anything a disclosure or menu
button opened (an opener with ``aria-expanded`` or ``aria-haspopup="menu"``),
because those patterns keep focus on the button by design.

Four checks, after the WAI-ARIA Authoring Practices dialog pattern
(https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/):

* focus moved into the dialog when it opened (SC 2.4.3 Focus Order);
* a close control exists but cannot take keyboard focus (SC 2.1.1 Keyboard);
* in a modal, Tab moves focus out to the page behind it (SC 2.4.3). A dialog
  declared non-modal (a ``role="dialog"`` without ``aria-modal``) is exempt;
* Escape does not close it. Best practice, unless the keyboard also has no
  other way out (focus held inside, no focusable close control): that is
  reported as a trap instead (SC 2.1.2 No Keyboard Trap), under its own rule.

Every result is a lead for a person to confirm. The checks press Tab and
Escape inside the exploration guard the probe already holds, and never click
anything themselves.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from audit.analyzer.keyboard.base import KeyboardTrap

if TYPE_CHECKING:
    from playwright.async_api import Page

RULE_FOCUS_NOT_MOVED = "keyboard-dialog-focus-not-moved"
RULE_FOCUS_ESCAPES = "keyboard-dialog-focus-escapes"
RULE_CLOSE_NOT_FOCUSABLE = "keyboard-dialog-close-not-focusable"
RULE_ESCAPE_DOES_NOT_CLOSE = "keyboard-dialog-escape-does-not-close"  # best practice
RULE_NO_KEYBOARD_EXIT = "keyboard-dialog-no-keyboard-exit"  # SC 2.1.2: no way out at all

_HELP_URLS = {
    "2.4.3": "https://www.w3.org/WAI/WCAG22/Understanding/focus-order.html",
    "2.1.1": "https://www.w3.org/WAI/WCAG22/Understanding/keyboard.html",
    "2.1.2": "https://www.w3.org/WAI/WCAG22/Understanding/no-keyboard-trap.html",
    "": "https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/",
}
# Dialogs checked per page. Each costs a few evaluations and at most
# ``_MAX_TABS`` key presses; one site-wide dialog opened from ten links is one
# problem, so the cap is low.
DEFAULT_MAX_DIALOG_CHECKS = 8
_MAX_TABS = 30

# Every rendered dialog-like element, tagged with a JS expando (attributes
# would serialize into stored HTML). ``offsetParent === null`` is a cheap
# first filter: it is null for fixed-position elements (and hidden ones),
# so the computed-style read only runs on a handful of elements.
_OVERLAYS_JS = r"""
() => {
  const out = [];
  const shown = (el) => {
    if (!el.getClientRects().length) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0;
  };
  const declared = new Set(document.querySelectorAll(
    'dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]'));
  const found = new Set(declared);
  for (const el of document.body ? document.body.querySelectorAll('*') : []) {
    if (el.offsetParent !== null || !el.getClientRects().length) continue;
    if (getComputedStyle(el).position === 'fixed') found.add(el);
  }
  const NOT_DIALOG = /^(status|alert|log|tooltip|marquee|timer|banner|navigation|menu|listbox)$/;
  for (const el of found) {
    if (!shown(el) || el.closest('[inert]')) continue;
    // The outermost one only: a fixed close button inside a fixed lightbox
    // is part of that lightbox.
    let inner = false;
    for (let up = el.parentElement; up; up = up.parentElement) {
      if (found.has(up) && shown(up)) { inner = true; break; }
    }
    if (inner) continue;
    const role = el.getAttribute('role') || '';
    if (NOT_DIALOG.test(role) || el.hasAttribute('aria-live')) continue;
    const isDeclared = declared.has(el);
    // A page landmark (a fixed header or footer a click revealed) is part of
    // the page, not a dialog over it.
    if (!isDeclared && (/^(HEADER|FOOTER|NAV|MAIN|ASIDE)$/.test(el.tagName) ||
        /^(contentinfo|complementary|main|search|form|region)$/.test(role))) continue;
    if (!isDeclared) {
      const r = el.getBoundingClientRect();
      if (r.width < 150 || r.height < 60) continue;
    }
    if (!el.__axcessOverlay) el.__axcessOverlay = 'ovl' + Math.random().toString(36).slice(2, 10);
    let modal = el.getAttribute('aria-modal') === 'true';
    if (!modal && el.tagName === 'DIALOG') {
      try { modal = el.matches(':modal'); } catch (e) {}
    }
    const parts = [];
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      if (node.id && document.querySelectorAll('#' + CSS.escape(node.id)).length === 1) {
        parts.unshift('#' + CSS.escape(node.id)); break;
      }
      let index = 1;
      for (let p = node.previousElementSibling; p; p = p.previousElementSibling)
        if (p.tagName === node.tagName) index++;
      parts.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + index + ')');
    }
    out.push({
      id: el.__axcessOverlay,
      selector: parts.join(' > '),
      declared: isDeclared,
      modal,
      // role="dialog" with no aria-modal says "not modal": Tab may leave it.
      nonModal: isDeclared && !modal,
      label: (el.getAttribute('aria-label') || el.getAttribute('title') ||
        (el.textContent || '')).replace(/\s+/g, ' ').trim().slice(0, 60),
      snippet: (el.outerHTML || '').slice(0, 240),
    });
  }
  return out;
}
"""

# Facts about one open dialog: does it hold focus, what can be focused in
# it, and its close controls. Also moves focus to its first focusable control
# when asked, for the Tab and Escape tests.
_FACTS_JS = r"""
([id, focusFirst]) => {
  let box = null;
  for (const el of document.querySelectorAll('*')) {
    if (el.__axcessOverlay === id) { box = el; break; }
  }
  if (!box || !box.getClientRects().length) return null;
  const deep = () => {
    let a = document.activeElement;
    while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
    return a;
  };
  const SEL = 'a[href], button, input:not([type=hidden]), select, textarea, summary, ' +
    '[tabindex]:not([tabindex="-1"]), [contenteditable]:not([contenteditable="false"])';
  const tabbable = (el) => el.matches(SEL) && el.tabIndex >= 0 && !el.disabled &&
    el.getClientRects().length > 0 && getComputedStyle(el).visibility === 'visible';
  const focusables = Array.from(box.querySelectorAll(SEL)).filter(tabbable);
  const CLOSE = /(^|[^a-z])(close|dismiss|cancel)([^a-z]|$)/i;
  // The usual close glyphs (multiplication sign, two heavy crosses) and x.
  const GLYPH = /^[\u00d7\u2715\u2716xX]$/;
  const closes = [];
  for (const el of box.querySelectorAll('*')) {
    if (!el.getClientRects().length) continue;
    const text = (el.textContent || '').trim();
    const named = [el.getAttribute('aria-label'), el.getAttribute('title'),
      text.length <= 12 ? text : '', el.getAttribute('class')].filter(Boolean).join(' ');
    if (!(CLOSE.test(named) || GLYPH.test(text))) continue;
    const keyboard = tabbable(el) || Array.from(el.querySelectorAll(SEL)).some(tabbable) ||
      !!(el.closest('a[href], button') && box.contains(el.closest('a[href], button')));
    closes.push(el);
    if (closes.length > 6) break;
    el.__axcessKeyboard = keyboard;
  }
  const info = closes.map((el) => {
    let path = [];
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      if (node.id && document.querySelectorAll('#' + CSS.escape(node.id)).length === 1) {
        path.unshift('#' + CSS.escape(node.id)); break;
      }
      let index = 1;
      for (let p = node.previousElementSibling; p; p = p.previousElementSibling)
        if (p.tagName === node.tagName) index++;
      path.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + index + ')');
    }
    return { selector: path.join(' > '), keyboard: !!el.__axcessKeyboard,
             html: (el.outerHTML || '').slice(0, 240) };
  });
  const active = deep();
  const focusInside = !!active && box.contains(active);
  if (focusFirst && focusables.length) focusables[0].focus();
  return { focusInside, focusables: focusables.length, closes: info };
}
"""

# Where focus is relative to one dialog: inside, outside on the page, or
# nowhere (body: focus left the document, which is not "escaping to the page").
_WHERE_JS = r"""
(id) => {
  let box = null;
  for (const el of document.querySelectorAll('*')) {
    if (el.__axcessOverlay === id) { box = el; break; }
  }
  if (!box || !box.getClientRects().length) return 'closed';
  let a = document.activeElement;
  while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
  if (!a || a === document.body || a === document.documentElement) return 'none';
  return box.contains(a) ? 'inside' : 'outside';
}
"""


@dataclass
class DialogRecord:
    """One dialog a click opened, and what its first checks learned."""

    overlay: dict[str, Any]
    opener: str
    keyboard_close: bool = False
    # True: Tab could not leave; False: it left; None: the dialog has more
    # controls than the Tab budget, so containment was not measured.
    held_focus: bool | None = None
    findings: list[KeyboardTrap] = field(default_factory=list)


async def overlay_ids(page: Page) -> set[str]:
    """Ids of every dialog-like element shown right now."""
    return {item["id"] for item in await _overlays(page)}


async def new_overlays(page: Page, before: set[str]) -> list[dict[str, Any]]:
    """Dialogs the last click opened: shown now, and not shown before it."""
    return [item for item in await _overlays(page) if item["id"] not in before]


async def check_opened(page: Page, overlay: dict[str, Any], *, opener: str) -> DialogRecord:
    """Focus moved in, close controls, and (modals) focus kept in."""
    record = DialogRecord(overlay=overlay, opener=opener)
    facts = await page.evaluate(_FACTS_JS, [overlay["id"], False])
    if not facts:
        return record
    closes = facts.get("closes") or []
    record.keyboard_close = any(item["keyboard"] for item in closes)
    if facts["focusables"] and not facts["focusInside"]:
        record.findings.append(
            _finding(
                RULE_FOCUS_NOT_MOVED,
                overlay,
                opener,
                "2.4.3",
                "A",
                "Measured: after the click opened this dialog, keyboard focus stayed "
                "outside it. A keyboard or screen reader user has to search for it, and "
                "may not know it opened.",
            )
        )
    if closes and not record.keyboard_close:
        first = closes[0]
        record.findings.append(
            _finding(
                RULE_CLOSE_NOT_FOCUSABLE,
                {**overlay, "selector": first["selector"], "snippet": first["html"]},
                opener,
                "2.1.1",
                "A",
                "Measured: this dialog's close control cannot get keyboard focus, so it "
                "works only with a mouse.",
            )
        )
    if facts["focusables"] and not overlay["nonModal"]:
        record.held_focus = await _holds_focus(page, overlay, facts["focusables"])
        if record.held_focus is False:
            record.findings.append(
                _finding(
                    RULE_FOCUS_ESCAPES,
                    overlay,
                    opener,
                    "2.4.3",
                    "A",
                    "Measured: pressing Tab inside this dialog moved focus to the page "
                    "behind it while the dialog stayed open. Keyboard users end up on "
                    "content they cannot see or use. If it is not meant to be a modal "
                    'dialog, mark it role="dialog" without aria-modal.',
                )
            )
    return record


async def check_escape(page: Page, record: DialogRecord) -> tuple[list[KeyboardTrap], bool]:
    """Press Escape inside the dialog. Returns the result and whether it closed.

    Called straight after :func:`check_opened`, before the probe's nested sweep
    (which may click the dialog's own close button); the probe reopens the
    dialog when Escape closed it.
    """
    overlay = record.overlay
    where = await page.evaluate(_WHERE_JS, overlay["id"])
    if where == "closed":
        return [], True
    await page.evaluate(_FACTS_JS, [overlay["id"], True])
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(250)
    if await page.evaluate(_WHERE_JS, overlay["id"]) == "closed":
        return [], True
    if record.held_focus is True and not record.keyboard_close:
        return [
            _finding(
                RULE_NO_KEYBOARD_EXIT,
                overlay,
                record.opener,
                "2.1.2",
                "A",
                "Measured: Escape does not close this dialog, Tab keeps focus inside it, "
                "and it has no close control the keyboard can reach. A keyboard user "
                "cannot leave it.",
                impact="critical",
            )
        ], False
    return [
        _finding(
            RULE_ESCAPE_DOES_NOT_CLOSE,
            overlay,
            record.opener,
            "",
            "",
            "Measured: Escape does not close this dialog. Keyboard users expect Escape "
            "to close a dialog; it has another way out, so this is best practice, not a "
            "WCAG failure.",
            impact="moderate",
        )
    ], False


async def _overlays(page: Page) -> list[dict[str, Any]]:
    try:
        found: list[dict[str, Any]] = await page.evaluate(_OVERLAYS_JS)
    except Exception:
        return []
    return found


async def _holds_focus(page: Page, overlay: dict[str, Any], focusables: int) -> bool | None:
    """Tab from the first control; False if focus lands on the page behind.

    None when the dialog has too many controls for the Tab budget: pressing
    Tab fewer times than there are controls cannot show that focus wraps.
    """
    if focusables + 2 > _MAX_TABS:
        return None
    await page.evaluate(_FACTS_JS, [overlay["id"], True])
    held = True
    for _ in range(focusables + 2):
        await page.keyboard.press("Tab")
        where = await page.evaluate(_WHERE_JS, overlay["id"])
        if where == "outside":
            held = False
            break
        if where == "closed":
            break
    with contextlib.suppress(Exception):
        await page.evaluate(_FACTS_JS, [overlay["id"], True])
    return held


def _finding(
    rule: str,
    overlay: dict[str, Any],
    opener: str,
    sc: str,
    level: str,
    observed: str,
    *,
    impact: str = "serious",
) -> KeyboardTrap:
    named = f' "{overlay["label"][:40]}"' if overlay.get("label") else ""
    return KeyboardTrap(
        rule_id=rule,
        impact=impact,
        target_selector=overlay["selector"] or "(unknown)",
        failure_summary=(
            f'{observed} Click-Through opened the dialog{named} by clicking "{opener[:60]}". '
            "Check it by hand with Tab, Shift+Tab, Enter and Escape."
        ),
        html_snippet=str(overlay.get("snippet", ""))[:240],
        criterion_sc=sc,
        wcag_level=level,
        help="A dialog must take keyboard focus, keep it while open, and close from the keyboard.",
        help_url=_HELP_URLS[sc],
    )
