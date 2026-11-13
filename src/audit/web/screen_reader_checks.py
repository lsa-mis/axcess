"""Step-by-step screen reader checks shared by several issue types.

The steps live in ``rules/screen_reader_checks.yaml``; a guidance card in
``rules/audit_report.yaml`` names one with ``screen_reader_check: <key>``.
The issue guidance shows them as one numbered list per computer, and the
exports print the same steps as text, so every surface says the same thing.

A key the reader presses is written ``{Command}`` in the YAML. The browser
shows it as a key; :func:`plain_text` drops the braces for exports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

_RULES_PACKAGE = "audit.rules"
_FILE = "screen_reader_checks.yaml"
_KEY = re.compile(r"\{([^{}]+)\}")


@dataclass(frozen=True)
class ScreenReaderPlatform:
    """The steps for one computer, such as a Mac with VoiceOver."""

    id: str
    name: str
    intro: str | None
    link_text: str | None
    link_url: str | None
    steps: list[str]


@dataclass(frozen=True)
class ScreenReaderCheck:
    """One kind of check (for example, landmarks) for each computer."""

    id: str
    title: str
    platforms: list[ScreenReaderPlatform]


def plain_text(text: str) -> str:
    """``{Command} + {F5}`` -> ``Command + F5``, for exports."""
    return _KEY.sub(r"\1", text)


def check_for(key: Any) -> ScreenReaderCheck | None:
    """The named check, or ``None`` when the card names none or an unknown one."""
    if not isinstance(key, str) or not key:
        return None
    return _load().get(key)


def as_text_lines(check: ScreenReaderCheck) -> list[str]:
    """The whole check as plain lines: a heading per computer, then its steps."""
    lines: list[str] = []
    for platform in check.platforms:
        lines.append(f"{platform.name}:")
        if platform.intro:
            lines.append(plain_text(platform.intro))
        if platform.link_url:
            lines.append(f"{platform.link_text or platform.link_url}: {platform.link_url}")
        lines.extend(f"{i}. {plain_text(step)}" for i, step in enumerate(platform.steps, 1))
    return lines


@lru_cache(maxsize=1)
def _load() -> dict[str, ScreenReaderCheck]:
    """Read the YAML once. Returns ``{}`` when it is missing or malformed,
    so the guidance still shows the card's own words."""
    try:
        text = (resources.files(_RULES_PACKAGE) / _FILE).read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
    except (FileNotFoundError, yaml.YAMLError):
        return {}
    if not isinstance(data, dict):
        return {}
    checks: dict[str, ScreenReaderCheck] = {}
    for key, block in data.items():
        if not isinstance(block, dict):
            continue
        platforms = [
            ScreenReaderPlatform(
                id=str(p["id"]),
                name=str(p["name"]),
                intro=p.get("intro"),
                link_text=p.get("link_text"),
                link_url=p.get("link_url"),
                steps=[str(s) for s in p.get("steps") or []],
            )
            for p in block.get("platforms") or []
            if isinstance(p, dict) and p.get("id") and p.get("name") and p.get("steps")
        ]
        if platforms:
            checks[str(key)] = ScreenReaderCheck(
                id=str(key), title=str(block.get("title") or ""), platforms=platforms
            )
    return checks
