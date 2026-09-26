# Axcess UX refresh: gauntlet log

Figma page "07 Gauntlet Log" mirrors this file. Critic outputs (full tables, every rubric item) were kept as working files during the session; this log records every Blocker and Major, and counts Minors.

**Loop rules.**
- 8 critics run in parallel, and each sees only research.md, ia.md, frame screenshots and its own lens.
- There are at most 3 rounds. The loop stops early at zero Blockers and zero Majors.
- Blockers are fixed first, then Majors. Minors stay in the backlog unless the fix is one line.
- In rounds 2 and 3, only the lenses that failed re-run, and only against the frames that changed.

## Round 1 (2026-09-23)

| Lens | Blockers | Majors | Minors |
|---|---|---|---|
| Screen reader | 0 | 2 | 11 |
| Keyboard and motor | 0 | 4 | 5 |
| Low vision | 0 | 3 | 9 |
| Cognitive and plain language | 0 | 4 | 6 |
| Analyst speed | 0 | 5 | 5 |
| Developer fixability | 0 | 4 | 6 |
| Leadership 10 seconds | 0 | 2 | 6 |
| Originality and consistency | 0 | 3 | 4 |
| **Total** | **0** | **27** | **52** |

The 27 Majors merged into 21 fixes (R1-01 to R1-21):

| Finding (lens id) | Sev | Fix made | Before frame | After frame |
|---|---|---|---|---|
| No Undo is drawn for decisions or bulk actions (analyst A5, cognitive C5) | Major | R1-01: "Confirmed" + Undo; message "Dismissed. 3 of 13 decided. Undo"; Stop scan asks to confirm | Dashboard 1440 Light, S6, S7, S2 | S12, S6, S7, S2 (round 1 rework) |
| Triage progress is missing; decided rows leave the filtered list, so J and focus return are undefined (analyst A6, X2; keyboard X1) | Major | R1-02: "Decided: 3 of 13"; decided rows stay in place until "Refresh list" (ia.md §6) | Dashboard 1440 Light, Issues | S12 |
| AI leads show only "Flagged", with no reason or text to judge (analyst A8) | Major | R1-03: "What the AI saw", "What the AI cannot see", "Why this might be wrong", Open the page | none (not drawn) | S12 panel |
| Jargon on list and leader surfaces: axe, Alfa, R11, template, instance, rule ids (cognitive C2; leadership L8) | Major | R1-04: glossary link and Help item; "AI only"; "No WCAG rule (best practice)"; SC names in the panel | Dashboard 1440 Light, Overview | same frames after rework |
| "New" means two things; issues and instances mixed; "closed" undefined; count formats differ (cognitive C3) | Major | R1-04: "First seen in Run 4"; units on tiles; "resolved" defined; one count format | Dashboard 1440 Light, S7, S4 | same frames after rework |
| The same Witness marks carry different phrases; the S6 panel header contradicts its own Checks table (originality O5) | Major | R1-05: one mark per check that saw it; component rebuilt | Dashboard 1440 Light rows 12, 13; S6 | same frames after rework |
| The Run picker shows Run 5 while the page shows Run 4 (cognitive C4) | Major | R1-06: picker keeps Run 4; separate "Run 5 scanning: 62%" chip | S2 | S2 after rework |
| No links to WCAG Understanding pages or rule docs (developer D9) | Major | R1-07: h3 References with links, repeated in the ticket | S6 panel | S6 after rework |
| Cannot tell whether a fix worked; the deep link pins an old run (developer D10) | Major | R1-08: newer-run notice; per-instance Still present or Gone; S13 "Gone after rescan" | S6 | S13 |
| Screenshot and HTML controls do not look like controls and have no state (developer X1; low vision V10) | Major | R1-09: secondary buttons "Show screenshot" or "Hide screenshot" with a chevron | Dashboard 1440 panel, S6, S9 | same frames after rework |
| No design for Alfa-only (XPath) or image instances (developer X2) | Major | R1-10: instance variants "XPath location" and "Image" | none | 03 Components, Instance row |
| The all-apps view has no per-app rollup and hides the trend (leadership L7) | Major | R1-11: "By app" table; the summary names the apps; Progress expanded | S5 | S5 after rework |
| border/control on bg/selected is 2.81:1 (low vision V2) | Major | R1-12: #6F86A2 on #EBF1F8 = 3.29:1 | 02 Tokens, S6 instance card | 02 Tokens after rework |
| Row content is 450 px apart with only a 1.29:1 divider (low vision V8) | Major | R1-13: zebra rows; full-width table capped at 1100 | Dashboard Overview | Overview after rework |
| Departures without a logged reason: Export, the evidence line, the logo, lanes, the success color, D8 (originality O4) | Major | R1-14: Export and the evidence line restored; D15 to D18 added | 02 Changes, Dashboard 1440 | same after rework |
| The logo is the "Person confirmed" glyph, which implies certification (originality X2) | Major | R1-15: real Axcess BrandMark restored | Top bar, every frame | Top bar after rework |
| Screenshot alt describes a different page and repeats the caption (screen reader SR9) | Major | R1-16: new alt and caption; drawn image fixed | Dashboard 1440 panel | same after rework |
| Single-key shortcuts collide with browse-mode quick keys (screen reader X1) | Major | R1-17: documented; Alt+Shift option; buttons 1 to 4 Tabs away | S11 | S11 after rework |
| Focus order differs from visual order in the panel and the toolbar (keyboard K1) | Major | R1-18: ia.md now follows the visual order | 06 Page 1440 | ia.md §6; 06 after rework |
| Text buttons and table links are at text height (keyboard K5) | Major | R1-19: 44 px hit areas | S8, S7, 06 | 03 after rework |
| Row keys defined two ways; Escape in the Decide form undefined; sort header lacks Space (keyboard K8) | Major | R1-20: Tab visits every row control, arrows are an extra; Escape closes only the form; Enter or Space | ia.md §7 | ia.md §6 and §7 |

