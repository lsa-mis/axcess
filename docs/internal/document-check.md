# The document check (linked files)

How the Documents tab's check finds files, decides which ones are the same,
and when it downloads and checks them. Since 2026-11-17 it checks Word
(.docx) and PowerPoint (.pptx) files and Google Docs and Slides as well as
PDFs (see "Word, PowerPoint, Google Docs and Slides" below; research and
measurements in `office-check-research.md`). Where this file says "PDF"
about downloading and timing, read "every file Axcess checks". Code: `src/audit/linked_files/`
(`tracker.py` is the part the crawl talks to), storage in
`src/audit/db/linked_files.py`, the report's view in
`src/audit/web/linked_files_queries.py`. In code these are "linked files",
because a crawler "document" is an HTML page.

## Identity: the link, then the hash for copies

- **The address is the identity.** Every address is normalized
  (`url_policy.normalize`) before it is stored, so `files/a.pdf`,
  `/files/a.pdf` and `https://site/files/a.pdf#page=2` are one file. The
  table keeps one row per address per scan (`UNIQUE (scan_id, url)`), and a
  file is downloaded at most once.
- **The hash spots copies.** After a download, the file's SHA-256 is stored
  (`linked_files.sha256`). When a PDF's bytes match a file already checked
  in the same scan, it gets that file's result without being read again
  (`store.checked_copy`), and the Documents tab says "Same file as …" on
  the later one (`same_as` in `LinkedFileRow`). Copies stay separate rows:
  each address is a link someone can fix or remove on its own.
- A hash cannot save a download: it needs the bytes. It saves reading the
  PDF again, and it tells the reader that one fix fixes both.
- Only a finished check (Mostly sure or Not sure) is reused. A copy of a
  file that timed out or failed is checked on its own.

## Timing: downloads run beside the crawl, never in front of it

**Rule: a page worker never waits for a document download.** The crawl
has `workers` page workers; the document check has its own downloads
(`DOWNLOAD_CONCURRENCY` at a time). After a page is read:

1. `record_page` stores the page's document links (fast, no network).
2. `queue_page` queues the PDFs this page reaches that are not checked
   yet, and returns at once. The page's worker goes on to the next
   page; the downloads work through the queued PDFs of earlier pages in the
   background.
3. After the last page, `check_pending` first waits for the queued
   downloads (`drain`), then checks anything still waiting (for example a
   file found by its Content-Type after its pages were recorded).
4. A stop or a failure cancels the queued downloads (`cancel_background`);
   the files not finished are reported as not checked.

