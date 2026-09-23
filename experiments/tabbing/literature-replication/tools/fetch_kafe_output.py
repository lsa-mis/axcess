"""Fetch KAFE's per-subject timing files from their `KAFE_output` Drive folder.

Why this exists: the results CSV's `Detection` column does not behave like a
per-subject detection time (it rises with run order, not with page size), so
the cost comparison is recomputed from KAFE's own per-subject logs instead.

Per subject this fetches exactly three files and nothing else:
`execTime.csv`, `execTimeDetection.csv` and `resultsSubjectStats.csv`.

Licence status, as for `fetch_kafe_all.py`: these are unlicensed third-party
files. Everything, including the Drive listing index, is written under
`artifacts/kafe_output/`, which this experiment's `.gitignore` excludes. Do not
commit, publish, or redistribute any fetched byte.

Listing uses Drive's non-paginating `embeddedfolderview` endpoint, parsed with
`fetch_kafe_all.parse_embedded`. A subject folder that does not hold a wanted
file at its top level is searched one level down; any other layout is recorded
as a gap, not guessed at.

Usage:
    uv run --offline --no-sync python -B tools/fetch_kafe_output.py resolve
    uv run --offline --no-sync python -B tools/fetch_kafe_output.py fetch
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from tools import drivemeta  # noqa: E402
from tools.fetch_kafe_all import _open, parse_embedded  # noqa: E402

FOLDER_KAFE_OUTPUT = "1hKV7KoaMA2Lsgzly9-3cwA-QTU4X-ZM4"
WANTED = ("execTime.csv", "execTimeDetection.csv", "resultsSubjectStats.csv")

OUT_DIR = HERE / "artifacts" / "kafe_output"
INDEX_PATH = OUT_DIR / "_index.json"
MANIFEST_PATH = OUT_DIR / "_manifest.json"

# Three small CSVs per subject; 20 MB is far above any plausible total and
# exists only to stop a mis-resolved id from pulling a capture archive.
CAP_BYTES = 20 * 1024 * 1024


def embed_url(folder_id: str) -> str:
    return f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"


def list_folder(folder_id: str) -> list[dict[str, object]]:
    with _open(embed_url(folder_id)) as response:
        page = response.read().decode("utf-8", "replace")
    return parse_embedded(page)


def cmd_resolve() -> int:
    top = list_folder(FOLDER_KAFE_OUTPUT)
    names = [e["name"] for e in top]
    if len(set(names)) != len(names):
        print("duplicate names in top listing; refusing", file=sys.stderr)
        return 1

    subjects: dict[str, dict[str, object]] = {}
    for i, entry in enumerate(top, 1):
        name = str(entry["name"])
        if not entry["is_folder"]:
            subjects[name] = {"folder_id": entry["file_id"], "gap": "not a folder"}
            print(f"[{i}/{len(top)}] {name}: not a folder")
            continue
        children = list_folder(str(entry["file_id"]))
        found = {
            str(c["name"]): str(c["file_id"])
            for c in children
            if not c["is_folder"] and c["name"] in WANTED
        }
        nested: list[str] = []
        if len(found) < len(WANTED):
            for child in children:
                if not child["is_folder"]:
                    continue
                for grand in list_folder(str(child["file_id"])):
                    gname = str(grand["name"])
                    if not grand["is_folder"] and gname in WANTED and gname not in found:
                        found[gname] = str(grand["file_id"])
                        nested.append(f"{child['name']}/{gname}")
                time.sleep(0.3)
        subjects[name] = {
            "folder_id": entry["file_id"],
            "files": found,
            "nested": nested,
            "children": [str(c["name"]) for c in children],
        }
        missing = [w for w in WANTED if w not in found]
        print(f"[{i}/{len(top)}] {name}: {len(found)}/3" + (f" missing {missing}" if missing else ""))
        time.sleep(0.3)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(
            {"source_url": embed_url(FOLDER_KAFE_OUTPUT), "subject_count": len(subjects), "subjects": subjects},
            indent=2,
        )
        + "\n"
    )
    print(f"resolved {len(subjects)} top-level entries")
    return 0


def cmd_fetch() -> int:
    if not INDEX_PATH.exists():
        print("run `resolve` first", file=sys.stderr)
        return 1
    subjects = json.loads(INDEX_PATH.read_text())["subjects"]

    records = json.loads(MANIFEST_PATH.read_text())["artifacts"] if MANIFEST_PATH.exists() else []
    have = {(r.get("subject"), r.get("file")) for r in records if "sha256" in r}
    budget = drivemeta.ByteBudget(limit=CAP_BYTES, used=sum(int(r["bytes"]) for r in records))

    todo = [
        (subject, fname, fid)
        for subject, meta in sorted(subjects.items())
        for fname, fid in sorted(meta.get("files", {}).items())
        if (subject, fname) not in have
    ]
    print(f"{len(todo)} files to fetch; budget {budget.used} / {budget.limit} B")

    for i, (subject, fname, fid) in enumerate(todo, 1):
        dest = OUT_DIR / subject / fname
        try:
            record = drivemeta.fetch(drivemeta.download_url(fid), dest, budget)
        except drivemeta.BudgetExceeded as exc:
            print(f"STOP at {subject}/{fname}: {exc}", file=sys.stderr)
            break
        except Exception as exc:  # network/Drive failure: record, keep going
            records = [r for r in records if (r.get("subject"), r.get("file")) != (subject, fname)]
            records.append({"subject": subject, "file": fname, "error": str(exc)[:200], "bytes": 0})
            drivemeta.write_manifest(MANIFEST_PATH, records)
            print(f"[{i}/{len(todo)}] FAIL {subject}/{fname}: {exc}")
            continue
        record.update({"subject": subject, "file": fname})
        records = [r for r in records if (r.get("subject"), r.get("file")) != (subject, fname)]
        records.append(record)
        drivemeta.write_manifest(MANIFEST_PATH, records)
        print(f"[{i}/{len(todo)}] {subject}/{fname}: {record['bytes']:,} B")
        time.sleep(0.3)  # a courtesy gap, not a rate limit we were given

    print(f"done; budget used {budget.used:,} / {budget.limit:,} B")
    return 0


COMMANDS = {"resolve": cmd_resolve, "fetch": cmd_fetch}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: {sys.argv[0]} {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(COMMANDS[sys.argv[1]]())
