"""Shared read-time Alfa diagnostics; stored scan evidence remains immutable."""

from __future__ import annotations

import json
import re
from typing import Any

STRUCTURED_TARGET_LABEL = "Element recorded in Alfa's structured target evidence"
_CONTRAST_CHECK = (
    "On the linked page, identify the text and measure its contrast against the actual "
    "background, including the lowest-contrast part of a gradient or image. Check normal "
    "text against 4.5:1 and large text against 3:1 for WCAG AA; record your manual result."
)
# A JSON string token must close completely. Never infer the unfinished tail.
_MESSAGE = re.compile(r'"message"\s*:\s*("(?:[^"\\\x00-\x1f]|\\["\\/bfnrt]|\\u[0-9a-fA-F]{4})*")')


def _text(value: Any, maximum: int = 800) -> str:
    return " ".join(str(value or "").replace("\x00", "").split())[:maximum]


def diagnostic_messages(value: Any) -> list[str]:
    """Extract only diagnostic fields, never instructions from target content."""
    messages: list[str] = []

    def visit(item: Any, depth: int = 0) -> None:
        if depth > 8 or len(messages) >= 8:
            return
        if isinstance(item, list):
            for child in item[:12]:
                visit(child, depth + 1)
        elif isinstance(item, dict):
            message = _text(item.get("message"))
            if message and message not in messages:
                messages.append(message)
            for key in ("diagnostic", "causes", "errors", "error", "expectations"):
                visit(item.get(key), depth + 1)

    if isinstance(value, dict) and isinstance(value.get("diagnostics"), list):
        messages = list(
            dict.fromkeys(_text(v) for v in value["diagnostics"][:8] if isinstance(v, str))
        )
    visit(value)
    return messages[:8]


def parse_evidence(raw: Any) -> tuple[dict[str, Any], str]:
    """Read valid payloads or recover complete diagnostics in the legacy prefix.

    Recovery is deliberately restricted to the old runner's diagnostic-first
    envelope ending in its truncation ellipsis; arbitrary malformed JSON is
    unavailable evidence. Stop before expectations or target data.
    """
    source = str(raw or "")
    try:
        value = json.loads(source)
    except (TypeError, ValueError):
        if source.startswith('{"diagnostic":') and source.endswith("…"):
            prefix = re.split(
                r',\s*"(?:expectations|mode|outcome|rule|target|element|children|attributes)"\s*:',
                source,
                maxsplit=1,
            )[0]
            messages = [_text(json.loads(match.group(1))) for match in _MESSAGE.finditer(prefix)]
            if messages:
                return {
                    "diagnostics": list(dict.fromkeys(messages))[:8],
                    "truncated": True,
                    "recovered_from_legacy_truncation": True,
                }, "recovered"
        return {}, "unavailable"
    if not isinstance(value, dict):
        return {}, "unavailable"
    status = (
        "recovered"
        if value.get("recovered_from_legacy_truncation")
        else "truncated"
        if value.get("truncated")
        else "complete"
    )
    return value, status


def bounded_evidence_json(raw: Any, maximum: int = 12000) -> str:
    """Validate runner evidence and compact structures, retaining valid JSON."""
    if maximum < 20:
        raise ValueError("Evidence bound must be at least 20 bytes")
    value, status = parse_evidence(raw)
    if status == "unavailable":
        value = {"truncated": True, "evidence_unavailable": True}
    if isinstance(raw, str) and status == "complete" and len(raw.encode("utf-8")) <= maximum:
        return raw
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) <= maximum:
        return serialized
    compact = {
        "diagnostics": diagnostic_messages(value),
        "target_identity": _text(value.get("target_identity"), 128),
        "truncated": True,
    }
    while True:
        serialized = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
        if len(serialized.encode("utf-8")) <= maximum:
            return serialized
        messages = compact["diagnostics"]
        if isinstance(messages, list) and messages:
            messages.pop()
        else:
            return '{"truncated":true}'


def humanize_target(raw: Any) -> str:
    """Readable target label, keeping raw locators separately for reproduction."""
    target = _text(raw, 4000) if not isinstance(raw, (dict, list)) else raw
    if isinstance(target, str):
        try:
            target = json.loads(target)
        except (TypeError, ValueError):
            if target.lstrip().startswith(("{", "[")):
                return STRUCTURED_TARGET_LABEL
            return target[:240] or "Page-level result"
    if isinstance(target, list):
        return "; ".join(humanize_target(item) for item in target[:3])[:500]
    if not isinstance(target, dict):
        return _text(target, 240) or "Page-level result"
    kind = target.get("type")
    if kind == "document":
        return "Document root"
    if kind == "text":
        text = _text(target.get("data"), 120)
        raw_path = target.get("path")
        path = _text(raw_path, 240) if isinstance(raw_path, str) else ""
        return f"Text “{text}”" + (f" at {path}" if path else "")
    if kind == "attribute":
        return f'[{_text(target.get("name"), 40)}="{_text(target.get("value"), 120)}"]'
    if kind == "element":
        selectors = []
        attributes = target.get("attributes") or []
        for attribute in (attributes if isinstance(attributes, list) else [])[:12]:
            if not isinstance(attribute, dict) or attribute.get("name") not in {
                "id",
                "class",
                "name",
                "role",
                "type",
                "href",
                "src",
            }:
                continue
            selectors.append(f'[{attribute["name"]}="{_text(attribute.get("value"), 100)}"]')
            if len(selectors) == 2:
                break
        return (_text(target.get("name"), 80) + "".join(selectors))[:240]
    return STRUCTURED_TARGET_LABEL


def evidence_notice(status: str | None) -> str:
    """An explicit completeness label for UIs and text-only exports."""
    if status == "recovered":
        return "Incomplete evidence: only complete legacy diagnostics were recovered."
    if status == "truncated":
        return "Incomplete evidence: stored details were shortened."
    if status == "unavailable":
        return "Stored evidence is unavailable."
    return ""


def bounded_summary(summary: str, status: str | None, maximum: int = 2400) -> str:
    """Reserve space for the completeness notice even for long diagnostics."""
    notice = evidence_notice(status)
    suffix = f" [{notice}]" if notice else ""
    if suffix and summary.endswith(suffix):
        summary = summary.removesuffix(suffix)
    remaining = max(0, maximum - len(suffix))
    return summary[:remaining].rstrip() + suffix


def normalize_finding(finding: dict[str, Any]) -> dict[str, Any]:
    """Extend an Alfa read model, preserving valid raw payloads for exports."""
    if finding.get("pipeline") != "alfa":
        return finding
    result = dict(finding)
    evidence, status = parse_evidence(finding.get("engine_evidence_json"))
    diagnostics = diagnostic_messages(evidence)
    summary = "; ".join(diagnostics) or _text(finding.get("failure_summary"), 2000)
    background_limitation = "background" in summary.lower() and any(
        word in summary.lower() for word in ("siz", "unsupported", "support")
    )
    if background_limitation and finding.get("engine_outcome") == "cant_tell":
        summary = (
            "Alfa could not calculate text contrast because of unsupported background sizing. "
            f"{summary}"
        )
    result["failure_summary"] = bounded_summary(summary, status)
    result["target_display"] = humanize_target(finding.get("target_selector"))
    result["engine_evidence_status"] = status
    result["manual_review_hint"] = _CONTRAST_CHECK if background_limitation else None
    if status == "recovered":
        result["engine_evidence_json"] = json.dumps(
            evidence, ensure_ascii=False, separators=(",", ":")
        )
    return result
