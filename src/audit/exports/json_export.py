"""JSON export, nested per-finding with an ``occurrences`` array."""

from __future__ import annotations

import json
from typing import Any

from audit.exports.collector import ExportScan

# Version 3 adds independently attributed Alfa coverage and per-finding ACT
# outcomes alongside the existing axe-core evidence. Earlier consumers still
# parse the additive fields, while the explicit version lets downstream users
# opt in to source-aware reporting.
#
# Version 4 adds ``revealed_by`` on each a11y finding: the control that had to
# be operated before the finding existed, or null when the page load showed it.
# A consumer that treats every finding as reachable on load will report
# click-revealed barriers as unreproducible, so the field is additive but
# meaningful, hence a version bump rather than a silent column.
SCHEMA_VERSION = 4


def render_json(scan: ExportScan, *, indent: int | None = 2) -> str:
    """Serialize a scan to deterministic JSON.

    Keys are sorted at every level so diffs across runs are meaningful.
    """
    payload = to_payload(scan)
    return json.dumps(payload, indent=indent, sort_keys=True, ensure_ascii=False)


def to_payload(scan: ExportScan) -> dict[str, Any]:
    """Return the Python dict that ``render_json`` serializes.

    Exposed separately so other surfaces (webhook, API endpoints) can build
    a JSON body without re-serializing through a string.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "scan": {
            "id": scan.id,
            "seed_url": scan.seed_url,
            "status": scan.status,
            "started_at": scan.started_at,
            "finished_at": scan.finished_at,
            "page_count": scan.page_count,
            "finding_count": scan.finding_count,
            "error_count": scan.error_count,
            "by_severity": dict(scan.by_severity),
            "axe_pages_scanned": scan.axe_pages_scanned,
            "axe_violations_total": scan.axe_violations_total,
            "alfa_pages_scanned": scan.alfa_pages_scanned,
            "alfa_failed_total": scan.alfa_failed_total,
            "alfa_cant_tell_total": scan.alfa_cant_tell_total,
            "by_wcag_level": dict(scan.by_wcag_level),
        },
        # Image-of-text findings (WCAG 1.4.5 pipeline), unchanged shape.
        "findings": [finding.to_dict() for finding in scan.findings],
        # WCAG axe-core findings (DOM pipeline). Sibling array so v1
        # consumers reading only `findings` keep working; v2-aware
        # consumers pick up the new pipeline here.
        "a11y_findings": [af.to_dict() for af in scan.a11y_findings],
    }
