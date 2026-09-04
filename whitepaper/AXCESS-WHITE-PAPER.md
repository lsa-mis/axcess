# Axcess: Evidence Before Verdicts

**A short product white paper**

**Updated:** August 31, 2026

> **Important:** Axcess helps people find, understand, and review accessibility barriers. It does not certify that a website conforms to WCAG, prove legal compliance, or replace testing by people with disabilities.

## Executive summary

Axcess is a local-first accessibility auditing workbench. It scans one authorized website at a time, collects evidence from several testing methods, groups repeated results into understandable issues, and helps an accessibility professional decide what should be fixed first.

“Local-first” means that reports, screenshots, and other scan evidence stay on the auditor’s computer by default. This is especially valuable when reviewing private, sensitive, or login-protected websites.

Axcess began with a narrow goal: find images of text across large websites more reliably. That first problem revealed a larger need. Accessibility professionals did not simply need another scanner. They needed a trustworthy way to connect automated results, browser behavior, human judgment, remediation work, and follow-up scans without losing the evidence behind each decision.

The project’s guiding idea is therefore simple: **preserve the evidence before presenting a verdict.**

## 1. What is Axcess?

Axcess is a desktop and local web application for expert accessibility review. It is designed to support the full path from discovery to verification:

1. An auditor chooses an authorized website and defines the scan boundaries.
2. Axcess visits pages and renders them in a real browser.
3. Several independent methods test the page and record what they observe.
4. Axcess groups related results into issues and explains their likely user impact.
5. A human reviews the evidence, records a decision, and shares remediation guidance.
6. A later scan shows which issues are new, still present, or resolved.

The completed scan is the source of truth. Every page, issue, screenshot, selector, and decision is tied to a specific report. Results from different scans are not silently mixed.

Axcess is not a generic web scraper, a public scanning service, or an automatic compliance judge. It is an evidence workbench built to help a qualified person make better, faster, and more defensible decisions.

## 2. The initial why

The original motivation was a concrete gap in existing accessibility tools.

An accessibility lead needed to find possible failures of WCAG 1.4.5, Images of Text, across an entire website. Existing tools did not provide strong enough coverage at that scale. Checking every page and image by hand was slow, repetitive, and easy to miss.

The first version of Axcess was designed to:

- crawl a website without sending its contents to a cloud service;
- find images and text embedded inside them;
- use optical character recognition, or OCR, to detect text;
- use an optional local vision model to understand the image’s purpose;
- compare visible image text with alternative text;
- prioritize likely barriers for human review; and
- support rescanning so an auditor could verify fixes.

The intent was never to remove the expert from the process. It was to reduce repetitive discovery work and give the expert better evidence.

## 3. How and why the vision evolved

As Axcess developed, the team learned that finding a possible problem is only one part of an accessibility audit.

A raw result does not answer the questions people actually ask: What happened? Who is affected? Which pages contain it? How certain is the result? What should change? How will the fix be verified?

The project therefore expanded from an image-text scanner into a broader accessibility evidence workbench. New testing layers were added for page structure, names and roles, keyboard behavior, focus, responsive layouts, media behavior, and contextual meaning. Manual evaluation was added because many accessibility questions cannot be answered honestly by automation.

The product also became more explicit about uncertainty. A deterministic browser rule, an observed interaction, and an AI-assisted suggestion are not treated as equally certain. Each result keeps the name of the method that produced it, its limitations, and whether a person must confirm it.

Finally, the project grew from a developer-run local service into a desktop application. This made the local-first model easier to use while preserving its privacy boundary.

The evolved purpose of Axcess is not “automate accessibility.” It is to create a clear and inspectable chain from evidence to human decision to verified improvement.

## 4. Existing features

Axcess currently includes:

- **Scoped website scanning.** The auditor can limit a scan by path, host, page count, depth, and rate.
- **Public and login-protected site support.** A visible browser allows the auditor to sign in directly without giving credentials to Axcess.
- **Real browser rendering.** Playwright Chromium loads JavaScript-driven pages before testing them.
- **Multiple testing methods.** Axcess uses axe-core, Siteimprove Alfa, OCR, optional local AI analysis, and browser probes for keyboard, focus, responsive, visual, and media behavior.
- **Honest WCAG capability tracking.** The project maps its testing methods across all 55 WCAG 2.2 Level A and AA success criteria. Its current methods can contribute evidence to 29 criteria; this does not mean that every enabled method completed successfully in every scan, or that those criteria were proven to conform.
- **Issue grouping.** Repeated occurrences are grouped into actionable issues while preserving exact page and element references.
- **Evidence review.** Reports include the testing source, confidence, user impact, affected pages, selectors, snippets, screenshots, remediation guidance, and verification steps where available.
- **Human decision records.** Auditors can review findings, record outcomes, and keep manual evidence separate from machine-generated evidence.
- **Exports.** Reports can be shared as Excel workbooks, Markdown, CSV, JSON, and Jira-oriented files.
- **Initial rescan comparison.** Image findings can be compared across scans. Extending trustworthy comparison to every testing pipeline is an important next step.
- **Local storage and private operation.** Scan data remains in local SQLite and evidence files by default. Axcess has no telemetry and does not silently send reports to an external model.
- **Accessible product interface.** The Axcess interface is designed and tested for keyboard use, screen readers, zoom, reflow, visible focus, and strong color contrast.

## 5. Long-term goals and recommended direction

Axcess’s strongest direction is to become an **offline, evidence-first accessibility quality system**. It should not compete by collecting the largest number of scanner engines. Its advantage should be the most trustworthy path from coverage planning to reproducible evidence, human judgment, remediation, and verified improvement.

