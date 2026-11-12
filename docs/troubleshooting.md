# Troubleshooting

Quick fixes for the problems people run into most often. The first sections
cover scanning and reports. The last section is for developers working from a
source checkout.

## My scan only fetched one page

The first page probably returned an error. Open the scan page: when the start
address fails, a red notice says "Site URL returned HTTP" with the status code
and the page title.

- **403 with the title "Just a moment..."**: a Cloudflare bot check. Axcess
  opens pages in a real browser by default, but a heavier bot check can still
  block it. If you turned on **Fast crawl without a browser** (or used
  `--static-only`), Axcess opens only some pages in the browser: those that
  look like a bot check, or like an app that shows its content only through
  scripts. Turn fast crawl off and scan again.
- **403 with the title "Access Denied"**: a firewall that refuses automated
  visitors, so Axcess cannot scan the site as it is. Ask the site owner
  whether they can allow your scan.
- **401, or a sign-in page**: the pages need a login. Start a new scan on the
  **Site with a login or 2FA** tab, sign in yourself in the browser window
  Axcess opens, then select **I'm signed in, start scan**. A
  [login scan](./glossary.md#sign-in-scan) needs an `https://` address and a
  site with a public internet address. It runs only in Axcess on your own
  computer, not in a copy hosted for a team.
- **404**: check the address for a typo.

## It's crawling too much or too little

- **Too much.** An address with no path, such as `https://site.example/`, puts
  the whole host in [scope](./glossary.md#scope), and so does **Crawl the
  entire host** (under Advanced settings, **Coverage**). Enter an address with
  a path, such as `https://site.example/blog/`, and leave that switch off.
  Before you start, the line under the address says what will be scanned.
- **Too little.** The path leaves out pages you want. Enter a shorter path, or
  turn on **Crawl the entire host**. Also check **Max pages** (2,500 by default
  in the app, 500 on the command line) and **Max link depth** (10 by default).
- **A new scan continued an old one.** If an earlier scan of the same address
  ended early, starting that address again in the app continues the earlier
  report instead of making a new one. That includes a scan you stopped with
  **Stop scan**. Axcess drops queued pages that fall outside the new scope.
  Login scans always start a new report. On the command line, an earlier scan
  continues only while pages are still waiting, so scanning again after a stop
  starts a new report. If you want a separate report and no longer need the
  earlier one, delete it first with **Delete** on the **Reports** list.

## The scan is stuck or very slow

- **Stop it.** Select **Stop scan** on the scan page. Axcess marks the scan as
  interrupted, drops the pages still waiting in its queue, and keeps everything
  it already collected.
- **The site is struggling.** Lower **Requests per second** or **Parallel
  workers** under Advanced settings, **Speed and debugging**, then scan again.
  On the command line, lower `--rps`.
- **Text recognition is slow.** [OCR](./glossary.md#ocr) uses 2 workers by
  default. On a source install, raise `AUDIT_OCR_MAX_WORKERS`. If you only
  need the other checks, turn off **Read text inside images (OCR)**, or pass
  `--skip-ocr`.
- **Local AI is slow.** The optional AI checks add time to every page, which
  is why the app leaves them off by default. The vision model reviews one
  image at a time (`AUDIT_VLM_CONCURRENCY`, default 1), and raising that can
  back up the AI service on a small machine.

## I closed the sign-in window before starting

Nothing is lost yet. Axcess keeps your sign-in in memory for 30 minutes after
the window closes. Go back to **New scan**: it shows your sign-in in progress.
Then select **I'm signed in, start scan**, or **Reopen sign-in window** to
open the window again on the page you were on.

- Some sites tie a sign-in to the exact browser window, or end it quickly.
  After you reopen the window, such a site may ask you to sign in again.
- After 30 minutes with the window closed, Axcess forgets the sign-in. Sign
  in again with **Open browser to sign in**. Your settings are still filled
  in.
- Axcess keeps one sign-in at a time, and quitting Axcess ends it.

## The local AI checks aren't running

A [local AI model](./glossary.md#local-ai-model) needs an AI service to run
it. The desktop app has its own private AI service: the AI program
(llama.cpp) comes with the app, and **Settings > AI features** downloads the
AI models after you choose a size. If you run Axcess from source code or on a
server, you run Ollama or a llama.cpp server yourself.

- **Is the switch on?** For a public website, the AI switches under Advanced
  settings, **Local AI**, are off by default. **Read text inside images
  (OCR)** is on and needs no AI model. When a switch can't be used, the form
  says why.
- **Is the AI service running?** In the desktop app, select **Start AI
  service** in Settings. If you run your own Ollama,
  `curl -s http://localhost:11434/api/tags` should return JSON.
- **Is the model installed?** In the desktop app, choose a size in **AI features**
  and confirm the size-labelled download. `ollama pull` does not work with
  the desktop app's private AI service. If you run your own Ollama, install a
  model with `ollama pull <model>`. `AUDIT_VLM_MODEL` picks a different image
  model.
- **Want the AI checks off?** Leave the switches off. On the command line they
  are on by default, so pass `--skip-vlm --skip-semantic --skip-visual`. Image
  findings are still created from OCR text and the alt text comparison.

If the AI service can't be reached when a scan starts, Axcess logs a warning
and continues without those checks.

## AI features setup in the desktop app stopped or failed

- **AI service is not running**: select **Start AI service** in Settings. This
  starts only Axcess's private AI service. It never starts or stops your own
  Ollama. When the app opens with AI on, the service starts in the background;
  until it is ready, AI requests say it is not running.
- **Private models are missing**: choose a size in **AI features**. Check the
  download size, then select **Download and set up**. Starting the service
  never downloads files without that separate choice.
- **"The AI models need to be downloaded again for this version of Axcess"**:
  your AI setup was saved by an older version, which used a private copy of
  Ollama. Choose a size and select **Download and set up**. When the download
  finishes, Axcess deletes the old private Ollama files.
- **AI could not be isolated**: the service stays stopped. On Windows, the
  private AI service cannot be isolated yet, so AI does not start. On Linux,
  install Bubblewrap (`bwrap`); without it, AI does not start. Do not disable
  the isolation check or expose a service to the internet to get past this
  error.
- **Isolation check failed**: check the application log. Axcess requires proof
  that the operating system blocks outside connections; a timeout does not
  count. Reports and saved suggestions remain readable.
- **Your own Ollama is not managed**: Axcess leaves it alone. To use the
  isolated private AI service instead, choose a size and select **Download
  and set up**.

- **AI features are off**: open **Settings > AI features** and select
  **Turn AI on** to reuse kept models, or choose a size and download if you
  have not set AI up yet. The setting stays off after a restart.
- **Cannot change the setting**: finish or stop the scan, finish or cancel
  waiting AI answers, or pause the download. A canceled answer may still
  have a model request finishing; wait for it before trying again.
- **Saved AI settings could not be read**: AI stays off and report browsing
  still works. Check the application log and the saved `ai/preferences.json`
  file. Do not delete your models or scan evidence to fix a settings file.
- **"Not enough free disk space"**: free up space or choose a smaller size.
  The page shows how much each size downloads.
- **The download stopped or was paused**: select **Resume download**. It
  carries on from where it stopped. After an error, select **Try again**.
- **"The AI model download did not match its published checksum"** (or "The
  AI program download"): the file was changed or damaged on the way. Axcess
  deletes it and does not use it. Try again later.
- **"The isolated AI service could not start"**: read `ai/llama-server.log`
  in the Axcess data folder. If the graphics chip build cannot load the
  models, Axcess tries the processor-only (CPU) build by itself.
- **Start over**: select **Remove AI features**, then download again.

## Compare reports has nothing to compare, or shows a surprise

A report's **Compare reports** view shows it beside another completed
report of the same start address, each in its own panel. From the report's
tab, the second panel starts empty: choose a report from its list. The
[rescan comparison](./glossary.md#rescan-comparison) itself, what is new,
still found or no longer found, is on **What changed**: choose **See what
changed between these reports** on Compare reports.

- **Nothing to compare.** The two start addresses must match. Letter case in
  the host name and a missing trailing slash don't matter, but
  `www.example.edu` and `example.edu`, or two different ports, count as
  different sites. Start the new scan from the same address as the old one.
- **No reports to choose in the empty panel.** The site has one completed
  report, or the others have a different start address (see above).
- **The wrong earlier report.** On Compare reports, choose another report
  in the panel's **Report** list, then **Show this report**, or choose
  **Close** on the second panel and pick again. On What
  changed, select the earlier scan in **Trend over time** (or in its data
  table) and choose **Compare with this report**, or add
  `?compare_to=<earlier report id>` to the address
  (`/app/scans/<new id>/compare/changes`). Both reports must be completed
  and share a start address. Old `/diff` links open What changed.
- **A panel of Compare reports is blank.** Behind a reverse proxy, the
  proxy may block frames. See [Hosting](./hosting.md#framing-headers-behind-a-proxy).
- **The command-line image diff.** `audit crawl` picks the earlier scan for
  its image findings by itself, and ignores the port on `localhost` addresses.
  To choose it yourself, pass `--compare-to <id>` to `audit crawl` or
  `audit synthesize`.

## Old "running" scans clutter the list

When Axcess starts, it marks any scan still listed as running as interrupted,
because the process that ran it has ended. If you still see stale rows, that
database hasn't been opened since the restart. Start Axcess (or
`audit serve`) once and they clear.

## I want to start completely over

On a source install, stop Axcess, then delete every report and create a fresh
database. This cannot be undone.

```bash
make clean     # deletes data/audit.db, data/blobs and data/logs
make migrate   # creates an empty database
```

## For developers

### My UI changes aren't showing up

The review app is a React build that Axcess serves from `/app/`. Run
`make frontend-build` again after changing frontend code, then hard refresh
the browser. For quicker iteration, `make frontend-dev` runs the Vite
development server on port 5173 and passes API calls to Axcess on port 8765.

### The axe-core UI tests fail after my change

Run the suite on its own:

```bash
uv run pytest tests/ui/test_accessibility_axe.py -v
```

Each failure lists the rule id (such as `color-contrast` or `label`), its
impact, and the offending selectors. Fix the markup and run it again. The
suite checks the built React app against axe-core's WCAG A, AA, and AAA rules
plus best practices, and fails on any violation by design. It skips itself
when Playwright or the frontend build is missing, so run
`make frontend-build` first.

### I need to dig through the database

```bash
sqlite3 data/audit.db
```

Handy queries:

```sql
-- Latest scans
SELECT id, seed_url, status, page_count, finding_count, started_at
FROM scans ORDER BY id DESC LIMIT 5;

-- Image findings for one scan, highest priority first
SELECT f.severity, f.priority_score, f.status,
       substr(i.src_url_canonical, 1, 60) AS image,
       substr(a.ocr_text, 1, 40) AS ocr
FROM findings f
JOIN images i ON i.id = f.image_id
LEFT JOIN analyses a ON a.image_id = i.id
WHERE f.scan_id = <id>
ORDER BY f.priority_score DESC
LIMIT 20;

-- Page-level results for one scan (rule engines, browser checks, AI), by check
SELECT pipeline, rule_id, COUNT(*) AS occurrences
FROM page_a11y_findings
WHERE scan_id = <id>
GROUP BY pipeline, rule_id
ORDER BY occurrences DESC;

-- Why is the queue big?
SELECT state, COUNT(*) FROM jobs
WHERE json_extract(payload_json, '$.scan_id') = <id>
GROUP BY state;

-- Which pages were rendered in a browser ('js') or fetched without one ('static')?
SELECT render_mode, status_code, COUNT(*)
FROM pages WHERE scan_id = <id>
GROUP BY render_mode, status_code;
```
