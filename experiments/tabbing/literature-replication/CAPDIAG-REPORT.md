# capdiag: what was wrong, what it now says, and what it still cannot say

Companion to `BRIEF-CAPDIAG.md`. Nothing under `src/audit/` was edited, nothing
was committed, and `derived/kafe_matrix.jsonl` was neither regenerated nor read
for anything but the list of capped subjects and the comparison figures below.

## 1. Read this first

### 1.1 The suspected cause is wrong

The brief proposed that `cap_diagnosis()` skipped focus initialisation that the
scored path performs. **It does not, and there is none to skip.** Both paths do
exactly the same thing before walking:

```python
page = await context.new_page()
await page.goto(url, wait_until="load", timeout=60_000)
await page.wait_for_timeout(1_000)
...
order = await compute_tab_order(page, max_tabs=...)
```

`compute_tab_order` requires a freshly navigated, never-focused page and both
callers give it one. Focus was never outside the document. Running the old
`cap_diagnosis()` path with the walk instrumented shows focus landing on a real
element on the very first Tab press:

```
A_untagged_as_capdiag_does.raw.first_12:
  #el:input:42, #el:input:47, #el:button:50, #el:a:54, #el:a:69, #el:a:74,
  #el:a:75, #el:iframe:79, #el:body:15, #el:iframe:79, #el:body:15, ...
```

Nine distinct focus positions, from the code that reported `distinct_stops: 0`.

### 1.2 The real cause: the diagnostic tagged nothing, so nothing could be counted

`cap_diagnosis()` built its context with

```python
factory = ReplayFactory(browser, replay.ReplayRouter(index), allow=[])
```

`ReplayFactory.tag_script` mirrors `data-probe` onto the ids in `allow`. With
`allow=[]` that is the empty set, so **no element in the page carried a probe
id**. The frozen `TabOrder.index` only records stops whose marker is not the
`#el:` placeholder:

```python
if not marker.startswith(UNNAMED) and marker not in index:
    index[marker] = step
```

`distinct_stops = len(order.index)` was therefore zero for every subject by
construction, whatever the page did. The scored path (`measure_subject`) runs a
discovery pass first, lets `collect_candidates` choose the ids, and builds its
walk context with `allow=probe_ids`.

The fix gives the diagnostic that same discovery pass. Same JS, same 3-second
settle, same collector, same `allow=probe_ids`. The two duplicated JS snippets
were lifted into `DISCOVERY_TAG_JS` and `FOCUSABLE_JS` so the two callers cannot
drift apart again — that is the only edit that touches the scored path, it is a
verbatim move, and §4 shows it changed no measurement.

The same run confirms both halves of the diagnosis at once:

| | old path (`allow=[]`) | fixed path (`allow=probe_ids`) |
| --- | ---: | ---: |
| elements carrying `data-probe` | 0 | 10 |
| `TabOrder.index` size | **0** | **5** |
| distinct focus positions actually visited | 9 | 9 |
| walk capped at 400 | yes | yes |

Focus moved identically in both. Only the counting differed.

### 1.3 The brief's dichotomy does not survive contact with the data

The brief asks whether the 7 are "genuine focus traps or merely tight budgets".
After the fix, **six of the seven are neither.** Their walk settles into a loop
in which `document.hasFocus()` is **false** — focus steps out of the page to the
browser's own UI and the next Tab re-enters at the position it left from rather
than at the first stop.

`compute_tab_order` intends to stop exactly there. Its own comment says so:

```python
if marker is None:
    # Focus left the document (browser chrome). The sequence has wrapped.
```

But it detects that condition as `document.activeElement === null`, and
`document.activeElement` falls back to `<body>` rather than going null. The
branch never fires, the wrap is never seen, and the walk runs to its budget.
Measured directly on `spotify`'s two loop positions:

```json
{"marker": "#el:iframe:79", "tag": "iframe", "document_has_focus": true,
 "src": "https://www.google.com/recaptcha/api2/anchor?...&size=invisible"}
{"marker": "#el:body:15",   "tag": "body",   "document_has_focus": false}
```

