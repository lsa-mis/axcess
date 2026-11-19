# Office check precision work: progress (resumable)

Task (the developer, 2026-11-19): find why the Word/PowerPoint check's
"Mostly sure" precision was low, change the rules so precision > 90% and
recall > 90%, proven on files the changes were not tuned on. Branch
`office-precision`, worktree
`/var/home/me/Development/axcess/.claude/worktrees/office-precision`
(branched from `documents` at be31ee8). No merge, no push.

Anyone resuming: read this file, then `git log --oneline be31ee8..HEAD`.

## Steps

| Step | State | Where |
|---|---|---|
| 1. Mechanism of the false alarms (development set) | done; written up in commit **65bb6a1** | `docs/internal/office-check-research.md`, "Why precision was low" and "Fresh validation set" |
| 2. Rule changes | done, one commit: **946ad6f** (no headings needs 2+ visual headings; table rule only for plain grids; alt text with no letter or digit is none) | `src/audit/linked_files/office_check.py`, `tests/unit/test_office_check.py`, `tests/support/office_docs.py` |
| 3. Development score | done: 145 of 150 scored, Mostly sure precision 100% (44/44), recall 100% (44/44). Old rules (be31ee8): 76.8% (43/56), 97.7% (43/44) | |
| 4a. Fresh files collected | done: 57 Word files, 24 sites | `artifacts/office-fresh/files/<sha256>.docx`; worklist `artifacts/office-fresh/collect/manifest.json` (URL, page, link text per SHA-256); skipped sources `collect/skipped.md`; downloader `collect/fetch.py` (skips known SHA-256) |
| 4b. Fresh files labelled | done: 4 batches (15, 14, 14, 14), all 57 labelled | `artifacts/office-fresh/label/batch_N.json`, labellers' work dirs `label/work_N/`, protocol `label/PROTOCOL.md` |
| 4c. Labels frozen | done 2026-11-19 10:16:23 -0500 (read-only copies and SHA-256 in `artifacts/office-fresh/frozen.sha256`), BEFORE the rules commit (10:23:44) and the first fresh score (10:24:46) | `artifacts/office-fresh/frozen/labels_N.json`, `manifest.json` |
| 4d. Fresh labels in the repo | done, commit **572a244** (`split: "fresh"` in `tests/real_pages/office_files.json`, built mechanically from the frozen files). Note: this commit is after the first score; the frozen copies' hashes and timestamps above are the proof that the labels predate it | |
| 4e. Fresh score | done, rules frozen at 946ad6f, not changed after | `artifacts/office-fresh/reports/new_rules_report.json`, `old_rules_report.json` |
| 5. Report wording | done, commit **c3072f3** (`terms.ts` LINKED_FILE_CHECK_WHY for no_alt_text, table_no_header, no_headings; `docs/glossary.md`); `docs/reading-your-report.md` needed no change; no UI test pins these sentences | |
| 6. Gates | done 2026-11-19: make lint, make typecheck, make frontend-build pass; tests/unit/test_office_check.py 55 passed; test_office_downloads.py and test_linked_file_checks.py pass. Failing, and failing before this work (not caused by it): tests/unit/test_office_report_rules.py::test_migrations_0046_then_0047_leave_table_barriers_mostly_sure (also fails with be31ee8's office_check.py), and 3 tests in tests/ui/test_documents_route.py that still expect a "Document title" check on a Google Slides deck, which 0fd0b9a removed without updating them | |

## Fresh results (rules frozen at 946ad6f)

Mostly sure: precision **81.8%** (18 of 22), recall **90.0%** (18 of 20); 56
of 57 scored (1 damaged as served), 1 disputed left out, 55 in the file
score. Old rules (be31ee8): 75.0% (18 of 24), 90.0% (18 of 20).
**Target (both above 90%) not met.** Errors, by file id: false alarms
6f0eb2e36703, ab47342fce67, d28372f96e20, edd7d5cddc9c (all "no
headings"); missed 5b3220a52069, a26b53665ba1 (both "no headings", short
documents). Mechanisms in the research doc.

## Rerun the scorer

```bash
cd /var/home/me/Development/axcess/.claude/worktrees/office-precision
AXCESS_REAL_PAGES=1 AXCESS_REAL_FILES_DIR=artifacts/office-real-files \
  env -u VIRTUAL_ENV uv run pytest tests/real_pages/test_office_real_files.py -q -s -p no:cacheprovider
```

`artifacts/office-real-files/` holds every labelled file (150 development
+ 57 fresh) as `<sha256>.<ext>`; the scorer writes
`office_real_files.json` there. Missing files are downloaded again from
the URLs in `office_files.json` (U-M sites answer 403 to the scorer since
2026-11-18, so keep that folder). Old rules on the same files:

```bash
env -u VIRTUAL_ENV uv run python artifacts/office-fresh/reports/old_rules.py \
  artifacts/office-fresh/reports/old_office_check.py artifacts/office-real-files /tmp/old.json
```

(`old_office_check.py` is `git show be31ee8:src/audit/linked_files/office_check.py`.)

## Where things live

- `artifacts/` is gitignored (`.gitignore` line 16): files and agents'
  notes are kept there, not committed. Every file's SHA-256 and URL are in
  `tests/real_pages/office_files.json`, so the set can be downloaded again.
- Scratch copy (may vanish): `/tmp/claude-1003/-var-home-me-Development-axcess--claude-worktrees-documents/07be128f-2331-40ee-b0f9-c857f7075117/scratchpad/prec/`.

## Next step

The brief is done; the target is not met on the fresh set. Waiting for the
developer's decision. If they want another round: make the fixes listed in
the research doc ("Why the fresh errors happen"), report the fresh set as
seen, and collect and label a second fresh set (other sites; same
protocol, `artifacts/office-fresh/label/PROTOCOL.md`; freeze labels and
commit them before scoring) to measure them. Separately, the two
pre-existing test failures in step 6 need fixing.