Minors, in the backlog. Examples:
- The trend's low series overlap (leadership X1, low vision X2); the table equivalent mitigates this.
- A Critical rise has the same weight as a Minor rise (leadership X2).
- 87 px presets at 320.

## Scope change (2026-09-23, requested by the user)
From round 2 on, only the desktop design (1440) is updated and critiqued. This covers "Dashboard 1440 Light, Dark, Forced colors", "Dashboard 1440 Overview Light and Dark", the 1440-wide states and the State 13 panel. The 1280, 768 and 320 frames, "State 9 Details at 320" and "Page annotations 320" stay as they were after round 1, each with a caption saying so. The reflow and zoom rules in ia.md §9 and a11y-annotations.md §1 still apply to the build. They are just not re-drawn.

## Round 2 (2026-09-23, desktop frames only)

All 8 lenses re-ran, because each had at least one Major in round 1. Each critic re-checked its own round-1 Blockers and Majors against the reworked desktop frames and looked for new ones. The counts below cover only those rows.

| Lens | Blockers | Majors | Minors |
|---|---|---|---|
| Screen reader | 0 | 0 | 3 |
| Keyboard and motor | 0 | 2 | 2 |
| Low vision | 0 | 1 | 0 |
| Cognitive and plain language | 0 | 1 | 2 |
| Analyst speed | 0 | 2 | 3 |
| Developer fixability | 0 | 1 | 1 |
| Leadership 10 seconds | 0 | 2 | 0 |
| Originality and consistency | 0 | 0 | 2 |
| **Total** | **0** | **9** | **13** |

Round 1 Majors resolved in round 2: 23 of 27.
- Every Major in the screen reader and originality lenses, and in developer D9, D10, X1 and X2.
- Low vision V2 and V10.
- Cognitive C2 (now Minor), C4 and C5.
- Analyst A5, A6, A8 and X2.
- Keyboard K1, K5, K8 and X1.
- Leadership L7.

