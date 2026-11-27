# How to test pop-up dialogs with the keyboard

For Mikhail Zolikoff. No coding needed for Part 1. Part 2 needs Axcess
running on your computer.

## Why you need to test by hand

A pop-up dialog (a "modal dialog") is a box that opens over the page, such
as a sign-in box or a settings box. Axcess **does not check** most of how
these boxes work with a keyboard. It only notices a box that never closes.
So every pop-up dialog on a site needs a person to try it with the keyboard.
The details are in
[keyboard-probe-modal-verification.md](keyboard-probe-modal-verification.md).

## Part 1: test any pop-up dialog by hand

You need: a keyboard, and a web page with a button that opens a dialog. Do
not use the mouse once you start.

1. Load the page. Click once on an empty part of the page, then put the
   mouse aside.
2. Press **Tab** until the button that opens the dialog is highlighted.
   Press **Enter**.
3. Write down your answers to these questions.

| Step | What to do | What should happen | WCAG criterion if it fails |
| --- | --- | --- | --- |
| A. Focus moves in | Look at the screen right after the dialog opens. | The highlight (focus) is inside the dialog, on its first control or its heading. | 2.4.3 Focus Order |
| B. Tab stays inside | Press **Tab** about 10 times. | The highlight moves through the dialog's controls and goes back to the first one. It never lands on the page behind the dialog, and never disappears. | 2.4.3 Focus Order |
| C. Order makes sense | Watch the order while you press Tab. | It follows the order you read the dialog: top to bottom, left to right. | 2.4.3 Focus Order |
| D. Backwards works | Press **Shift+Tab** a few times. | The highlight moves backwards through the same controls. | 2.1.2 No Keyboard Trap |
| E. Every control works | On each control, press **Enter** (or **Space** for check boxes). | Each one does what it would do with a click. | 2.1.1 Keyboard |
| F. Escape closes | Open the dialog again. Press **Escape**. | The dialog closes. | Recommended pattern, not a WCAG failure on its own |
| G. Focus comes back | Look at the screen right after the dialog closes. | The highlight is on the button you used to open it. | 2.4.3 Focus Order |
| H. You can always leave | If the dialog has no Escape, find another way out with only the keyboard (a Close button, for example). | There is at least one way out. If there is none, and Tab and Shift+Tab are stuck, you are trapped. | 2.1.2 No Keyboard Trap (serious: report it first) |

Tips:

- If you cannot see where the highlight is, that is a problem too (WCAG
  2.4.7 Focus Visible). Note it.
- Write down the page address, the button name, and the step letter that
  failed. Example: "Contact page, Open settings, step G failed: focus went to
  the top of the page."

### Practice pages

There are six practice pages in the Axcess folder, at
`tests/fixtures/site/sc_2_1_2/modal_verify/`. Open any of them in a web
browser (double-click the file). Each one breaks one step, so you can see
what a failure looks like:

| Page | Step that fails |
| --- | --- |
| `good.html` | None. Every step passes. |
| `no-trap.html` | B: Tab goes to the page behind the dialog. |
| `no-escape.html` | F: Escape does nothing. (Use "Close settings" to leave.) |
| `no-return.html` | G: after closing, the highlight is not on "Open settings". |
| `no-exit.html` | F: Escape does nothing, and the only button says "Got it". |
| `hard-trap.html` | B, D, F and H: you are trapped. Reload the page to get out. |

## Part 2: check what Axcess reports

This checks that a real scan agrees with the verification report. Ask Regan
to start Axcess for you if you have not set it up. It usually runs at
`http://127.0.0.1:8765/app/`.

1. Open the Terminal app. Go to the Axcess folder, then run this command.
   It shows the practice pages to your computer only (not to the internet):

   ```bash
   python3 -m http.server 8000 --bind 127.0.0.1 --directory tests/fixtures/site/sc_2_1_2/modal_verify
   ```

   Leave this window open while you test.
2. In Axcess, go to **New scan**. In **Website address**, type
   `http://127.0.0.1:8000/hard-trap.html` and choose **Start scan**.
3. When the report is ready, open it. Find the **What was checked** section.
   Look at the Click-Through row.
   - **Expected:** a note that 1 dialog would not close, stopping that page
     early.
   - **Expected:** the Issues page has **no** keyboard trap issue type for
     this page. (This is the gap: the trap is only a note, not an issue.)
4. Start another scan with the address
   `http://127.0.0.1:8000/hard-trap.html?open=1`. This version opens the
   dialog as the page loads.
   - **Expected:** the Issues page shows one issue type from the Keyboard
     check, for WCAG 2.1.2, on the name box (`input#name`). It asks a person
     to confirm it.
5. Start a scan with the address `http://127.0.0.1:8000/no-escape.html`.
   - **Expected:** no keyboard issue type, and no "would not close" note.
6. When you finish, go back to the Terminal window and press **Control+C**
   to stop showing the practice pages.

If what you see is different from "Expected", write down the step number and
what you saw, take a screenshot, and send it to Regan. That difference is
useful: it means a real scan does not behave like the direct test.

Note: Part 2 has not been tried through the app yet. The direct test results
are in the verification report.
