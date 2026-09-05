# Alfa evidence investigation

The investigation found a reproducible contrast limitation in Alfa and separate
defects in how Axcess retained and presented the result. These cases do not
establish an overall accuracy score for either Alfa or axe.

## Report 46

A read-only inspection of the local report for
`https://lsa-mis.github.io/axcess/` found eight completed pages, 40 Alfa
`cantTell` contrast results, and zero Alfa failures. All 40 stored evidence
payloads had been cut into invalid JSON. Complete diagnostic strings surviving
in those payloads said that colors could not be fully resolved because a
`background-size` was encountered. Axcess displayed a generic message instead.

This is an inability to calculate contrast in that case, not evidence that the
text passes or fails. Check the rendered foreground and background at the
affected text, including the least favorable background beneath any gradient,
and measure contrast with a contrast checker. Confirm the applicable text size
and weight before deciding whether remediation is needed.

The upstream [SIA-R69 rule documentation](https://alfa.siteimprove.com/rules/sia-r69)
describes the text contrast condition and its assumptions. The background-sizing
limitation here comes from the observed engine diagnostic, not a claim that all
gradients or all sized backgrounds are unsupported.

## Distinguishing engine behavior from adapter defects

The browser fixtures exercise dark text on white, low-contrast text on white,
a sized gradient, an unnamed button, and identical text at separate DOM locations.
They compare each engine's expected outcomes without treating one engine as the
reference truth. Separate payload and persistence tests exercise large diagnostics,
location identity, evidence limits, and legacy malformed evidence.

The local Chromium fixture results were:

| Fixture | Alfa | axe |
| --- | --- | --- |
| Dark text on white | No retained failure or review lead | No violation |
| Low-contrast text and unnamed button | Contrast and button-name failures | Contrast and button-name violations |
| Text over a sized gradient | Cannot tell; background-sizing diagnostic | Incomplete contrast result |
| Repeated text, including separate shadow roots | Separate DOM identities retained | Checked independently in the same fixture |

The cap fixture produced 205 review leads and one failure. Axcess retained the
failure first in its 200-finding sample and preserved the full totals. Repeated
insertion of the two repeated-text findings kept two database rows. Large Unicode
and escaped diagnostic payloads remained valid JSON within the byte limit.

Run these regression checks with installed local dependencies:

```bash
uv run pytest tests/unit/test_alfa_evidence.py tests/unit/test_alfa_scan_engine.py
uv run pytest tests/integration/test_alfa_browser.py
```

The browser fixture blocks network requests and uses an already installed
Chromium; it does not crawl an external site or download dependencies.

Axcess must retain the diagnostic and its causes, keep JSON valid when bounding
evidence, and use DOM location rather than displayed text for finding identity.
When an evidence cap is reached, failures take priority over review leads while
the full outcome totals remain available. Read-time recovery of older evidence
is limited to complete diagnostic strings in the known legacy format and is
explicitly labeled incomplete; stored reports are not rewritten.

## Reviewing and verifying fixes

Alfa failures and results requiring manual review remain separate in the report.
The comparison groups both outcomes for a rule so an outcome transition is
visible as a change. A disappearing finding is only evidence of absence when
the saved coverage can support that comparison. Changed settings, missing pages,
skipped checks, and incomplete evidence remain visible limitations. Historical
reports without sufficient coverage information cannot establish remediation.

Publish a fix, rescan the same site with the same checks, inspect the comparison,
then verify the affected page before changing its workflow status. Comparisons
are read-only and never mark findings remediated automatically.
