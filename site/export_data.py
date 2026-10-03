#!/usr/bin/env python3
"""Export the product data the public site renders (``site/src/data/*.json``).

Every coverage number and criterion card on the site comes from the same
source of truth the product uses (``src/audit/rules/wcag_coverage.yaml`` via
``audit.coverage_matrix``, plus the roadmap in ``audit.web.coverage_status``),
so the site can never claim coverage the code does not have. The Astro build
imports these files; it never keeps its own copy of the numbers.

Run from the repo root before ``npm run build`` (``make site`` does both)::

    uv run python site/export_data.py

The glossary is not exported: ``docs/glossary.md`` is rendered as a docs page
directly (``site/src/content.config.ts``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "src" / "data"
sys.path.insert(0, str(ROOT / "src"))


def coverage() -> dict[str, object]:
    from audit import coverage_matrix
    from audit.web import coverage_status

    crit = coverage_matrix.load_matrix()
    summ = coverage_matrix.summary()
    return {
        "summary": {
            "total": summ.total,
            "covered": summ.covered,
            "manualOnly": summ.manual_only,
            "byMethod": summ.by_method,
            "byLevel": summ.by_level,
        },
        "criteria": [
            {
                "sc": c.sc,
                "name": c.name,
                "level": c.level,
                "method": c.method,
                "pipelines": list(c.pipelines),
                "confidence": c.confidence,
                "automatedCheck": c.automated_check,
                "manualCheck": c.manual_check,
            }
            for c in crit
        ],
        "roadmap": [
            {"wcag": r.wcag, "issue": r.issue, "what": r.what, "status": r.status}
            for r in coverage_status.ROADMAP
        ],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "coverage.json"
    path.write_text(json.dumps(coverage(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
