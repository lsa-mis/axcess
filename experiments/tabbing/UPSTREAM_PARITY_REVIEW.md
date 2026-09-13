# Upstream parity review

The Axcess experiment now contains all twelve upstream detector families,
including both D10 variants and the coverage-based Stage 4 filter. **The whole
experiment is not an exact replication.** The source rules, browser harness,
engine versions, and reliability changes must be distinguished.

Reference: [`harryg02/a11y-crawler`, commit
`6c40f7c714ab053e40a8e0d80d33f27812403f1b`](https://github.com/harryg02/a11y-crawler/tree/6c40f7c714ab053e40a8e0d80d33f27812403f1b).
The important files are `experiments/tabbing/candidates.ts`, `instrument.ts`,
`differential.ts`, `taborder.ts`, and `tests/tabbing-experiment.spec.ts`.

## Which implementation is being measured?

The older D0–D8 rows use Axcess adaptations. Their matching logic differs from
upstream and those rows must not be presented as one-to-one ports. The new
`U-D*` rows use [upstream_candidates.py](runner/upstream_candidates.py).
The `C*` rows are explicitly new experimental combinations and rules.

| Family | Upstream rule reproduced in the new arm | Difference or limit to retain in the report |
|---|---|---|
| D0 | Original crawler selector list; reject elements inside anchors, `offsetParent === null`, and table cells/rows; attribute to the nearest annotated ancestor; visit each frame. | This rule uses its own layout test, not the survey visibility test. Axcess's older collector row differs. |
| D1 | Run tags `wcag2a`, `wcag2aa`, `wcag21aa`; attribute **any** matching axe violation through the main document selector and nearest annotated ancestor. No Tab subtraction. | Local axe is **4.10.2**, upstream's lockfile uses **4.11.1**. Direct frame injection replaces Node AxeBuilder. The rules and attribution are matched, not the engine or package integration. This is a broad baseline, not a keyboard-specific rule. |
| D2 | Seven inline attributes: click, keyup, keydown, keypress, mousedown, mouseup, mouseover; exclude native focusable elements and any `tabindex`. | The older Axcess row checks `onclick` alone. |
| D2b | Five assigned mouse handler properties: click, mousedown, mouseup, mouseover, double-click. | Assigned properties and markup attributes are different observations. |
| D3 | Interactive role, inline handler, `aria-expanded`, or `aria-haspopup`, with native focusable elements and **any** `tabindex` excluded. | The older Axcess version proposed elements carrying `tabindex`; that was a material logic difference. |
| D4 | `cursor:pointer`, the original class lexicon with token boundaries, or an interactive role. | Styling does not prove the element does anything. |
| D5 | Pierced CDP DOM resolution; eight mouse event types; `getEventListeners` depth **0**; visibility gate. | Direct listeners are not arbitrary delegated-listener attribution. A shim-only node supplies geometry but no CDP object, matching upstream's unsuccessful `nodeId=-1` resolution. |
| D6 | Document-start registration registry; seven mouse types; inspect the target element at read time; retain stack provenance. | Document/window delegation is excluded. Registry observations can include registrations whose listeners were later removed. |
| D7 | Inspect `__reactProps$` keys and truthiness of `onClick`, `onMouseDown`, or `onMouseOver`. | Framework-specific; does not infer what the function does. |
| D8 | Compare two clipped PNGs; original clip margins, viewport test, pointer parking, and 60/120 ms waits. | The older Axcess row compares document appearance/geometry instead. Animations and unrelated changes inside the clip can cause false alarms. |
| D9 | Exact upstream init-script text; upstream snapshot/delta channels; mouse hover then click; reload the same page/context between modalities; Enter, Space, ArrowDown in sequence; keyboard baseline before Tab replay. | The runner creates a fresh context per target, whereas upstream reuses its page more broadly. Axcess's main D9 instead compares effect payloads and isolates trials. Neither should be described as the other. |
| D10 | From the upstream-instrumented pass, subtract the handler-free page baseline. D10a asks whether mouse coverage is nonempty and keyboard coverage empty; D10b asks whether mouse coverage contains functions absent from keyboard coverage. | Coverage records executed function identities, not action meaning. A different keyboard function can perform the same action. |
| Stage 4 | On upstream D9 findings, search the whole measured corpus for a Tab-reachable keyboard control with the same changed-channel set and equal, nonempty function coverage. | This measures upstream's strongest published **1.0 threshold**. The original lower-threshold sweep is not reproduced by this matrix. Axcess's separate ablation applies coverage equality to Axcess measurements on the same page; its payload filter is another arm. |

D2, D2b, D3, D4, and D7 use upstream's element traversal, including captured
shadow roots and frames, and its visibility rule. D0, D2–D8 report their raw
proposals minus the observed Tab set. D1 does not subtract Tab. Raw proposals
are retained separately because candidate discovery and deciding a violation
are different tasks.

## Harness and reliability differences

The Tab walker uses Axcess's frame-aware traversal and a cap of 300 rather than
upstream's 80. Capped traversal is uncertain. Ordinary script cannot read focus
inside a closed shadow root; the improved C3–C9 rules abstain on relevant absent
targets instead of inferring inaccessibility from an opaque observation.

The candidate study measures static rules/features before its hover experiment.
In upstream's ordering the registration-shim read follows hover. A page that
installs listeners during hover could therefore produce different registrations.
No byte-for-byte claim about the entire measurement sequence is made.

CDP box resolution now takes the minimum and maximum of **all four border-quad
corners**, which matters for transformed elements. The original shim fallback
and its frame-offset calculation are present, with the resolution surface saved
in the evidence. That is a source transcription, not a claim that the upstream
frame-offset formula handles every transformed iframe correctly.

Unexpected frame, listener, or screenshot failures raise and invalidate the
candidate run. Upstream often catches these failures and returns no candidates.
Normal absence of a rendered box and out-of-viewport hover targets remain
exclusions. The stricter failure policy is an intentional reliability change.

A failed profiler recording can affect both a finding and another finding that
needs the failed control as an equivalent keyboard alternative. The coverage
ablation therefore abstains for that page; upstream Stage 4 abstains for its
global comparison pool on coverage failures. Independent effect-based arms keep
their own results. Expected missing geometry is recorded as a target-observation
limitation and is not mislabeled as a profiler failure.

## Verification and meaning

The tests in [test_upstream_candidates.py](../../tests/integration/test_upstream_candidates.py)
exercise individual rules in Chromium, including listener depth/event sets,
token matching, transformed bounds, closed-shadow fallback, broad axe
attribution, and failure propagation. The init script was separately compared
with the pinned upstream text and exercised against browser channel cases.
Tests establish the cases they cover; they do not prove equivalence for every
possible page.

The 95 targets include the original 60 and 35 initially blind-authored examples.
The C1–C9 rules were designed **after inspecting their errors**, so their new
scores are development results, even though the fixture bytes and answer key
remain frozen. They need unseen pages before any general accuracy claim.

See [the cheap-detector review](CHEAP_DETECTOR_REVIEW.md) for measured changes,
remaining false alarms and misses, candidate budget, and reproducible evidence.
