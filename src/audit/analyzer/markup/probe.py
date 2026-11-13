"""The page code check: the browser part.

Runs on each rendered page after the rule check (axe), and before any check
that presses keys, clicks or resizes the page, so it reads the page code
(DOM) as the page loaded. It only reads: nothing is focused, clicked or
changed. Each rule is one ``page.evaluate`` that returns at most the rule's
``max_results`` elements as ``{selector, html, detail}``; Python turns
``detail`` into the occurrence's plain-language summary.

Bounded: at most :data:`MAX_ELEMENTS` elements are read per rule, at most
``max_results`` are returned, and element code (HTML) is cut to
:data:`~audit.analyzer.markup.base.MAX_SNIPPET_CHARS`. Never raises: a rule
that fails is logged and left out, and the other rules still run.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from audit.analyzer.markup.base import (
    MAX_SNIPPET_CHARS,
    RULE_LABEL_FOR_MISSING,
    RULE_PLACEHOLDER_ONLY,
    RULE_STYLED_AS_HEADING,
    RULE_TITLE_REPEATS_TEXT,
    RULES,
    MarkupFinding,
)
from audit.logging import get_logger

if TYPE_CHECKING:
    from playwright.async_api import Page

log = get_logger(__name__)

# Elements read per rule, at most, so a page with tens of thousands of
# elements costs the same as one with a few thousand.
MAX_ELEMENTS = 5000

# Shared by every rule's script, inside its own function scope.
#   path(el)     a CSS selector that matches this element alone, as the form
#                error check builds it (an id, else nth-of-type steps).
#   squash(s)    whitespace collapsed and trimmed.
#   rendered(el) the element has a box: not display:none, not inside one, and
#                not visibility:hidden.
#   shown(el)    rendered, and not visually hidden: no zero opacity, no
#                clipped one-pixel box (the "screen-reader-only" pattern),
#                and not inside aria-hidden="true".
#   snippet(el)  the element's code (HTML), cut to the snippet cap.
_HELPERS = """
  const path = el => {
    const parts = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      if (n.id) { parts.unshift('#' + CSS.escape(n.id)); break; }
      let i = 1;
      for (let p = n.previousElementSibling; p; p = p.previousElementSibling) {
        if (p.tagName === n.tagName) i++;
      }
      parts.unshift(n.tagName.toLowerCase() + ':nth-of-type(' + i + ')');
      if (n !== el && document.querySelectorAll(parts.join(' > ')).length === 1) break;
    }
    return parts.join(' > ');
  };
  const squash = s => (s || '').replace(/\\s+/g, ' ').trim();
  const rendered = el => {
    if (!el || !el.isConnected || !el.getClientRects().length) return false;
    return getComputedStyle(el).visibility !== 'hidden';
  };
  const shown = el => {
    if (!rendered(el)) return false;
    if (el.closest('[aria-hidden="true"]')) return false;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (parseFloat(s.opacity) === 0) return false;
      if (s.clip === 'rect(0px, 0px, 0px, 0px)' || s.clipPath === 'inset(50%)') return false;
      const r = n.getBoundingClientRect();
      if (r.width <= 1 && r.height <= 1 && s.overflow === 'hidden') return false;
    }
    return true;
  };
  const snippet = el => (el.outerHTML || '').slice(0, SNIPPET);
