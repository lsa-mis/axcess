"""Cross-scan finding diff.

Compares two scans by the ``(content_hash, url_normalized)`` pair so an image
that moved to a new page counts as "resolved at the old URL, new at the new
URL" — which is what a reviewer wants to see.

Buckets:
  * ``new`` — pair present in current scan but not in the compare-to scan.
  * ``resolved`` — pair present in the compare-to scan but not in the current.
  * ``still_open`` — pair present in both; current status is open-ish
    (``new``, ``reviewing``, or ``in_progress``).
  * ``status_changed`` — pair present in both, status differs.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import TypedDict

from audit.crawler.url_policy import compare_key

_OPEN_STATUSES = {"new", "reviewing", "in_progress"}


class _PairRow(TypedDict):
    image_id: int
    finding_id: int
    severity: str
    status: str
    original_url: str


@dataclass(frozen=True)
class DiffEntry:
    """One pair-level row in a diff bucket."""

    content_hash: str
    url_normalized: str
    image_id: int
    severity: str | None
    previous_severity: str | None
    current_finding_id: int | None
    previous_finding_id: int | None
    current_status: str | None
    previous_status: str | None


@dataclass
class DiffReport:
    """Full diff between two scans."""

    current_scan_id: int
    compare_to_scan_id: int
    new: list[DiffEntry] = field(default_factory=list)
    resolved: list[DiffEntry] = field(default_factory=list)
    still_open: list[DiffEntry] = field(default_factory=list)
    status_changed: list[DiffEntry] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "new": len(self.new),
            "resolved": len(self.resolved),
            "still_open": len(self.still_open),
            "status_changed": len(self.status_changed),
        }


def compute_diff(
    conn: sqlite3.Connection,
    *,
    current_scan_id: int,
    compare_to_scan_id: int,
) -> DiffReport:
    """Build a :class:`DiffReport` between two scans."""
    current = _collect_pairs(conn, current_scan_id)
    previous = _collect_pairs(conn, compare_to_scan_id)

    report = DiffReport(
        current_scan_id=current_scan_id,
        compare_to_scan_id=compare_to_scan_id,
    )

    current_keys = set(current.keys())
    previous_keys = set(previous.keys())

    for key in sorted(current_keys - previous_keys):
        cur = current[key]
        report.new.append(
            DiffEntry(
                content_hash=key[0],
                url_normalized=cur["original_url"],
                image_id=cur["image_id"],
                severity=cur["severity"],
                previous_severity=None,
                current_finding_id=cur["finding_id"],
                previous_finding_id=None,
                current_status=cur["status"],
                previous_status=None,
            )
        )

    for key in sorted(previous_keys - current_keys):
        prev = previous[key]
        report.resolved.append(
            DiffEntry(
                content_hash=key[0],
                url_normalized=prev["original_url"],
                image_id=prev["image_id"],
                severity=None,
                previous_severity=prev["severity"],
                current_finding_id=None,
                previous_finding_id=prev["finding_id"],
                current_status=None,
                previous_status=prev["status"],
            )
        )

    for key in sorted(current_keys & previous_keys):
        cur = current[key]
        prev = previous[key]
        entry = DiffEntry(
            content_hash=key[0],
            url_normalized=cur["original_url"],
            image_id=cur["image_id"],
            severity=cur["severity"],
            previous_severity=prev["severity"],
            current_finding_id=cur["finding_id"],
            previous_finding_id=prev["finding_id"],
            current_status=cur["status"],
            previous_status=prev["status"],
        )
        if cur["status"] != prev["status"]:
            report.status_changed.append(entry)
        elif cur["status"] in _OPEN_STATUSES:
            report.still_open.append(entry)

    return report


def _collect_pairs(conn: sqlite3.Connection, scan_id: int) -> dict[tuple[str, str], _PairRow]:
    """Return ``{(content_hash, url_normalized): finding_data}`` for a scan."""
    rows = conn.execute(
        """
        SELECT DISTINCT i.content_hash,
                        p.url_normalized,
                        i.id AS image_id,
                        f.id AS finding_id,
                        f.severity,
                        f.status
          FROM findings f
          JOIN images i ON i.id = f.image_id
          JOIN page_images pi ON pi.image_id = i.id
          JOIN pages p ON p.id = pi.page_id
         WHERE f.scan_id = ? AND p.scan_id = ?
        """,
        (scan_id, scan_id),
    ).fetchall()
    out: dict[tuple[str, str], _PairRow] = {}
    for row in rows:
        url = str(row["url_normalized"])
        # The match key is the port-tolerant canonical form; the display URL
        # on the DiffEntry stays the as-crawled URL.
        key = (str(row["content_hash"]), compare_key(url))
        out.setdefault(
            key,
            _PairRow(
                image_id=int(row["image_id"]),
                finding_id=int(row["finding_id"]),
                severity=str(row["severity"]),
                status=str(row["status"]),
                original_url=url,
            ),
        )
    return out


def materialize_history(
    conn: sqlite3.Connection,
    *,
    current_scan_id: int,
    compare_to_scan_id: int,
) -> dict[str, int]:
    """Write ``finding_history`` rows for first-seen and resolved pairs.

    Idempotent on ``(finding_id, change_type)``: re-running against the same
    two scans won't produce duplicate history rows.
    """
    report = compute_diff(
        conn,
        current_scan_id=current_scan_id,
        compare_to_scan_id=compare_to_scan_id,
    )
    first_seen = 0
    resolved = 0
    for entry in report.new:
        if entry.current_finding_id is None:
            continue
        inserted = _insert_history_once(
            conn,
            finding_id=entry.current_finding_id,
            scan_id=current_scan_id,
            change_type="first_seen",
        )
        if inserted:
            first_seen += 1
    for entry in report.resolved:
        if entry.previous_finding_id is None:
            continue
        inserted = _insert_history_once(
            conn,
            finding_id=entry.previous_finding_id,
            scan_id=current_scan_id,
            change_type="resolved",
        )
        if inserted:
            resolved += 1
    return {"first_seen": first_seen, "resolved": resolved}


def _insert_history_once(
    conn: sqlite3.Connection,
    *,
    finding_id: int,
    scan_id: int,
    change_type: str,
) -> bool:
    existing = conn.execute(
        "SELECT 1 FROM finding_history WHERE finding_id = ? AND change_type = ? AND scan_id = ?",
        (finding_id, change_type, scan_id),
    ).fetchone()
    if existing is not None:
        return False
    conn.execute(
        """
        INSERT INTO finding_history
            (finding_id, scan_id, change_type, from_status, to_status, actor, note)
        VALUES (?, ?, ?, NULL, NULL, 'system', NULL)
        """,
        (finding_id, scan_id, change_type),
    )
    return True
