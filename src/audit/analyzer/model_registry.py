"""Per-criterion offline model selection.

Reads ``src/audit/rules/analyzer_models.yaml`` and resolves
"what Ollama model should I use for analyzer X" without hard-coding
model tags throughout the codebase. The YAML is the editable surface;
this module is the typed accessor.

Design notes:

* **YAML, not code.** Model picks change as the open-model ecosystem
  moves. We edit one file when a better Qwen / Llama / Gemma drops,
  not 12 call sites. The model_registry's contract is "give me a
  string I can hand to Ollama"; the editorial decision lives outside
  Python.
* **Graceful degradation.** Missing YAML, parse errors, unknown
  criterion keys — all return the configured fallback rather than
  raising. The analyzer pipeline then falls back to whatever the user
  passed via ``--vlm-model`` or has in ``config.py``. Never block a
  scan because the model registry is unhappy.
* **No I/O at import time.** YAML is read lazily and cached for the
  process lifetime. Tests can call ``reset_cache()`` to force a
  re-read.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Any, Literal

import yaml

Kind = Literal["vision", "text", "code", "reasoning"]
KINDS: tuple[Kind, ...] = ("vision", "text", "code", "reasoning")

_RULES_PACKAGE = "audit.rules"
_RULES_FILE = "analyzer_models.yaml"

_cache: dict[str, Any] | None = None


@dataclass(frozen=True)
class ModelPick:
    """Resolved model recommendation for one criterion."""

    primary: str  # tag suitable for `ollama pull` or `/api/generate`
    fast: str | None  # quicker / smaller fallback, if defined
    kind: Kind
    rationale: str | None = None


def get_pick(criterion_sc: str | None, *, kind: Kind | None = None) -> ModelPick:
    """Return the recommended model for a criterion (or for a kind).

    Resolution order, top to bottom:
      1. ``criteria[<sc>]`` exact match — picks override default.
      2. ``defaults[<kind>]`` — used when the criterion isn't pinned
         or no SC is given.
      3. Last-ditch hardcoded fallback so the call never raises.

    ``criterion_sc`` is the dotted form (e.g. ``"2.4.4"``).
    ``kind`` is required when ``criterion_sc`` is None.
    """
    data = _load()
    crit_map = data.get("criteria") or {}
    if criterion_sc and criterion_sc in crit_map:
        entry = crit_map[criterion_sc] or {}
        return ModelPick(
            primary=str(entry.get("primary") or _default_for(data, entry.get("kind") or kind)),
            fast=_str_or_none(entry.get("fast")),
            kind=_normalize_kind(entry.get("kind") or kind or "text"),
            rationale=_str_or_none(entry.get("rationale")),
        )
    # No per-criterion pin: pick from defaults by kind.
    resolved_kind = _normalize_kind(kind or "text")
    primary = _default_for(data, resolved_kind)
    fast = _default_for(data, resolved_kind, slot="fast")
    return ModelPick(
        primary=primary,
        fast=fast if fast != primary else None,
        kind=resolved_kind,
        rationale=None,
    )


def fetch_set(tier: str = "required") -> list[str]:
    """Return the list of model tags this project recommends pulling.

    Tiers: ``"required"`` (minimum to run any new analyzer),
    ``"recommended"`` (full feature set), ``"optional"`` (heavier
    models for borderline cases).
    """
    data = _load()
    block = data.get("fetch_set") or {}
    raw = block.get(tier) or []
    return [str(t) for t in raw]


def all_fetch_tags() -> list[str]:
    """Deduped union of required + recommended fetch tags.

    What ``make fetch-analyzer-models`` actually pulls.
    """
    seen: list[str] = []
    for tier in ("required", "recommended"):
        for tag in fetch_set(tier):
            if tag and tag not in seen:
                seen.append(tag)
    return seen


def reset_cache() -> None:
    """Clear the YAML cache. Tests use this between cases."""
    global _cache
    _cache = None


# --------------------------------------------------------------------
# Internals.
# --------------------------------------------------------------------


def _load() -> dict[str, Any]:
    """Read + cache the YAML, returning {} on any failure."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        text = (resources.files(_RULES_PACKAGE) / _RULES_FILE).read_text(encoding="utf-8")
        parsed = yaml.safe_load(text) or {}
        _cache = parsed if isinstance(parsed, dict) else {}
    except (FileNotFoundError, yaml.YAMLError):
        _cache = {}
    return _cache


def _default_for(data: dict[str, Any], kind: str | None, *, slot: str = "primary") -> str:
    """Pick from ``defaults[<kind>][<slot>]`` with a hard fallback."""
    defaults = data.get("defaults") or {}
    if isinstance(defaults, dict) and kind in defaults:
        block = defaults[kind] or {}
        if isinstance(block, dict) and block.get(slot):
            return str(block[slot])
    # Hard fallback — this is the "the YAML is broken or absent" case.
    # qwen2.5:7b is a reasonable safe default at the 7B parameter
    # band; if it's not installed, the analyzer fails loudly and the
    # user pulls it.
    return "qwen2.5:7b-instruct" if slot == "primary" else "llama3.2:3b-instruct"


def _normalize_kind(value: str | None) -> Kind:
    """Coerce free-form kind input to the typed set."""
    if value in KINDS:
        return value  # type: ignore[return-value]
    return "text"


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


__all__ = [
    "KINDS",
    "Kind",
    "ModelPick",
    "all_fetch_tags",
    "fetch_set",
    "get_pick",
    "reset_cache",
]
