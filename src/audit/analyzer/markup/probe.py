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
        for item in raw or []:
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
