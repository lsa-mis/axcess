"""Read-side queries for the grouped image-of-text findings view.

Parallels :mod:`audit.web.a11y_queries` for the other pipeline. Where
the WCAG view groups by ``wcag_sc``, this view groups by the
``(classification, alt_adequacy)`` pair, because that pair is the
*natural identity of an issue type*: every finding sharing that pair
maps to the same row in ``rules/remediation.yaml`` and therefore the
same recommended fix.

The shape returned by :func:`grouped_by_remediation`:

    [
        {
            "classification": "essential",
            "alt_adequacy": "missing",
            "label": "Essential, missing alt",          # human-readable
            "remediation_hint": "This image contains...",
            "finding_count": 8,
            "occurrence_count": 14,
            "severity_breakdown": {"critical": 6, "major": 2, ...},
            "status_breakdown": {"new": 7, "remediated": 1, ...},
            "findings": [
                {
                    "id": ...,
                    "severity": "critical",
                    "priority_score": 9.1,
                    "status": "new",
                    "classification": "essential",
                    "alt_adequacy": "missing",
                    "ocr_text": "BUY WIDGETS NOW",
                    "image_url": "...",
                    "content_hash": "...",
                    "has_svg_text": False,
                    "occurrences": [
                        {"page_id": ..., "page_url": "...", "alt_text": None, ...},
                        ...
                    ],
                    "ui_url": "/findings/123",
                },
                ...
            ],
        },
        ...
    ]

Groups are ordered worst-first by:

1. Highest severity in the group (critical > major > minor > info).
2. Within an equal worst-severity, the largest occurrence count.

This gives the operator a stack-ranked work queue: the most urgent
class of problem at the top, the most-repeated next.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from audit.synthesizer.alt_compare import AltAdequacy, compare, worst

_SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2, "info": 3}

# Canonical ordering for the inner severity / status breakdown tables.
SEVERITIES = ("critical", "major", "minor", "info")
ALT_ADEQUACIES = ("missing", "inadequate", "partial", "adequate")

# Human-readable labels for the (classification, alt_adequacy) pairs.
# Kept here, not in the template, because both the SPA and Jinja views
# render the same label, duplicating it would invite drift.
_CLASSIFICATION_LABELS = {
    "essential": "Essential image",
    "informational": "Informational image",
    "logo": "Logo",
    "decorative": "Decorative image",
    "no_meaningful_text": "Image with no meaningful text",
    None: "Image (unclassified)",
}
_ADEQUACY_LABELS = {
    "missing": "missing alt",
    "inadequate": "inadequate alt",
    "partial": "partial alt",
    "adequate": "adequate alt",
}


def group_label(classification: str | None, alt_adequacy: str) -> str:
    """Render a human label for a (classification, alt_adequacy) pair."""
    cls = _CLASSIFICATION_LABELS.get(classification, classification or "Image")
    adq = _ADEQUACY_LABELS.get(alt_adequacy, alt_adequacy)
    return f"{cls}, {adq}"


def grouped_by_remediation(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    """Return image findings grouped by ``(classification, alt_adequacy)``.

    The grouping key is the same key that drives `rules/remediation.yaml`,
    so every finding in a group inherits the same ``remediation_hint``.
    We surface the hint at the group level (not per-finding) because
    repeating it on every row is noisy and risks the user assuming
    different findings have different fixes when in fact they don't.
    """
    findings = _load_findings(conn, scan_id, status=status)
    groups: dict[tuple[str | None, str], dict[str, Any]] = {}

    for f in findings:
        key = (f["classification"], f["alt_adequacy"])
        entry = groups.setdefault(
            key,
            {
                "classification": f["classification"],
                "alt_adequacy": f["alt_adequacy"],
                "label": group_label(f["classification"], f["alt_adequacy"]),
                # We pick the hint from the first finding we see in the
                # group. Because the rules table is keyed on
                # (classification, alt_adequacy) and rendered by the
                # synthesizer at write-time, every finding in the same
                # group carries the *same* hint string, there is no
                # ambiguity here, just first-write-wins.
                "remediation_hint": f["remediation_hint"],
                "finding_count": 0,
                "occurrence_count": 0,
                "severity_breakdown": dict.fromkeys(SEVERITIES, 0),
                "status_breakdown": {},
                "worst_severity_rank": _SEVERITY_RANK["info"] + 1,
                "worst_severity": "info",
                "findings": [],
            },
        )
        entry["finding_count"] += 1
        entry["occurrence_count"] += len(f["occurrences"])
        entry["severity_breakdown"][f["severity"]] = (
            entry["severity_breakdown"].get(f["severity"], 0) + 1
        )
        entry["status_breakdown"][f["status"]] = entry["status_breakdown"].get(f["status"], 0) + 1
        rank = _SEVERITY_RANK.get(f["severity"], _SEVERITY_RANK["info"])
        if rank < entry["worst_severity_rank"]:
            entry["worst_severity_rank"] = rank
            entry["worst_severity"] = f["severity"]
        entry["findings"].append(f)

    # Within each group, sort findings by priority desc so the operator
    # sees the most-urgent rows first when they expand a group.
    for entry in groups.values():
        entry["findings"].sort(key=lambda x: (-(x["priority_score"] or 0), x["id"]))
        entry.pop("worst_severity_rank", None)

    # Order the groups themselves: worst severity first, then largest
    # occurrence count.
    return sorted(
        groups.values(),
        key=lambda g: (
            _SEVERITY_RANK.get(g["worst_severity"], 4),
            -g["occurrence_count"],
        ),
    )


def coverage(conn: sqlite3.Connection, scan_id: int) -> dict[str, int]:
    """Top-line counts for the per-scan header card."""
    row = conn.execute(
        "SELECT finding_count, page_count FROM scans WHERE id = ?",
        (scan_id,),
    ).fetchone()
    if row is None:
        return {"finding_count": 0, "page_count": 0, "occurrence_total": 0}
    occ = conn.execute(
        """
        SELECT COUNT(*) AS n
          FROM page_images pi
          JOIN findings f ON f.image_id = pi.image_id AND f.scan_id = ?
          JOIN pages p ON p.id = pi.page_id AND p.scan_id = ?
        """,
        (scan_id, scan_id),
    ).fetchone()
    return {
        "finding_count": int(row["finding_count"] or 0),
        "page_count": int(row["page_count"] or 0),
        "occurrence_total": int(occ["n"] if occ else 0),
    }


def _load_findings(
    conn: sqlite3.Connection,
    scan_id: int,
    *,
    status: str | None,
) -> list[dict[str, Any]]:
    """Flat list of image findings with per-row classification and adequacy.

    Joins to ``analyses`` (best-rank per image, same trick as the
    exports collector) for OCR / VLM context, then recomputes
    ``alt_adequacy`` from the image's occurrences. We keep adequacy
    out of the DB schema deliberately: it's cheap to compute and the
    string comparison heuristic in :mod:`alt_compare` can evolve
    without a migration.
    """
    extra_clause = ""
    params: list[Any] = [scan_id]
    if status:
        extra_clause = " AND f.status = ?"
        params.append(status)

    rows = conn.execute(
        f"""
        WITH best AS (
            SELECT a.image_id,
                   a.ocr_text,
                   a.ocr_confidence,
                   a.vlm_classification,
                   a.vlm_rationale,
                   ROW_NUMBER() OVER (
                       PARTITION BY a.image_id
                       ORDER BY
                           CASE WHEN a.vlm_classification IS NOT NULL THEN 0 ELSE 1 END,
                           a.analyzed_at DESC,
                           a.id DESC
                   ) AS rank
              FROM analyses a
        )
        SELECT f.id, f.severity, f.status, f.priority_score,
               f.remediation_hint,
               i.id AS image_id, i.content_hash, i.mime, i.src_url_canonical,
               i.has_svg_text,
               b.ocr_text, b.ocr_confidence, b.vlm_classification, b.vlm_rationale
          FROM findings f
          JOIN images i ON i.id = f.image_id
          LEFT JOIN best b ON b.image_id = i.id AND b.rank = 1
         WHERE f.scan_id = ?{extra_clause}
         ORDER BY f.priority_score DESC, f.id ASC
        """,  # noqa: S608, `extra_clause` is one of two fixed strings
        tuple(params),
    ).fetchall()

    findings: list[dict[str, Any]] = []
    for r in rows:
        occurrences = _load_occurrences(conn, scan_id=scan_id, image_id=int(r["image_id"]))
        ocr_text = r["ocr_text"] or ""
        # Mirror the synthesizer: prefer OCR, fall back to the SVG
        # snippet when the image is an inline SVG.
        visible_text = ocr_text
        if not visible_text and bool(r["has_svg_text"]) and occurrences:
            visible_text = occurrences[0].get("context_snippet") or ""
        adequacy = (
            worst([compare(occ["alt_text"], visible_text) for occ in occurrences])
            if occurrences
            else AltAdequacy.MISSING
        )
        findings.append(
            {
                "id": int(r["id"]),
                "severity": str(r["severity"]),
                "status": str(r["status"]),
                "priority_score": float(r["priority_score"] or 0),
                "classification": r["vlm_classification"],
                "alt_adequacy": adequacy.value,
                "remediation_hint": r["remediation_hint"],
                "ocr_text": r["ocr_text"],
                "ocr_confidence": (
                    float(r["ocr_confidence"]) if r["ocr_confidence"] is not None else None
                ),
                "vlm_rationale": r["vlm_rationale"],
                "image_url": str(r["src_url_canonical"]),
                "content_hash": str(r["content_hash"]),
                "mime": r["mime"],
                "has_svg_text": bool(r["has_svg_text"]),
                "occurrences": occurrences,
            }
        )
    return findings


def _load_occurrences(
    conn: sqlite3.Connection, *, scan_id: int, image_id: int
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT pi.page_id, pi.alt_text, pi.above_fold, pi.position,
               pi.context_snippet,
               p.url_normalized AS page_url, p.title AS page_title
          FROM page_images pi
          JOIN pages p ON p.id = pi.page_id
         WHERE pi.image_id = ? AND p.scan_id = ?
         ORDER BY pi.position
        """,
        (image_id, scan_id),
    ).fetchall()
    return [
        {
            "page_id": int(r["page_id"]),
            "page_url": str(r["page_url"]),
            "page_title": r["page_title"],
            "alt_text": r["alt_text"],
            "above_fold": bool(r["above_fold"]),
            "position": int(r["position"]),
            "context_snippet": r["context_snippet"],
        }
        for r in rows
    ]
