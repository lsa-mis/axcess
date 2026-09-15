# Premise correction: arm 1 never ran the frozen detectors

Written by Opus 5 after Claude Code's checkpoint challenged the brief's premise.
This supersedes the arm-1 headline in `STATUS-THREE-ARMS.md`.

## The defect

`tools/gds_run.py` imports `asyncio`, `json`, `pathlib`, `sys`, `time` and
`playwright`. Nothing else. The string `kbdiff` appears once, in its docstring.
`grep` across `tools/` finds **no import of anything under `src/audit/`**.

So arm 1's **TP=6 FN=0 FP=0 TN=2** measured a reimplementation of the
differential idea written for this experiment. It is not evidence about the
shipped Axcess detectors, and the objective — *do the frozen Axcess detectors do
better than KAFE's* — was never tested by it.

Claude Code found this by checking the brief's premise. None of the five
negative controls in `gds_run.py` could have: every one of them tested whether
the harness measured *the page* correctly, and all five passed. They could not
detect that the harness was the wrong subject. Logged as
`arm1-never-ran-frozen-detectors`, author opus-5, finder claude-code.

## The frozen detectors do run

`tools/frozen_detector_probe.py` imports `DifferentialRunner`, `TrialConfig` and
`collect_candidates` from `src/audit/analyzer/keyboard/kbdiff/` unmodified, and
runs them against the GDS page.

Pre-registered: VIOLATION for `#webchat`, NO_LEAD for the real `<button>`
control. Falsified if it errors, returns UNKNOWN for both, or cannot address the
elements.

| Probe | Proposed by frozen generator | In tab order | Verdict |
| --- | --- | --- | --- |
| `gds-fake-button` (`#webchat`) | yes | **false** | `no_lead` |
| `gds-real-button` (control) | no | true | `no_lead` |

**H-run falsified.** The frozen candidate generator proposed 283 elements and
correctly placed `#webchat` outside the tab order — but the verdict was
`no_lead`, not `violation`.

## Why, and why it is not a detector bug

The runner logged `kbdiff.taborder.capped found=1 presses=300`. `TabOrder`'s own
docstring states the rule:

> `capped` is true when the walk stopped at the cap rather than completing a
> cycle, which makes every *absent* probe inconclusive rather than unreachable.

Measured directly:

| Tab cap | Focusable elements on page | `capped` | `#webchat` reachability certain |
| --- | --- | --- | --- |
| 300 (default) | 306 | **true** | **false** |
| 1200 | 306 | false | **true** |

The GDS test-cases page carries **306 focusable elements against a 300-press
default cap** — six over. The detector declined to call an unproven absence a
violation, which is correct behaviour and the distinction `Verdict.UNKNOWN` and
`reachability_is_certain()` exist to preserve. At cap 1200 the walk completes and
the unreachability becomes certain.

My reimplementation had no such safeguard. It read "not focusable" straight off
the DOM and reported a violation, which is why it scored 6/6 where the frozen
detector abstains. **The reimplementation was more confident, not more correct.**

## Consequences

1. **Arm 1's 6/6 is retracted as a claim about Axcess detectors.** It stands
   only as a statement about a reimplementation, and must be labelled that way
   wherever it appears.
2. **The scored run must import the frozen detectors** — reading (a) in Claude
   Code's checkpoint §3.3. Reading (b) would answer a question nobody asked.
3. **The tab cap is now a pre-registered parameter**, not a default to inherit.
   It must be set per subject from that subject's focusable-element count, with
   the count recorded, and any capped walk reported as an abstention rather than
   a negative. KAFE's subjects include craigslist at 1540 elements, so this is
   load-bearing for the real run, not a GDS artifact.
4. Arm 1 should be re-run through the frozen detectors before any GDS number is
   quoted again.

## Denominator: Claude Code's hand-derived numbers verified

Its `tools/kafe_denominator.py` crashed (`KeyError: 'yhat'` — records built with
`kafe_yhat`, matrix reading `yhat`; logged as
`kafe-denominator-yhat-keyerror`). After the one-word fix, both of its own
controls pass and every hand-derived figure is confirmed:

```
P1_full_corpus_reproduces_published: true   (TP=36 FP=3 FN=0 TN=21)
P2_exclusions_account_for_difference: true
replayable 53 -> 31 positive / 22 negative / 0 label-unknown
KAFE on the same 53: TP=31 FP=2 FN=0 TN=20, precision 31/33, recall 31/31
KAFE FPs surviving into the subset: bowiestate, dell
```

Its mid-session self-correction on `dmv_wc` (IAF-negative, being one of KAFE's
false positives) was right. One detail its manual method could not surface:
`godaddy` is a **partial read**, which the census flags and the scored run must
treat as an abstention rather than a clean subject.

Its selection-bias note stands and should not be softened: the exclusion is
label-correlated (5 of 7 excluded are IAF-positive), so no result on these 53
may be described as a result on KAFE's corpus.