"""

# Each rule's script: the body of ``(args) => { ... }``, after the helpers,
# with ``cap`` (results), ``limit`` (elements read) and ``SNIPPET`` in scope.
# Returns a list of ``{selector, html, detail}``.
_RULE_JS: dict[str, str] = {}

# Each rule's summary, from the ``detail`` its script returned. Shown with
# the occurrence, so it follows docs/plain-language.md.
_SUMMARIES: dict[str, Callable[[Mapping[str, Any]], str]] = {}

# A field whose only name is its placeholder: an input (not hidden, submit,
# button, reset or image), textarea or select with placeholder text, and no
# label with text (``el.labels``), no aria-label, no aria-labelledby that
# points at text, and no title. A label's text leaves out the text of the
# controls inside it, so a select's options never count as its label.
# Fields hidden from everyone, or visually hidden, are skipped.
_RULE_JS[RULE_PLACEHOLDER_ONLY] = """
  const NO_PLACEHOLDER = new Set(['hidden', 'submit', 'button', 'reset', 'image']);
  const labelText = label => {
    let text = '';
    const walk = node => {
      for (const child of node.childNodes) {
        if (child.nodeType === 3) text += child.nodeValue;
        else if (child.nodeType === 1) {
          if (child.matches('input, select, textarea, button, option, script, style')) continue;
          if (child.tagName === 'IMG') text += ' ' + (child.getAttribute('alt') || '');
          else walk(child);
        }
      }
    };
    walk(label);
    return squash(text);
  };
  const named = (root, id) => {
    const target = root.getElementById ? root.getElementById(id) : document.getElementById(id);
    return !!target && !!squash(target.getAttribute('aria-label') || target.textContent);
  };
  const out = [];
  const fields = Array.from(
    document.querySelectorAll('input[placeholder], textarea[placeholder], select[placeholder]')
  ).slice(0, limit);
  for (const el of fields) {
    if (out.length >= cap) break;
    if (el.tagName === 'INPUT' && NO_PLACEHOLDER.has((el.type || '').toLowerCase())) continue;
    const placeholder = squash(el.getAttribute('placeholder'));
    if (!placeholder) continue;
    if (Array.from(el.labels || []).some(label => labelText(label))) continue;
    if (squash(el.getAttribute('aria-label'))) continue;
    const ids = squash(el.getAttribute('aria-labelledby')).split(' ').filter(Boolean);
    if (ids.some(id => named(el.getRootNode(), id))) continue;
    if (squash(el.getAttribute('title'))) continue;
    if (!shown(el)) continue;
    out.push({
      selector: path(el),
      html: snippet(el),
      detail: {placeholder: placeholder.slice(0, 200), tag: el.tagName.toLowerCase()},
    });
  }
  return out;
"""
_SUMMARIES[RULE_PLACEHOLDER_ONLY] = lambda d: (
    f"This field's only name is its placeholder text, {_quote(d.get('placeholder'))}. "
    "It has no label (a label element), aria-label, aria-labelledby or title, so once "
    "someone types, nothing on screen says what the field is for."
)

# A <label for> the browser ties to nothing: ``label.control`` is null, so
# the for value names no element in the label's document (or shadow root),
# or names one a label cannot name (a div, a hidden input). A label hidden
# from everyone (display:none) is skipped: it names nothing anyway. A label
# hidden only from sight (the screen-reader-only pattern) is still flagged,
# because it exists for screen reader users, the people this gap affects.
# The detail names the field just after the label, when there is one, so
# the summary can say which id the for value probably meant.
_RULE_JS[RULE_LABEL_FOR_MISSING] = """
  const LABELABLE = 'button, input:not([type=hidden]), meter, output, progress, select, textarea';
  const nearby = label => {
    let n = label;
    for (let step = 0; step < 3 && n; step++) {
      n = n.nextElementSibling;
      if (!n) break;
      const field = n.matches(LABELABLE) ? n : n.querySelector(LABELABLE);
      if (field) return field;
    }
    return null;
  };
  const out = [];
  const labels = Array.from(document.querySelectorAll('label[for]')).slice(0, limit);
  for (const label of labels) {
    if (out.length >= cap) break;
    if (label.control) continue;
    if (!rendered(label)) continue;
    const forId = label.getAttribute('for') || '';
    const root = label.getRootNode();
    const target = forId && root.getElementById ? root.getElementById(forId) : null;
    const field = nearby(label);
    out.push({
      selector: path(label),
      html: snippet(label),
      detail: {
        for: forId.slice(0, 200),
        text: squash(label.textContent).slice(0, 200),
        target: target ? target.tagName.toLowerCase() : '',
        next_id: field && field.id ? field.id.slice(0, 200) : '',
      },
    });
  }
  return out;
"""


def _label_for_summary(d: Mapping[str, Any]) -> str:
    target = str(d.get("target") or "")
    parts = [
        f"This label, {_quote(d.get('text'))}, has for={_quote(d.get('for'))}, "
        + (
            f"which points at a <{target}> element, and a label cannot name that."
            if target
            else "but no element on the page has that id."
        ),
        "So the label is tied to no field, and a screen reader does not read it with any field.",
    ]
    next_id = str(d.get("next_id") or "")
    if next_id and next_id != d.get("for"):
        parts.append(f"The field after it has id={_quote(next_id)}.")
    return " ".join(parts)


_SUMMARIES[RULE_LABEL_FOR_MISSING] = _label_for_summary

# A title on a link, button or input (or an element with role link or
# button) that says the same as the element's own visible text, ignoring
# case and spacing. The visible text is what is drawn (innerText), the value
# of a submit, button or reset input, or another input's label text. A
# control with no visible text is skipped: there, a title may be its only
# name, which is a different question. Hidden elements are skipped.
_RULE_JS[RULE_TITLE_REPEATS_TEXT] = """
  const BUTTON_INPUTS = new Set(['submit', 'button', 'reset']);
  const visibleText = el => {
    if (el.tagName === 'INPUT') {
      if (BUTTON_INPUTS.has((el.type || '').toLowerCase())) return squash(el.value);
      return squash(Array.from(el.labels || []).map(label => label.innerText).join(' '));
    }
    return squash(el.innerText);
  };
  const out = [];
  const els = Array.from(document.querySelectorAll(
    'a[href][title], button[title], input[title], [role=link][title], [role=button][title]'
  )).slice(0, limit);
  for (const el of els) {
    if (out.length >= cap) break;
    const title = squash(el.getAttribute('title'));
    if (!title) continue;
    const text = visibleText(el);
    if (!text || text.toLowerCase() !== title.toLowerCase()) continue;
    if (!shown(el)) continue;
    out.push({
      selector: path(el),
      html: snippet(el),
      detail: {title: title.slice(0, 200), tag: el.tagName.toLowerCase()},
    });
  }
  return out;
