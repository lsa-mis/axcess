# A/B: the shipped keyboard check against the SC 2.1.1 upgrade

This compares what a scan runs today with the two modes of the new mouse-only
control check in `src/audit/analyzer/keyboard/operability.py`. Every number
comes from a `results/ab-*.json` artifact written by `run_ab.py`, and each
artifact pins the SHA-256 of the detector it measured.

| arm | what runs on each page |
|---|---|
| **A current** | `KeyboardProbe`: the SC 2.1.2 Tab/Shift+Tab walk, as shipped. |
| **B Standard** | A, then `KeyboardOperabilityProbe()`: one CDP `getEventListeners(document, depth=-1, pierce)` call and one DOM read per frame. It presses no keys of its own. |
| **C Advanced** | A, then `KeyboardOperabilityProbe(advanced=True)`: B's leads, plus the weak "clickable styling" leads B leaves out, each clicked under the interaction probe's guard. Leads Tab can reach are then tried with Enter and Space. |

A only looks for SC 2.1.2 traps. It is here as the cost baseline and to show
what a scan misses today. Its 0% recall on these SC 2.1.1 corpora is expected;
it does not mean the trap check is broken.

The sections after this one describe round 1, the first release of Standard.
**Round 2**, at the end, adds three cheap detectors to Standard and re-scores
it against round 1 in the same runs (arm `B1 standard-v1`).

## Development corpora and held-out corpora

The rules were written while reading errors on `fixtures` and `edgecases`.
`gds` and `ma11y` were held out for one run (`heldout1`). Five general fixes
were then made from their misses (listed below), so they are **development
corpora now**, and their first-contact result is reported separately.
**KAFE was the only corpus never used to change the detector.** It ran once
with the design frozen (`ab-kafe-heldout1.json`, detector
`bde66603…`). After that, the embedded JavaScript was rewrapped to meet the
100-column lint, with line breaks only (`2ed40db3…`). KAFE then ran again
(`ab-kafe-repeat1.json`): B's leads were identical on all 40 subjects, and C's
scores were identical.

## KAFE corpus (held out): 40 replayed subjects, page-level

Unit: the page. KAFE labels pages, so a subject counts as flagged if the arm
reported at least one finding. These are the same 40 subjects the literature
matrix scored (25 KAFE-positive, 15 negative). Captures are replayed offline
with default-deny routing, and no site was contacted.

| arm | TP | FP | FN | TN | precision | recall | F1 | mean ms/page | added ms/button |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A current | 0 | 0 | 25 | 15 | — | 0.0% | — | 706 | — |
| **B Standard** | **21** | **0** | 4 | 15 | **100.0%** | 84.0% | **91.3%** | 844 | **0.9** |
| C Advanced | 22 | 2 | 3 | 13 | 91.7% | **88.0%** | 89.8% | 3,620 | 20.7 |

The same corpus in the literature study (`literature-replication/FINAL-REPORT.md`
§5.1). Their "ms/button" divides by the 5,605 candidates; the column above uses
the same denominator.

| row | precision | recall | F1 | ms/button |
|---|---:|---:|---:|---:|
| KAFE, published output (not a local run) | 96.2% | 100.0% | 98.0% | 19,978.6 (full pipeline) |
| best Axcess row before this: `D9+S4ours` | 75.0% | 100.0% (decided) | 85.7% | 1,428.7 |
| best cheap row before this: `D5 CDP getEventListeners` | 80.8% | 91.3% (decided) | 85.7% | 3.2 |
| **B Standard (this work)** | **100.0%** | **84.0% (strict)** | **91.3%** | **6.0 with the trap walk; 0.9 added** |

**What this does and does not show.**

- On KAFE's own benchmark, Standard is the best Axcess row: F1 91.3% against the
  previous 85.7%. It is still below KAFE's 98.0%.
- Recall here is **strict**: TP / 25, with no abstentions. The literature rows
  quote recall over decided subjects, which flatters them.
