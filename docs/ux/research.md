# Axcess UX refresh: research

Status: Phase 1 output, 2026-09-23. This file is the shared state for the IA, the Figma mock and every critic.
Nothing in `src/` was changed. The repo and `data/audit.db` were read only (sqlite opened with `-readonly`).

Figma file: https://www.figma.com/design/rLrpOJZ73V1qXS4qzy5t3p

Every claim below is tagged **(read)** when it came from the code or database, **(inferred)** when reasoned from them, or **(A#)** when it rests on an assumption listed in section 8.

---

## 1. Current screens, routes and components

### 1.1 Routes (all under `/app/`, `src/audit/web/frontend/src/App.tsx:55-94`) (read)

| Route | Shows | What the user can do there |
|---|---|---|
| `/` Dashboard | Banner while a scan runs. A "Waiting on you" card that covers the **newest report only**. 4 stat cards. The 6 most recent reports. | Open issues; open a report |
| `/scans` | Table of reports, 10 per page. A protected-report table when identity is ready. | Search by URL or number; delete (`window.confirm`); start a new login scan |
| `/scans/new` | Public or Login mode, the scan form and a summary rail | Configure and start a scan |
| `/scans/:id` Overview | **While running:** a progress panel with Stop. **When done:** stat cards, the method coverage ledger, and a collapsed "Expert tools and scan details" section. **When failed:** a partial report with `failure_reason`. | Export, retry, delete |
| `/scans/:id/issues` | Flat 9-column table: Issue, Type, WCAG, Priority, Pages, Occurrences, Difficulty, Responsibility, About. The About row expands to show what, why, fix, done-when. | Search, Level and Type filters, sort, Export. **No status column, no status change, no pipeline column, no bulk actions.** |
| `/scans/:id/issues/:key` | Lane card, facts, pages table, a collapsed fix, and **at most 3 sample selectors** | Read only |
| `…/issues/:key/pages`, `…/screenshots` | Pages for one issue; circled screenshots | Navigate only |
| `/scans/:id/pages/:pageId` | Finding cards for one page: selector, screenshot, text-fragment link | Read only |
| `…/pages/:pageId/inspect` | Page state picker, highlighted iframe, DOM source with Copy | Navigate only |
| `/scans/:id/findings`, `/findings/grouped`, `/findings/:id` | Image-of-text rows, groups and single findings | Filter; **bulk status per group**; single status with **0 to 5 single-key shortcuts** |
| `/scans/:id/a11y`, `/a11y/by-rule` | DOM-engine rollup by success criterion and by rule | **Per-row status select**; **bulk status per rule** |
| `/scans/:id/diff` "Verify changes" | Before/after, coverage, and 5 categories: New, Still detected, Changed, No longer detected, Cannot compare | Filter by category and method. **No baseline picker.** |
| `/scans/:id/protected/*` | Protected (authenticated) companion flow: stepper, redacted issue index, manual checks | Stop, pair, redacted export, record manual outcomes |
| `/tracking` "Product Roadmap" | Tool coverage matrix (about the product, not the site) | Filter, sort |

### 1.2 App shell (read)
- A 256 px sidebar with Dashboard, Reports and Product Roadmap. A sticky 72 px top bar with the crumb, Search (Ctrl or Cmd K), Give feedback, and Create New Scan.
- Report tabs (Overview, Issues, Verify changes) appear on some routes only; the expert routes have none.
- There are 4 separate orientation mechanisms: the crumb chain (up to 12 levels), the sub-trail, in-page crumbs and ad-hoc back buttons.

### 1.3 Components worth keeping (read)
`Button`/`LinkButton` (primary, secondary, danger, ghost; 44 and 52 px), `StatCard`, `PageHeader`, `ReportHeader`, `Disclosure`, `Tabs` (blue active fill with a sliding indicator), `Select`, `Checkbox`, `SwitchRow`, `SeverityChip` (`.sev-chip`), neutral `StatusChip`, `ConformanceBadge` (A, AA, AAA, BP, tuned for 7:1), `ScanStatusBadge`, the sortable-table pattern (header button, `aria-sort`, a visible sort line, sticky first column in a named scroll region), `IssueEvidence`, `PageLink`, `DomSource` (virtualized, copy), `MethodCoverageLedger`, `ScanProgressPanel`, `ExportMenu`.

Duplicates and drift:
- `ImpactChip` is defined twice.
- Two label sets exist for one method-state enum ("Checked" vs "Ran").
- The sortable table is implemented twice.

### 1.4 Accessibility features already present (read)
- A skip link to `#main`, and focus moves to `main` on route change with a polite "page loaded" message.
- Named landmarks and one h1 per route.
- Sortable tables with a caption, `scope` and `aria-sort`.
- Live regions for filter counts and scan progress.
- 44 px targets in most places, and several reduced-motion guards.

## 2. The data a finding and an issue carry

### 2.1 Finding (one row = one place on one page) (read)
DOM findings live in one table, `page_a11y_findings`. The `pipeline` field says which detector produced the row: `axe`, `alfa`, `keyboard`, `responsive`, `focus`, `visual`, `semantic`, `protected_image`.

| Field | Meaning | Notes for design |
|---|---|---|
| `rule_id`, `help`, `help_url` | Detector rule and a one-line description | Semantic rows use `semantic:<sc>`, and their help text changes per instance |
| `wcag_sc`, `wcag_scs`, `wcag_level` | Primary SC, every mapped SC, strictest level | NULL means best practice (axe best-practice rules) |
| `impact` | critical, serious, moderate, minor, or NULL | **Alfa rows are always NULL.** Semantic rows map LLM confidence to impact (high→serious). |
| `target_selector` | CSS selector (axe, probes) or JSON with an XPath (Alfa) | Selectors can be long; they must wrap |
| `html_snippet` | outerHTML, up to 4,000 chars | For Alfa it holds JSON, not HTML |
| `failure_summary` | Why it failed | Semantic rows embed an LLM "Suggested fix" here |
| `engine_outcome` | `failed` or `cant_tell` (Alfa only) | A cant_tell result is a lead, not a failure |
| `engine_evidence_json` + read-time `engine_evidence_status` | Alfa evidence: complete, truncated, recovered, unavailable | Evidence completeness is a trust input |
| `screenshot_hash` | Circled screenshot blob | 802 of 1,314 axe rows have one; semantic, Alfa and visual rows have none |
| `revealed_by`, `revealed_state_key` | The control that had to be clicked to reveal the problem, and its click chain | This is the raw material for "Steps to reproduce" |
| `status` | new, reviewing, in_progress, remediated, accepted_risk, false_positive | Stored per finding. **Reset to `new` on every rescan.** |

Image-of-text findings use separate tables: `findings`, `images`, `page_images`, `analyses`. They carry:
- severity (critical, major, minor, info), computed from a priority score;
- `ocr_text` and **`ocr_confidence`**, the only numeric confidence stored anywhere;
- `vlm_classification` and its rationale;
- alt adequacy (missing, inadequate, partial, adequate), recomputed on every read;
- no CSS selector.

### 2.2 Issue (grouped view) (read)
- **Grouping key:** (pipeline, rule_id), plus the outcome for Alfa. Resulting `issue_key` values: `axe:link-name`, `alfa:sia-r11:failed`, `semantic:2.4.4`, `image:essential_inadequate`.
- **Engines are never merged.** axe `link-name` and Alfa `sia-r11` appear as two rows even when they flag the same 143 elements.
- **Fields:** title, conformance, WCAG SC and name, responsibility, abilities affected, difficulty, occurrence and page counts, priority, impact, `status_summary` (counts per status), `review_lane` (likely_barrier, expert_review, informational), `evidence_confidence` (high, medium, low), description, why it matters, fix steps, acceptance, help URL, and up to 3 sample locations.
- **Priority** = impact weight × log(1 + pages). The default sort is lane, then priority.
- **Remediation text** comes from `rules/audit_report.yaml` cards. Those cards also carry `fix_options` with a label, an approach and a watch-out, but only the XLSX export uses them today.

### 2.3 Cross-run and health data (read)
- **Comparison.** `GET /api/scans/{id}/comparison` returns `new`, `still_detected`, `changed`, `no_longer_detected` and `cannot_compare`, keyed on `issue_key`. Any coverage limitation turns a new or gone issue into `cannot_compare`, so that category dominates by design.
- **What is missing across runs.** There is no "Regressed", no "Ticketed", no ticket key, and no carry-over of status between runs. "No longer detected" is not "Fixed", and the API says so.
- **Scan health.** Available: `status` (running, completed, failed, interrupted), `failure_reason` (exceptions only), `error_count`, per-method counters, and `methods_used[]` with a state per method. Not persisted: skip counts (scope, blocklist, robots, auth wall) and the reasons for login-scan failures.
- **Protected scans.** These store only opaque page keys, never URLs or selectors, and are excluded from comparison.
- **Jira.** Today's Jira export is a CSV with **one row per finding**. It has no Expected Behavior and no fix disclaimer. The XLSX export already builds the root-cause layout with a numbered instances table and fix options.

## 3. Current design tokens and where they fail the bar

### 3.1 Tokens (read; `tailwind.config.ts`, `styles.css`, `fonts.css`)
- **Brand:** U-M Blue `#00274C` (hover `#003A6C`) and Maize `#FFCB05`, both pinned by brand rules.
- **Surfaces:**
  - page `#F7F9FC`, card `#FFFFFF`, muted `#F1F4F8`;
  - borders: decorative `#DCE3EC`, strong `#B8C4D2`.
- **Text:** fg `#111827` (17.7:1), muted `#374151` (10.3:1), subtle `#475263` (7.9:1 on white, 7.17:1 on muted).
- **Severity (text on tint):**

  | Level | Text | Tint | Ratio |
  |---|---|---|---|
  | critical | `#7A0000` | `#FEE2E2` | 9.41 |
  | major | `#6B2E00` | `#FFEBC7` | 8.91 |
  | minor | `#4F4200` | `#FEF9C3` | 9.26 |
  | info | `#1F2937` | `#E5E7EB` | 11.86 |

- **Conformance badges** (white text on fill): A `#A40059`, AA `#4B1D8A`, AAA `#275580`, BP `#4A4A4A`. All are 7.7:1 or better.
- **Type:** Atkinson Hyperlegible Next and Atkinson Hyperlegible Mono, self-hosted variable fonts. The scale is 12, 13, 14, 16, 18, 20, 24, 28, 32 px. Body line height is 1.5, and semibold (600) is the dominant weight.
- **Shape:** radius 8 px on most controls (5 px on small chips, 12 px on overlays), with soft blue-tinted shadows. Spacing is a 4 px scale and content is capped at 1,440 px.
- **Targets:** `min-h-target` 44 px, large buttons 52 px.
- **Focus:** a global 3 px Maize outline with a 2 px offset, plus a `shadow-focus` ring (3 px Blue) on 14 controls.

### 3.2 Failures against the showcase bar (read, contrast computed)
| # | Failure | Bar | Evidence |
|---|---|---|---|
| T1 | The global focus ring is Maize: **1.27 to 1.52:1** on every light surface | 1.4.11, 2.4.13 | styles.css:30-34, confirmed in the built CSS |
| T2 | The docs, the config comment and the code disagree about the ring color | Consistency | tailwind.config.ts:21-24 vs styles.css:31 |
| T3 | Control borders `#B8C4D2` measure **1.60 to 1.77:1**; the switch knob measures 1.77:1 | 1.4.11 | inputs, selects, checkboxes, switch |
| T4 | ImpactChip puts white text on pale tints: **1.07 to 1.24:1** | 1.4.3, 1.4.6 | A11y.tsx:559, A11yByRule.tsx:441 |
| T5 | The running badge drops to 2.88:1 mid-pulse | 1.4.6 | ui.tsx:507 |
| T6 | Links are underlined on hover only; several have no underline at all | 1.4.1 | styles.css:35-40, Dashboard.tsx:190 |
| T7 | No dark theme at all, and no `prefers-color-scheme` | Bar requirement | index.html:7 |
| T8 | No `forced-colors` rules. `shadow-focus` rings, the switch, the active tab and the active nav item probably disappear in High Contrast mode. | Bar requirement | grep: none |
| T9 | 7 animations ignore reduced motion | 2.3.3 | ui.tsx:507, ScanDetail.tsx:451 |
| T10 | Sticky 72 px top bar with no `scroll-padding-top` | 2.4.11 | AppShell.tsx:302 |
| T11 | Targets under 44 px: skip link (36), palette options (36), crumbs (18), PageLink secondary links (17), DomSource icon buttons (38 wide) | 2.5.5 | see tokens research |
| T12 | Single-key 0 to 5 status shortcuts on FindingDetail cannot be turned off or remapped | 2.1.4 (Level A) | FindingDetail.tsx:28-36 |
| T13 | The sort pill is 10.4 px text | Readability | Issues.tsx:527 |
| T14 | 28 `truncate` uses, plus `overflow-x:hidden` on `html` | 1.4.10, 1.4.12 | styles.css:17 |
| T15 | Rationale is collected in `window.prompt`, which cannot show evidence and blocks the page | 3.3.2, usability | statusDecision.ts:22-31 |
| T16 | The running-scan status line toggles every 2 s inside a live region, which is chatty | 4.1.3 | ScanDetail.tsx:549-559 |
| T17 | The command palette does not announce the active option (no `aria-activedescendant`) and does not return focus on close | 4.1.2, 2.4.3 | CommandPalette.tsx |
| T18 | The access gate is a plain-text 401 page that says "Append ?token=… to the URL". There is no form, so a password manager cannot fill it. | 3.3.8 | server.py:641-680 |

## 4. Users, jobs, what they need first, where they hunt

### 4.1 Accessibility analyst (primary)

**Top 3 jobs**
1. Triage a new run: confirm or dismiss each root cause, worst and least certain first.
2. Turn confirmed root causes into Jira tickets in the ITS format.
3. After a rescan, check what went away and what came back.

**Needs to see first**
- Needs-review count and came-back count.
- New since the last run.
- How sure the tool is about each finding.
- Severity.

**Where the current UI makes them hunt**
- Status can be changed only on 4 legacy screens behind a collapsed "Expert tools" section.
- A decision takes 8 or more route changes, a hidden disclosure and a native prompt.
- There is no Jira path.
- The diff is pairwise with no baseline picker.

### 4.2 Developer on an internal app

**Top 3 jobs**
1. Find exactly where the problem is: URL, selector, element, screenshot, and the clicks needed to reveal it.
2. Understand the cause and pick a fix, with trade-offs and a definition of done.
3. See whether their fix worked in the next run.

**Needs to see first**
- The one issue named in their ticket.
- Every instance, with a selector they can copy.
- The recommended fix.

**Where the current UI makes them hunt**
- Evidence is spread over 5 routes.
- The fix and the screenshot never appear on the same screen.
- Only 3 sample selectors are shown.
- Copy exists only for the DOM source.

### 4.3 App owner or leader

**Top 3 jobs**
1. Know the current risk: open blockers and critical issues, and anything that came back.
2. See the trend: better or worse than last time, and credit for fixed work.
3. Know whether to trust the numbers: was the scan complete, did sign-in work?

**Needs to see first**
- A one-sentence status.
- Counts by severity with the change since the last run.
- A trend with a table equivalent.

**Where the current UI makes them hunt**
- The dashboard covers the newest report only.
- There is no trend and no progress view.
- The reviewer rejection rate is hidden in Expert tools.
- "Issues Found" actually counts occurrences.

## 5. Pain points ranked (frequency × severity, each rated 1 to 5)

| Rank | Pain point | F | S | Score | Users hit |
|---|---|---|---|---|---|
| 1 | Triage happens away from the main list: 8+ route changes, native prompts, 3 different status interactions | 5 | 5 | 25 | Analyst |
| 2 | Evidence is split across 5 routes; the fix and the screenshot are never together; only 3 sample locations | 5 | 4 | 20 | Developer, analyst |
| 3 | Triage is lost on every rescan (status resets), so fixed and regressed cannot be tracked | 4 | 5 | 20 | Analyst, leader |
| 4 | Axcess fails its own bar: focus ring 1.5:1, no dark mode, no forced colors, hotkeys that cannot be disabled, white-on-tint chips | 5 | 4 | 20 | Every user of assistive tech |
| 5 | The same root cause appears once per engine (axe and Alfa agree on 143 of 143 link-name elements), and there is no trust signal beyond the lane | 4 | 4 | 16 | Analyst, leader |
| 6 | No Jira path; export is all or nothing, one ticket per finding | 4 | 4 | 16 | Analyst |
| 7 | Inconsistent words: 3 names for the lanes; "Issues Found" counts occurrences; "findings" means image-only in some places | 5 | 3 | 15 | Everyone |
| 8 | No cross-run trend or progress; the dashboard shows the newest run only | 3 | 4 | 12 | Leader |
| 9 | Scan health is opaque: auth-failure reasons and skip counts are not saved; http and https duplicates inflate counts | 3 | 4 | 12 | Leader, analyst |
| 10 | Broken or looping links (the GroupedFindings `/pages/:id` link; the protected "Report overview" loop) | 2 | 3 | 6 | Analyst |

## 6. Brief vs repo: premise checks

These points differ from the brief. None of them blocks a design, but each one changes what the design can honestly show.

| Brief says | Repo reality (read) | How the design handles it |
|---|---|---|
| Detection is Alfa plus AI checks | axe-core **and** Alfa, plus browser probes (keyboard, zoom/spacing, focus), a VLM visual check, a local-LLM semantic check, and OCR plus VLM for image text | The trust signal names 4 kinds of check: rule check, browser test, AI review, person |
| ITS severity: Blocker, Critical, Major, Minor, Best practice | No such scale in the code. It uses axe impact (critical to minor, NULL for Alfa), image severity, and conformance A/AA/AAA/BP | The mock shows the ITS scale using the proposed mapping in A1 |
| Statuses: New, Needs review, Confirmed, Ticketed, Fixed, Regressed, Dismissed | Stored: new, reviewing, in_progress, remediated, accepted_risk, false_positive. **No ticketed, no regressed, no carry-over across runs.** | The mock uses the brief's statuses plus **Accepted risk**, which exists in the data. Mapping in A2. |
| App scope (one app or all apps) | There is no app entity, only `seed_url` | "App" = the normalized seed URL (A3) |
| Scans run against authenticated apps | Local login scans store full evidence. Protected (companion) scans store only a redacted index. The local DB holds no authenticated scans. | The design covers sign-in failure; protected reports show page keys instead of URLs (A4) |
| Jira tickets in the ITS format | CSV, one row per finding; no Expected Behavior, no disclaimer | The mock drafts a ticket per root cause, to copy or download. Sending to Jira is a separate confirmed action (A5). |
| SAMPLE_SCAN is a JSON file | Real scan data lives in SQLite. The golden JSON files are synthetic fixtures ("Fixture rule 12"). | Scan 2 in `data/audit.db` is used, read only |
| A login screen exists (3.3.8) | Hosted mode shows a plain-text 401. Local use has no login. Login scans hand sign-in to a visible browser, and Axcess never sees the password. | The design adds an Access screen and keeps the sign-in handoff |

## 7. Sample data used in the mock

**Real (scan 2, read):**
- Site and run: https://museumcollab.anthro.lsa.umich.edu/ (Omeka S, "Anishinaabe Plants"), run on 2026-09-11 from 22:39 to 00:10 UTC (1 h 30 m).
- Pages: 403 URLs, of which 214 are HTML pages and 189 are image files. 5 pages were crawled over both http and https (152 duplicate rows). 2 `/admin/...` links redirected to `/login`.
- Checks: axe 214 pages / 681 violations; Alfa 214 pages / 367 failed + 17 cannot tell; semantic, keyboard, responsive and interaction on 214 pages. Keyboard and focus found 0 issues. The interaction sweep operated 21 controls and found 0 new states.
- Engine agreement: axe `link-name` and Alfa `sia-r11` agree on 143 of 143. On target size, both flagged 100 elements and Alfa alone flagged 120 more. On link purpose, the semantic check agrees with both engines on 27 links.
- Image of text: the site banner (essential text, alt matches, on 211 pages) and the "Fading Colors" poster (essential text, `alt=""`).
- Real selectors and snippets appear in the mock, for example:
  - `.item.resource:nth-child(1) > a[href="/s/Anishinaabe/item/29"]`
  - `div.description`
  - an `iframe` 560 px wide at a 320 px viewport
  - `input.page-input-top`, whose label is "too vague"

**Root causes shown in the mock.** Rows are merged across engines; this merge is the proposed design.

| # | Severity (A1) | Plain title | SC | Instances / pages | Checks | Status in mock |
|---|---|---|---|---|---|---|
| 1 | Critical | Poster text is only in an image | 1.1.1 A, 1.4.5 AA | 2 / 2 | AI review (OCR + image model) | Needs review |
| 2 | Critical | Image links have no name | 2.4.4 A, 4.1.2 A | 143 / 19 | 2 rule checks agree (+ AI review on 27) | Confirmed |
| 3 | Major | Item descriptions get cut off when text is bigger or spaced out | 1.4.4 AA, 1.4.12 AA | 42 / 9 | Browser test | New |
| 4 | Major | Embedded videos make the page scroll sideways on phones | 1.4.10 AA | 8 / 8 | Browser test | Came back (illustrative) |
| 5 | Major | Links are too small to tap easily | 2.5.8 AA | 220 / 58 | 2 rule checks agree on 100; 1 check on 120 | Ticketed (A11Y-214, illustrative key) |
| 6 | Major | Banner text is part of an image | 1.4.5 AA | 1 image / 211 | AI review | Needs review |
| 7 | Major | Headings do not describe their section | 2.4.6 AA | 677 / 155 | AI review | Needs review |
| 8 | Major | Link text does not say where it goes | 2.4.4 A | 238 / 158 | AI review; Alfa "cannot tell" on 17 | Needs review |
| 9 | Major | Search and page fields have vague labels | 3.3.2 A | 107 / 50 | AI review | Needs review |
| 10 | Major | Reading order on screen differs from the code | 1.3.2 A | 91 / 91 | AI review (image model) | Needs review |
| 11 | Minor | Footer credit text is too faint | 1.4.3 AA | 3 / 3 | 1 rule check | New |
| 12 | Minor | A heading is empty | 1.3.1 A | 1 / 1 | 2 rule checks agree | New |
| 13 | Best practice | Pages have no main heading | none | 211 / 211 | 1 rule check | New |
| 14 | Best practice | Heading levels skip | none | 170 / 170 | 1 rule check | New |
| 15 | Best practice | Navigation areas share the same name | none | 56 / 56 | 1 rule check | New |

Totals: Blocker 0, Critical 2, Major 8, Minor 2, Best practice 3 (15 root causes).
Later changes to labels used in this table (see ia.md §13 and gauntlet-log.md): the status "New" is shown as "Not decided", "AI lead" is shown as "AI only", and the Since column says "First seen in Run 4" for issues new in this run.
 The real data has no Blocker, so the mock shows 0 and demonstrates the Blocker treatment on the component sheet and the states page.

**Illustrative (not in the DB, labeled as such in Figma):**
- The mock calls scan 2 "Run 4, Sep 11" and compares it with an earlier "Run 3, Aug 28".
- The deltas copy the real scan 5→6 pattern on reganmaharjan.com.np: 4 new, 19 fixed, 276 still present, almost all color contrast. They are applied as: 19 instances fixed (17 target size, 2 image links), 1 issue came back (embedded video reflow), and 2 new issues (poster text, and footer contrast reached through the login redirect). Every other issue was already in Run 3.
- Resulting change since Run 3: Blocker same (0), Critical up 1 (poster), Major up 1 (the video issue came back), Minor up 1 (footer), Best practice same. Status counts: Needs review 6, New 6, Confirmed 1, Ticketed 1, Came back 1.
- Ticket key A11Y-214, person names and history entries are illustrative.

## 8. Assumptions (each needs an owner's sign-off before build)

- **A1 ITS severity mapping (proposed).** Map each root cause from its worst confirmed instance:

  | Level | Rule |
  |---|---|
  | Blocker | Stops a core task with no workaround, for example a keyboard trap or an unnamed only submit button. Set by a person, or proposed by a critical-impact deterministic failure. |
  | Critical | Serious impact on A/AA; essential image text with no alternative. |
  | Major | Moderate impact on A/AA, and any serious A/AA lead from the AI or browser tests. |
  | Minor | Minor impact, AAA, or a low-reach A/AA failure on non-content chrome. |
  | Best practice | No WCAG SC. |

  Alfa rows (NULL impact) inherit the level of the equivalent axe rule when both flag the element. Otherwise they default to Major for A/AA. An analyst can change the level; the change is recorded with a reason. ITS must confirm this mapping.
- **A2 Status mapping:**

  | Brief (UI label) | Stored as |
  |---|---|
  | Not decided (the brief's "New"; renamed in round 2, see ia.md §13) | `new` |
  | Needs review | `reviewing`, or `new` + expert_review lane (derived) |
  | Confirmed | `in_progress` |
  | Ticketed | new stored state, with a ticket key |
  | Fixed | `remediated`, confirmed by a person; "Gone in the latest run" is shown separately and is not Fixed |
  | Came back | derived: was Fixed or Dismissed in an earlier run and is detected again |
  | Accepted risk | `accepted_risk` |
  | Dismissed | `false_positive` + reason |

  This needs status carry-over across runs, keyed on (normalized URL, pipeline, rule, target hash).
- **A3 App.** An app is the normalized seed URL. "All apps" groups every seed the user has scanned. A true app entity that groups several seeds is out of scope.
- **A4 Protected reports.** The same page layout is used, but the Instances table shows opaque page keys and a "Locations withheld" note, as the protected design requires.
- **A5 Jira.** Axcess is local-first. "Create Jira ticket" builds a draft to copy or download (CSV in the ITS format). Sending directly to Jira happens only if an admin has connected Jira, and it asks for confirmation every time (AGENTS.md: contacting an external service is a separately confirmed action). "Mark as ticketed" records the key.
- **A6 Root-cause merge.** Rows from different engines merge into one root cause when they share the page, the element (resolved against the stored rendered HTML) and the SC. Where element matching fails, they fall back to rule equivalence (for example axe `link-name` ≡ Alfa R11). The per-engine `issue_key` stays available in the detail panel.
- **A7 Fix reach.** A shared selector pattern across pages (for example `.item.resource > a` on 19 pages) is shown as "likely one template". This is a heuristic and is labeled "likely".
- **A8 Trend.** It needs a per-run summary snapshot (counts by severity, status and trust), because computing a trend from raw rows for every run is too slow.
- **A9 Personas.** The repo personas (Sam, the lead analyst; the editor; the maintainer) are themselves assumptions. The brief's three users take priority. No user interviews were available.
- **A10 Fonts in Figma.** Atkinson Hyperlegible Next and Mono are used if Figma lists them; otherwise the closest available Atkinson family. The fallback is logged on page 02.

## 9. Five design principles

1. **Finish every job on one page.** Views change what is emphasized, never where you are.
2. **Say how sure we are.** Every finding shows which checks saw it and whether a person confirmed it. Leads never look like facts.
3. **Compare honestly.** Call something fixed or came back only when the runs are comparable; otherwise say what is unknown.
4. **Credit the work.** Fixed and decided work gets as much room as open work.
5. **One word, one place.** Each status, severity and count has one name and one home, the same in every view.

## 10. What the design needs from the data (build notes, not changes made)
1. A per-run summary snapshot for the trend and the status strip (A8).
2. Status carry-over and finding identity across runs, to support Fixed, Came back and Ticketed (A2).
3. A root-cause merge across engines, and the trust record (engines that agree, outcome, evidence status, human confirmation) (A6).
4. Persisted scan-health counts: pages skipped by scope, blocklist, robots and auth wall; duplicate schemes; login failure reason.
5. A ticket draft built from the existing XLSX root-cause builder, plus Expected Behavior (`acceptance`) and a disclaimer.
6. An Access screen for hosted mode (T18).
