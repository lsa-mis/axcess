<div align="center">

# Axcess

**A free accessibility scanner that runs on your computer, including on pages
behind a sign-in.**

[Website](https://lsa-mis.github.io/axcess/) ·
[Get started](https://lsa-mis.github.io/axcess/get-started/) ·
[What Axcess checks](https://lsa-mis.github.io/axcess/coverage/) ·
[Glossary](./docs/glossary.md) ·
[Documentation](./docs/README.md)

</div>

Axcess scans a website you are authorized to test, keeps the evidence on your
computer, and helps you decide what to fix first. It is built by LSA
Technology Services at the University of Michigan for accessibility analysts
and testers, web editors and app owners, and the developers who fix what it
finds.

> [!IMPORTANT]
> Axcess finds evidence for a person to review. It does not prove
> [WCAG](./docs/glossary.md#wcag) conformance or legal compliance, and it does
> not replace [manual testing](./docs/glossary.md#manual-testing).

## What makes it different

- **Scans behind a sign-in.** You sign in yourself in a normal browser window,
  including single sign-on and two-factor steps. Axcess never sees your
  password and saves no reusable login.
- **Opens what visitors open.** It clicks through menus, tabs, and dialogs,
  tests what appears, and tells you which button revealed each problem.
- **Checks rule-based tools rarely automate.** Reflow at phone width, text cut
  off at 200% zoom or with wider text spacing, keyboard traps, and text inside
  images.
- **Honest about certainty.** Every result is a
  [Barrier](./docs/glossary.md#barrier),
  [Needs review](./docs/glossary.md#needs-review), or
  [Informational](./docs/glossary.md#informational), so you know what to fix
  now and what a person should confirm first.
- **Local-first.** Reports, screenshots, and decisions stay on your computer.
  There is no account, no telemetry, and no upload.

We use and like Siteimprove and axe DevTools, and Axcess is meant to fill gaps
rather than replace them. See
[how Axcess compares with Siteimprove and axe DevTools](https://lsa-mis.github.io/axcess/coverage/#compare).

## Get started

Download the desktop preview:

- [Axcess for macOS (Apple Silicon)](https://github.com/lsa-mis/axcess/releases/latest/download/Axcess-macOS-AppleSilicon.dmg)
- [Axcess for Windows 10 or 11 (64-bit)](https://github.com/lsa-mis/axcess/releases/latest/download/Axcess-Windows-x64-Setup.exe)

The preview is not yet notarized or code-signed, so macOS and Windows warn you
the first time. Follow the
[first-launch steps on the Get started page](https://lsa-mis.github.io/axcess/get-started/#first-launch),
then run a small scan. Optional AI checks need a separately installed local
service called Ollama; everything else works without it. Release notes and
earlier builds are on the [releases page](https://github.com/lsa-mis/axcess/releases).

## Read your report

![Diagram of the three report groups. Barrier holds rule-engine failures from axe-core and Siteimprove Alfa, including problems found after clicking or after a configured search; confirm them on the page, fix, and rescan. Needs review holds browser checks, the keyboard trap check, motion checks, text in images whose alt text is missing or does not match, AI checks, and Alfa "cannot tell" results; a person tests and records a decision. Informational holds images whose alt text already matches and older records kept for history; no action is needed.](./docs/images/diagrams/report-groups.png)

Every result lands in one of three groups. Start with Barriers, test and decide
on Needs review items, and leave Informational records alone.
[Reading your Axcess report](./docs/reading-your-report.md) walks through every
screen, column, and export, including how to find a problem in your code and
fix it.

## Documentation

| I want to... | Read |
| --- | --- |
| Look up a term | [Glossary](./docs/glossary.md) |
| Know what Axcess checks and what I still test by hand | [What Axcess checks](https://lsa-mis.github.io/axcess/coverage/) |
| Find a problem and fix it | [Reading your Axcess report](./docs/reading-your-report.md) |
| Install and run a first scan | [Get started](https://lsa-mis.github.io/axcess/get-started/) |
| Understand what stays on my computer | [Privacy and trust](https://lsa-mis.github.io/axcess/privacy/) |
| Fix a scan that went wrong | [Troubleshooting](./docs/troubleshooting.md) |
| Share Axcess with a small team | [Hosting](./docs/hosting.md) |
| Contribute or maintain Axcess | [Contributing guide](./CONTRIBUTING.md) and [internal docs](./docs/internal/README.md) |

The [documentation hub](./docs/README.md) lists everything.

## Run from source

For developers and IT staff on macOS, Linux, or Windows with WSL. You need
Python 3.11 or newer, [uv](https://docs.astral.sh/uv/), Node.js 22.22 or
newer, and Tesseract.

```bash
git clone https://github.com/lsa-mis/axcess.git
cd axcess
make setup            # Python dependencies and Chromium
make migrate          # local database
make alfa-install     # optional second rule engine
make frontend-build   # build the review app
make run              # open http://127.0.0.1:8765/app/
```

To scan from the command line, run `uv run audit crawl https://www.example.edu/ --max-pages 25`,
then `uv run audit --help` for every option. The
[contributing guide](./CONTRIBUTING.md) covers quality checks and how to
propose changes.

## License

[MIT](./LICENSE). Built for evidence-led accessibility work at the University
of Michigan. Axcess is not an official U-M conformance certification service.
