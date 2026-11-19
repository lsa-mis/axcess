# The Word and PowerPoint check: research and decisions

Research for the document check's Word (.docx) and PowerPoint (.pptx)
check, 2026-11-17 and 18. Code: `src/audit/linked_files/office_check.py`;
how files reach it: `docs/internal/document-check.md`. The labelled real
files and their scorer: `tests/real_pages/office_files.json`,
`tests/real_pages/test_office_real_files.py`.

## The question

Use an existing accessibility checker for Word and PowerPoint files, or
write our own rules on python-docx and python-pptx (already approved
dependencies)? The developer's conditions: compare rule coverage with
Microsoft's Accessibility Checker, licence, maintenance, code quality and
false alarms on real U-M files (measured, not guessed), and how it fits
Axcess (pure Python, in process, no new heavy dependency; a new package
needs the developer's approval).

## The candidates (read 2026-11-17)

| | panocheck | pptx-accessibility-scanner | office-accessibility-checker | accessibility-pass | LibreOffice Accessibility Check |
|---|---|---|---|---|---|
| Where | github.com/msu/panocheck | github.com/jdmiller/pptx-accessibility-scanner | github.com/rlorenzo/office-accessibility-checker | "microsoft/accessibility-pass" | LibreOffice, Tools > Accessibility Check |
| Licence | 0BSD | MIT | MIT | not found | MPL 2.0 |
| Maintenance | created 2026-10-30; 10 commits, all that day; no release; 0 stars; not on PyPI (installed from git) | 5 commits, 2026-10-20 to 22; no release; 0 stars | 24 commits, 2026-05-06 to 12; 1 release (PowerShell Gallery); 0 stars | GitHub answers 404 for that name, and a repository search found nothing like it | maintained with LibreOffice |
| Formats | HTML, DOCX, PPTX, XLSX, PDF | PPTX only | DOCX, XLSX, PPTX | – | Writer, Impress (in the program) |
| Runtime | one Python file; lxml for Office, html5lib, pikepdf and PyMuPDF (AGPL-3.0) for PDF; uses `subprocess` for LibreOffice conversion and `urllib.request` | Python CLI; imports python-pptx, Pillow, pytesseract, tqdm, boto3, pdf2image, an Ollama client; LibreOffice and Poppler for screenshots | PowerShell 7 and Microsoft's .NET Open XML SDK, downloaded by its setup script | – | the whole office suite; we found no documented command-line mode for the check (not installed here, not run) |
| Fits Axcess in process, no new dependency? | Office part needs only lxml, but the file brings PDF, HTML, LibreOffice and network code with it | No: tqdm is not installed, and it is a report-writing CLI | No: not Python | – | No |

Rule coverage against Microsoft's "Rules for the Accessibility Checker"
(https://support.microsoft.com/en-us/office/rules-for-the-accessibility-checker-651e08f2-0fc3-4e10-aaca-74b4a67101c1):

| Microsoft rule (category) | panocheck | jdmiller | rlorenzo | Axcess |
|---|---|---|---|---|
| All non-text content has alt text (Error) | Word: every `wp:docPr` without `descr`, text boxes included; VML pictures not read; PowerPoint: pictures only | pictures | every drawing, by `descr` or `title` | pictures, charts, diagrams, VML pictures; text boxes and plain shapes left out |
| Decorative mark honoured | yes (extension element) | yes | reads `@decorative` as an attribute of `docPr`, but Office writes it as an `adec:decorative` element, so marked images are reported (`Test-AltTextAttribute`, check-docx-accessibility.ps1) | yes |
| Tables specify column header information (Error) | Word: first row's `w:tblHeader` element, its value ignored (`w:val="0"` counts as a header); PowerPoint: `firstRow` | `firstRow` | Word: `w:tblHeader` only, `tblLook` refused on purpose | Word: Microsoft's own "Header Row" option (`tblLook firstRow`) or "Repeat as header row" with its value read; PowerPoint: `firstRow` |
| All slides have titles (Error) | yes | yes | yes | yes |
| Document access is not restricted (Error) | – | – | yes | an encrypted or rights-managed file reads "needs a password" |
| All content control fields have titles (Error) | – | – | yes | not checked |
| Sections have meaningful names (Error) | – | – | – | not checked |
| Table has a simple structure, contrast, captions, reading order (Warnings) | contrast, a reading-order guess | contrast, reading-order guess | merged cells, contrast | not checked (see office_check.py) |
| Documents use heading styles (Tip) | yes, plus first heading level 1 and skipped levels | a deck-level heading check | yes, plus skipped levels | long documents without headings; skipped levels as a possible problem |
| Link text, language, document title (not Microsoft rules) | generic words and `http…` only; language from the style defaults only; title | yes | link text | web addresses with or without `https://`, generic words; language anywhere in the file; title from the file's own properties (python-docx invents "Word Document" for a file without them, as every Google export is) |

## Measured on the labelled real files

We could not run the other tools' code here: the environment's safety
policy refused running the downloaded panocheck copy (twice), and we did
not work around it. Instead, their Word alt text and table header rules
were written out again from their source code (panocheck at commit
7a64612, rlorenzo's `check-docx-accessibility.ps1`) and scored on the same
67 labelled Word files as our check. This is an emulation of their rules as
we read them, not a run of their code.

| On 67 labelled Word files | Images without alt text: right, false alarms, missed | Tables without a header row: right, false alarms, missed |
|---|---|---|
| panocheck's rules, re-stated | 11, 16, 1 | 1, 20, 8 |
| rlorenzo's rules, re-stated | 11, 16, 1 | 9, 24, 0 |
| Axcess | 12, 0, 0 | 9, 5, 0 |

Their alt text false alarms are mostly text boxes (Word gives a text box a
`docPr` too); their table false alarms come from reading
`<w:tblHeader w:val="0"/>`, which Google's exports put on every row, as a
header (panocheck), or from refusing Microsoft's own Header Row option
(rlorenzo). Our 5 table false alarms are layout tables (see below).

## Decision (2026-11-17)

**Our own rules on python-docx and python-pptx.** Reasons:

1. None of the candidates is mature: all are weeks or months old, with no
   users we could see and at most one release.
2. None fits in process without new dependencies or code Axcess does not
   want (PDF libraries under AGPL, LibreOffice, subprocesses, network
   calls, PowerShell and .NET).
3. Their rules disagree with Microsoft's own instructions or with the files
   real sites publish (the decorative mark, `w:tblHeader w:val="0"`,
   Header Row), and those disagreements are most of their false alarms on
   our labelled files.
4. Our rules are a few hundred lines on libraries already approved, read
   only what the file states, and are measured on real files here.

## The rules

Which rule makes a file "Mostly sure" follows the developer's rule
(2026-11-17): only rules that are machine-checkable and affect a screen
reader user. The rest are "possible problems" a person must judge.

| Check | Word | PowerPoint | Mostly sure? | Basis |
|---|---|---|---|---|
| Images without alt text | yes | yes | yes | Microsoft Error; WCAG 1.1.1 |
| Tables without a header row (plain grids of 2+ rows, 2+ columns, since 2026-11-19; see "Why precision was low") | yes | yes | yes | Microsoft Error; WCAG 1.3.1, F91. Made a possible problem on 2026-11-18 and counted again on 2026-11-19 (migrations 0046, 0047): as a possible problem it missed every file whose only barrier was an unmarked data table (holdout recall 100% to 91.3%, tuning 100% to 66.7%) and removed no wrong verdict, since each layout-table file was already Mostly sure for another real barrier. The cost kept: a layout table can show "Problem found" on its row |
| Slides without a title | – | yes | yes | Microsoft Error; WCAG 2.4.6 |
| No headings (Word: until 2026-11-19 over 400 words; since then 2+ visual headings) | yes | – | yes | Microsoft Tip; WCAG 1.3.1, F2 |
| No language set | yes | yes | yes | WCAG 3.1.1 (as the PDF check) |
| Heading levels skipped | yes | – | possible problem | Microsoft guidance |
| Links that do not say where they go | yes | yes | possible problem | Microsoft guidance; WCAG 2.4.4 lets context give the purpose |
| No document title | yes | yes | possible problem; not checked for Google Docs and Slides (since 2026-11-18) | Word and PowerPoint show the file name; Google exports never have a title, and the author cannot set one |

Not checked: reading order (Microsoft lists it as a Warning for a person;
shape order alone says nothing about sense), contrast, merged cells,
content control titles, alt text quality.

## The labelled set

73 distinct files (by SHA-256), all linked from the approved U-M sites:

| Source | Word | PowerPoint |
|---|---|---|
| hr.umich.edu (.docx, .pptx) | 19 | 1 |
| finance.umich.edu (.docx) | 11 | – |
| Google Docs and Slides exports linked from rossweb (ross-it), hr, its, lsa | 37 | 5 |

Not in the set: files over 10 MB (three hr.umich.edu decks), Google files
that need a sign-in (HTTP 401) or were deleted (410), Drive files (Google's
robots.txt asks scanners not to download them), and old .doc/.ppt files.

**Labelling.** Agents separate from the check's author labelled each file
from its XML (and viewed its pictures where a verdict needed it), without
access to the check's code: 46 Word files on 2026-11-17 before any rule
was written, 21 more Word files after the Word rules existed but without
seeing them, and the 6 PowerPoint files on 2026-11-18 before any
PowerPoint rule was written. A second agent re-read every Word table after
the first misread `<w:tblHeader w:val="0"/>` as a header; 7 labels changed
from pass to fail (recorded per file under `relabelled`). No file was
opened in Word, PowerPoint or a screen reader, and no outside source
labelled these files: this is evidence, not expert validation.

The protocol, per file: `alt_text` (a picture, chart, diagram or video
with no alt text and not marked decorative; a file name or default object
name counts as none; text boxes, plain shapes, slide masters and Word
headers and footers left out), `table_header` (a DATA table, not a layout
table, with no header row marked; a property set to "0" is off),
`slide_title`, `language` (none anywhere), `headings` (visible section
headings but no heading style), `heading_order`, `link_text` (a web
address or a phrase such as "click here"; an email address is fine),
`title`, and `barrier` (any of the first five fails).

**Split.** Fixed before labelling, not by the labels: a file is in the
holdout part when its SHA-256 starts with 0 to 7. The Word rules were
tuned on the tuning part only (28 Word files); all 6 PowerPoint files fell
in the holdout part, so the PowerPoint rules had no real-file tuning.

**Google exports change.** Google renames pictures and relationship IDs in
every export, so one Doc's bytes differ each time. The scorer compares a
content key for Google files. The labelled bytes were lost with a cleared
scratch directory before the keys were taken, so the keys come from a new
export a day later: that the 37 Google Docs did not change in that day is
assumed, not verified.

## Results (2026-11-18, the code at the commit that adds this file)

File level, "Mostly sure" against `barrier`:

| Part | Files | Barriers | Right | False alarms | Missed | Precision | Recall |
|---|---|---|---|---|---|---|---|
| Holdout | 45 (39 Word, 6 PowerPoint) | 25 | 25 | 1 | 0 | 96.2% (upper 95% bound on false alarms 15.5%) | 100% (upper 95% bound on misses 11.3%) |
| Tuning | 28 Word | 13 | 13 | 0 | 0 | 100% | 100% |

PowerPoint alone (all holdout): 6 files, 4 barriers, 4 found, no false
alarm. Too few files to say anything general about PowerPoint.

Per check on the holdout part (right, false alarms, missed): images
without alt text 11, 0, 0; tables without a header row 4, 4, 0; slides
without a title 3, 0, 0; no language 1, 0, 0; no headings 11, 1, 1;
skipped heading levels 3, 0, 0; link text 11, 0, 1; no title 37, 0, 0.

The errors:

- **Tables, 4 false alarms**: four Math department course lists (Google
  Docs, one template), each 34 to 39 two- or three-row tables, one per
  course, with no row of column names. The labeller judged them layout
  tables; read as data tables, they fail too. A machine cannot tell a
  layout table from a data table by structure alone. The four files are
  barriers anyway (no headings), so the file-level result is right.
- **No headings, 1 false alarm**: a 442-word, one-part payroll form; the
  400-word threshold flags it. This is the file-level false alarm.
- **No headings, 1 missed**: a 421-word two-part application form the
  labeller failed; the check counted fewer than 400 words in its body.
- **Link text, 1 missed**: a link whose text is "Topic", not on the list
  of vague phrases.

On the tuning part the only error is one layout table flagged (a form's
grid), in a file that is a barrier anyway.

## More files: government and non-profit sites (2026-11-18 and 19)

To measure the check on files no rule was tuned on, 77 more files (by
SHA-256) were added, all to the holdout part, with the rules as they
stood at ed3d59d (tables without a header row counted). No rule was
changed after scoring them. Each is marked `"source":
"gov-org-2026-11-18"` in `office_files.json`.

| Linked from | Word | PowerPoint | Barriers |
|---|---|---|---|
| www.section508.gov (presentations, IAAF 2023 and 2024, Accessible Presentations) | 16 | 38 | 4 |
| grants.nih.gov forms directory and protocol templates (2 hosted on osp.od.nih.gov) | 16 | – | 1 |
| www.cdc.gov, stacks.cdc.gov | – | 4 | 2 |
| www.aaal.org (file hosted on assets.noviams.com), isaac-online.org | – | 2 | 2 |
| accessible.org | 1 | – | 0 |
| **Total** | **33** | **44** | **9** |

How they were found: pages read one at a time, at most one request a
second, robots.txt obeyed, read only. Not in the set: 4 section508.gov
decks over 10 MB, a Dropbox file (Dropbox's robots.txt disallows it), old
.doc files, and sites that answered with HTTP 403 (sites.ed.gov,
printdisability.org, oercommons.org).

Labelling: 7 agents, the same protocol as above (written out in full for
them, Word and PowerPoint together), without access to the check's code,
before the check was run on these files. No file was opened in Word,
PowerPoint or a screen reader; no outside audit exists for any of them.
No criterion was left disputed.

### Results with the new files (rules at ed3d59d)

File level, "Mostly sure" against `barrier`:

| Part | Files scored | Barriers | Right | False alarms | Missed | Precision | Recall |
|---|---|---|---|---|---|---|---|
| Holdout, U-M files | 41 of 45 (4 Google files changed) | 23 | 23 | 1 | 0 | 95.8% (upper 95% bound on false alarms 16.7%) | 100% (upper 95% bound on misses 12.2%) |
| Holdout, new files | 77 | 9 | 8 | 12 | 1 | 40.0% (bound 75.8%) | 88.9% (bound 37.7%) |
| Holdout, all | 118 of 122 | 32 | 31 | 13 | 1 | **70.5%** (bound 41.8%) | **96.9%** (bound 12.9%) |
| Tuning | 27 of 28 (1 changed) | 12 | 12 | 0 | 0 | 100% | 100% |
| New Word files | 33 | 3 | 2 | 12 | 1 | 14.3% | 66.7% |
| New PowerPoint files | 44 | 6 | 6 | 0 | 0 | 100% (bound 39.3%) | 100% (bound 39.3%) |
| All PowerPoint | 46 of 50 | 8 | 8 | 0 | 0 | 100% (bound 31.2%) | 100% (bound 31.2%) |

Holdout precision is below the 90% the developer asked for; recall is
above it. Every false alarm is in a Word file.

Per check on the new files (right, false alarms, missed): images without
alt text 6, 0, 1; tables without a header row 1, 2, 0; slides without a
title 1, 0, 0; no headings 0, 10, 0; skipped heading levels 2, 0, 0; link
text 35, 0, 1; no title 10, 0, 0.

The errors on the new files:

- **No headings, 10 false alarms**: six section508.gov meeting
  transcripts (12,000 to 17,000 words, one part, a Title line and speaker
  turns) and four one-part NIH forms (520 to 1,400 words: a Title line,
  then numbered questions or statements). The labellers found no visible
  section headings in them, so nothing is lost to a screen reader user;
  the check flags any document over 400 words with no heading style. Two
  more transcripts were not flagged only because their author put
  Heading 1 on the "--- BEGIN CAPTIONED TEXT ---" line.
- **Tables, 2 false alarms**: two NIH forms (HHS 568, PHS 416-7) laid out
  as one large table, with a small fill-in grid with column names inside
  (inventions; stipend years). The labellers called them form layout
  tables and said the inner grids could be read as data tables.
- **Images, 1 missed** (the file-level miss): section508.gov's PowerPoint
  2016 authoring guide gives 12 informative screenshots the alt text `"  "`
  (two quote marks around spaces), a way of marking a picture decorative
  that the guide itself teaches. The check counts any text as alt text;
  the labeller counted this as none, since the pictures are not
  decorative.
- **Link text, 1 missed**: links whose words are "video" and "short
  video".

What this suggests (not changed; for the developer to decide, and to be
measured on files not yet seen, since these are now seen):

- "No headings" needs a sign of visible headings (for example short,
  bold or larger lines that start a part), not a word count alone. Simply
  not counting it is worse: holdout recall falls to 78.1% (25 of 32) and
  tuning recall to 58.3%, while holdout precision is 92.6%.
- Alt text made only of spaces and punctuation could count as none.

### Two real scans (2026-11-19)

Fresh databases, New scan's public defaults:

- `https://www.section508.gov/training/presentations-workshops/`, 10-page
  limit: 1 page in scope, 35 documents. 3 PowerPoint files were checked,
  all "Not sure", each matching its label (one with a possible link text
  problem, labelled as such). 2 decks were over 10 MB. 28 of the other
  30 timed out: after the first 4 downloads (done in 3 seconds), every
  download waited the full 30 s, four at a time, including 50 KB Word
  files that the labelling downloads (one at a time) fetched at once. Why
  was not found: the site slowing parallel downloads and a fault in the
  scan's own downloader are both possible.
- `https://grants.nih.gov/grants-process/write-application/forms-directory`,
  15-page limit: 17 pages, 24 documents, 11 Word files checked, no
  timeouts. Against the labels: the Chimpanzee research form ("Not sure",
  no title as a possible problem), PHS 6031-1 ("Not sure", heading levels
  and link text as possible problems) and SF424 additional locations
  ("Not sure") are right; the 2026 data management plan page is "Mostly
  sure" for no headings and HHS 568 for a table without a header row,
  both false alarms by the labels (see the errors above).

## Why precision was low (2026-11-19)

All 13 holdout false alarms at be31ee8 were Word files: 11 from "No
headings" and 6 from "Tables without a header row" (some files had both).
Each rule fired on a fact that does not decide whether a reader meets the
barrier. WCAG 1.3.1 (Info and Relationships, Level A) fails when structure
a reader can see is not in the markup; neither rule looked at what a
reader sees.

**No headings.** The rule failed any Word document over 400 words with no
heading style. Length says nothing: the 11 false alarms ran from 442 to
16,573 words, the 17 real failures from 421 to 7,255. What separates them
is whether the document shows headings at all. Counting "visual headings"
(a line of at most 12 words, at least 80% bold, underlined, in capitals or
2 points larger than the body text, starting with a letter, digit or "(",
followed by at least 20 words before the next such line) on every
development Word file with no heading style:

| Label | Visual headings found |
|---|---|
| Fail (17 files) | 3 to 39 (3: two short forms of 421 and 462 words) |
| Pass, false alarm before (11 files) | 1 each: the transcripts' and forms' Title line |
| Pass, other (15 files) | 0 or 1 |

The six section508.gov transcripts are a Title line, a "--- BEGIN
CAPTIONED TEXT ---" marker and plain speaker turns; the four NIH forms are
a Title line and numbered questions in body text. The transcripts'
marker and one transcript's "[LAUGHTER]" lines are in capitals, which is
why a line must start with a letter, digit or "(". A policy whose
sections are only underlined (2fb0c01f2fb2) shows 4, and the 421-word
form the old rule missed by its word count (0e1588d7eae2) shows 3.

**Tables.** The rule failed any table of 2+ rows and 2+ columns without a
header row. Every table false alarm was a layout or form table with merged
cells: the four Math course lists (a second row merged across all three
columns, one course per table), a gift form's 12-by-2 grid (11 merged
cells), and NIH's HHS 568 and PHS 416-7, each one table holding the whole
form (64 and 95 merged cells). Every file with an unmarked data table had
at least one plain grid: every row the same number of cells, none merged
(budgets, contact lists, plan comparisons, Canvas feature tables). Merged
cells are how Word builds a form or a layout; Microsoft's checker warns
about them in any table ("Tables have a simple structure", paraphrased),
and a layout table must not get a header row (WCAG failure F46).

**Alt text.** The one missed barrier: section508.gov's PowerPoint guide
gives 12 screenshots the alt text `"  "`. Alt text with no letter or digit
gives a screen reader nothing to say (WCAG 1.1.1).

## The rules since 2026-11-19 (commit 946ad6f)

| Rule | Before | Now | Basis |
|---|---|---|---|
| No headings (Word) | no heading style and more than 400 words | no heading style and at least 2 visual headings (defined above), any length | WCAG 1.3.1, failure F2: a change in how text looks used to show structure without the markup |
| Tables without a header row | any table of 2+ rows and 2+ columns | only a plain grid: same number of cells in every row, no cell merged across rows or columns, no table inside it; others are left to a person | WCAG 1.3.1, F91 (data table headers not marked), F46 (layout tables get no headers); Microsoft "Tables have a simple structure" (paraphrased) |
| Images without alt text | alt text empty, a file name or a default name | also: alt text with no letter or digit (spaces, quote marks, dashes) | WCAG 1.1.1 |

PowerPoint tables follow the same plain-grid rule (`gridSpan`, `rowSpan`,
`hMerge`, `vMerge`). No PowerPoint score changed on the development set,
and the fresh set has no PowerPoint files, so that part is not validated.

These rules were chosen looking at all 150 labelled files, so those files
are now the **development set**, not a test: every number on them below is
how well the rules fit what they were made from.

## Fresh validation set (2026-11-19)

57 Word files no rule had seen (24 .gov and .org sites, none used before:
federal agencies, state departments, counties, a school district and
non-profits; `split: "fresh"` in `office_files.json`, sources in
`office_files.py`). Order of work: files collected by source and type
only; four labelling agents labelled them without the check's code; the
labels were frozen (10:16) before the rules were committed (946ad6f,
10:23) and before the check first ran on them (10:24). No rule was changed
after. One file is disputed (a school policy whose section names are bold
words starting their paragraphs) and not scored; one (a dol.gov guide) is
a damaged ZIP as served (bad CRC on a picture), which the check, like the
app, reads as "damaged"; it is a barrier by its label, so counted as a
miss, recall would be 18 of 21 (85.7%).

### Scores

File level, "Mostly sure" against `barrier`, with the one-sided 95% upper
bounds on false alarms among "Mostly sure" files and on missed barriers:

| Set | Rules | Files scored | Barriers | Right | False alarms | Missed | Precision (false alarms at most) | Recall (misses at most) |
|---|---|---|---|---|---|---|---|---|
| Development | be31ee8 | 145 | 44 | 43 | 13 | 1 | 76.8% (33.6%) | 97.7% (9.6%) |
| Development | 946ad6f | 145 | 44 | 44 | 0 | 0 | 100% (6.6%) | 100% (6.6%) |
| Fresh | be31ee8 | 55 | 20 | 18 | 6 | 2 | 75.0% (41.5%) | 90.0% (26.2%) |
| Fresh | 946ad6f | 55 | 20 | 18 | 4 | 2 | **81.8%** (34.9%) | **90.0%** (26.2%) |

**The goal, precision and recall both above 90% on files the rules were
not made on, is not met**: fresh precision 81.8%, recall exactly 90.0%.
The new rules remove two of the six fresh false alarms and miss nothing
the old rules found. The development score (100%) is fit, not evidence.

Per check on the fresh set (right, false alarms, missed), old then new:
no headings 9, 5, 2 then 9, 4, 2; tables without a header row 6, 5, 0
then 5, 0, 1; images without alt text 10, 0, 0 both. The table rule now
makes no false alarm on fresh files either (it had 5); all remaining
errors are "No headings".

### Why the fresh errors happen

| File | Error | Mechanism | Labeller |
|---|---|---|---|
| 6f0eb2e36703, garfieldar.gov forum minutes | false alarm | two thirds of the body text is bold, so bold lines do not stand out; the rule compares size with the body text but not bold | close call |
| d28372f96e20, dir.texas.gov fee schedule | false alarm | the column names of its data tables are in capitals ("PAYMENT CONVENIENCE FEES (Bankcard)") and its title is 24 pt: read as visual headings, though they sit in header rows that are marked | clear |
| edd7d5cddc9c, Wisconsin court form GF-223 | false alarm | a form laid out in tables: bold caption lines and a bold "See attached" read as headings | clear |
| ab47342fce67, utah.gov meeting minutes | false alarm | two bold lines ending in colons that introduce lists ("Immediate Action Items:") | close call |
| 5b3220a52069, county pension checklist (71 words) | missed | "Income", "Assets", "Expenses" are bold, underlined and larger, but each is followed by a list of 12 to 17 words, under the 20-word minimum | clear |
| a26b53665ba1, county incident report form (66 words) | missed | "WHEN:", "WHAT:" are bold capitals, but so are most field labels after them, so no line is followed by body text | close call |
| 1dad5be3d018, energy.gov template | table missed (file still found, for alt text) | an 8-by-10 data table without a header row has one merged cell | clear |

Three of the six file-level errors are close calls the labellers flagged
themselves. Fixes these suggest, not made (each was found on the fresh
files, so the fresh set can no longer test it): count bold, underline and
capitals as standing out only when most body text lacks them; do not read
lines in a table whose header row is marked as visual headings; a smaller
body-text minimum for very short documents (the risk is a form's bold
labels). Testing them needs another fresh set, collected and labelled the
same way before the rules change.

## Limits

- 207 files: 73 from one university's sites, 77 from government and
  non-profit sites, 57 fresh Word files from other .gov and .org sites;
  50 PowerPoint, all in the development set. The new files are mostly from
  accessibility teams (section508.gov) and have few barriers (9 of 77), so
  recall rests mostly on the U-M files. Small numbers: a 95% bound is
  given beside each rate.
- Labels are one agent's reading of the XML, reviewed only for the U-M
  Word tables.
- hr.umich.edu, finance.umich.edu, lsa.umich.edu and its.umich.edu began
  answering the scanner's HTTP client with a bot challenge (HTTP 403) on
  2026-11-18, so the scorer cannot download their files again until that
  changes; rossweb and Google still answer. On 2026-11-18 a real Axcess
  scan of hr.umich.edu (5-page limit, the scan's browser name set to
  Axcess's own) got through: 11 pages saved with HTTP 200 and their
  titles, and its linked files downloaded.

## Extra scan time (measured 2026-11-18)

The real app on a fresh database each run, `https://rossweb.bus.umich.edu/ross-it/`,
New scan's public defaults, a 25-page limit (32 pages saved: the limit
counts pages visited). "Off" runs the same code with Word, PowerPoint,
Docs and Slides left unchecked (`formats.CHECKED` cut back to PDF and Drive
in the launcher), which is how the documents branch behaves: its 42 Google
links read "google_file" and are never asked for. hr.umich.edu, the site
the PDF timing used, answered the scanner with a bot challenge that day.

| Run | Whole scan | Start to last page saved | Last document result before the last page | Files checked as Word |
|---|---|---|---|---|
| On 1 | 443 s | 442 s | 21 s before | 9 (+1 PDF) |
| Off 1 | 455 s | 454 s | 52 s before | 0 (1 PDF) |
| On 2 | 513 s | 510 s | 59 s before | 9 (+1 PDF) |
| Off 2 | over 590 s (stopped by our 10-minute limit while finishing after the last page) | 479 s | 29 s before | 0 (1 PDF) |

With the check on, the scan asks docs.google.com for 41 more files (9
public Doc exports, 32 that answer "needs a sign-in"), on Google's host, so
the site's own rate limit is not shared; reading a file takes a median of
5 ms (at most 0.2 s on the 73 labelled files). In every run the last
document was done 21 to 59 seconds before the last page, so the check
never kept a scan waiting. The page crawl, with the click-through check,
varies by more than the difference between on and off (442 to 510 s): the
runs show no measurable extra time, which is not the same as none.
