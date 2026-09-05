"""Read-side queries for the per-scan WCAG / axe view.

Kept as a separate module so the same shaping powers both the Jinja
template (`/scans/{id}/a11y`) and the SPA JSON endpoint
(`/api/scans/{id}/a11y`). Both surfaces need the same aggregate views;
duplicating the SQL between them would invite drift.

Three aggregation axes the UI cares about:

* **By WCAG SC**, "you're failing SC 1.4.3 on 47 pages." This is what
  the accessibility lead reports to stakeholders.
* **By rule**, "color-contrast accounts for 47 of those 50 failures
  on SC 1.4.3." This is what the developer fixing the bug needs.
* **By impact**, axe's own severity scale, useful for ordering effort.

The functions here all take a connection and a scan id, return plain
dicts, and never raise on an empty scan, the empty-state case is part
of the contract.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from audit.analyzer.alfa_evidence import normalize_finding

# Impact ordering, for sorting "worst first", axe doesn't always set
# impact (best-practice rules and a few WCAG rules leave it None), so
# None ranks last.
_IMPACT_RANK = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3, None: 4}


def coverage(conn: sqlite3.Connection, scan_id: int) -> dict[str, int]:
    """Top-line counts for the per-scan header card."""
    row = conn.execute(
        "SELECT axe_pages_scanned, axe_violations_total, alfa_pages_scanned, "
        "alfa_failed_total, alfa_cant_tell_total FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    if row is None:
        return {
            "axe_pages_scanned": 0,
            "axe_violations_total": 0,
            "alfa_pages_scanned": 0,
            "alfa_failed_total": 0,
            "alfa_cant_tell_total": 0,
            "pages_total": 0,
        }
    pages_total = int(
        conn.execute("SELECT COUNT(*) AS n FROM pages WHERE scan_id = ?", (scan_id,)).fetchone()[
            "n"
        ]
    )
    return {
        "axe_pages_scanned": int(row["axe_pages_scanned"] or 0),
        "axe_violations_total": int(row["axe_violations_total"] or 0),
        "alfa_pages_scanned": int(row["alfa_pages_scanned"] or 0),
        "alfa_failed_total": int(row["alfa_failed_total"] or 0),
        "alfa_cant_tell_total": int(row["alfa_cant_tell_total"] or 0),
        "pages_total": pages_total,
    }


def by_level(conn: sqlite3.Connection, scan_id: int) -> dict[str, int]:
    """Violation counts grouped by WCAG conformance level.

    Best-practice findings (axe-coined rules with no SC mapping) land
    under the ``"best_practice"`` key, they're worth surfacing but
    they're not a WCAG fail in the strict sense.
    """
    out = {"A": 0, "AA": 0, "AAA": 0, "best_practice": 0}
    rows = conn.execute(
        """
        SELECT wcag_level, COUNT(*) AS n
          FROM page_a11y_findings
         WHERE scan_id = ?
         GROUP BY wcag_level
        """,
        (scan_id,),
    ).fetchall()
    for row in rows:
        level = row["wcag_level"]
        key = level if level in {"A", "AA", "AAA"} else "best_practice"
        out[key] = out.get(key, 0) + int(row["n"])
    return out


def by_impact(conn: sqlite3.Connection, scan_id: int) -> dict[str, int]:
    """Violation counts grouped by axe's own impact scale."""
    out = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
    rows = conn.execute(
        """
        SELECT impact, COUNT(*) AS n
          FROM page_a11y_findings
         WHERE scan_id = ?
         GROUP BY impact
        """,
        (scan_id,),
    ).fetchall()
    for row in rows:
        key = row["impact"] or "unspecified"
        out[key] = out.get(key, 0) + int(row["n"])
    return out


