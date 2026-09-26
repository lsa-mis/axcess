# Plain-language audit of the Axcess interface, September 2026

An app-wide check of the interface text against four standards: ISO 24495-1:2023, the U.S. Federal Plain Language Guidelines, WCAG 3.1.3, 3.1.4 and 3.1.5 (Level AAA), and W3C COGA. The rewrite that followed uses the terms in [../plain-language.md](../plain-language.md).

This file records what the audit found and what was left for a decision. The exact wording changes are in the git history of the commit that added this file.

## Part A: New scan form, scan progress, dashboard

### Findings

#### ISO 24495-1 (find, understand, use; relevant)

| File:line (before) | Problem | What I did |
| --- | --- | --- |
| copy.ts:18,224 | The field label was "Site URL", but the terms table says "Website address". | Changed to "Website address" everywhere, including the error and summary text. |
| copy.ts:44, ScanForm.tsx:123, copy.ts:225 | "Coverage" is a banned word and was vague. | Changed to "Pages to scan". |
| copy.ts:57, ScanForm.tsx:140 | "Speed and debugging": nothing in this group is about debugging. | Changed to "Speed and browser window". |
| copy.ts:228 | "Storage" did not say what gets saved. | Changed to "What is saved". |
| ScanSummaryCard.tsx:73 | "Load state only." was internal jargon. | Changed to "Checks each page at page load only." |
| LocalLoginScan.tsx:116 | "Opening the normal Axcess report now." Nothing opens by itself. The user has to press "Open report". | Changed to "Open the report to see what the scan found." |
| Dashboard.tsx:199 | "N findings" counted `scans.finding_count`, which holds only image-text rows (`synthesizer/findings.py`). Readers took it as the total. | Changed to "N images with text". |
| ScanDetail.tsx:165,173 | Showed the raw status value `failed` or `interrupted`. | Now uses `SCAN_STATUS_LABEL` ("Failed", "Stopped"). |
| statusDecision.ts:23 | Showed raw values such as "remediated" and "false positive". | Now uses `STATUS_LABEL` ("Fixed", "Not a problem"). |

#### U.S. Federal Plain Language Guidelines (main point first, short, active voice, examples)

| File:line (before) | Problem | What I did |
| --- | --- | --- |
| copy.ts:20,26 | Help text used semicolons and the passive voice, and had no example. | Split into short sentences, with an example ("an address ending in /section/"). |
| copy.ts:80,85,102,187,193,195 | Long passive sentences ("is flagged", "is typed", "is destroyed", "will be stored"). | Rewrote in the active voice with "Axcess" or "you" as the subject. Every safety and privacy fact is kept. |
| copy.ts:199,203 | The notes joined two ideas with a semicolon. | Split into two sentences. |
| copy.ts:209 | "Fix these before starting:" | Changed to "Fix these problems, then start the scan:" |
| copy.ts:213 | "query string, fragment or credentials" | Changed to "anything after a ? or #, and any user name or password". |
| ScanDetail.tsx:165-176 | "is not evidence of full coverage", "No report evidence was created" | Rewrote as short statements in the active voice. |
| ScanDetail.tsx:274 | "Pending pages will be dropped." | Changed to "Axcess will not check the pages that are still waiting." |
| ScanDetail.tsx:380 | "Fetching, rendering, and running selected checks · depth N · attempt N" | Changed to "Loading the page and running the checks you chose · N clicks from the start page · try N". |
| ScanDetail.tsx:451,460 | Hints were abstract ("reports completed work, not merely configuration"). | Rewrote in plain words. |
| Dashboard.tsx:108-116 | The headline used "issue group", "expert decision", and "high-confidence enough to act on without confirmation". | Changed to "N issues need review" and "N issues are Barriers: sure enough to fix without checking first." |
| Dashboard.tsx:219 | One run-on sentence joined with commas. | Split into four sentences. The caveats are kept: results are not proof, and a check that did not run is not a pass. |
| statusDecision.ts:320,326 | Bureaucratic ("Document why", "basis for the decision", "rationale is required"). | Changed to "Explain why…", "Say what evidence you looked at…", "You need to give a reason. The status was not changed." |

#### WCAG 3.1.3, 3.1.4, 3.1.5 (unusual words, abbreviations, reading level)

| File:line (before) | Problem | What I did |
| --- | --- | --- |
| DefaultSettingsCard.tsx:14, copy.ts:160 | "WCAG" was not spelled out. | The first mention on the page is now "Web Content Accessibility Guidelines (WCAG) 2.2", on the default card and in the Standard hint. |
| copy.ts:93,97 | "SC 2.4.11" and similar. | Changed to "WCAG 2.4.11" (the terms table bans "SC"). |
| copy.ts:97 | "px" | Changed to "pixels". |
| copy.ts:14, ProtectedScanSteps.tsx:28,69, LocalLoginScan.tsx:96 | "2FA" was not spelled out. | Changed to "two-step sign-in (2FA)". |
| copy.ts:105-107 | "OCR" was not spelled out. | The hint now says "optical character recognition (OCR)". |
| copy.ts:51-54 | "AI" was not spelled out. | The group description says "AI (artificial intelligence)". |
| copy.ts:172 | "ACT" and "W3C" were not spelled out. | Changed to "ACT rules (Accessibility Conformance Testing)" and "W3C (World Wide Web Consortium)". |
| ScanSummaryCard.tsx:178 | "GB" | Changed to "gigabytes (GB)". |
| scanProgress.ts:265-272 | "sec", "min", "hr" | Spelled out, with correct singular and plural. |
| scanProgress.ts:261 | ETA used an en dash range ("2–5 min"). | Changed to "2 minutes to 5 minutes". |
| copy.ts:75,78,89,93,112,185 | Unusual words were not explained: subdomain, robots.txt, keyboard trap, focus, alt text, least privilege. | Added a short definition or a concrete example to each. |
| copy.ts:66,100,127, ScanSummaryCard.tsx | "host", "rendered pages", "HTML", "markup", "capture" | Plain phrase first, with the technical term in parentheses: "page code (HTML)", "saved copy". |
| SearchSettings.tsx:25-31,66 | "match by", "Accessible label", "CSS selector" | Changed to "find it by", "Its label (accessible name)", and "element locator (CSS selector)", as the terms table asks. |
| SearchSettings.tsx:64,68 | "autocomplete", "pagination" | Changed to "when results appear as you type (autocomplete)" and "Open more pages of results". |
| pageLabels.ts | "Redirected", "Processing method", "Fetched without browser rendering" | Changed to "Sent to another address (redirect, HTTP n)", "How it was loaded", and "Page code read without a browser (fast scan)". |
| copy.ts:195 | "verified loopback Ollama endpoint" | Changed to "Ollama at a checked address on this same computer (loopback)". |

