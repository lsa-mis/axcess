"""SC 1.2.1 — Audio-only (Prerecorded): transcript presence analyzer.

Scoped to ``<audio>`` elements — the unambiguous "audio-only prerecorded"
case that requires a text transcript. ``<video>`` is intentionally left to a
human (a video with sound falls under 1.2.2/1.2.3/1.2.5, and the DOM can't
tell us whether a video is silent). The analyzer judges whether a transcript
or text alternative is reachable from the page; it can't read the audio, so
it reasons over nearby links + surrounding text.

Same shape as the other semantic analyzers: extract, one bounded prompt,
parse JSON to SemanticFinding rows, fail graceful.
"""

from __future__ import annotations

import hashlib
from importlib import resources
from typing import Any

from audit.analyzer.ollama_base import OllamaError, prompt_content_version
from audit.analyzer.semantic.base import AnalysisContext, SemanticFinding
from audit.analyzer.semantic.extractor import MediaRecord, extract_media
from audit.analyzer.semantic.ollama_text import OllamaTextProvider
from audit.logging import get_logger

log = get_logger(__name__)

_PROMPT_PACKAGE = "audit.analyzer.semantic.prompts"
PROMPT_NAME = "sc_1_2_1_audio_transcript.txt"

MAX_MEDIA_PER_CALL = 40

_HELP_URL = "https://www.w3.org/WAI/WCAG22/Understanding/audio-only-and-video-only-prerecorded.html"


def _load_prompt() -> str:
    return (resources.files(_PROMPT_PACKAGE) / PROMPT_NAME).read_text(encoding="utf-8")


class AudioTranscriptAnalyzer:
    """LLM-driven SC 1.2.1 analyzer (prerecorded audio transcript presence)."""

    criterion_sc = "1.2.1"

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
        # Only audio elements — see module docstring for why video is excluded.
        audio = [m for m in extract_media(ctx.body) if m.kind == "audio"]
        if not audio:
            return []

        chunk = audio[:MAX_MEDIA_PER_CALL]
        if len(audio) > MAX_MEDIA_PER_CALL:
            log.info(
                "sc_1_2_1.audio_truncated",
                page_url=ctx.page_url,
                total=len(audio),
                kept=MAX_MEDIA_PER_CALL,
            )

        prompt = self._render_prompt(chunk)
        try:
            raw = await self._provider.generate_json(prompt, model=self._model)
        except OllamaError as exc:
            log.warning("sc_1_2_1.llm_failed", page_url=ctx.page_url, error=str(exc))
            return []

        return list(self._parse_response(raw, chunk))

    def _render_prompt(self, media: list[MediaRecord]) -> str:
        return self._prompt_template.format(elements=_format_media(media))

    def _parse_response(
        self,
        raw: dict[str, Any] | list[Any],
        media: list[MediaRecord],
    ) -> list[SemanticFinding]:
        if not isinstance(raw, dict):
            log.warning("sc_1_2_1.bad_response_shape", got=type(raw).__name__)
            return []
        violations = raw.get("violations")
        if not isinstance(violations, list):
            log.warning("sc_1_2_1.missing_violations_array", payload_keys=list(raw.keys()))
            return []

        out: list[SemanticFinding] = []
        seen: set[int] = set()
        for entry in violations:
            if not isinstance(entry, dict):
                continue
            try:
                idx = int(entry.get("index"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                log.warning("sc_1_2_1.bad_index", entry=entry)
                continue
            if idx < 0 or idx >= len(media):
                log.warning("sc_1_2_1.index_out_of_range", index=idx, count=len(media))
                continue
            if idx in seen:
                continue
            seen.add(idx)

            m = media[idx]
            reason = _str_or_default(entry.get("reason"), "")
            recommendation = _str_or_default(entry.get("recommendation"), "")
            confidence = _normalize_confidence(entry.get("confidence"))

            failure_summary = reason
            if recommendation:
                failure_summary = f"{reason} Suggested fix: {recommendation}"

            impact = {"high": "serious", "medium": "moderate", "low": "minor"}.get(
                confidence, "moderate"
            )
            out.append(
                SemanticFinding(
                    criterion_sc=self.criterion_sc,
                    wcag_level="A",
                    impact=impact,
                    help=reason or "Audio has no reachable text transcript.",
                    target_selector=m.selector,
                    failure_summary=failure_summary,
                    html_snippet=m.snippet,
                    target_hash=_hash_target(
                        criterion_sc=self.criterion_sc,
                        selector=m.selector,
                        snippet=m.snippet,
                    ),
                    help_url=_HELP_URL,
                    wcag_scs="1.2.1",
                )
            )
        return out


def _format_media(media: list[MediaRecord]) -> str:
    """Render the AUDIO section of the prompt as a readable numbered list."""
    lines: list[str] = []
    for i, m in enumerate(media):
        lines.append(f"---- AUDIO {i} ----")
        lines.append(f"  src: {m.src!r}")
        lines.append(f"  track_kinds: {list(m.track_kinds)}")
        if m.nearby_links:
            lines.append(f"  nearby_links: {list(m.nearby_links)}")
        else:
            lines.append("  nearby_links: (none)")
        if m.nearby_text:
            lines.append(f"  nearby_text: {m.nearby_text!r}")
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


__all__ = ["MAX_MEDIA_PER_CALL", "PROMPT_NAME", "AudioTranscriptAnalyzer"]
