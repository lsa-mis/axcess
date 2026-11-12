# Plain language in the Axcess interface

How Axcess writes the words people see and hear in the app. Follow this for
every label, heading, button, hint, message, tooltip, `aria-label`, `title`,
`alt`, and placeholder. [glossary.md](glossary.md) explains the terms to
readers; this page tells contributors which words to use.

## The standards

| Standard | What it asks for |
| --- | --- |
| ISO 24495-1:2023 | Readers can find what they need, understand it, and use it, and the content is relevant to them. |
| U.S. Federal Plain Language Guidelines | Lead with the main point. Short sentences, active voice, examples, tables for comparisons. |
| WCAG 3.1.3, 3.1.4, 3.1.5 (Level AAA) | Explain unusual words. Spell out abbreviations. Keep text at about lower-secondary reading level, or offer a simpler version. |
| W3C COGA, "Making Content Usable" | One idea per chunk. Concrete examples. The same word for the same thing everywhere. |

## Writing rules

1. **Main point first.** Say what the reader needs, then why.
2. **Short sentences.** Aim for 20 words or fewer. Never more than 25.
3. **Active voice.** "Axcess stores the page", not "The page is stored".
   Address the reader as "you".
4. **One idea per sentence**, and one topic per hint or paragraph. Use a
   list for three or more items, and a table to compare things.
5. **Everyday words.** "Use", not "utilize". "Start", not "initiate". "Fix",
   not "remediate". No idioms.
6. **Technical terms in parentheses.** Put the plain phrase first and keep the
   technical term after it for developers: "page code (DOM)", "element
   locator (CSS selector)", "rule check (axe)".
7. **Spell out abbreviations** the first time they appear on a screen:
   "Web Content Accessibility Guidelines (WCAG)". Well-known file formats
   (PDF, CSV) and "URL" do not need it.
8. **Buttons and links say what they do**: a verb and an object, such as
   "Delete report", or the place a link goes, such as "Image #12". Never
   "OK", "Submit", "Cancel", "Done", "Read more", "Download", "Click here"
   or a bare count such as "2 pages": cancel what, download which file?
   The words are the control's own text, visible or screen-reader-only
   inside it, never an `aria-label`. `tests/ui/test_control_text_purpose.py`
   checks every screen.
9. **Messages say what happened and what to do**, without blame: "This page
   could not be loaded. Open the live page, or try again later."
10. **Concrete examples** for anything abstract: "for example, a menu that
    opens when you click it".
11. **Sentence case** for everything. No "please", no double negatives.
    Buttons and controls too: "Start a scan", not "Start A Scan". Names
    keep their capitals ("Axcess", "Excel", "Claude Code"), and so do the
    named terms in the table below ("Mostly sure", "Not sure", "Best practice",
    "Click-Through"). The ITS technical review export names the team it is
    for, and that name keeps its capitals too: "University of Michigan
    Information and Technology Services (ITS) Accessibility Team". One
    exception: the logo beside the brand mark,
    top left, spells it "axcess", in lowercase, as a logo; text everywhere
    else writes "Axcess".
    Two tests enforce this: `tests/ui/test_control_label_case.py` reads
    every control on the main screens of the review app, and
    `desktop/test/installer-wording.test.cjs` reads every string of the
    Windows installer. A new name or term goes in their allowed lists; a
    Title Case label does not.
12. **Never drop a limit or a safety fact** to make text shorter. Say it
    more simply instead. Axcess never claims a site meets WCAG.

## Terms

Use the word in the first column, and never the words in the last.