#### W3C COGA (one idea per chunk, examples, consistent terms)

| File:line (before) | Problem | What I did |
| --- | --- | --- |
| copy.ts:66,70,125, ChecksGroup.tsx:71,79,87, CoverageGroup.tsx:24,78, SpeedGroup.tsx:67, Dashboard.tsx:78,177 | "crawl" and "crawler" are banned words. | Changed to "scan", and "Fast crawl" became "Fast scan" everywhere. |
| copy.ts:164, ChecksGroup.tsx:25, ScanSummaryCard.tsx:163, CoverageGroup.tsx:26, SearchSettings.tsx:45,48 | "Rule engine", "axe-core", and "Siteimprove Alfa" were used inconsistently. | Now "Rule check tool" with options "axe", "Alfa", "Both". Prose uses CHECK_LABEL ("Rule check (axe)", "Rule check (Alfa)"). |
| ScanSummaryCard.tsx:39-49, DefaultSettingsCard.tsx:15-26 | Chips and lines used four different names for the same checks ("Keyboard traps", "Responsive & zoom", "Wording review", "Motion & animation"). | Now use CHECK_LABEL names, with a short description in parentheses on the default card. |
| ChecksGroup.tsx:39-41 | Options "A", "AA", "AAA" did not match the "Level AA" term. | Changed to "Level A", "Level AA", "Level AAA". The chip, digest and default card also say "Level". |
| copy.ts:102, ScanSummaryCard.tsx:188-189 | "findings" is a banned word. | Changed to "occurrences". |
| LocalLoginScan.tsx:119,124,134,317, ProtectedScanSteps.tsx:63,66, copy.ts:212, NewScan.tsx:476 | "login scan", "protected scan", "secure browser flow" | Changed to "sign-in scan". |
| Dashboard.tsx:140-142 | "Review leads" and "expert decision" | Changed to "Needs review" (REVIEW_TYPE_LABEL). |
| Dashboard.tsx:136,149,155 | "n/a" is a banned word. | Changed to "Not available", or "Loading" while the list loads. |
| Dashboard.tsx:98,176 | "report #", "No scans yet" | Changed to "Report #" and "No reports yet". |
| ScanDetail.tsx:302-325 | Progress stages mixed "discovered", "queued", "active", "leased" and "crawl settles". | Now use one set of words: found, waiting, checked, in progress. |

### Left for a decision

Need a product decision. The existing text already contradicts what the code does. I kept the old claim in plain words and did not change the facts:

1. **FIXED_NOTE_LOGIN says sign-in scans "respect robots.txt" and run at "1 page per second".**
   - robots.txt: `LOGIN_POLICY.fixed.ignore_robots = true`, and `server.py:1240` and
     `protected_api.py:1038` pass `ignore_robots=True`. So sign-in scans actually **ignore** robots.txt.
   - Speed: the Speed group still shows "Page requests per second" for sign-in scans. The server
     accepts 0.1 to 5 (`server.py:145`). So the speed is 1 page per second by default, not fixed.
   - The note needs a corrected fact, for example "ignore robots.txt, because the site owner's
     permission replaces it" and "start at 1 page per second". I did not choose this myself.
2. **"Occurrences and screenshots are saved as usual" (ScanSummaryCard, storage line) is wrong for
   sign-in scans.** For those scans `capture_screenshots=not body.skip_rendered_storage`
   (`server.py:1238`), so turning the switch on also drops screenshots. The switch hint in copy.ts
   says "Occurrences and their evidence are saved as usual", which is only true for public scans.
3. **Dashboard "images with text"** is my reading of `scans.finding_count`: one findings row per
   image that has OCR or SVG text (`synthesizer/findings.py`). Someone should confirm this label, or
   the dashboard should show the occurrence count instead.
4. **"Scan again with faster settings"** (it was "Retry with balanced settings"). The button runs a
   fixed profile: default settings with menu-opening, the vision model, AI review and the motion check
   turned off. A product owner may want the button or a hint to say that.

Out of my scope or not changed:
- `statusDecision.ts`: the `${subject}` text comes from callers in other agents' files
  (`finding #${id}`, and so on). "finding" is a banned term there, so they should pass "image #"
  or "occurrence".
- Backend text is shown unchanged: `data?.error` (scope preview), `capabilities.*.reason`,
  `method.label/description/result/caveat`, `failure_reason`, `status.data.error`, and API error messages.
- `ScanStatusBadge` and `StatCard` live in `components/ui.tsx`, which is not mine.
- `ScanDetail.tsx` keeps the page title `Scan #${id}` on the failed-scan page, because it sits next
  to "No report was produced". The terms table would prefer "Report #" when a report exists.
