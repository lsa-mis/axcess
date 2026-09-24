# Adding or tuning a check

This guide walks you through adding a new check to Axcess or changing how an
existing one behaves. It assumes you already have a working setup from
[CONTRIBUTING.md](../../CONTRIBUTING.md). For what each pipeline does today
and how results are assigned to report groups, see
[Detection pipelines](detection-pipelines.md).

Code references name files and functions rather than line numbers, because
line numbers drift. When a step says "like the focus probe", open that file
and copy its shape.

## Decide the report group first

Before you write any code, decide which report group your check's results
belong in. The group decides where people act first, so it matters more than
any threshold.

- **[Barrier](../glossary.md#barrier) (`likely_barrier`)** is only for a rule
  engine that failed a fixed, machine-testable rule. Today that means axe-core
  violations and Siteimprove Alfa `failed` outcomes.
- **[Needs review](../glossary.md#needs-review) (`expert_review`)** is for
  anything a person has to confirm: browser measurements, heuristics, anything
  a model judged, and engine results such as Alfa `cantTell`. Almost every new
  check belongs here.
- **[Informational](../glossary.md#informational) (`informational`)** is for
  records that show a check ran and found nothing to fix, such as an image
  whose alt text already matches its words.

A useful test: if you cannot name a fixed rule whose failure is a real
barrier every time, the check goes to Needs review. Browser probes repeat
reliably, but they do not see every interaction state or how assistive
technology behaves, which is why the keyboard, focus, responsive, and visual
probes all go to Needs review.
Keeping Barrier this narrow is how we work toward the
[zero false positive goal](../glossary.md#zero-false-positive-goal).

### Why the default for an unknown pipeline is dangerous

`_axe_issue_rows` in `src/audit/web/issues.py` has one branch per known
pipeline and a final `else` meant for axe. Any `pipeline` value without its own
branch falls into that `else` and is treated exactly like axe: issue key
`axe:<rule_id>`, group `likely_barrier`, high confidence, and the summary
"Deterministic axe-core rule failure; verify after remediation."

So the moment your migration allows a new `pipeline` value, every row it
writes shows up as a Barrier. It counts toward the dashboard's Barriers tile,
sorts to the top of the Issues table, and can become an issue card in the audit
report and the workbook. Meanwhile the issue page looks for its card and its
pages in the image tables, because `_rule_meta_for` and `_pages_for_issue`
do not know the new value either.

Nothing fails loudly when this happens, because no test covers an unknown
value. Add the branch in the same change as the migration, and add a test that
asserts the group (step 13 below).

## Checklist: a new browser probe

This checklist follows the focus probe (`src/audit/analyzer/focus/`), the
smallest browser probe, through the code. The analyzers arrived in large
import commits, so there is no small commit that shows one check being added;
the focus probe is the example instead. Replace `x` with your pipeline name.

1. **Analyzer package.** Create `src/audit/analyzer/<x>/` with `__init__.py`,
   `base.py`, and `probe.py`.
   - In `base.py`, copy `FocusFinding`: a frozen dataclass with `rule_id`,
     `target_selector`, `html_snippet`, a `target_hash` property, and
     `to_repo_kwargs()` returning `"pipeline": "<x>"` and `criterion_sc`.
   - Prefix every rule id with the pipeline name, like `focus-not-obscured`.
     The dedupe key `UNIQUE (page_id, rule_id, target_hash)` ignores
     `pipeline`, and an upsert conflict does not update it, so a reused rule
     id would merge into another pipeline's row.
   - In `probe.py`, `run(page)` must never raise. Catch, log, and return what
     you have, because the browser fetch relies on it. Bound the work, as the
     focus probe does with its 150-element cap.
2. **Storage.**
   - Add a migration pair in `src/audit/db/migrations/`:
     `0030_<x>_pipeline.sql` and `0030_<x>_pipeline.rollback.sql` (0030 is the
     next free number today). SQLite cannot change a CHECK in place, so copy
     the column rebuild in `0012_protected_image_pipeline.sql`, the latest
     widening, which lists every current value. The rollback deletes the new
     rows first, like `0012_protected_image_pipeline.rollback.sql`.
   - Copying 0012 as it is fails on today's schema, with
     `error in index idx_a11y_rule_lookup after drop column: no such column: pipeline`.
     Migration `0029_hot_path_indexes.sql` added `idx_a11y_rule_lookup` on
     `(scan_id, pipeline, rule_id, page_id)`, and SQLite will not drop a
     column that an index names. 0012 drops only `idx_a11y_pipeline`.
   - So in both the forward file and the rollback, start with
     `DROP INDEX IF EXISTS idx_a11y_rule_lookup;` next to 0012's
     `DROP INDEX IF EXISTS idx_a11y_pipeline;`. After the rebuild, recreate
     both exactly as 0012 and 0029 define them:

     ```sql
     CREATE INDEX idx_a11y_pipeline ON page_a11y_findings(scan_id, pipeline);
     CREATE INDEX idx_a11y_rule_lookup
         ON page_a11y_findings(scan_id, pipeline, rule_id, page_id);
     ```

   - Before you write the migration, list the indexes that name `pipeline`,
     in case a later migration added another:
     `SELECT name, sql FROM sqlite_master WHERE tbl_name = 'page_a11y_findings' AND type = 'index' AND sql LIKE '%pipeline%';`
   - The [developer guide](developer-guide.md#add-a-migration) shows how to
     apply and roll back a migration safely. Tests pick it up on their own,
     and you can add a forward and rollback test like
     `test_a11y_history_migration_forward_and_rollback` in
     `tests/unit/test_status_history.py`.
   - Add `upsert_<x>_finding` to `src/audit/db/repo.py`, delegating to
     `upsert_keyboard_finding(pipeline="<x>")` like `upsert_focus_finding`.
   - Optional: a per-scan coverage counter, so the report can say how many
     pages the check covered. Add a `scans` column (pattern:
     `0020_method_coverage.sql`) and extend the `Literal` and column map in
     `increment_scan_method_coverage`. Focus and visual have no counter today.
3. **Browser fetch.**
   - In `src/audit/crawler/fetcher.py`, add a `FetchResult` field like
     `focus_findings`.
   - In `src/audit/crawler/js_fetcher.py`, add a `JsFetcher.__init__`
     parameter, a run step in `fetch()`, the findings to the screenshot
     candidates, and the field to the returned `FetchResult`.
   - Order matters. A step that resizes the viewport or injects CSS goes after
     the others, like the responsive probe.
4. **Orchestrator wiring** in `src/audit/crawler/orchestrator.py`.
   - Add a `CrawlConfig` flag like `focus_checks_enabled`.
   - Build the probe in `run_crawl` and pass it through `_LazyJs.__init__` and
     the `_LazyJs(...)` call.
   - Write `_persist_<x>` with the `@_batched_writes` decorator, like
     `_persist_focus`. Call it from `_process_job` when `render_mode == "js"`
     and the flag is on.
   - `_persist_focus` updates `focus_pages_probed` and `focus_findings_total`
     on `CrawlSummary`, so add `<x>_pages_probed` and `<x>_findings_total`
     next to them. Optionally, add a row for them to the end-of-crawl summary
     table in `src/audit/cli.py`, next to "Pages focus-probed (SC 2.4.11)".
   - Add the flag to `config_json_for_scan`, so every scan records whether the
     check ran.
5. **CLI and web toggles.**
   - CLI: a `--skip-<x>` option in `src/audit/cli.py`, passed into
     `CrawlConfig`.
   - Server, in `src/audit/web/server.py`: the raw API body in
     `api_create_scan`, `_build_crawl_config`, and the login scan request
     model `LocalLoginScanRequest` with the `CrawlConfig` built in
     `api_create_local_login_scan`.
   - Login scans hand `run_crawl` a ready-made fetcher, and `_LazyJs` uses an
     injected fetcher as it is, so the probe you build in `run_crawl` never
     reaches a login scan. The rest of step 4 (persistence, counters, and
     `config_json_for_scan`) still applies.
   - `_run_local_login_background` in `server.py` builds that fetcher with
     `run.session.create_shared_js_fetcher(...)`, which takes one parameter
     per probe (`src/audit/protected/session.py`). Add a `<x>_probe`
     parameter there, pass it on to `JsFetcher`, and pass the probe from
     `_run_local_login_background`, gated on the config flag the way
     `responsive_probe` is. If you only set the flag, the probe never runs in
     a login scan, and nothing fails.
   - Protected scans run only axe-core, Alfa, and the keyboard, responsive,
     and focus probes, plus the protected image lead. They build their own
     config in `src/audit/web/protected_api.py` and run checks in the
     companion. If your check belongs there, every one of these closed lists
     needs the new value, or its rows show as "unavailable" or are rejected:
     - the probe build in `_ProtectedBrowserCrawler.crawl` and the index
       rows in `_index_findings_from_result`, in
       `src/audit/protected/companion.py`;
     - `ProtectedIndexPipeline` in `src/audit/protected/models.py`;
     - the source layer set in `_protected_issue_group_payload` in
       `src/audit/web/protected_api.py`;
     - `_PIPELINE_LABELS` in `src/audit/protected/export.py`;
     - the `ProtectedIssueIndexGroup.source_layer` union in
       `frontend/src/api/types.ts`, and `SOURCE_LABEL` in
       `frontend/src/routes/ProtectedIssueIndex.tsx`;
     - the protected pipeline enum in `tests/ui/golden/api_openapi.json`
       (step 12 regenerates it).
   - Review app, under `src/audit/web/frontend/src/`: the `NewScanPayload`
     type in `api/types.ts`; `SETTING_KEYS`, `PUBLIC_DEFAULTS`,
     `LOGIN_POLICY`, `SwitchKey`, and `SWITCH_FIELDS` in
     `components/newScan/scanPolicy.ts`; the switch in `ChecksGroup.tsx`; the
     label and hint in `SWITCHES` in `copy.ts`; the summaries in
     `DefaultSettingsCard.tsx` and `ScanSummaryCard.tsx`; and the retry
     settings in `routes/ScanDetail.tsx`. Searching the frontend for
     `skip_focus` finds every spot except `copy.ts`, whose `SWITCHES` entry
     is keyed `focus:`.
   - Choose each entry point's default on purpose. The raw API treats a
     missing `skip_<x>` field as "on".
6. **Report group branch** in `src/audit/web/issues.py`. Do this in the same
   change as the migration.
   - Add `elif pipeline == "<x>":` to `_axe_issue_rows`. Set
     `issue_key = f"{pipeline}:{raw_rule_id}"`, a default title, and an
     `evidence_summary` that tells a reviewer what to confirm. Leave
     `review_lane` at its `expert_review` default unless you decided otherwise
     above.
   - Add `"<x>"` to the pipeline tuples in `_rule_meta_for` and
     `_pages_for_issue`.
7. **Report card.**
   - Add an entry under `semantic_criteria:` in
     `src/audit/rules/audit_report.yaml`, keyed by the WCAG success criterion.
     Probe rows find their card by criterion, so one card covers every rule
     id for that criterion.
   - Copy the fields of the `"2.4.11"` card, from `title` through
     `confidence_default`.
   - Leave `rules/remediation.yaml` alone; it holds image-of-text hints only.
8. **Coverage.**
   - In `src/audit/rules/wcag_coverage.yaml`, update `method`, `pipelines`,
     and `confidence` for the criterion. The file's header explains each
     value.
   - No written rule picks `method` and `confidence` for a browser probe, and
     today's values differ. The responsive criteria (1.4.4, 1.4.10, and
     1.4.12) are `automated` with `high` confidence, while the keyboard and
     focus criteria (2.1.2, 2.4.3, and 2.4.11) are `partial` with `medium`,
     although all of these rows land in Needs review. Agree on the values in
     review, and never claim more than the probe can show.
   - Three different fields are called confidence. The matrix `confidence`
     here is what the public site's coverage page shows ("Confidence: high").
     A card's `confidence_default` in `audit_report.yaml` is what the audit
     report shows on the issue card. An issue's `evidence_confidence`, set
     in `issues.py`, is what the review app shows on the issue page.
   - Add the name to `PIPELINES` in `src/audit/coverage_matrix.py`, or the
     loader rejects the matrix.
   - Update `SHIPPED_PIPELINE_SCS` in `tests/unit/test_coverage_matrix.py`.
   - In `src/audit/web/coverage_status.py`, add a `SHIPPED` entry and update
     any `ROADMAP` item the check delivers. The in-app Product Roadmap page
     (`/tracking`) and the public site read this file.
9. **Methods used and rescan comparison.**
   - Add a row to `_methods_used` in `src/audit/web/server.py`. It feeds the
     Overview's "What this scan actually checked" card.
   - In `src/audit/web/comparison.py`, extend the `Pipeline` literal, the
     `PIPELINES` tuple, and `_FLAGS`. Rows whose pipeline is not in
     `PIPELINES` are silently left out of the rescan comparison.
   - If you added a counter, add it to `_COUNTERS`. If you did not, add the
     pipeline to the `{"focus", "visual"}` set in `_coverage`; otherwise
     `_coverage` looks it up in `_COUNTERS` and raises `KeyError`.
10. **Frontend types and labels**, under `src/audit/web/frontend/src/`:
    - the `DetectionPipeline` union in `api/types.ts`;
    - the pipeline labels in `routes/PageEvidence.tsx`;
    - the `ScanMethodCoverage.key` union in `api/types.ts`, if you added a
      row to `_methods_used`. It is a closed union, so add the key there
      before `METHOD_PIPELINE`, or `make typecheck` fails;
    - `METHOD_PIPELINE` in `components/MethodCoverageLedger.tsx`;
    - `PIPELINES` in `routes/Diff.tsx`, the rescan comparison page's labels
      and its Detection method filter. A missing entry shows the raw pipeline
      name as the label, and the pipeline is missing from the filter.
11. **Exports.**
    - In `src/audit/exports/audit_report.py`: `_PIPELINE_LABEL`,
      `_PIPELINE_COVERAGE`, and the hard-coded pipeline tuples in the location
      query and in `_methods_line`.
    - Also in `audit_report.py`, add an `<x>:` branch to `_meta_for_row` that
      looks the card up by `row.wcag_sc` in `semantic_criteria`, like the
      `keyboard:` branch. `_meta_for_row` handles only `axe:`, `semantic:`,
      and `keyboard:` keys and sends every other key to the image cards,
      where it finds nothing.
    - That is a known bug today for responsive, focus, and visual rows. Their
      audit report cards lack the Manual and Automated verify lines and always
      show Medium confidence, even where the card says high (1.4.10, 1.4.12,
      and 2.4.3). The issue page and the workbook's other ticket fields are
      not affected, because they use `_rule_meta_for` in `issues.py`, which
      handles these pipelines; the workbook's fix options are the exception
      (see below). Until the bug is fixed, read verification steps
      for those issues on the issue page or in the workbook.
    - Alfa rows have no card on purpose: `_rule_meta_for` returns nothing for
      them either, and Alfa's own rule documentation is the remediation lead.
    - The workbook's fix options come from `fix_options_for`, which uses the
      same `_meta_for_row` lookup. No `semantic_criteria` card has
      `fix_options` today, so if you want workbook fix options for your check,
      add them to its card as well as adding the `_meta_for_row` branch.
    - `_SOURCE_LABELS` in `jira_export.py` and in `markdown_report.py`.
    - The workbook reuses `_PIPELINE_LABEL`, so it needs no change of its own.
12. **Goldens.** `tests/ui/golden/api_openapi.json` pins the pipeline
    enums, and a new probe can also change the export goldens. Regenerate
    them with:

    ```bash
    AUDIT_UPDATE_GOLDEN=1 uv run pytest tests/ui/test_api_surface.py \
      tests/ui/test_api_contract.py tests/unit/test_export_goldens.py \
      tests/unit/test_audit_report.py tests/unit/test_exports_csv_json.py \
      tests/unit/test_exports_jira_markdown.py
    ```

    The API surface and contract tests and `test_export_goldens.py` write
    their goldens and fail on purpose (under `CI` they refuse to write).
    `test_audit_report.py`, `test_exports_csv_json.py`, and
    `test_exports_jira_markdown.py` write theirs and pass, with no `CI`
    guard. Either way, review `git diff tests/ui/golden tests/unit/golden`,
    then run the same tests again without the variable.
13. **Tests and fixtures.**
    - Fixture pages in `tests/fixtures/site/<x>/`, with failing and clean
      cases. The focus probe has `clean.html`, `obscured.html`, and
      `tabindex.html`.
    - An integration test like `tests/integration/test_focus_probe.py`, and a
      unit test for the dataclass like `tests/unit/test_keyboard_probe_base.py`.
    - A report group test in `tests/unit/test_issues_view.py` that asserts
      `review_lane`, `evidence_confidence`, `issue_key`, and the card fallback.
      Responsive and focus have no such test today, so please do not widen
      that gap.
    - Optional: rows in `tests/support/rich_scan.py`, so the export goldens
      cover the pipeline. It seeds no focus, responsive, or visual rows today.
    - A route test that the new toggle reaches `CrawlConfig`, because the raw
      API treats a missing field as "on". Copy the `skip_focus` case in
      `test_api_create_scan_respects_whole_host` in `tests/ui/test_routes.py`.
    - Decide whether `tests/integration/test_crawl_end_to_end.py` should turn
      the probe off. It turns the keyboard, responsive, focus, and visual
      probes off explicitly, so a new probe that is on by default runs inside
      that suite unless you add it there.
14. **Precision corpus.**
    - Add the pipeline to the right layer in `_LAYER_PIPELINES` in
      `src/audit/quality_benchmark.py`, usually `behavioral`, or the loader
      rejects its samples. If your check changes the group policy, update
      `_REVIEW_ONLY_LAYERS` or `_FINDING_ONLY_LAYERS` to match `issues.py`;
      no test checks that for you.
    - Add labeled samples to `tests/quality/corpora/detection_precision_v1.json`
      and bump `corpus_version`. Also update the corpus's `producers` entry
      for the layer so it names your probe; today `behavioral` reads "Axcess
      keyboard, responsive, focus, and deterministic motion probes".
    - Update the pinned version and pipeline set in
      `tests/quality/test_detection_precision_gate.py`.
    - Follow [the corpus rules](../../tests/quality/README.md): never relabel
      a sample to make the gate pass.
15. **Glossary.** If the check introduces a term people will see in the app or
    a report, add it to [the glossary](../glossary.md) and link to it
    everywhere else. Check that the Needs review and Browser check entries
    still describe what goes there.
16. **Public site.** `site/build.py` renders the
    [What Axcess checks](https://lsa-mis.github.io/axcess/coverage/) page from
    `wcag_coverage.yaml` and `coverage_status.py`.
    - Add a display name for the pipeline to `PIPE_NAMES` in `site/build.py`
      and to `PIPELINE_NAMES` in `site/volume.py`.
    - Update the hand-written copy that lists the checks. It is spread over
      several pages in `site/build.py`: `home()`, `how_it_works()` (the check
      cards and the Needs review text), the `CHECKS` table that
      `checks_sections()` renders (including its Siteimprove and axe
      DevTools columns), and `faq()`.
    - Run `make site` and commit the regenerated `site/**/index.html`, as
      [Editing the public site](../../CONTRIBUTING.md#editing-the-public-site)
      explains.
17. **These docs.** Add the check to both tables in
    [Detection pipelines](detection-pipelines.md).
18. **Other docs that list the checks by hand.**
    - [The coverage tracker](../coverage-tracker.md): its table of shipped
      checks and its roadmap. `coverage_status.py` describes the same data
      but does not generate this file.
    - The list of checks in the [README](../../README.md).
    - [Reading your report](../reading-your-report.md), which says the focus
      and visual checks have no row under "What this scan actually checked".
      Change it if you added a `_methods_used` row.
    - The report groups diagram, if your check changes what a group holds.
      Follow the [diagram sources guide](../images/diagrams/source/README.md),
      then update its alt text everywhere it appears: `README.md`,
      `docs/reading-your-report.md`, [Detection pipelines](detection-pipelines.md),
      and `REPORT_GROUPS_ALT` in `site/build.py`.
19. **Desktop build.** `desktop/backend.spec` lists the data folders the
    packaged app includes, by hand. If your probe reads any file that is not
    Python (JavaScript, JSON, or a prompt), add its folder to `datas` and
    check a packaged build with `make desktop-backend`. Merging to `main`
    publishes a desktop release with no CI gate, as
    [Releases](releases.md#what-does-not-gate-a-release) explains, so get CI
    and the browser suites green first.

## Adding axe rules or another engine

### New axe rules

New axe rules need no registration. They come from the committed bundle
`src/audit/web/static/axe.min.js` (axe-core 4.10.2), and `AxeAnalyzer` picks
them by WCAG level tag plus `best-practice`. axe's default exclusions still
apply, so experimental and deprecated rules never run.

- **Upgrading axe** means replacing that file. Treat it as a producer change:
  update the `producers` entry in the precision corpus and bump
  `corpus_version`, as [DETECTION_EFFICACY.md](../../DETECTION_EFFICACY.md)
  asks.
- **Cards.** Every axe rule already lands in Barrier; a card makes it
  readable. Add one under `axe_rules:` in `audit_report.yaml`, keyed by rule
  id. Without a card, the row's title falls back to axe's own help text with
  no what, why, or fix, and the audit report marks the card "Human review
  needed".
- **Card values win.** A card's `wcag_sc` and `wcag_level` override what axe
  stored. The `tabindex` card, for example, shows axe's best-practice rule as
  2.4.3, Level A.
- **Coverage.** If a rule changes what Axcess can say about a criterion,
  update `wcag_coverage.yaml` too.

### Another rule engine

Follow the Alfa template, then work through the browser probe checklist for
everything downstream:

- An analyzer and evidence parser like `src/audit/analyzer/alfa.py` and
  `alfa_evidence.py`, with any runner kept in its own folder like
  `src/audit/alfa_runner/`.
- Its own upsert and counters, like `upsert_alfa_finding` and
  `increment_scan_alfa_counters` in `repo.py`.
- A migration like `0010_alfa_scan_engine.sql`, which added `engine_outcome`
  (`failed` or `cant_tell`) and widened the pipeline CHECK.
- Outcome subgroups in `grouped_by_rule` (`src/audit/web/a11y_queries.py`),
  so a failure and a "cannot tell" result never share an issue group. Today
  only Alfa gets subgroups.
- An explicit branch in `_axe_issue_rows`. The Alfa branch sets Barrier only
  for `failed`.
- The per-page hook in `_process_job` and engine selection through
  `scan_engine` in the server and the form.
- A decision about coverage credit. `PIPELINES` in `coverage_matrix.py` has no
  `alfa`, so the coverage matrix credits no criterion to Alfa today.

## Adding a semantic analyzer

The docstring in `src/audit/analyzer/semantic/registry.py` and
`src/audit/analyzer/semantic/prompts/README.md` describe these steps. This list
also corrects the places where they have drifted.

1. **Analyzer class.**
   - Write `src/audit/analyzer/semantic/analyzers/sc_<n>_<n>_<n>.py`,
     implementing the `SemanticAnalyzer` protocol in `semantic/base.py`.
   - Copy `sc_2_4_6.py`: set `criterion_sc`, accept `model=`, load the prompt
     with `importlib.resources`, and set `self.prompt_version`.
   - Fail soft by returning an empty list and logging a warning.
   - Export the class from `analyzers/__init__.py`.
2. **Register it.** Add a `{sc: cls}` row to `_REGISTRY` in `registry.py`.
   Today it holds 1.2.1, 2.4.4, 2.4.6, and 3.3.2. A requested criterion with
   no row is logged as `semantic.unknown_criterion` and skipped.
3. **Prompt.** Add `semantic/prompts/sc_<n>_<n>_<n>_<slug>.txt` with an
   `{elements}` placeholder. The file is filled with `str.format`, so write
   literal braces as `{{` and `}}`. Ask for a top-level `violations` array,
   which is what all four analyzers parse; the README's output schema
   (`overall_violation`, `violated_elements`) does not match the code.
4. **Extraction.** Reuse or add a function in `semantic/extractor.py`:
   `extract_links`, `extract_headings`, `extract_form_fields`, or
   `extract_media`. Cap the elements sent per call, as the existing analyzers
   do (40 to 60). Anything past the cap is dropped with only a log line.
5. **Report card.** Add an entry under `semantic_criteria:` in
   `audit_report.yaml`, keyed by criterion. 1.2.1, 2.4.6, and 3.3.2 have none
   today, so their rows are titled "WCAG SC <sc> (LLM-detected)" with no what,
   why, or fix.
6. **Model pick (optional).** Add a `criteria:` entry in
   `src/audit/rules/analyzer_models.yaml`; otherwise the analyzer uses the
   `text` default. See [Model settings](#model-settings).
7. **Default criteria.** The default list is `CrawlConfig.semantic_criteria`
   in `src/audit/crawler/orchestrator.py`, not `src/audit/config.py` as the
   prompts README says. It already names 11 criteria, and 7 of them (2.4.9,
   2.4.10, 2.5.3, 1.3.5, 1.3.1, 4.1.2, and 1.1.1) have no analyzer, so each
   crawl logs and skips them. Registering an analyzer for one of those 7
   turns it on by default for CLI and raw API scans, whenever the semantic
   pass runs.
8. **Tests and fixtures.**
   - A unit test with a fake provider, like
     `tests/unit/test_semantic_sc_2_4_6.py`.
   - Fixture pages in `tests/fixtures/site/sc_<n>_<n>_<n>/`.
   - Registry behavior in `tests/unit/test_semantic_runner_and_registry.py`.
   - Only 2.4.4 has a live calibration against labeled pages; consider a
     labeled set for yours.
9. **Coverage.**
   - `wcag_coverage.yaml` for the criterion.
   - In `coverage_status.py`, the `ROADMAP` item and the semantic `SHIPPED`
     entry, whose `scs` text and "Four per-criterion analyzers are registered"
     note are written by hand.
   - The semantic description in `_methods_used` (`server.py`), which names
     the topics covered.
10. **Precision corpus.** Add labeled samples for `semantic:<sc>` to the
    `semantic` layer and bump `corpus_version`.
11. **Report group.** Nothing to do: semantic rows always go to Needs review.
12. **Desktop build.** `desktop/backend.spec` lists data folders by hand. It
    includes `analyzer/vlm/prompts` but not `analyzer/semantic/prompts`, so
    check that a packaged build can load your prompt.

## Tuning a check

### Where thresholds live

| Check | Setting and current value | Where |
| --- | --- | --- |
| OCR text candidate | `ocr_min_confidence` 60 (mean word confidence), `ocr_min_word_count` 3 | `Settings` in `src/audit/config.py`, read from `AUDIT_OCR_MIN_CONFIDENCE` and `AUDIT_OCR_MIN_WORD_COUNT`; the CLI and server copy them into `CrawlConfig`. |
| axe and Alfa level | `axe_level` "AA" | `CrawlConfig`; CLI `--axe-level`; form "Standard to check against". |
| Keyboard | `DEFAULT_STUCK_THRESHOLD` 4, `DEFAULT_MAX_FOCUSABLE` 50 | `src/audit/analyzer/keyboard/probe.py`; `keyboard_probe_max_focusable` in `CrawlConfig`; CLI `--keyboard-max-focusable` (5 to 500). |
| Focus | `MAX_FOCUSABLE` 150 | `src/audit/analyzer/focus/probe.py` |
| Responsive | `_REFLOW_VIEWPORT` 320 x 900, `_ZOOM_VIEWPORT` 640 x 450, `_OVERFLOW_TOLERANCE_PX` 8, clipping over 4 px in `_CLIPPED_TEXT_JS`, `_MAX_ELEMENTS_SCANNED` 2000, `_MAX_OFFENDERS_PER_CHECK` 5, spacing values in `_TEXT_SPACING_CSS` | `src/audit/analyzer/responsive/probe.py` |
| Visual | 350 ms sample, playback advance over 0.05 s, audio over 3 s, video over 5 s (all in `_MOTION_JS`); `_MAX_BLOCKS` 60 for reading order | `src/audit/analyzer/visual/probe.py` |
| Interaction | `DEFAULT_MAX_CLICKS` 100, `DEFAULT_MAX_REPEATED` 20, `DEFAULT_MAX_DEPTH` 5, `DEFAULT_TIMEOUT_S` 120 | `src/audit/analyzer/interaction/probe.py`; `interaction_max_*` in `CrawlConfig`. No CLI option. |
| Semantic | `MAX_MEDIA_PER_CALL` 40, `MAX_LINKS_PER_CALL` 50, `MAX_HEADINGS_PER_CALL` 60, `MAX_FIELDS_PER_CALL` 50; `semantic_concurrency` 1 | Each analyzer module in `src/audit/analyzer/semantic/analyzers/`; `CrawlConfig`. |
| Alfa | `alfa_timeout_s` 75; `MAX_FINDINGS` 200, `MAX_EVIDENCE_BYTES` 4000 | `CrawlConfig`; `src/audit/alfa_runner/evidence.mjs` |
| Search journeys | `max_result_pages` 3 (1 to 5), `max_results` 20 (1 to 50), `timeout_ms` 5000 (500 to 15000), set per scan | `SearchConfig` in `src/audit/crawler/search.py` |
| Image alt adequacy | `_ADEQUATE_RATIO` 85, `_PARTIAL_RATIO` 55 | `src/audit/synthesizer/alt_compare.py` |
| Image priority and severity | `CLASSIFICATION_WEIGHTS`, `ADEQUACY_WEIGHTS`, severity cutoffs 8, 5, and 2 | `src/audit/synthesizer/priority.py` |
| Image fix hints | First matching `(classification, adequacy)` rule wins; `*` is a wildcard | `src/audit/rules/remediation.yaml` |
| Issue priority | `_SEVERITY_WEIGHT` and `_priority`; the Issues table shows High from 6 and Medium from 3 | `src/audit/web/issues.py`; `priorityTier` in `routes/Issues.tsx`. Priority orders rows only within a report group. |

A threshold change changes what a detector reports, so treat it like a test
contract. [Prompt versioning](#prompt-versioning) below explains what that
means here.

### Model settings

- `src/audit/rules/analyzer_models.yaml` is read by
  `src/audit/analyzer/model_registry.py`, which caches it for the life of the
  process. Tests call `reset_cache()`.
- `get_pick` resolves a model in this order: `criteria[<sc>]`, then
  `defaults[<kind>]`, then a hard-coded fallback.
- Only the semantic analyzers read this file. The `text` default is
  `gemma2:9b`, with a comment calling it a temporary demo pin to flip back to
  `qwen2.5:7b-instruct`. 2.4.4 uses `gemma2:9b`; 1.2.1, 2.4.6, and 3.3.2 use
  `qwen2.5:7b-instruct`.
- The semantic health check needs the `text` default's exact tag in Ollama's
  `/api/tags`. Without it the whole semantic pass is skipped with a
  `semantic.unavailable` warning, whatever the per-criterion picks say.
- `make fetch-analyzer-models` pulls the `required` and `recommended` tiers:
  `qwen3-vl:2b-instruct`, `qwen2.5:7b-instruct`, `qwen2.5-vl:7b`,
  `qwen2.5-coder:7b-instruct`, and `llama3.2:3b-instruct`. It does not pull
  `gemma2:9b`, so pull that yourself or change the `text` default.
  `make fetch-models` pulls only `qwen3-vl:2b-instruct` and `moondream:2b`.
- The vision pipelines ignore `analyzer_models.yaml`. The image-of-text
  classifier and the reading-order check both use `AUDIT_VLM_MODEL` (default
  `qwen3-vl:2b-instruct`) through `CrawlConfig.vlm_model`. The YAML's `vision`
  defaults and its `"1.4.5"` entry are read by no scan pipeline.
- The classifier's prompt file comes from `AUDIT_VLM_PROMPT_NAME` (default
  `classify_v1.txt`). Ollama's address, `AUDIT_OLLAMA_BASE_URL` (default
  `http://localhost:11434`), is shared by the vision and semantic passes. A
  login scan with the vision model on refuses to start unless that address is
  a loopback address.

### Prompt versioning

- **Image classifier.** The prompt is
  `src/audit/analyzer/vlm/prompts/classify_v1.txt`. Its version is `v1-` plus
  the first 12 hex characters of the prompt's SHA-256 (`prompt_content_version`
  in `src/audit/analyzer/ollama_base.py`). Each image's `analyses` row stores
  `{"ocr", "vlm", "prompt"}` in `model_versions_json`, unique per image and
  version set, so a new prompt or model adds a row instead of overwriting one.
- **Semantic analyzers.** They compute `prompt_version` the same way, but
  nothing stores it, because `upsert_semantic_finding` has no prompt or model
  column. The prompts README says the hash is stored; that section is out of
  date.
- **Reading-order check.** Its prompt is the inline `_PROMPT` string in
  `src/audit/analyzer/visual/probe.py`, with no version at all.
- **The scan record.** `scans.config_json` (`config_json_for_scan`) records
  which checks were on, the axe level, the interaction limits, and the search
  setup. It records no model name, prompt, semantic criteria list, OCR
  threshold, or keyboard focusable cap.

So a completed report cannot tell you which model or prompt produced its
semantic or reading-order findings. When you change a model, prompt,
threshold, or expected result, treat it as a test contract, as
[DETECTION_EFFICACY.md](../../DETECTION_EFFICACY.md) asks. Explain why, bump
`corpus_version`, and follow [the corpus rules](../../tests/quality/README.md).

## Verification before merging

Run the standard gates in [CONTRIBUTING.md](../../CONTRIBUTING.md) first. For a
change to a check, also run the commands that match what you touched:

| Command | What it shows |
| --- | --- |
| `uv run pytest tests/unit/test_issues_view.py` | Report groups, issue keys, and card fallbacks, including your new group test. |
| `uv run pytest tests/integration/test_<x>_probe.py` | The probe against its fixture pages in a real browser. Needs Playwright Chromium from `make setup`. |
| `make quality-gate` | The precision corpus loads and passes, and its pins match. |
| `make detection-evals` | The efficacy, efficiency, and scale gates. Reports land in `artifacts/detection-evals/`. |
| `uv run pytest tests/unit/test_export_goldens.py tests/ui/test_api_contract.py tests/ui/test_api_surface.py` | Export and API goldens still match. |
| `make site`, then `uv run pytest tests/unit/test_coverage_matrix.py tests/unit/test_site_build.py` | The coverage matrix loads, and the site's numbers agree with it. |
| `make a11y-check` | The review app's axe tests, if you changed the New scan form. |
| `make test` | Everything. Run it when a change crosses the crawler, storage, or UI, which a new probe always does. |

Two more things before you ask for review:

- Probe tests are browser tests, which CI runs on a pull request only when it
  carries the `run-browser-tests` label. Add the label, as
  [What CI runs](../../CONTRIBUTING.md#what-ci-runs) explains.
- Commit the regenerated `site/**/index.html` in the same pull request as the
  coverage change, so the public site matches the code.
