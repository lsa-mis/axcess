# axe-core on its own compared with the Axcess rule check (axe)

Date: 2026-11-10. Pages: the local fixture site in `tests/fixtures/site`.
One Axcess scan only (report 1 in a separate scratch database, not
`data/audit.db`).

## Main point

At page load, Axcess reports exactly what axe-core reports. On the same 53
pages, axe-core found 113 failing elements under 11 rules, and Axcess stored
113 occurrences under the same 11 rules. Every one matched by page, rule,
element locator (CSS selector) and element code (HTML). Nothing appeared on
only one side.

The numbers you see in Axcess still differ from a plain axe-core report, for
four reasons that have nothing to do with how axe runs:

| Difference | Effect in this scan |
| --- | --- |
| Click-Through adds occurrences that only exist after a control is clicked. | +39 occurrences, 1 extra rule |
| The Issues table counts a repeated element once. | 152 stored rows show as 145 occurrences |
| Axcess drops axe-core's "incomplete" (needs review) results. | 9 results not shown |
| Axcess does not run axe on pages that fail to load. | 26 "not found" pages skipped |

Neither result proves that a site meets WCAG. axe-core checks only what
fixed rules can test, and both sides here ran the same rules.

## What was compared

| Side | What ran |
| --- | --- |
| Axcess | `audit crawl http://127.0.0.1:8000/all-pages/ --whole-host` with the rule check (axe) and Click-Through on, and the keyboard, zoom and layout, focus, motion, AI review and image text checks off. WCAG 2.1, Level AA (the app's defaults). |
| axe-core | Run directly with Playwright on every page address Axcess stored, four ways: version 4.11.3 (from the frontend packages) and version 4.10.2 (the copy Axcess ships), each with axe's default settings and with Axcess's tag list. |

The direct runs used the same browser setup as Axcess: Chromium 145, a
1440 by 900 window, the same user agent, wait for load and then for the
network to go quiet. They did not call any Axcess analyzer, storage or issue
code.

The fixture home page links to only 6 pages. To reach all of them in one
scan, the local server added one generated page, `/all-pages/`, that links
to every fixture file. The fixture files were served unchanged.

Axcess stored 79 pages: 53 loaded (status 200) and 26 were "not found"
(status 404, links in the fixtures to pages that do not exist).

## Counts for each rule

"Failing elements" is axe-core's `violations` list, one count per element.
All four axe-core runs gave the same numbers, so they share one column.

| axe rule | axe-core: failing elements (pages) | Axcess: at page load | Axcess: after clicking | Axcess: stored rows | Issues table: occurrences (pages) | Repeats left out | axe-core: needs review |
| --- | --- | --- | --- | --- | --- | --- | --- |
| aria-input-field-name | 0 | 0 | 1 | 1 | 1 (1) | 0 | 0 |
| aria-required-children | 1 (1) | 1 | 1 | 2 | 2 (2) | 0 | 0 |
| bypass | 0 | 0 | 0 | 0 | none | none | 3 |
| color-contrast | 1 (1) | 1 | 0 | 1 | 1 (1) | 0 | 2 |
| frame-tested | 0 | 0 | 0 | 0 | none | none | 4 |
| frame-title | 1 (1) | 1 | 0 | 1 | 1 (1) | 0 | 0 |
| html-has-lang | 1 (1) | 1 | 0 | 1 | 1 (1) | 0 | 0 |
| image-alt | 2 (2) | 2 | 2 | 4 | 4 (4) | 0 | 0 |
| label | 7 (5) | 7 | 26 | 33 | 29 (12) | 4 | 0 |
| landmark-one-main | 24 (24) | 24 | 0 | 24 | 24 (24) | 0 | 0 |
| link-name | 3 (2) | 3 | 0 | 3 | 3 (2) | 0 | 0 |
| page-has-heading-one | 14 (14) | 14 | 0 | 14 | 14 (14) | 0 | 0 |
| region | 58 (22) | 58 | 9 | 67 | 64 (21) | 3 | 0 |
| tabindex | 1 (1) | 1 | 0 | 1 | 1 (1) | 0 | 0 |
| **Total** | **113** | **113** | **39** | **152** | **145** | **7** | **9** |

The Issues table shows 12 axe issue types: the 11 rules that fail at page
load, plus `aria-input-field-name`, which fails only after clicking.

## Each difference, with evidence

### 1. Click-Through adds occurrences (Axcess only)

Axcess stored 39 occurrences on 11 pages that appear only after a control is
clicked. A page-load axe-core run cannot see them. They are stored with
`pipeline='axe'` and the control's name in `revealed_by`
(`_persist_interaction` in `src/audit/crawler/orchestrator.py`), and they are
counted in the same `axe:<rule>` issue type.

Five of those rows are an element that was already stored, stored again
because its code changed between page states:

- `div[role="tablist"]` on `/interaction/stress.html`: once at page load and
  twice after clicking, because `aria-selected` moved. axe-core at page load
  counts it once; Axcess shows 3 occurrences.
- Three unlabelled fields (`#guest-name`, `#field-1`, `#nav-panel > input`):
  two rows each, because the later copy has an empty `style=""`. The fixture
  page's own script does not add that attribute. I did not find which step
  adds it.

The cause is the row key: page, rule, and a hash of rule, locator and element
code (`target_hash` in `src/audit/analyzer/axe.py`).

### 2. The Issues table counts a repeated element once (Axcess only)

`_first_instances` in `src/audit/web/issues.py` reports an element once when
the same rule, locator and element code appear on a later page. Here it left
out 7 rows:

| Rule | Element | What repeated |
| --- | --- | --- |
| label | `#unlabelled` | The same field on 4 addresses of one single-page app. 3 left out. |
| label | `#guest-name` | Same code on two different fixture pages. 1 left out. |
| region | `p`, `h1` | `/` and `/index.html` are the same document. 2 left out. |
| region | `form` | Two different forms on two different pages. 1 left out. |

The last row is worth a look. `/sc_3_3_2/clean_form.html` and
`/sc_3_3_2/unlabelled_form.html` hold different forms, but axe-core shortens
a long element's code to its opening tag, `<form>`, so both have the same
locator, code and hash. axe-core counts 2 elements; Axcess shows 1.

Page-level results (`html`) are never merged, so `landmark-one-main` and
`page-has-heading-one` match axe-core exactly.

### 3. "Incomplete" results are dropped (axe-core only)

`AxeAnalyzer.run` returns only `r.violations`
(`src/audit/analyzer/axe.py`, line 319). axe-core also returned 9 results it
could not decide:

- `color-contrast`, 2: text over an image on `/gallery.html` and
  `/saved-styles/index.html`.
- `bypass`, 3: no skip link, heading or landmark found.
- `frame-tested`, 4: "The iframe still has to be tested with axe-core".

The `frame-tested` results matter most. Axcess loads axe into the page but
not into its frames, so content inside a frame is not checked at page load,
and the one signal that says so is dropped. The Click-Through docstring in
`src/audit/analyzer/interaction/probe.py` says the same. Tools such as
`@axe-core/cli` and the axe browser extension load axe into every frame, so
they can report more on pages with frames. I did not measure how much (see
"Not done").

### 4. Pages that fail to load are skipped (axe-core only)

Axcess runs axe only on a successful HTML response
(`src/audit/crawler/js_fetcher.py`, lines 370 to 378). Run on the 26 "not
found" pages, axe-core reported 130 failing elements (`region` 104,
`landmark-one-main` 26), all about the server's error page. A tool given the
same address list would include them.

