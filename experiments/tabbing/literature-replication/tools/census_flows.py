"""Summarize what each downloaded KAFE capture actually contains.

Feasibility evidence only: counts of flows, exchanges, statuses and content
types, plus which URL looks like the top-level document. No browser, no
scoring. Writes compact derived metadata that is safe to commit; the captured
bytes themselves stay under artifacts/.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tools import flowfile

HERE = Path(__file__).resolve().parent.parent
ARTIFACTS = HERE / "artifacts"
DERIVED = HERE / "derived"

# Appendix Table 1 of the authors' supplementary PDF, for later comparison.
APPENDIX = {
    "citiprogram": {"total": 57, "visible": 43, "ctrl": 13, "iaf": 3, "ktf": 0},
    "craigslist": {"total": 1522, "visible": 851, "ctrl": 288, "iaf": 11, "ktf": 0},
    "coronavirus": {"total": 121, "visible": 118, "ctrl": 34, "iaf": 0, "ktf": 0},
}


def _family(content_type: str) -> str:
    base = content_type.split(";")[0].strip().lower()
    if not base:
        return "(none)"
    if base.startswith("text/html"):
        return "html"
    if "javascript" in base or base.endswith("/json"):
        return "script/json"
    if base.startswith("text/css"):
        return "css"
    if base.startswith("image/"):
        return "image"
    if base.startswith("font/") or "font" in base:
        return "font"
    return base


def summarize(path: Path) -> dict[str, object]:
    subject = path.stem.replace("subject_", "")
    index = flowfile.load_exchanges(path.read_bytes())

    statuses: Counter[int] = Counter()
    families: Counter[str] = Counter()
    hosts: Counter[str] = Counter()
    body_bytes = 0
    html_docs: list[tuple[str, int]] = []

    for url, exchanges in index.by_url.items():
        for exchange in exchanges:
            statuses[exchange.status] += 1
            family = _family(exchange.headers.get("content-type", ""))
            families[family] += 1
            hosts[url.split("/")[2]] += 1
            body_bytes += len(exchange.body)
            if family == "html" and exchange.status == 200:
                html_docs.append((url, len(exchange.body)))

    html_docs.sort(key=lambda item: -item[1])

    return {
        "subject": subject,
        "capture_bytes": path.stat().st_size,
        "flows": index.flow_count,
        "exchanges": index.exchange_count,
        "unique_urls": len(index.by_url),
        "responseless_flows": index.responseless,
        "unreadable_tail": index.unreadable,
        "body_bytes_total": body_bytes,
        "statuses": dict(sorted(statuses.items())),
        "content_families": dict(families.most_common()),
        "distinct_hosts": len(hosts),
        "top_hosts": dict(hosts.most_common(5)),
        "html_200_count": len(html_docs),
        "largest_html": html_docs[0][0] if html_docs else None,
        "largest_html_bytes": html_docs[0][1] if html_docs else 0,
        "appendix": APPENDIX.get(subject),
    }


if __name__ == "__main__":
    report = [summarize(p) for p in sorted(ARTIFACTS.glob("subject_*.bin"))]
    DERIVED.mkdir(parents=True, exist_ok=True)
    (DERIVED / "capture_census.json").write_text(json.dumps(report, indent=2) + "\n")
    for entry in report:
        print(
            f"{entry['subject']:>13} "
            f"flows={entry['flows']:<5} urls={entry['unique_urls']:<5} "
            f"hosts={entry['distinct_hosts']:<4} "
            f"html200={entry['html_200_count']:<4} "
            f"body={entry['body_bytes_total']:>9} "
            f"unreadable={entry['unreadable_tail']}"
        )
        print(f"{'':>13} statuses={entry['statuses']}")
        print(f"{'':>13} families={entry['content_families']}")
        print(f"{'':>13} doc={entry['largest_html']}")
