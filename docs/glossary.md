# Axcess glossary

Plain-language definitions of the words you will see in Axcess and in its
reports. Every other Axcess page links here instead of defining these terms
again. If a word is missing or unclear, please open an issue.

## Report groups

### Barrier

A result where a rule engine failed a fixed, machine-testable rule, such as an
image with no text alternative. These are the most certain results, so start
here: confirm the problem on the page, fix it, then [rescan](#rescan-comparison).

### Needs review

A lead that a person must confirm before anyone calls it a barrier, found by a
[browser check](#browser-check), the keyboard check, a [local AI
model](#local-ai-model), or an Alfa "can't tell" result. Open the evidence, test
it on the page, and record your decision (the issue page calls this group
"Needs confirmation" and the dashboard calls it "Review leads").

### Informational

A record kept for transparency, not a problem to fix, such as text in an image
whose alt text already says the same words. You do not need to act on it.

## Issues and findings

### Finding

One result a check recorded, with its page, element, and
[evidence](#evidence). Findings are the raw records behind the Issues table.

### Occurrence

One place a problem appears: one element on one page, or in one
[DOM state](#dom-state). The Issues table counts these in its Occurrences
column, and the Excel workbook calls them Instances.

### Issue group

One row in the Issues table: every occurrence found by the same check (for
images, the same kind of image with the same alt text problem). The Issues
page shows the number of issue groups and occurrences side by side.

### Root cause

The underlying reason a problem repeats, such as one template or stylesheet
used on 40 pages. Axcess groups occurrences by the check that found them, not
by root cause, so look for a shared source before fixing page by page.

### Evidence

What a check actually recorded: the page, the element, a code snippet, often a
screenshot, the rule, and the method. It stays with the report so anyone can
check a result later.

## Severity and priority

### Impact

How badly a problem affects people, as reported by the check: critical,
serious, moderate, or minor. Image findings use critical, major, minor, or info,
and the workbook and audit report show every result as Critical, Serious,
Moderate, or Minor.

### Priority

A High, Medium, or Low label in the Issues table that combines
[impact](#impact) with how many pages an issue touches. Because it rewards
spread, a severe problem on a single page shows as Low, so check its impact too.

### Status

Where a finding stands in review: new, reviewing, in progress, remediated,
accepted risk, or false positive. The workbook shows these as Not Started,
Reviewing, In Progress, Resolved, Accepted Risk, and Not an Issue, and the last
four require a short reason.

## WCAG terms

### WCAG

The Web Content Accessibility Guidelines, the international standard for
accessible web content. Axcess checks against WCAG 2.2.

### Success criterion

One testable requirement in WCAG, numbered like 1.4.3 (Contrast Minimum).
WCAG 2.2 has 55 success criteria at Levels A and AA.

### Conformance level

WCAG sorts success criteria into Level A (the minimum), AA (what most policies
require), and AAA (the strictest). Axcess checks Level AA by default, and you
can choose A or AAA when you start a scan.

### Best practice

A rule-engine result that is good practice but not tied to a WCAG success
criterion. Axcess labels it BP and still lists it with
[Barriers](#barrier) when a rule engine found it.

## Coverage

### Scan coverage

What a scan actually checked: which pages it tested, which methods ran, and how
many [DOM states](#dom-state) it reached. The report's Overview shows this under
"What this scan actually checked."

### Pages not reached

Pages the scan tried but could not test, such as pages that failed to load or
needed a sign-in. The Overview counts these as crawl errors, but it does not
list pages skipped because of robots.txt or because they were outside the
[scope](#scope).

### Scope

The part of a site a scan may visit: the start address's host and path, such as
`/admissions/`, plus limits on pages and link depth.

### DOM state

What a page looks like after a control is used, for example after a menu opens.
Problems that appear only in such a state are labeled "After clicking" with the
control's name, so you can reproduce them.

## Accuracy

### False positive

A result that turns out not to be a real problem. Mark it as a false positive
with a short reason, and Axcess keeps that decision with the report and moves
it out of the audit report's worklist.

### Zero false positive goal

Our goal is that nothing Axcess reports as a [Barrier](#barrier) is a false
positive, which is why only rule-engine failures go there and every other
check waits for a person. It is a goal, not a guarantee, so confirm each
Barrier on the page before you report it.

## Testing methods

### Automated testing

Checks a program runs on its own, such as a rule engine or a browser
measurement. They are fast and consistent, but they only test what a machine
can measure.

### Manual testing

A person checks the site directly, for example using only a keyboard or
listening with a screen reader. Many WCAG success criteria can only be judged
this way.

### Axcess and manual testing

Axcess speeds up manual testing by finding the machine-testable problems and
pointing you to the pages, elements, and states that need a closer look. It
does not replace manual testing, because many success criteria have no
automated check at all; [What Axcess checks](https://lsa-mis.github.io/axcess/coverage/)
lists them.

## Checks and tools

### Rule engine

Software that tests a page against a fixed list of machine-testable rules.
Axcess runs [axe-core](#axe-core) on every scan and can also run
[Siteimprove Alfa](#siteimprove-alfa).

### axe-core

The open-source rule engine from Deque Systems. Axcess runs a bundled copy on
every rendered page.

### Siteimprove Alfa

Siteimprove's open-source rule engine, built on [ACT rules](#act-rule). Axcess
can run it on your computer as an optional second engine.

### ACT rule

An accessibility test written in the W3C's Accessibility Conformance Testing
format, precise enough that different tools can run it the same way.

### Browser check

A check that measures how a page behaves in a real browser, such as resizing it
to phone width or pressing Tab through it. Its results go to
[Needs review](#needs-review).

### Local AI model

An optional language or vision model that runs on your own computer through a
free program called Ollama. Axcess never installs one for you, and AI results
are never reported as [Barriers](#barrier).

### OCR

Optical character recognition: software that reads text inside images. Axcess
includes the Tesseract OCR engine.

### Rendered page

A page after the browser has run its scripts and drawn it, which is what
visitors see. Axcess tests rendered pages by default.

## Common problems

### Image of text

Text that is part of a picture instead of real text (WCAG 1.4.5). Screen
readers cannot read it, and people cannot resize or restyle it.

### Keyboard trap

A spot where keyboard focus gets stuck and Tab or Shift+Tab cannot move it away
(WCAG 2.1.2). People who do not use a mouse are stranded there.

### Reflow

Content should fit a screen 320 CSS pixels wide without scrolling sideways
(WCAG 1.4.10).

### Resize text

Text should stay readable, with nothing cut off, when zoomed to 200%
(WCAG 1.4.4).

### Text spacing

Text should not be cut off when a reader increases line, letter, word, and
paragraph spacing (WCAG 1.4.12).

### Focus not obscured

A control that has keyboard focus should not be completely hidden behind
something else on the page, such as a sticky header (WCAG 2.4.11).

### Target size

Buttons and links should be at least 24 by 24 CSS pixels, or have enough space
around them (WCAG 2.5.8, Level AA). The stricter 44 by 44 pixel size is WCAG
2.5.5, Level AAA, which Axcess does not check.

## Using Axcess

### Login scan

A scan of pages behind a sign-in. Axcess opens a browser window, you sign in
yourself (including any two-factor step), and Axcess scans with that session
without ever seeing your password.

### Rescan comparison

Two reports of the same scope lined up, with each issue marked New, Still
detected, Changed, No longer detected, or Cannot compare reliably. "No longer
detected" is not proof of a fix, so confirm fixes on the page.

### Draft export

An export made before expert review is finished. Axcess marks it DRAFT in the
file name and inside the file.

### Local-first

Axcess stores your reports on your computer and has no account and no
telemetry. It connects to the site you scan, and the desktop app checks GitHub
for updates.