That reading has one obvious alternative — that `hasFocus()` goes false simply
because focus moved *into* the iframe — which would make these six real traps
after all. It does not, on this Chromium build
(`tools/capdiag_hasfocus_check.py`, no network, `srcdoc` iframe):

```json
{"focus_inside_iframe": {"top_activeElement": "IFRAME", "top_hasFocus": true,
                         "frame_activeElement": "inner"},
 "nothing_focused":     {"top_activeElement": "BODY",
                         "top_activeElement_is_null": false,
                         "top_hasFocus": true}}
```

Focus inside a child iframe keeps the top document's `hasFocus()` **true**, so
`false` means the page lost focus outright. The same check also confirms the
second half directly: with nothing focused, `document.activeElement` is `BODY`
and **is not null**, so `compute_tab_order`'s wrap branch cannot fire.

**These six subjects cap for an instrument reason, and nothing in this work says
whether those sites trap a keyboard user.** Only `dell` shows a loop the page
holds focus through, and it is the only subject here I would call a focus trap.

Fixing that would mean changing `compute_tab_order`'s termination test from a
null `activeElement` to `document.hasFocus()`. That is a frozen detector and
would move published numbers, so per the brief I stopped and am reporting it
rather than doing it. It is the single highest-value follow-up in this file.

### 1.4 Three of the seven are not reproducible, so their verdicts are not properties of the subject

Five independent runs (§5). `spotify` **capped twice and completed three
times**, which is a straight contradiction between runs of identical code. I
cannot explain it: the frozen walk that decides `capped` runs before and
independently of everything I changed between those runs, and the two runs that
capped were the two earliest. `raise` and `cnn` agree on capping but disagree
substantially on what the walk contains.

So `spotify`'s row in the artifact — "completes at 2645 presses" — is one
reading of an unstable subject, not a finding about `spotify`.

### 1.5 Smaller things that were wrong or are still open

- **A defect in my own loop detector, found and fixed.** The first version read
  a fixed 60-press tail. `raise` orbits 82 positions, so it reported "no loop"
  and the verdict then guessed that "a larger budget may complete it" — for a
  walk that had not reached a new position in its last hundred presses. The
  window now scales with the period, and a no-loop verdict that also has no new
  positions now says "not decided" instead of guessing. `tests/test_capdiag.py`
  pins both failure directions.
- **Whether these loops exist on the live sites is not established.** Everything
  here is an offline replay. Six of seven loops involve an iframe; on `spotify`
  it is an invisible reCAPTCHA frame and the router reports
  `functionally_degraded: true`. That said, degradation does not predict
  capping — 26 of the 45 subjects that did *not* cap are degraded too, and
  `salesforce` caps with `functionally_degraded: false` — so "the replay broke
  it" is not a sufficient explanation either.
- **`raise` and `cnn` named-stop counts swing** (2–45 and 17–126 across runs).
  This is the identity instability §1.4 of `KAFE-MATRIX-REPORT.md` already
  records for those two subjects, showing up again here.

## 2. Controls

Both required controls, on `snapchat` — a subject that scored normally in the
matrix (`tab_capped: false`, `tab_presses: 13`, `tab_stops: 11`). Run through
the fixed diagnostic path, not a special one.

### 2.1 Tiny ceiling must come back capped — `derived/capdiag_control_tiny.json`

```json
{
  "ceiling": 3,
  "subjects": {
    "snapchat": {
      "focusable": 11, "probe_ids": 22, "headroom_cap": 211,
      "presses_at_ceiling": 3,
      "still_capped_at_ceiling": true,
      "distinct_stops": 3,
      "walk": {"observed_presses": 3, "ended": "budget exhausted",
               "distinct_positions": 3, "new_positions_in_last_100": 3,
               "terminal_loop_period": null},
      "verdict": "budget, not a trap: 3 distinct positions in 3 presses with no repeating loop, and 3 of them first reached in the last 100 presses; the walk was still finding new controls when the budget ran out",
      "elapsed_s": 7.2
    }
  }
}
```

Capped, as required. Note `distinct_stops: 3` rather than `0` — under the old
code this control would have read `0` too, and would have looked like the bug.

### 2.2 Same subject at 4000 must terminate with stops — `derived/capdiag_control_full.json`

