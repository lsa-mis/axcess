"""JSON export — nested per-finding with an ``occurrences`` array."""

from __future__ import annotations

import json
from typing import Any

from audit.exports.collector import ExportScan

SCHEMA_VERSION = 1


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
        },
        "findings": [finding.to_dict() for finding in scan.findings],
    }
