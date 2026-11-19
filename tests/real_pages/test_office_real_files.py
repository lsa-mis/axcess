"""The Word and PowerPoint check's metric: precision and recall on real files.

AGENTS.md ("Building a check: real pages first", steps 6 and 7): a check is
measured on a labelled set of real files, not on files we wrote. This reads
each labelled file (``office_files.json``; how it was made is in
``office_files.py``) with the app's own code (``office_check.sniff`` and
``check_office``) and scores it twice:

* per check: the check key a criterion names (``office_files.CRITERIA``)
  against the label, "fail" a positive, "pass" and "n/a" negatives;
* per file: "Mostly sure" against ``barrier``, the labeller's verdict that
  a screen reader user meets a barrier the counted checks can prove.

Each score is given for each part (``split``): "holdout" and "tuning",
together the "development" set (every rule of 2026-11-19 was chosen
looking at all of them), and "fresh", 57 Word files labelled and frozen
before the check was run on them, with the rules frozen at commit 946ad6f.
The fresh part is the number that counts. A criterion or ``barrier``
labelled "disputed" is listed, not scored (AGENTS.md, step 6).

It downloads the files from their sites, so it runs only on request:

    AXCESS_REAL_PAGES=1 uv run pytest tests/real_pages/test_office_real_files.py -s

The bytes are kept in ``AXCESS_REAL_FILES_DIR`` (default
``build/real_files``) as ``<sha256>.<ext>``, and a file already there is not
downloaded again. Downloads go one at a time, at most one a second, with
robots.txt obeyed, a Google Doc or deck through Google's export address
(``google.export_address``). A file that changed since it was labelled is
reported as "changed" and not scored: it must be labelled again. "Changed"
means another SHA-256 for a file a site serves, and another ``content_key``
for a Google export: Google renames the pictures and relationship IDs in
every export (two exports of one Doc a minute apart differ in bytes), so
the key hashes the parts with those names taken out. Writes
``office_real_files.json`` there.

The labelling protocol the labellers followed (2026-11-17), in short: each
criterion is "fail", "pass" or "n/a" for the file's body (Word) or slides
(PowerPoint). alt_text: a picture, chart, diagram or video with no alt text
and not marked decorative (a file name counts as none; text boxes, plain
shapes, slide masters and Word headers and footers excluded).
table_header: a DATA table (not a layout table) with no header row marked.
slide_title: a slide with no title placeholder holding text. language: no
language anywhere. headings: a document with visible section headings and
no heading style. heading_order: a heading more than one level deeper than
the one before. link_text: a link whose words are a web address or a
phrase such as "click here". title: no Title property. barrier: any of the
first five fails.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import time
import urllib.robotparser
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pytest

from audit.linked_files.google import export_address
from audit.linked_files.office_check import check_office, sniff

from .office_files import CRITERIA, load

pytestmark = pytest.mark.skipif(
    os.environ.get("AXCESS_REAL_PAGES") != "1",
    reason="downloads files from outside sites; set AXCESS_REAL_PAGES=1 to run",
)

_DIR = Path(os.environ.get("AXCESS_REAL_FILES_DIR", "build/real_files"))
_AGENT = "axcess/0.1 (+local accessibility audit)"


class _Polite:
    """One request at a time, at most one a second, robots.txt obeyed."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": _AGENT}, timeout=30, follow_redirects=True
        )
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last = 0.0

    def _get(self, url: str) -> httpx.Response:
        wait = 1.0 - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        return self._client.get(url)

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                answer = self._get(f"{origin}/robots.txt")
                parser.parse(answer.text.splitlines() if answer.status_code < 400 else [])
            except httpx.HTTPError:
                parser.parse([])
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(_AGENT, url)

    def fetch(self, url: str) -> bytes | None:
        if not self.allowed(url):
            return None
        try:
            answer = self._get(url)
        except httpx.HTTPError:
            return None
        return answer.content if answer.status_code < 400 else None


def _bytes(entry: dict[str, Any], polite: _Polite) -> bytes | None:
    """The entry's file, from the cache (named by the labelled SHA-256) or downloaded."""
    for path in _DIR.glob(f"{entry['sha256']}.*"):
        return path.read_bytes()
    target = export_address(entry["url"]) if entry["kind"].startswith("google") else entry["url"]
    data = polite.fetch(target) if target else None
    if data is not None:
        _DIR.mkdir(parents=True, exist_ok=True)
        ext = "pptx" if entry["kind"] in {"pptx", "google_slides"} else "docx"
        (_DIR / f"{entry['sha256']}.{ext}").write_bytes(data)
    return data


def content_key(data: bytes) -> str:
    """A hash of a Word or PowerPoint file's content that is the same for
    every export Google makes of one Doc: each XML part with relationship
    IDs and picture file names taken out, then each picture's own hash."""
    digest = hashlib.sha256()
    pictures = []
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        for name in sorted(package.namelist()):
            body = package.read(name)
            if "/media/" in name:
                pictures.append(hashlib.sha256(body).hexdigest())
            elif not (
                name.endswith(".rels")
                or name.startswith("docProps/")
                or name == "[Content_Types].xml"
            ):
                body = re.sub(rb'(r:(id|embed|link|pict)|Id)="[^"]*"', b"", body)
                digest.update(name.encode() + re.sub(rb"image\d+\.\w+", b"image", body))
    for picture in sorted(pictures):
        digest.update(picture.encode())
    return digest.hexdigest()