```json
{
  "ceiling": 4000,
  "subjects": {
    "snapchat": {
      "focusable": 11, "probe_ids": 22, "headroom_cap": 211,
      "presses_at_ceiling": 13,
      "still_capped_at_ceiling": false,
      "distinct_stops": 11,
      "verdict": "terminates at 13 presses; headroom was 198 presses clear of the end",
      "elapsed_s": 5.6
    }
  }
}
```

Terminating, `distinct_stops: 11 > 0`. **The diagnostic can return both
answers.** The old code could not: it returned `capped` for everything.

### 2.3 A third check the brief did not ask for

Control 2.2's figures are identical to `snapchat`'s row in
`derived/kafe_matrix.jsonl` — `focusable 11`, `probe_ids 22`, `tab_presses 13`,
`tab_stops 11`. The fixed diagnostic reproduces the scored run exactly, which is
the direct evidence that it now "walks the page the same way the scored run
does", and also the evidence that lifting the two JS snippets into constants
left the scored path's behaviour alone.

## 3. Per-subject outcome

`derived/kafe_matrix_capdiag.json`, ceiling **4000**, primary run. Every row has
`distinct_stops > 0`; the instrument that answered `capped, 0 stops` for
everything is gone.

| subject | focusable | budget was | stops | presses | capped at 4000 | what the walk does |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `spotify` | 12 | 212 | 7 | 2645 | **no** | completes; the original budget was short by 2433 — but see §1.4, this subject is unstable |
| `salesforce` | 38 | 238 | 5 | 4000 | yes | leaves the page at press 9, 2-position orbit `#el:body:42` ↔ `#el:iframe:131` (sessionserver frame) — **not decided** |
| `raise` | 62 | 262 | 45 | 4000 | yes | leaves the page at press 2531, 49-position orbit — **not decided** |
| `costco` | 69 | 269 | 37 | 4000 | yes | leaves the page at press 39, 2-position orbit `#el:iframe:355` ↔ `#el:body:17` — **not decided** |
| `dell` | 97 | 297 | 32 | 4000 | yes | **focus trap**: from press 36, focus stays on one `<a class="dropdown-toggle check-float-cs">` (`/343:a`) with the page holding focus throughout |
| `dpreview` | 94 | 294 | 92 | 4000 | yes | leaves the page at press 95, 3-position orbit across two iframes — **not decided** |
| `cnn` | 283 | 483 | 67 | 4000 | yes | leaves the page at press 167, 2-position orbit `#el:body:119` ↔ `#el:iframe:965` — **not decided** |

Summary: **1 genuine focus trap** (`dell`), **5 not decided** because the walk
leaves the page and the frozen walker cannot see the wrap, **1 completing** at a
much larger budget (`spotify`, unstable). Zero subjects are "the budget was
merely a little tight" in the sense the brief anticipated — `spotify`'s walk
needs 2645 presses against a 212-press budget, which is not a tight budget but a
page whose tab sequence is an order of magnitude longer than its focusable
count.

No ceiling was tuned. 4000 is the value the diagnostic already used, kept
unchanged so the "before" and "after" are comparable.

## 4. What changed, and the evidence it changed nothing it should not

All edits are in `experiments/tabbing/literature-replication/`.

`tools/kafe_matrix.py`:

- `DISCOVERY_TAG_JS`, `FOCUSABLE_JS` — the discovery init script and focusable
  count lifted verbatim out of `measure_subject`, now shared with the
  diagnostic. **The only change that touches the scored path.** Whitespace
  aside, the text is identical; control 2.3 confirms the behaviour is too.
- `diagnose_subject()` — replaces the body of `cap_diagnosis()`'s loop. Runs the
  scored run's discovery pass, then the frozen walk with `allow=probe_ids`.
- `observe_walk()`, `terminal_period()` — a second, observation-only walk on a
  fresh page, used only to explain a cap. Reads focus with the walker's own
  `_active_marker`, and asks `document.hasFocus()` at each new position.
  **`capped` always comes from the frozen walker; nothing here can override it.**
