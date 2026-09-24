# Detection pipelines

This page is for people who build and maintain Axcess. It lists every
detection pipeline, shows how each result is assigned to a report group, and
describes the safeguards that keep uncertain results out of the Barrier group.
When you are ready to add or tune a check, continue with
[Adding or tuning a check](adding-a-check.md).

Report groups and other terms are defined in the [glossary](../glossary.md).
Code references name the file and function. Line numbers match commit
`38eae99` and will drift, so search for the function name if a line has moved.

## Pipelines at a glance

A pipeline is one source of [findings](../glossary.md#finding). Most
pipelines write rows to the `page_a11y_findings` table and tag each row with a
`pipeline` value. Image-of-text results live in their own tables.

| Pipeline | What it detects | WCAG criteria | Source module | Stored `pipeline` value | Report group (code lane value) | Key limits |
| --- | --- | --- | --- | --- | --- | --- |
| [axe-core](../glossary.md#axe-core) | Rule violations in the rendered page: missing names, alt text, and labels, ARIA misuse, contrast, language, landmarks, [target size](../glossary.md#target-size), and more. | A and AA rules at the default level (or A only, or AAA, when chosen), plus best-practice rules with no criterion (shown as BP). | `src/audit/analyzer/axe.py`, running the committed bundle `src/audit/web/static/axe.min.js` (axe-core 4.10.2). | `axe` | Barrier (`likely_barrier`), including best-practice rules. | Stores axe `violations` only; axe's `incomplete` results are dropped. Experimental and deprecated rules never run, so `label-content-name-mismatch` (2.5.3) is never checked. HTML snippets are capped at 4,000 characters. |
| [Siteimprove Alfa](../glossary.md#siteimprove-alfa) | Failed and "cannot tell" outcomes from Alfa's [ACT rules](../glossary.md#act-rule), on its own capture of the page. | Per ACT rule, at the level chosen for axe. | `src/audit/analyzer/alfa.py` and the Node runner in `src/audit/alfa_runner/`. | `alfa`, with `engine_outcome` set to `failed` or `cant_tell`. | `failed`: Barrier (`likely_barrier`). `cantTell`: Needs review (`expert_review`). | Needs `make alfa-install` and Node 22 or later. Separate headless capture at 1440 x 900, 75 seconds per page. At most 200 findings per page, failures first. `passed` and `inapplicable` outcomes are counted, not stored. |
| Keyboard | A [keyboard trap](../glossary.md#keyboard-trap): focus that stays on one element through repeated Tab and Shift+Tab presses. | 2.1.2 (A), rule `keyboard-trap-stuck`. | `src/audit/analyzer/keyboard/` | `keyboard` | Needs review (`expert_review`). Rows from older probe versions: Informational (`informational`). | Up to `max_focusable * 2 + 4` Tab presses (104 at the default of 50). Flags an element only when 4 Tabs and then 4 Shift+Tabs all stay on it. Stops at the first trap, so at most one finding per page. Does not test focus order, focus visibility, or reachability. |
| Focus | A focused control hidden behind a sticky or fixed header or overlay ([focus not obscured](../glossary.md#focus-not-obscured)), and elements with a positive `tabindex`. | 2.4.11 (AA) `focus-not-obscured`; 2.4.3 (A) `focus-order-positive-tabindex`. | `src/audit/analyzer/focus/` | `focus` | Needs review (`expert_review`). | Tests the first 150 focusable elements and the first 150 `[tabindex]` elements. Samples only the centre point of each element, and only when that point is inside the 1440 x 900 viewport. No model. |
| Responsive | Sideways scrolling at 320 CSS px ([reflow](../glossary.md#reflow)), text cut off at about 200% zoom ([resize text](../glossary.md#resize-text)), and text cut off with wider spacing ([text spacing](../glossary.md#text-spacing)). | 1.4.10 (AA) `responsive-reflow-overflow`; 1.4.4 (AA) `responsive-text-clipped`; 1.4.12 (AA) `responsive-text-spacing-clipped`. | `src/audit/analyzer/responsive/` | `responsive` | Needs review (`expert_review`). | Reflow at 320 x 900 with an 8 px tolerance; zoom uses a 640 x 450 viewport as a stand-in for 200%. Clipping means more than 4 px hidden by `overflow: hidden`, skipping `text-overflow: ellipsis`. Up to 5 offenders per check and 2,000 elements scanned. Runs last because it resizes the viewport. |
| Visual | Audio that plays by itself with no control, autoplaying video or `<marquee>` with no pause, and a visual reading order that differs from the DOM order. | 1.4.2 (A) `visual-autoplay-audio-no-control`; 2.2.2 (A) `visual-motion-no-pause`; 1.3.2 (A) `visual-meaningful-sequence`. | `src/audit/analyzer/visual/` | `visual` | Needs review (`expert_review`). Older markup-only motion rows: Informational. | Measures 350 ms of playback instead of trusting `autoplay` markup; audio must last over 3 seconds and video over 5, and every `<marquee>` is a lead. Reading order needs a reachable vision model: one screenshot and one call per page, up to 60 text blocks, at most one finding per page. No flashing (2.3.1) check exists, even though the New scan form hint mentions flashing. |
| Interaction (click-through) | Problems that appear only after a control is used, such as an open menu, dialog, tab, or disclosure (a [DOM state](../glossary.md#dom-state)). | Whatever the axe rule maps to. | `src/audit/analyzer/interaction/` | `axe`, with `revealed_by` set to the operated control's name. | Barrier (`likely_barrier`), because the rows are axe rows. | Needs axe. Up to 100 clicks, 20 per repeated control shape, 5 levels deep, and 120 seconds per page. Only axe re-runs in a revealed state, and problems already present at load are not reported again. Skips controls with destructive names and blocks navigation, non-GET/HEAD/OPTIONS requests, and cross-origin requests. |
| Configured search journeys | Problems on search results pages that exist only after a query is entered. | Whatever the axe rule maps to. | `src/audit/crawler/search.py` | `axe`, with `revealed_by` set to `Configured search`. | Barrier (`likely_barrier`). | Runs only when the scan carries a confirmed search configuration (1 to 6 fields). Defaults to 3 result pages (at most 5) and 20 results (at most 50), within 120 seconds. Needs axe and browser rendering. |
| [Image of text](../glossary.md#image-of-text): [OCR](../glossary.md#ocr), optional vision model, inline SVG text | Words inside images, how the alt text compares with them, and text drawn inside inline `<svg>`. | 1.4.5 (AA) for `essential` images; 1.1.1 (A) for `informational`, `logo`, and `decorative` images with missing alt; otherwise none (BP). Adequate and unclassified groups get no criterion. | `src/audit/extractor/` (including `svg_text.py`), `src/audit/analyzer/ocr/`, `src/audit/analyzer/vlm/`, `src/audit/synthesizer/` | None. Rows live in `images`, `page_images`, `analyses`, and `findings`; issue rows use `image`. | Adequate alt: Informational (`informational`). Otherwise Needs review (`expert_review`), with low confidence when unclassified. | Reads `<img>` and `<picture><source>` only (not CSS backgrounds or `<canvas>`), up to 25 MB per image. An OCR text candidate needs mean word confidence of at least 60 and at least 3 words; SVG and icon files are not OCR'd, and inline SVG text is flagged with no OCR or model. The vision model sees OCR candidates only, and alt adequacy is a string comparison, not a model. Synthesis writes the findings after a completed crawl. |
| Semantic analyzers | Wording that rule engines cannot judge: audio with no transcript, vague link text, vague headings, and missing or vague form labels. | 1.2.1 (A), 2.4.4 (A), 2.4.6 (AA), 3.3.2 (A); rule id `semantic:<sc>`. | `src/audit/analyzer/semantic/` | `semantic` | Needs review (`expert_review`). | Reads the page HTML, so rows have no screenshots; per page it sends at most 40 audio elements, 50 links, 60 headings, and 50 form fields, and drops the rest with only a log line. The whole pass is skipped unless the text default model (`gemma2:9b`) is installed. Only 4 of the 11 default criteria have an analyzer. 2.4.4 drops low-confidence flags; the others keep them as `minor`. |
| Protected image leads | Text in images on protected-scan pages, found in memory by the protected-scan companion. | Stored as 1.4.5 (AA). | `src/audit/protected/companion.py` | `protected_image` | Needs review (`expert_review`). | Protected scans only (see [Protected scans](protected-scans.md)). Image bytes and OCR text are not retained. |

A few rules apply across the table:

- Every browser check needs a [rendered page](../glossary.md#rendered-page).
  The CLI's `--static-only` skips axe and every probe on statically fetched
  pages.
- Inside one browser fetch the order is fixed: axe, keyboard, focus, visual,
  interaction, then responsive, then element screenshots, then the search
  journey (`JsFetcher.fetch` in `src/audit/crawler/js_fetcher.py`).
- Keyboard, focus, responsive, visual, and semantic checks look at the page as
  it loaded. Only axe runs again in states that a click or a search reveals.
- Image classifications come from the vision model prompt
  (`src/audit/analyzer/vlm/prompts/classify_v1.txt`). There, `essential` means
  text that carries unique information and should usually become real text.
  It is not the "essential" exception in WCAG 1.4.5.

### Default state per entry point

The same check can be on in one entry point and off in another. Quoted text is
the toggle label on the New scan form.

| Pipeline | CLI (`audit crawl`) | Web New scan form, "Public website" | Raw API (`POST /api/scans`) | Login scan (`POST /api/local-login-scans`) |
| --- | --- | --- | --- | --- |
| axe-core | On (`--skip-axe`, `--axe-level`) | On: Rule engine "axe-core" (the default) or "Both" | On unless `scan_engine` is `alfa` | On unless `scan_engine` is `alfa` |
| Siteimprove Alfa | Not available | Off: choose "Siteimprove Alfa" or "Both" | Off: `scan_engine` `alfa` or `both` | Off: `scan_engine` `alfa` or `both` |
| Keyboard | On (`--skip-keyboard`) | On ("Check for keyboard traps") | On | On |
| Focus | On (`--skip-focus`) | On ("Check that focus is never hidden") | On | Always on |
| Responsive | On (`--skip-responsive`) | On ("Check narrow screens and zoom") | On | On |
| Visual | On (`--skip-visual`); reading order also needs the vision model | Off ("Check motion and animation") | On | Always off |
| Interaction | On (`--skip-interaction`) | On ("Click through menus, tabs and dialogs") | On | On |
| Configured search journeys | Not available | Off ("Search to discover result pages") | Only with a `search` object | Only with a `search` object |
| Image of text: OCR | On (`--skip-ocr`) | On ("Read text inside images (OCR)") | On | Off; turning it on needs an acknowledgement |
| Image of text: inline SVG text | On | On | On | Only when OCR is on |
| Image of text: vision model | On when Ollama has the model (`--skip-vlm`) | Off ("Review image text with a local vision model") | On when Ollama has the model | Off; needs OCR and an acknowledgement |
| Semantic analyzers | On when Ollama has the model (`--skip-semantic`, `--semantic-criteria`) | Off ("Review wording with local AI") | On when Ollama has the model | Always off |
| Protected image leads | Not produced | Not produced | Not produced | Not produced; protected scans only |

Things that surprise people:

- The raw API reads each `skip_*` field as `bool(body.get(...))`, so a field
  you leave out means the check is on. That is the opposite of the form for
  the vision model, the semantic analyzers, and the visual probe.
- The form and the raw API turn off interaction when the engine is Alfa only
  or static-only mode is on. Login scans turn it off when the engine is Alfa
  only.
- The CLI has no option for Alfa or for search journeys.

## How a check is assigned to a report group

![Diagram of the three report groups. Barrier holds rule-engine failures from axe-core and Siteimprove Alfa, including problems found after clicking or after a configured search; confirm them on the page, fix, and rescan. Needs review holds browser checks, the keyboard trap check, motion checks, text in images whose alt text is missing or does not match, AI checks, and Alfa "cannot tell" results; a person tests and records a decision. Informational holds images whose alt text already matches and older records kept for history; no action is needed.](../images/diagrams/report-groups.png)

In short: rule-engine failures, including those found after clicking, go to
Barrier. Browser checks, AI checks, and Alfa "cannot tell" results go to Needs
review, and records such as matching alt text go to Informational.

### The rule in plain words

Every issue row gets exactly one report group, stored as `review_lane`:

- **[Barrier](../glossary.md#barrier) (`likely_barrier`)**: axe-core
  violations, including the axe rows written by the interaction probe and by
  search journeys, and Alfa `failed` outcomes. Nothing else.
- **[Needs review](../glossary.md#needs-review) (`expert_review`)**: the
  default. It covers keyboard, focus, responsive, visual, semantic, and
  protected image rows, Alfa `cantTell` outcomes, and image groups whose alt
  text is not adequate.
- **[Informational](../glossary.md#informational) (`informational`)**: image
  groups whose alt text comparison is `adequate`, plus keyboard and autoplay
  rows from older probe versions.

The group depends only on the pipeline, the rule id, the Alfa outcome, and the
image classification and alt adequacy. A finding's
[status](../glossary.md#status) never changes its group. The Issues table
labels the groups Barrier, Needs review, and Informational; the issue page
calls the middle group "Needs confirmation" and the dashboard calls it
"Review leads".

### Where the code decides

`list_issues` in `src/audit/web/issues.py` (line 247) builds rows from two
functions and then filters and sorts them (lines 285-298). DOM findings are
grouped by `(pipeline, rule_id, outcome_group)`, where `outcome_group` is set
only for Alfa (`grouped_by_rule` in `src/audit/web/a11y_queries.py`).

`_axe_issue_rows` (line 689) handles every row in `page_a11y_findings`. It
first marks legacy keyboard and visual rows (lines 708-725), then sets
defaults and branches on the pipeline:

| Lines | Branch | Report group | Confidence |
| --- | --- | --- | --- |
| 764-767 | Defaults, before any branch | `expert_review` | medium |
| 768-772 | `semantic` | default | medium |
| 773-796 | `protected_image` | default | medium |
| 797-828 | `keyboard`; legacy rows at 799-822 | default; legacy rows `informational` | medium; legacy low |
| 829-832 | `responsive` | default | medium |
| 833-838 | `focus` | default | medium |
| 839-880 | `visual`; legacy motion rows at 841-863 | default; legacy rows `informational` | medium; legacy low |
| 881-945 | `alfa`; `cant_tell` at 887-895, `failed` at 896-907 | `cant_tell` keeps the default; `failed` sets `likely_barrier` | medium; `failed` high |
| 946-952 | Final `else`: `axe` and any unrecognized pipeline | `likely_barrier` | high |

The image rule lives in `_image_issue_rows` (line 1009). An image group is
`informational` when its alt adequacy is `adequate` (lines 1027 and 1044) and
`expert_review` otherwise. Unclassified groups get low confidence (line 1045),
and adequate or unclassified groups lose their WCAG criterion (line 1029).

Ordering uses `_LANE_RANK` (line 1224): Barrier first, then Needs review, then
Informational. `_sort_rows` applies it to the default `priority_desc` sort and
to `priority_asc`, so priority only orders rows within a group. The
`conformance`, `occurrences_desc`, and `pages_desc` sorts ignore the group.

> **Warning:** the final `else` at lines 946-952 catches `axe` and also every
> pipeline value that has no branch of its own. Those rows get the issue key
> `axe:<rule_id>`, the group `likely_barrier`, high confidence, and the
> summary "Deterministic axe-core rule failure; verify after remediation." As
> soon as a migration allows a new `pipeline` value, its rows appear as
> Barriers unless `_axe_issue_rows` has an explicit branch for it. Also add
> the new value to the pipeline tuples
> in `_rule_meta_for` (line 469) and `_pages_for_issue` (lines 511-520), or
> the issue page looks for its card and its pages in the image tables.

### Downstream consumers

The group feeds these places, so a change to the rule changes all of them:

- **API.** `GET /api/scans/{id}/issues` accepts `review_lane=` with one of the
  three code values and ignores anything else. It always returns scan-wide
  `review_lane_counts` (`api_scan_issues` in `src/audit/web/server.py`).
- **Review app.** The `ReviewLane` type in
  `src/audit/web/frontend/src/api/types.ts` drives the Issues table's Type
  column and filter (`laneLabel` in `routes/Issues.tsx`), the issue evidence
  card (`components/IssueEvidence.tsx`), and the dashboard tiles
  (`routes/Dashboard.tsx`).
- **Audit report and workbook.** `_bucket_rows_into_cards` in
  `src/audit/exports/audit_report.py` sorts rows into issue cards and
  appendices; the Excel workbook reaches it through `build_audit_cards`.
  - Findings already marked `remediated`, `accepted_risk`, or `false_positive`
    move to Appendix A.
  - In a Needs review group, only `in_progress` findings (an expert confirmed
    the barrier) become an issue card. `new` and `reviewing` findings go to
    Appendix B.
  - A Barrier group becomes an issue card only when it has a WCAG criterion
    and is not best practice. Otherwise it goes to Appendix B, along with
    every Informational group.
- **Final-export readiness.** `_unreviewed_actionable_evidence_blockers` in
  `src/audit/web/export_readiness.py` blocks a final export while any finding
  behind a Barrier or Needs review group lacks an expert decision. See
  [False-positive safeguards](#false-positive-safeguards) for the full rule.

Some consumers ignore the group. The CSV, JSON, Jira CSV, and Markdown
evidence inventory exports carry no group field. The read-only report helpers
in `src/audit/mcp_server.py` drop `review_lane` from their issue rows
(`_issue_row`). The comment above `ReviewLane` in `issues.py` says the field
exists to stop UI, MCP, and export renderers from turning review leads into
failures, so treat that as a gap.

### Tests that assert report groups

These tests pin the rule today:

- `tests/unit/test_issues_view.py`:
  - `test_issue_lanes_keep_review_leads_out_of_barrier_totals` (axe and image)
  - `test_adequate_unclassified_image_is_informational_with_real_page_count`
  - `test_list_issues_priority_sort_default` (groups sort first)
  - `test_legacy_keyboard_heuristic_is_informational_not_a_barrier`
  - `test_bidirectional_keyboard_measurement_remains_an_expert_review_lead`
  - `test_legacy_autoplay_markup_is_informational_not_a_barrier`
  - `test_runtime_motion_measurement_remains_an_expert_review_lead`
  - `test_alfa_rows_expose_rule_name_diagnostic_and_outcome_boundary`
- `tests/unit/test_alfa_scan_engine.py`, `tests/ui/test_alfa_outcome_routes.py`,
  `tests/ui/test_expert_workbench_routes.py`,
  `tests/ui/test_report_workflow.py`, `tests/ui/test_accessibility_axe.py`, and
  `tests/ui/test_routes.py` also read `review_lane`.

Known gaps:

- No test asserts `review_lane` for responsive, focus, semantic, or protected
  image rows. The responsive test pins the `responsive:` issue key, which
  would fail if that branch disappeared. Focus rows appear only in the rescan
  comparison tests (`tests/unit/test_report_comparison.py`), which never check
  the group.
- `_LAYER_PIPELINES`, `_REVIEW_ONLY_LAYERS`, and `_FINDING_ONLY_LAYERS` in
  `src/audit/quality_benchmark.py` mirror the group rule for the precision
  gate. A comment there asks you to keep them aligned with `issues.py`, but no
  test cross-checks the two, so update both by hand.

## False-positive safeguards

A [false positive](../glossary.md#false-positive) in the Barrier group costs
the most trust, because Barrier is where people act first. The team's goal is
[zero false positives in the Barrier group](../glossary.md#zero-false-positive-goal),
which is why only rule-engine failures go there. This section lists what
supports that goal and then says plainly what the repo enforces today.

### Safeguards in the product

- **Three report groups.** Probe, model, and heuristic output can only reach
  Needs review or Informational, so it never inflates Barrier totals.
- **Keyboard: both directions.** The probe reports an element only when 4 Tab
  presses and then 4 Shift+Tab presses all stay on it. The code calls the
  second direction "the precision gate" (`_confirm_reverse_exit_blocked` in
  `src/audit/analyzer/keyboard/probe.py`). Escape and iframe heuristics are no
  longer run, and older rows built on them show as Informational.
- **Visual: measured playback.** The motion and audio checks measure
  `currentTime` instead of trusting `autoplay` markup. Older markup-only rows
  show as Informational.
- **axe `incomplete` results are dropped.** `AxeAnalyzer.run` keeps
  `violations` only, so axe's own "needs review" results never become
  Barriers. They are not shown anywhere.
- **Alfa outcomes stay apart.** `failed` and `cantTell` are separate groups
  with separate issue keys, and `cantTell` never becomes a Barrier.
- **Final-export readiness.** A final (non-draft) export through the API needs
  a completed expert evaluation. It also needs every finding behind every
  Barrier and Needs review group to be `in_progress`, `remediated`,
  `accepted_risk`, or `false_positive`; Informational groups are exempt.
  Otherwise the API returns 409 unless the caller asks for a
  [draft export](../glossary.md#draft-export), which is labeled DRAFT.
- **Status history.** Setting `in_progress`, `remediated`, `accepted_risk`,
  or `false_positive` requires a reason of up to 2,000 characters, with common
  secret and identifier patterns redacted. Every status change is recorded in
  `finding_history` (image findings) or `a11y_finding_history` (page findings)
  with the old and new status, the time, and an actor of `system` or `user`,
  not a named person.

### Safeguards in the test suite

**Precision gate (`make quality-gate`).** It scores frozen labels in
`tests/quality/corpora/detection_precision_v1.json` (version `1.0.2`, labels
"synthetic by construction"). Overall and in each layer, the false-discovery
rate must stay below 5% and recall at 80% or more, and each layer needs at
least 20 surfaced results and 5 negative controls. The layers are `axe`,
`alfa`, `behavioral` (keyboard, responsive, focus, visual), `ocr_vlm` (image,
visual), and `semantic`.

- The loader also checks dispositions: `behavioral`, `ocr_vlm`, and
  `semantic` outputs must be review leads, and `axe` outputs must be findings.
- It never runs a detector. Each sample stores what Axcess did with it, so a
  detector code change cannot move the result unless someone edits the
  corpus. Treat it as a guard on recorded labels and group policy, not a live
  test of detector behavior.
- CI runs `tests/quality` on every pull request, and that test asserts the
  same gate. The `make quality-gate` command itself is not a CI step.
- Today every layer scores 0 false positives on 20 surfaced samples. One false
  positive in a layer of 20 would be exactly 5% and fail, but a larger layer
  could carry one and still pass. The gate is "below 5%", not zero.

**Detection evaluations (`make detection-evals`).** Its efficacy lane
re-scores the same frozen corpus. Its efficiency and scale lanes time SQLite
writes and the issue projection on synthetic axe rows at 100, 500, and 1,000
pages. So the only new thing it measures is performance: it does not crawl,
render, run OCR, or call a model. The `detection-evals.yml` workflow runs it on
relevant pull requests, pushes to `main`, a weekly schedule, and on demand.

**Export goldens.** Pinned exports in `tests/unit/golden/` and API goldens in
`tests/ui/golden/` turn a change in grouping, bucketing, or labels into a
visible diff, for the pipelines their fixtures seed. The rich export fixture
has no focus, responsive, or visual rows. `AUDIT_UPDATE_GOLDEN=1` rewrites the
goldens and fails on purpose, and it refuses to run under CI.

**Live semantic calibration (opt-in).** Run it with
`AUDIT_OLLAMA_LIVE=1 uv run pytest tests/integration/test_semantic_pipeline.py -k live`.
It runs only the 2.4.4 analyzer against the labeled pages in
`tests/fixtures/site/sc_2_4_4/` and asserts precision of at least 85% and
recall of at least 75%. The analyzer uses its registry model (`gemma2:9b`), not
the test's `MODEL` constant, and CI never sets the variable, so it only runs by
hand.

### What the repo enforces today

- **Enforced in code:** only axe violations and Alfa `failed` outcomes can be
  Barriers, as long as every pipeline has its own branch (see the warning
  above).
- **Enforced in CI:** the report group unit tests and the corpus gate in
  `tests/quality` run on every pull request.
- **Enforced for final API exports:** an expert decision on every Barrier and
  Needs review finding. The CLI `audit export` command skips this gate and the
  draft labels.
- **Not enforced: zero.** Nothing measures false positives on real sites. An
  axe false positive lands in Barrier until someone marks it `false_positive`.
  The dashboard's Barriers tile says "act without confirmation", which is
  looser than the goal, so confirm each Barrier on the page anyway.
- **Not visible in the repo:** whether `main` requires CI to pass before a
  merge is a branch-protection setting. The desktop release job depends only
  on the two build jobs, not on CI or the detection evaluations.
