"""Form error check (WCAG SC 3.3.1 Error Identification): the browser part.

For each form on a rendered page, at most ``max_forms``:

1. Describe it without touching it (``_COLLECT_JS``) and decide whether it may
   be submitted at all (``base.skip_reason``). Sign-in, payment, destructive,
   CAPTCHA and search forms, forms with nothing empty, and forms with no
   submit control are never pressed.
2. Record each field's state and the page's visible text (``_SNAPSHOT_JS``),
   and start watching for text that appears, the browser's own ``invalid``
   events and ``alert()`` messages (``_ARM_JS``).
3. Press the form's submit control once, with nothing typed, inside the same
   network guard Click-Through uses (``interaction.safety``): every request
   that could change anything, and every page navigation, is blocked. The
   check never types, never clears a value, and never presses Enter.
4. Wait for the page to settle, take the second record, and hand both to
   ``base.classify``.
5. Load the page again before the next form, so each form starts as the page
   first showed it.

A form that appears on many pages (a footer sign-up) is checked once per
probe instance, which lives for one scan, keyed by its fields and its submit
control. Never raises: a form the probe could not finish is left out.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from audit.analyzer.forms.base import (
    Attempt,
    FieldState,
    FormResult,
    Message,
    classify,
    skip_reason,
)
from audit.analyzer.interaction.probe import DEFAULT_BLOCKED_LABELS
from audit.analyzer.interaction.safety import exploration_guard
from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Dialog, Frame, Page, Request

log = get_logger(__name__)

DEFAULT_MAX_FORMS = 5
# Long enough for validation that runs a moment after the click (a debounce or
# a short async check); a page that takes longer is a known limit.
DEFAULT_SETTLE_MS = 1200
DEFAULT_TIMEOUT_S = 30.0

_COLLECT_JS = r"""
() => {
  const FIELD = 'input:not([type=hidden]):not([type=submit]):not([type=button])' +
    ':not([type=reset]):not([type=image]), textarea, select';
  const shown = el => !!el && el.getClientRects().length > 0 &&
    (el.checkVisibility
      ? el.checkVisibility({opacityProperty: true, visibilityProperty: true}) : true);
  const squash = s => (s || '').replace(/\s+/g, ' ').trim();
  const nameOf = el => squash(el.getAttribute('aria-label') || el.innerText || el.value ||
    el.getAttribute('title') || '');
  const fieldsIn = root => [...root.querySelectorAll(FIELD)]
    .filter(f => shown(f) && !f.disabled && !f.readOnly);
  const labelOf = f => {
    const by = (f.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => document.getElementById(id)?.textContent || '').join(' ');
    return squash(by || [...(f.labels || [])].map(l => l.textContent).join(' ') ||
      f.getAttribute('aria-label') || f.placeholder || f.name || '');
  };
  const isEmpty = f => {
    if (f.type === 'checkbox' || f.type === 'radio') return !f.checked;
    if (f.tagName === 'SELECT') return f.selectedIndex <= 0 || !f.value;
    return !f.value;
  };
  const path = el => {
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && parts.length < 5; n = n.parentElement) {
      if (n.id) { parts.unshift('#' + CSS.escape(n.id)); break; }
      let i = 1;
      for (let p = n.previousElementSibling; p; p = p.previousElementSibling) {
        if (p.tagName === n.tagName) i++;
      }
      parts.unshift(n.tagName.toLowerCase() + ':nth-of-type(' + i + ')');
    }
    return parts.join(' > ');
  };
  const SUBMITISH = new RegExp('\\b(submit|send|continue|next|sign up|register|apply|' +
    'request|join|subscribe|contact|book|create|add|update|save|go|done|finish|' +
    'get started|confirm)\\b', 'i');
  const units = [];
  const taken = [];
  for (const form of document.querySelectorAll('form')) {
    if (!shown(form)) continue;
    const fields = fieldsIn(form);
    if (!fields.length) continue;
    const SUBMITS = 'button[type=submit], button:not([type]), ' +
      'input[type=submit], input[type=image]';
    let submit = [...form.querySelectorAll(SUBMITS)].find(shown) || null;
    if (!submit && form.id) {
      submit = [...document.querySelectorAll('[form="' + CSS.escape(form.id) + '"]')]
        .find(b => shown(b) && (b.type === 'submit' || b.tagName === 'BUTTON')) || null;
    }
    units.push({root: form, submit, fields});
    taken.push(form);
  }
  // A group of fields with a submit-like button and no <form>, as many
  // single-page apps build them: the nearest container of the button that
  // holds fields.
  for (const b of document.querySelectorAll('button, [role=button], input[type=button]')) {
    if (b.closest('form') || !shown(b) || !SUBMITISH.test(nameOf(b))) continue;
    let c = b.parentElement;
    for (let depth = 0; c && depth < 6 && !fieldsIn(c).length; depth++) c = c.parentElement;
    if (!c || c === document.body || c === document.documentElement) continue;
    if (taken.some(t => t.contains(c) || c.contains(t))) continue;
    taken.push(c);
    units.push({root: c, submit: b, fields: fieldsIn(c)});
  }
  for (const u of units) {
    // Each field's own group: the largest ancestor that holds no other field,
    // so its label, hint and error text count as "beside it".
    u.groups = u.fields.map(f => {
      let g = f;
      while (g.parentElement && g.parentElement !== u.root &&
             fieldsIn(g.parentElement).length === 1) g = g.parentElement;
      return g;
    });
  }
  window.__axcessForms = units;
  const heading = root => {
    const h = root.querySelector('h1,h2,h3,h4,legend') ||
      root.previousElementSibling?.matches?.('h1,h2,h3,h4') && root.previousElementSibling;
    return squash(root.getAttribute('aria-label') || (h && h.textContent) || '');
  };
  return units.map(u => {
    const r = u.root;
    const words = [u.submit ? nameOf(u.submit) : '', heading(r)].join(' ');
    const ac = u.fields.map(f =>
      [f.getAttribute('autocomplete') || '', f.name || '', f.id || ''].join(' '));
    return {
      selector: path(r),
      label: heading(r) || (u.submit ? nameOf(u.submit) : '') || 'form',
      submit: u.submit ? nameOf(u.submit) : '',
      words,
      fields: u.fields.map((f, key) => ({
        key, label: labelOf(f), type: f.type || f.tagName.toLowerCase(), empty: isEmpty(f)})),
      // The browser shows its own message only for a real submit of a form
      // without novalidate. checkValidity() (Bootstrap's pattern) fires the
      // same invalid events and shows nothing.
      noValidate: r.tagName !== 'FORM' || r.noValidate || !!(u.submit && u.submit.formNoValidate),
      hasPassword: u.fields.some(f => f.type === 'password') ||
        !!r.querySelector('input[type=password]'),
      hasCard: ac.some(a => /\bcc-|card|cvv|cvc/i.test(a)),
      hasCaptcha: !!r.querySelector('iframe[src*="captcha" i], iframe[src*="turnstile" i], ' +
        '.g-recaptcha, .h-captcha, .cf-turnstile'),
      isSearch: r.matches('[role=search]') || !!r.closest('[role=search]') ||
        (u.fields.length === 1 && (u.fields[0].type === 'search' ||
          /^(q|query|search|s)$/i.test(u.fields[0].name || ''))),
    };
  });
}
"""

# Shared by the snapshot and the watcher: each visible piece of text in scope,
# with the fields it belongs to and whether it sits in an announced region.
_TEXT_HELPERS = r"""
  const u = window.__axcessForms[index];
  const squash = s => (s || '').replace(/\s+/g, ' ').trim();
  const seen = el => {
    if (!el || !el.getClientRects().length) return false;
    if (el.checkVisibility &&
        !el.checkVisibility({opacityProperty: true, visibilityProperty: true})) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1) return false;  // visually hidden
    const s = getComputedStyle(el);
    return !(s.clip === 'rect(0px, 0px, 0px, 0px)' || s.clipPath === 'inset(50%)');
  };
  const pseudo = (el, which) => {
    const c = getComputedStyle(el, which).content;
    return c && c !== 'none' && c !== 'normal' && /^["']/.test(c) ? c.slice(1, -1) : '';
  };
  const ownText = el => squash([pseudo(el, '::before'),
    ...[...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent),
    pseudo(el, '::after')].join(' '));
  const describedBy = u.fields.map(f => ((f.getAttribute('aria-describedby') || '') + ' ' +
    (f.getAttribute('aria-errormessage') || '')).split(/\s+/).filter(Boolean)
    .map(id => document.getElementById(id)).filter(Boolean));
  // The element right after a field (or after its group) when it holds no
  // field itself: where a message goes when fields have no wrapper.
  // Not when it holds a control: then it is the next part of the form (the
  // submit button's row, another step), not a note about this field.
  const nextTo = k => {
    const n = u.groups[k].nextElementSibling;
    const control = 'input, select, textarea, button, a[href], [role=button]';
    return n && !n.matches(control) && !n.querySelector(control) ? n : null;
  };
  const fieldsOf = el => {
    const keys = [];
    u.fields.forEach((f, k) => {
      if (u.groups[k].contains(el) || describedBy[k].some(d => d.contains(el)) ||
          [...(f.labels || [])].some(l => l.contains(el)) || nextTo(k)?.contains(el)) keys.push(k);
    });
    return keys;
  };
  const linkedTo = el => describedBy.some(ds => ds.some(d => d.contains(el)));
  const announced = el =>
    !!el.closest('[role=alert],[role=status],[aria-live]:not([aria-live=off])');
  const entry = el => {
    const text = ownText(el);
    if (!text || !seen(el)) return null;
    return {text, fields: fieldsOf(el), linked: linkedTo(el), announced: announced(el),
      colour: getComputedStyle(el).color};
  };
"""

_SNAPSHOT_JS = (
    r"""
(index) => {
"""
    + _TEXT_HELPERS
    + r"""
  const colours = el => {
    if (!el) return [];
    const s = getComputedStyle(el);
    const out = [s.borderTopColor, s.borderBottomColor, s.borderLeftColor,
      s.backgroundColor, s.color, s.stroke, s.fill];
    if (s.outlineStyle !== 'none') out.push(s.outlineColor);
    out.push(...(s.boxShadow.match(/rgba?\([^)]*\)/g) || []));
    return out;
  };
  const fields = u.fields.map((f, key) => {
    const label = f.labels && f.labels[0];
    const wrap = f.parentElement && f.parentElement !== u.root ? f.parentElement : null;
    // A radio or checkbox group is often marked on its fieldset and legend,
    // and a required mark (an asterisk) inside the field's own group.
    const set = f.closest('fieldset');
    const next = nextTo(key);
    const extra = [set, set && set.querySelector('legend'),
      ...[...u.groups[key].querySelectorAll('*')].slice(0, 12),
      next, ...(next ? [...next.querySelectorAll('*')].slice(0, 6) : [])];
    return {
      key,
      ariaInvalid: f.getAttribute('aria-invalid') === 'true',
      colours: [...colours(f), ...colours(wrap), ...colours(label), ...extra.flatMap(colours)],
      classes: [f.className, wrap ? wrap.className : '', label ? label.className : ''].join(' '),
    };
  });
  const texts = [];
  const scope = new Set([u.root,
    ...document.querySelectorAll('[role=alert],[role=status],[aria-live]'),
    ...describedBy.flat()]);
  for (const root of scope) {
    for (const el of [root, ...root.querySelectorAll('*')].slice(0, 3000)) {
      const e = entry(el);
      if (e) texts.push(e);
    }
  }
  // Every visible text on the page, so text that only moved or re-rendered
  // is not taken for a new message.
  const all = [];
  for (const el of [...document.body.querySelectorAll('*')].slice(0, 6000)) {
    const t = ownText(el);
    if (t && seen(el)) all.push(t);
  }
  return {fields, texts, all};
}
"""
)

_ARM_JS = (
    r"""