**A document link is never a page.** The crawl does not queue a link whose
address names a document (`.pdf`, `.docx`, a Google file;
`formats.classify_url`, checked in `_enqueue_children`). So documents take
no slot of the page cap and no line in Pages visited (a 50-page cap means
50 web pages; the developer's decision, 2026-11-14), the site is asked for
each PDF once, by the document check, and with the document check off they
are not downloaded at all. An address with no extension that answers with a
file's Content-Type is still fetched by the crawl and recognised then
(`record_response`), and a file being read is awaited by a copy that
arrives at the same time, so the bytes are read once.

All downloads share the crawl's HTTP client, its per-host rate limit and its
robots.txt rules, and the scan-wide cap (`MAX_DOWNLOADS`, 200; each file at
most 10 MB). A PDF linked from many pages is downloaded once: a file being
checked for one page is awaited, not downloaded again, by another.

## Google Drive files

A link to a file kept in Google Drive (`drive.google.com/file/d/ID/...`) is
downloaded from Google's download address, the one Drive's own Download
button uses, with the button pressed in a browser as the fallback
(`linked_files/google.py`). It follows robots.txt like every other
download, and Google's robots.txt asks scanners not to download from that
host, so Drive files are checked only in a scan set to ignore robots.txt.
New scan says so beside the switch. A file shared only with signed-in
accounts reads "needs a sign-in (HTTP 401)". Research, the real pages it
was tested on, and the decisions: `docs/internal/google-files-research.md`.

## Word, PowerPoint, Google Docs and Slides

- **Which check reads a file is decided by its bytes**
  (`office_check.sniff`), not its address: a PDF goes to `pdf_check`, a
  Word or PowerPoint file to `office_check`, an Excel file is identified
  and waits for a check of its format, an encrypted Office file reads
  "needs a password", an old binary one "old format", anything else (a web
  page) "did not lead to a file Axcess can check" (`not_a_pdf`, worded by
  the link's type in the interface). The check that ran is stored in
  `linked_files.checked_as` (migration 0045; NULL on a checked row means a
  PDF, the only type checked before). Copies by SHA-256 reuse the result,
  `checked_as` included.
- **Google Docs and Slides** are downloaded as the .docx and .pptx Google
  exports (`google.export_address`:
  `docs.google.com/document/d/ID/export?format=docx`,
  `docs.google.com/presentation/d/ID/export/pptx`), with robots.txt asked
  about that export address; Google's allows `/document` and
  `/presentation`. A private Doc answers 401 and reads "needs a sign-in". A
  copy published to the web (`/d/e/…/pub`) has no export and reads
  `google_file`. Google Sheets are never asked for: Google's robots.txt does
  not allow `/spreadsheets` (they read `google_file`, "Axcess does not check
  Google Sheets"). The row says the file was checked as the file Google
  exports.
- **Word and PowerPoint files kept in Drive** are checked when downloaded
  (still only in a scan set to ignore robots.txt), instead of waiting.
- **Status.** A PDF is Mostly sure when any check fails. A Word or
  PowerPoint file is Mostly sure only when a check in `office_check.COUNTED`
  fails; the others (title, link text, heading levels) are stored in
  `failed_checks` with the rest and sent to the browser as
  `possible_problems`. The API also sends `checks_run`, the checks for the
  type the file was read as, which the document page's table lists.
- **No first-page picture** for Word or PowerPoint: nothing in Axcess draws
  one.
- **Untrusted bytes.** A ZIP that would unpack past 200 MB is not read, the
  XML parsers do not resolve entities, the check runs in a thread under the
  same 20-second limit as a PDF, and any exception reads "damaged".

## First-page pictures

A PDF the check could read gets pictures of its first page
(`linked_files/thumbnail.py`, drawn with PDFium through `pypdfium2`, because
pypdf cannot draw a page): one drawing saved in two sizes, a JPEG at most
480 by 960 pixels for the document's own page and one that fits 144 by 96
for the Documents table's 72 by 48 box, so a table page loads a few
kilobytes per row, not tens. Both are kept in the scan's blob store by
content hash (`thumbnail_hash`, `thumbnail_small_hash`, migration 0041).

**When:** during the scan, right after the check and before the result is
stored, because that is the only time the bytes exist: the scan keeps the
result, not the file, so drawing after the scan would mean downloading every
PDF again. A copy of the file reuses the first copy's pictures. Measured on
the developer's machine: 40 ms for a text page, about 175 ms for a 300 dpi
full-page photo, in a worker thread beside the downloads, which the site's
rate limit (2 a second) already spaces out more than that. No pictures when
the scan chose not to store rendered pages, for a file that is not a PDF, or
for one PDFium cannot open or draw in 10 seconds.

**Loading:** the table shows the small picture, lazily (`loading="lazy"`,
only rows scrolled into view), with its size fixed so the rows do not jump;
the document's own page shows the large one, captioned "First page". The
pictures are served only through their report
(`/api/scans/{scan}/documents/{file}/thumbnail`, `?size=small` for the
table), never by a hash the browser sends, and cached by the browser for a
day, since a picture never changes. The Documents tab does not update while
a scan runs (neither do Issues and Images); the scanning page shows
progress.

PDFium is not thread-safe: two drawings at once crashed the process (a
segmentation fault, caught by the crawl tests before release). Every PDFium
call runs under one process-wide lock (`thumbnail._PDFIUM`), every PDFium
object is closed inside it, and a drawing that cannot get the lock within 10
seconds is skipped (no picture). Keep any new PDFium call under that lock.

PDFium is C code running inside the app's process, where pypdf is pure
Python. It is the engine Chrome uses on PDFs from anywhere, but a file that
crashes it would take the app down with it; running it in a separate
process is the fix if that ever happens.

## Sign-in scans

Since 2026-11-16 a sign-in scan offers the document check too (the
developer's decision), on by default. Its PDFs download only through the
signed-in browser's request client (`SignedInFileFetcher` in `fetch.py`,
made by `ManualAuthenticationSession.create_authenticated_file_fetcher`), with
the person's cookies, and every address and redirect goes through the
sign-in scan's egress policy first. A file on another site is refused, never
downloaded anonymously instead, and reads "Could not check" with the reason
`blocked`. The crawl will not start the check without that fetcher
(`CrawlConfig.documents_signed_in`, `run_crawl`'s `file_fetcher`); the
protected agent pipeline never runs it. Playwright reads a response whole,
so the 10 MB limit is checked from a HEAD request's declared size first and
from the body after.

## The scanning page

The progress table's **Document check** column (`live_progress` key
`documents`) is marked running when a page's links are recorded and done
when that page's queued PDFs are checked (`live_progress.later`). Because
the page does not wait, its row can read "Checked" while this column still
reads "Checking"; the line over the table says so.

## Measured cost (hr.umich.edu, 50-page cap, the real app)

Before document links stopped being queued as pages, PDFs on the site
reached by ordinary links were left to the crawl, which with a 50-page cap
never reached them, so all 111 waited for the pass after the last page: 55
s, which is the site's rate limit (2 requests a second) for 111 downloads,
on top of about 119 s with the check off. The page crawl itself was not
slower with the check on.

After document links stopped being pages (same site, settings and method,
two runs each): off 101 s and 93 s, on 132 s and 115 s, so about 26 s
(27%) more with the check on. The pass after the last page is gone (at
most 13 s of downloads still running), but the page crawl is slower by
about as much: a 50-page scan of hr.umich.edu makes about 57 page requests
and 110 PDF downloads, at least 83 s of requests at the crawl's 2 a
second, while the page crawl alone takes about 95 s, so pages and PDFs
now share an almost full rate limit. The per-host connection limit is not
the bottleneck: the app sets it to the worker count (8 by default), and at
most 4 downloads run at once. The rate limit is the floor.

## Why it is built this way

- Checking PDFs only after the last page (the first version) left every PDF
  on another site unchecked when a scan was stopped part way. Checking with
  the page keeps the results for the pages the scan reached.
- Making the page wait for its PDFs (the second version) let one page with
  many new PDFs hold up a page worker. Queuing them keeps the crawl moving
  (the developer's request, 2026-11-14).

## The structure checks (2026-11-17)

Seven checks read a PDF's tags and page contents beside the five catalog
checks: `field_no_name`, `link_no_description`, `no_alt_text`,
`formula_no_description`, `table_cells_misplaced`, `table_uneven_rows` and
`untagged_text` (`linked_files/pdf_structure.py`, whose docstring defines
each). They run only where they apply, so each file stores the checks it was
given (`linked_files.checks_run`, migration 0046); a file checked before then
has none stored and ran the five (`pdf_check.BASE_CHECKS`). The document's
page lists only the checks the file was given.

**Why not veraPDF.** veraPDF (PDF/UA-1) was tried and built in on
2026-11-17, then removed the same day at the developer's request: on the
labelled set its curated rules caught no reader problem the five pypdf
checks missed (6 of 11 either way), and it needs a Java runtime (about
177 MB) and 2 to 3.4 s per call. Its commits were taken out of history
(kept on the local branch `backup/documents-with-verapdf`); migration 0044
drops what its migration 0042 left in databases that ran it. The experiment
that led to it: branch `verapdf-experiment`,
`docs/experiments/verapdf-hr-umich-2026-11-14.md`.

**Built on real files.** Tuned on the 59 PDFs a 20-page scan of hr.umich.edu
reached (2026-11-14), checked against the labelled set
(`tests/real_pages/document_check_labels.json`). What the real files
changed:

- pypdf's own text extraction hands text to a visitor after the
  marked-content sequence may have closed, so it put tagged text outside
  its tag (50 of 56 tagged files "had untagged text"). The checks read
  page contents one operator at a time instead.
- Untagged revision footers ("Revised 06/2026 for digital accessibility")
  sat 0.8% to 3.4% from the bottom of seven hr.umich.edu forms; the
  labeller judged them no reader problem. Text in the top and bottom 5% is
  not counted; the one untagged body text found sat at 46%.
- WH-385's "PART A" heading is marked with an MCID no tag refers to, so a
  screen reader never reaches it: counted as untagged.
- hr.umich.edu's supplemental appointment form marks its repeated page-3
  title with an MCID whose only parent is an "/Artifact" element: not
  counted (decoration by intent).
- Its logo alt text ends in a NUL byte, so pypdf returns bytes. An earlier
  probe that printed those bytes with `str()` showed Chinese characters and
  was wrongly reported as garbled alt text; a screen reader reads the
  words. There is no real example of garbled alt text, so there is no check
  for it.

**Measured** (2026-11-17, the 28 labelled files from the disk copies the
scan downloaded; 26 with a decided label, 11 with a reader problem):

| Score | Precision | Recall |
| --- | --- | --- |
| File: any failed check (before these four) | 6/6 | 6/11 |
| File: any failed check | 9/9 | 9/11 |
| `field_no_name` | 3/3 | 3/3 |
| `link_no_description` | 2/2 | 2/2 |
| `untagged_text` | 2/2 | 2/2 |
| `no_alt_text` | 0/1 | no real failure |

The two files still missed have problems no check tests (no heading tags;
wrong table headers). Limits: the set is small, mostly one publisher's forms,
judged by an agent reading each file's structure, not by a person with a
screen reader, and the four checks were tuned on these same files, so their
scores here are not independent. `no_alt_text`'s one hit is a
decorative border box tagged as a figure. Each check needs more real failing
files, from other publishers, before its number means much.

**Time.** All 59 files in 6.1 s; the slowest 0.26 s. The structure checks
have their own budget (`pdf_structure.TIME_BUDGET_S`, 8 s): past it they are
recorded as not run and the five catalog checks keep their result, where the
whole check's limit (`tracker.CHECK_TIMEOUT_S`) would mark the file "Could
not check". IRS Publication 15-T (71 pages, 57,727 tags) took 6.8 s to 17 s
on this machine from run to run, so it can run out; its tag count is why
`MAX_ELEMENTS` is 200,000.

### Tables and formulas (2026-11-18)

`table_uneven_rows` and `formula_no_description` were added after the
hr.umich.edu files showed one table veraPDF faulted (file 23, a row a cell
short) and none with formulas. An agent collected 54 more PDFs from 25 hosts
(manifest: `artifacts/real-pdfs/manifest.jsonl` in the `verapdf-experiment`
worktree, not in git): 28 real-world from 22 publishers (US and UK
government, NIST, Census, universities, Pew, ETSI, TUG, texdoc) and 26
test-suite files (veraPDF's corpus, the PDF/UA Reference Suite, W3C's PDF
technique examples, the LaTeX Project's tagged demos). The labelled set is
`tests/real_pages/document_structure_labels.json`; each file is judged only
on the checks it names.

What the files changed:

- Tagged LaTeX (LaTeX News, TUGboat, the STEM demos) describes formulas with
  MathML, as associated files or MathML elements inside the formula, and no
  alt text: PDF 2.0's and PDF/UA-2's way. 470 formulas failed until MathML
  counted as a description. TeX source alone (latex-lab-math, latex-lab-table)
  does not count; those two are labelled unsure.
- veraPDF's corpus passes a formula whose ActualText is present but empty
  (7.7-t01-pass-c). A screen reader reads nothing, so Axcess fails it; the
  file is listed as disputed.

**Measured** (from the downloaded copies):

| Check | Files | Precision | Recall |
| --- | --- | --- | --- |
| Either table check, test-suite (outside verdicts) | 16 | 11/11 | 11/11 |
| `table_cells_misplaced`, real-world (looked at) | 5 | 5/5 | not measured |
| `table_uneven_rows`, real-world (looked at) | 1 | 1/1 | not measured |
| `formula_no_description`, test-suite (outside verdicts) | 6 | 2/2 | 2/2 |
| `formula_no_description`, real-world (tags read) | 5 | 1/1 | 1/1 |

Read these with their limits. Test-suite files each show one fault, so they
are not real-world accuracy. The real-world tables are only ones the check
flagged and an agent then looked at (rendered page and tags), so they show
the flags were right, not what the check misses; no real-world file has an
outside verdict. The one real-world formula failure (NIST FIPS 203: 34
formulas, no alt text, no MathML) rests on its tags alone.

**What a flagged table means.** The check fired on 15 of the 24 real-world
files with tables. Two kinds of fault, both failures of PDF/UA-1 7.2:

- Header cells without their spans (the Australian Budget's "Projections"
  falls on 2029-30's column; NIST SP 800-90B's "Non-binary data" heads the
  binary "Cutoff Value C"; W3C's table.pdf), or a data row missing a cell
  (hr.umich.edu file 23). These mislead: a value is read under the wrong
  heading.
- A label row across the table tagged as one or two cells with no span (Pew
  Research's "PHONE TREND PRESENTED FOR COMPARISON", St Albans' "This Capital
  Programme was financed as follows:"). These fail the rule but a reader
  hears the label under the first column; no other cell moves.

**The split (2026-11-18).** Each table cell's text now has a left and
right edge on the page (text position plus the font's glyph widths,
clamped to the page: one run on Pew's topline was estimated to end at x
1626 on a 612 pt page). The full rows' cells give each column's extent. A
cell of a short row whose text sits under another column than its tags
give it fails `table_cells_misplaced`; text wider than its columns (a
label, a heading over several columns) is placed by its left edge, other
text by its centre. Uneven tables with no cell out of place fail
`table_uneven_rows`, and so do those whose text could not be placed: the
checks read text from the first 50 pages only, so St Albans' 118-page
accounts have 33 uneven tables past page 50 that can only be "uneven".
"Misplaced" needs a cell seen out of place; uneven rows are a fact from
the tags alone. On the tables looked at, the split matched the page every
time, and corrected one call made by eye: Pew's label row is the second
cell after an empty one, so it is read under "At least once a week".

### Cost of the structure checks (hr.umich.edu, 50-page cap, 2026-11-18)

Four CLI scans (`audit crawl --max-pages 50 --skip-ocr --skip-vlm
--skip-semantic`, a fresh database each), alternating the old checker
(`documents`, five catalog checks) and the new one:

| Run | Wall time | Last page | Last PDF checked |
| --- | --- | --- | --- |
| new 1 | 204 s | 15:25:48 | 15:25:33 |
| old 1 | 265 s | 15:31:17 | 15:31:14 |
| new 2 | 159 s | 15:35:04 | 15:34:56 |
| old 2 | 267 s | 15:40:36 | 15:40:34 |

Each scan crawled 52 or 53 pages and checked 104 to 107 of 111 to 115 PDFs.
The old runs were slower, which the checker cannot cause: same commit
otherwise, same packages and settings, the same work in the crawl summary.
So two runs each cannot measure the checker in wall time; the site and this
machine vary more than it costs. In every run the last PDF was checked
before the last page was crawled, so the checks, which run beside the crawl,
added nothing to when the scan ended.

The checker alone, on the same 101 PDFs (best of three per file, two
rounds): old 7.8 s and 8.0 s in all, new 17.2 s and 21.6 s (2.2 to 2.7
times); median per file 0.04 s old, 0.08 to 0.10 s new; the most added to
one file 1.5 s. About 10 to 14 s more CPU across a 50-page scan, in the
check's own thread. A scan with many more PDFs per page could make that
compete with the crawl for the CPU; not seen here.
