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
2. `queue_page` queues the PDFs this page reaches that the crawl will not
   fetch itself, and returns at once. The page's worker goes on to the next
   page; the downloads work through the queued PDFs of earlier pages in the
   background.
3. After the last page, `check_pending` first waits for the queued
   downloads (`drain`), then checks anything still waiting (for example a
   PDF on the site past the page or depth limit).
4. A stop or a failure cancels the queued downloads (`cancel_background`);
   the files not finished are reported as not checked.

Which PDFs a page queues:

| PDF | Checked |
| --- | --- |
| On another site (Google Drive, Box, a partner's site) | Queued by the page that links to it. The crawl never visits other sites. |
| Shown in a frame, object or embed | Queued by the page. The crawl follows only ordinary links. |
| On the site, reached by an ordinary link | By the crawl, which fetches it as it fetches a page and checks it from that response (`record_response`). Queuing it too would ask the site for it twice. |
| Anything left | At the end (`check_pending`). |

One rare case asks twice: a PDF on the site shown in a frame on one page and
found later as an ordinary link on another. Avoiding it would mean the crawl
skipping that fetch, which changes what "Pages visited" counts.

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

## Why it is built this way

- Checking PDFs only after the last page (the first version) left every PDF
  on another site unchecked when a scan was stopped part way. Checking with
  the page keeps the results for the pages the scan reached.
- Making the page wait for its PDFs (the second version) let one page with
  many new PDFs hold up a page worker. Queuing them keeps the crawl moving
  (the developer's request, 2026-11-14).