"""
_SUMMARIES[RULE_TITLE_REPEATS_TEXT] = lambda d: (
    f"This element's title, {_quote(d.get('title'))}, says the same as its visible text. "
    "Some screen readers read both, so people hear the same words twice."
)

# Text styled like a heading but not marked up as one (WCAG failure F2). A
# guess, so every condition narrows it:
#   - a p, div or span drawn as a block (display block, flex, grid, table,
#     list-item or flow-root) whose children are only inline text elements
#     (span, strong, b, em, i and the like), so it is one line of text;
#   - 1 to 80 characters on one line, with a letter, not ending like a
#     sentence (. ! ? , ;);
#   - every piece of its text bold (font-weight 600 or more), or every piece
#     at least 1.25 times the body's font size;
#   - not inside a heading or role=heading, nor inside a control or a part
#     that already has its own meaning: label, button, a, li, th, td, legend,
#     summary, caption, dt, option, or a role of button, link, tab,
#     menuitem, option or treeitem;
#   - followed by more content: the next element with text after it, which
#     is not a heading;
#   - not one of a run of short bold or large lines (the element with text
#     just before or after it is not another one): a run is an address or a
#     list of names, not headings;
#   - shown: not hidden from everyone or visually hidden.
# The outermost match wins: a styled span inside a matched p is not counted
# again.
_RULE_JS[RULE_STYLED_AS_HEADING] = """
  const BLOCK = new Set(['block', 'flex', 'grid', 'table', 'list-item', 'flow-root']);
  const INLINE = new Set(['SPAN', 'STRONG', 'B', 'EM', 'I', 'U', 'SMALL', 'MARK', 'FONT',
    'SUP', 'SUB', 'ABBR', 'CODE', 'TIME', 'Q', 'CITE', 'DFN', 'S', 'DEL', 'INS']);
  const MEANING = 'h1, h2, h3, h4, h5, h6, [role=heading], label, button, a, li, th, td, ' +
    'legend, summary, caption, dt, option, [role=button], [role=link], [role=tab], ' +
    '[role=menuitem], [role=option], [role=treeitem]';
  const HEADING = 'h1, h2, h3, h4, h5, h6, [role=heading]';
  const bodySize = parseFloat(getComputedStyle(document.body).fontSize) || 16;
  const weight = s => {
    const w = parseInt(s.fontWeight, 10);
    if (Number.isFinite(w)) return w;
    return s.fontWeight === 'bold' || s.fontWeight === 'bolder' ? 700 : 400;
  };
  const style = el => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let bold = true, big = true, any = false, size = 0;
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.nodeValue.trim()) continue;
      any = true;
      const s = getComputedStyle(n.parentElement);
      if (weight(s) < 600) bold = false;
      const fs = parseFloat(s.fontSize) || 0;
      size = Math.max(size, fs);
      if (fs < bodySize * 1.25) big = false;
    }
    return any && (bold || big) ? {bold, big, size} : null;
  };
  const line = el => (el.innerText || '').trim();
  const looksLikeOne = el => {
    const text = line(el);
    return text.length > 0 && text.length <= 80 && !text.includes('\\n') && !!style(el);
  };
  // The nearest element with text after (or before) this one, leaving the
  // blocks it sits in when they run out of siblings.
  const near = (el, sibling) => {
    let n = el;
    for (let step = 0; n && step < 50; step++) {
      if (n[sibling]) {
        n = n[sibling];
        if (rendered(n) && squash(n.innerText)) return n;
        continue;
      }
      n = n.parentElement;
      if (!n || n === document.body || n === document.documentElement) return null;
    }
    return null;
  };
  const out = [];
  const taken = [];
  const els = Array.from(document.querySelectorAll('p, div, span')).slice(0, limit);
  for (const el of els) {
    if (out.length >= cap) break;
    if (taken.some(t => t.contains(el))) continue;
    if (!BLOCK.has(getComputedStyle(el).display)) continue;
    if (!Array.from(el.querySelectorAll('*')).every(c => INLINE.has(c.tagName))) continue;
    const text = line(el);
    if (!text || text.length > 80 || text.includes('\\n')) continue;
    if (!/[A-Za-z\\u00C0-\\u024F\\u0370-\\u03FF\\u0400-\\u04FF]/.test(text)) continue;
    if (/[.!?,;]$/.test(text)) continue;
    if (el.closest(MEANING)) continue;
    const styled = style(el);
    if (!styled) continue;
    const next = near(el, 'nextElementSibling');
    if (!next || next.matches(HEADING) || next.querySelector(HEADING)) continue;
    const previous = near(el, 'previousElementSibling');
    if (looksLikeOne(next) || (previous && looksLikeOne(previous))) continue;
    if (!shown(el)) continue;
    taken.push(el);
    out.push({
      selector: path(el),
      html: snippet(el),
      detail: {
        text: text.slice(0, 200),
        bold: styled.bold,
        big: styled.big,
        size: Math.round(styled.size),
        body: Math.round(bodySize),
      },
    });
  }
  return out;
