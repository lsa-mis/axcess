"""Fetch the authorized KAFE artifacts into this experiment's artifacts/ dir.

Authorized scope (manager gate 1): staged local downloads up to 150 MB, no
redistribution, starting with three named subjects plus the small label and
reference artifacts. Captured third-party bytes stay under artifacts/, which
this experiment's .gitignore excludes.

Usage:
    uv run --offline --no-sync python -m tools.fetch_kafe list
    uv run --offline --no-sync python -m tools.fetch_kafe labels
    uv run --offline --no-sync python -m tools.fetch_kafe subjects
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tools import drivemeta

HERE = Path(__file__).resolve().parent.parent
ARTIFACTS = HERE / "artifacts"
DERIVED = HERE / "derived"

CAP_BYTES = 150 * 1024 * 1024

# Drive ids read from the public KAFE project folder (sources.json id 12).
FOLDER_SUBJECTS = "1pU6osxQUgAH6EfZ93sMcG9LPxgwstUYS"
FILE_SUPPLEMENTARY = "14g3qBzRM52i5FWvf07mbypwFyha7FgOM"
SHEET_RESULTS = "1Hy9-lFflGnmm-8eztyM3Zz3hzwvAyWSF6wZlcpAb3LU"
SHEET_CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_RESULTS}/export?format=csv"
)

# Named in PROTOCOL.md before any label was consulted for selection: two
# IAF-positive subjects and one clean control.
SAMPLE_SUBJECTS = ("citiprogram", "craigslist", "coronavirus")


def _manifest_path() -> Path:
    return ARTIFACTS / "MANIFEST.json"


def _load_records() -> list[dict[str, object]]:
    path = _manifest_path()
    if not path.exists():
        return []
    return json.loads(path.read_text())["artifacts"]


def _budget() -> drivemeta.ByteBudget:
    used = sum(int(r["bytes"]) for r in _load_records())
    return drivemeta.ByteBudget(limit=CAP_BYTES, used=used)


def _save(records: list[dict[str, object]]) -> None:
    drivemeta.write_manifest(_manifest_path(), records)


def cmd_list() -> int:
    """Fetch the subjects folder listing and record name -> id, sizes."""
    budget = _budget()
    page = drivemeta.read_text(drivemeta.folder_url(FOLDER_SUBJECTS), budget)
    entries = drivemeta.parse_listing(page)

    DERIVED.mkdir(parents=True, exist_ok=True)
    index = {
        "source_url": drivemeta.folder_url(FOLDER_SUBJECTS),
        "listing_bytes": len(page),
        "entry_count": len(entries),
        "entries": [
            {
                "name": e.name,
                "file_id": e.file_id,
                "is_folder": e.is_folder,
                "size_text": e.size_text,
            }
            for e in entries
        ],
    }
    (DERIVED / "kafe_subjects_index.json").write_text(
        json.dumps(index, indent=2) + "\n"
    )
    print(f"parsed {len(entries)} entries from {len(page)} bytes of listing HTML")
    for name in SAMPLE_SUBJECTS:
        hit = next((e for e in entries if e.name == name), None)
        print(f"  {name}: {hit}")
    return 0


def cmd_labels() -> int:
    """Fetch the two small label/reference artifacts."""
    budget = _budget()
    records = _load_records()
    have = {r["path"] for r in records}

    targets = [
        (
            drivemeta.download_url(FILE_SUPPLEMENTARY),
            "kafe_supplementary_appendix.pdf",
        ),
        (SHEET_CSV_URL, "kafe_results_to_reproduce.csv"),
    ]
    for url, name in targets:
        if name in have:
            print(f"skip {name}: already fetched")
            continue
        record = drivemeta.fetch(url, ARTIFACTS / name, budget)
        records.append(record)
        _save(records)
        print(f"fetched {name}: {record['bytes']} B sha256={record['sha256'][:16]}")

    print(f"budget used {budget.used} / {budget.limit} B")
    return 0


def cmd_subjects() -> int:
    """Fetch exactly the three authorized sample subjects."""
    index_path = DERIVED / "kafe_subjects_index.json"
    if not index_path.exists():
        print("run `list` first", file=sys.stderr)
        return 1
    entries = json.loads(index_path.read_text())["entries"]
    by_name = {e["name"]: e for e in entries}

    budget = _budget()
    records = _load_records()
    have = {r["path"] for r in records}

    for name in SAMPLE_SUBJECTS:
        entry = by_name.get(name)
        if entry is None:
            print(f"MISSING from listing: {name}", file=sys.stderr)
            continue
        if entry["is_folder"]:
            print(f"SKIP {name}: stored as a folder, not a single file")
            continue
        dest_name = f"subject_{name}.bin"
        if dest_name in have:
            print(f"skip {dest_name}: already fetched")
            continue
        record = drivemeta.fetch(
            drivemeta.download_url(entry["file_id"]), ARTIFACTS / dest_name, budget
        )
        record["subject"] = name
        record["reported_size_text"] = entry["size_text"]
        records.append(record)
        _save(records)
        print(f"fetched {dest_name}: {record['bytes']} B sha256={record['sha256'][:16]}")

    print(f"budget used {budget.used} / {budget.limit} B")
    return 0


COMMANDS = {"list": cmd_list, "labels": cmd_labels, "subjects": cmd_subjects}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: {sys.argv[0]} {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(COMMANDS[sys.argv[1]]())