| Use | Meaning | Do not use |
| --- | --- | --- |
| report | The results of one scan, with a number: "Report #40". | audit, scan (for the results) |
| scan | The act of checking a site: "Start a scan", "The scan is running". | crawl, audit |
| issue type | All the occurrences one check found for the same reason (for images, the same kind of image with the same alt text problem). One row in the Issues table: "6 issue types". As a label: "Issue types". | kind of issue, issue (for a row), issue group, type of issue, evidence group, evidence record, rule (for the row) |
| occurrence | One place a problem appears: one element on one page, or in one page state. "476 occurrences". As a label or column header: "Issue occurrences". Explain it where a screen first counts it: "An occurrence is one place a problem appears." | issue (for one place), instance, violation, result, finding, hit, error (for an occurrence); "Occurrences" alone as a label |
| issue | A general word for a problem, and part of names: the Issues page, the Issues table, "All issues", "Issue type". | "N issues" as a count (count issue types or occurrences) |
| image | One image the image text check looked at: "Image #12". | finding (for an image) |
| Mostly sure / Not sure / For information | The three "How sure" values, in the Issues table's "How sure" column: how sure Axcess is that an issue type is a real problem. An Alfa "cannot tell" result is Not sure; a clear form error is Mostly sure, an unclear one Not sure. | Barrier, Needs review, Informational, likely barrier, likely problem, possible problem, needs confirmation, review lead, lead, expert decision, cantTell, "Type" (for this column) |
| At page load / After clicking / In an image | The values of the Issues table's "Where it shows" column: where an issue type shows up. "At page load" and "After clicking" match the page state names. | Found by, Found (as the header), WCAG (as a value), Click-Through (as a value; it stays the feature's name), Alt Text (as a value), finding type |
| Critical / Serious / Moderate / Minor | An issue type's impact rating: how badly the problem affects people (glossary "Impact"). | critical, serious (lower case, as raw values), severity (for this rating) |
| status | Where an occurrence stands in review. Values: New, Reviewing, In progress, Fixed, Accepted risk, Not a problem (false positive). | triage status, review status, remediated, raw values like `in_progress` |
| Checked by a person | A person's choice about an element in the page inspector. Values: Not checked yet; Checked: a problem to report; Checked: a repeat of one already reported. Separate from status. | confirmed, verified, validated, approved, human-checked, triaged, redundant, duplicate |
| Issue notes | What a person writes about one element for the vendor. Matches the ITS technical review's column. | comment, annotation, remarks, rationale (for these notes) |
| check | One way Axcess tests pages. See the check names below. | engine, pipeline, probe, method, detector, source |
| page state | How a page looked at one moment: "At page load" or "After clicking Menu". | DOM state, interaction state, captured state |
| saved copy | The copy of a page the scan stored. | capture, stored capture, stored render, loaded DOM |
| live page | The page on the real site, as it is now. | live render |
| WCAG criterion | One numbered WCAG requirement: "WCAG 1.4.3 Contrast (Minimum)". | SC, success criterion (in the interface) |
| Level A, AA, AAA, Best practice | How strict a requirement is. | BP, Lvl, criterion level |
| fix | To correct a problem, or the correction itself. | remediate, remediation |
| start page | The address a scan starts from. The form field is "Website address". | seed URL, entry page, starting page |
| sign-in scan | A scan of pages behind a sign-in, with the report it makes. | login scan, protected scan, secure browser flow |
| helper app | The Axcess companion app that runs a sign-in scan on your computer. | companion (alone), agent |
| two-step sign-in (2FA) | A sign-in that needs a second step, such as a code or a phone approval. | MFA, 1FA, OTP without explanation |
| what was checked | Which checks ran and which pages and states a report covers. | coverage, method coverage |
| Product roadmap | The page listing planned checks. | coverage tracking, coverage and tracking |
| element code (HTML) | The code of one flagged element. | snippet, outerHTML, markup |
| AI suggestion | A fix the local AI model suggests for one occurrence, on request. It can be wrong; a person checks it. | AI fix, AI remediation, recommendation, auto-fix |
| AI features | The optional local AI models the desktop app can download, in one of three sizes: Small, Standard, Large, and the private AI service that runs them. | AI pack, AI bundle, AI dependencies, tier |
| Private AI service | The desktop app's own AI program (llama.cpp), kept away from the internet, that runs the downloaded models. Name Ollama only for an Ollama the person runs. | AI runtime, AI backend, model server, Ollama (for the desktop app's own service) |
| Image model | The local AI model that looks at pictures. | vision model, VLM (outside developer notes) |
| element locator (CSS selector) | The text that finds an element in the page code. | selector (alone) |
| element locator (XPath) | The path that finds an element in the page code, as the rule check (Alfa) records it. | selector, path (alone) |
| panel | One of the two reports on Compare reports, each in its own frame: "Go back in the report #24 panel". Never "left" or "right": on a narrow screen the panels are one above the other. | pane, side, left, right |
| What changed | The page that lists what is new, still found and no longer found between two reports. | Compare reports (for this page), diff, verify changes |
| Does not apply | A table cell with no value for this row. | n/a |
| remove private details (redact) | Replace likely private details in a download with "[redacted]". The choice is "Remove private details (redact)"; the file is a "redacted copy". | sanitize, scrub, anonymize, mask, PII |

### Why "occurrence" and "issue type"

The terms changed three times in October 2026. On screen the pair now reads
"7 issue types, 22 issue occurrences", issue types first.

| Dates | One row of the Issues table | One place a problem appears |
| --- | --- | --- |
| Until 2026-10-26 | issue | occurrence |
| 2026-10-26 to 2026-10-28 | kind of issue | issue |
| 2026-10-28 to 2026-10-30 | kind of issue | occurrence |
| Since 2026-10-30 | issue type | occurrence ("Issue occurrences" as a label) |

**2026-10-26: "issue" for a place.** A report read "6 issues, 476
occurrences". People called the 476 "issues" and misread the 6. The
developer changed the terms after this research:

- Most accessibility tools call each place an issue, error or failure, and
  name the group after its rule, check or type: axe DevTools and Equalize
  Digital count "issues", axe Monitor groups them as "types of issues",
  Accessibility Insights counts "failed instances" by rule. Siteimprove was
  the only tool found that used our old pair, issue and occurrence.