- `SubmitBar` "Cancel" is left as is. It is a standard dismiss action, not a vague "OK".
- `ScanDetail` `METHOD_STATE_LABEL` and the Checked/Waiting/In progress badges could be shared
  labels in `terms.ts` if other screens show method states. Suggested addition: `METHOD_STATE_LABEL`.
- A term is missing from terms.ts and plain-language.md: the "click-through" setting (opening
  menus, tabs and dialogs) has no fixed interface name. I used "Open menus, tabs, and pop-up windows
  (dialogs)" for the switch, and "Opens menus and pop-up windows" for the chip and summary.
  "Fast scan" (was "Fast crawl") should be added to the terms table too.
- WCAG is spelled out on the New scan page (default card and Standard hint), but not on the dashboard.
  The dashboard avoids the abbreviation and says "accessibility rules".

## Part B: Sign-in scan screens, app shell, navigation, reports list

### Findings

#### ISO 24495-1 (readers can find, understand, and use it; content is relevant)

| File:line (original) | Problem | What I did |
| --- | --- | --- |
| AppShell.tsx:527-529, ProtectedCompanion.tsx:890-892, ProtectedManualChecks.tsx:117-120, ProtectedIssueIndex.tsx:78-81 | The protected pages had three different names for one thing ("Protected companion", "Protected scan #", "Protected report #"). Tab titles did not match page titles. | All of them now use "Sign-in scan", "Sign-in scan #N", "Sign-in scan issues", and "Manual checks for the sign-in scan". routeTitle, the breadcrumbs, the h1s, and the back buttons all match. |
| AppShell.tsx:540-549, ReportCrumb.tsx:35-38 | Tab titles and breadcrumbs showed internal words ("DOM-engine evidence", "Finding evidence", "Coverage tracking"). | Changed to "Rule check results", "Rule check results by rule", "Images", "Images by issue", "Image details", "Product roadmap". |
| CommandPalette.tsx:84,98 | Search results showed raw enum values (`completed`, `axe`). | Now shows SCAN_STATUS_LABEL and CHECK_LABEL, with "Report #N". |
| ui.tsx:18, 515-521 | StatusChip showed `in progress` / `remediated`. ScanStatusBadge showed `completed` / `interrupted`. | Both now use STATUS_LABEL / SCAN_STATUS_LABEL. The aria-label is `Scan status: <same visible label>`. |
| Scans.tsx:266, ProtectedIssueIndex.tsx:145-151 | Raw enum values in table cells (`awaiting authentication`, `cant tell`, `failed`). | Added local display maps. PROTECTED_STATUS_LABEL is in Scans.tsx. RESULT_LABEL is in ProtectedIssueIndex.tsx, where cant_tell shows as REVIEW_TYPE_LABEL.expert_review, "Needs review". |
| api/client.ts:69 | The fallback error was `500: <raw body>`, which does not tell the reader what to do. | Now says what happened and what to do. The body is still kept as "Details: …". |
| NotFound.tsx:279 | "No route matches" is developer language. | Rewritten: the page does not exist, check the address, use the menu, or go to the dashboard. |

#### U.S. Federal Plain Language Guidelines (main point first, short sentences, active voice)

| File:line (original) | Problem | What I did |
| --- | --- | --- |
| ProtectedCompanion.tsx:71-96 (STATUS_COPY) | Passive and long ("No automatic recovery or re-authentication occurred…"). | Short, active sentences. Each status detail says what happened, then what to do. |
| ProtectedCompanion.tsx:600-606 | Long steps with jargon (headed browser, 1FA, MFA). The "never requests" facts were in one sentence of 8 items. | The steps are split into short sentences. The never-requested items are now a bulleted list of 8 items, and all 8 are kept. The "stops and asks you to sign in again" fact is its own sentence. |
| ProtectedCompanion.tsx:708, 737, 767, 835, 871 | Paragraphs of 25+ words, with several ideas per sentence. | Split into sentences of 20 words or fewer. Every fact is kept: encrypted, tied to this scan, sent only after the certificate check (mTLS), not kept or shown on this page. |
| ProtectedManualChecks.tsx:147 | One long sentence listing 11 forbidden inputs, plus a semicolon clause. | Now 5 short sentences. All forbidden items are kept. "U-M" is spelled out. |
| Scans.tsx:105-109 | Help text defined "findings" and "DOM states" in the passive voice. | Rewritten in active voice, with an example of a page state. |
| Scans.tsx:411-414 | The delete confirmation put "cannot be undone" last. | Order is now: what happens, then "You cannot undo this", then why image files are kept. |
| Scans.tsx:202-203 | "authorized the scope and a least-privilege audit account is ready" | Now two sentences: the owner approves the pages, and you need a test account with only the access it needs (least privilege). |

#### WCAG 3.1.3 / 3.1.4 / 3.1.5 (unusual words, abbreviations, reading level)