def by_sc(conn: sqlite3.Connection, scan_id: int) -> list[dict[str, Any]]:
    """One row per WCAG SC, with per-rule breakdown nested inside.

    The shape:

        [
            {
                "wcag_sc": "1.4.3",
                "wcag_level": "AA",
                "violation_count": 47,
                "page_count": 12,
                "worst_impact": "serious",
                "rules": [
                    {"rule_id": "color-contrast", "impact": "serious",
                     "help": "...", "help_url": "...",
                     "violation_count": 47, "page_count": 12},
                    ...
                ],
            },
            ...
        ]

    Findings tagged ``best_practice`` (no SC) collapse under a single
    entry with ``wcag_sc = None`` so the UI can render them in a
    distinct section.
    """
    rule_rows = conn.execute(
        """
        SELECT pipeline, wcag_sc, wcag_level, rule_id, impact, help, help_url,
               COUNT(*) AS violation_count,
               COUNT(DISTINCT page_id) AS page_count
          FROM page_a11y_findings
         WHERE scan_id = ?
         GROUP BY pipeline, wcag_sc, wcag_level, rule_id, impact, help, help_url
        """,
        (scan_id,),
    ).fetchall()

    # Group rule rows under their SC. Sort SCs by their numeric tuple so
    # 1.4.11 follows 1.4.3 instead of preceding it (string sort would
    # mis-order them as 1.4.10 < 1.4.11 < 1.4.3).
    by_sc_dict: dict[str | None, dict[str, Any]] = {}
    for r in rule_rows:
        sc = r["wcag_sc"]
        entry = by_sc_dict.setdefault(
            sc,
            {
                "wcag_sc": sc,
                "wcag_level": r["wcag_level"],
                "violation_count": 0,
                "page_count_set": set(),
                "worst_impact_rank": _IMPACT_RANK[None],
                "worst_impact": None,
                "rules": [],
            },
        )
        entry["violation_count"] += int(r["violation_count"])
        # We can't sum page_count across rules, same page may fail two
        # rules under the same SC. Re-query for the SC's unique page count.
        impact = r["impact"]
        rank = _IMPACT_RANK.get(impact, _IMPACT_RANK[None])
        if rank < entry["worst_impact_rank"]:
            entry["worst_impact_rank"] = rank
            entry["worst_impact"] = impact
        entry["rules"].append(
            {
                "rule_id": r["rule_id"],
                "pipeline": r["pipeline"],
                "impact": impact,
                "help": r["help"],
                "help_url": r["help_url"],
                "violation_count": int(r["violation_count"]),
                "page_count": int(r["page_count"]),
            }
        )

    # Now fill in each SC's true unique page count (re-query is cheap and
    # avoids the wrong-sum trap above).
    for sc, entry in by_sc_dict.items():
        page_count_row = conn.execute(
            """
            SELECT COUNT(DISTINCT page_id) AS n
              FROM page_a11y_findings
             WHERE scan_id = ? AND wcag_sc IS ?
            """,
            (scan_id, sc),
        ).fetchone()
        entry["page_count"] = int(page_count_row["n"]) if page_count_row else 0
        # Sort rules within the SC: worst impact first, then page count.
        entry["rules"].sort(key=lambda x: (_IMPACT_RANK.get(x["impact"], 4), -x["page_count"]))
        entry.pop("page_count_set", None)
        entry.pop("worst_impact_rank", None)

    return sorted(by_sc_dict.values(), key=lambda x: _sc_sort_key(x["wcag_sc"]))


def _sc_sort_key(sc: str | None) -> tuple[int, int, int, int]:
    """Numeric sort for SC strings; non-SC rules sort last."""
    if sc is None:
        return (99, 99, 99, 99)
    parts = sc.split(".")
    if len(parts) != 3:
        return (99, 99, 99, 0)
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]), 0)
    except ValueError:
        return (99, 99, 99, 0)


_STATUSES: frozenset[str] = frozenset(
    {
        "new",
        "reviewing",
        "in_progress",
        "remediated",
        "accepted_risk",
        "false_positive",
    }
)