- Precision is **page** precision. It says no false lead appeared on any of the
  15 KAFE-negative pages. It does not measure element-level precision on real
  sites.
- Timings are this machine's Chromium 145 on replays, and KAFE's were measured
  in their 2019 setup. Compare them only as orders of magnitude.
- **Advanced is worse than Standard on KAFE's page precision.** Its two false
  positives (`venmo`, `walmart`) and its one extra true positive all come from
  weak "clickable styling" leads that a click then confirmed.
- Replay also handicaps Advanced. Requests missing from the capture are denied,
  so a handler that depends on a new request "changes nothing" and is
  dismissed. That is how C lost `waze`, which B finds. A live scan would not
  have this handicap, but it has not been measured.

The 4 subjects Standard misses are `adorama`, `coinbase`, `godaddy` and
`groupon`. Advanced finds `adorama` and `coinbase` through weak leads.

## Element corpora (development)

Unit: the labelled element. "Unlabelled" counts leads on elements with no
`data-probe` ancestor, which cannot be scored.

| corpus | arm | TP | FP | FN | precision | strict recall | F1 | median ms/page | unlabelled |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fixtures (95 targets, 39 defects) | A | 0 | 0 | 39 | — | 0.0% | — | 241 | 0 |
| | B | 32 | 1 | 7 | 97.0% | 82.1% | 88.9% | 253 | 1 |
| | C | 34 | 0 | 5 | 100.0% | 87.2% | 93.2% | 1,277 | 0 |
| edgecases (74 targets, 40 defects) | A | 0 | 0 | 40 | — | 0.0% | — | 257 | 0 |
| | B | 33 | 3 | 7 | 91.7% | 82.5% | 86.8% | 239 | 0 |
| | C | 34 | 0 | 6 | 100.0% | 85.0% | 91.9% | 1,635 | 0 |
| gds (8 targets, 6 defects) | B | 3 | 0 | 3 | 100.0% | 50.0% | 66.7% | 475 | 2 |
| | C | 3 | 0 | 3 | 100.0% | 50.0% | 66.7% | 8,119 | 2 |
| ma11y (7 targets, 1 defect) | B | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% | 424 | 3 |
| | C | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% | 5,123 | 3 |

**First contact with `gds` and `ma11y`**, before the five fixes below
(`ab-{gds,ma11y}-heldout1.json`):

- gds: B 2/6 and C 1/6, with no false positives.
- ma11y: 0/1 for both arms.

For comparison, the literature study's cheap C-rules score 71.4–82.6% page
precision on KAFE, and C16 scores 100%/97.4% on `fixtures`, where it was
developed. Every figure in this section is a development result. None is
measured accuracy.

## Changes made after the held-out `gds`/`ma11y` run

Each fix is a general principle, not a rule for one probe. Each is also a
reason those two corpora no longer count as held out.

1. **A dialog or popup counts as an effect.** The guard dismisses alerts and
   blocks new windows, so Advanced read the GDS fake button as doing nothing.
2. **Native controls are candidates when Tab cannot reach them.** A button or
   link is mouse-operable by definition, except inside `aria-hidden`.
3. **Focus must stick.** A statically tabbable candidate that the Tab walk
   never visited is focused once, and it counts as reachable only if focus
   stays (WCAG F55, `onfocus="blur()"`). The shipped focus probe already
   focuses every element.
4. **A link with `role=button` and no key handler** is a no-key-activation lead,
   and Advanced tests only Space on it, because Enter already follows links.
5. **A native control never takes the weak-lead path**, even when its class
   looks like a button.

## Known misses (every arm)

- **Focus redirect and Tab interception** (`e110`, `e111`): the element is
  tabbable, but Tab never lands on it. The walk could see this, but only on a
  complete walk, and it risks false leads on content rendered after the walk.
- **Closed shadow roots** (`p91`, `e131`): focus there cannot be observed, so
  these are left out by design.
- **Keys that run a different action** (`h102`, `e43`): the element has a key
  handler. The study found that testing every such element costs precision
  (C16 over all 95 targets: 77.6%).