| File:line (original) | Problem | What I did |
| --- | --- | --- |
| ProtectedCompanion.tsx:602, 606; ProtectedManualChecks.tsx:135, 147, 249 | 1FA, MFA, OTP, and push approval were not explained. | Now "two-step sign-in (2FA)", "one-time code (OTP)", and "phone approval (push approval)". |
| ProtectedCompanion.tsx:600, 617, 631, 634 | "SHA-256 fingerprint of the pre-provisioned companion certificate", "64 hexadecimal characters". | Now "helper app's certificate ID (SHA-256 fingerprint)", "set up in advance", and "64 characters, 0–9 and A–F". |
| ProtectedCompanion.tsx:737, 745-752 | "origins", "mTLS", "CDN", "scope commitment". | Plain phrase first, with the term in parentheses: "site addresses (origins)", "(mTLS)", "File and resource sites (CDN)", "Approved sites (scope)". |
| ProtectedCompanion.tsx:805-808 | Webhooks, MCP, and workers were not explained. | Now "automatic messages to other services (webhooks)", "report chat (MCP)", and "background scripts (workers)". |
| ProtectedCompanion.tsx:820; ProtectedManualChecks.tsx:121, 135; ProtectedIssueIndex.tsx:96, 136 | "WCAG 2.2 AA 3.3.8" and "SC 3.3.8": WCAG was not spelled out, and SC is a banned word. | WCAG is spelled out at its first use on each screen. The criterion now follows the TERMS format: "WCAG 3.3.8 Accessible Authentication (Minimum), Level AA". |
| ProtectedCompanion.tsx:541, 691, 835; ProtectedManualChecks.tsx:147 | Bare "selectors". "OCR" was not spelled out. | Now "element locators (CSS selectors)" and "text read from images (OCR)". |
| ui.tsx:1168-1178 (relativeTime) | "2h ago", "3d ago", "5mo ago" are abbreviations, and "n/a" is a banned word. | Now "2 hours ago", "3 days ago", "5 months ago", with correct singular and plural. A missing time shows "Not recorded". |
| ProtectedIssueIndex.tsx:150 | "n/a" | Now "Does not apply", as TERMS requires. |
| CommandPalette.tsx:210 | "⌘K anytime": Mac-only, with no verb. | Now "⌘K or Ctrl+K opens search anytime". |

#### W3C COGA (one idea per chunk, concrete examples, consistent terms)

| File:line (original) | Problem | What I did |
| --- | --- | --- |
| All protected files | Banned words: companion (alone), crawl, protected scan, login scan, secure browser, lead, evidence group, remediation, triage. | Now helper app, scan, sign-in scan, possible problem, issue, fix. |
| ProtectedCompanion.tsx:553-556, ProtectedIssueIndex.tsx:12-20 | Check names were "axe-core", "Alfa", "Keyboard probe", "Responsive probe", and "In-memory image lead". | Now CHECK_LABEL from terms.ts. |
| Scans.tsx:150, 153, 218 | "DOM states", "Image findings", "Issue leads" | Now "Page states", "Images with text", "Occurrences". |
| AppShell.tsx:68; CommandPalette.tsx:73 | "Product Roadmap" and "Coverage & tracking" name the same page differently. | Both now say "Product roadmap". |
| AppShell.tsx:246; Scans.tsx:124 | "Create New Scan" was in Title Case and did not match the TERMS verb. | Now "Start a new scan". The visible text "New scan" is still inside the accessible name. |
| CommandPalette.tsx:166 | The empty result had no example. | Now gives examples: a site name, a report number, or an issue name. |
| ReportHeader.tsx:143 | "Evidence for expert review, not a conformance verdict." | Now "Results for an expert to review. They do not prove that the site meets accessibility standards." The no-conformance-claim fact is kept. |

### Left for a decision

- **Shared label missing from terms.ts:** labels for protection status (awaiting_authentication, authentication_required, running, completed, failed, interrupted). Scans.tsx now has a local PROTECTED_STATUS_LABEL. ProtectedCompanion STATUS_COPY uses longer heading forms ("Sign-in scan running"). Recommend adding a PROTECTED_STATUS_LABEL to terms.ts.
- **Shared label missing from terms.ts:** labels for axe impact and engine outcome (Critical/Serious/Moderate/Minor, Failed). ProtectedIssueIndex.tsx has a local RESULT_LABEL. SeverityChip in ui.tsx still shows the raw severity value; I assume CSS capitalizes it and did not verify.
- **Route and view names need to match other agents' page titles:** A11y.tsx, A11yByRule.tsx, Findings.tsx, GroupedFindings.tsx, and FindingDetail.tsx belong to other agents. I chose "Rule check results", "Rule check results by rule", "Images", "Images by issue", and "Image details" for routeTitle and VIEWS. If those agents picked different h1s, align the names in AppShell.routeTitle and ReportCrumb.VIEWS.
- **Unchanged on purpose:** ReportCrumb VIEWS "Issue evidence". `trailFor` compares `match?.view === "Issue evidence"`, so renaming it would need a logic change.
- **Filename out of scope:** the redacted download filename `protected_scan_{id}_redacted.md` (client.ts). It is visible in the Downloads folder, but it is a file name and tests or ops may rely on it.
- **Not changed:** Search aria-label `Search everything (Cmd+K)` and title `Search everything (Cmd/Ctrl+K)` (AppShell). They are inconsistent, but both are acceptable, and changing the accessible name was not needed.
- **Not changed:** the `esc` key cap and the nav landmark label `Primary`.
- **Backend text left as is:** criterion names, `manual_check`, level/method on ProtectedManualChecks, rule_id, `environment` and `data_classification` values, and API error messages (`error.message`).
- **Product decisions:**
  1. Page naming. I made "Sign-in scan" the h1 and crumb for the /protected workspace. Its subtitle says the helper app does the work. The step component ProtectedScanSteps.tsx (not mine) still says "How the secure browser flow works" and "Login before scanning", which break TERMS; its owner should update it.
  2. Scans.tsx now pluralizes the "public reports" subtitle, and relativeTime now pluralizes units. Both are small display logic changes.
- **Tests likely to need updates (I did not edit any):**
  - tests/ui/test_reports_table.py: headers "DOM states" and "Image findings"; nav "Public reports pagination".
  - tests/ui/_paging.py: `f"{label} pagination"` becomes `f"{label}: page controls"`.
  - tests/ui/test_report_workflow.py:646: link "stored evidence" becomes "Page evidence".
  - Any test matching "Create New Scan", "Product Roadmap", "Scan status: completed", "Delete scan N", the old protected-page headings, or "2h ago"-style times.

## Part C: Issues, issue pages, page details, Verify changes, report summary

### Findings

#### ISO 24495-1 (find, understand, use; relevant)

