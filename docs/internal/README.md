# Internal documentation

These guides are for people who build and maintain Axcess. If you use Axcess
to scan websites, the [docs hub](../README.md) is a better place to start.
Every term is defined once, in the [glossary](../glossary.md).

## Guides

| Guide | What it covers |
| --- | --- |
| [Contributing guide](../../CONTRIBUTING.md) | Setting up from source, the quality gates and what CI runs, and the rules for code, docs, and the public site. |
| [Architecture](architecture.md) | How a scan flows from crawl to report, where evidence is stored, and what connects beyond your computer. |
| [Developer guide](developer-guide.md) | The code layout, conventions, command-line scans, extension recipes, testing, and debugging. |
| [Detection pipelines](detection-pipelines.md) | Every check, the report group it lands in, and the safeguards against false positives. |
| [Adding a check](adding-a-check.md) | How to add a new check or tune an existing one. |
| [Releases](releases.md) | Desktop releases, the in-app update check, and publishing the public site. |
| [Protected scans](protected-scans.md) | Deploying the off-by-default protected companion for hosted scans of signed-in pages. |
| [UI accessibility](ui-accessibility.md) | The accessibility contract for the Axcess review app itself. |
| [Design principles](design-principles.md) | Universal Design and usability principles applied to the review app. |
| [Personas](personas.md) | The people the product is designed for, and who it is not for. |
| [Alfa evidence review](alfa-evidence-review.md) | An investigation into Siteimprove Alfa "cannot tell" results and how to verify them. |
| [Detection efficacy gates](../../DETECTION_EFFICACY.md) | The efficacy, efficiency, and scale gates, and how to run `make detection-evals`. |
| [Precision corpus rules](../../tests/quality/README.md) | The labeled detection corpus behind `make quality-gate`: how to add samples and when to bump `corpus_version`. |
| [Diagram sources](../images/diagrams/source/README.md) | Where the diagram sources live, and how to edit and render a diagram again. |
| [System design and coverage gap](system-design-and-coverage-gap.md) | A historical single-page design, kept for context. The architecture guide replaces it. |

## History and planning

These files stay where they are. Some describe the product as it was planned,
not as it is now.

- [PLAN.md](../../PLAN.md): the original plan for the image-of-text auditor
  that grew into Axcess.
- [image-text-audit-prompt.md](../../image-text-audit-prompt.md): the original
  build prompt for that first tool.
- [audits/](../../audits/): the April 2026 discovery audit of the review app
  and its axe-core baseline runs, from before the current React-only UI.
- [AGENTS.md](../../AGENTS.md): the contract for coding agents working in this
  repository. Its design for a conversation attached to one report is a plan,
  not a shipped feature.
