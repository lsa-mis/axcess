# Clickable controls skipped by Tab

This development corpus includes deliberately broken pages. The `violation`
labels are fixture expectations about keyboard access, not compliance findings.
The September 2026 additions were brainstormed before examining the seven
existing pages, then compared by behavior rather than wording or appearance.
The comparison below is against `edgecases/pages/`, not the separate frozen
`fixtures/` corpus.

## Ideas already covered

| Idea | Existing coverage | Decision |
| --- | --- | --- |
| Click handler on a non-focusable HTML control | `binding.html`, e01–e07 | Reuse; changing its tag or label alone adds no mechanism. |
| Explicit negative `tabindex` | `keyboard.html`, e45 | Reuse the simple case; add only state or scope differences below. |
| Focusable control with no key activation | `keyboard.html`, e44 | Reuse; this is an activation problem, not missing Tab access. |
| Positive `tabindex` changes order | `keyboard.html`, e46 | Reuse; reordered focus is not automatically unreachable. |
| CSS hover-only content | `hover.html`, e31–e32 | Reuse; new pointer cases change actual button eligibility. |
| Inert, hidden, permanently disabled, or occluded control | `geometry.html`, e61–e70 | Reuse; these do not establish a visible, mouse-operable button. |
| Label or wrapper with an equivalent reachable native control | `decoys.html`, e85–e87b | Reuse; add a proxy whose native control is hidden. |

## New pages and their distinguishing behavior

| Page | Probes | Difference from existing cases |
| --- | --- | --- |
| [native-proxy.html](pages/native-proxy.html) | e100 | A button-styled label opens a hidden file input through native label activation. Unlike e86, the input offers no Tab alternative. |
| [focus-redirect.html](pages/focus-redirect.html) | e110 | A native button has `tabIndex === 0` but immediately sends focus to a sibling. It briefly receives focus and never remains a usable keyboard stop. |
| [tab-trap.html](pages/tab-trap.html) | e111 | A document handler cancels both Tab directions and moves focus elsewhere before the native action can be reached. Isolated so the trap cannot mask other fixtures. |
| [pointer-gated.html](pages/pointer-gated.html) | e120–e121 | Pointer entry changes a button's negative `tabindex` or removes `disabled`. Fresh keyboard-only navigation cannot trigger either change; mouse approach can. |
| [shadow-tab-scope.html](pages/shadow-tab-scope.html) | e130–e131 | Negative `tabindex` on open/closed shadow hosts excludes native buttons that have no negative `tabindex` themselves. The closed root also tests discovery limits. |
| [iframe-tab-scope.html](pages/iframe-tab-scope.html) | e140 | Negative `tabindex` on an iframe excludes its native button from the parent sequence. Same-origin `srcdoc` keeps this local and reproducible. |
| [graphical-controls.html](pages/graphical-controls.html) | e150–e151 | An SVG group and a painted canvas hit region act as buttons. Unlike e23, the canvas is the input surface rather than just an effect destination. |
| [roving-tabindex.html](pages/roving-tabindex.html) | e160–e163 | A working toolbar provides an arrow-key route to its skipped item; a broken toolbar has the same arrow handlers but no initial Tab entry point. |

The additions contain **12 expected violations and 2 working controls**.
e160 and e161 are `ok`: from a fresh page, press Tab twice to enter the working
toolbar, then Right Arrow to reach e161 and Enter or Space to activate it.
Home/End and Left Arrow also move between the working actions. The broken
toolbar has no keyboard entry point even though arrows work after a mouse click.

## Inspecting the fixtures

Open each page with the pointer away from the controls. Compare a fresh
keyboard-only trial with a separate fresh mouse trial. The Before/After buttons
provide navigation landmarks; they intentionally have no action. Successful
activation writes the deterministic value `fired:<probe-id>` into `#out`.
e100 also opens the native file picker; dismiss it without selecting a file.

- Test both Tab and Shift+Tab. e110 redirects focus after receiving it, whereas
  e111 prevents the Tab navigation itself.
- For e120/e121, moving the pointer away resets eligibility. A reused mouse
  trial is not valid evidence of initial keyboard reachability.
- For e121, move the pointer onto the wrapper before clicking. A browser
  automation `locator.click()` that waits for enabled state **before** moving
  the mouse can time out; that is an automation limitation, not an exclusion.
- e131 is inside a closed shadow root. A real coordinate click on the visible
  component works, but DOM queries cannot locate its probe. Preserve the
  runner's `unobservable` outcome instead of interpreting it as a pass.
- e150 has SVG descendant hit targets. e151 responds only inside its painted
  rectangle; the blank canvas margin intentionally does nothing.
- A Tab/Enter-only detector may miss the valid arrow-key path to e161. Labels
  describe available functionality, not the detector's current search budget.

All new probes are registered in [truth.json](truth.json), so the existing
offline bakeoff includes them. See [the experiment README](../README.md) for
the command and request interception details. New files and labels change the
development corpus fingerprint; existing result files describe the older corpus
and must not be presented as measurements of these additions. The separate
frozen fixture manifest is unchanged.