| File:line (original) | Problem | What I did |
| --- | --- | --- |
| ReportSummary.tsx:46 | "Issues Found" showed the occurrence count, so it named the wrong thing. | Now "Occurrences found", with the hint "Each place an issue appears". |
| ReportSummary.tsx:47 | "Issue Groups" is not the TERMS word. | Now "Issues found", with the hint "Kinds of problem, one per row below". |
| ReportSummary.tsx:68 | The disclosure summary "Details" did not say what it opens. | Now "See what was checked". |
| ExportMenu.tsx:21-24 | Export names did not say what each file holds ("Raw findings", "Audit report"). | Each name now says what the file is and keeps the format, for example "Issue list with fixes (Excel)". |
| ExportMenu.tsx:76 | The button "Export" had no object. | Now "Export report". |
| IssueDetail.tsx:42, IssuePages.tsx:47 | The not-found message said "evidence group" and gave no clear next step. | Now "Issue not found", plus what may have happened and where to go. |
| Issues.tsx:96, IssuePages.tsx:40, IssuePageScreenshots.tsx:45, IssueEvidence.tsx:45, PageEvidence.tsx:60 | Load errors said "Couldn’t load…" with no action to take. | Each says what failed, that the saved report is safe, and to reload and try again. |
| PageEvidence.tsx:57 | The 404 message gave no next step. | Added "Check the link, or go back to the Issues table." |
| IssuePagesTable/IssuePageScreenshots "Stored evidence" | The link name did not say where it goes. | Now "Page details". It opens the page's details view. |
| ReportSummary.tsx:133-136 | "DOM engines" and "Image evidence" were unclear link names. | Now "Rule check details (axe and Alfa)" and "Image text check ({n} images)". |

#### U.S. Federal Plain Language Guidelines (main point first, short, active)

| File:line | Problem | What I did |
| --- | --- | --- |
| Issues.tsx:158-162 | The ACT explanation used passive, abstract wording ("evidence about that condition"). | Rewrote it as short active sentences. It keeps "not proof that the whole page or site fails WCAG". |
| ReportSummary.tsx:139-150 | "Observed reviewer rejection rate" was jargon, and "detector-accuracy claim" was abstract. | Now "Reviewed occurrences marked “Not a problem”:", then "This number is for this report only. It does not show how accurate the checks are in general." |
| ReportSummary.tsx:155-158 | "Danger zone" is an idiom, and "image blobs" is jargon. | Now "Delete this report". The blob fact is now "Image files that other reports also use may stay in storage." |
| ReportSummary.tsx:174 | The confirm text used passive voice and "scan" for the results. | Now "Delete report #…? This removes the report for good… You cannot undo this." |
| ReportSummary.tsx:204-210 | "The crawler could not read past the entry page… requires authentication." | Now leads with the error, then the next step. The "authorized" fact is kept as "and you have permission". |
| IssueEvidence.tsx:96, 101 | Passive wording ("until the expert decision is documented", "read-only evidence retained for transparency"). | Rewrote in active voice and kept both facts. |
| Diff.tsx:17-21, 73-77 | Long help text in passive voice. | Split into short sentences. It keeps "not a compliance verdict" as "does not show whether the site meets WCAG". |
| Diff.tsx:203-221 | changeSummary said "Recorded findings" and "review statuses differ". | Now "Occurrences", "Pages with the issue", and "Status changed". |
| IssuePageScreenshots.tsx:169 | "exceeded the per-page safety limit" was abstract. | Now "the page reached its safety limit for screenshots". The safety fact is kept. |

#### WCAG 3.1.3 / 3.1.4 / 3.1.5 (unusual words, abbreviations, reading level)

| File:line | Problem | What I did |
| --- | --- | --- |
| ConformanceBadge.tsx:25 | "BP" was an unexplained abbreviation. | Now "Best practice". A/AA/AAA get a screen-reader "Level " prefix, and the title explains them. |
| IssueEvidence.tsx:269 | "Criterion level" showed raw "BP" and "n/a". | Now "WCAG level", with values "Level AA", "Best practice", or "Does not apply". |
| IssueDetail.tsx:75, IssuePages.tsx:87 | "WCAG SC" left "SC" unexplained, and "WCAG" was not spelled out. | Now `<abbr>WCAG</abbr> 1.4.3 Name`, which drops "SC". |
| Issues.tsx:300 (header) | "WCAG" was not spelled out on the Issues screen. | The header now uses `<abbr title>`. The ACT paragraph spells out "Web Content Accessibility Guidelines (WCAG)". |
| Issues.tsx:150-151 | "ACT rule" was not explained at first use. | Now "standard test rule (ACT rule)". |
| PageEvidence.tsx:260, 322 | "ACT test" and "ACT rules are evaluated in a separate browser session". | Now "failed a standard test rule (ACT rule)" and "the rule check (Alfa) runs in a separate browser". |
| PageEvidence.tsx:294 | "Selector for developers" used a technical word alone. | Now "Element locator (CSS selector), for developers". |
| PageEvidence.tsx:165 | "Alt text" was never explained. | Added "Alt text is the text a screen reader reads for an image." |
| PageEvidence.tsx:189 | "alt attribute" was jargon. | Now "no alt text (alt attribute)". |
| AlfaEvidenceNote.tsx:8 | "engine diagnostic" and "historical report" were jargon. | Now "the rule check's message" and "an older report". |
| IssueEvidence.tsx:275 | The hint "Severity × how many pages it touches" used a symbol. | Now "Based on how serious the issue is and how many pages have it." |
| Issues.tsx:634/660/667, PageEvidence.tsx:228, MethodCoverageLedger.tsx:121 | "n/a" | Now "Does not apply", as TERMS requires. For the missing load time and the checks that did not run, "Not recorded" and "No result" are more accurate. |

#### W3C COGA (consistent terms, one idea per chunk, examples)

