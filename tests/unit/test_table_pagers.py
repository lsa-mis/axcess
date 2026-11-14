"""Every paged table draws its pager twice: over the table and under its last row.

The pager under the last row (``TablePagination`` with ``place="end"``,
components/TablePagination.tsx) lets a reader who has read to the end of a
long page of rows turn the page there instead of scrolling back up. It is
not part of the shared table parts: each screen draws it beside the top
one. The Documents tab was written without it and shipped without it
(found 2026-11-14), so this check makes the pair the default: a screen that
draws a top pager and no copy under the table fails here, in CI, without a
browser or a report long enough to need paging.

It reads the source, so it counts per file: as many ``place="end"`` pagers
as top ones. A file with a real reason to differ goes in ``KEEP`` with that
reason.
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).parents[2] / "src/audit/web/frontend/src"
# The component itself, which defines the prop rather than drawing a table.
DEFINES = {"components/TablePagination.tsx"}
# File (relative to FRONTEND) -> why its pagers do not pair up.
KEEP: dict[str, str] = {}

_ELEMENT = re.compile(r"<TablePagination\b(?P<props>[^>]*?)/>", re.DOTALL)


def _pagers(source: str) -> tuple[int, int]:
    """(top pagers, end pagers) drawn in ``source``."""
    top = end = 0
    for match in _ELEMENT.finditer(source):
        if re.search(r"""\bplace=(?:"end"|\{\s*"end"\s*\})""", match.group("props")):
            end += 1
        else:
            top += 1
    return top, end


def test_the_check_tells_a_pair_from_a_lone_pager() -> None:
    pair = """
      <TableBar pager={<TablePagination label="Issues" noun="issue types" {...paged} />} />
      <TablePagination label="Issues" noun="issue types" place="end" {...paged} />
    """
    lone = """
      <TableBar
        pager={
          <TablePagination
            label="Documents"
            {...pagerProps}
          />
        }
      />
    """
    assert _pagers(pair) == (1, 1)
    assert _pagers(lone) == (1, 0)


def test_every_top_pager_has_its_copy_under_the_table() -> None:
    files = sorted(FRONTEND.rglob("*.tsx"))
    assert files, f"no frontend source under {FRONTEND}"
    unpaired: list[str] = []
    for path in files:
        name = path.relative_to(FRONTEND).as_posix()
        if name in DEFINES or name in KEEP:
            continue
        top, end = _pagers(path.read_text(encoding="utf-8"))
        if top != end:
            unpaired.append(f"{name}: {top} top pager(s), {end} under the table")
    assert not unpaired, (
        "Draw the same pager under the last row too: "
        '<TablePagination {...sameProps} place="end" />\n' + "\n".join(unpaired)
    )
