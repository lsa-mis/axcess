"""SC 2.4.4 — Link Purpose (In Context) analyzer.

The Phase 9.1 pilot. Per the plan: extract every navigable link plus
its 5-level ancestor context, send a focused prompt to a local Ollama
text model, parse the model's JSON response into
:class:`SemanticFinding` rows.

The analyzer is built to be wrong gracefully: a malformed model
response, an unreachable Ollama daemon, an empty page, all return an
empty findings list with a logged warning. The crawl moves on.

Token budget: ``MAX_LINKS_PER_CALL`` caps how many links we feed in
one prompt. A page with 200 links → first 50 go in; the rest are
logged and dropped for this pass. Most pages have ≤ 30 navigable
links so this caps the worst case rather than the median.
"""

from __future__ import annotations

import hashlib
from importlib import resources
from typing import Any

from audit.analyzer.ollama_base import OllamaError, prompt_content_version
from audit.analyzer.semantic.base import (
    AnalysisContext,
    SemanticFinding,
)
from audit.analyzer.semantic.extractor import LinkRecord, extract_links
from audit.analyzer.semantic.ollama_text import OllamaTextProvider
from audit.logging import get_logger

log = get_logger(__name__)

_PROMPT_PACKAGE = "audit.analyzer.semantic.prompts"
PROMPT_NAME = "sc_2_4_4_link_purpose_in_context.txt"

# Hard cap so a 1000-link page can't blow the prompt budget. Picked at
# 50 because that's where qwen2.5:7b's accuracy on similar bounded
# tasks plateaus in informal testing — bigger batches dilute attention.
MAX_LINKS_PER_CALL = 50


def _load_prompt() -> str:
    """Read the SC 2.4.4 prompt template from the packaged ``prompts/`` dir."""
    return (resources.files(_PROMPT_PACKAGE) / PROMPT_NAME).read_text(encoding="utf-8")


