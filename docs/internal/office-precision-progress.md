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

## Round 2 (the developer, 2026-11-19): evolved heading probe

Goal: Word "Mostly sure" precision > 90% and recall > 90% on files never
used for design or selection. Plan: a family of visual-heading probes,
an evolutionary search with cross-validation on the development data
(every Word file in office_files.json before fresh2: holdout, tuning,
fresh), freeze the winner in office_check.py, then score once on a second
fresh set ("fresh2").

| Step | State | Where |
|---|---|---|
| R1. fresh2 files collected | done 2026-11-19 by a collecting agent (by source and type only, files not opened): 74 Word files, 41 hosts, max 4 per host; none in office_files.json or the earlier artifacts (SHA-256 checked) | `artifacts/office-fresh2/files/<sha256>.docx`; worklist `collect/manifest.json`; skips `collect/skipped.md`; fetcher `collect/fetch.py` (exclusion list of earlier sites, known SHA-256 in `collect/known_sha256.txt`) |
| R2. fresh2 labelled | done: 5 labelling agents (batches `label/batch_N_files.json`, 15/15/15/15/14), cut off by a usage limit with 7 files unlabelled and one SHA-256 mistyped; a 6th agent (work_6) labelled the 7 and corrected the SHA (notes say so). 74 labelled: barrier 39 true, 33 false, 2 disputed | `artifacts/office-fresh2/label/batch_N.json`, protocol `label/PROTOCOL.md` |
| R3. fresh2 labels frozen | done 2026-11-20T08:21:03-05:00: read-only copies `artifacts/office-fresh2/frozen/labels_N.json` + `manifest.json`, hashes in `artifacts/office-fresh2/frozen.sha256` (labels_1 74dc0dc1..., labels_2 e7065c78..., labels_3 1338a9d6..., labels_4 4e2b097e..., labels_5 a9db829e..., manifest 43b6e841...) | |
| R4. fresh2 labels in the repo | done, commit **2f90223**: `split: "fresh2"` in `office_files.json`, built mechanically by `artifacts/office-fresh2/collect/build_entries.py` from the frozen copies; scorer reports "fresh2" | |
| R5. probe family + search | done 2026-11-20: 3 seeds x 60 generations x 150 probes, all three reach the same best (fitness 0.9746, CV mean min(P,R) 0.9826); nested CV (5 outer folds, 40 generations each) pooled P 94.7% (54/57), R 94.7% (54/57) vs 946ad6f on the same files 93.2%, 96.5% | `scripts/office_heading_search.py`; features of the 157 development Word files cached in `artifacts/office-search/features.json` (`... features`; `... check` confirms the base genome reproduces 946ad6f's no_headings on every file); checkpoints per generation in `artifacts/office-search/main/seed_N/gen_XXX.json` (resume: rerun the same command), logs `artifacts/office-search/search_seed_N.out`, nested CV in `artifacts/office-search/nested/fold_K/` and `nested/summary.json` |
| R6. freeze winner in office_check.py | done, commit **1256e02** (before R7): capitals no longer make a line stand out; 40 words under a heading, or 15% of the document's words if fewer; at least 3 visual headings. `... product` confirms office_check.py gives the frozen probe's verdict on all 155 scored development files. Unit tests: 6 cut-downs of the fresh-1 errors (5 fail on 946ad6f, pass now; the incident form is pinned as a known miss) | `src/audit/linked_files/office_check.py`, `tests/unit/test_office_check.py` (62 passed), `FROZEN` in the script |
| R7. score fresh2 once | done 2026-11-20 08:35 (after f55e523, a tooling-only commit): frozen probe P **88.2%** (30/34), R **76.9%** (30/39), 72 scored, 2 disputed. Target NOT met. For information: 946ad6f 80.0% / 92.3%; top 2 89.5% / 87.2%; top 3 85.4% / 89.7%; top 5 88.9% / 82.1%; top 1 87.1% / 69.2%; top 4 81.8% / 69.2%. Rule not changed after | `artifacts/office-fresh2/reports/frozen_probe_report.json`, `rules_946ad6f_report.json`; `artifacts/office-search/fresh2_probes.json`, `top5.txt` |
| R8. research doc "Second round: evolved heading probe" | done (this commit); glossary updated (3 headings, capitals alone do not count); terms.ts sentence still true, unchanged | `docs/internal/office-check-research.md`, `docs/glossary.md` |

## Round 3 (the developer, 2026-11-20): two tiers

Decision: counted ("Mostly sure") = no_alt_text, no_language,
slide_no_title. Possible problems = no_headings, table_no_header,
unclear_link_text, no_title, skipped_heading_level. no_headings becomes
the developer's simple rule: no heading style, and a bold line that is its
own paragraph and at most one sentence (replaces 1256e02's probe). Keep
946ad6f's plain-grid table rule and the "no letter or digit" alt rule.

| Step | State | Where |
|---|---|---|
| T1. Per-check scores on fresh and fresh2 at 354d04b | done | `docs/internal/office-check-research.md`, "Two tiers" |
| T2. Tiers in office_check.py (+ migration if stored statuses need it) | done: **68af8c2** (COUNTED, check order), **cd2f2a0** (migration **0049**, numbered past documents' 0048; renumber on merge if needed) | `src/audit/linked_files/office_check.py`, `src/audit/db/migrations/0049_office_two_tiers*.sql`, `tests/unit/test_office_report_rules.py` |
| T3. Bold-line heading rule + unit tests | done in **68af8c2** (`_word_bold_line`, `_sentences`); real cut-downs from 06f21a62fbbb, 0cf575d1dc40, 0e1588d7eae2, 3828c86e0f47, 1d10e2d9fe14; tests not yet run | `tests/unit/test_office_check.py` |
| T4. Score Mostly sure and every check, all sets | done: scorer rows `any_problem`, `any_barrier_check` (**a7fa2a9**); Mostly sure P 100% on all sets, R dev 50.0%, fresh 50.0%, fresh2 33.3% (by design); every fresh/fresh2 barrier file shown a problem | research doc, "Scores with the two tiers" |
| T5. Wording: Documents tab, document page, terms.ts, glossary, reading-your-report, tests | next | |
| T6. Gates | | |

## Next step (round 2, superseded by round 3)

Round 2 is done; the target is not met on fresh2. Waiting for the
developer: keep 1256e02's heading rule or go back to 946ad6f's (fresh2:
88.2%/76.9% vs 80.0%/92.3%). Open items: layout grids in court forms read
as data tables (3 of 4 fresh2 false alarms); alt text such as "sm_seal3"
(a file name without an extension); any further change needs a third
fresh set. The two older test failures (round 1, step 6) still stand.

(Round 1 note, kept:) The brief is done; the target is not met on the fresh set. Waiting for the
developer's decision. If they want another round: make the fixes listed in
the research doc ("Why the fresh errors happen"), report the fresh set as
seen, and collect and label a second fresh set (other sites; same
protocol, `artifacts/office-fresh/label/PROTOCOL.md`; freeze labels and
commit them before scoring) to measure them. Separately, the two
pre-existing test failures in step 6 need fixing.
