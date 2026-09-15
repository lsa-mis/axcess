# Pre-registration: G1c, does tagging perturb focus order?

Written **before** the run that tests it. Manager: Opus 5 (claude-opus-5).
Baseline `fc5a1d5be193212c44f4b92b57a3fbb0679eb1eb`, branch `tabbing`.

## Why this run exists

`FEASIBILITY.md` §5 established G1a (census ids stable across fresh contexts) and
G1b (tagged and untagged DOM signatures identical). It did **not** establish that
tagging leaves *focus order* unchanged, and reported "11-15 distinct focus stops"
as if it had. Those figures were tagged-only; the untagged arm recorded 3 / 1 / 1
because the probe fell back to `tagName` when the census attribute was absent.
The two arms were not measuring the same quantity, so the comparison was void.

The probe is now structural (`replay.FOCUS_PROBE_JS`), identical in both arms.

## Hypotheses

- **H0 (inert):** the census attribute does not change tab order. Tagged and
  untagged runs on the same subject produce **identical focus trails**.
- **H1 (perturbing):** the attribute changes what is focusable or in what order.

H1 is live, not a formality: `setAttribute` invalidates style and can trigger
attribute selectors, and any layout shift can move a focus target.

## Numeric predictions

Per subject, 15 `Tab` presses, 2 repeats per arm, fresh context each run.

1. **Within-arm reproducibility:** repeat 0 and repeat 1 trails identical.
   Spread 0. If an arm disagrees with itself, the comparison is uninterpretable
   and this run is void.
2. **Between-arm equality (the test):** tagged trail == untagged trail,
   element for element, in order.
3. **Probe discrimination (control):** untagged `distinct_focus_stops` > 1 on at
   least two of three subjects. This guards against a probe that returns a
   constant and would make H0 pass trivially.

## Falsification

- Any subject where the tagged and untagged trails differ **falsifies H0**. The
  census is then rejected for focus-dependent measurement and the scored arm
  stops until an alternative identity scheme is found. It is not repaired by
  re-running.
- If prediction 3 fails, the probe itself is broken and no conclusion about
  H0 may be drawn from this run.

## Method

`uv run --offline --no-sync python -m tools.feasibility_run`, Chromium
145.0.7632.6, Playwright 1.58.0, viewport 1920x1080, `wait_until="load"` + 3 s
settle, service workers blocked, default-deny routing.

Stopping rule: one pass, 12 runs. Every run is written to
`derived/feasibility.json` including failures. The prior run is preserved as
`derived/feasibility.pre-focus-fix.json` and is not overwritten or discarded.
Both the superseded 11-15 figures and these are reported.

## Scope

Holds for these three captures, this browser, these conditions. It does not
show the frozen detectors behave identically with the attribute present -- that
remains a separate control in `FEASIBILITY.md` §6.
