/**
 * Common questions, kept in one place so the home page and the Questions page
 * give the same answer in the same words (COGA: the same word for the same
 * thing). Each answer was checked against the code; the comment above an
 * entry names where.
 *
 * Shape:
 * - `a` is the whole answer in plain text. The home page shows only `a`
 *   (it reads `q.q` and `q.a`), so `a` must stand on its own and must never
 *   drop a limit or safety fact that the extra fields add.
 * - `list` and `after` are optional extra detail that only the Questions
 *   page shows, for an answer that is clearer as steps or a list (COGA: a
 *   list for three or more items).
 * - `links` are optional "read more" links, shown only on the Questions page.
 *   A site path starts with "/" and the page adds the base path (url() in
 *   lib/site.ts); any other value is a full address.
 *
 * Kept as structured plain text rather than an HTML string, so no answer can
 * carry markup that skips the page's own link and list styles.
 */
import coverage from "./coverage.json";
import { REPO } from "../lib/site";

export interface QuestionLink {
  href: string;
  text: string;
}

export interface Question {
  /** Stable anchor on /faq/ (for example /faq/#sign-in). Do not rename. */
  id: string;
  q: string;
  /** The full answer, plain text. */
  a: string;
  /** Optional bullet points, shown after `a` on the Questions page only. */
  list?: string[];
  /** Optional plain text after the list, on the Questions page only. */
  after?: string;
  /** Optional links, on the Questions page only. */
  links?: QuestionLink[];
}

const { covered, total, manualOnly } = coverage.summary;