- **Console-only effects** (`p63`): console output is not treated as an
  effect, because analytics logging would make every click look effective.
- **States that need interaction first**: the GDS lightbox and the hover
  dropdown are not rendered when the page loads.

## Recommendation

- **Ship Standard as part of the keyboard check, on by default.** On held-out
  KAFE it has no false page-level leads and 84% strict recall. It adds under
  1 ms per button, about 140 ms per page on real captures, on top of the
  existing Tab walk.
- **Offer Advanced as an opt-in: "Keyboard (Advanced)".** It has the better
  recall everywhere, and perfect precision on the element corpora. Median page
  cost is 1.3–8 s; the time budget caps it at 20 s plus reloads. On KAFE it
  traded 2 false pages for 1 true one, so it should not be the default until a
  live-site evaluation says otherwise.
- **The next measurement worth running** is an element-level precision audit of
  Standard's leads on a sample of real, live pages, reviewed by a person. None
  of the corpora here can supply that.

## Reproduce

```bash
uv run python experiments/tabbing/ab/run_ab.py --corpus fixtures --label <new>
uv run python experiments/tabbing/ab/run_ab.py --corpus edgecases --label <new>
uv run python experiments/tabbing/ab/run_ab.py --corpus gds --label <new>      # needs the gitignored build
uv run python experiments/tabbing/ab/run_ab.py --corpus ma11y --label <new>    # needs the gitignored build
uv run python experiments/tabbing/ab/run_ab.py --corpus kafe --label <new>     # ~11 min, offline replay
```

The runner refuses to overwrite an existing label.

Artifacts kept in `results/`: round 1 is `*-final.json` (element corpora),
`ab-{gds,ma11y}-heldout1.json` (first contact), `ab-kafe-heldout1.json` and
`ab-kafe-repeat1.json`. Round 2 is `*-v2final.json` (arms `B1` and `B`, final
detector) and `ab-kafe-sealed-{baseline-v1,v2-heldout}.json`. The
intermediate tuning runs are not kept; `v2final` reproduces the last of them
verdict for verdict. The `final` element runs
and `repeat1` pin `2ed40db3…`; the only later change to `operability.py` is its
module docstring.

## Round 2: raising Standard's recall with three more static detectors

Round 1 Standard missed controls with no listener of their own. Its misses on
every corpus fell into two groups: clicks delegated to the document, and menus
shown only by CSS `:hover`. Round 2 adds three static signals. Each costs one
`evaluate` or one CDP call per page, and none clicks anything.

| detector | where the idea comes from | what it reads |
|---|---|---|
| **Resolved event delegation** | the D6/C7 family (a listener on an ancestor or the document) made element-specific | The source of click handlers on `document`, `body` and `window`, through DevTools' `getEventListeners`. It extracts the selectors they test: `closest()`, `matches()`, `.is()`, `classList.contains()`, `hasClass()`, `hasAttribute('data-…')` and `target.id === '…'`. It also reads jQuery's own record of delegated handlers (`$._data(node, 'events')`). A selector matching more than 300 elements is ignored. |
| **CSS hover disclosure** | R5's "hover reveals something hidden", decided from the stylesheet instead of by hovering | Every readable style rule with `:hover`, filtered in the page. It keeps `trigger:hover target` rules that show hidden content holding a control, when no `:focus`/`:focus-within` rule shows the same element (checked element by element) and no script path opens it: `aria-expanded`, a focus or key listener, or a clickable control Tab reaches. |
| **React hover props** | U-D7 (React props) extended | `onMouseEnter` and `onMouseOver` count like a hover listener. |

Round 2 also treats a control scrolled out of view inside a scroll container as
not covered, since scrolling would expose it.

Three changes came from errors, and each is a general rule:

- `getAttribute('data-…')` is **not** delegation evidence. Click trackers read
  attributes; walmart's reads `data-automation-id`.
- Text-only hover content (a tooltip) is left out, because the corpora label it
  as SC 1.4.13 content, not 2.1.1 functionality.
