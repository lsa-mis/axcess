"""Per-criterion semantic accessibility analyzers (Phase 9+).

This package adds LLM-driven detection of WCAG success criteria that
rule-based tools (axe-core) can't reliably check — link descriptiveness,
heading meaningfulness, label-in-name match, and so on.

Architecture mirrors the GenA11y paper (He, Huq, Malek; FSE 2025):
per-criterion element extraction → per-criterion prompt → structured
JSON output → page_a11y_findings row with ``pipeline='semantic'``.

Modules:

* :mod:`audit.analyzer.semantic.base` — :class:`SemanticFinding` dataclass
  and the :class:`SemanticAnalyzer` protocol every per-criterion
  analyzer implements.
* :mod:`audit.analyzer.semantic.ollama_text` — generic text-only
  Ollama client. Caller-owned prompts; ``generate(prompt) -> str``.
* :mod:`audit.analyzer.semantic.runner` — orchestrates "for each SC,
  extract, analyze, collect" with bounded concurrency.
* :mod:`audit.analyzer.semantic.extractor` — per-criterion DOM/CSS
  element extraction. Reuses selectolax for the static portion and
  Playwright ``page.evaluate()`` for the computed-style portion.
"""

from audit.analyzer.semantic.base import (
    AnalysisContext,
    SemanticAnalyzer,
    SemanticFinding,
)
from audit.analyzer.semantic.ollama_text import OllamaTextProvider
from audit.analyzer.semantic.registry import build_analyzers, supported_criteria

__all__ = [
    "AnalysisContext",
    "OllamaTextProvider",
    "SemanticAnalyzer",
    "SemanticFinding",
    "build_analyzers",
    "supported_criteria",
]
