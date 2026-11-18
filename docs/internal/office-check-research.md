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
| Tables without a header row (2+ rows, 2+ columns) | yes | yes | yes | Microsoft Error; WCAG 1.3.1 |
| Slides without a title | – | yes | yes | Microsoft Error; WCAG 2.4.6 |
| No headings (Word, over 400 words) | yes | – | yes | Microsoft Tip; WCAG 1.3.1 |
| No language set | yes | yes | yes | WCAG 3.1.1 (as the PDF check) |
| Heading levels skipped | yes | – | possible problem | Microsoft guidance |
| Links that do not say where they go | yes | yes | possible problem | Microsoft guidance; WCAG 2.4.4 lets context give the purpose |
| No document title | yes | yes | possible problem | Word and PowerPoint show the file name; Google exports never have a title |

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

## Limits

- 73 files from one university's sites, 6 of them PowerPoint; most
  barriers are images without alt text and long documents without
  headings. Small numbers: a 95% bound is given beside each rate.
- Labels are one agent's reading of the XML, reviewed only for tables.
- hr.umich.edu, finance.umich.edu, lsa.umich.edu and its.umich.edu began
  answering the scanner's HTTP client with a bot challenge (HTTP 403) on
  2026-11-18, so the scorer cannot download their files again until that
  changes; rossweb and Google still answer.