| File:line | Problem | What I did |
| --- | --- | --- |
| IssueEvidence.tsx:56-60 | The issue page said "Needs confirmation" / "Informational evidence", but the table said "Needs review" / "Informational". | Both screens now use `REVIEW_TYPE_LABEL`. |
| Issues.tsx:695-701 | The lane labels were hard-coded. | Now `REVIEW_TYPE_LABEL`. |
| PageEvidence.tsx:343-353, Diff.tsx:23-26 | Check names ("axe-core", "keyboard probe", "Responsive", "Semantic") differed from TERMS and from each other. | Both now use `CHECK_LABEL`. |
| IssuePagesTable.tsx:375 | Status chips showed raw values ("remediated", "false positive"). | Now `STATUS_LABEL` ("Fixed", "Not a problem"). |
| Diff.tsx:192 | Status and outcome keys were shown raw, and "cant_tell" was labeled "manual review". | Statuses now use `STATUS_LABEL`. "cant_tell" is now "Needs review (cannot tell)". |
| Diff.tsx:200 | Coverage states were shown raw ("complete", "disabled"). | They now use the same words as the "What was checked" list ("Ran", "Partly ran", "Not recorded", "Not selected"). |
| Many files | Mixed wording for the same things: finding / instance / issue group / evidence group, coverage / method, scan (for the results). | Changed to TERMS: occurrence, issue, check, what was checked, report. |
| MethodCoverageLedger.tsx:70 | The heading "What this scan actually checked". | Now "What was checked", the TERMS word. |
| Issues.tsx:305, IssueEvidence.tsx:286 | "Responsibility" | Now "Who fixes it" on both screens. |
| Issues.tsx:764 | The search placeholder gave no example. | Now "Search by issue name or WCAG number, such as 1.4.3". |
| ReportSummary.tsx:53 | "Reached by operating controls" | Now "Reached by using controls, such as menus". |
| ReportWorkspaceNav.tsx:35 | The nav name "Report workspace" | Now "Report views". |

### Left for a decision

1. **PageEvidence status chip shows raw values** ("in progress", "remediated", "false positive").
   It uses the shared `StatusChip` in `components/ui.tsx`, which renders `value.replace(/_/g, " ")`.
   That file is not assigned to me. The fix is one line: have `StatusChip` render
   `STATUS_LABEL[value]`.
2. **Backend text, out of scope:**
   - `method.label`, `method.result`, `method.description`, and `method.caveat` in
     MethodCoverageLedger. The labels probably still say "axe-core" and similar; they should be
     `CHECK_LABEL` names.
   - The Diff `limitations` notes.
   - Issue titles, `evidence_summary`, `failure_summary`, `manual_review_hint`, `fix_steps`, and
     the comparison link labels.
3. **A shared label missing from terms.ts:** there is no `LEVEL_LABEL` (A → "Level A", BP →
   "Best practice"). I wrote the mapping inline in ConformanceBadge.tsx and IssueEvidence.tsx.
   Suggestion: add `LEVEL_LABEL: Record<ConformanceLabel, string>` to terms.ts.
4. **Coverage state words:** the words for coverage states (Ran / Partly ran / Not recorded /
   Not selected) are duplicated between `METHOD_STATE_LABEL` in MethodCoverageLedger and the new
   `COVERAGE_STATE` in Diff.tsx. A shared map in terms.ts would keep them in step.
5. **Trail labels left as they are:**
   - `ISSUE_SCREENSHOTS_VIEW = "Issue screenshots"` and `ISSUE_PAGES_VIEW = "Pages"`: ReportCrumb
     must show the same words, and ReportCrumb is not my file.
   - The Diff trail label "Verify changes": this is the tab name.
6. **Names of the expert-tools links:** "Rule check details (axe and Alfa)" and
   "Image text check ({n} images)" should match whatever the A11y and Findings routes now call
   themselves. Those files belong to another agent; align the names after merge.
7. **WCAG spelled out using `<abbr title>`:** this is a sufficient technique for 3.1.4 (H28), but
   a title is hard to reach by touch or keyboard. The ACT note and the Diff note spell WCAG out in
   full. If the product wants the full form in visible text at the first use on every screen,
   that is a design decision.
8. **Priority tier words** "High / Medium / Low" and **difficulty values** "Beginner /
   Intermediate / Advanced" were left as they are. They are plain already.
9. **Tests** were not edited, as instructed. Known string matches to update:
   tests/ui/test_expert_interactions.py references at least one changed string ("Issues Found",
   "Evidence group not found", "Needs confirmation", "Remediation workbook", or
   "DOM States Found"). Check it against section 2.

## Part D: Rule check and image views, page inspector, product roadmap

### Findings

#### ISO 24495-1 (find, understand, use; relevant)