def unchanged(entry: dict[str, Any], data: bytes) -> bool:
    if entry["kind"].startswith("google"):
        return bool(entry.get("content_key")) and content_key(data) == entry["content_key"]
    return hashlib.sha256(data).hexdigest() == entry["sha256"]


def _upper_95(errors: int, n: int) -> float | None:
    """One-sided 95% upper bound on a rate seen ``errors`` times in ``n``
    (Clopper-Pearson for zero; Wilson otherwise)."""
    if n == 0:
        return None
    if errors == 0:
        return 1 - 0.05 ** (1 / n)
    z = 1.645
    p = errors / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (centre + spread) / (1 + z * z / n))


def score(pairs: list[tuple[bool, bool, str]]) -> dict[str, Any]:
    """(expected positive, predicted positive, id) pairs: counts and rates."""
    tp = sum(e and p for e, p, _ in pairs)
    fp = sum(not e and p for e, p, _ in pairs)
    fn = sum(e and not p for e, p, _ in pairs)
    return {
        "n": len(pairs),
        "positives": tp + fn,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "false_discovery_upper_95": _upper_95(fp, tp + fp),
        "recall": tp / (tp + fn) if tp + fn else None,
        "miss_rate_upper_95": _upper_95(fn, tp + fn),
        "false_positives": [i for e, p, i in pairs if not e and p],
        "false_negatives": [i for e, p, i in pairs if e and not p],
    }


def run_set() -> dict[str, Any]:
    polite = _Polite()
    rows: list[dict[str, Any]] = []
    for entry in load():
        data = _bytes(entry, polite)
        row: dict[str, Any] = {"id": entry["id"], "split": entry["split"], "kind": entry["kind"]}
        if data is None:
            row["outcome"] = "not downloaded"
        elif not unchanged(entry, data):
            row["outcome"] = "changed"
        else:
            started = time.perf_counter()
            result = check_office(data, sniff(data))
            row.update(
                outcome=result.outcome,
                seconds=round(time.perf_counter() - started, 4),
                failed=list(result.failed),
                status=result.status if result.outcome == "checked" else None,
            )
        rows.append(row)

    by_id = {entry["id"]: entry for entry in load()}
    report: dict[str, Any] = {"files": rows, "scores": {}}
    for split, members in SPLITS.items():
        rows_in = [r for r in rows if r["split"] in members]
        scored = [r for r in rows_in if r.get("outcome") == "checked"]
        part: dict[str, Any] = {
            "files": len(rows_in),
            "scored": len(scored),
            "not_scored": dict(Counter(r["outcome"] for r in rows_in if r["outcome"] != "checked")),
            "disputed": [r["id"] for r in scored if by_id[r["id"]]["barrier"] == "disputed"],
            "mostly_sure": score(
                [
                    (by_id[r["id"]]["barrier"] is True, r["status"] == "mostly_sure", r["id"])
                    for r in scored
                    if by_id[r["id"]]["barrier"] != "disputed"
                ]
            ),
        }
        for criterion, key in CRITERIA.items():
            part[key] = score(
                [
                    (by_id[r["id"]]["expected"][criterion] == "fail", key in r["failed"], r["id"])
                    for r in scored
                    if by_id[r["id"]]["expected"][criterion] != "disputed"
                ]
            )
        report["scores"][split] = part
    return report


#: Each reported part and the ``split`` values it holds.
SPLITS: dict[str, tuple[str, ...]] = {
    "holdout": ("holdout",),
    "tuning": ("tuning",),
    "development": ("holdout", "tuning"),
    "fresh": ("fresh",),
}


def _rate(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def test_office_check_on_real_files() -> None:
    report = run_set()
    _DIR.mkdir(parents=True, exist_ok=True)
    (_DIR / "office_real_files.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    for split, part in report["scores"].items():
        print(
            f"\n== {split}: {part['scored']} of {part['files']} files scored {part['not_scored']}"
            f" disputed={part['disputed']}"
        )
        for name, s in part.items():
            if isinstance(s, dict) and "tp" in s:
                print(
                    f"  {name:24} n={s['n']:3} pos={s['positives']:3} tp={s['tp']:3} "
                    f"fp={s['fp']:3} fn={s['fn']:3} precision={_rate(s['precision'])} "
                    f"(false alarms <= {_rate(s['false_discovery_upper_95'])}) "
                    f"recall={_rate(s['recall'])} (misses <= {_rate(s['miss_rate_upper_95'])})"
                )
    # A file whose label records it as damaged as served (a bad ZIP) is
    # expected to read "damaged"; any other is a fault in the check.
    known = {entry["id"] for entry in load() if entry.get("damaged")}
    damaged = [
        r["id"] for r in report["files"] if r.get("outcome") == "damaged" and r["id"] not in known
    ]
    assert not damaged, f"real files the check could not read: {damaged}"
