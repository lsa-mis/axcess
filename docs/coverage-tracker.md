# Axcess coverage and feature tracker

> Last reconciled: **2026-08-12** against the shipped code, WCAG matrix,
> semantic registry, migrations, desktop package, and release workflow.

Axcess targets **WCAG 2.2 Level A and AA** for report coverage. It is an
evidence workbench for expert review, not a conformance-certification engine.
A criterion being listed as automated, partially automated, or AI-assisted
does not mean a scan proves that the page or site conforms.

## Sources of truth

Coverage information has three deliberately separate sources:

| Source | What it controls |
|---|---|
| [`wcag_coverage.yaml`](../src/audit/rules/wcag_coverage.yaml) | The authoritative classification and manual-test guidance for all 55 WCAG 2.2 A/AA success criteria. |
| [`coverage_matrix.py`](../src/audit/coverage_matrix.py) | Validates the YAML and calculates the totals used by reports and API/UI summaries. |
| [`coverage_status.py`](../src/audit/web/coverage_status.py) | The shipped-pipeline and roadmap inventory shown on `/app/tracking`. |

This document is the human-readable reconciliation of those sources. Update
the YAML or structured tracker first when implementation changes, then update
this document. Scan-specific method coverage remains authoritative in the
scan's stored configuration and counters: selected, completed, skipped, and
unavailable are different states.

## Current WCAG 2.2 A/AA coverage

| Scope | Total | Automated | Partly automated | AI-assisted | Manual only | Any Axcess contribution |
|---|---:|---:|---:|---:|---:|---:|
| Level A | 31 | 2 | 11 | 4 | 14 | 17 |
| Level AA | 24 | 3 | 7 | 2 | 12 | 12 |
| **A + AA** | **55** | **5** | **18** | **6** | **26** | **29** |

The 29-criterion figure means that at least one Axcess layer contributes
evidence. It does **not** mean 29 criteria can be fully decided without an
expert. Every matrix row includes a residual manual check.

### Classification rules

- **Automated:** deterministic checks cover defined machine-testable
  conditions with high confidence; applicability and remaining states still
  receive expert review.
- **Partly automated:** a deterministic layer catches mechanical failures,
  but substantial states, exceptions, or meaning require manual testing.
- **AI-assisted:** a local model creates a review lead. It is never treated as
  a conformance verdict.
- **Manual only:** Axcess currently has no detector for the criterion; the
  report gives the auditor a manual procedure instead.

### Automated criteria (5)

- 1.4.4 Resize Text
- 1.4.10 Reflow
- 1.4.12 Text Spacing
- 2.4.2 Page Titled
- 3.1.1 Language of Page

### AI-assisted criteria (6)

| Criterion | Contribution | Required expert check |
|---|---|---|
| 1.2.1 Audio-only and Video-only (Prerecorded) | Semantic review looks for a reachable transcript near an `<audio>` element. | Confirm transcript accuracy/equivalence and test video-only content manually. |
| 1.3.2 Meaningful Sequence | Visual review compares a screenshot with DOM/source order. | Confirm reading and interaction order; below-fold and subtle layouts remain manual. |
| 1.4.5 Images of Text | OCR plus a local vision model identifies likely images of text. | Confirm the classification and permitted exceptions. |
| 2.4.4 Link Purpose (In Context) | axe checks names; semantic review judges link text with surrounding context. | Confirm ambiguous/context-dependent calls. |
| 2.4.6 Headings and Labels | axe checks structural/name failures; semantic review judges heading descriptiveness. | Confirm heading calls and review label descriptiveness manually. |
| 3.3.2 Labels or Instructions | axe checks programmatic labels; semantic review judges instruction sufficiency. | Confirm sufficiency and test real form states/submissions. |

### Partly automated criteria (18)

1.1.1, 1.3.1, 1.3.5, 1.4.1, 1.4.2, 1.4.3, 2.1.1, 2.1.2,
2.2.2, 2.4.1, 2.4.3, 2.4.7, 2.4.11, 2.5.3, 2.5.8, 3.1.2,
4.1.2, and 4.1.3.

