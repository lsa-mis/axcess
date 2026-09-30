"""Mouse-only control probe (SC 2.1.1 Keyboard).

What it does
============

A keyboard *differential*: find controls a mouse can operate and a keyboard
cannot. It is the production port of the ``tabbing`` study
(``experiments/tabbing/``), which scored 48 detectors on five corpora. The
study's conclusion drives the design: a cheap static tier finds leads, and a
behavioural tier, run only on the leads the static tier keeps, decides them.

**Standard** (the default when the keyboard check is on) costs one CDP call
and one ``evaluate`` per frame, with no key presses of its own:

1. ``DOMDebugger.getEventListeners`` on the document with ``depth=-1`` and
   ``pierce=true`` returns every listener in the page, frames and closed shadow
   roots included, in one round trip. Each listener's node is marked in-page.
2. One ``evaluate`` per frame reads those marks with the page's styles and
   attributes and proposes a candidate on a bound mouse listener, an
   ``onclick`` property, React ``onClick``-style props, or a non-native
   interactive ARIA role.
3. A candidate is a lead when the Tab key cannot reach it, or when Tab
   reaches a custom control that has no key handler. Reachable means visited
   by the keyboard-trap probe's walk earlier on the same page, or statically
   tabbable *and* able to keep focus when focused once (WCAG F55).
4. Free structural rules then dismiss what another keyboard path already
   covers: a nested or wrapping reachable control, a roving-tabindex item, a
   declared shortcut, or a reachable control with the same name.

Three more static signals find controls with no listener of their own:

* **Event delegation, resolved.** The selectors a document-level click
  handler tests (``closest('.row-action')``, ``target.id === 'x'``, read from
  the handler's source) and jQuery's record of delegated handlers become
  element-level evidence.
* **CSS hover disclosure.** A ``trigger:hover target`` rule that shows
  hidden content holding a control, with no ``:focus``/``:focus-within`` rule
  or script that shows it for the keyboard, is a lead on the trigger.
* **React hover props** (``onMouseEnter``, ``onMouseOver``) count like a
  hover listener.

A pointer cursor or button-like class name alone is a *weak* signal. Standard
reports it only when an element ancestor (not the document) has a click
listener; otherwise only Advanced tests it.

**Advanced** adds a behavioural pass under the interaction probe's
``exploration_guard``, on at most ``advanced_max_leads`` leads inside a time
budget. Clicking a lead that changes nothing observable (DOM rendering, text,
storage, canvas, URL, same-origin requests) dismisses it. A lead Tab can reach
is then operated with Enter and Space. If the keys produce the click's effect,
the lead is dismissed; if they do nothing, or something else, it is
confirmed. Leads the budget does not reach stay Standard leads.

What it does NOT detect
=======================

* Controls inside closed shadow roots, whose focus cannot be observed.
* Drag-and-drop, hover-only and gesture-only functionality with no click.
* Custom key handlers that work but are undocumented (a person must check).
* Anything after the load state (the interaction probe reveals those states).

Every output is a review lead for a person to confirm, never a conformance
decision.

Safety
======

Never raises; a bad page returns ``[]``. Standard dispatches no clicks or keys;
its only page-visible action is focusing a candidate the Tab walk did not
visit, as the focus probe does for every control. Advanced dispatches real
clicks and key presses, so it skips any control whose name
matches the interaction probe's destructive-word list, blocks navigation,
writes and popups, and reloads the page after any trial that changed it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from audit.analyzer.keyboard.base import (
    HELP_URL_2_1_1,
    RULE_NO_KEY_HANDLER,
    RULE_UNREACHABLE,
    SC_2_1_1,
    KeyboardTrap,
)

if TYPE_CHECKING:
    from playwright.async_api import CDPSession, Frame, Page, Request

log = logging.getLogger(__name__)

LeadKind = Literal["unreachable", "no_key_handler", "label", "hover_only"]
Verdict = Literal["lead", "confirmed", "dismissed"]

# Per-page bounds. Every one is a cost bound, not an accuracy setting.
DEFAULT_MAX_SCAN = 8000  # elements read per frame
DEFAULT_MAX_LEADS = 25  # leads reported per page
DEFAULT_MAX_FRAMES = 6
DEFAULT_ADVANCED_MAX_LEADS = 10
DEFAULT_ADVANCED_BUDGET_S = 20.0
# How long a trial waits for an effect. The study found 80 ms missed a real
# 700 ms deferred effect; 900 ms caught every delayed fixture.
_SETTLE_MAX_MS = 900
_SETTLE_POLL_MS = 60
# After the first change, wait a little more so a two-step effect is compared
# whole, not at whatever point the first poll happened to see.
_SETTLE_TAIL_MS = 150
_NOISE_WINDOW_MS = 300
_SNIPPET_CHARS = 240
# Two effects are "the same" when their changed-item sets overlap this much.
_SAME_EFFECT_JACCARD = 0.5

# Listener bits, written by the CDP marking pass and read by the collector.
_BIT_ACTIVATE = 1  # click, mousedown, mouseup, pointerdown, pointerup
_BIT_DBLCLICK = 2
_BIT_HOVER = 4  # mouseover, mouseenter
_BIT_KEY = 8  # keydown, keyup, keypress
_BIT_FOCUS = 16  # focus, focusin: a script that opens something on focus
_LISTENER_BITS: dict[str, int] = {
    "click": _BIT_ACTIVATE,
    "mousedown": _BIT_ACTIVATE,
    "mouseup": _BIT_ACTIVATE,
    "pointerdown": _BIT_ACTIVATE,
    "pointerup": _BIT_ACTIVATE,
    "dblclick": _BIT_DBLCLICK,
    "mouseover": _BIT_HOVER,
    "mouseenter": _BIT_HOVER,
    "keydown": _BIT_KEY,
    "keyup": _BIT_KEY,
    "keypress": _BIT_KEY,
    "focus": _BIT_FOCUS,
    "focusin": _BIT_FOCUS,
}
# A page with more listener nodes than this is marked only up to the cap;
# the collector then reports the frame as truncated.
_MAX_MARKED_NODES = 3000


# Runs with ``this`` bound to a node that carries a listener. Elements go in a
# per-window WeakMap so no attribute is written into the audited DOM; the
# document's bits are kept separately (delegation evidence), and nodes inside
# closed shadow roots are remembered because no in-page walk can reach them.
_MARK_FN = """
function(bits) {
  const w = window;
  if (!w.__axkbMarks) { w.__axkbMarks = new WeakMap(); w.__axkbDoc = 0; w.__axkbClosed = []; }
  if (this.nodeType === 9) { w.__axkbDoc |= bits; return; }
  if (this.nodeType !== 1) return;
  w.__axkbMarks.set(this, (w.__axkbMarks.get(this) || 0) | bits);
  const root = this.getRootNode && this.getRootNode();
  if (root && root.host && root.mode === 'closed' && w.__axkbClosed.length < 500) {
    w.__axkbClosed.push(this);
  }
}
"""

_WINDOW_MARK_FN = """
function(bits) {
  if (!window.__axkbMarks) {
    window.__axkbMarks = new WeakMap(); window.__axkbDoc = 0; window.__axkbClosed = [];
  }
  window.__axkbDoc |= bits;
}
"""

_CLEANUP_JS = """
() => { try { delete window.__axkbMarks; delete window.__axkbDoc; delete window.__axkbClosed;
  delete window.__axkbEff; } catch (e) {} }