Still failing: V8, C3, A2, L8. New in round 2: analyst N1, keyboard N1 and N2, developer N1 (a regression from the round 1 relabel), and leadership L4 (a regression: the new summary sentence disagreed with its tile).

| Finding (lens id) | Sev | Fix made (round 2) | Before frame | After frame |
|---|---|---|---|---|
| Overview rows still 476 px from title to status; zebra 1.05:1 (low vision V8) | Major | R2-01: Overview table 880 wide (Severity 128, Issue 400, Since 176, Status 176); row dividers use border/control, 3.39:1 or better | Dashboard 1440 Overview Light and Dark | same, round 2 rework |
| Three "to decide" counts (6, 12, 13); "New" beside "No change"; "Confirm" means two things (cognitive C3) | Major | R2-02: summary repeats the tiles only; "Decided in this view: 0 of 13"; status "New" shown as "Not decided"; "Mark as fixed" for fixes | 1440 header, Overview, S2, S7, S12, S13 | same, round 2 rework |
| Issues and instances mixed in the strip; 19 fixed reads as closed issues (leadership L8) | Major | R2-02: summary states open issues and instances; Fixed tile says "instances fixed" and "On 2 issues" | Overview, S5 | same, round 2 rework |
| Summary sentence disagrees with the Needs review tile (leadership L4, regression) | Major | R2-02: summary uses the tile's number (6 need review) | Overview, 1440 header | same, round 2 rework |
| Bulk bar reachable only after every row and pagination (analyst A2) | Major | R2-03: bar sits between the chips and the table; B jumps to it | S7 | S7 round 2 rework |
| Escape in the bulk bar could wipe a selection; role toolbar vs section (keyboard N2) | Major | R2-03: plain section of buttons; Escape returns focus and never clears; Clear selection has Undo | 03 Bulk bar, 06 card 29 | same, round 2 rework |
| Focus after T undefined; Copy ticket about 22 Tabs away (analyst N1) | Major | R2-04: T moves focus to the Jira ticket h3; the action row comes first | S6 panel B | S6 round 2 rework |
| "Confirmed" toggle could be reversed by a second press (keyboard N1) | Major | R2-05: done state is aria-disabled, not a toggle; a second press says "Already confirmed. Use Undo to change it." | 03 Decision done, 06 card 33 | same, round 2 rework |
| Alfa instance label clipped mid-word (developer N1, regression) | Major | R2-06: shorter label "Alfa location (XPath). axe also found it." set to wrap | S6 panel A, S13 | same, round 2 rework |

One-line Minor fixes made along the way:
- ia.md §7 now gives the correct Tab distance from the details h2.
- The announcement script notes browse mode (screen reader X1).
- One Progress sentence is used everywhere (originality O5).

Other Minors stay in the backlog. Examples:
- D8 and D17 describe the same change twice.
- The Settings dialog uses a checkbox where the shortcuts dialog uses a switch.
- S13's trust slot uses a phrase outside the Witness set.

## Round 3 (2026-09-23, final round, desktop frames only)

Only the six lenses that still had Majors after round 2 re-ran. The screen reader and originality lenses were already clean.

| Lens | Blockers | Majors | Minors |
|---|---|---|---|
| Keyboard and motor | 0 | 2 | 0 |
| Low vision | 0 | 0 | 0 |
| Cognitive and plain language | 0 | 1 | 0 |
| Analyst speed | 0 | 0 | 2 |
| Developer fixability | 0 | 0 | 1 |
| Leadership 10 seconds | 0 | 1 | 1 |
| **Total** | **0** | **4** | **4** |

Resolved in round 3:
- Low vision V8.
- Leadership L8 (now Minor) and L4.
- Analyst A2 and N1.
- Developer N1.
- Keyboard N1 and N2.
- Cognitive C3, in its round 2 form: the counts, "Not decided" and "Mark as fixed".