| file:line | Problem | Action |
| --- | --- | --- |
| A11y.tsx:103, A11yByRule.tsx:93 | Titles used internal jargon: "WCAG DOM-engine findings". | Changed to "Rule check issues by WCAG criterion" and "Rule check issues by rule". |
| A11y.tsx:153-158, A11yByRule.tsx:162 | The empty state named engines and "static-only crawl mode", and the button said only "New scan". | Rewrote with the check names. Explained static-only mode. Button is now "Start a new scan". |
| A11y/A11yByRule/GroupedFindings/FindingDetail status selects | Options showed raw values such as `in progress` and `false positive`. | Options now use `STATUS_OPTION_LABEL`. Breakdowns and cells use `STATUS_LABEL`. |
| A11yByRule.tsx:375 | The status cell showed the raw `finding.status` value, for example `accepted_risk`. | Uses `STATUS_LABEL`. |
| GroupedFindings.tsx:242, A11yByRule.tsx:272 | The status breakdown listed raw keys, for example `false_positive (3)`. | Uses `STATUS_LABEL`. The empty value is "None", not "n/a". |
| FindingDetail.tsx:62 | The toast showed the raw value: "Status updated to in_progress". | Changed to "Status changed to In progress", using `STATUS_LABEL`. |
| Inspector.tsx:535-551 | The error named "login-protected" and "inspected", and the button said "stored page evidence". | Changed to "sign-in scan". The button is "Back to page evidence". |
| Inspector.tsx:577-590 | The render note used "Stored render", "Captured state", "Live render", and a bare HTTP code. | Changed to "Saved copy", "Saved page state", and "Live page". The code now reads "(server code 404)". |
| Inspector.tsx:639-661 | Two failure messages said what happened but were hard to act on. | Each now says what happened, then the next step. |
| Inspector.tsx:856 | "in another state" did not say how to reach that state. | Added "Choose it in the Page state list." |
| Tracking.tsx:120-141 | The subtitle said "reconciled against the actual code". The intro used coverage jargon. | Rewrote in plain words. Kept the fact that "a check does not test every part of a requirement". |
| Tracking.tsx:333 | The footer read "Long-form version with the verification map". | Changed to "For more detail, including how each check is verified, see … in the Axcess source code." |
| GroupedFindings.tsx:478 | The link text said "view in audit". | Changed to "Page evidence". |

#### U.S. Federal Plain Language Guidelines (main point first, short sentences, active voice)

| file:line | Problem | Action |
| --- | --- | --- |
| A11y.tsx:196-208 | The scope banner was one dense, passive, 80-word paragraph. | Split it into short active sentences, with an example ("for example that an image has alt text"). |
| A11yByRule.tsx:110-122 | The "fixing axis" and "reporting axis" jargon had no clear main point. | Leads with "Each issue is one rule from one check", then gives the 800-occurrence example. |
| GroupedFindings.tsx:108-114 | Used "bucketed" and "remediation rule book is keyed on". | Two plain criteria and one outcome ("same suggested fix"). |
| Inspector.tsx:404-427 | The missing-element messages ran two clauses together with a semicolon or comma splice, and some started in lowercase. | Now full sentences. "activating" became "clicking" to match the picker's "After clicking …" wording. The messages still stop at "flagged" and do not overstate. |
| Inspector.tsx:880-884 | The standing note was two long sentences ("forced visible to be highlighted"). | Now four short active sentences. The styling caveat and the no-scripts caveat are both kept. |
| Inspector.tsx:866 | "This scan was run without storing rendered pages, the page is re-rendered live on demand." was passive, with a comma splice. | Changed to "This scan did not save copies of pages, so Axcess loads the live page each time you open it." |
| Tracking.tsx:271 | "deterministic pipelines need only chromium (no Ollama)…". | Changed to "{n} checks use fixed rules. They need only the Chromium browser…". |
| Buttons in A11yByRule and GroupedFindings bulk bars, FindingDetail | "Apply to all N" and "Save" did not name their object. | Changed to "Change status of all N" and "Save status". |

#### WCAG 3.1.3 / 3.1.4 / 3.1.5 (unusual words, abbreviations, reading level)

| file:line | Problem | Action |
| --- | --- | --- |
| A11y.tsx:204, Tracking.tsx:137 | WCAG was not spelled out anywhere on these screens. | Spelled out as "Web Content Accessibility Guidelines (WCAG)" in the page intro (see Deferred about titles). |
| A11y.tsx (many), A11yByRule.tsx | Used "SC" and "success criterion". | Now "WCAG {n}", "WCAG criterion", and "Back to all WCAG criteria". |
| Tracking.tsx:216-219 | Column headers "SC", "Lvl", and "A/AA". | Now "Number", "WCAG criterion", "Level", and "Level A and AA". |
| A11y.tsx:199, A11yByRule.tsx:219 | ACT was unexplained in places. | Now "(ACT, Accessibility Conformance Testing)" and "Failed a standard test (ACT)". |
| A11y.tsx:403, A11yByRule.tsx:300 | Headers "Target selector" and "Target". | Changed to "Element locator (CSS selector)". |
| A11y.tsx:452, A11yByRule.tsx:355 | "show HTML" (a snippet). | Changed to "Show element code (HTML)". |
| FindingDetail.tsx:209 | Header said "VLM classification". | Changed to "Image type, suggested by AI (vision model)". |
| FindingDetail.tsx:201, Findings.tsx | Used "Alt attribute" and "Alt". | Changed to "Alt text". GroupedFindings explains alt text once. |
| Findings/GroupedFindings/FindingDetail | Used "OCR text" and "Image text (OCR)". | Changed to "Text read from image (OCR)". The acronym is not spelled out; see Deferred. |
| FindingDetail/GroupedFindings | "Above fold" is jargon. | Changed to "Visible without scrolling". |
| FindingDetail.tsx:158 | "Inline SVG" and "image blob" were unexplained. | Changed to "Graphic in the page code (inline SVG)" and "No saved image file". |
| Tracking.tsx:271-273 | "Ollama daemon" was unexplained. | Changed to "Ollama, an app that runs AI models on this computer". |
| Tracking.tsx:357 | "Shipped" is jargon. | Changed to "Available". |
| DomSource.tsx:213 | Said "display capped; the capture continues". | Changed to "only these lines are shown; the page code goes on past the last one". |

#### W3C COGA (consistent terms, one idea per chunk, examples)