def findings_for_sc(
    conn: sqlite3.Connection,
    scan_id: int,
    wcag_sc: str | None,
    *,
    status: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Drill-down list of individual violations for a single SC.

    Used by the detail view when the operator clicks into an SC heading.
    Joined to ``pages`` so each row carries the page URL.

    ``status`` filters by triage state, pass e.g. ``"new"`` to hide
    already-handled findings. ``None`` (the default) returns every
    status. An unrecognized status string is ignored rather than
    raising, so a stale URL with a bad ``status`` param still loads.
    """
    # Both `page_a11y_findings` and `pages` carry a `scan_id` column —
    # qualify the alias so the SQL doesn't go ambiguous after the JOIN.
    clauses: list[str] = ["a.scan_id = ?"]
    params: list[Any] = [scan_id]
    if wcag_sc is None:
        clauses.append("a.wcag_sc IS NULL")
    else:
        clauses.append("a.wcag_sc = ?")
        params.append(wcag_sc)
    if status is not None and status in _STATUSES:
        clauses.append("a.status = ?")
        params.append(status)
    where = " AND ".join(clauses)
    params.extend([limit, offset])
    # The f-string only interpolates `where`, which is itself built from
    # a fixed set of string literals defined above, never from caller
    # input. Caller-supplied values (`scan_id`, `wcag_sc`, `status`,
    # `limit`, `offset`) all flow through parameter binding.
    sql = f"""
        SELECT a.id, a.pipeline, a.engine_outcome, a.rule_id, a.impact, a.help, a.help_url,
               a.target_selector, a.failure_summary, a.html_snippet, a.engine_evidence_json,
               a.status, a.wcag_sc, a.wcag_level, a.revealed_by,
               p.id AS page_id, p.url_normalized AS page_url,
               p.title AS page_title
          FROM page_a11y_findings a
          JOIN pages p ON p.id = a.page_id
         WHERE {where}
         ORDER BY
            CASE a.impact
              WHEN 'critical' THEN 0
              WHEN 'serious' THEN 1
              WHEN 'moderate' THEN 2
              WHEN 'minor' THEN 3
              ELSE 4
            END,
            p.url_normalized
         LIMIT ? OFFSET ?
        """  # noqa: S608
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [normalize_finding(dict(r)) for r in rows]


def grouped_by_rule(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Per-rule rollup, the actionable WCAG cut.

    The :func:`by_sc` view groups by WCAG success criterion, which is
    the *reporting* axis ("we're failing 1.4.3 on 47 pages"). This view
    groups by axe ``rule_id``, which is the *fixing* axis: ``color-contrast``
    failing 800 times is usually one CSS class on one template; the
    operator wants to see one group of 800, not 800 separate rows.

    Alfa is deliberately one level narrower: ``failed`` and ``cant_tell``
    are separate outcome subgroups even when they share a rule id. A
    ``cantTell`` observation is an expert-review lead, not a failed ACT
    outcome, and combining the two would let a bulk action or confidence
    label from the failed subgroup silently apply to ambiguous evidence.

    Each group carries:

    * ``rule_id``, ``impact``, ``help``, ``help_url``, ``wcag_sc``,
      ``wcag_scs`` (every SC the rule maps to), ``wcag_level``
    * ``violation_count``, ``page_count``
    * ``status_breakdown`` (one bucket per triage status)
    * ``findings``, every individual violation row, page-joined,
      ready for bulk-status

    Ordered worst-impact-first, then largest page_count (most spread →
    biggest payoff for the fix).
    """
    extra_clause = ""
    params: list[Any] = [scan_id]
    if status and status in _STATUSES:
        extra_clause = " AND a.status = ?"
        params.append(status)

    rows = conn.execute(
        f"""
        SELECT a.id, a.pipeline, a.engine_outcome, a.rule_id, a.wcag_sc, a.wcag_scs, a.wcag_level,
               a.impact, a.help, a.help_url, a.target_selector,
               a.failure_summary, a.html_snippet, a.engine_evidence_json, a.status,
               a.revealed_by, a.screenshot_hash,
               p.id AS page_id, p.url_normalized AS page_url,
               p.title AS page_title
          FROM page_a11y_findings a
          JOIN pages p ON p.id = a.page_id
         WHERE a.scan_id = ?{extra_clause}
         ORDER BY a.pipeline, a.rule_id, p.url_normalized
        """,  # noqa: S608, extra_clause is one of two fixed strings
        tuple(params),
    ).fetchall()

    groups: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for r in rows:
        rule_id = str(r["rule_id"])
        pipeline = str(r["pipeline"])
        raw_outcome = str(r["engine_outcome"] or "failed")
        # Non-Alfa pipelines keep their established per-rule grouping. Alfa's
        # two outcome types have materially different evidentiary meaning and
        # therefore may never share a group or a list of bulk-action ids.
        outcome_group = raw_outcome if pipeline == "alfa" else None
        key = (pipeline, rule_id, outcome_group)
        entry = groups.setdefault(
            key,
            {
                "rule_id": rule_id,
                "pipeline": pipeline,
                "outcome_group": outcome_group,
                "impact": r["impact"],
                "help": str(r["help"] or ""),
                "help_url": str(r["help_url"] or ""),
                "wcag_sc": r["wcag_sc"],
                "wcag_scs": r["wcag_scs"],
                "wcag_level": r["wcag_level"],
                "violation_count": 0,
                "page_count_set": set(),
                "status_breakdown": dict.fromkeys(_STATUSES, 0),
                "engine_outcomes": {"failed": 0, "cant_tell": 0},
                "findings": [],
            },
        )
        entry["violation_count"] += 1
        entry["page_count_set"].add(int(r["page_id"]))
        entry["status_breakdown"][str(r["status"])] = (
            entry["status_breakdown"].get(str(r["status"]), 0) + 1
        )
        outcome = raw_outcome
        if outcome in entry["engine_outcomes"]:
            entry["engine_outcomes"][outcome] += 1
        entry["findings"].append(
            normalize_finding(
                {
                    "id": int(r["id"]),
                    "pipeline": pipeline,
                    "engine_outcome": r["engine_outcome"],
                    "page_id": int(r["page_id"]),
                    "page_url": str(r["page_url"]),
                    "page_title": r["page_title"],
                    "target_selector": str(r["target_selector"] or ""),
                    # The control operated to reach this state; NULL when the
                    # finding was present at page load.
                    "revealed_by": (str(r["revealed_by"]) if r["revealed_by"] else None),
                    "failure_summary": r["failure_summary"],
                    "html_snippet": r["html_snippet"],
                    "engine_evidence_json": r["engine_evidence_json"],
                    "status": str(r["status"]),
                    # Blob hash of the scan-time screenshot with the detected
                    # location circled, the inline evidence the Issues view
                    # expands, so the reviewer never has to leave the list.
                    "screenshot_hash": (
                        str(r["screenshot_hash"]) if r["screenshot_hash"] else None
                    ),
                }
            )
        )

    out: list[dict[str, Any]] = []
    for entry in groups.values():
        entry["page_count"] = len(entry.pop("page_count_set"))
        out.append(entry)

    return sorted(
        out,
        key=lambda g: (
            _IMPACT_RANK.get(g["impact"], 4),
            -g["page_count"],
            g["rule_id"],
            0 if g["outcome_group"] == "failed" else 1,
        ),
    )


def by_status(conn: sqlite3.Connection, scan_id: int) -> dict[str, int]:
    """Violation counts grouped by triage status, for the filter bar."""
    out: dict[str, int] = dict.fromkeys(_STATUSES, 0)
    rows = conn.execute(
        """
        SELECT status, COUNT(*) AS n
          FROM page_a11y_findings
         WHERE scan_id = ?
         GROUP BY status
        """,
        (scan_id,),
    ).fetchall()
    for row in rows:
        out[row["status"]] = int(row["n"])
    return out