- `capdiag --subjects/--ceiling/--out` — needed to run the controls.
- `report --reuse` — rebuilds only `KAFE-MATRIX-REPORT.md` from the summaries
  and controls already on disk. A plain `report` re-runs the controls in a
  browser and rewrites `KAFE-MATRIX.md`; this was the change that let §1.3 be
  regenerated with no published number able to move.
- `write_report` — §1.3 now renders the per-subject outcome, the ceiling, the
  cross-run agreement, and the `hasFocus` mechanism.

`tests/test_capdiag.py` — 8 tests over `terminal_period`, covering both the
false-positive and false-negative directions. `uv run pytest tests/test_capdiag.py` → 8 passed.

`tools/capdiag_probe.py`, `tools/capdiag_hasfocus_check.py` — the throwaway
instruments behind §1.1, §1.2 and §1.3. Neither writes a published artefact.
Kept because they are the evidence.

Not changed: anything under `src/audit/`, the scored run's logic, any detector,
`derived/kafe_matrix.jsonl`, and `KAFE-MATRIX.md` (verified: `git diff --stat
KAFE-MATRIX.md` is empty after regenerating the report). Nothing committed.

`KAFE-MATRIX-REPORT.md` diff is 22 insertions and 2 deletions, all inside §1.3.

## 5. Reproducing, and the run-to-run record

```bash
cd experiments/tabbing/literature-replication
uv run --offline --no-sync python -u -m tools.kafe_matrix capdiag
uv run --offline --no-sync python -u -m tools.kafe_matrix capdiag \
    --subjects snapchat --ceiling 3    --out derived/capdiag_control_tiny.json
uv run --offline --no-sync python -u -m tools.kafe_matrix capdiag \
    --subjects snapchat --ceiling 4000 --out derived/capdiag_control_full.json
uv run --offline --no-sync python -u -m tools.kafe_matrix report --reuse

# the evidence in §1.1-§1.3, none of which writes a published artefact
uv run --offline --no-sync python -u -m tools.capdiag_probe spotify --ceiling 400
uv run --offline --no-sync python -u -m tools.capdiag_probe spotify --mode loop
uv run --offline --no-sync python -u -m tools.capdiag_hasfocus_check
```

One chromium per subject, launched and closed inside a `try`/`finally` as
before. I checked `pgrep -af chrome-linux64/chrome` between runs and after the
last one; no orphans at any point. The primary run took 1091 s, the repeats
1039 s and 663 s.

Five runs, newest last. Full output in `derived/capdiag-runs.log`; runs 1 and 2
survive only there, because each run overwrote the previous JSON before I
started writing repeats to separate files.

| subject | run 1 | run 2 | run 3 (primary) | run 4 | run 5 |
| --- | --- | --- | --- | --- | --- |
| `spotify` | cap 4000 | cap 4000 | **term 2645** | **term 2502** | **term 2472** |
| `salesforce` | cap, 2-orbit @9 | cap, 2-orbit @9 | cap, 2-orbit @9 | cap, 2-orbit @9 | cap, 2-orbit @9 |
| `raise` | cap, 2-orbit @415 | cap, no orbit found | cap, 49-orbit @2531 | cap, 49-orbit @2433 | cap, 2-orbit |
| `costco` | cap, 2-orbit @39 | cap, 2-orbit @39 | cap, 2-orbit @39 | cap, 2-orbit @39 | cap, 2-orbit @39 |
| `dell` | cap, 1-orbit @36 | cap, 1-orbit @36 | cap, 1-orbit @36 | cap, 1-orbit @36 | cap, 1-orbit @36 |
| `dpreview` | cap, 3-orbit @95 | cap, 3-orbit @95 | cap, 3-orbit @95 | cap, 3-orbit @95 | cap, 3-orbit @95 |
| `cnn` | cap, 2-orbit @435 | cap, 2-orbit @169 | cap, 2-orbit @167 | cap, 2-orbit @213 | cap, 2-orbit |

Run 2's `raise` reading is the detector defect of §1.5, not the subject. Runs 3
to 5 are identical code; runs 1 and 2 differ only in the observation pass and
the verdict wording, never in the frozen walk that decides `capped`.

`salesforce`, `costco`, `dell` and `dpreview` are stable across all five.
`dell`'s trap is the one result here I would report as a property of a subject.
