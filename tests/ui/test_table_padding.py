"""Every table keeps the side padding it was given (the developer's rule,
2026-11-16): a heading or cell is never squeezed to make a table fit.

The shared table parts (``ColumnHeader``, ``SortHeader``, ``RowHeader`` and
``Cell`` in components/table/Table.tsx) pad 16px at each side. Two tables
choose less on purpose, and the least each may have is written here so a
change cannot go lower without this test saying so:

- Reports, whose headings keep 12px (the box under the site's name, and the
  actions column, set the rest).
- Issues, which keeps nine columns in view at 1280px beside the sidebar
  (tests/ui/test_accessibility_axe.py::test_issue_table_fits_the_default_desktop_width):
  4px on the three headings that carry a "?" and 6px elsewhere.

Each heading and cell also has the same padding on both sides: a narrow side
is made as wide as the wide one (the developer's rule, 2026-11-16), so a
column's words are not nearer one line than the other. The one exception is
named in ``_indent``.

To fit a table, narrow a column's width (a ``w-*`` or ``min-w-*`` on its
heading), never its padding.
"""

from __future__ import annotations

from typing import Any

import pytest

from .test_wcag_aaa import _open, _screens, report  # noqa: F401 - the fixture

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

pytest.importorskip("playwright.async_api")

# Every visible table's headings and cells with their side padding in pixels.
_PADDING = r"""() => {
  const shown = (el) =>
    el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const out = [];
  document.querySelectorAll('main table').forEach((table, t) => {
    if (!shown(table)) return;
    const caption =
      (table.caption && table.caption.innerText.trim().slice(0, 50)) || `table ${t + 1}`;
    table.querySelectorAll('th, td').forEach((cell) => {
      if (cell.colSpan > 1) return; // an empty-state message, not a column
      const style = getComputedStyle(cell);
      out.push({
        table: caption,
        kind: cell.tagName === 'TH' ? 'heading' : 'cell',
        text: cell.innerText.trim().split('\n')[0].slice(0, 30),
        left: parseFloat(style.paddingLeft),
        right: parseFloat(style.paddingRight),
      });
    });
  });
  return out;
}"""

SHARED_MINIMUM = 16
REPORTS_MINIMUM = 12
ISSUES_MINIMUM = 4


def _minimum(table: str) -> int:
    if table.startswith("Accessibility issue types"):
        return ISSUES_MINIMUM
    if table.startswith("Public reports by site"):
        return REPORTS_MINIMUM
    return SHARED_MINIMUM


def _indent(item: dict[str, Any]) -> bool:
    """The Reports table's Site heading: 64px on the left puts it over the
    site names, which start after the open and close arrow, so it is an
    indent that lines the heading up, not padding."""
    return item["table"].startswith("Public reports by site") and item["text"] == "Site"


async def test_no_table_squeezes_its_side_padding_on_any_screen(
    live_server: tuple[str, int],
    new_page: Any,
    report: tuple[int, int],  # noqa: F811
) -> None:
    base, _ = live_server
    scan_id, page_id = report
    problems: list[str] = []
    checked = 0
    for path in _screens(scan_id, page_id):
        page = await _open(new_page, base, path)
        for item in await page.evaluate(_PADDING):
            checked += 1
            if item["left"] != item["right"] and not _indent(item):
                problems.append(
                    f"{path}: {item['table']} / {item['kind']} {item['text']!r}: "
                    f"uneven, {item['left']}px left, {item['right']}px right"
                )
            least = _minimum(item["table"])
            if min(item["left"], item["right"]) < least:
                problems.append(
                    f"{path}: {item['table']} / {item['kind']} {item['text']!r}: "
                    f"{item['left']}px left, {item['right']}px right, least {least}px"
                )
        await page.context.close()
    assert checked >= 100, checked
    assert not problems, "\n".join(problems)
