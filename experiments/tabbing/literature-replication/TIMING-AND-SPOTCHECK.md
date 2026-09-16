# First real numbers from the frozen detectors

Produced by Opus 5 while Claude Code runs the full scored experiment. Everything
here was executed, not inferred. **This is not the scored result** — it is the
timing baseline and the GDS spot-check that the scored run depends on.

## 1. Per-button cost against the 300 ms cap

Unit: one `run_probe` call on the frozen `DifferentialRunner` — the mouse trial
plus one keyboard trial per configured key, each in its own fresh context.
`tab_order()` is timed separately and excluded, being a once-per-page cost.

Pre-registered: median per-probe time **exceeds** 300 ms, because each probe
opens several browser contexts. Falsified if the median came in under 300 ms.
N=3 probes x 2 repeats, order reversed, all runs reported.

| Probe | repeat 0 | repeat 1 | verdict |
| --- | --- | --- | --- |
| fake button | 1,500.4 ms | 1,282.1 ms | `no_lead` |
| real button (control) | 6,908.7 ms | 6,725.6 ms | `no_lead` |
| tooltip icon | 1,308.7 ms | 1,458.3 ms | **`violation`** |

```
median 1,479.3 ms | min 1,282.1 | max 6,908.7 | spread 5,626.6
runs over the 300 ms cap: 6/6
tab_order, once per page: 2,173 ms
keys tried per probe: Enter, Space, ArrowDown
```

**H-cap not falsified: the frozen differential misses the 300 ms per-button cap
by roughly 5x**, and the worst case is 23x. The pattern explains itself — the
in-tab-order control costs 6.9 s precisely *because* it is reachable, so all
three keys get delivered; an unreachable probe short-circuits after the mouse
trial. Cost scales with how operable an element is.

The 300 ms cap is therefore **not currently met**. Whether that matters is
Harry's call: the cap was set as a ceiling for detecting one button, and this is
a research harness opening fresh contexts per trial for isolation, not a tuned
production path. Recorded as a breach, not explained away.

Scale reference, not a comparison: KAFE's Detection phase averages 995 ms
**per subject page**, recomputed from its own artifact. That is a per-page
figure and cannot be compared with a per-probe one. The published 19.22 min is
proxy/crawl/extract infrastructure, not detection.

## 2. The tab cap was suppressing real detections

Same four probes, same page, only `max_tabs` changed:

| Probe | cap 300 (`capped=true`) | cap 1200 (`capped=false`) |
| --- | --- | --- |
| tooltip icon | `unknown` | **`violation`** |
| concertina | `unknown` | **`violation`** |
| fake button | `no_lead` | `no_lead` |
| real button (control) | `no_lead` | `no_lead` |

The GDS page holds **306 focusable elements against the 300-press default**. At
the default the walk is capped, so `reachability_is_certain()` is false and the
detector returns `unknown` rather than guessing. Raise the cap past the page's
own focusable count and **the frozen detectors find both failures, with the
negative control still clean**.

This is the concrete reason the tab cap must be a pre-registered per-subject
parameter rather than an inherited default. craigslist carries 1540 focusable
elements. A capped walk scored as a negative would understate recall across the
entire corpus, silently.

## 3. Why the fake button stays `no_lead` — and why that is right

Full outcome record at cap 1200:

```
verdict      : no_lead
in_tab_order : False
mouse        : attempted=True, note=None
mouse effect : Effect(changed=frozenset(), payloads={})
key (none)   : attempted=False
               note=probe is not in the tab order; no key could be delivered
```

`changed=frozenset()` — **the mouse click produced no observable effect**.
`#webchat`'s handler is `window.open(...)`, which the harness stubs and which
alters nothing in the page's observable channels. With no mouse effect there is
no differential to measure, so the detector declines to report. It will not call
an element broken-for-keyboard when it never observed it working for mouse.

The retracted reimplementation counted *a listener firing* as mouse success,
which is a weaker standard and is why it scored this case a violation. On this
case the frozen detector is the more conservative and better-justified of the
two. Whether `window.open` should count as an observable effect is a real
question about detector coverage — but it is a detector design question, not a
harness defect, and the detectors stay frozen.

## 4. Status of the actual question

Harry asked for precision, recall and ms versus the published papers. As of this
file:

| Quantity | Status |
| --- | --- |
| Per-button ms | **measured** — median 1,479 ms, 6/6 over the 300 ms cap |
| GDS precision/recall, frozen detectors | in progress (Claude Code, deliverable A) |
| KAFE 53-subject precision/recall | in progress (Claude Code, deliverable B) |

References the run will be scored against, both already recomputed from the
source artifacts:

- **GDS**: all 13 audited tools score **0/6** on the six IAF-matching cases.
- **KAFE, matched to the same 53 replayable subjects**: TP=31 FP=2 FN=0 TN=20,
  **precision 31/33, recall 31/31**. Not the published 36/39 — that is a
  different retained subset.

No precision or recall figure for the frozen detectors exists yet beyond the
four spot-checked probes above. Anything quoted before `RESULTS.md` lands would
be a guess.
