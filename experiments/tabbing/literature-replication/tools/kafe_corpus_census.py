"""Verify every fetched KAFE subject parses as a real mitmproxy capture.

A download can succeed at the HTTP level and still be worthless: Drive answers
an expired or rate-limited request with an HTML interstitial, which lands on
disk as a plausible-looking file of plausible-looking size. The only way to know
the bytes are captures is to parse them, so this reads every subject and reports
per-file flow counts, entry documents and failures.

Reports failures prominently and does not stop on the first one: a partial
corpus with three bad files is a different situation from a broken parser, and
the counts are what distinguish them.
"""

from __future__ import annotations

import json
import pathlib

from tools.flowfile import load_exchanges

HERE = pathlib.Path(__file__).resolve().parent.parent
SUBJECTS = HERE / "artifacts" / "subjects"
LEGACY = {
    "citiprogram": HERE / "artifacts" / "subject_citiprogram.bin",
    "craigslist": HERE / "artifacts" / "subject_craigslist.bin",
    "coronavirus": HERE / "artifacts" / "subject_coronavirus.bin",
}
OUT = HERE / "derived" / "kafe_corpus_census.json"


def census_one(name: str, path: pathlib.Path) -> dict:
    raw = path.read_bytes()
    try:
        index = load_exchanges(raw)
    except Exception as exc:  # a bad download must be visible, not fatal
        return {"subject": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    exchanges = [e for group in index.by_url.values() for e in group]
    html = [
        e
        for e in exchanges
        if e.status == 200
        and "text/html" in (e.headers.get("content-type", "")).lower()
    ]
    hosts = {e.url.split("/")[2] for e in exchanges if "//" in e.url}
    return {
        "subject": name,
        "ok": True,
        "bytes": len(raw),
        "flows": index.flow_count,
        "exchanges": index.exchange_count,
        "responseless": index.responseless,
        "unreadable": index.unreadable,
        "html_200s": len(html),
        "hosts": len(hosts),
        "entry": html[0].url if html else None,
    }


def main() -> int:
    targets: dict[str, pathlib.Path] = dict(LEGACY)
    for path in sorted(SUBJECTS.glob("*.bin")):
        targets.setdefault(path.stem, path)

    rows = [census_one(name, path) for name, path in sorted(targets.items())]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=2) + "\n")

    good = [r for r in rows if r["ok"]]
    bad = [r for r in rows if not r["ok"]]

    if bad:
        print(f"PARSE FAILURES ({len(bad)}):")
        for r in bad:
            print(f"  {r['subject']:<22}{r['error']}")
        print()

    print(f"parsed {len(good)}/{len(rows)} subjects")
    print(f"total flows     : {sum(r['flows'] for r in good):,}")
    print(f"total bytes     : {sum(r['bytes'] for r in good):,}")
    print(f"subjects with an HTML entry document: "
          f"{sum(1 for r in good if r['entry'])}/{len(good)}")
    print()
    print(f"{'subject':<22}{'flows':>7}{'html':>6}{'hosts':>7}  entry")
    for r in good[:6]:
        print(f"{r['subject']:<22}{r['flows']:>7}{r['html_200s']:>6}"
              f"{r['hosts']:>7}  {(r['entry'] or '')[:52]}")
    print(f"  ... {len(good) - 6} more in {OUT.name}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