This direction is grounded in [WCAG-EM 2.0](https://www.w3.org/TR/WCAG-EM/), W3C’s methodology for evaluating websites, and the [ACT Rules Format 1.1](https://www.w3.org/TR/act-rules-format/), which provides a useful vocabulary for automated, semi-automated, and manual tests. Both reinforce an important product principle: automated results are evidence, not proof that a site conforms.

### First: make coverage truthful and inspectable

Before adding more detectors, Axcess should record exactly what happened for every page, state, and testing method. A method may have completed and found nothing, failed, been skipped, been unavailable, or produced a result that still needs human review. Those outcomes must never look the same in the report.

Coverage should be shown across several separate dimensions:

- which pages and representative templates were evaluated;
- which interactive states and essential user journeys were tested;
- which browsers, viewports, preferences, and assistive-technology baselines were included;
- which automated, behavioral, AI-assisted, and manual methods completed; and
- which questions remain untested or require human judgment.

This is more useful and more honest than one accessibility score. W3C warns that combined scores can be misleading because WCAG has no single reliable rating system.

### Second: test experiences, not only URLs

The largest coverage gap is not another static scanner. It is everything that happens after a person interacts with a page: opening a menu, revealing a dialog, selecting a tab, encountering a form error, signing in, or completing a multi-step task.

Axcess should add safe, user-authorized journey recipes. An auditor could record the steps of an essential process and allow Axcess to retest each meaningful state. Every state should retain its action path, rendered page evidence, screenshot, browser settings, rule versions, and any incomplete network activity. Axcess should never blindly submit a purchase, delete data, or perform another consequential action.

The best coverage model would combine:

- axe-core as the stable deterministic baseline;
- Alfa as an independent second engine, retained only where measured results add confirmed value;
- browser probes for keyboard, focus, reflow, text spacing, pointer interaction, motion, hover content, and form behavior;
- guided manual checks for meaning, exceptions, and assistive-technology behavior; and
- optional local AI for narrow questions where it can show evidence, express uncertainty, and abstain.

### Third: make issues durable work objects

Raw observations, grouped issues, and remediation work should be separate concepts.

An observation is an immutable record of what a method saw. An occurrence is that result at one target and state. An issue groups occurrences that probably share a fix. The workflow then records what people decided and did about the issue.

Axcess should separately track:

- the review decision: unreviewed, confirmed, rejected, or inconclusive;
- the remediation state: open, planned, in progress, ready for verification, verified, deferred, or accepted risk; and
- the comparison result: new, unchanged, changed, no longer observed under equivalent coverage, or not comparable.

“Not found in the next scan” should not automatically mean “fixed.” The same page, state, method, and rule version must be comparable, and a confirmed fix should still pass a relevant retest or human verification.

Axcess should also suggest shared root causes across templates and design-system components. One navigation component fixed once may remove hundreds of page-level occurrences. Suggested groups should remain inspectable and editable by a person.

### Fourth: make the report a product, not an export afterthought

The primary human-facing deliverable should be a self-contained, keyboard- and screen-reader-accessible HTML report that works without Axcess running and loads no remote assets. The local database and evidence files should remain the source of truth. The report should answer, in order:

1. What was evaluated?
2. What was not evaluated, skipped, or incomplete?
3. What should be fixed first, and why?
4. Which pages, states, components, and user journeys are affected?
5. What evidence supports each claim?
6. What needs manual review?
7. What changed since a comparable report?
8. Which tools, rules, models, browsers, settings, and versions produced the evidence?

The report should use transparent reasons for priority—user impact, essential-task risk, prevalence, confidence, regression status, and fix leverage—rather than hiding them inside one score.

Axcess should produce different views from the same local evidence:

- a short leadership summary;
- a design and engineering work queue;
- a WCAG-EM-style evaluator report;
- a versioned Axcess JSON file as a portable machine-readable export;
- an optional EARL JSON-LD export for accessibility-tool interchange; and
- an optional SARIF export for developer and CI systems.

Excel, CSV, Markdown, and printable output remain useful secondary formats. A VPAT or Accessibility Conformance Report should never be generated automatically from a scan; at most, Axcess could prepare an evidence worksheet for a qualified person to complete.

### Fifth: define “fully offline” precisely

Scanning a live website still requires a connection to that authorized target. For Axcess, fully offline should mean that no evidence, prompts, telemetry, or results are sent to a third party.

Two modes would make that promise clear:

- **Private live scan:** the browser may contact the approved target and required site resources, while analysis stays local and all other outbound traffic is blocked or reported.
- **Air-gapped replay:** an approved capture is imported and analyzed without any live network access.

Both modes should bundle the required rules, help text, fonts, browser runtime, schemas, and optional local model packs. Completed scans must record exact versions and must never be silently reinterpreted after an update. Shareable reports should offer a redacted profile, hashed evidence manifest, and clear retention and deletion controls.

### A practical order of work

1. Build a per-page, per-state method ledger and correct the report language.
2. Make scan evidence immutable and reproducible, including explicit scan-to-analysis bindings.
3. Separate observations, issue groups, review decisions, remediation states, and verification.
4. Restore a complete keyboard-first flow from coverage review to manual checks and final report.
5. Add accessible offline HTML and coverage-aware comparison across all pipelines.
6. Add recorded journeys and representative cross-browser testing.
7. Expand high-value deterministic probes and guided manual testing.
8. Validate every detector against expert-reviewed real-world examples before promoting it.
9. Add report conversation only after provenance, privacy, and issue management are dependable.

## 6. Interesting directions and open questions

The following questions could guide future research and product decisions.

### Better evidence

- Could Axcess show when two independent methods agree, disagree, or observe different parts of the same barrier?
- How should evidence age over time as pages, standards, browsers, and testing engines change?
- Can the product explain uncertainty in language that is useful to both experts and content owners?
- What minimum evidence should be required before an issue can be called “verified fixed”?

### Better outcomes

- Can Axcess measure whether fixes improved a real user task, not only whether a rule stopped firing?
- Could recurring root causes reveal where a design system, content template, or development process should change?
- What is the best way to turn repeated findings into prevention guidance for designers, developers, and editors?
- How should accepted-risk decisions expire so that old exceptions do not hide new regressions?

### Human participation

- How can people with disabilities contribute lived-experience evidence directly to a report?
- Which decisions should always require manual or assistive-technology testing?
- Could Axcess help teams plan a manual test without making the process feel like a checklist exercise?
- Which browser and assistive-technology combinations should define each organization’s accessibility-support baseline?

### Privacy and trust

- What is the smallest amount of report evidence a model needs to answer a useful question?
- How can sensitive content be redacted while keeping enough context for a valid accessibility decision?
- What proof should Axcess provide that report data stayed on the local device?
- How should offline rule and model packs be signed, updated, rolled back, and connected to historical results?

### Product direction

- Should Axcess remain primarily a single-expert desktop tool, or should it eventually support controlled team workflows?
- Could a shared, anonymized test corpus improve detector quality without exposing scanned content?
- What would responsible integration with issue trackers, design systems, and continuous delivery look like while preserving explicit human approval?
- Should issue work live inside one historical report, or in durable remediation cases linked across explicit report comparisons?
- Which essential journeys may Axcess safely replay, and which actions must always require confirmation?

## Conclusion

Axcess started by solving one difficult accessibility problem: finding images of text across a website. It evolved into a broader response to an even more important challenge—the loss of context, confidence, and accountability between a scanner result and a real fix.

Its promise is deliberately modest but meaningful. Axcess does not declare a website accessible. It helps people understand how thoroughly it was evaluated, collect better evidence, make clearer decisions, communicate what needs to change, and verify that the change actually happened.
