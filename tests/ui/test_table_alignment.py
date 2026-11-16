"""Every table's headings sit on their column's side: left over words, right
over numbers (the developer's rule, 2026-11-16).

Centred headings (e905267, 2026-09-26) floated away from the left edge of the
text under them, more so in wide columns, so a reader using screen
magnification, or anyone tracking a dense table, could lose which heading went
with which column. The shared table parts set the side (``ColumnHeader``,
``SortHeader``, ``Cell numeric`` in components/table/Table.tsx); this test
checks every main screen, so a table built by hand, or a cell or heading
given ``text-center``, is caught.

For each visible table: no heading and no cell is centred, and each heading
sits on the same side as the cells under it. A sortable heading is read from
its sort button too, since the button's own alignment is what the reader sees.
"""

from __future__ import annotations

from typing import Any

import pytest

from .test_wcag_aaa import _open, _screens, report  # noqa: F401 - the fixture

pytestmark = [pytest.mark.ui, pytest.mark.asyncio(loop_scope="module")]

pytest.importorskip("playwright.async_api")

# Per visible table: each column's heading side and its cells' sides.
_ALIGNMENT = r"""() => {
  const side = (value) => {
    const left = ['left', 'start', 'flex-start', 'normal'];
    if (left.includes(value)) return 'left';
    if (value === 'right' || value === 'end' || value === 'flex-end') return 'right';
    if (value === 'center') return 'center';
    return value;
  };
  const shown = (el) =>
    el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const out = [];
  document.querySelectorAll('main table').forEach((table, t) => {
    if (!shown(table)) return;
    const head = table.tHead && table.tHead.rows[table.tHead.rows.length - 1];
    if (!head) return;
    const headings = [...head.cells];
    if (headings.some((cell) => cell.colSpan > 1)) return;
    const caption =
      (table.caption && table.caption.innerText.trim().slice(0, 50)) || `table ${t + 1}`;
    const rows = [...table.tBodies].flatMap((body) => [...body.rows])
      .filter((row) => row.cells.length === headings.length)
      .filter((row) => [...row.cells].every((c) => c.colSpan === 1))
      .slice(0, 8);
    headings.forEach((th, i) => {
      const button = th.querySelector('button:not([popovertarget])');
      const heading = side(getComputedStyle(th).textAlign);
      const inner = button ? side(getComputedStyle(button).justifyContent) : heading;
      const text = (button ? button.innerText : th.innerText).trim();
      const label = text.split('\n')[0] || `column ${i + 1}`;
      out.push({
        table: caption,
        column: label,
        heading,
        inner,
        cells: rows.map((row) => side(getComputedStyle(row.cells[i]).textAlign)),
      });
    });
  });
  return out;
}"""


async def _image_id(page: Any, base: str, scan_id: int) -> int:
    body = await (
        await page.request.get(f"{base}/api/scans/{scan_id}/images?group=with_text")
    ).json()
    return int(body["rows"][0]["image_id"])


async def test_headings_sit_on_their_columns_side_on_every_screen(
    live_server: tuple[str, int],
    new_page: Any,
    report: tuple[int, int],  # noqa: F811
) -> None:
    base, _ = live_server
    scan_id, page_id = report
    probe = await _open(new_page, base, "/scans")
    image = await _image_id(probe, base, scan_id)
    await probe.context.close()
    screens = [*_screens(scan_id, page_id), f"/scans/{scan_id}/images/{image}"]
    problems: list[str] = []
    checked = 0
    for path in screens:
        page = await _open(new_page, base, path)
        for column in await page.evaluate(_ALIGNMENT):
            checked += 1
            where = f"{path}: {column['table']} / {column['column']}"
            if "center" in (column["heading"], column["inner"]):
                problems.append(f"{where}: heading centred")
            elif column["heading"] != column["inner"]:
                problems.append(
                    f"{where}: heading {column['heading']}, its button {column['inner']}"
                )
            centred = [c for c in column["cells"] if c == "center"]
            if centred:
                problems.append(f"{where}: {len(centred)} cell(s) centred")
            other = {c for c in column["cells"] if c != "center"} - {column["heading"]}
            if other:
                problems.append(f"{where}: heading {column['heading']}, cells {sorted(other)}")
        await page.context.close()
    # The check reads enough tables to mean something.
    assert checked >= 40, checked
    assert not problems, "\n".join(problems)


async def test_the_check_tells_left_right_and_centre_apart(new_page: Any) -> None:
    """The checker on a table built to break each rule."""
    page = await new_page(viewport={"width": 1280, "height": 720})
    await page.set_content(
        "<main><table><caption>Built</caption><thead><tr>"
        "<th scope=col style='text-align:left'>Name</th>"
        "<th scope=col style='text-align:center'>Count</th>"
        "<th scope=col style='text-align:left'>Total</th>"
        "</tr></thead><tbody><tr>"
        "<td style='text-align:left'>A</td>"
        "<td style='text-align:center'>1</td>"
        "<td style='text-align:right'>2</td>"
        "</tr></tbody></table></main>"
    )
    columns = await page.evaluate(_ALIGNMENT)
    await page.context.close()
    assert [(c["heading"], c["cells"]) for c in columns] == [
        ("left", ["left"]),
        ("center", ["center"]),
        ("left", ["right"]),
    ]
