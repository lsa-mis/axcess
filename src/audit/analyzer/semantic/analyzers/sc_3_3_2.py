"""SC 3.3.2, Labels or Instructions analyzer.

Judges whether each form control's label/instructions are sufficient for a
first-time user to know what to enter, the sufficiency call no rule engine
can make (axe only checks that a programmatic label *exists*).

Mirrors the SC 2.4.4 / 2.4.6 shape: extract the focused slice, one bounded
prompt to a local Ollama text model, parse JSON into SemanticFinding rows,
fail graceful on any model/IO problem.
"""

from __future__ import annotations

import hashlib
from importlib import resources
from typing import Any

from audit.analyzer.ollama_base import OllamaError, prompt_content_version
from audit.analyzer.semantic.base import AnalysisContext, SemanticFinding
from audit.analyzer.semantic.extractor import FormFieldRecord, extract_form_fields
from audit.analyzer.semantic.ollama_text import OllamaTextProvider
from audit.logging import get_logger

log = get_logger(__name__)

_PROMPT_PACKAGE = "audit.analyzer.semantic.prompts"
PROMPT_NAME = "sc_3_3_2_labels_or_instructions.txt"

MAX_FIELDS_PER_CALL = 50

_HELP_URL = "https://www.w3.org/WAI/WCAG22/Understanding/labels-or-instructions.html"


def _load_prompt() -> str:
    return (resources.files(_PROMPT_PACKAGE) / PROMPT_NAME).read_text(encoding="utf-8")


class LabelsOrInstructionsAnalyzer:
    """LLM-driven SC 3.3.2 analyzer (form-control label/instruction sufficiency)."""

    criterion_sc = "3.3.2"

    def __init__(
        self,
        provider: OllamaTextProvider,
        *,
        model: str | None = None,
        prompt_template: str | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._prompt_template = prompt_template or _load_prompt()
        self.prompt_version = prompt_content_version(self._prompt_template)

    async def analyze(self, ctx: AnalysisContext) -> list[SemanticFinding]:
        fields = extract_form_fields(ctx.body)
        if not fields:
            return []

        chunk = fields[:MAX_FIELDS_PER_CALL]
        if len(fields) > MAX_FIELDS_PER_CALL:
            log.info(
                "sc_3_3_2.fields_truncated",
                page_url=ctx.page_url,
                total=len(fields),
                kept=MAX_FIELDS_PER_CALL,
            )

        prompt = self._render_prompt(chunk)
        try:
            raw = await self._provider.generate_json(prompt, model=self._model)
        except OllamaError as exc:
            log.warning("sc_3_3_2.llm_failed", page_url=ctx.page_url, error=str(exc))
            return []

        return list(self._parse_response(raw, chunk))

    def _render_prompt(self, fields: list[FormFieldRecord]) -> str:
        return self._prompt_template.format(elements=_format_fields(fields))

    def _parse_response(
        self,
        raw: dict[str, Any] | list[Any],
        fields: list[FormFieldRecord],
    ) -> list[SemanticFinding]:
        if not isinstance(raw, dict):
            log.warning("sc_3_3_2.bad_response_shape", got=type(raw).__name__)
            return []
        violations = raw.get("violations")
        if not isinstance(violations, list):
            log.warning("sc_3_3_2.missing_violations_array", payload_keys=list(raw.keys()))
            return []

        out: list[SemanticFinding] = []
        seen: set[int] = set()
        for entry in violations:
            if not isinstance(entry, dict):
                continue
            try:
                idx = int(entry.get("index"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                log.warning("sc_3_3_2.bad_index", entry=entry)
                continue
            if idx < 0 or idx >= len(fields):
                log.warning("sc_3_3_2.index_out_of_range", index=idx, count=len(fields))
                continue
            if idx in seen:
                continue
            seen.add(idx)

            field = fields[idx]
            reason = _str_or_default(entry.get("reason"), "")
            recommendation = _str_or_default(entry.get("recommendation"), "")
            confidence = _normalize_confidence(entry.get("confidence"))

            failure_summary = reason
            if recommendation:
                failure_summary = f"{reason} Suggested label/instruction: {recommendation}"

            impact = {"high": "serious", "medium": "moderate", "low": "minor"}.get(
                confidence, "moderate"
            )
            out.append(
                SemanticFinding(
                    criterion_sc=self.criterion_sc,
                    wcag_level="A",
                    impact=impact,
                    help=reason or "Form control lacks a clear label or instruction.",
                    target_selector=field.selector,
                    failure_summary=failure_summary,
                    html_snippet=field.snippet,
                    target_hash=_hash_target(
                        criterion_sc=self.criterion_sc,
                        selector=field.selector,
                        snippet=field.snippet,
                    ),
                    help_url=_HELP_URL,
                    wcag_scs="3.3.2",
                )
            )
        return out


def _format_fields(fields: list[FormFieldRecord]) -> str:
    """Render the FIELDS section of the prompt as a readable numbered list."""
    lines: list[str] = []
    for i, f in enumerate(fields):
        lines.append(f"---- FIELD {i} ----")
        lines.append(f"  control: {f.control}")
        lines.append(f"  label: {f.label!r}")
        lines.append(f"  label_source: {f.label_source}")
        if f.placeholder:
            lines.append(f"  placeholder: {f.placeholder!r}")
        if f.described_by:
            lines.append(f"  instruction (aria-describedby): {f.described_by!r}")
        lines.append(f"  required: {f.required}")
    return "\n".join(lines)


def _str_or_default(value: Any, default: str) -> str:
    if isinstance(value, str):
        return value.strip()[:500]
    return default


def _normalize_confidence(value: Any) -> str:
    if not isinstance(value, str):
        return "medium"
    lowered = value.strip().lower()
    return lowered if lowered in ("high", "medium", "low") else "medium"


def _hash_target(*, criterion_sc: str, selector: str, snippet: str) -> str:
    h = hashlib.sha256()
    h.update(criterion_sc.encode("utf-8"))
    h.update(b"\x00")
    h.update(selector.encode("utf-8"))
    h.update(b"\x00")
    h.update(snippet.encode("utf-8"))
    return h.hexdigest()


__all__ = ["MAX_FIELDS_PER_CALL", "PROMPT_NAME", "LabelsOrInstructionsAnalyzer"]
