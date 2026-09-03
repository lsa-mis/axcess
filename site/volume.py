#!/usr/bin/env python3
"""Export aggregate "coverage by volume" figures from the local scan database.

Reads ``data/audit.db`` and writes ``site/data/volume.json`` containing only
totals: occurrences per WCAG criterion, per check, per impact, and per
coverage method across completed scans. No URLs, page titles, selectors, or
snippets leave the database, so the snapshot is safe to publish.

Run from the repo root (the database is local and not in git)::

    uv run python site/volume.py

``site/build.py`` renders the snapshot if it exists and skips the section
otherwise, so a checkout without scan data still builds the site.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "audit.db"
OUT = ROOT / "site" / "data" / "volume.json"
sys.path.insert(0, str(ROOT / "src"))

# Plain-language names for rule ids that carry no single success criterion.
BEST_PRACTICE_NAMES = {
    "region": "Content outside landmark regions",
    "aria-hidden-focus": "Focusable content hidden from assistive technology",
    "dlitem": "Definition list items outside a list",
    "list": "List items outside a list",
    "page-has-heading-one": "Page without a level-one heading",
    "heading-order": "Heading levels that skip",
    "landmark-unique": "Duplicate landmarks",
}
PIPELINE_NAMES = {
    "axe": "Rule engine (axe-core)",
    "alfa": "Second opinion (Alfa)",
    "keyboard": "Keyboard check",
    "responsive": "Zoom and reflow check",
    "focus": "Focus check",
    "visual": "Visual and motion check",
    "image": "Image text check",
    "semantic": "Meaning check (local AI)",
}


def main() -> None:
    from audit import coverage_matrix

    if not DB.exists():
        raise SystemExit(f"no database at {DB}")
    names = {c.sc: c.name for c in coverage_matrix.load_matrix()}
    methods = {c.sc: c.method for c in coverage_matrix.load_matrix()}
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    completed = "select id from scans where status='completed'"
    scans, pages, hosts = con.execute(
        """
        select count(*) scans, coalesce(sum(p.n), 0) pages,
               count(distinct substr(seed_url, instr(seed_url, '//') + 2,
                     instr(substr(seed_url, instr(seed_url, '//') + 2), '/') - 1)) hosts
        from scans s join (select scan_id, count(*) n from pages group by scan_id) p on p.scan_id = s.id
        where s.status = 'completed'
        """
    ).fetchone()
    where = f"scan_id in ({completed}) and coalesce(engine_outcome, 'failed') = 'failed'"

    total = con.execute(f"select count(*) from page_a11y_findings where {where}").fetchone()[0]
    image_total = con.execute(
        f"select count(*) from findings where scan_id in ({completed})"
    ).fetchone()[0]

    by_sc = []
    for r in con.execute(
        f"""
        select coalesce(criterion_sc, wcag_sc, '') sc, count(*) n,
               count(distinct page_id) pages, count(distinct scan_id) scans
        from page_a11y_findings where {where} group by 1 order by n desc
        """
    ):
        sc = r["sc"]
        by_sc.append(
            {
                "sc": sc,
                "name": names.get(sc, "Best-practice rules (no single criterion)"),
                "method": methods.get(sc, "best-practice"),
                "occurrences": r["n"],
                "pages": r["pages"],
                "scans": r["scans"],
            }
        )

    by_rule = [
        {
            "rule": r["rule_id"],
            "pipeline": r["pipeline"],
            "sc": r["sc"],
            "name": BEST_PRACTICE_NAMES.get(r["rule_id"], names.get(r["sc"], r["rule_id"])),
            "occurrences": r["n"],
            "pages": r["pages"],
        }
        for r in con.execute(
            f"""
            select rule_id, pipeline, coalesce(criterion_sc, wcag_sc, '') sc, count(*) n,
                   count(distinct page_id) pages
            from page_a11y_findings where {where} group by rule_id, pipeline order by n desc limit 12
            """
        )
    ]

    by_pipeline = [
        {
            "pipeline": r["pipeline"],
            "name": PIPELINE_NAMES.get(r["pipeline"], r["pipeline"]),
            "occurrences": r["n"],
        }
        for r in con.execute(
            f"select pipeline, count(*) n from page_a11y_findings where {where} group by pipeline order by n desc"
        )
    ]
    if image_total:
        by_pipeline.append(
            {"pipeline": "image", "name": PIPELINE_NAMES["image"], "occurrences": image_total}
        )

    by_impact = [
        {"impact": r["impact"] or "unrated", "occurrences": r["n"]}
        for r in con.execute(
            f"select impact, count(*) n from page_a11y_findings where {where} group by impact order by n desc"
        )
    ]

    by_method: dict[str, int] = {}
    for row in by_sc:
        by_method[row["method"]] = by_method.get(row["method"], 0) + row["occurrences"]

    snapshot = {
        "generated": datetime.now(UTC).date().isoformat(),
        "scans": scans,
        "pages": pages,
        "hosts": hosts,
        "occurrences": total,
        "image_findings": image_total,
        "by_method": by_method,
        "by_criterion": by_sc,
        "by_rule": by_rule,
        "by_pipeline": by_pipeline,
        "by_impact": by_impact,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {scans} scans, {pages:,} pages, {total:,} occurrences")


if __name__ == "__main__":
    main()
