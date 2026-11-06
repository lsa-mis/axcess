# Detection efficacy and evaluation pipeline

Axcess measures detection quality as an evidence system, not as a claim that a
scan proves WCAG conformance. Deterministic engines may produce likely-barrier
findings. Browser probes, OCR/VLM, and semantic analyzers produce review leads
that require an accessibility expert to confirm or reject them.

## What is evaluated

| Dimension | Question | Current gate |
| --- | --- | --- |
| Efficacy | Are surfaced findings and review leads supported by the labeled reference answer? | False-discovery rate below 5% and recall of at least 80%, overall and for every detection layer. |
| Efficiency | Can the local evidence path ingest detector output and build the unified issue view without a major regression? | At least 100 findings stored per second and issue projection below 5 seconds on the reference workload. |
| Scale | Does evidence processing remain usable as the report grows? | Correct row counts at 100, 500, and 1,000 pages, with no more than 3x normalized per-finding slowdown from the smallest to largest workload. |
| Crawl coverage | Does a scan find every page under its starting address, and say which it left out? | On the test site `tests/fixtures/site/coverage`: 100% recall, 0 wrong pages, at most 1.1 page fetches per unique page, every one of the 9 hard cases passing, and exact "not visited" counts. |

The efficacy corpus also requires at least 20 surfaced labels and five negative
controls per layer. These floors prevent a detector from passing by suppressing
everything or by relying on a tiny denominator.

### Metric definitions

- **Precision** is `TP / (TP + FP)`.
- **False-discovery rate (FDR)** is `FP / (TP + FP)`: the share of surfaced
  results that become report noise.
- **False-positive rate (FPR)** is `FP / (FP + TN)`: the statistical rate among
  negative controls. It is reported separately from FDR.
- **Recall** is `TP / (TP + FN)`.
- **Write throughput** is persisted detector observations divided by transaction
  time. Migration/setup time is excluded.
- **Projection latency** is the time required to group the stored evidence into
  the report's unified issue rows.
- **Normalized slowdown** compares seconds per finding at the largest and
  smallest workloads.
- **Crawl recall** is expected pages visited divided by the pages in the test
  site's answer key (`expected.json`).
- **Wrong pages** counts page rows that are not an expected page (out of
  scope, blocked, a search result) or repeat one under a URL variant, plus any
  request for a page that must never be requested (a sign-out link, a page
  robots.txt disallows, an out-of-scope page).
- **Page fetches per unique page** is the requests the test server answered
  for page documents (redirect answers included; robots.txt and sitemap files
  excluded) divided by unique pages found. The report also lists every request
  beyond one per page, and the seconds until 90% of expected pages were
  requested.
- **Honesty** checks the counts a report stores for pages it found but did not
  visit: with the default depth limit of 10, the page 11 clicks deep must be
  counted under the depth limit and the sign-out and robots.txt pages under
  blocked; with a page limit of 8, every page counted under the page limit must
  be a real page on the site.

### Crawl-coverage hard cases

The test site's answer key lists the 9 hard cases from the crawl-coverage
ticket, each scored on its own: a page only in a sitemap (one in the sitemap
robots.txt names, one in `/sitemap.xml`), a page 11 clicks deep, pages reached
only by a button (an `onclick` address and a form that is only a button), an
image-map `<area>` link, URL variants (letter case, a trailing slash, tracking
query text), a redirect, an out-of-scope page, a sign-out link, and a page
robots.txt disallows. The site's server ignores letter case, as many real
servers do, so `/About.html` is a duplicate rather than a broken link.

## Current evidence and limitations

The versioned corpus at
`tests/quality/corpora/detection_precision_v1.json` covers all report-facing
layers: axe, Alfa, behavioral probes, OCR/VLM, and semantic analysis. It records
the pipeline, rule, reference label, and the product disposition for every
sample. The same evaluation keeps model- and probe-backed results in the expert
review lane.

The bundled corpus is synthetic by construction. Its results are regression
evidence, not a real-world accuracy estimate or confidence bound. An external
efficacy claim requires a held-out, representative corpus labeled independently
by at least two accessibility experts, with adjudication, inter-rater agreement,
per-rule denominators, abstentions, and confidence intervals.

The efficiency and scale gates exercise the durable local evidence path:
SQLite writes followed by the same unified issue projection used by the report
UI. They do not yet measure network crawling, browser rendering, OCR latency, or
local-model inference. Those measurements require pinned hardware, browser and
model versions, warm/cold-run separation, and representative authorized sites;
mixing them into a shared CI runner would produce misleading thresholds.

The crawl-coverage lane runs the real crawler, but over plain HTTP on one small
local site. It does not render pages in a browser, so it does not count the
second request a default scan makes for each page it also renders (unless
`skip_static_when_rendering` is on), and it finds no address that only a script
builds: those are left to Click-Through. Its 32 pages make the fetch ratio
sensitive to each extra request, which is why the report names every one.

## Running the pipeline

```bash
make detection-evals
```

The command writes machine-readable and human-readable reports to
`artifacts/detection-evals/report.json` and
`artifacts/detection-evals/report.md`. It exits non-zero when any efficacy,
efficiency, scale, crawl-coverage, or integrity gate fails.

The dedicated GitHub Actions workflow runs on relevant pull requests, pushes to
`main`, weekly schedules, and manual dispatches. It publishes both reports as a
workflow artifact and adds the Markdown report to the job summary.

Thresholds and workload sizes live in
`tests/quality/detection_eval_config.json`. Changes to a threshold, workload,
producer, prompt, model, or reference label should be reviewed like a test
contract: explain the reason, preserve prior results when comparisons matter,
and increment the applicable corpus or configuration version.

## Next evaluation increments

1. Add a governed, expert-labeled validation corpus separate from development
   fixtures.
2. Record confidence intervals and calibration by rule, framework, page type,
   language, and protected/public context.
3. Add pinned-runner browser benchmarks for crawl time, render time, probe time,
   peak memory, and evidence bytes per page.
4. Add pinned local-model benchmarks for OCR/VLM and semantic latency, resource
   use, abstention rate, and quality by model version.
5. Track longitudinal results rather than weakening a gate when a regression is
   inconvenient.
