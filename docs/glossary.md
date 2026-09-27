# Axcess glossary

Plain-language definitions of the words you will see in Axcess and in its
reports. Every other Axcess page links here instead of defining these terms
again. If a word is missing or unclear, please open an issue.

## Report groups

### Barrier

A result where a [rule engine](#rule-engine) ([axe-core](#axe-core) or
[Siteimprove Alfa](#siteimprove-alfa)) failed a fixed, machine-testable rule,
such as an image with no [alt text](#alt-text). These rules give the same result
every time, so these are the most certain results. Start here: check that the
rule applies to that part of the page, fix it, test the fix, then
[rescan](#rescan-comparison) to see if it is still found.

- Good to know: some Barriers are [best practices](#best-practice), not WCAG
  failures. The Issues table's WCAG column shows Best practice for these.

### Needs review

A possible problem, found by a less certain check, that a person must confirm
before it counts as a [Barrier](#barrier). Open the page and check the item
yourself. If it is a real problem, record that in its [status](#status) and fix
it; if not, mark it as a [false positive](#false-positive) with a short note.

- Found by: a [browser check](#browser-check) (such as focus, zoom, or reflow),
  the [keyboard trap](#keyboard-trap) check, a [motion check](#motion-check),
  image text whose [alt text](#alt-text) is missing or does not match, a
  [local AI model](#local-ai-model) (such as for link text, headings, or form
  labels), or a [Siteimprove Alfa](#siteimprove-alfa) "cannot tell" result.

### Informational

A record kept so you can see what was checked, not a problem to fix. You do not
need to act on it, and it should not be reported as an issue.

- Examples: text in an image whose [alt text](#alt-text) already says the same
  words, and results from older checks that are no longer considered reliable.

## Issues and findings

### Finding

One result a check recorded, with its page, [element](#element), and
[evidence](#evidence). The app calls each one an
[occurrence](#occurrence); exports and developer tools still say finding.

### Occurrence

One place a problem appears: one element on one page, or in one
[page state](#page-state). The Issues table counts these in its Occurrences
column, and the Excel workbook calls them Instances.

### Issue

One row in the Issues table: every occurrence found by the same check (for
images, the same kind of image with the same [alt text](#alt-text) problem). The
Issues page shows the number of issues and occurrences side by side.

### Found by

Which kind of check found an issue, shown in the Issues table's Found by
column and filter.

- WCAG: found at page load by a [rule engine](#rule-engine)
  ([axe-core](#axe-core) or [Siteimprove Alfa](#siteimprove-alfa)), a
  [browser check](#browser-check), or a [local AI model](#local-ai-model).
- [Click-Through](#click-through): found only in a [page state](#page-state)
  opened by clicking a control, such as a menu. It shows only when at least
  one of the issue's occurrences needed the click. One issue can be both WCAG
  and Click-Through when the same problem appears at page load and behind a
  control.
- Alt Text: text found in an image, and whether its [alt text](#alt-text) says
  the same thing.

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

### Element locator

The text that finds one [element](#element) in the page code. The rule check
(axe) and the browser checks record it as a CSS selector, such as
`main > h2`. The rule check (Alfa) records it as an XPath, a path from the top
of the page, such as `/html[1]/body[1]/main[1]/h2[1]`. The page inspector names
which one it shows and can copy it.

## Severity and priority

### Impact

How badly a problem affects people: Critical, Serious, Moderate, or Minor (for
local AI checks, this rating shows how confident the model is). Image checks say
major for Serious and info for Minor, and the workbook and [written
report](#written-report) show Siteimprove Alfa results, which have no rating, as
Moderate.

### Priority

A High, Medium, or Low label in the Issues table that combines
[impact](#impact) with how many pages an issue touches. Because it rewards
spread, a severe problem on a single page shows as Low, so check its impact too.

### Status

Where an occurrence stands in review: New, Reviewing, In progress, Fixed,
Accepted risk (a known problem your team chose not to fix for now), or Not a
problem (a [false positive](#false-positive)). The last four need a short
reason. The Excel workbook uses Not Started for New, Resolved for Fixed, and
Not an Issue for Not a problem.

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
labeled Best practice. When a rule engine finds one, Axcess lists it with
[Barriers](#barrier), so fix WCAG Barriers first and treat Best practice items
as recommended.

## Coverage

### Scan coverage

What a scan actually checked: which pages it tested, which checks ran, and how
many [page states](#page-state) it reached. The report shows this under **What
was checked**, above the Issues table.

### Crawl

How a scan moves through a site: Axcess starts at the address you give,
follows links to find more pages, and tests each page in the [scope](#scope).

### Pages not reached

Pages the scan tried but could not load, which the report summary counts as
errors next to the number of pages checked; a page that answered with an
error, such as "Sign-in required", is listed with that status instead. The
report does not list pages skipped because the site asked scanners to stay out
(its robots.txt file) or because they were outside the [scope](#scope).

### Scope

The part of a site a scan may visit: pages under the address you start from,
such as everything under `www.example.edu/admissions/`. A page limit and a limit
on how many links deep the [crawl](#crawl) goes also apply.

### Page state

How a page looks at one moment: "At page load", or after a control is used,
for example after a menu opens. Problems that appear only after a click are
labeled "After clicking" with the control's name, so you can reproduce them.
Developers call this a DOM state (the DOM is the browser's live copy of the
page).

### Click-Through

The check that opens menus, tabs, dialogs, and other controls, then checks the
page again in each new [page state](#page-state) it reaches. It is on by
default. On the New scan form it is **Open menus, tabs, and pop-up windows
(Click-Through)**.

## Accuracy

### False positive

A result that turns out not to be a real problem. Mark it as a false positive
with a short reason, and Axcess keeps that decision with the report and moves
it out of the written report's worklist.

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

### Sign-in scan

A scan of pages behind a sign-in. Axcess opens a browser window, you sign in
yourself (including any two-factor step), and Axcess then scans the site as
you, signed in, without ever seeing your password.

### Rescan comparison

Two reports of the same [scope](#scope) lined up on a report's **Compare
reports** view, with each issue marked New, No longer found, or Still found. No
longer found means only that the later scan did not find the issue again. It
is not proof of a fix, so check the page yourself before you mark the issue
Fixed.

### Draft export

An export downloaded from the app before expert review is finished. The app
marks it DRAFT in the file name and inside the file; command-line exports are
not marked.

### Configured search

An optional scan setting, **Use a search box to find more pages**, that types
a sample search you choose and tests the result pages it finds.
[Single-page apps and search scans](spa-search-scans.md) explains how to set it
up.

### Written report

The report you download as **Written report (Markdown)** from the **Export
report** menu. It is a plain text file with headings (Markdown format). The Excel
workbook is a separate export, **Issue list with fixes (Excel)**, with one row
per issue.

### Local-first

Axcess stores your reports on your computer, has no account, and sends no usage
data back to us (no telemetry). It connects to the site you scan, and the
desktop app checks GitHub for updates.