"""

# The collector. One call per frame. Returns leads (already filtered), the
# number of candidates considered and whether the element cap was hit.
_COLLECT_JS = r"""
(opts) => {
  const marks = window.__axkbMarks || new WeakMap();
  const docBits = window.__axkbDoc || 0;
  const visited = (window.__kbprobe_ids && window.__kbprobe_ids.map) || null;
  const NATIVE = 'a[href],area[href],button,input:not([type=hidden]),select,textarea,' +
    'summary,iframe,object,embed,audio[controls],video[controls]';
  const FOCUSABLE = NATIVE + ',[tabindex]:not([tabindex="-1"]),' +
    '[contenteditable]:not([contenteditable="false"])';
  const ROLE = new RegExp('^(button|link|checkbox|radio|switch|tab|menuitem|menuitemcheckbox|' +
    'menuitemradio|option|slider|spinbutton|treeitem|combobox)$');
  const LEX = new RegExp('(^|[-_ ])(btn|button|click|clickable|toggle|action|dropdown|expand|' +
    'close|open)([-_ ]|$)', 'i');
  const COMPOSITE = /^(menubar|menu|tablist|listbox|radiogroup|tree|treegrid|grid|toolbar)$/;
  const CHORD = /\b(alt|ctrl|control|cmd|command|shift|meta|option)\s*[+\-]\s*\S/i;
  const REACT_MOUSE = /^on(Click|MouseDown|MouseUp|PointerDown|PointerUp|DoubleClick)$/;
  const REACT_KEY = /^on(KeyDown|KeyUp|KeyPress)$/;
  const REACT_HOVER = /^on(MouseEnter|MouseOver)$/;

  const parentOf = (el) => el.parentElement || (el.getRootNode && el.getRootNode().host) || null;
  const reactProps = (el) => {
    for (const k in el) {
      // React 17+ and React 16 respectively.
      if (k.startsWith('__reactProps$') || k.startsWith('__reactEventHandlers$')) {
        return el[k] || null;
      }
    }
    return null;
  };
  // React binds every event it supports on its root container, so the root's
  // listeners say nothing about any one element below it.
  const reactRoot = (el) => {
    if (el._reactRootContainer) return true;
    for (const k in el) if (k.startsWith('__reactContainer$')) return true;
    return false;
  };
  const inert = (el) => {
    for (let cur = el; cur; cur = parentOf(cur)) {
      if (cur.hasAttribute && cur.hasAttribute('inert')) return true;
    }
    return false;
  };
  const rendered = (el) => {
    if (typeof el.checkVisibility === 'function') {
      if (!el.checkVisibility({ visibilityProperty: true })) return false;
    } else {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility !== 'visible') return false;
    }
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  // Whether the frame this document is in can itself be tabbed into. Only
  // same-origin ancestors are readable; an unreadable one is assumed open.
  let frameOpen = true;
  try {
    for (let w = window; w !== w.parent; w = w.parent) {
      const fe = w.frameElement;
      if (!fe) break;
      if (fe.getAttribute('tabindex') !== null && fe.tabIndex < 0) { frameOpen = false; break; }
      if (fe.hasAttribute('inert')) { frameOpen = false; break; }
    }
  } catch (e) {}
  // A shadow host with a negative tabindex takes its whole tree out of the
  // sequential focus order (HTML focus navigation scopes).
  const hostBlocked = (el) => {
    for (let root = el.getRootNode(); root && root.host; root = root.host.getRootNode()) {
      const h = root.host;
      if (h.getAttribute('tabindex') !== null && h.tabIndex < 0) return true;
    }
    return false;
  };
  const tabCache = new Map();
  const reachable = (el) => {
    if (tabCache.has(el)) return tabCache.get(el);
    let ok = false;
    if (visited && visited.has(el)) ok = true;
    else if (frameOpen && el.tabIndex >= 0 && !el.matches(':disabled') && !inert(el) &&
             !hostBlocked(el) && rendered(el)) ok = true;
    tabCache.set(el, ok);
    return ok;
  };
  // Tab reaches a statically tabbable element unless focusing it does not
  // stick (a focus handler blurs it or moves focus on, WCAG failure F55). Only
  // asked of a candidate the keyboard-trap walk did not visit.
  const deepActive = () => {
    let a = document.activeElement;
    while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
    return a;
  };
  const focusSticks = (el) => {
    if (visited && visited.has(el)) return true;
    const prev = deepActive();
    try { el.focus({ preventScroll: true }); } catch (e) { return true; }
    const ok = deepActive() === el;
    try {
      if (prev && prev !== document.body && prev.focus) prev.focus({ preventScroll: true });
      else if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    } catch (e) {}
    return ok;
  };
  const ownReachable = (el) => reachable(el) && focusSticks(el);
  const accName = (el) => {
    const raw = el.getAttribute('aria-label') || el.getAttribute('title') ||
      (el.tagName === 'INPUT' ? (el.value || '') : '') || el.textContent || '';
    return raw.replace(/\s+/g, ' ').trim().toLowerCase().slice(0, 100);
  };
  const path = (el) => {
    // A unique CSS path in the element's own tree (nth-of-type chain, anchored
    // at the nearest id), so a later trial or screenshot finds this element.
    const parts = [];
    for (let cur = el; cur && cur.nodeType === 1; cur = cur.parentElement) {
      const tag = cur.tagName.toLowerCase();
      if (cur.id && /^[A-Za-z][\w-]*$/.test(cur.id)) {
        const root = cur.getRootNode();
        if (root.querySelectorAll('#' + cur.id).length === 1) {
          parts.unshift(tag + '#' + cur.id);
          break;
        }
      }
      const p = cur.parentElement;
      if (!p) { parts.unshift(tag); break; }
      let n = 1;
      for (let s = cur.previousElementSibling; s; s = s.previousElementSibling) {
        if (s.tagName === cur.tagName) n += 1;
      }
      parts.unshift(tag + ':nth-of-type(' + n + ')');
    }
    return parts.join(' > ');
  };
  const annotate = (el) => {
    if (!opts.annotateAttr) return null;
    for (let cur = el; cur; cur = parentOf(cur)) {
      if (cur.getAttribute && cur.hasAttribute(opts.annotateAttr)) {
        return cur.getAttribute(opts.annotateAttr);
      }
    }
    return null;
  };

  // --- enumerate: the light DOM, open shadow roots, and closed-root nodes the
  // CDP pass remembered.
  const all = [];
  let truncated = false;
  const visit = (root) => {
    const list = root.querySelectorAll('*');
    for (let i = 0; i < list.length; i++) {
      if (all.length >= opts.maxScan) { truncated = true; return; }
      const el = list[i];
      all.push(el);
      if (el.shadowRoot) visit(el.shadowRoot);
    }
  };
  visit(document);
  const closedSet = new Set(window.__axkbClosed || []);

  // Event delegation, resolved to elements: selectors a document-level click
  // handler tests (read from its source over CDP), and jQuery's own record of
  // delegated handlers (``$(document).on('click', '.row-action', fn)``). A
  // selector matching hundreds of elements is too generic to mean anything.
  const delegatedEls = new Map();
  const addSel = (root, sel) => {
    let list;
    try { list = root.querySelectorAll(sel); } catch (e) { return; }
    if (list.length > 300) return;
    for (const el of list) if (!delegatedEls.has(el)) delegatedEls.set(el, sel);
  };
  for (const sel of opts.delegated || []) {
    // The harness's label attribute must never feed a verdict.
    if (opts.annotateAttr && sel.includes(opts.annotateAttr)) continue;
    addSel(document, sel);
  }
  const jq = opts.extended && window.jQuery && typeof window.jQuery._data === 'function'
    ? window.jQuery : null;
  if (jq) {
    const hosts = [document, document.body];
    for (const el of all) if ((marks.get(el) || 0) & 1 && hosts.length < 300) hosts.push(el);
    for (const host of hosts) {
      let events = null;
      try { events = jq._data(host, 'events'); } catch (e) {}
      if (!events) continue;
      for (const type of ['click', 'mousedown', 'mouseup', 'dblclick', 'tap']) {
        for (const h of events[type] || []) if (h && h.selector) addSel(host, h.selector);
      }
    }
  }

  const hasKeyPath = (el, props) => {
    if ((marks.get(el) || 0) & 8) return true;
    if (props && Object.keys(props).some((k) => REACT_KEY.test(k))) return true;
    for (const h of ['onkeydown', 'onkeyup', 'onkeypress']) {
      if (typeof el[h] === 'function') return true;
    }
    // A key handler on a nearby element ancestor (a listbox or toolbar that
    // manages its items) counts; one on the document or body does not, since
    // nearly every page has one for unrelated reasons.
    let cur = parentOf(el);
    for (let depth = 0; cur && depth < 5; depth += 1, cur = parentOf(cur)) {
      if (cur === document.body || cur === document.documentElement || reactRoot(cur)) break;
      if ((marks.get(cur) || 0) & 8) return true;
      const p = reactProps(cur);
      if (p && Object.keys(p).some((k) => REACT_KEY.test(k))) return true;
    }
    return false;
  };
  const elementDelegate = (el) => {
    let cur = parentOf(el);
    for (let depth = 0; cur && depth < 8; depth += 1, cur = parentOf(cur)) {
      if (cur === document.body || cur === document.documentElement || reactRoot(cur)) return false;
      if ((marks.get(cur) || 0) & 1) return true;
    }
    return false;
  };
  // true: a point of the element is exposed; false: something else covers
  // every sampled point; null: cannot tell (offscreen, or clipped by an
  // ancestor such as a scroll container, which scrolling would fix).
  const centerClear = (el) => {
    // Scrolled out of view inside a scroll container: scrolling would expose
    // it, so it is not covered.
    const er = el.getBoundingClientRect();
    const ex = (er.left + er.right) / 2, ey = (er.top + er.bottom) / 2;
    const scrollers = opts.extended ? parentOf(el) : null;
    for (let cur = scrollers; cur && cur !== document.body; cur = parentOf(cur)) {
      if (cur.nodeType !== 1) continue;
      const o = getComputedStyle(cur);
      if (o.overflowX === 'visible' && o.overflowY === 'visible') continue;
      const cr = cur.getBoundingClientRect();
      if (ex < cr.left || ex > cr.right || ey < cr.top || ey > cr.bottom) return null;
    }
    const root = el.getRootNode();
    const from = root.elementFromPoint ? root : document;
    const rects = Array.from(el.getClientRects()).slice(0, 4);
    let sampled = 0, clipped = 0;
    for (const r of rects) {
      if (r.width <= 0 || r.height <= 0) continue;
      const x = Math.floor(r.left + r.width / 2), y = Math.floor(r.top + r.height / 2);
      if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
      const hit = from.elementFromPoint(x, y);
      if (!hit) continue;
      sampled += 1;
      for (let cur = hit; cur; cur = parentOf(cur)) if (cur === el) return true;
      for (let cur = parentOf(el); cur; cur = parentOf(cur)) {
        if (cur === hit) { clipped += 1; break; }
      }
    }
    if (!sampled || clipped === sampled) return null;
    return false;
  };
  const containsReachable = (el) => {
    const found = el.querySelectorAll(FOCUSABLE);
    for (let i = 0; i < found.length && i < 40; i++) if (reachable(found[i])) return true;
    if (el.shadowRoot) {
      const inner = el.shadowRoot.querySelectorAll(FOCUSABLE);
      for (let i = 0; i < inner.length && i < 40; i++) if (reachable(inner[i])) return true;
    }
    return false;
  };
  const insideReachable = (el) => {
    for (let cur = parentOf(el); cur; cur = parentOf(cur)) {
      if (cur.matches && cur.matches(FOCUSABLE) && reachable(cur)) return true;
      if (cur.tagName === 'LABEL' && cur.control && reachable(cur.control)) return true;
    }
    return false;
  };
  const roving = (el) => {
    if (el.getAttribute('tabindex') !== '-1') return false;
    // An ARIA item inside a composite owner whose items hold a tab stop.
    for (let cur = parentOf(el), depth = 0; cur && depth < 6; depth += 1, cur = parentOf(cur)) {
      const role = cur.getAttribute && cur.getAttribute('role');
      if (role && COMPOSITE.test(role)) {
        const stops = cur.querySelectorAll('[tabindex]:not([tabindex="-1"])');
        for (const s of stops) if (s !== el && reachable(s)) return true;
        break;
      }
    }
    // The role-less shape: a sibling of the same tag holds tabindex=0 while
    // this one holds -1, and the group has a key handler to move between them.
    const p = el.parentElement;
    if (!p) return false;
    const keyBits = (node) => (node ? (marks.get(node) || 0) & 8 : 0);
    const groupKeys = keyBits(p) || keyBits(p.parentElement);
    if (!groupKeys) return false;
    for (const s of p.children) {
      if (s !== el && s.tagName === el.tagName && s.getAttribute('tabindex') === '0' &&
          reachable(s)) return true;
    }
    return false;
  };
  // A click listener on a container with a clickable-looking descendant is a
  // delegation root: the descendant, not the container, is the control.
  const delegatesTo = (el) => {
    const inner = el.querySelectorAll('*');
    const own = getComputedStyle(el).cursor;
    for (let i = 0; i < inner.length && i < 300; i++) {
      const d = inner[i];
      if (d.matches(NATIVE)) continue;
      if (ROLE.test(d.getAttribute('role') || '')) return true;
      if (LEX.test(d.getAttribute('class') || '')) return true;
      if (own !== 'pointer' && getComputedStyle(d).cursor === 'pointer') return true;
    }
    return false;
  };
  const shortcut = (el) => {
    if (el.hasAttribute('aria-keyshortcuts') || el.hasAttribute('accesskey')) return true;
    const text = (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '') +
      ' ' + (el.textContent || '').slice(0, 200);
    return CHORD.test(text);
  };
  let twins = null;
  const twinOf = (el) => {
    const name = accName(el);
    if (name.length < 2) return false;
    if (twins === null) {
      twins = new Map();
      for (const c of all) {
        if (!c.matches(NATIVE) || !reachable(c)) continue;
        const n = accName(c);
        if (n.length < 2) continue;
        if (!twins.has(n)) twins.set(n, []);
        const bucket = twins.get(n);
        if (bucket.length < 8) bucket.push(c);
      }
    }
    for (const c of twins.get(name) || []) {
      if (c !== el && !el.contains(c) && !c.contains(el)) return true;
    }
    return false;
  };

  const leads = [];
  const drops = [];
  const drop = (el, why) => {
    if (opts.annotateAttr && drops.length < 400) {
      const html = (el.outerHTML || '').slice(0, 120);
      drops.push({ probe: annotate(el), why, sel: path(el), html });
    }
  };
  let considered = 0;
  const dismissed = {
    contained: 0, roving: 0, shortcut: 0, twin: 0, covered: 0, delegated_only: 0,
  };
  const seenLabels = new Set();
  for (const el of all) {
    if (leads.length >= opts.maxLeads * 3) { truncated = true; break; }
    const tag = el.tagName;
    if (['HTML', 'BODY', 'HEAD', 'SCRIPT', 'STYLE'].includes(tag)) continue;
    const bits = marks.get(el) || 0;
    const props = reactProps(el);
    const reactMouse = !!(props && Object.keys(props).some(
      (k) => REACT_MOUSE.test(k) && typeof props[k] === 'function'));
    const onclick = typeof el.onclick === 'function';
    const role = el.getAttribute('role') || '';
    const native = el.matches(NATIVE);
    const isLabel = tag === 'LABEL';
    const strongRaw = !!(bits & 1) || !!(bits & 2) || onclick || reactMouse;
    const reactHover = opts.extended && !!(props && Object.keys(props).some(
      (k) => REACT_HOVER.test(k) && typeof props[k] === 'function'));
    const strong = strongRaw && !reactRoot(el);
    // A native control is mouse-operable by definition; it matters here only
    // if Tab cannot reach it. Inside aria-hidden it is deliberately removed
    // (a carousel clone, say), so it is left out.
    const nativeSig = native && !isLabel &&
      !['IFRAME', 'OBJECT', 'EMBED', 'AUDIO', 'VIDEO'].includes(tag) &&
      !el.closest('[aria-hidden="true"]');
    // A link given role=button promises Space activation, which links lack.
    const linkButton = tag === 'A' && el.hasAttribute('href') && role === 'button';
    // A hover listener opens menus and tooltips; it is a mouse path, but only
    // for an element Tab cannot reach (focus can stand in for hover).
    const hover = (!!(bits & 4) || reactHover) && !reactRoot(el);
    const delegated = delegatedEls.has(el) && !reactRoot(el);
    const roleSig = !native && ROLE.test(role);
    let weak = false;
    if (!strong && !roleSig && !hover && !delegated && !isLabel) {
      const cls = el.getAttribute('class') || '';
      if (LEX.test(cls)) weak = true;
      else {
        const cur = getComputedStyle(el).cursor;
        if (cur === 'pointer') {
          const p = parentOf(el);
          weak = !(p && p.nodeType === 1 && getComputedStyle(p).cursor === 'pointer');
        }
      }
    }
    // A native control needs no styling evidence; it is operable by definition.
    if (nativeSig) weak = false;
    if (!strong && !roleSig && !hover && !weak && !isLabel && !nativeSig && !delegated) continue;
    // Inside a label, the label decides: its control is either reachable (the
    // keyboard path exists) or it is not (the label's own lead reports it).
    if (!isLabel && !strong) {
      const lab = el.closest('label');
      if (lab && lab.control) continue;
    }
    // A label only matters when it is the only way to operate its control.
    let labelFor = null;
    if (isLabel) {
      const c = el.control;
      if (!c || c.disabled || !/^(checkbox|radio|file)$/.test(c.type || '')) continue;
      if (seenLabels.has(c)) continue;
      seenLabels.add(c);
      labelFor = c;
    }
    considered += 1;
    if (el.matches(':disabled') || el.getAttribute('aria-disabled') === 'true') {
      drop(el, 'disabled'); continue;
    }
    if (inert(el) || !rendered(el)) { drop(el, 'not rendered'); continue; }
    const cs = getComputedStyle(el);
    if (cs.pointerEvents === 'none') { drop(el, 'pointer-events'); continue; }
    // Nothing a mouse can reach: wholly off the page's scrollable area, or
    // fully transparent (a 1.4.x concern, not 2.1.1).
    const r = el.getBoundingClientRect();
    if (r.right + scrollX <= 0 || r.bottom + scrollY <= 0) { drop(el, 'offscreen'); continue; }
    const opaque = typeof el.checkVisibility !== 'function' ||
      el.checkVisibility({ opacityProperty: true });
    if (!opaque) {
      drop(el, 'transparent'); continue;
    }
    if (centerClear(el) === false) { dismissed.covered += 1; drop(el, 'covered'); continue; }
    if (closedSet.has(el)) { drop(el, 'closed shadow'); continue; } // focus there is unobservable

    let kind = null;
    if (labelFor) {
      if (!ownReachable(labelFor)) kind = 'label';
    } else if (!ownReachable(el)) {
      kind = 'unreachable';
    } else if (strong && !native && !hasKeyPath(el, props)) {
      kind = 'no_key_handler';
    } else if (linkButton && !hasKeyPath(el, props)) {
      kind = 'no_key_handler';
    }
    if (!kind) { drop(el, 'keyboard path'); continue; }
    // A weak lead with no element-level delegate is left to Advanced, where
    // clicking it answers what the page's styling cannot.
    if (kind === 'unreachable' && weak && !delegated && !elementDelegate(el)) {
      if (!opts.keepWeak) { dismissed.delegated_only += 1; drop(el, 'weak'); continue; }
    }
    if (kind === 'unreachable' && strong && delegatesTo(el)) {
      drop(el, 'delegation root'); continue;
    }
    if (kind !== 'label') {
      if (containsReachable(el) || insideReachable(el)) {
        dismissed.contained += 1; drop(el, 'contained'); continue;
      }
      if (roving(el)) { dismissed.roving += 1; drop(el, 'roving'); continue; }
    }
    if (shortcut(el)) { dismissed.shortcut += 1; drop(el, 'shortcut'); continue; }
    if (kind !== 'no_key_handler' && twinOf(el)) {
      dismissed.twin += 1; drop(el, 'twin'); continue;
    }

    const signals = [];
    if (bits & 1) signals.push('mouse listener');
    if (bits & 2) signals.push('double-click listener');
    if (hover && !strong) signals.push('hover listener');
    if (delegated && !strong) {
      const handled = delegatedEls.get(el).slice(0, 60);
      signals.push('a click listener on the page that handles "' + handled +
        '"');
    }
    if (onclick && !(bits & 1)) signals.push('onclick property');
    if (reactMouse) signals.push('React mouse handler');
    if (roleSig || linkButton) signals.push('role=' + role);
    if (nativeSig && !strong && !roleSig) signals.push('native ' + tag.toLowerCase());
    if (weak) {
      signals.push(elementDelegate(el)
        ? 'clickable styling under a delegated click listener' : 'clickable styling');
    }
    if (labelFor) {
      signals.push('label for a ' + (labelFor.type || 'control') + ' the Tab key cannot reach');
    }
    const inShadow = el.getRootNode() !== document;
    leads.push({
      kind,
      strength: strong ? 3 : roleSig || labelFor || hover || nativeSig || delegated ? 2 : 1,
      selector: path(el),
      html: (el.outerHTML || '').slice(0, 240),
      name: accName(el).slice(0, 80),
      signals,
      dblclickOnly: !!(bits & 2) && !(bits & 1) && !onclick && !reactMouse,
      // A link already activates on Enter; its role=button promise is Space.
      spaceOnly: kind === 'no_key_handler' && linkButton,
      testable: opts.isMain && !inShadow,
      probe: annotate(el),
      weak,
    });
  }
  // Content a CSS ``:hover`` rule reveals, with no focus twin (checked over
  // CDP) and no script path: the keyboard cannot reach what is inside it.
  const scriptPath = (trig) => {
    if (trig.hasAttribute('aria-expanded') || trig.querySelector('[aria-expanded]')) return true;
    const nodes = [trig, ...Array.from(trig.querySelectorAll(FOCUSABLE)).slice(0, 30)];
    for (let cur = parentOf(trig), d = 0; cur && d < 3; d += 1, cur = parentOf(cur)) {
      nodes.push(cur);
    }
    for (const n of nodes) {
      const b = marks.get(n) || 0;
      if (b & (8 | 16)) return true; // key or focus handling can open it
    }
    for (const n of nodes.slice(0, 31)) {
      if ((marks.get(n) || 0) & 1 && reachable(n)) return true; // Enter clicks it open
      if (n.matches && n.matches('button,summary') && reachable(n)) return true;
    }
    return false;
  };
  const hoverSeen = new Set();
  const focusRules = (opts.hover || []).filter((r) => r.kind === 'focus');
  const focusShows = (trig, t) => focusRules.some((r) => {
    try {
      const within = trig.matches(r.trigger) || !!trig.closest(r.trigger);
      return within && t.matches(r.target);
    } catch (e) { return false; }
  });
  // The part of the trigger a person sees and points at: the trigger itself
  // when it holds text of its own, else its first rendered child outside the
  // hidden content.
  const handleOf = (trig, t) => {
    for (const n of trig.childNodes) if (n.nodeType === 3 && n.nodeValue.trim()) return trig;
    for (const c of trig.children) if (!c.contains(t) && rendered(c)) return c;
    return trig;
  };
  for (const rule of (opts.hover || []).filter((r) => r.kind !== 'focus')) {
    let targets;
    try { targets = document.querySelectorAll(rule.target); } catch (e) { continue; }
    for (const t of Array.from(targets).slice(0, 20)) {
      if (hoverSeen.has(t) || rendered(t) || inert(t)) continue;
      let trig = null;
      try { trig = t.parentElement && t.parentElement.closest(rule.trigger); } catch (e) {}
      for (let sib = t.previousElementSibling; !trig && sib; sib = sib.previousElementSibling) {
        try { if (sib.matches(rule.trigger)) trig = sib; } catch (e) { break; }
      }
      if (!trig || !rendered(trig) || scriptPath(trig) || focusShows(trig, t)) continue;
      const inner = t.matches(FOCUSABLE) ? t : t.querySelector(FOCUSABLE);
      // Text alone (a tooltip) is a 1.4.13 concern, not 2.1.1 functionality.
      if (!inner) continue;
      const handle = handleOf(trig, t);
      if (closedSet.has(handle) || centerClear(handle) === false) continue;
      hoverSeen.add(t);
      const shown = accName(inner) || inner.tagName.toLowerCase();
      leads.push({
        kind: 'hover_only', strength: 2, selector: path(handle),
        html: (handle.outerHTML || '').slice(0, 240), name: accName(handle).slice(0, 80),
        signals: ['a CSS :hover rule on it shows hidden content ("' + shown.slice(0, 40) + '")'],
        dblclickOnly: false, spaceOnly: false, testable: false, probe: annotate(handle),
        alsoProbe: annotate(inner), weak: false,
      });
    }
  }
  leads.sort((a, b) => b.strength - a.strength);
  return { leads: leads.slice(0, opts.maxLeads * 3), considered, truncated, dismissed, drops,
           docDelegation: !!(docBits & 1) };
}
"""

# The effect digest for Advanced trials. ``snap`` returns a set of strings
# describing everything observable except styling: which elements render,
# visible text, URL, both storages and canvases. Keys are tree paths, so they
# are comparable across a reload of a deterministic page.
_EFFECT_INSTALL_JS = r"""
() => {
  if (window.__axkbEff) return false;
  const hash = (s) => {
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
    return h;
  };
  const snap = () => {
    const out = new Set();
    let budget = 12000;
    const walk = (node, key) => {
      let i = 0;
      for (let c = node.firstChild; c && budget > 0; c = c.nextSibling, i++) {
        budget -= 1;
        if (c.nodeType === 3) {
          const t = c.nodeValue.trim();
          if (t) out.add('t:' + key + '/' + i + ':' + hash(t.slice(0, 300)));
        } else if (c.nodeType === 1) {
          const tag = c.tagName;
          if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') continue;
          const k = key + '/' + i + tag;
          const r = c.getBoundingClientRect();
          let on = r.width > 0 && r.height > 0;
          if (on) {
            const cs = getComputedStyle(c);
            on = cs.visibility !== 'hidden' && cs.display !== 'none';
          }
          if (!on) continue;
          out.add('e:' + k);
          if (tag === 'CANVAS') {
            try {
              const d = c.toDataURL();
              out.add('c:' + k + ':' + d.length + ':' + hash(d.slice(-64)));
            } catch (e) {}
          }
          const expanded = c.getAttribute('aria-expanded');
          if (expanded !== null) out.add('x:' + k + ':' + expanded);
          const pressed = c.getAttribute('aria-pressed');
          if (pressed !== null) out.add('p:' + k + ':' + pressed);
          if (c.shadowRoot) walk(c.shadowRoot, k + '#');
          walk(c, k);
        }
      }
    };
    if (document.body) walk(document.body, '');
    // Form state counts even when the control is hidden: a label is often the
    // only visible part of the checkbox it toggles.
    const fields = document.querySelectorAll('input,select,textarea');
    for (let i = 0; i < fields.length && i < 500; i++) {
      const f = fields[i];
      out.add('v:' + i + ':' + hash(String(f.value)) + ':' + (f.checked ? 1 : 0));
    }
    out.add('u:' + location.href);
    for (const name of ['localStorage', 'sessionStorage']) {
      try {
        const st = window[name];
        for (let i = 0; i < st.length && i < 200; i++) {
          const k = st.key(i);
          out.add('s:' + k + '=' + hash(st.getItem(k) || ''));
        }
      } catch (e) {}
    }
    return out;
  };
  window.__axkbEff = {
    base: null, noise: new Set(),
    mark() { this.base = snap(); return this.base.size; },
    noiseFrom() {
      const now = snap();
      for (const k of now) if (!this.base.has(k)) this.noise.add(k);
      for (const k of this.base) if (!now.has(k)) this.noise.add(k);
      this.base = now;
      return this.noise.size;
    },
    diff(cap) {
      const now = snap(); const out = [];
      for (const k of now) {
        if (this.base.has(k) || this.noise.has(k)) continue;
        out.push('+' + k);
        if (out.length >= cap) return out;
      }
      for (const k of this.base) {
        if (now.has(k) || this.noise.has(k)) continue;
        out.push('-' + k);
        if (out.length >= cap) return out;
      }
      return out;
    },
  };
  return true;
}
"""


@dataclass(frozen=True)
class OperabilityLead:
    """One candidate a mouse can operate and the keyboard apparently cannot."""

    kind: LeadKind
    selector: str
    html: str
    name: str
    signals: tuple[str, ...]
    strength: int
    testable: bool
    dblclick_only: bool = False
    space_only: bool = False
    weak: bool = False
    frame_url: str = ""
    # Harness-only: the nearest ancestor's value of ``annotate_attr``, and for
    # a hover-only lead, that of the hidden control it would reveal.
    probe: str | None = None
    also_probe: str | None = None
    verdict: Verdict = "lead"
    evidence: str = ""


@dataclass
class OperabilityResult:
    """Leads plus the per-page accounting a report needs to be honest."""

    leads: list[OperabilityLead] = field(default_factory=list)
    considered: int = 0
    truncated: bool = False
    tested: int = 0
    confirmed: int = 0
    dismissed_behaviour: int = 0
    limits: set[str] = field(default_factory=set)
    # Harness-only (``annotate_attr``): why each annotated candidate was dropped.
    drops: list[dict[str, Any]] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def reported(self) -> list[OperabilityLead]:
        return [lead for lead in self.leads if lead.verdict != "dismissed"]


@dataclass
class KeyboardOperabilityProbe:
    """Reusable probe; construct once per crawl, call :meth:`run` per page."""

    advanced: bool = False
    # The second-round detectors: resolved event delegation, CSS :hover
    # disclosure, React hover props and scroll-container clipping. Off gives
    # the first release's rules, which the A/B harness keeps as an arm.
    extended: bool = True
    max_scan: int = DEFAULT_MAX_SCAN
    max_leads: int = DEFAULT_MAX_LEADS
    max_frames: int = DEFAULT_MAX_FRAMES
    advanced_max_leads: int = DEFAULT_ADVANCED_MAX_LEADS
    advanced_budget_s: float = DEFAULT_ADVANCED_BUDGET_S
    blocked_labels: tuple[str, ...] = ()
    suppress_diagnostics: bool = False
    # Harness hook: report the nearest ancestor's value of this attribute on
    # each lead so a labelled corpus can be scored. Never set by a scan.
    annotate_attr: str | None = None

    def __post_init__(self) -> None:
        if not self.blocked_labels:
            from audit.analyzer.interaction.probe import DEFAULT_BLOCKED_LABELS

            self.blocked_labels = DEFAULT_BLOCKED_LABELS

    async def run(self, page: Page) -> list[KeyboardTrap]:
        """Findings for ``page``, in the keyboard pipeline's row shape."""
        result = await self.analyze(page)
        return [self._finding(lead) for lead in result.reported()[: self.max_leads]]

    async def analyze(self, page: Page) -> OperabilityResult:
        """The full result, including dismissed leads and accounting."""
        started = time.perf_counter()
        result = OperabilityResult()
        try:
            hints = await self._mark_listeners(page)
            await self._collect(page, result, hints)
        except Exception as exc:
            self._log_failure("collect", exc)
        if self.advanced and result.leads:
            try:
                await self._behavioural(page, result)
            except Exception as exc:
                self._log_failure("behavioural", exc)
        with contextlib.suppress(Exception):
            for frame in page.frames[: self.max_frames]:
                with contextlib.suppress(Exception):
                    await frame.evaluate(_CLEANUP_JS)
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        return result

    # -----------------------------------------------------------------
    # Standard tier.
    # -----------------------------------------------------------------

    async def _mark_listeners(self, page: Page) -> dict[str, Any]:
        """Mark every listener's node in-page with one subtree CDP query.

        Returns the page-level hints the collector uses: selectors that
        document-level click handlers test (event delegation), and ``:hover``
        disclosure rules from every stylesheet the page can read.
        """
        hints: dict[str, Any] = {"delegated": [], "hover": []}
        session: CDPSession = await page.context.new_cdp_session(page)
        try:
            if self.extended:
                with contextlib.suppress(Exception):
                    hints["hover"] = await _hover_rules(page)
            doc = await session.send("Runtime.evaluate", {"expression": "document"})
            doc_id = doc["result"].get("objectId")
            if not doc_id:
                return hints
            if self.extended:
                with contextlib.suppress(Exception):
                    hints["delegated"] = await _delegated_selectors(session)
            listeners = await session.send(
                "DOMDebugger.getEventListeners",
                {"objectId": doc_id, "depth": -1, "pierce": True},
            )
            by_node: dict[int, int] = {}
            for entry in listeners.get("listeners", []):
                bits = _LISTENER_BITS.get(str(entry.get("type", "")))
                node = entry.get("backendNodeId")
                if bits and isinstance(node, int):
                    by_node[node] = by_node.get(node, 0) | bits
            win = await session.send("Runtime.evaluate", {"expression": "window"})
            win_id = win["result"].get("objectId")
            if win_id:
                on_window = await session.send(
                    "DOMDebugger.getEventListeners", {"objectId": win_id, "depth": 0}
                )
                win_bits = 0
                for entry in on_window.get("listeners", []):
                    win_bits |= _LISTENER_BITS.get(str(entry.get("type", "")), 0)
                if win_bits:
                    await session.send(
                        "Runtime.callFunctionOn",
                        {
                            "objectId": win_id,
                            "functionDeclaration": _WINDOW_MARK_FN,
                            "arguments": [{"value": win_bits}],
                        },
                    )

            async def mark(node: int, bits: int) -> None:
                with contextlib.suppress(Exception):
                    resolved = await session.send("DOM.resolveNode", {"backendNodeId": node})
                    object_id = resolved["object"]["objectId"]
                    await session.send(
                        "Runtime.callFunctionOn",
                        {
                            "objectId": object_id,
                            "functionDeclaration": _MARK_FN,
                            "arguments": [{"value": bits}],
                        },
                    )

            items = list(by_node.items())[:_MAX_MARKED_NODES]
            # Pipelined: CDP answers in order, so the round trips overlap.
            await asyncio.gather(*(mark(node, bits) for node, bits in items))
        finally:
            with contextlib.suppress(Exception):
                await session.detach()
        return hints

    async def _collect(
        self, page: Page, result: OperabilityResult, hints: dict[str, Any] | None = None
    ) -> None:
        hints = hints or {"delegated": [], "hover": []}
        frames: Sequence[Frame] = page.frames[: self.max_frames]
        leads: list[OperabilityLead] = []
        for frame in frames:
            is_main = frame == page.main_frame
            try:
                raw: Any = await frame.evaluate(
                    _COLLECT_JS,
                    {
                        "maxScan": self.max_scan,
                        "maxLeads": self.max_leads,
                        "isMain": is_main,
                        "annotateAttr": self.annotate_attr,
                        # Advanced gets the weak leads Standard leaves out, so a
                        # click can decide them.
                        "keepWeak": self.advanced,
                        "delegated": hints["delegated"] if is_main else [],
                        "hover": hints["hover"],
                        "extended": self.extended,
                    },
                )
            except Exception as exc:
                self._log_failure("frame_collect", exc, debug=True)
                continue
            if not isinstance(raw, dict):
                continue
            result.considered += int(raw.get("considered", 0))
            result.truncated = result.truncated or bool(raw.get("truncated"))
            result.drops.extend(raw.get("drops", []))
            for item in raw.get("leads", []):
                leads.append(
                    OperabilityLead(
                        kind=item["kind"],
                        selector=str(item.get("selector", "")),
                        html=str(item.get("html", ""))[:_SNIPPET_CHARS],
                        name=str(item.get("name", "")),
                        signals=tuple(str(s) for s in item.get("signals", [])),
                        strength=int(item.get("strength", 1)),
                        testable=bool(item.get("testable")),
                        dblclick_only=bool(item.get("dblclickOnly")),
                        space_only=bool(item.get("spaceOnly")),
                        weak=bool(item.get("weak")),
                        frame_url="" if is_main else frame.url,
                        probe=item.get("probe"),
                        also_probe=item.get("alsoProbe"),
                    )
                )
        if result.truncated:
            result.limits.add("elements")
        result.leads = leads

    # -----------------------------------------------------------------
    # Advanced tier.
    # -----------------------------------------------------------------

    async def _behavioural(self, page: Page, result: OperabilityResult) -> None:
        from audit.analyzer.interaction.safety import exploration_guard

        pinned = page.url
        deadline = time.monotonic() + self.advanced_budget_s
        dirty = False
        order = sorted(
            (i for i, lead in enumerate(result.leads) if lead.testable),
            key=lambda i: -result.leads[i].strength,
        )
        # Weak leads exist only for Advanced to test; any it cannot reach are
        # dropped, exactly as Standard drops them.
        untested_weak: set[int] = {i for i, lead in enumerate(result.leads) if lead.weak}
        for index in order:
            if result.tested >= self.advanced_max_leads:
                result.limits.add("leads")
                break
            if time.monotonic() > deadline:
                result.limits.add("time")
                break
            lead = result.leads[index]
            if self._is_blocked(lead.name):
                continue
            if dirty:
                await self._reload(page, pinned)
                dirty = False
            remaining = deadline - time.monotonic()
            try:
                async with asyncio.timeout(max(remaining, 1.0)):
                    verdict, evidence, dirty = await self._trial(
                        page, lead, pinned, exploration_guard
                    )
            except TimeoutError:
                result.limits.add("time")
                dirty = True
                break
            result.tested += 1
            untested_weak.discard(index)
            if verdict == "confirmed":
                result.confirmed += 1
            elif verdict == "dismissed":
                result.dismissed_behaviour += 1
            result.leads[index] = replace(lead, verdict=verdict, evidence=evidence)
        if dirty or page.url != pinned:
            await self._reload(page, pinned)
        for index in untested_weak:
            result.leads[index] = replace(result.leads[index], verdict="dismissed")

    async def _trial(
        self, page: Page, lead: OperabilityLead, pinned: str, guard: Any
    ) -> tuple[Verdict, str, bool]:
        """Click the lead, then (if Tab reaches it) try Enter and Space."""
        async with guard(page, set(), self.blocked_labels):
            click_diff, requests = await self._effect_of(page, lead, action="click")
        if click_diff is None:
            return "lead", "", False
        if not click_diff and not requests:
            return (
                "dismissed",
                "Clicking it changed nothing Axcess could observe.",
                False,
            )
        what = _describe(click_diff, requests)
        if lead.kind != "no_key_handler":
            return (
                "confirmed",
                f"Measured: clicking it {what}, and the Tab key does not reach it.",
                True,
            )
        await self._reload(page, pinned)
        async with guard(page, set(), self.blocked_labels):
            key_diff, key_requests = await self._effect_of(page, lead, action="keys")
        if key_diff is None:
            return "lead", "", True
        if key_diff or key_requests:
            if _similar(click_diff, key_diff) or (not click_diff and key_requests):
                return "dismissed", "Enter or Space did what the click did.", True
            return (
                "confirmed",
                f"Measured: clicking it {what}, but Enter and Space did something else.",
                True,
            )
        return (
            "confirmed",
            f"Measured: clicking it {what}, but with focus on it Enter and Space did nothing.",
            True,
        )

    async def _effect_of(
        self, page: Page, lead: OperabilityLead, *, action: Literal["click", "keys"]
    ) -> tuple[list[str] | None, int]:
        """The changed items and same-origin requests one action caused."""
        fresh = await page.evaluate(_EFFECT_INSTALL_JS)
        locator = page.locator(lead.selector).first
        if await locator.count() == 0:
            return None, 0
        await page.evaluate("() => window.__axkbEff.mark()")
        if fresh:
            # Once per page load: whatever changes on its own (a carousel, a
            # clock) is noise for every trial on this load.
            await page.wait_for_timeout(_NOISE_WINDOW_MS)
            await page.evaluate("() => window.__axkbEff.noiseFrom()")
        origin = _origin(page.url)
        requests = 0

        def count(request: Request) -> None:
            nonlocal requests
            with contextlib.suppress(Exception):
                if request.frame.page != page:
                    return
                if request.is_navigation_request() or (
                    request.resource_type in {"fetch", "xhr", "websocket", "eventsource"}
                    and _origin(request.url) == origin
                ):
                    requests += 1

        def surfaced(_: object) -> None:
            nonlocal requests
            requests += 1

        # An alert, confirm or new window is an effect even though the guard
        # dismisses or blocks it before it can change this page.
        page.on("request", count)
        page.on("dialog", surfaced)
        page.on("popup", surfaced)
        try:
            if action == "click":
                if lead.dblclick_only:
                    await locator.dblclick(force=True, timeout=1500, no_wait_after=True)
                else:
                    await locator.click(force=True, timeout=1500, no_wait_after=True)
                diff = await self._settle(page)
            else:
                await locator.focus(timeout=1500)
                keys = ("Space",) if lead.space_only else ("Enter", "Space")
                diff = []
                for key in keys:
                    await page.keyboard.press(key)
                    diff = await self._settle(page)
                    if diff or requests:
                        break
        except Exception as exc:
            self._log_failure("trial", exc, debug=True)
            return None, 0
        finally:
            page.remove_listener("request", count)
            page.remove_listener("dialog", surfaced)
            page.remove_listener("popup", surfaced)
        return diff, requests

    async def _settle(self, page: Page) -> list[str]:
        waited = 0
        while waited < _SETTLE_MAX_MS:
            await page.wait_for_timeout(_SETTLE_POLL_MS)
            waited += _SETTLE_POLL_MS
            diff: list[str] = await page.evaluate("() => window.__axkbEff.diff(1)")
            if diff:
                await page.wait_for_timeout(_SETTLE_TAIL_MS)
                break
        full: list[str] = await page.evaluate("() => window.__axkbEff.diff(400)")
        return full

    async def _reload(self, page: Page, pinned: str) -> None:
        with contextlib.suppress(Exception):
            await page.goto(pinned, timeout=15000, wait_until="load")
            await page.wait_for_timeout(120)

    def _is_blocked(self, name: str) -> bool:
        lowered = re.sub(r"[-_]+", " ", name).casefold()
        return any(
            re.sub(r"[-_]+", " ", word).casefold() in lowered
            for word in self.blocked_labels
            if word.strip()
        )

    # -----------------------------------------------------------------
    # Findings.
    # -----------------------------------------------------------------

    def _finding(self, lead: OperabilityLead) -> KeyboardTrap:
        signals = ", ".join(lead.signals) or "a mouse handler"
        if lead.kind == "no_key_handler":
            rule = RULE_NO_KEY_HANDLER
            observed = (
                f"The Tab key reaches this custom control and it has {signals}, but "
                "Axcess found no key handler on it or a nearby parent, so Enter and "
                "Space may do nothing."
            )
        elif lead.kind == "hover_only":
            rule = RULE_UNREACHABLE
            observed = (
                f"Moving the mouse over this element shows content ({signals}), but no "
                "matching :focus or :focus-within rule, and no script, shows it for the "
                "keyboard, so the Tab key cannot reach what is inside."
            )
        elif lead.kind == "label":
            rule = RULE_UNREACHABLE
            observed = (
                f"This control is operated through its label ({signals}); the Tab key "
                "cannot reach the control itself."
            )
        else:
            rule = RULE_UNREACHABLE
            observed = (
                f"This element has {signals}, but the Tab key cannot reach it and no "
                "reachable control nearby does the same job."
            )
        if lead.verdict == "confirmed":
            observed = f"{lead.evidence} {observed}"
        else:
            observed = (
                f"{observed} Static evidence only: Axcess did not operate it. Test it "
                "with the mouse and then with Tab, Enter and Space."
            )
        if lead.frame_url:
            observed += " The element is inside an embedded frame."
        return KeyboardTrap(
            rule_id=rule,
            impact="serious",
            target_selector=lead.selector or "(unknown)",
            failure_summary=observed,
            html_snippet=lead.html[:_SNIPPET_CHARS],
            criterion_sc=SC_2_1_1,
            help="Everything a mouse can operate must also work from a keyboard alone.",
            help_url=HELP_URL_2_1_1,
        )

    def _log_failure(self, check: str, exc: Exception, *, debug: bool = False) -> None:
        logger = log.debug if debug else log.warning
        if self.suppress_diagnostics:
            logger("keyboard_operability.%s_failed_in_protected_context", check)
        else:
            logger("keyboard_operability.%s_failed: %s", check, exc)