See the matrix for the exact automated condition and residual manual test for
each criterion. In particular, a keyboard-trap lead is intentionally
conservative: Axcess requires repeated bidirectional exit failure on the same
observable element and suppresses ordinary focus wrapping, small cycles,
modal containment, and opaque iframe/closed-shadow focus. Every lead still
requires manual reproduction.

### Manual-only criteria (26)

1.2.2, 1.2.3, 1.2.4, 1.2.5, 1.3.3, 1.3.4, 1.4.11, 1.4.13, 2.1.4,
2.2.1, 2.3.1, 2.4.5, 2.5.1, 2.5.2, 2.5.4, 2.5.7, 3.2.1, 3.2.2,
3.2.3, 3.2.4, 3.2.6, 3.3.1, 3.3.3, 3.3.4, 3.3.7, and 3.3.8.

## Detection and evidence layers

| Layer | Stored source/pipeline | What it checks | Availability and limitation |
|---|---|---|---|
| Browser rendering | scan coverage counters | Executes JavaScript and exposes the live DOM for interaction checks. | A rendered page is not itself an accessibility pass. |
| axe-core 4.10.2 | `axe` | Deterministic rendered-DOM rules at the selected WCAG level. | High-confidence rule evidence, but it covers only machine-testable conditions. |
| Siteimprove Alfa | `alfa` | An independent ACT-rule evaluation with failed and cannot-tell outcomes. | Select axe, Alfa, or both. Alfa evidence is stored separately and does not inflate matrix counts simply because two engines overlap. |
| Keyboard probe | `keyboard` | Tab/Shift+Tab exit evidence and Escape behavior for likely traps. | Conservative review leads; full keyboard operability is manual. |
| Responsive and zoom probe | `responsive` | 320 CSS-pixel reflow, approximately 200% text zoom, and text-spacing overrides. | Geometry identifies likely clipping/loss; an expert determines user impact. |
| Focus probe | `focus` | Positive `tabindex` and focus obscured by fixed/sticky overlays. | Full focus order and interaction-created overlays remain manual. |
| Visual probe | `visual` | Meaningful sequence through local vision analysis; measured autoplay/moving-content leads. | Model-dependent 1.3.2 results require confirmation; media coverage remains partial. |
| Image analysis | `image` | Image discovery, Tesseract OCR, and local VLM classification. | OCR/VLM results are evidence, not a legal conclusion. |
| Semantic review | `semantic` | Registered analyzers for 1.2.1, 2.4.4, 2.4.6, and 3.3.2. | Requires an explicitly configured local Ollama service; unsupported configured criteria are skipped and logged. |

The standard public-scan profile renders pages and selects both DOM engines
when Alfa is available. Advanced settings can choose axe-only, Alfa-only,
both, static-only crawling, visible browser navigation, and whether to run
image or interaction layers. Every report shows the number of pages or images
actually checked—not merely that a feature was selected.

## Authenticated-site coverage

Axcess supports two manual sign-in models without collecting credentials:

- **Local login/2FA scan:** a visible Playwright browser opens on the Axcess
  computer, the auditor signs in directly, and the crawl reuses that live,
  memory-only browser context after the auditor confirms the target page.
- **Managed protected scan:** an identity-gated, scan-bound companion model
  with stricter scope, retention, encryption, and permission controls.

Authentication secrets, OTPs, passkeys, cookies, and reusable browser state
must not enter reports or ordinary application storage. Successfully crawling
after sign-in does not test or pass WCAG 3.3.8 Accessible Authentication; the
login and MFA experience remains a manual-only criterion.

## Reporting and review status

Shipped reporting behavior includes:

- issue groups and detected occurrences labeled separately;
- source layer, confidence, WCAG criterion, affected users, exact location,
  evidence, remediation, and verification guidance;
- scan-scoped page-evidence links with scan/page relationship validation;
- manual evaluation records and evidence that persist separately from
  immutable scan evidence;
- Markdown, JSON/CSV, Jira-oriented, and structured XLSX outputs;
- clickable workbook links and source-layer columns;
- final-export readiness that requires expert disposition, with an explicit
  acknowledged draft path;
