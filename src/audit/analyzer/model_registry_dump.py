"""``python -m audit.analyzer.model_registry_dump`` — print the model matrix.

A tiny CLI wrapper around :mod:`audit.analyzer.model_registry`. Useful
when an operator runs ``make list-analyzer-models`` and wants to see
which local Ollama model each criterion will use without grepping the
YAML.

Kept separate from ``model_registry.py`` so importing the registry
doesn't pull in ``rich`` or any other reporting deps.
"""

from __future__ import annotations

import sys

from audit.analyzer import model_registry


def main() -> int:
    data = model_registry._load()
    if not data:
        print("(no analyzer_models.yaml present, or YAML failed to parse)", file=sys.stderr)
        return 1

    defaults = data.get("defaults") or {}
    print("== Defaults (used when a criterion has no override) ==")
    for kind, block in defaults.items():
        if not isinstance(block, dict):
            continue
        primary = block.get("primary", "—")
        fast = block.get("fast", "—")
        print(f"  {kind:10s}  primary={primary:<32s}  fast={fast}")
    print()

    criteria = data.get("criteria") or {}
    if criteria:
        print("== Per-criterion overrides ==")
        print(f"  {'SC':<8s}{'Kind':<12s}{'Primary':<32s}{'Title'}")
        print(f"  {'-' * 8:<8s}{'-' * 12:<12s}{'-' * 32:<32s}{'-' * 40}")
        for sc, entry in criteria.items():
            if not isinstance(entry, dict):
                continue
            kind = entry.get("kind", "—")
            primary = entry.get("primary", "—")
            title = entry.get("title", "")
            print(f"  {sc:<8s}{kind:<12s}{primary:<32s}{title}")
        print()

    print("== Fetch tiers ==")
    for tier in ("required", "recommended", "optional"):
        tags = model_registry.fetch_set(tier)
        if tags:
            print(f"  {tier:<12s} {', '.join(tags)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
