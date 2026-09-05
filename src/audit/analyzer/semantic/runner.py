"""Per-criterion analyzer orchestration.

The runner is the bit the crawler's ``_process_one`` calls once per
page. It owns:

* Picking which criteria to run (from ``config.semantic_criteria``).
* Calling each analyzer in parallel via ``asyncio.gather`` (bounded
  by the shared :class:`OllamaTextProvider` semaphore, *not* by a
  per-criterion semaphore, because the bottleneck is Ollama, not
  Python's event loop).
* Collecting :class:`SemanticFinding` rows.
* Logging per-criterion failures without killing the page (mirrors
  ``axe.py``'s pattern at line 261-262).

This module ships as a stub in Phase 9.0. The first concrete
analyzer (SC 2.4.4) lands in Phase 9.1; the rest of the wave 1 SCs
follow in Phase 9.2. The shape is here so the orchestrator wiring
in Phase 9.0 has something to call.
"""

from __future__ import annotations

import asyncio

from audit.analyzer.semantic.base import (
    AnalysisContext,
    SemanticAnalyzer,
    SemanticFinding,
)
from audit.logging import get_logger

log = get_logger(__name__)


async def analyze_page(
    ctx: AnalysisContext,
    analyzers: list[SemanticAnalyzer],
) -> list[SemanticFinding]:
    """Run every analyzer against ``page``; return the flat list of findings.

    Per-criterion failures are logged at WARNING and dropped from the
    result list, they must not bubble out and kill the page's other
    analyzers or the crawl's other pages. This mirrors the axe runner's
    behavior in ``audit.analyzer.axe`` so the failure-mode contract is
    uniform across pipelines.

    Analyzers run concurrently via :func:`asyncio.gather`; the actual
    throttling is at the Ollama-client level (each analyzer shares the
    same :class:`OllamaTextProvider` instance and its semaphore), so
    ``gather`` here doesn't multiply load on the daemon, it just gives
    each analyzer a chance to make progress while others wait for the
    semaphore.
    """
    if not analyzers:
        return []
    tasks = [analyzer.analyze(ctx) for analyzer in analyzers]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    findings: list[SemanticFinding] = []
    for analyzer, result in zip(analyzers, raw_results, strict=True):
        if isinstance(result, BaseException):
            # asyncio.gather(..., return_exceptions=True) replaces
            # raises with the exception object in place. Anything
            # non-Exception (Cancel, KeyboardInterrupt) flowing here
            # is also a per-analyzer event we want to log + skip
            # rather than tear down the page.
            log.warning(
                "semantic.analyzer_failed",
                criterion=analyzer.criterion_sc,
                error=str(result),
            )
            continue
        findings.extend(result)
    return findings


__all__ = ["analyze_page"]