"""


def _styled_heading_summary(d: Mapping[str, Any]) -> str:
    looks = []
    if d.get("bold"):
        looks.append("bold")
    if d.get("big"):
        looks.append(f"larger than the body text ({d.get('size')} pixels, not {d.get('body')})")
    style = " and ".join(looks) or "styled"
    return (
        f"This text may be a heading: {_quote(d.get('text'))}. It is {style}, on a line "
        "of its own, and comes before more content, but it is not marked up as a heading "
        "(h1 to h6). This is a guess: check whether it starts a section."
    )


_SUMMARIES[RULE_STYLED_AS_HEADING] = _styled_heading_summary


def _script(body: str) -> str:
    return "(args) => {\n  const {cap, limit, SNIPPET} = args;\n" + _HELPERS + body + "\n}"


def _quote(text: Any, limit: int = 120) -> str:
    """Page text for a summary: whitespace collapsed, cut, in quotes."""
    value = " ".join(str(text or "").split())
    if len(value) > limit:
        value = value[: limit - 1] + "…"
    return f'"{value}"'


@dataclass
class MarkupProbe:
    """Runs every page code rule against a live page."""

    max_elements: int = MAX_ELEMENTS
    # The protected companion must not log browser exception text, which can
    # carry an authenticated route or page text (as the focus check).
    suppress_diagnostics: bool = False

    async def run(self, page: Page) -> list[MarkupFinding]:
        """Run each rule. Never raises: each rule is isolated, so one that
        fails does not lose the others' occurrences."""
        findings: list[MarkupFinding] = []
        for rule_id, body in _RULE_JS.items():
            try:
                findings.extend(await self._run_rule(page, rule_id, body))
            except Exception as exc:
                if self.suppress_diagnostics:
                    log.warning("markup.rule_failed_in_protected_context", rule_id=rule_id)
                else:
                    log.warning("markup.rule_failed", rule_id=rule_id, error=str(exc))
        return findings

    async def _run_rule(self, page: Page, rule_id: str, body: str) -> list[MarkupFinding]:
        rule = RULES[rule_id]
        raw: Any = await page.evaluate(
            _script(body),
            {"cap": rule.max_results, "limit": self.max_elements, "SNIPPET": MAX_SNIPPET_CHARS},
        )
        summarize = _SUMMARIES[rule_id]
        out: list[MarkupFinding] = []
        seen: set[str] = set()
        # A page that redefines built-ins can hand back anything.
        for item in raw if isinstance(raw, list) else []:
            if len(out) >= rule.max_results:
                break
            if not isinstance(item, dict):
                continue
            selector = str(item.get("selector") or "").strip()
            if not selector or selector in seen:
                continue
            seen.add(selector)
            detail = item.get("detail")
            out.append(
                MarkupFinding(
                    rule_id=rule_id,
                    target_selector=selector,
                    html_snippet=str(item.get("html") or "")[:MAX_SNIPPET_CHARS],
                    failure_summary=summarize(detail if isinstance(detail, dict) else {})[:1000],
                )
            )
        return out
