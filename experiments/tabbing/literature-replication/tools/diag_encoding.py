"""Check what content-encodings the captures use and what the doc body looks like."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools import flowfile

ARTIFACTS = Path(__file__).resolve().parent.parent / "artifacts"

for path in sorted(ARTIFACTS.glob("subject_*.bin")):
    index = flowfile.load_exchanges(path.read_bytes())
    encodings: Counter[str] = Counter()
    doc = None
    for url, exchanges in index.by_url.items():
        for exchange in exchanges:
            encodings[exchange.headers.get("content-encoding", "(none)")] += 1
            if exchange.headers.get("content-type", "").startswith("text/html"):
                if doc is None or len(exchange.body) > len(doc.body):
                    doc = exchange
    print(f"== {path.stem}: encodings={dict(encodings)}")
    if doc:
        print(f"   doc {doc.url}")
        print(f"   enc={doc.headers.get('content-encoding')!r} bytes={len(doc.body)}")
        print(f"   head={doc.body[:70]!r}")
