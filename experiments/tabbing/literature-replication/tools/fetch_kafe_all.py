"""Resolve and fetch all 60 KAFE subjects (arm 3).

Why this exists alongside `fetch_kafe.py`: that module's `list` command parses
the *rendered* Drive folder page, which paginates at 50 items and silently lost
ten subjects (`tinyurl` .. `wiktionary`). Drive's `embeddedfolderview` endpoint
returns all 60 entries in one 44 KB response with no pagination, so it is the
listing this uses.

Licence status, unchanged and load-bearing: no licence or terms statement
accompanies these captures, and they are copies of third-party commercial sites
the KAFE authors do not own. The paper carries only ACM's author-retained
notice, which covers the paper and not the subject bytes. Harry authorized a
local, git-ignored, non-redistributed download for inspection. Everything here
therefore writes under `artifacts/`, which this experiment's `.gitignore`
excludes. Do not commit, publish, or redistribute any fetched byte.

Usage:
    uv run --offline --no-sync python -m tools.fetch_kafe_all resolve
    uv run --offline --no-sync python -m tools.fetch_kafe_all fetch
"""

from __future__ import annotations

import html as html_mod
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from tools import drivemeta

HERE = Path(__file__).resolve().parent.parent
ARTIFACTS = HERE / "artifacts"
SUBJECTS_DIR = ARTIFACTS / "subjects"
DERIVED = HERE / "derived"

FOLDER_SUBJECTS = "1pU6osxQUgAH6EfZ93sMcG9LPxgwstUYS"
EMBED_URL = f"https://drive.google.com/embeddedfolderview?id={FOLDER_SUBJECTS}#list"

# The three already fetched under the earlier authorization keep their original
# paths; re-downloading them would spend budget for bytes already on disk.
ALREADY = {"citiprogram", "craigslist", "coronavirus"}

CAP_BYTES = 150 * 1024 * 1024
INDEX_PATH = DERIVED / "kafe_subjects_index_full.json"


def _open(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(request, timeout=180)


def parse_embedded(page: str) -> list[dict[str, object]]:
    """One record per folder entry, from the non-paginating embedded view.

    Entries are split on the container div rather than matched with a nested
    regex: the title sits inside a child div, so a greedy nested pattern
    captures the id but loses the name.
    """
    out: list[dict[str, object]] = []
    for block in page.split('<div class="flip-entry"')[1:]:
        fid = re.search(r'id="entry-([^"]+)"', block)
        title = re.search(r'flip-entry-title">([^<]+)<', block)
        if not (fid and title):
            continue
        head = block[: block.find("flip-entry-title")].lower()
        out.append(
            {
                "name": html_mod.unescape(title.group(1)).strip(),
                "file_id": fid.group(1),
                "is_folder": "folder" in head,
            }
        )
    return out


def cmd_resolve() -> int:
    with _open(EMBED_URL) as response:
        page = response.read().decode("utf-8", "replace")
    entries = parse_embedded(page)

    names = [e["name"] for e in entries]
    if len(set(names)) != len(names):
        print("duplicate names in listing; refusing", file=sys.stderr)
        return 1

    DERIVED.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(
            {
                "source_url": EMBED_URL,
                "listing_bytes": len(page),
                "entry_count": len(entries),
                "entries": entries,
            },
            indent=2,
        )
        + "\n"
    )
    folders = [e["name"] for e in entries if e["is_folder"]]
    print(f"resolved {len(entries)} entries ({len(folders)} folder-form: {folders})")
    return 0


def cmd_fetch() -> int:
    if not INDEX_PATH.exists():
        print("run `resolve` first", file=sys.stderr)
        return 1
    entries = json.loads(INDEX_PATH.read_text())["entries"]

    manifest = ARTIFACTS / "MANIFEST-full.json"
    records = json.loads(manifest.read_text())["artifacts"] if manifest.exists() else []
    have = {r.get("subject") for r in records}

    prior = ARTIFACTS / "MANIFEST.json"
    used = (
        sum(int(r["bytes"]) for r in json.loads(prior.read_text())["artifacts"])
        if prior.exists()
        else 0
    )
    budget = drivemeta.ByteBudget(limit=CAP_BYTES, used=used + sum(int(r["bytes"]) for r in records))
    SUBJECTS_DIR.mkdir(parents=True, exist_ok=True)

    todo = [e for e in entries if e["name"] not in ALREADY and e["name"] not in have]
    print(f"{len(todo)} subjects to fetch; budget {budget.used} / {budget.limit} B")

    for i, entry in enumerate(todo, 1):
        name = entry["name"]
        if entry["is_folder"]:
            # Five subjects are stored expanded. Their inner files need a
            # separate listing pass; record the gap rather than guessing.
            records.append({"subject": name, "skipped": "folder-form", "bytes": 0})
            drivemeta.write_manifest(manifest, records)
            print(f"[{i}/{len(todo)}] SKIP {name}: stored as a folder")
            continue
        dest = SUBJECTS_DIR / f"{name}.bin"
        try:
            record = drivemeta.fetch(
                drivemeta.download_url(entry["file_id"]), dest, budget
            )
        except drivemeta.BudgetExceeded as exc:
            print(f"STOP at {name}: {exc}", file=sys.stderr)
            break
        except Exception as exc:  # network/Drive failure: record, keep going
            records.append({"subject": name, "error": str(exc)[:200], "bytes": 0})
            drivemeta.write_manifest(manifest, records)
            print(f"[{i}/{len(todo)}] FAIL {name}: {exc}")
            continue
        record["subject"] = name
        records.append(record)
        drivemeta.write_manifest(manifest, records)
        print(
            f"[{i}/{len(todo)}] {name}: {record['bytes']:,} B "
            f"sha256={record['sha256'][:16]} (used {budget.used:,})"
        )
        time.sleep(0.5)  # a courtesy gap, not a rate limit we were given

    print(f"done; budget used {budget.used:,} / {budget.limit:,} B")
    return 0


COMMANDS = {"resolve": cmd_resolve, "fetch": cmd_fetch}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: {sys.argv[0]} {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(COMMANDS[sys.argv[1]]())
