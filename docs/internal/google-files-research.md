# Downloading Google Drive and Google Docs files: research

Research for the document check (`src/audit/linked_files/`), 2026-11-16.
Today every Google link is listed as "Could not check" (`google_file`).
The question was how to download the PDF or Word file behind a Google
link: Google's download addresses, or Axcess's own browser finding and
pressing the download button.

Decided and built for Drive files on 2026-11-16 (`linked_files/google.py`,
"Decisions" at the end), and for Docs and Slides on 2026-11-17. Sheets
stay unchecked: robots.txt refuses them.

## What was tested

These tests used real links from a real Axcess scan of
`https://rossweb.bus.umich.edu/ross-it/` on 2026-11-16 (approved by the
developer). The scan used the New scan public defaults, 40 pages, and
found 45 Google Docs, 15 Drive files and 1 Sheet. Every probe sent one
request at a time, about one a second, with Chrome's browser name. The
probes ran outside Axcess, from scratch scripts, and are not in the repo.

### Drive files (`drive.google.com/file/d/ID/view`)

| Way | Result |
|---|---|
| A: `GET https://drive.usercontent.google.com/download?id=ID&export=download` | 1 of 15 public: `200`, `application/octet-stream`, the PDF (214,363 bytes), name in `Content-Disposition`. 14 of 15 private: a redirect to `accounts.google.com`, the sign-in page (about 1.25 MB of HTML). |
| B: Chromium opens `drive.google.com/file/d/ID/view`, presses the button whose accessible name starts with "Download", and waits for the download (`page.expect_download`) | The public file: exactly one such button, and the same 214,363-byte PDF in 3.4 s (A took 1.1 s). The download came from `drive.usercontent.google.com`, the address A calls. The 12 private files on `/faculty-services/`: the page is "Google Drive: Sign-in", with no download button (the only buttons were "Forgot email?", "Next" and "Create account"). |

The download button and address A are the same request: the button is
Google's interface on top of that address.

### Google Docs, Sheets and Slides

`GET https://docs.google.com/document/d/ID/export?format=pdf` is what the
editor's File > Download > PDF uses. On `/faculty-services/`:

| Result | Docs | Meaning |
|---|---|---|
| `200`, a PDF (218 KB, 289 KB), via `doc-…-docstext.googleusercontent.com` | 2 of 6 | Public ("anyone with the link") |
| `401` | 4 of 6, and the 1 Sheet | Shared only with signed-in accounts |
| `410`, "Page Not Found" | 1 of 6 | Deleted |

Sheets use `/spreadsheets/d/ID/export?format=pdf` (or `xlsx`), and Slides
use `/presentation/d/ID/export/pdf` (sources below). A Google Doc has no
original file to download. Its "PDF" is Google's rendering of it, so a
check of that PDF measures Google's export, not something the author
made.

## robots.txt decides most of this

Axcess obeys robots.txt unless the person turns that off (New scan). It
applies to a page, a PDF download, and a click a scanner makes. Google's
files on 2026-11-16 said:

