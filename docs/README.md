# Axcess documentation

Axcess is a free accessibility scanner that runs on your computer. It scans a
website you are allowed to test, keeps the evidence on your machine, and helps
you decide what to fix first. Terms such as "barrier" and "occurrence" are
defined once, in the [glossary](./glossary.md).

## Using Axcess

Start with the public site:

- [Get started](https://lsa-mis.github.io/axcess/get-started/): install the
  desktop app or run from source, then run and read your first scan.
- [What Axcess checks](https://lsa-mis.github.io/axcess/coverage/): what each
  check covers, which report group its results land in, and what a person
  still needs to test for each WCAG 2.2 A and AA success criterion.
- [How it works](https://lsa-mis.github.io/axcess/how-it-works/): the steps
  from a web address to a verified fix.
- [Privacy and trust](https://lsa-mis.github.io/axcess/privacy/): what stays
  on your computer and what Axcess connects to.
- [FAQ](https://lsa-mis.github.io/axcess/faq/): answers to common questions.

Then use these guides:

- [Glossary](./glossary.md): plain-language definitions of report terms.
- [Reading your report](./reading-your-report.md): a walkthrough of a report
  and its exports.
- [Troubleshooting](./troubleshooting.md): fixes for scans that stop at one
  page, crawl too much or too little, or run slowly.
- [Hosting for a small team](./hosting.md): run Axcess on an always-on machine
  for your team, behind a shared token on a private network.
- [Coverage tracker](./coverage-tracker.md): WCAG coverage counts, detection
  layers, desktop build status, and what is planned next.
- [Single-page apps and search scans](./spa-search-scans.md): how Axcess
  clicks through menus, tabs and dialogs, and finds pages that only appear
  after a search.
- [Desktop app](./desktop-app.md): how the desktop app runs, where it keeps
  its data, what to do when it won't start, and how updates reach it.

## Building and maintaining Axcess

- [Contributing](../CONTRIBUTING.md): set up a development copy, run the
  quality gates, and follow the documentation rules.
- [Internal docs index](./internal/README.md): the map of maintainer docs.
- [Architecture](./internal/architecture.md): how a scan flows through the
  crawler, the checks, storage, and the review app.
- [Developer guide](./internal/developer-guide.md): where the code lives, the
  command-line tool, and recipes for common changes.
- [Detection pipelines](./internal/detection-pipelines.md): every check, the
  report group it feeds, and its false-positive safeguards.
- [Adding a check](./internal/adding-a-check.md): how to add or tune a check.
- [Releases](./internal/releases.md): desktop releases, auto-update, and
  publishing the site.
- [Protected scans](./internal/protected-scans.md): deploying the
  off-by-default protected companion for hosted scans of signed-in pages.
- [UI accessibility](./internal/ui-accessibility.md): the accessibility
  standard the review app holds itself to, and how it is tested.
- [Design principles](./internal/design-principles.md): Universal Design and
  usability principles applied to the review app.
- [Personas](./internal/personas.md): who the review app is designed for.
- [Alfa evidence review](./internal/alfa-evidence-review.md): an investigation
  into Siteimprove Alfa "cannot tell" results and how to verify them.
- [System design and coverage gap](./internal/system-design-and-coverage-gap.md):
  an earlier design document, kept for history.
- [Detection efficacy](../DETECTION_EFFICACY.md): the accuracy, speed, and
  scale gates for detectors, and how to run them.
- [Agent guide](../AGENTS.md): the contract for coding agents working in this
  repository.
- [Original plan](../PLAN.md): the first build plan, kept for history.
