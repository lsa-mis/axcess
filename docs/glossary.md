# Axcess glossary

Plain-language definitions of the words you will see in Axcess and in its
reports. Every other Axcess page links here instead of defining these terms
again. If a word is missing or unclear, please open an issue.

## Report groups

### Barrier

A result where a [rule engine](#rule-engine) failed a fixed, machine-testable
rule, such as an image with no [alt text](#alt-text). These are the most certain
results, so start here: confirm the problem on the page, fix it, then
[rescan](#rescan-comparison).

### Needs review

A possible problem, found by a less certain check, that a person must confirm
before it counts as a [Barrier](#barrier). Open the evidence, test it on the
page, and record your decision.

- Found by: a [browser check](#browser-check), the [keyboard
  trap](#keyboard-trap) check, a [motion check](#motion-check), image text whose
  [alt text](#alt-text) is missing or does not match, a [local AI
  model](#local-ai-model), or a [Siteimprove Alfa](#siteimprove-alfa) "cannot
  tell" result.
- Also called: "Needs confirmation" on the issue page and "Review leads" on the
  dashboard.

### Informational

A record kept for transparency, not a problem to fix, such as text in an image
whose [alt text](#alt-text) already says the same words. You do not need to act
on it.

## Issues and findings

### Finding

One result a check recorded, with its page, [element](#element), and
[evidence](#evidence). Findings are the raw records behind the Issues table.

### Occurrence

One place a problem appears: one element on one page, or in one
[DOM state](#dom-state). The Issues table counts these in its Occurrences
column, and the Excel workbook calls them Instances.

### Issue group

One row in the Issues table: every occurrence found by the same check (for
images, the same kind of image with the same [alt text](#alt-text) problem). The
Issues page shows the number of issue groups and occurrences side by side.

### Root cause

The underlying reason a problem repeats, such as one template or shared style
file (stylesheet) used on 40 pages. Axcess groups occurrences by the check that
found them, not by root cause, so look for a shared source before fixing page by
page.

### Evidence

What a check actually recorded: the page, the element, a code snippet, often a
screenshot, the rule, and the method. It stays with the report so anyone can
check a result later.

### Element

One piece of a web page, such as a heading, image, link, button, or form
field.

## Severity and priority

### Impact

How badly a problem affects people: Critical, Serious, Moderate, or Minor (for
local AI checks, this rating shows how confident the model is). Image checks say
major for Serious and info for Minor, and the workbook and [audit
report](#audit-report) show Siteimprove Alfa results, which have no rating, as
Moderate.

### Priority

A High, Medium, or Low label in the Issues table that combines
[impact](#impact) with how many pages an issue touches. Because it rewards
spread, a severe problem on a single page shows as Low, so check its impact too.

### Status

Where a finding stands in review: new, reviewing, in progress, remediated
(fixed), accepted risk (a known problem your team chose not to fix for now), or
false positive. The last four need a short reason, and the Excel workbook uses
the same words except Not Started for new, Resolved for remediated, and Not an
Issue for false positive.

## WCAG terms

### WCAG

The Web Content Accessibility Guidelines, the international standard for
accessible web content. Axcess checks against WCAG 2.2.

### Success criterion

One testable requirement in WCAG, numbered like 1.4.3 (Contrast Minimum).
WCAG 2.2 has 55 success criteria at Levels A and AA.

### Alt text

The written description of an image that [screen readers](#screen-reader) read
aloud, and that appears if the image does not load. WCAG calls it a text
alternative.

### Conformance

A page conforms to WCAG when it meets every success criterion at a chosen
[conformance level](#conformance-level). A scan cannot prove conformance,
because many success criteria need [manual testing](#manual-testing).

### Conformance level

WCAG sorts success criteria into Level A (the minimum), AA (what most policies
require), and AAA (the strictest). Axcess checks Level AA by default, and you
can choose A or AAA when you start a scan.

### Best practice

A result that is good practice but not tied to a WCAG success criterion,
labeled BP. When a rule engine finds one, Axcess lists it with
[Barriers](#barrier), so fix WCAG Barriers first and treat BP items as
recommended.

## Coverage

### Scan coverage

What a scan actually checked: which pages it tested, which methods ran, and how
many [DOM states](#dom-state) it reached. The report's Overview shows this under
"What this scan actually checked."

### Crawl

How a scan moves through a site: Axcess starts at the address you give,
follows links to find more pages, and tests each page in the [scope](#scope).

### Pages not reached

Pages the scan tried but could not load, which the Overview counts as
[crawl](#crawl) errors; a page that answered with an error, such as "Sign-in
required", is listed with that status instead. The report does not list pages
skipped because the site asked scanners to stay out (its robots.txt file) or
because they were outside the [scope](#scope).

### Scope

The part of a site a scan may visit: pages under the address you start from,
such as everything under `www.example.edu/admissions/`. A page limit and a limit
on how many links deep the [crawl](#crawl) goes also apply.

### DOM state

What a page looks like after a control is used, for example after a menu opens
(DOM is the browser's live copy of the page). Problems that appear only in such
a state are labeled "After clicking" with the control's name, so you can
reproduce them.

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
listening with a [screen reader](#screen-reader). Many WCAG success criteria
can only be judged this way.

### Screen reader

Software that reads a page aloud, or shows it on a braille display, for people
who are blind or have low vision. JAWS, NVDA, and VoiceOver are common screen
readers.

### Keyboard focus

The item a keyboard user is on right now, usually shown with an outline.
Pressing Tab moves focus to the next link, button, or form field.

### Axcess and manual testing

Axcess speeds up manual testing by finding the machine-testable problems and
pointing you to the pages, elements, and states that need a closer look. It does
not replace manual testing, because many success criteria have no automated
check at all; [What Axcess checks](https://lsa-mis.github.io/axcess/coverage/)
lists them.

## Checks and tools

### Rule engine

Software that tests a page against a fixed list of machine-testable rules.
Axcess runs [axe-core](#axe-core) by default and can also run, or instead run,
[Siteimprove Alfa](#siteimprove-alfa).

### axe-core

The open-source rule engine from Deque Systems. By default, Axcess runs a
bundled copy on every [rendered page](#rendered-page).

### Siteimprove Alfa

Siteimprove's open-source rule engine, built on [ACT rules](#act-rule), which
Axcess can run on your computer alongside or instead of axe-core. When Alfa
cannot decide a result by itself, it reports "cannot tell", and Axcess puts
that result in [Needs review](#needs-review).

### ACT rule

An accessibility test written in the Accessibility Conformance Testing format
from the W3C (the group that publishes WCAG), precise enough that different
tools can run it the same way.

### Browser check

A check that measures how a page behaves in a real browser, such as resizing it
to phone width or pressing Tab through it. Its results go to
[Needs review](#needs-review).

### Motion check

A check for audio that plays by itself with no control, and for autoplaying
video or scrolling marquee text with no way to pause it (WCAG 1.4.2 and 2.2.2).
Its results go to [Needs review](#needs-review), and in the app it runs only
when you turn on **Check motion and animation**.

### Local AI model

An optional AI model that reads text (a language model) or looks at images (a
vision model), running on your own computer through a free program called
Ollama. Axcess never installs one for you, and AI results
are never reported as [Barriers](#barrier).

### OCR

Optical character recognition: software that reads text inside images. The
desktop app includes the Tesseract OCR engine; if you [run Axcess from source
code](https://github.com/lsa-mis/axcess#run-from-source), install Tesseract
separately.

### Rendered page

A page after the browser has run its scripts and drawn it, which is what
visitors see. Axcess tests rendered pages by default.

## Common problems

### Image of text

Text that is part of a picture instead of real text (WCAG 1.4.5). [Screen
readers](#screen-reader) cannot read it, and people cannot resize or restyle it.

### Keyboard trap

A spot where [keyboard focus](#keyboard-focus) gets stuck and Tab or Shift+Tab
cannot move it away (WCAG 2.1.2). People who do not use a mouse are stranded
there.

### Reflow

Content should fit a window 320 CSS pixels wide (about a small phone, or a
desktop browser zoomed to 400%) without scrolling sideways (WCAG 1.4.10). A CSS
pixel is the browser's unit of measure, not a physical dot on your screen.

### Resize text

Text should stay readable, with nothing cut off, when zoomed to 200%
(WCAG 1.4.4).

### Text spacing

Text should not be cut off when a reader increases line, letter, word, and
paragraph spacing (WCAG 1.4.12).

### Focus not obscured

A control that has [keyboard focus](#keyboard-focus) should not be completely
hidden behind something else on the page, such as a sticky header that stays
on screen while you scroll (WCAG 2.4.11).

### Target size

Buttons and links should be at least 24 by 24 CSS pixels, or have enough space
around them (WCAG 2.5.8, Level AA). The stricter 44 by 44 CSS pixel size is
WCAG 2.5.5, Level AAA, which Axcess checks only when Siteimprove Alfa runs at
Level AAA.

## Using Axcess

### Login scan

A scan of pages behind a sign-in. Axcess opens a browser window, you sign in
yourself (including any two-factor step), and Axcess then scans the site as
you, signed in, without ever seeing your password.

### Rescan comparison

Two reports of the same [scope](#scope) lined up, with each issue marked New,
Still detected, Changed, No longer detected, or Cannot compare reliably. "No
longer detected" is not proof of a fix, so confirm fixes on the page.

### Draft export

An export downloaded from the app before expert review is finished. The app
marks it DRAFT in the file name and inside the file; command-line exports are
not marked.

### Configured search

An optional scan setting, **Search to discover result pages**, that types a
sample search you choose and tests the result pages it finds. [Single-page apps
and search scans](spa-search-scans.md) explains how to set it up.

### Audit report

The written report, a plain text file with headings (Markdown format), that you
download as **Audit report** from the Export menu. The Excel workbook is a separate export, **Remediation workbook**, with
one row per issue.

### Local-first

Axcess stores your reports on your computer, has no account, and sends no usage
data back to us (no telemetry). It connects to the site you scan, and the
desktop app checks GitHub for updates.