- "Occurrence" is an advanced word (Oxford 5000, level C1). "Issue" is B1;
  "kind" and "place" are A1 (Oxford Learner's Dictionaries word levels).
- W3C COGA, "Making Content Usable" (https://www.w3.org/TR/coga-usable/),
  "Use Clear Words" (paraphrased): use common words, and do not give
  common words new meanings. Calling a group of problems "an issue" did
  that.

**2026-10-28: "occurrence" again for a place.** User testing on 2026-10-28
was with Siteimprove users. They know Siteimprove's pair: an "issue" is a
rule, and each place it appears is an "occurrence". The developer decided
that the count of places goes back to "occurrence" everywhere a user sees or
hears it, and a row stays a "kind of issue". The row keeps its 2026-10-26
name, so "issue" alone still never names one row in a count, and the two
numbers never share a word.

"Occurrence" is still an advanced word (SC 3.1.3 Unusual Words, Level AAA;
SC 3.1.5 Reading Level, Level AAA). So where a screen or a document first
counts occurrences, it says what one is: "An occurrence is one place a
problem appears: one element on one page, or in one page state." The Issues
table's Issue occurrences column hint and the glossary do this.

**2026-10-30: "issue type", and "Issue occurrences" as a label.** After the
same testing, the developer renamed a row "issue type" and labelled the
count of places "Issue occurrences" everywhere, with issue types first on
every screen that shows both counts (the Issues summary, Reports, the
grouped views, What changed). Both labels now start with "Issue", so a
reader scanning the numbers sees at once that they count the same problems
two ways. The reasons "kind" won on 2026-10-28, below, were weighed again:
"Scan type" is a different screen's setting, the "Type" column has been
"How sure" since, and the Jira export's "Issue Type" is Jira's own field
(always "Bug"), seen only inside Jira. "Kind of issue" is now in the "Do
not use" column.

Until 2026-10-30, "Kind of issue", not "issue type" or "type of issue". "Kind" and "type"
are equally plain (both Oxford A1), and "kinds of issues" is a little more
common than "types of issues" (Google Books Ngram, 2010-2019). But "type"
already names other things: "Scan type" on New scan, the Jira export's
"Issue Type" field, and the old "Type" column that became "How sure". One
word for one thing keeps "kind" for this.

"Kinds of issues", plural, from 2026-10-28 to 2026-10-30. "Issue" is a countable noun,
and "kinds of issues" is about 30 times as common as "kinds of issue" in
the same data, so it is what readers expect. The singular stays for one
row: "Kind of issue", "1 kind of issue".

The words in code and data never changed: `occurrence_count`, `issue_key`
and the API fields keep their names, because an export or script may read
them. Only the words people see changed. The exports (CSV, Excel, Markdown,
Jira) still use their own column names; see docs/glossary.md.

### Why "Mostly sure", "Not sure", and "For information"

The "How sure" column answers one question: how sure is Axcess that this
issue type is a real problem? Each word was chosen against these alternatives.

| Choice | Rejected | Why |
| --- | --- | --- |
| "How sure" (column) | "Type" | "Type" names no question, so the badges under it had nothing to answer. |
| "Mostly sure" | "Barrier" | Jargon, and it sounds certain. |
| "Mostly sure" | "Very sure", "Sure" | A fixed rule gives the same result every time, but it can still misjudge a page, such as contrast on text over a picture. We tell people to check each one on the page first ("Zero false positive goal" in the glossary). "Very sure" invites them to skip that check, and AGENTS.md says never to claim more than the evidence shows. |
| "Mostly sure" | "Fairly certain", "Pretty certain", "High chance" | Longer words. "Fairly" and "pretty" have other meanings that confuse translation, and "High chance" does not say of what. |
| "Not sure" | "Needs review" | It did not say who reviews, or that the problem may not be real. |
| "Mostly sure" / "Not sure" | "Likely problem" / "Possible problem" | Both mean "maybe", so readers could not tell them apart. Badges in one column are read against each other, so they need to be clear opposites. |
| "For information" | "Informational" | A longer word for the same idea. |
| "For information" | "Not a problem" | Already the status for a false positive. One phrase names one thing. |

### Check names

| Check | Name in the interface |
| --- | --- |
| axe-core | Rule check (axe) |
| Siteimprove Alfa | Rule check (Alfa) |
| Keyboard | Keyboard check |
| Responsive and zoom | Zoom and layout check |
| Focus | Focus check |
| Form errors (WCAG 3.3.1) | Form error check |
| Page code (rendered DOM questions axe-core does not ask) | Page code check |
| Visual order, motion, and autoplay | Motion and reading-order check |
| Semantic (local language model) | AI review |
| Image text (OCR and vision model) | Image text check |

Name the tool only when it matters to the reader, and in parentheses.

## Words that are fine as they are

"Axcess", "WCAG" after it is spelled out, "screen reader", "keyboard",
"alt text" (explain once as "the text a screen reader reads for an image"),
"screenshot", "export", "Excel", "Markdown", "CSV", "JSON", "Claude Code"
(a product name, in the hints for the fix brief export).
