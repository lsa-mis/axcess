# Keyboard check and modal dialogs: what Axcess covers

Asana task 1218150268010182, "Test keyboard behavior probes - Feature to
cover modal dialogs". Checked on 6 November 2026 on branch
`claude/kbd-probe-modal-verify-c6c47c`. Scope was to verify what already
ships, not to build anything new.

## The short answer

Axcess does **not** check most modal dialog keyboard behaviour today.

- It finds a dialog that **traps the keyboard completely** (Tab, Shift+Tab
  and Escape all fail) **only if the dialog is already open when the page
  loads**. Most dialogs open after a click, so in practice this is rare.
- When a dialog opens after a click, Click-Through opens it and checks that
  it **closes again**. A dialog that will not close is counted in the
  report's coverage notes ("1 dialog would not close, stopping those pages
  early"). It is **not** listed as an issue type or an occurrence.
- Axcess does **not** check whether focus moves into the dialog, whether Tab
  stays inside it, whether Escape closes it, whether focus goes back to the
  button that opened it, or the Tab order inside it.

So a person still has to test every modal dialog by hand. The steps for
that are in [testing-keyboard-probe.md](testing-keyboard-probe.md).

## A note on the WCAG number

The Asana task names WCAG 2.1.1 Keyboard. The Keyboard check tests
**WCAG 2.1.2 No Keyboard Trap** (Level A), and only that. Nothing in Axcess
tests 2.1.1 by pressing keys: it does not check that each control in a
dialog can be used from the keyboard. (Some 2.1.1 problems, such as a
clickable `div` with no keyboard access, are found by the rule check
(axe-core) when the page code shows them.)

## Which parts of Axcess touch modal dialogs

| Part | Code | When it runs | What it looks for in a dialog | What the report shows |
| --- | --- | --- | --- | --- |
| Keyboard check | `src/audit/analyzer/keyboard/probe.py` | Once, on the page as it loaded | One element that keeps focus after 4 Tab presses **and** 4 Shift+Tab presses | An occurrence, rule `keyboard-trap-stuck`, WCAG 2.1.2, marked as needing a person to confirm |
| Click-Through | `src/audit/analyzer/interaction/probe.py` | After the Keyboard check; clicks buttons and checks each new page state | Whether a dialog it opened closes again (Escape, then a button named Close, Cancel, Dismiss and similar) | A count in the coverage notes. No occurrence. |
| Escape check (turned off) | `KeyboardProbe._probe_modal_escape` | Never. `run()` does not call it. | Whether pressing Escape moves focus out of an open dialog | Nothing. The rule `keyboard-trap-modal-no-escape` is marked "legacy; no longer emitted" in `keyboard/base.py`. |

The Escape check was turned off on purpose. The probe's own comments say
that Escape is not the only allowed way out of a component, so ignoring
Escape does not prove a 2.1.2 failure. The coverage tracker
(`src/audit/web/coverage_status.py`) says the Keyboard check suppresses
"modal containment": a dialog that keeps Tab inside itself is correct
behaviour, so it must not be reported as a trap.

## How this was tested

Six small test pages were added in
`tests/fixtures/site/sc_2_1_2/modal_verify/`. Each has one button, "Open
settings", that opens one modal dialog (`role="dialog"`,
`aria-modal="true"`). Each page breaks one thing:

| Page | What is wrong |
| --- | --- |
| `good.html` | Nothing. Focus moves in, Tab stays inside, Escape closes it, focus goes back to "Open settings". |
| `no-trap.html` | Tab moves out of the open dialog into the page behind it. |
| `no-escape.html` | Escape does nothing. The "Close settings" button works. |
| `no-return.html` | After closing, focus is on the page body, not on "Open settings". |
| `no-exit.html` | Escape does nothing, and the only button says "Got it". |
| `hard-trap.html` | Tab, Shift+Tab and Escape all do nothing, and there is no button. This is a real 2.1.2 failure. |

Adding `?open=1` to a page's address opens the dialog as the page loads.
That shows what the Keyboard check does when it can see an open dialog.