# --- Page-level hints, gathered over CDP. ---------------------------------

# Selector arguments in a handler's source: ``closest('.row-action')``,
# ``matches("[data-action]")`` and the like, which is how a document-level
# listener decides which clicks are its own (event delegation).
_SELECTOR_CALL = re.compile(
    r"\.(?:closest|matches|webkitMatchesSelector|msMatchesSelector|is)\(\s*(['\"`])([^'\"`]{1,120})\1"
)
# ``target.id === 'delegated'`` and jQuery's ``hasClass('row-action')``.
_ID_TEST = re.compile(r"\.id\s*===?\s*(['\"])([A-Za-z][\w-]{0,60})\1")
_HAS_CLASS = re.compile(r"\.hasClass\(\s*(['\"])([\w-]{1,60})\1")
_CLASS_TEST = re.compile(r"classList\.contains\(\s*(['\"])([\w-]{1,60})\1")
# ``hasAttribute`` tests; ``getAttribute`` only reads, which is what click
# trackers do with ``data-automation-id`` and the like, so it is not evidence.
_ATTR_TEST = re.compile(r"hasAttribute\(\s*(['\"])(data-[\w-]{1,60})\1")
_MAX_HANDLER_SOURCE = 40_000
_HANDLER_SOURCES_JS = """(() => {
  const out = [];
  for (const target of [document, document.body, window]) {
    if (!target) continue;
    const all = getEventListeners(target);
    for (const type of ['click', 'mousedown', 'mouseup', 'pointerdown', 'pointerup']) {
      for (const entry of all[type] || []) out.push(String(entry.listener).slice(0, MAX_SOURCE));
    }
  }
  return out;
})()"""
_MAX_DELEGATED = 40