| file:line | Problem | Action |
| --- | --- | --- |
| All files | Mixed terms: finding, violation, result, "×", "location", and "rule groups". | Uses occurrence, issue, and image, per the TERMS table. |
| A11y/A11yByRule source chips and columns | Tool names such as "axe-core" and "Siteimprove Alfa", with a "Source" column. | Uses `CHECK_LABEL` and a "Check" column. |
| A11y/A11yByRule | "Needs expert review", "review leads", and "Expert review leads". | Changed to "Needs review" (a cantTell result counts as Needs review). |
| Findings/GroupedFindings/FindingDetail | Images were called "findings", for example "Finding #12". | Changed to "Image #12", "Images", and "Back to images". Breadcrumb/origin labels were updated to match. |
| Inspector tabs | "Rendered page" / "DOM source", and panel names "Rendered page" / "Loaded DOM". | Changed to "Saved copy" ("Live page" when no copy was saved) and "Page code (DOM)". Tab text and panel names now match. |
| Inspector.tsx "capture" (many) | Used "capture", "stored capture", "re-rendered". | Changed to "saved copy", "copy", and "page state". |
| Tracking | Used coverage, pipeline, and engine. | Changed to "What Axcess checks", "Checks", "Tool", "Checked now", "Not checked yet", and "AI reviews". |
| All "n/a" cells | Used "n/a". | Changed to "Does not apply" in table cells. Where the real meaning is known, the text says it: "No image", "No text found", "Not classified". Breakdown lines use "None". |
| DomSource.tsx:265 | This region would have had the same name as its parent region ("Page code (DOM)"), and duplicate names break landmark uniqueness. | Renamed it "Scrollable page code (DOM)". |

#### Accessibility wiring fixed along the way

- Inspector.tsx:622: the "Open live page" button's `aria-label` was
  "Open {title} in a new tab". That name did not contain the visible text, so
  it failed WCAG 2.5.3. It is now "Open live page: {title} (opens in a new
  tab)".
- A11y.tsx:285 and A11yByRule.tsx:259: the external "About this rule" links
  now include sr-only "(opens in a new tab)".
- GroupedFindings.tsx:448: the ▸/▾ glyph on the pages toggle is now
  `aria-hidden`, so it is no longer read aloud as "black right-pointing
  triangle".
- FindingDetail keyboard hint: the text comes from `STATUS_KEY_MAP` and
  `STATUS_OPTION_LABEL`, so it no longer shows raw values. The shortcuts
  (0–5) still work.

---

### Left for a decision

1. **statusDecision.ts (not mine)**: the rationale prompt reads "Document why
   {subject} should be marked {status.replace('_',' ')}". It shows raw values
   such as "remediated" and "false positive", and uses "rationale". It should
   use `STATUS_OPTION_LABEL`. It is used by all bulk and single status
   controls in my files. The window.alert "A decision rationale is required.
   No status was changed." also needs plain words.
2. **ui.tsx (not mine)**:
   - `StatusChip` shows `value.replace(/_/g," ")` (raw, for example
     "remediated"). It should use `STATUS_LABEL`. It appears in Findings and
     GroupedFindings.
   - `SeverityChip` shows raw lowercase severities.
   - `AltTag` shows `missing` and `alt=""`.
   - `TablePagination` builds "{label} pagination".
3. **Severity and axe impact labels**: there is no shared SEVERITY_LABEL or
   IMPACT_LABEL in terms.ts. The Findings filter now shows sentence case
   locally, but the chips and the GroupedFindings severity breakdown still
   show raw words (critical / major / minor / info; axe critical / serious /
   moderate / minor). Two options:
   - Add `SEVERITY_LABEL` and `IMPACT_LABEL` to terms.ts.
   - Decide that the raw words are fine.
4. **Classification labels**: there is no shared CLASSIFICATION_LABEL.
   Findings and FindingDetail use a local `sentenceCase`. A shared map could
   use better words, for example `no_meaningful_text` -> "No meaningful
   text".
5. **OCR / SVG / ACT abbreviations**:
   - "OCR" appears as "Text read from image (OCR)" and is not spelled out
     (optical character recognition), to keep column headers short.
   - "SVG" / "SVG text" placeholders are unchanged.
   Decide whether glossary.md counts as the WCAG 3.1.4 mechanism, or whether
   each screen should spell them out.
6. **WCAG spelled out**: on the A11y page and Tracking, the spelled-out form
   is in the intro paragraph, not the page title, where "WCAG" first appears.
   A11yByRule, GroupedFindings, Findings, and FindingDetail do not spell out
   WCAG at all ("WCAG {criterion}" subtitle, "Group by WCAG criterion").
   Decide whether the app shell or glossary covers this, or whether each page
   needs it.
7. **Document titles (App.tsx, not mine)**: these still say "DOM-engine
   evidence", "DOM-engine rules", "Image evidence", "Grouped image evidence",
   "Finding evidence", and "Coverage tracking". They should match the new
   headings (`Rule check issues by WCAG criterion`, `Rule check issues by
   rule`, `Images`, `Images, grouped by issue`, `Image #n`, `Product
   roadmap`). tests/ui/test_accessibility_axe.py:604-621 pins the current
   titles.
8. **Backend text**: out of scope and unchanged:
   - `help`, `failure_summary`, `remediation_hint`, and group `label`.
   - Tracking `method_labels` (for example "Automated", "Partial",
     "AI-assisted"; they appear in the "Where it stands" badges and the
     method filter chips), and the roadmap rows, including their "Model:" and
     "Reuses:" text.
   - The `p.pipeline` code chip, and `render.error`.
9. **Tracking "Where it stands" column**: it mixes method labels (current
   rows) and progress labels (AI rows). A product decision could split it.
   The "Group" column and "Not checked yet" badge repeat each other for
   future rows, as they did before.
10. **Breadcrumb origin values**: these are visible crumb text passed through
    the `origin` query value (`Rule check issues by WCAG criterion`, `Rule
    check issues by rule`, `Image #n`). Old bookmarked URLs keep their old
    origin text until they are followed again.
11. **Existing logic bug (not fixed; logic)**: A11y.tsx hides the
    best-practice drill-down because `wcagSc ? … : …` treats `""` as the
    roll-up. My heading fallback for an empty criterion is harmless but never
    shown.