Four Majors remain. The round limit is reached, so each is recorded below as an open decision instead of a fourth round.

## Open decisions (no Blockers remain; each needs an owner's choice)

| # | Finding (lens id) | Options and trade-offs | Recommendation |
|---|---|---|---|
| OD1 | "Confirmed" still means two things. The status says "this issue is real", while "2 fixed, confirmed by a person" describes a verified fix. It appears in the same Overview row, the Fixed tile, the Done ledger and the State 13 panel (cognitive C3). | (1) Use "verified" for fixes everywhere: "2 fixed, verified by a person", "Not verified as fixed yet", "all verified by a person", "Fixed (verified)". About 8 strings and one new glossary word; nothing else uses "verified". (2) Rename the status to "Confirmed real". This touches the status set, chips, bulk bar, History and the C key, and Confirm would no longer match its result label. (3) Drop the qualifier, since Fixed already implies a person checked. Fewest strings, but it removes the trust cue from the leader view. | (1). Also change the Needs review tile unit to "need review by a person", so that "decide" belongs only to "Not decided". |
| OD2 | The zero-issues state over-credits. The Run 3 all-clear shows 7 issues down but only 4 with a confirmed fix, and no count of issues that are gone but unconfirmed (leadership R3-N1). | (a) Fix only the sample numbers. Smallest change, but the design still hides unconfirmed gone issues. (b) Add a "Gone, needs a person to confirm" count to the Work tiles and the sentence, and show the all-clear headline only when that count is 0. Matches principle 3 and IA C4, but adds a tile or state and tempers the celebration. (c) Narrow the headline to "No open issues in Run 3" and name any accepted risk still in place. Keeps known barriers visible; the sentence gets longer. | (b), plus the accepted-risk clause from (c). |
| OD3 | "Clear selection" removes the bulk bar and the focused button, so focus is lost and the Undo message has nowhere to live (keyboard R3-N1). | (a) Keep the bar mounted showing "0 selected" with Undo inside it, with focus staying on the now aria-disabled "Clear selection". No focus jump, and Undo is 1 Tab away; needs a rule for when the bar leaves. (b) Move focus to "Select all" and show the message at a fixed spot under the toolbar. A predictable target, but focus moves without being asked. (c) Move focus to Undo. Fastest recovery, but a stray Enter undoes, and it breaks "focus never jumps on its own". | (a). The bar leaves on the next list action. |
| OD4 | The list jumps when the bar appears. Inserting about 100 px above the rows moves the rows under a pointer (keyboard R3-N2, a regression from the round 2 move). | (a) Always reserve the bar's height in Triage and Fix, as a "No issues selected" strip hidden from assistive tech until used. No shift; costs about 60 px. (b) Make it a sticky overlay at the top of the Issues region with scroll-padding-top, not sticky below 1024 px. No shift and always in view, but it covers part of the list and needs a 2.4.11 retest. (c) Keep the in-flow insert and scroll by the inserted height. Rows hold still, but the toolbar seems to jump, and the scroll fix needs testing in each browser. | (a). It fits OD3 (a): the strip is always there, so clearing a selection never removes a focused control. |

## Final state
- **Blockers:** 0 across all 3 rounds.
- **Majors:** 27 in round 1, 9 in round 2, 4 in round 3. The 4 remaining are OD1 to OD4 above.
- **Minor backlog:**
  - The trend's low series overlap; the table equivalent mitigates it.
  - A rise in Critical has the same visual weight as a rise in Minor.
  - D8 and D17 duplicate each other.
  - The Settings dialog uses a checkbox where the shortcuts dialog uses a switch.
  - The State 13 trust slot uses a phrase outside the Witness set.
  - "Resolved 212" has no unit in the Progress line.
  - Fixed tiles are taller than the other tiles.
- **Scope:** desktop (1440) from round 2 on. The 1280, 768 and 320 frames include the round 1 fixes and are captioned as not reviewed after that.
