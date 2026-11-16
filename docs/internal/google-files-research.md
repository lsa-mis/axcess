# Downloading Google Drive and Google Docs files: research

Research for the document check (`src/audit/linked_files/`), 2026-11-16.
Today every Google link is listed as "Could not check" (`google_file`).
The question was how to download the PDF or Word file behind a Google
link: Google's download addresses, or Axcess's own browser finding and
pressing the download button.

Nothing here is built yet. Product decisions are open (end of this page).

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

## Open decisions

1. **Drive files and robots.txt.** Obey Google's `Disallow: /` (Drive files
   stay unchecked, "robots.txt asks scanners not to download them") unless
   the person chose to ignore robots.txt? Or treat a download as a person's
   click? The first is consistent with the rest of Axcess.
2. **Private files.** On this site, 14 of 15 Drive files and 4 of 6 Docs
   need a Google sign-in. Checking them would mean a signed-in Google
   session. Sign-in scans keep to the signed-in site (egress policy), so
   that is separate work.
3. **Docs and Slides.** Check Google's PDF export, and say in the row that
   it is the PDF Google makes from the document?

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
