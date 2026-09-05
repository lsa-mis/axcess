"""Protocol + dataclass that every per-criterion analyzer implements.

The shape mirrors how axe-core findings reach the rest of the system
(see ``audit.analyzer.axe.AxeViolation``) so the runner can persist
semantic findings through the existing ``page_a11y_findings`` table
with only a ``pipeline`` discriminator swap.

Keep this tiny on purpose. Per-criterion analyzers expand prompts +
extraction; the shared contract here just describes what they hand
back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Inputs every per-criterion analyzer receives.

    Most static SCs (link purpose, heading descriptiveness, label-in-name)
    only need the rendered HTML body, selectolax parses it; no
    Playwright required. A few SCs (1.4.3 contrast, 2.4.7 focus visible)
    need a live Playwright Page so the analyzer can call
    ``page.evaluate()`` for computed styles. The context carries both;
    analyzers pick what they need.

    ``page`` is intentionally typed ``Any`` here so this module doesn't
    import Playwright at module load, keeping the contract narrow
    means analyzers that don't need a Page never indirectly drag in
    the dependency.
    """

    body: bytes  # rendered HTML, after JS settle if the fetcher used Playwright
    page: Any | None = None  # live Playwright Page, only set on JS-rendered fetches
    page_url: str = ""  # for logging / error messages, not for parsing


@dataclass(frozen=True, slots=True)
class SemanticFinding:
    """One per-criterion LLM-detected accessibility violation.

    Shape intentionally close to :class:`audit.analyzer.axe.AxeViolation`:
    same persistence sink, same UI surface, same triage workflow. The
    differences:

    * ``criterion_sc`` is mandatory, the per-criterion analyzer always
      knows which WCAG SC it's about, where axe rules sometimes
      aren't SC-mapped at all (best-practice rules).
    * No ``rule_id``, there's no axe rule. The DB-side helper
      composes a synthetic ``rule_id = f"semantic:{criterion_sc}"`` so
      the existing UNIQUE constraint on
      ``(page_id, rule_id, target_hash)`` still applies.

    Fields are the same flat shape regardless of which SC produced the
    finding so the runner can collect a heterogeneous list and pass
    them all through one persistence loop.
    """

    criterion_sc: str  # e.g. "2.4.4"
    wcag_level: str | None  # "A" | "AA" | "AAA"
    impact: str | None  # critical | serious | moderate | minor
    help: str  # short human-readable explanation of *this* failure
    target_selector: str  # CSS selector for the failing element
    failure_summary: str  # why-it-failed prose from the model
    html_snippet: str  # the failing element's outerHTML (truncated)
    target_hash: str  # dedupe key, (criterion, selector, snippet)
    help_url: str | None = None  # WCAG docs link, optional
    wcag_scs: str | None = None  # multi-mapped SCs, comma-separated

    def to_repo_kwargs(self) -> dict[str, Any]:
        """Convert to the kwargs ``repo.upsert_semantic_finding`` expects."""
        return {
            "criterion_sc": self.criterion_sc,
            "wcag_level": self.wcag_level,
            "impact": self.impact,
            "help": self.help,
            "target_selector": self.target_selector,
            "failure_summary": self.failure_summary,
            "html_snippet": self.html_snippet,
            "target_hash": self.target_hash,
            "help_url": self.help_url,
            "wcag_scs": self.wcag_scs,
        }


class SemanticAnalyzer(Protocol):
    """Per-criterion analyzer interface.

    Every analyzer takes a Playwright page (for DOM/computed-style
    extraction) and returns a list of :class:`SemanticFinding` rows.

    Analyzers MAY return an empty list when there are no violations,
    or when the page has no elements the analyzer cares about (e.g.
    a link-purpose analyzer running on a page with zero ``<a href>``
    tags). They SHOULD NOT raise on transient model failures —
    the runner expects per-criterion failures to be logged but
    non-fatal (mirrors axe runner behavior).
    """

    criterion_sc: str
    """The WCAG SC this analyzer is about, e.g. ``"2.4.4"``."""

    async def analyze(self, ctx: AnalysisContext) -> list[SemanticFinding]:
        """Run the analyzer against a fetched page.

        ``ctx.body`` is always set; ``ctx.page`` is set only when the
        Playwright fetcher was used. Static-only analyzers ignore
        ``page`` entirely; computed-style analyzers check for ``None``
        and short-circuit if the page was fetched statically.
        """
        ...


__all__ = ["AnalysisContext", "SemanticAnalyzer", "SemanticFinding"]
