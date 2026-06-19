"""Registry of per-criterion analyzer classes.

The orchestrator reads ``config.semantic_criteria`` (a tuple of WCAG
SC dotted strings), looks each one up here, and instantiates the
matching analyzer with a shared :class:`OllamaTextProvider`. Unknown
SCs are logged and skipped — that lets ``--semantic-criteria 2.4.4,
9.9.9`` still run 2.4.4 cleanly while flagging the typo.

To add a new criterion: write the analyzer class, import it here,
add the ``{sc: cls}`` row, write the prompt template, and add a
fixture HTML page. The runner picks it up on the next crawl.
"""

from __future__ import annotations

from collections.abc import Sequence

from audit.analyzer.model_registry import get_pick
from audit.analyzer.semantic.analyzers import LinkPurposeInContextAnalyzer
from audit.analyzer.semantic.base import SemanticAnalyzer
from audit.analyzer.semantic.ollama_text import OllamaTextProvider
from audit.logging import get_logger

log = get_logger(__name__)

# {WCAG SC -> analyzer class}. The lookup is exact-match on the
# dotted string; we deliberately do NOT fuzzy-match (so a typo like
# "2.4.04" is caught loudly).
_REGISTRY: dict[str, type[SemanticAnalyzer]] = {
    "2.4.4": LinkPurposeInContextAnalyzer,
    # Wave-1 SCs land in Phase 9.2; each adds one row here.
}


def supported_criteria() -> list[str]:
    """Return every SC the registry can analyze, in stable order."""
    return sorted(_REGISTRY.keys())


def build_analyzers(
    criteria: Sequence[str],
    provider: OllamaTextProvider,
) -> list[SemanticAnalyzer]:
    """Instantiate the analyzers for the requested ``criteria``.

    Unknown SCs are logged at WARNING and skipped — never raise. This
    keeps the orchestrator's "list of criteria" config robust: a
    typo doesn't crash a 10k-page crawl, it just means one fewer
    analyzer runs.

    Per-criterion model picks come from
    :mod:`audit.analyzer.model_registry`. The shared
    :class:`OllamaTextProvider` carries the default model; the
    per-criterion pick is passed through as the analyzer's
    ``model=`` override so a single provider can drive every analyzer
    while still using the right model for each.
    """
    out: list[SemanticAnalyzer] = []
    seen: set[str] = set()
    for sc in criteria:
        sc = sc.strip()
        if not sc:
            continue
        if sc in seen:
            # De-dupe so `--semantic-criteria 2.4.4,2.4.4` doesn't
            # double-bill the LLM.
            continue
        seen.add(sc)
        cls = _REGISTRY.get(sc)
        if cls is None:
            log.warning(
                "semantic.unknown_criterion",
                criterion=sc,
                supported=supported_criteria(),
            )
            continue
        # Look up the model recommended for this SC. The registry
        # falls back to a sensible default if the SC has no pin.
        pick = get_pick(sc)
        out.append(cls(provider, model=pick.primary))  # type: ignore[call-arg]
    return out


__all__ = ["build_analyzers", "supported_criteria"]
