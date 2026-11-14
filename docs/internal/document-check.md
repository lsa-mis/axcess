# The document check (linked files)

How the Documents tab's check finds files, decides which ones are the same,
and when it downloads and checks them. Code: `src/audit/linked_files/`
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
and 110 PDF downloads, at least 83 s of requests at the site's 2 a
second, while the page crawl alone takes about 95 s, so pages and PDFs
now share an almost full rate limit and the site's 2 connections (a PDF
holds one for its whole transfer). The rate limit is the floor; what is
left to gain is letting page requests go ahead of PDF downloads.

## Why it is built this way

- Checking PDFs only after the last page (the first version) left every PDF
  on another site unchecked when a scan was stopped part way. Checking with
  the page keeps the results for the pages the scan reached.
- Making the page wait for its PDFs (the second version) let one page with
  many new PDFs hold up a page worker. Queuing them keeps the crawl moving
  (the developer's request, 2026-11-14).