- The harness's own label attribute is never used as a delegation selector.
  That costs one edgecases probe, `e05`, whose handler routes on
  `data-probe`.

Reading every stylesheet through CDP's CSS domain first cost 1.2–2.1 s per real
page, and Chromium kept no text for linked sheets. So the filter runs in the
page instead: 38–99 ms. A cross-origin stylesheet served without CORS cannot be
read, so its rules are missed.

### Results, round 1 against round 2 in the same run

| corpus | round 1 (`B1`) P / R / F1 | round 2 (`B`) P / R / F1 | status |
|---|---|---|---|
| fixtures | 97.0% / 82.1% / 88.9% | **97.4% / 94.9% / 96.1%** | development |
| edgecases | 91.7% / 82.5% / 86.8% | 91.9% / 85.0% / 88.3% | development |
| gds | 100% / 50.0% / 66.7% (3/6) | **100% / 66.7% / 80.0% (4/6)** | development |
| ma11y | 100% / 100% | 100% / 100% | development |
| KAFE, the 40 | 100% / 84.0% / 91.3% | **100% / 92.0% / 95.8%** | **development in round 2** |
| **KAFE, sealed 13** | 80.0% / 66.7% / 72.7% | 80.0% / 66.7% / 72.7% | **held out** |

- **KAFE's 40 became development data in round 2**, because their four misses
  were read to design the detectors. Round 2 adds `adorama` (jQuery-delegated
  `.action` handlers) and `coinbase` (React hover menus). `godaddy` and
  `groupon` are still missed.
- **The sealed 13** are the subjects the literature matrix abstained on:
  their candidate collector found nothing, or their Tab walk capped. This probe
  depends on neither, so they are a fresh test set. Round 1's result on them
  was recorded unseen before round 2 began
  (`ab-kafe-sealed-baseline-v1.json`). Round 2 ran once, frozen
  (`ab-kafe-sealed-v2-heldout.json`).
  - Round 2 neither gained nor lost anything there. The gains above therefore
    have **no held-out confirmation yet**, and 13 subjects (6 positive) could
    not show a small effect either way.
  - The one false positive is `dell`. KAFE labels it negative, but the
    literature's cap diagnosis found a genuine keyboard trap on it. The shipped
    trap check flags it too. KAFE's Type 1 label covers only inaccessible
    functionality; traps are its Type 2.
  - The two misses, `indiegogo` and `salesforce`, were not inspected.
- **Cost, same session:** round 2 adds about 5–10 ms per page over round 1 on
  the element corpora, and about 35 ms mean per page on KAFE replays (the
  largest page: 0.9 s). The unchanged Tab walk still dominates.

### Updated recommendation

Ship round 2 as Standard. On every development corpus it gains recall or
holds it, with no new false positive. On the sealed set it matches round 1.
Keep Advanced opt-in, for the reasons given above.

## Round 3: the other benchmarks

Two more local benchmarks speak to keyboard access and had not been used:
**KAFE's Type 2 labels** (keyboard traps), and the **ten GDS "Keyboard access"
cases** beyond the six inaccessible-functionality cases above. BAGEL's corpus
was unreachable when the literature study checked, and NavA11y's dataset
would need downloading; neither was used. **Every GDS result in this section
is a development result**: the misses were read before the new rules were
written.

### Keyboard traps on KAFE (Type 2): no cheap fix found

KAFE marks 9 of its 60 subjects as containing a trap; 5 are replayable here
(`bowiestate`, `dell`, `dmv_ca`, `vk`, `wendys`). The shipped trap check finds
**1 of 5** (`dell`) and flags **none of the other 48** replayable subjects.

- On the other four, Tab and Shift+Tab from the page as loaded reach the same
  stops and wrap normally. No trap appears in load-state keyboard navigation.
  KAFE's crawl also presses Enter and explores the states it opens, so those
  traps most likely sit inside opened menus or dialogs. Re-walking focus in
  every revealed state is not cheap.