class LinkPurposeInContextAnalyzer:
    """LLM-driven SC 2.4.4 analyzer.

    Instances share the :class:`OllamaTextProvider` with the rest of
    the semantic runner so the daemon-side concurrency is bounded by
    a single semaphore.
    """

    criterion_sc = "2.4.4"

    def __init__(
        self,
        provider: OllamaTextProvider,
        *,
        model: str | None = None,
        prompt_template: str | None = None,
    ) -> None:
        self._provider = provider
        # `model` override is for the registry to swap per-criterion
        # picks (e.g. SC 2.5.3 uses 14B). None means "use whatever the
        # provider was constructed with."
        self._model = model
        self._prompt_template = prompt_template or _load_prompt()
        self.prompt_version = prompt_content_version(self._prompt_template)

    async def analyze(self, ctx: AnalysisContext) -> list[SemanticFinding]:
        """Run SC 2.4.4 against the page in ``ctx``."""
        links = extract_links(ctx.body)
        if not links:
            # No navigable links → trivially compliant. Returning an
            # empty list is the contract; the runner will move on.
            return []

        chunk = links[:MAX_LINKS_PER_CALL]
        if len(links) > MAX_LINKS_PER_CALL:
            log.info(
                "sc_2_4_4.links_truncated",
                page_url=ctx.page_url,
                total=len(links),
                kept=MAX_LINKS_PER_CALL,
            )

        prompt = self._render_prompt(chunk)
        try:
            raw = await self._provider.generate_json(prompt, model=self._model)
        except OllamaError as exc:
            log.warning(
                "sc_2_4_4.llm_failed",
                page_url=ctx.page_url,
                error=str(exc),
            )
            return []

        return list(self._parse_response(raw, chunk))

    # ----------------------------------------------------------------
    # Prompt rendering.
    # ----------------------------------------------------------------

    def _render_prompt(self, links: list[LinkRecord]) -> str:
        """Substitute the link list into the prompt template."""
        return self._prompt_template.format(elements=_format_links(links))

    # ----------------------------------------------------------------
    # Response parsing.
    # ----------------------------------------------------------------

    def _parse_response(
        self,
        raw: dict[str, Any] | list[Any],
        links: list[LinkRecord],
    ) -> list[SemanticFinding]:
        """Turn the model's JSON into SemanticFinding rows.

        Defensive against:
          * Wrong outer shape (model returned a list, or string, or
            an object with a different key name).
          * Index out of range (model hallucinated an index).
          * Missing required fields on individual violation entries.
          * Non-string field values where strings expected.

        For each defect we log + skip the offending row rather than
        raising — the goal is to surface as many real findings as we
        can without one bad row killing the page's output.
        """
        if not isinstance(raw, dict):
            log.warning(
                "sc_2_4_4.bad_response_shape",
                got=type(raw).__name__,
            )
            return []
        violations = raw.get("violations")
        if not isinstance(violations, list):
            log.warning(
                "sc_2_4_4.missing_violations_array",
                payload_keys=list(raw.keys()),
            )
            return []

        out: list[SemanticFinding] = []
        seen_indices: set[int] = set()
        for entry in violations:
            if not isinstance(entry, dict):
                continue
            idx_raw = entry.get("index")
            try:
                idx = int(idx_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                log.warning("sc_2_4_4.bad_index", entry=entry)
                continue
            if idx < 0 or idx >= len(links):
                log.warning(
                    "sc_2_4_4.index_out_of_range",
                    index=idx,
                    link_count=len(links),
                )
                continue
            if idx in seen_indices:
                # Same link flagged twice — keep the first, drop dupes
                # so the bulk-status UI doesn't show duplicates.
                continue
            seen_indices.add(idx)

            link = links[idx]
            reason = _str_or_default(entry.get("reason"), "")
            recommendation = _str_or_default(entry.get("recommendation"), "")
            confidence = _normalize_confidence(entry.get("confidence"))

            # Confidence floor. Link purpose is a judgment call where false
            # positives ("could be more specific") erode trust fast, so a
            # low-confidence flag is dropped rather than surfaced. The prompt
            # already instructs the model to omit these; this enforces it even
            # when the model includes one anyway.
            if confidence == "low":
                log.debug(
                    "sc_2_4_4.dropped_low_confidence",
                    selector=link.selector,
                    reason=reason[:120],
                )
                continue

            # We pack "reason" into help (one-line) and "reason +
            # recommendation" into failure_summary (longer). The UI
            # shows help in the card header and failure_summary in the
            # expanded card.
            failure_summary = reason
            if recommendation:
                failure_summary = f"{reason} Suggested fix: {recommendation}"

            target_hash = _hash_target(
                criterion_sc=self.criterion_sc,
                selector=link.selector,
                snippet=link.snippet,
            )
            # Map model confidence to a coarse impact. A low-confidence
            # finding is "moderate" rather than "serious" — keeps the
            # priority scoring honest about probabilistic detection.
            impact = {"high": "serious", "medium": "moderate", "low": "minor"}.get(
                confidence, "moderate"
            )

            out.append(
                SemanticFinding(
                    criterion_sc=self.criterion_sc,
                    wcag_level="A",
                    impact=impact,
                    help=reason or "Link purpose is unclear from text and context.",
                    target_selector=link.selector,
                    failure_summary=failure_summary,
                    html_snippet=link.snippet,
                    target_hash=target_hash,
                    help_url="https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html",
                    wcag_scs="2.4.4",
                )
            )
        return out


# --------------------------------------------------------------------
# Prompt-side serialization helpers.
# --------------------------------------------------------------------


def _format_links(links: list[LinkRecord]) -> str:
    """Render the LINKS section of the prompt as readable text.

    JSON would be cleaner for the model to parse, but several open
    models follow numbered-list instructions more reliably than they
    follow inline-JSON instructions. We render a hybrid: numbered
    blocks of human-readable fields the model can scan, with the
    index as the only thing it needs to copy back.
    """
    lines: list[str] = []
    for i, link in enumerate(links):
        lines.append(f"---- LINK {i} ----")
        lines.append(f"  accessible_name: {link.accessible_name!r}")
        lines.append(f"  accessible_name_source: {link.accessible_name_source}")
        lines.append(f"  href: {link.href!r}")
        if link.aria_label and link.aria_label != link.accessible_name:
            lines.append(f"  aria_label: {link.aria_label!r}")
        if link.title and link.title != link.accessible_name:
            lines.append(f"  title: {link.title!r}")
        if link.ancestors:
            lines.append("  ancestors (innermost first):")
            for j, ancestor in enumerate(link.ancestors):
                lines.append(f"    [{j}] {ancestor!r}")
        else:
            lines.append("  ancestors: (none)")
    return "\n".join(lines)


# --------------------------------------------------------------------
# Misc.
# --------------------------------------------------------------------


def _str_or_default(value: Any, default: str) -> str:
    if isinstance(value, str):
        return value.strip()[:500]
    return default


def _normalize_confidence(value: Any) -> str:
    """Coerce free-form confidence labels to the {high, medium, low} set."""
    if not isinstance(value, str):
        return "medium"
    lowered = value.strip().lower()
    if lowered in ("high", "medium", "low"):
        return lowered
    return "medium"


def _hash_target(*, criterion_sc: str, selector: str, snippet: str) -> str:
    """Stable dedupe key. The DB uniqueness constraint pivots on this."""
    h = hashlib.sha256()
    h.update(criterion_sc.encode("utf-8"))
    h.update(b"\x00")
    h.update(selector.encode("utf-8"))
    h.update(b"\x00")
    h.update(snippet.encode("utf-8"))
    return h.hexdigest()


__all__ = [
    "MAX_LINKS_PER_CALL",
    "PROMPT_NAME",
    "LinkPurposeInContextAnalyzer",
]