async def _delegated_selectors(session: CDPSession) -> list[str]:
    """Selectors tested by click handlers on the document, body or window.

    ``getEventListeners`` from the DevTools command-line API is the one route
    that hands back the handler functions themselves, so their source can be
    read for the selectors they test.
    """
    expression = _HANDLER_SOURCES_JS.replace("MAX_SOURCE", str(_MAX_HANDLER_SOURCE))
    got = await session.send(
        "Runtime.evaluate",
        {"expression": expression, "includeCommandLineAPI": True, "returnByValue": True},
    )
    found: list[str] = []
    for text in got.get("result", {}).get("value") or []:
        found += selectors_in_handler(str(text))
    return list(dict.fromkeys(found))[:_MAX_DELEGATED]


def selectors_in_handler(source: str) -> list[str]:
    """The CSS selectors a click handler's source tests its target against."""
    found = [m.group(2).strip() for m in _SELECTOR_CALL.finditer(source)]
    found += ["." + m.group(2) for m in _CLASS_TEST.finditer(source)]
    found += ["[" + m.group(2) + "]" for m in _ATTR_TEST.finditer(source)]
    found += ["#" + m.group(2) for m in _ID_TEST.finditer(source)]
    found += ["." + m.group(2) for m in _HAS_CLASS.finditer(source)]
    return found


