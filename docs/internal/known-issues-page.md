# Known issues test page

`tests/fixtures/site/known_issues/index.html` is a small page with one short,
real pattern for each issue below. `tests/integration/test_known_issues_page.py`
checks that Axcess still finds each one after every change:

```bash
uv run pytest tests/integration/test_known_issues_page.py -rxX
```

| # | Pattern on the page | What Axcess finds | Check |
| --- | --- | --- | --- |
| 1 | A menu hidden until its button is pressed, with a link that has no name | `link-name`, after clicking "Menu" | Rule check (axe) with Click-Through |
| 2 | A heading level skipped (h1, then h3) | `heading-order` (Best practice) | Rule check (axe) |
| 3 | A button with only an icon and no name | `button-name` | Rule check (axe) |
| 4 | Grey text on white, about 2:1 contrast | `color-contrast` | Rule check (axe) |
| 5 | An email field with a placeholder and no label | `markup-placeholder-only` on the field (Mostly sure). axe accepts a placeholder as a name and reports nothing | Page code check (backlog item 8) |
| 6 | A label whose `for` points at no field | `label` on the phone field it leaves unnamed; nothing on the label itself | Known gap for the label (backlog item 9) |
| 7 | White text over a gradient | `color-contrast` as "needs review", shown as Not sure: axe cannot measure contrast over a gradient | Rule check (axe) |

The known gaps are `xfail(strict=True)` tests. When a new check finds one of
them, the test reports XPASS and fails: move that row out of the gaps and
turn its test into a plain one in the same change.

## Comparing with WAVE by hand

Open the file in a browser with the WAVE extension and compare its list
with the table above. Expect two differences, and check them each time
rather than trusting this list:

- WAVE checks the page as it is when you run it. With the menu closed, it
  does not see the link inside (row 1), which Axcess finds after clicking.
- WAVE reports the unconnected label (row 6) itself, as well as the unnamed
  field. Axcess reports only the field.
- WAVE may list the gradient text (row 7) as a contrast alert or not at all.
  Axcess lists it as Not sure, never as a failure.

Keep the page small. Add a pattern only together with the assertion that
says what Axcess must find on it.