The checks are in `tests/integration/test_keyboard_probe_modal_coverage.py`.
It first proves that each page really has the problem it claims (so "nothing
found" cannot be blamed on a broken test page). Then it runs the Keyboard
check, the turned-off Escape check, and Click-Through on every page. The
tests pin today's behaviour, gaps included. If a later change starts
catching one of these, the test will fail, and this document must be
updated with it.

Pages were opened from local files (`file://`) in headless Chromium. No
website was scanned.

## Results

What each part reported. "Nothing" means an empty result.

| Page | Keyboard check, dialog closed at load (normal case) | Keyboard check, dialog open at load | Escape check (turned off) | Click-Through |
| --- | --- | --- | --- | --- |
| `good` | Nothing | Nothing | Nothing | Opened 1 dialog, closed it |
| `no-trap` | Nothing | Nothing | Nothing | Opened 1 dialog, closed it |
| `no-escape` | Nothing | Nothing | Would report `keyboard-trap-modal-no-escape` | Opened 1 dialog, closed it with "Close settings" |
| `no-return` | Nothing | Nothing | Nothing | Opened 1 dialog, closed it |
| `no-exit` | Nothing | Nothing | Would report `keyboard-trap-modal-no-escape` | Opened 1 dialog, closed it (see note) |
| `hard-trap` | **Nothing (missed)** | **`keyboard-trap-stuck` on `input#name`** | Would report `keyboard-trap-modal-no-escape` | Opened 1 dialog; **it would not close**; page stopped early |

Note on `no-exit`: Click-Through closed this dialog by clicking "Got it".
It did not do that as a dismissal (that only uses names such as Close or
Cancel). It clicked "Got it" while exploring the controls inside the
dialog, and the click happened to close it.

The occurrence recorded for `hard-trap` with the dialog open at load:

```text
rule_id         keyboard-trap-stuck
target_selector input#name
impact          critical
WCAG            2.1.2, Level A
summary         Measured focus exit behavior: focus remained on this same element
                after 4 Tab attempts and 4 Shift+Tab attempts (8 failed exit
                attempts total). Axcess does not count ordinary focus wrapping,
                two-control cycles, modal containment, or opaque iframe focus as a
                trap. Confirm manually that the component has no documented
                keyboard exit command before recording a WCAG 2.1.2 failure.
```

The Click-Through result for `hard-trap` (dialog opened by a click):

```text
dialogs_opened  1
dialogs_stuck   1
limits          ['dialog_not_dismissed']
detail          Dialog "#dialog" opened by "Open settings" did not close
                (tried Escape); page exploration stopped.
findings        ()
```

## Test output

All commands were run in this worktree with `uv run --offline` (packages
came from the local cache; nothing was downloaded).

New modal tests, one line per test:

```text
$ uv run pytest tests/integration/test_keyboard_probe_modal_coverage.py -v
test_fixture_good_keeps_tab_inside_and_returns_focus PASSED
test_fixture_no_trap_lets_tab_leave PASSED
test_fixture_no_escape_ignores_escape PASSED
test_fixture_no_return_drops_focus_on_close PASSED
test_fixture_hard_trap_holds_focus PASSED
test_keyboard_probe_never_opens_a_closed_dialog[good|no-trap|no-escape|no-return|no-exit|hard-trap] PASSED (6)
test_keyboard_probe_reports_nothing_for_open_soft_failures[good|no-trap|no-escape|no-return|no-exit] PASSED (5)
test_keyboard_probe_catches_hard_trap_open_at_load PASSED
test_disabled_escape_check_would_flag_ignored_escape[no-escape|no-exit|hard-trap] PASSED (3)
test_interaction_probe_opens_and_closes_soft_failures[good|no-trap|no-escape|no-return|no-exit] PASSED (5)
test_interaction_probe_counts_hard_trap_as_stuck_dialog PASSED
============================== 26 passed in 9.96s ==============================
```

New and existing Keyboard check tests together:

```text
$ uv run pytest tests/integration/test_keyboard_probe_modal_coverage.py \
    tests/integration/test_keyboard_probe.py tests/unit/test_keyboard_probe_base.py -q
46 passed in 13.88s
```

Existing Click-Through dialog tests:

```text
$ uv run pytest tests/integration/test_interaction_probe.py -q -k dialog
5 passed, 33 deselected in 11.60s
```

Unit tests:

```text
$ uv run pytest tests/unit -q
SKIPPED [1] tests/unit/test_guidance_cards.py:111: the Alfa runner is not installed
1252 passed, 1 skipped, 220 warnings in 27.50s
```

## What Axcess misses, and which WCAG criterion it touches

| Modal behaviour | Checked by Axcess? | WCAG criterion or guidance |
| --- | --- | --- |
| Keyboard fully stuck in a dialog opened by a click | Only as a coverage note ("would not close"), not an occurrence | 2.1.2 No Keyboard Trap, Level A |
| Keyboard fully stuck in a dialog open at page load | Yes, as an occurrence to confirm | 2.1.2 No Keyboard Trap, Level A |
| Focus moves into the dialog when it opens | No | 2.4.3 Focus Order, Level A |
| Focus goes back to the opening button when it closes | No | 2.4.3 Focus Order, Level A |
| Tab stays inside the open dialog | No | WAI-ARIA Authoring Practices, modal dialog pattern; can also fail 2.4.3 when focus lands on hidden content |
| Escape closes the dialog | No (check exists but is turned off) | WAI-ARIA Authoring Practices, modal dialog pattern (not itself a WCAG failure) |
| Tab order inside the dialog makes sense | No | 2.4.3 Focus Order, Level A |
| Every control inside works from the keyboard | No keyboard test; the rule check (axe-core) finds some cases in the page code | 2.1.1 Keyboard, Level A |
| Rule-check problems inside a dialog (missing labels, contrast) | Yes, by Click-Through, while the dialog is open | Many; for example 1.3.1, 4.1.2 |

Modal dialog pattern:
https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/

## Possible follow-ups (not done here)

These would be new features, so they were left out of this task:

1. Run the Keyboard check inside each dialog that Click-Through opens, so a
   full trap opened by a click becomes an occurrence instead of only a
   coverage note.
2. Add a "focus moved into the dialog" and "focus came back to the opening
   button" check to Click-Through, reported against 2.4.3 as needing a
   person to confirm.
3. Decide whether the turned-off Escape check should come back as a "For
   information" result. It works (see the table above), but by itself it is
   not a WCAG failure.

## What was verified and what was assumed

Verified (run and seen): every result in the tables above, the test output,
and that each test page behaves as described.

Assumed, not run: that a full scan through the app gives the same results.
The probes were called directly, the way `src/audit/crawler/js_fetcher.py`
calls them (Keyboard check first, then Click-Through), but no scan was
started through the app or the web server. The steps for Mikhail include a
way to check this.