- One cheap signal was tried and rejected: Tab and Shift+Tab reaching
  different sets of stops (`tab_asymmetry.py`,
  `results/kafe-ktf-tab-asymmetry.jsonl`). It fires on 2 of the 5 positives,
  and one of them (`dell`) is already found. It also fires on 4 of the 48
  negatives. Those 4 (`spotify`, `salesforce`, `raise`, `costco`) are subjects
  where focus leaves the page into the browser's own UI, an instrument
  effect. Net: +1 true positive for +4 false positives, so it was not shipped.

### GDS keyboard-access cases: 5 → 8 of 16

`gds_coverage.py` runs every check a default scan runs that bears on the
keyboard (axe at AAA/WCAG 2.2, the focus probe, the keyboard check in both
modes). It attributes each result to the GDS example it sits in
(`results/gds-keyboard-coverage.json`). AAA colour contrast, which fires in
every example, is left out.

| GDS case | caught by |
|---|---|
| tabindex greater than 0 | axe `tabindex` (before this work) |
| fake button / concertina / dropdown / link with role=button | the keyboard check (rounds 1–2) |
| **focus not indicated visually** | new: `focus-not-visible` (SC 2.4.7) |
| **focus assigned to a non-focusable element (tabindex=0)** | new: `focus-order-non-interactive-stop` (SC 2.4.3) |
| **focus order in wrong order** | new: `focus-order-visual-mismatch` (SC 2.4.3) |
| lightbox ×4 (close not focusable, focus not moved, not retained, Esc) | — needs the lightbox open; a Click-Through extension |
| tooltips don't receive focus | — the corpora disagree: GDS counts it, fixtures/edgecases label it a 1.4.13 decoy |
| keyboard trap | — its example page is not in the local GDS copy; its script blocks every key on one link, which the shipped trap check is built for |
| accesskey used / alert shown briefly | — best practice / timing, not keyboard operability |

None of the three new rules fires on GDS's other 126 cases.

**The three new focus-probe rules** (`audit.analyzer.focus.probe`):

- `focus-not-visible` (SC 2.4.7): focus each control (up to 400) and compare
  every property a focus indicator can use. That covers outline (only when it
  draws), shadow, border, background, colour, underline, weight, transform,
  opacity and filter. It reads them on the control, its `::before`/`::after`,
  its parent and grandparent, its neighbours and its labels. Transitions are
  frozen while it runs. Text fields are left out, because the caret shows
  focus. A Shift key press first lets `:focus-visible` polyfills show their
  ring. One lead per tag-and-class shape, at most 10 per page.
- `focus-order-non-interactive-stop` (SC 2.4.3): `tabindex="0"` on plain
  content with no role, no ARIA, no title and no listener (checked over CDP),
  that does not scroll and is not named like a control.
- `focus-order-visual-mismatch` (SC 2.4.3): three or more sibling controls in
  a container where two sharing a line are reached by Tab in the opposite
  order to how they are shown (floats, flex `order`, `row-reverse`; RTL
  aware).

**On 53 real pages (the KAFE replays)**, the three rules cost a median of 53 ms
per page (max 154 ms):

- `focus-not-visible` fires on 20 pages (71 leads). An independent pixel check
  (`focus_pixel_check.py`) screenshots each control before and after focus.
  For **70 of the 70 leads it could measure**, no pixel changed within 10 px.
  It cannot see an indicator drawn further away, and it says nothing about
  whether a change that does happen is visible enough. An earlier version
  disagreed on 3 leads. Two were the short `tag.class` selectors pointing at
  a different element, now unique paths. One was a text field, whose caret
  counts as an indicator; text fields are now excluded.
- `focus-order-visual-mismatch` fires once (`alexa`): a submenu floated right,
  whose links are shown in reverse order. That is a genuine mismatch.
- `focus-order-non-interactive-stop` fires on none. An earlier version flagged
  groupon's `tabindex="0"` `div.facebook-login-button`. That is a broken
  control, not an extra stop, so elements named like controls are now
  excluded.