(index) => {
"""
    + _TEXT_HELPERS
    + r"""
  const logged = {invalid: [], texts: []};
  const scan = node => {
    if (!node || node.nodeType !== 1) return;
    for (const el of [node, ...node.querySelectorAll('*')].slice(0, 400)) {
      const e = entry(el);
      if (e) logged.texts.push({...e, t: Date.now()});
    }
  };
  const observer = new MutationObserver(records => {
    for (const r of records) {
      if (r.type === 'childList') {
        r.addedNodes.forEach(n => scan(n.nodeType === 3 ? n.parentElement : n));
      }
      else scan(r.type === 'characterData' ? r.target.parentElement : r.target);
    }
  });
  observer.observe(document.documentElement, {subtree: true, childList: true, characterData: true,
    attributes: true,
    attributeFilter: ['class', 'style', 'hidden', 'aria-hidden', 'aria-invalid']});
  const onInvalid = e => {
    const k = u.fields.indexOf(e.target);
    if (k >= 0) logged.invalid.push(k);
  };
  document.addEventListener('invalid', onInvalid, true);
  window.__axcessFormWatch = {logged, stop: () => {
    observer.disconnect();
    document.removeEventListener('invalid', onInvalid, true);
  }};
}
"""
)

_DISARM_JS = """
() => {
  const w = window.__axcessFormWatch;
  if (!w) return {invalid: [], texts: []};
  w.stop();
  return w.logged;
}
"""


@dataclass
class ErrorIdentificationProbe:
    """Submits each form once, empty and guarded, and reads what it said.

    One per scan: ``_seen`` remembers the forms already checked, so a form
    repeated on every page is checked once.
    """

    max_forms: int = DEFAULT_MAX_FORMS
    settle_ms: int = DEFAULT_SETTLE_MS
    timeout_s: float = DEFAULT_TIMEOUT_S
    _seen: set[str] = field(default_factory=set)

    async def run(self, page: Page) -> list[FormResult]:
        results: list[FormResult] = []
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(self.timeout_s):
                await self._run(page, results)
        return results

    async def _run(self, page: Page, results: list[FormResult]) -> None:
        pinned = page.url
        attempted = 0
        plan = await self._plan(page)
        for frame_index, form_index, info in plan:
            reason = self._skip(info)
            if reason:
                results.append(self._result("skipped", reason, info, page, frame_index))
                continue
            if attempted >= self.max_forms:
                results.append(
                    self._result(
                        "skipped",
                        f"more than {self.max_forms} forms on the page",
                        info,
                        page,
                        frame_index,
                    )
                )
                continue
            if attempted:
                # Start from the page as it first loaded, not as the last
                # attempt left it. Outside the guard, which blocks navigation.
                try:
                    await page.goto(pinned, wait_until="load", timeout=15000)
                except Exception as exc:
                    log.debug("forms.reload_failed", error_type=type(exc).__name__)
                    return
            attempted += 1
            frame = self._frame(page, frame_index)
            if frame is None:
                continue
            try:
                outcome = await self._attempt(page, frame, form_index, info)
            except Exception as exc:
                log.debug("forms.attempt_failed", error_type=type(exc).__name__)
                continue
            if outcome is not None:
                results.append(outcome)

    async def _plan(self, page: Page) -> list[tuple[int, int, dict[str, Any]]]:
        plan: list[tuple[int, int, dict[str, Any]]] = []
        for frame_index, frame in enumerate(page.frames):
            if frame is not page.main_frame:
                try:
                    if not await (await frame.frame_element()).is_visible():
                        continue
                except Exception as exc:
                    log.debug("forms.frame_skipped", error_type=type(exc).__name__)
                    continue
            try:
                forms = await frame.evaluate(_COLLECT_JS)
            except Exception as exc:
                log.debug("forms.collect_failed", error_type=type(exc).__name__)
                continue
            for form_index, info in enumerate(forms):
                key = self._key(info)
                if key in self._seen:
                    continue
                self._seen.add(key)
                plan.append((frame_index, form_index, info))
        return plan

    @staticmethod
    def _key(info: dict[str, Any]) -> str:
        fields = ",".join(f"{f['type']}:{f['label']}" for f in info["fields"])
        return f"{info['submit']}|{fields}"

    @staticmethod
    def _skip(info: dict[str, Any]) -> str | None:
        reason = skip_reason(
            has_password=info["hasPassword"],
            has_card=info["hasCard"],
            has_captcha=info["hasCaptcha"],
            is_search=info["isSearch"],
            has_submit=bool(info["submit"]),
            words=info["words"],
        )
        if reason is None and not any(f["empty"] for f in info["fields"]):
            # Submitting it would send values, which this check never does.
            reason = "nothing in the form is empty"
        return reason

    @staticmethod
    def _frame(page: Page, frame_index: int) -> Frame | None:
        frames = page.frames
        return frames[frame_index] if frame_index < len(frames) else None

    def _result(
        self, outcome: Any, reason: str, info: dict[str, Any], page: Page, frame_index: int
    ) -> FormResult:
        frame = self._frame(page, frame_index)
        return FormResult(
            outcome=outcome,
            reason=reason,
            form=info["label"][:120],
            selector=info["selector"],
            frame_url="" if frame is None or frame is page.main_frame else frame.url,
        )

    async def _attempt(
        self, page: Page, frame: Frame, form_index: int, info: dict[str, Any]
    ) -> FormResult | None:
        # Collect again: a reload replaced the elements the plan described.
        forms = await frame.evaluate(_COLLECT_JS)
        if form_index >= len(forms) or self._key(forms[form_index]) != self._key(info):
            return None
        before = await frame.evaluate(_SNAPSHOT_JS, form_index)
        await frame.evaluate(_ARM_JS, form_index)
        requests: list[float] = []
        dialogs: list[tuple[str, float]] = []

        def on_request(request: Request) -> None:
            with contextlib.suppress(Exception):
                if request.frame.page != page:
                    return
                if (
                    request.method not in {"GET", "HEAD", "OPTIONS"}
                    or request.is_navigation_request()
                ):
                    requests.append(time.time() * 1000)

        def on_dialog(dialog: Dialog) -> None:
            dialogs.append((dialog.message, time.time() * 1000))

        page.on("request", on_request)
        page.on("dialog", on_dialog)
        try:
            async with exploration_guard(page, set(), DEFAULT_BLOCKED_LABELS):
                submit = await frame.evaluate_handle(
                    "i => window.__axcessForms[i].submit", form_index
                )
                element = submit.as_element()
                if element is None:
                    return None
                await element.click(timeout=3000)
                await page.wait_for_timeout(self.settle_ms)
                # Hover and focus styles are not error marks.
                with contextlib.suppress(Exception):
                    await page.mouse.move(0, 0)
                    await frame.evaluate(
                        "() => document.activeElement && document.activeElement.blur()"
                    )
                    await page.wait_for_timeout(100)
                watched = await frame.evaluate(_DISARM_JS)
                after = await frame.evaluate(_SNAPSHOT_JS, form_index)
        finally:
            page.remove_listener("request", on_request)
            page.remove_listener("dialog", on_dialog)

        attempt = _attempt_from(info, before, after, watched, requests, dialogs)
        outcome, reason, undescribed = classify(attempt)
        labels = {f["key"]: f["label"] or f"field {f['key'] + 1}" for f in info["fields"]}
        result = self._result(
            outcome, reason, info, page, page.frames.index(frame) if frame in page.frames else 0
        )
        result.fields_in_error = [labels[k] for k in (undescribed or attempt.marked)]
        result.messages = [m.text for m in attempt.messages][:10]
        return result


def _is_error_colour(colour: str) -> bool:
    """Red or orange, saturated enough to read as an error mark."""
    parts = colour[colour.find("(") + 1 : colour.rfind(")")].replace("/", ",").split(",")
    try:
        r, g, b = (float(p) for p in parts[:3])
        alpha = float(parts[3]) if len(parts) > 3 else 1.0
    except ValueError:
        return False
    if alpha < 0.3:
        return False
    hi, lo = max(r, g, b) / 255, min(r, g, b) / 255
    light = (hi + lo) / 2
    if hi == lo or not 0.2 <= light <= 0.94:
        return False
    sat = (hi - lo) / (1 - abs(2 * light - 1))
    # Pale tints (a pink field background) count only when strongly tinted;
    # beige and cream, at hue 40 to 60, are excluded by the hue test below.
    if sat < 0.4 or (light > 0.8 and sat < 0.6):
        return False
    rn, gn, bn = r / 255, g / 255, b / 255
    if hi == rn:
        hue = (60 * ((gn - bn) / (hi - lo))) % 360
    elif hi == gn:
        hue = 60 * ((bn - rn) / (hi - lo)) + 120
    else:
        hue = 60 * ((rn - gn) / (hi - lo)) + 240
    return hue <= 40 or hue >= 340


_ERROR_CLASS = ("error", "invalid", "danger", "has-error", "is-error", "is-invalid")


def _attempt_from(
    info: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
    watched: dict[str, Any],
    requests: list[float],
    dialogs: list[tuple[str, float]],
) -> Attempt:
    first_request = min(requests) if requests else None
    states: list[FieldState] = []
    marked: list[int] = []
    for meta, old, new in zip(info["fields"], before["fields"], after["fields"], strict=False):
        newly_invalid = new["ariaInvalid"] and not old["ariaInvalid"]
        # Colours present now that were not before, counted as a multiset, so
        # a new red icon inside the field's group counts as well as a border
        # that changed colour.
        appeared = Counter(new["colours"]) - Counter(old["colours"])
        colour = any(_is_error_colour(c) for c in appeared)
        gained = set(new["classes"].lower().split()) - set(old["classes"].lower().split())
        error_class = any(any(word in cls for word in _ERROR_CLASS) for cls in gained)
        states.append(
            FieldState(
                meta["key"],
                meta["label"],
                new["ariaInvalid"],
                error_colour=colour,
                error_class=error_class,
            )
        )
        if newly_invalid or colour or error_class:
            marked.append(meta["key"])

    existing = set(before["all"])
    messages: dict[tuple[str, tuple[int, ...]], Message] = {}

    def add(item: dict[str, Any], when: float | None) -> None:
        text = item["text"]
        if not text or text in existing:
            return
        fields = tuple(sorted(item.get("fields", [])))
        key = (text, fields)
        early = first_request is None or (when is not None and when < first_request)
        old = messages.get(key)
        if old is None or (early and not old.before_request):
            colour = _is_error_colour(item.get("colour", ""))
            messages[key] = Message(
                text, fields, item.get("announced", False), early, colour, item.get("linked", False)
            )

    for item in watched["texts"]:
        add(item, item["t"])
    for item in after["texts"]:
        # Seen only after settling: before the first request only if the
        # watcher also saw it in time (added above); otherwise unknown.
        add(item, None)
    for text, when in dialogs:
        add({"text": text, "announced": True}, when)

    return Attempt(
        fields=tuple(states),
        marked=tuple(marked),
        messages=tuple(messages.values()),
        # Only a real submit of a form without novalidate shows the browser's
        # message; otherwise the invalid events came from checkValidity().
        native_invalid=() if info["noValidate"] else tuple(sorted(set(watched["invalid"]))),
        blocked_request=bool(requests),
    )