### Checked and found no difference on these pages

| Possible cause | What I ran | Result |
| --- | --- | --- |
| axe-core version | 4.10.2 against 4.11.3 | Same 113 failures and same 9 "incomplete". Only change: 4.11.3 treats 17 links as "does not apply" under `link-in-text-block` where 4.10.2 passed them. Axcess stores neither. |
| Rule settings | axe defaults against Axcess's tags (`wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `best-practice`) | The same 89 rules ran. |
| When axe runs | Right after load, no wait for the network | Same results. |
| Window size | 1280 by 720 and 375 by 812 | Same results. |
| Stored fields | Impact and failure summary against the same build | Same on all 113. |

The fixture pages are small and static, so the last three rows do not show
that timing and window size never matter on a real site.

Other settings change the rule list (checked on one page with 4.10.2):

| Axcess setting | Rules run | Against axe-core's default 89 |
| --- | --- | --- |
| Level AA, WCAG 2.1 | 89 | The same |
| Level AA, WCAG 2.2 | 90 | Adds `target-size` |
| Level AAA, WCAG 2.1 | 92 | Adds `color-contrast-enhanced`, `identical-links-same-purpose`, `meta-refresh-no-exceptions` |
| Level A | 84 | Leaves out `autocomplete-valid`, `avoid-inline-spacing`, `color-contrast`, `meta-viewport`, `valid-lang` |

## Verified and assumed

Verified (I ran it and read the output):

- Every number in the tables above.
- The element-by-element match of the 113 page-load occurrences.
- `scans.axe_violations_total` is 152: page-load plus Click-Through rows.
- The scan stored one image row from the image text check. It is not an axe
  result and is left out here.

Assumed or inferred from reading the code:

- Turning Click-Through off would leave exactly the 113 page-load rows. The
  page-load pass runs first and its rows are not changed later, but I did
  not run a second scan to confirm it.
- The Issues numbers came from the working tree, where `issues.py` had
  uncommitted changes from other work. I did not re-run them on the last
  commit (`20ded03`).
- What `@axe-core/cli` and axe DevTools do with frames and waiting is from
  their documented behaviour, not from a run.

## Not done

- A run with axe loaded into every frame, to count what Axcess misses inside
  frames at page load. The script is written but did not run.
- A comparison on a real site. The fixture has no shared header or
  late-loading content, which is where de-duplication and timing matter most.
- No existing harness does this comparison. `src/audit/detection_evals.py`
  writes made-up axe rows to time storage; it never runs axe-core.

## Where the raw data is

Scripts, the scratch database and the axe-core JSON results are in a
temporary folder for this session and will not last:
`/private/tmp/claude-502/-Users-imregan-projects-work-axcess-lsa/3c33f3d5-ab68-4bb4-9deb-c37060b7b820/scratchpad/axe-compare`.
Copy it somewhere permanent if the numbers need to be re-checked.