# The page-side filter: every readable style rule (nested @media/@supports
# included) whose selector has :hover or a :focus form, and whose declarations
# change something that shows or hides content. Only those rules come back.
# A cross-origin stylesheet without CORS cannot be read by the page; its rules
# are missed, never guessed at.
_HOVER_RULES_JS = """
(cap) => {
  const out = [];
  const shows = (st) => (st.display && st.display !== 'none') || st.visibility === 'visible' ||
    (st.opacity && parseFloat(st.opacity) > 0) || st.maxHeight || st.height || st.clip ||
    st.clipPath || st.left || st.top || st.transform;
  let seen = 0;
  const walk = (rules) => {
    for (const r of rules) {
      if (out.length >= cap || seen > 60000) return;
      seen += 1;
      const sel = r.selectorText;
      if (sel !== undefined && r.style) {
        if ((sel.includes(':hover') || sel.includes(':focus')) && shows(r.style)) out.push(sel);
      } else if (r.cssRules) walk(r.cssRules);
    }
  };
  for (const sheet of document.styleSheets) {
    try { walk(sheet.cssRules); } catch (e) {}
  }
  return out;
}
"""
_MAX_HOVER_RULES = 60  # hover rules; up to 200 focus rules travel with them
_FOCUS_FORMS = (":focus-within", ":focus-visible", ":focus")


