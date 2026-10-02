"""Re-run the same rule check (axe) on the suggested markup, offline.

The suggested markup is loaded into a blank page in a local browser with
every network request blocked, so nothing is fetched and no site is
contacted. The answer is one of three:

* ``passed``: the rule ran on the new markup and found nothing.
* ``still_fails``: the rule still reports a problem.
* ``not_checked``: the check cannot judge markup on its own (contrast needs
  the page's styles; landmarks need the whole page), there was no markup,
  or the browser could not run.

A pass is about this one rule on this one fragment. It does not prove the
page meets WCAG, and the interface says so.
"""

from __future__ import annotations

import logging
from typing import Any, Literal, Protocol

from audit.analyzer.axe import DEFAULT_AXE_BUNDLE

log = logging.getLogger(__name__)

Outcome = Literal["passed", "still_fails", "not_checked"]

# Rules whose answer depends on the whole page or on its real styles, so a
# fragment on a blank page would give a misleading result either way.
_WHOLE_PAGE_RULES = frozenset(
    {
        "bypass",
        "color-contrast",
        "color-contrast-enhanced",
        "document-title",
        "duplicate-id",
        "duplicate-id-active",
        "duplicate-id-aria",
        "heading-order",
        "landmark-banner-is-top-level",
        "landmark-complementary-is-top-level",
        "landmark-contentinfo-is-top-level",
        "landmark-main-is-top-level",
        "landmark-no-duplicate-banner",
        "landmark-no-duplicate-contentinfo",
        "landmark-no-duplicate-main",
        "landmark-one-main",
        "landmark-unique",
        "link-in-text-block",
        "meta-refresh",
        "meta-viewport",
        "page-has-heading-one",
        "region",
        "scrollable-region-focusable",
        "target-size",
    }
)
_WHOLE_PAGE_PREFIXES = ("html-", "frame-", "aria-hidden-body")


def can_check(rule_id: str | None) -> bool:
    if not rule_id:
        return False
    return rule_id not in _WHOLE_PAGE_RULES and not rule_id.startswith(_WHOLE_PAGE_PREFIXES)


class Verifier(Protocol):
    async def check(self, rule_id: str | None, html: str | None, css: str | None) -> Outcome: ...


def _document(html: str, css: str | None) -> str:
    style = f"<style>{css}</style>" if css else ""
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Check</title>'
        f"{style}</head><body><main>{html}</main></body></html>"
    )


def _outcome(result: dict[str, Any]) -> Outcome:
    if result.get("violations"):
        return "still_fails"
    if result.get("passes"):
        return "passed"
    return "not_checked"


class AxeFragmentVerifier:
    def __init__(self, axe_source: str | None = None) -> None:
        self._axe_source = axe_source

    def _source(self) -> str | None:
        if self._axe_source is None:
            try:
                self._axe_source = DEFAULT_AXE_BUNDLE.read_text(encoding="utf-8")
            except OSError:
                return None
        return self._axe_source

    async def check(self, rule_id: str | None, html: str | None, css: str | None) -> Outcome:
        if not html or not can_check(rule_id):
            return "not_checked"
        source = self._source()
        if source is None:
            return "not_checked"
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(offline=True)
                    await context.route("**/*", lambda route: route.abort())
                    page = await context.new_page()
                    await page.set_content(_document(html, css), wait_until="domcontentloaded")
                    await page.evaluate(source)
                    result: dict[str, Any] = await page.evaluate(
                        """async (rule) => {
                            const r = await window.axe.run(document, {
                                runOnly: { type: 'rule', values: [rule] },
                            });
                            return { violations: r.violations.length, passes: r.passes.length };
                        }""",
                        rule_id,
                    )
                finally:
                    await browser.close()
        except Exception as exc:  # a missing browser must not fail the suggestion
            log.warning("suggest.verify_failed: %s", type(exc).__name__)
            return "not_checked"
        return _outcome(result)