export const QUESTIONS: Question[] = [
  // Honesty rule (AGENTS.md, docs/plain-language.md rule 12). Numbers come
  // from coverage.json, exported from src/audit/rules/wcag_coverage.yaml.
  {
    id: "prove",
    q: "Will a scan prove we meet WCAG or the law?",
    a: `No. No tool can. Axcess gives you specific evidence, and a person reviews it to decide what meets the Web Content Accessibility Guidelines (WCAG). Its checks help with ${covered} of the ${total} WCAG 2.2 Level A and AA criteria. The other ${manualOnly} need a person to test them. A scan also doesn't replace testing with people who use assistive technology, such as screen readers.`,
    links: [{ href: "/coverage/", text: "See what Axcess checks for each WCAG criterion" }],
  },
  {
    id: "experts",
    q: "Does this replace our accessibility experts?",
    a: "No. Axcess does the slow work of finding and recording problems, so your experts can spend their time reviewing results and planning fixes.",
  },
  // Issue types: docs/glossary.md "Report groups"; only rule checks make a
  // Mostly sure (glossary "Zero false positive goal"; Alfa "cannot tell" is
  // Not sure, docs/plain-language.md terms table).
  {
    id: "issue-types",
    q: "What do Mostly sure, Not sure and For information mean?",
    a: "They say how sure Axcess is that an issue is a real problem, in the How sure column of the Issues table. Mostly sure means a rule check (axe or Alfa) found a fixed rule broken. Check it on the page, then fix it. Not sure comes from a check that cannot be certain, and a person must decide whether it is a real problem before it counts. For information is a record of what was checked, with nothing to fix.",
    links: [
      { href: "/docs/glossary/#mostly-sure", text: "Mostly sure, in the glossary" },
      { href: "/docs/glossary/#not-sure", text: "Not sure, in the glossary" },
      { href: "/docs/glossary/#for-information", text: "For information, in the glossary" },
    ],
  },
  // Default standard: src/audit/wcag_version.py:3-4. Manual list with steps:
  // the written report's "Needs manual testing" table
  // (src/audit/exports/audit_report.py, _wcag_coverage_matrix).
  {
    id: "how-much",
    q: "How much does it check?",
    a: `Axcess has at least one check that helps with ${covered} of the ${total} WCAG 2.2 Level A and AA criteria. That doesn't mean a scan decides those ${covered} on its own, or that a site that passes them meets WCAG. The other ${manualOnly} have no check yet. The written report lists them, with what a person needs to test for each. New scans check against WCAG 2.1 Level AA by default, the current U-M standard, and you can choose 2.2 instead.`,
    links: [{ href: "/coverage/", text: "See every criterion on What Axcess checks" }],
  },
  {
    id: "compare",
    q: "How is Axcess different from Siteimprove or axe DevTools?",
    a: "We use and like both. Siteimprove checks whole sites from its cloud service. The axe DevTools browser extension checks the page in front of you. Axcess runs on your computer, can check the pages behind your sign-in, and opens menus and dialogs on its own. It also adds browser checks, such as how a page looks when zoomed in or with wider text spacing.",
    links: [{ href: "/coverage/", text: "Compare them on What Axcess checks" }],
  },
  // AI is optional: semantic_enabled and vlm_enabled default to false
  // (src/audit/web/scan_settings.py). The desktop app bundles Chromium and
  // Tesseract (docs/desktop-app.md). AI results are never Mostly sure
  // (docs/glossary.md "Local AI model").
  {
    id: "ai",
    q: "Do I need AI to use it?",
    a: "No. Most checks need only a browser and software that reads text in images (OCR), and the desktop app includes both. AI review is optional, and so is the AI step of the Image text check. They use a local AI model that you install yourself, through a free program called Ollama. Their results are never marked Mostly sure.",
    links: [{ href: "/docs/glossary/#local-ai-model", text: "Local AI model, in the glossary" }],
  },
  // Update check: desktop/src/updates.cjs, desktop/src/main.cjs:508
  // (AXCESS_DISABLE_UPDATE_CHECK=1). No telemetry: docs/glossary.md
  // "Local-first".
  {
    id: "cloud",
    q: "Does IT need to approve a cloud service?",
    a: "No. Axcess runs on the computer of the person scanning, and scan data stays there unless your team shares a report. There is no account and no usage tracking (telemetry). The desktop app does ask GitHub once each time it opens whether a newer version exists. That request carries no scan data, and you can turn it off.",
    links: [{ href: "/privacy/", text: "Read what Axcess connects to, and how to turn off the update check" }],
  },
  // Sign-in scans: LocalLoginScanRequest in src/audit/web/server.py (public
  // HTTPS address, authorization_acknowledged required, loopback only), and
  // the memory-only session that is never resumed (server.py, resumable=False).
  {
    id: "sign-in",
    q: "Can it check pages behind a sign-in?",
    a: "Yes, when Axcess runs on your own computer. It opens a browser window and you sign in yourself, including U-M sign-in and Duo two-step sign-in. Axcess never sees your password or code. It checks the pages behind the sign-in and deletes the sign-in when the scan ends. The site must have a secure public address (HTTPS), and you must confirm you have permission to test it. Sign-in scans are not available when Axcess runs on a shared server.",
    links: [{ href: "/docs/glossary/#sign-in-scan", text: "Sign-in scan, in the glossary" }],
  },
  // src/audit/web/export_readiness.py (draft title and file name);
  // docs/glossary.md "Draft export" (command-line exports are not marked).
  {
    id: "draft",
    q: "Why are some exports marked draft?",
    a: "Until expert review of a report is finished, every export you download from the app is a draft. Axcess marks it DRAFT in the file name and inside the file. That stops raw scan results from being passed around as a finished review. Exports made from the command line are not marked.",
    links: [{ href: "/docs/glossary/#draft-export", text: "Draft export, in the glossary" }],
  },
  // Reasons required: RATIONALE_REQUIRED_STATUSES in
  // src/audit/web/frontend/src/statusDecision.ts and src/audit/db/repo.py.
  // Test examples are synthetic: tests/quality/corpora/
  // detection_precision_v1.json, label_method "synthetic_by_construction".
  {
    id: "accuracy",
    q: "How accurate is it?",
    a: "Every occurrence records which check found it, and every issue shows how sure Axcess is. Only rule check failures are marked Mostly sure. Everything else waits for a person to confirm it. You can mark any occurrence Not a problem (a false positive), with a short reason. The project also tests its checks against a fixed set of made-up examples. That is a safety rail, not a measure of accuracy on real sites.",
    links: [
      { href: "/docs/glossary/#zero-false-positive-goal", text: "Zero false positive goal, in the glossary" },
      { href: "/docs/glossary/#false-positive", text: "False positive, in the glossary" },
    ],
  },
  // "Checks" is the New scan form's group (components/newScan/copy.ts).
  {
    id: "scan-time",
    q: "How long does a scan take?",
    a: "It depends on how many pages you scan and which checks you turn on. Axcess opens each page in a real browser and checks it several ways, so large scans take a while. Start with about 25 pages and grow from there. To go faster, turn off checks you don't need in the Checks group of the New scan form.",
  },
  // Click-through safety: DEFAULT_BLOCKED_LABELS and the limits in
  // src/audit/analyzer/interaction/probe.py; exploration_guard in
  // analyzer/interaction/safety.py blocks writes, new windows and page
  // changes. Robots: ignore_robots defaults to false for public scans
  // (src/audit/web/scan_settings.py); sign-in scans set it true.
  {
    id: "will-it-break-anything",
    q: "Will it break anything on the site?",
    a: "Axcess reads pages. Unless you turn it off, it also clicks visible controls such as menus and tabs, to check what they open. It takes care while it clicks, but that care is a safety net, not a guarantee. Use a test copy of the site when you can.",
    list: [
      "It skips controls named like Sign out, Delete, Buy, Submit, Save and similar words.",
      "It blocks form submissions and other requests that could change data on the site.",
      "It does not leave the page or open new windows while it clicks.",
      "It stops after 100 clicks, 5 levels of menus, or 2 minutes on each page.",
    ],
    after: "Scans of public sites follow the site's instructions for automated visitors (robots.txt) by default.",
    links: [{ href: "/docs/glossary/#click-through", text: "Click-Through, in the glossary" }],
  },
  // js_eager defaults to true (scan_settings.py); docs/spa-search-scans.md.
  {
    id: "single-page-apps",
    q: "Does it work on single-page apps built with React, Vue or Angular?",
    a: "Yes. By default, Axcess opens each page in a real browser and lets its scripts run before checking it. It follows links to the app's pages within your scan's limits. It also opens menus and dialogs, and adds the pages they lead to. Axcess does not read the app's code to guess hidden addresses, so a page needs a real link to be found.",
    links: [{ href: "/docs/spa-search-scans/", text: "Scanning search-driven sites" }],
  },
  // docs/hosting.md: one crawl at a time, shared token, no per-user
  // accounts, private network only, local sign-in scans not available to
  // team members, protected deployments described separately.
  {
    id: "team",
    q: "Can several people use one Axcess?",
    a: "Yes, a small trusted team can share one Axcess on an always-on computer on a private network. Everyone uses one shared access code, and there are no separate accounts. It runs one scan at a time. Never make it reachable from the public internet. Sign-in scans work only on that computer itself, not for the rest of the team.",
    links: [{ href: "/docs/hosting/", text: "Hosting Axcess, including stricter setups for an organization" }],
  },
  // LICENSE (MIT).
  {
    id: "cost",
    q: "What does it cost?",
    a: "Nothing. Axcess is free and open source under the MIT license. There are no seats and no subscriptions.",
  },
  // The production site's footer wording (the developer's direction).
  {
    id: "who-builds",
    q: "Who builds and looks after Axcess?",
    a: "Axcess is led by the College of Literature, Science, and the Arts Technology Services (LSA-TS) and Information and Technology Services (ITS) groups at the University of Michigan. The source code, documentation and white paper are public on GitHub.",
    links: [
      { href: REPO, text: "Axcess on GitHub" },
      { href: "/about/", text: "About Axcess" },
    ],
  },
  // .github/workflows/desktop-build.yml release files; README.md
  // "Get started" and "Run from source".
  {
    id: "platforms",
    q: "Which computers does it run on?",
    a: "The desktop app runs on a Mac with Apple silicon, on Windows 10 and 11 (64-bit), and on 64-bit Linux. There is no version for Mac computers with Intel processors. The app doesn't yet carry the signatures Mac and Windows look for, so they warn you the first time you open it. To run Axcess from its source code, use macOS, Linux, or Windows with WSL (Windows Subsystem for Linux).",
    links: [{ href: "/get-started/#first-launch", text: "Get started: install and open it" }],
  },
];