async def _hover_rules(page: Page) -> list[dict[str, str]]:
    """``trigger:hover target`` rules that reveal content, with no focus twin."""
    heads = await page.evaluate(_HOVER_RULES_JS, 2000)
    selectors: list[str] = []
    for head in heads or []:
        selectors += [" ".join(part.split()) for part in str(head).split(",")]
    known = set(selectors)
    focus_rules: list[dict[str, str]] = []
    for norm in dict.fromkeys(selectors):
        for twin in _FOCUS_FORMS:
            if twin in norm and len(focus_rules) < 200:
                trigger, _, _rest = norm.partition(twin)
                focus_rules.append(
                    {"trigger": trigger.strip(), "target": norm.replace(twin, "", 1)}
                )
                break
    out: list[dict[str, str]] = []
    for selector in dict.fromkeys(s for s in selectors if ":hover" in s):
        trigger, _, rest = selector.partition(":hover")
        # ``.btn:hover { opacity: 1 }`` restyles the element itself; only a
        # rule that reveals *another* element is a disclosure.
        if not rest.strip() or not (rest[0] == " " or rest.strip()[0] in ">+~"):
            continue
        if any(selector.replace(":hover", twin, 1) in known for twin in _FOCUS_FORMS):
            continue
        out.append(
            {
                "trigger": trigger.strip(),
                "target": selector.replace(":hover", "", 1),
                "kind": "hover",
            }
        )
        if len(out) >= _MAX_HOVER_RULES:
            break
    # The focus rules travel with them, so the page can check, element by
    # element, whether a differently written rule shows the same content.
    return out + [{**rule, "kind": "focus"} for rule in focus_rules]


def _origin(url: str) -> str:
    match = re.match(r"^([a-z][a-z0-9+.-]*://[^/?#]*)", url, re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _similar(a: Sequence[str], b: Sequence[str]) -> bool:
    if not a and not b:
        return True
    sa, sb = set(a), set(b)
    return len(sa & sb) / max(len(sa | sb), 1) >= _SAME_EFFECT_JACCARD


def _describe(diff: Sequence[str], requests: int) -> str:
    appeared = sum(1 for d in diff if d.startswith("+e:"))
    vanished = sum(1 for d in diff if d.startswith("-e:"))
    parts: list[str] = []
    if appeared:
        parts.append(f"showed {appeared} element{'s' if appeared != 1 else ''}")
    if vanished:
        parts.append(f"hid {vanished} element{'s' if vanished != 1 else ''}")
    if any(d[1:3] in {"t:", "v:", "x:", "p:"} for d in diff) and not parts:
        parts.append("changed text or state on the page")
    if any(d[1:3] in {"s:", "u:", "c:"} for d in diff):
        parts.append("changed the page's URL, storage or drawing")
    if requests:
        parts.append("sent a request, opened a dialog or window, or started navigation")
    return " and ".join(parts) or "changed the page"