- status-filtered report projections so false positives and other terminal
  occurrences do not inflate open issue counts or locations.

The versioned detector-quality corpus enforces a false-discovery-rate gate,
but that measured corpus result is not a universal real-world false-positive
guarantee. The product must continue to present automated and model-assisted
outputs as evidence requiring proportionate expert review.

## Desktop distribution status

The Electron work is published from `feature/electron-desktop` as an Apple
Silicon macOS artifact. The package includes the React frontend, frozen
FastAPI/Python backend, Playwright Chromium, axe-core, Siteimprove Alfa and its
Node dependencies, Tesseract plus English OCR data, migrations, rule files,
and the Excel report engine.

The packaging gate executes these components from inside the finished app:

- Python backend and database migrations;
- React assets;
- Chromium rendering;
- axe-core injection;
- Alfa browser evaluation through Electron's embedded Node runtime;
- Tesseract OCR with English data;
- Excel workbook generation.

The current DMG is ad-hoc signed and is **not Apple-notarized**. Gatekeeper can
therefore show “Apple could not verify Axcess is free of malware.” Production
distribution still requires a Developer ID Application certificate, hardened
runtime, Apple notarization, and a stapled ticket. Intel macOS, Windows, and
Linux artifacts are not currently published.

Optional Ollama models are not bundled or downloaded silently. They remain a
separately configured loopback-only dependency for AI-assisted checks.

## Next coverage priorities

| Priority | Gap | Intended approach | Status |
|---|---|---|---|
| 1 | 3.2.3 Consistent Navigation | Post-crawl cross-page structure/embedding comparison. | Planned |
| 1 | 3.2.4 Consistent Identification | Cross-page component identity and accessible-name comparison. | Planned |
| 1 | 3.2.6 Consistent Help | Cross-page help-location/order comparison. | Planned |
| 2 | 1.2.2 prerecorded captions | Media extraction plus ASR/caption comparison with strict privacy controls. | Planned |
| 2 | 1.4.11 Non-text Contrast | Component/focus-indicator contrast measurement with exception handling. | Planned |
| 2 | 1.4.13 Content on Hover or Focus | Trigger/dismiss/hover/persistence browser probe. | Planned |
| 2 | 2.3.1 Three Flashes | Time-based video/screenshot luminance analysis. | Planned |
| 3 | Form errors and stateful criteria | Safe, explicitly authorized interaction fixtures and manual evidence workflow. | Planned |
| Release | Warning-free macOS distribution | Developer ID signing, hardened runtime, notarization, and stapling. | Blocked on Apple credentials |
| Release | Additional desktop platforms | Bundle and verify equivalent OCR/browser runtimes on each OS. | Planned |

## How to verify this tracker

```bash
# Validate the 55-row matrix and print live totals.
uv run python -c 'from audit.coverage_matrix import summary; print(summary())'

# Verify registered semantic criteria.
uv run python -c 'from audit.analyzer.semantic.registry import supported_criteria; print(supported_criteria())'

# Enforce the labeled detector-quality corpus.
make quality-gate

# Run project and desktop checks.
make lint
make typecheck
uv run pytest tests/unit
make desktop-test
```

Implementation map:

| Claim | Where to confirm |
|---|---|
| Criterion classifications and manual procedures | `src/audit/rules/wcag_coverage.yaml` |
| Matrix validation and totals | `src/audit/coverage_matrix.py` |
| Shipped feature and roadmap inventory | `src/audit/web/coverage_status.py` |
| Semantic analyzers | `src/audit/analyzer/semantic/registry.py` and `analyzers/` |
| axe and Alfa integration | `src/audit/analyzer/axe.py`, `src/audit/analyzer/alfa.py`, `src/audit/alfa_runner/` |
| Interaction probes | `src/audit/analyzer/keyboard/`, `responsive/`, `focus/`, and `visual/` |
| Durable method counters | migration `0020_method_coverage.sql` and `audit.web.server._methods_used` |
| Desktop dependency gate | `src/audit/desktop_server.py` and `desktop/scripts/verify-packaged.cjs` |
| False-discovery-rate corpus | `tests/quality/corpora/detection_precision_v1.json` |