| Host | robots.txt for `User-agent: *` | Effect |
|---|---|---|
| `drive.usercontent.google.com` | `Disallow: /` | Every Drive file download is refused, whether by address A or by the button. Both request this host. |
| `docs.google.com` | `Allow: /document`, `Allow: /presentation`, …, then `Disallow: /` | Doc and Slides exports are allowed (the longest matching rule wins). `/spreadsheets` is not on the allow list, so Sheets are refused. |
| `drive.google.com` | `Allow: /file`, `Allow: /open`, …, then `Disallow: /` | The `/view` page may be opened, but its download goes to the refused host above. |
| `doc-…-docstext.googleusercontent.com` (the export's redirect) | No robots.txt (an HTML page answers instead) | Treated as allowing everything, as for any host without one. |

So, while robots.txt is obeyed:
- Drive files cannot be downloaded at all, by the button or otherwise.
- Docs and Slides can be exported to PDF and checked.
- Sheets cannot.

## Future-proofing

- **Address first.** The export and download addresses have been stable
  for years, and widely used tools build on them, for example `gdown`
  (sources below). They are faster than a browser, work in a Fast scan
  (no browser), and go through the crawl's own rate limit and robots.txt
  check.
- **The button as the fallback, not the main way.** Find it by role and
  accessible name, as the probe did, not by CSS class (Google's class
  names are generated and change). In the probe it was the same request,
  three times slower. Its weak points are localisation (Axcess's browser
  is set to English, so the name is "Download") and redesigns that move
  the button into a menu or an iframe.
- **How a failure is recognised.** A sign-in redirect (`accounts.google.com`)
  or `401` means private. `404` or `410` means deleted. An HTML page where
  a file was expected is the large-file "Google Drive can't scan this file
  for viruses" page (it submits `#download-form`, which `gdown` parses) or
  a new interface. Check the bytes (`%PDF`), never only the status.
- **A canary.** An opt-in test (like the real-pages sets, never in CI)
  that downloads one known public Drive file and one public Doc through
  the real code, to catch Google changing either address before users do.
- **Owners can turn downloads off.** That is the share setting "Viewers and
  commenters can see the option to download, print, and copy",
  `copyRequiresWriterPermission` or `downloadRestrictions` in the Drive API.
  Then there is nothing to download, and the row has to say so, not call
  it broken.

## Decisions (the developer, 2026-11-16)

1. **Drive files follow robots.txt.** A scan that follows robots.txt asks
   about `drive.usercontent.google.com`, the host every Drive download comes
   from, and lists the file as "Not checked, because the scan followed
   robots.txt", telling the reader to scan again with "Ignore the site's
   robots.txt rules" turned on. A scan set to ignore robots.txt downloads
   them. New scan says so beside the document check while robots.txt is
   followed.
2. **Google's address first, the button as the fallback.** `fetch_drive_file`
   asks the download address, passes the virus-scan page's form once, and
   reports a sign-in redirect as HTTP 401 ("needs a sign-in"). If an HTML
   page still comes back where a file should be, `download_with_button`
   opens the file's page in Chromium and presses the button whose
   accessible name starts with "Download". A Word or PowerPoint file kept
   in Drive is downloaded and identified, and waits for a check of its
   format.
3. **Docs and Slides: export them as .docx and .pptx and check them with
   another engine.** Built 2026-11-17: `google.export_address` and
   `office_check.py`, Axcess's own rules on python-docx and python-pptx
   (why not an existing checker: `office-check-research.md`). On
   2026-11-17 the export of a public Doc linked from the U-M sites answered
   200 with a .docx, a private one 401, a deleted one 410, and a copy
   published to the web (`/d/e/…/pub?output=docx`) only an HTML page. Two
   exports of one Doc a minute apart differ in bytes (Google renames
   pictures and relationship IDs), so a Google file's SHA-256 is no
   identity across scans.
4. **Not built, an option:** Google's Drive API
   (`www.googleapis.com/drive/v3/files/ID?alt=media`) has no robots.txt, so
   it could download public Drive files while robots.txt is followed. It
   needs an API key that an administrator creates and configures.

## Verified on real pages (2026-11-16)

This was a real Axcess scan of one page,
`https://rossweb.bus.umich.edu/ross-it/student-services/` (1 page), whose
Drive links are 1 public file and 1 private one:

| Scan setting | Public Drive file | Private Drive file |
|---|---|---|
| Follows robots.txt | Could not check, robots.txt | Could not check, robots.txt |
| Ignores robots.txt | Downloaded (214 KB) and checked: Mostly sure (not tagged, no title, no language), with its first-page picture | Could not check, needs a sign-in (HTTP 401) |

`/ross-it/faculty-services/` (1 page, robots.txt ignored): all 12 Drive
files read "needs a sign-in (HTTP 401)".

## Sources

- Google, "Protect file content", Drive API guide (`copyRequiresWriterPermission`,
  `downloadRestrictions`): https://developers.google.com/workspace/drive/api/guides/content-restrictions
- Playwright for Python, Downloads: https://playwright.dev/python/docs/downloads
- `gdown` source, `gdown/download.py`: https://github.com/wkentaro/gdown
- Export URL patterns for Docs, Sheets and Slides: https://www.labnol.org/internet/direct-links-for-google-drive/28356
- The `drive.usercontent.google.com` download host and `confirm=t`:
  https://www.mergedocs.pro/download-large-file-google-drive-curl-wget and
  https://github.com/tensorflow/datasets/issues/3935
- robots.txt files read on 2026-11-16: `https://docs.google.com/robots.txt`,
  `https://drive.google.com/robots.txt`, `https://drive.usercontent.google.com/robots.txt`
