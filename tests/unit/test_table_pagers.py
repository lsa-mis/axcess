"""Every paged table draws its pager over the table and again under its last row.

Each screen used to draw the two pagers by hand: one in the bar over the
table and a second, ``place="end"``, under it. A screen added later drew only
the first, so a reader at the foot of a long page had to scroll back up to
turn it. ``PagedTable`` (components/TablePagination.tsx) now draws both as
one pair, so a screen cannot draw one without the other. This check keeps it
that way: no file but TablePagination.tsx itself may draw ``TablePagination``.
The rationale is on ``PagedTable``.
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "src/audit/web/frontend/src"
ALLOWED = FRONTEND_SRC / "components/TablePagination.tsx"

# A JSX element: `<TablePagination` followed by whitespace, `/` or `>`, so
# `<TablePaginationProps>` (a type argument) is not one.
_DRAWS_PAGER = re.compile(r"<TablePagination(?=[\s/>])")


def _drawn_pagers(source: str) -> list[int]:
    """Line numbers on which ``source`` draws a ``TablePagination``."""
    return [source.count("\n", 0, match.start()) + 1 for match in _DRAWS_PAGER.finditer(source)]


def test_matcher_finds_a_drawn_pager_and_ignores_the_rest() -> None:
    assert _drawn_pagers('<TableBar pager={<TablePagination label="Issues" />} />') == [1]
    assert _drawn_pagers('x\n  <TablePagination\n    label="Pages"\n  />') == [2]
    assert _drawn_pagers("<TablePagination/>") == [1]
    assert _drawn_pagers("const props: Omit<TablePaginationProps, 'place'> = p;") == []
    assert _drawn_pagers('import { PagedTable } from "../components/TablePagination";') == []
    assert _drawn_pagers("<PagedTable pagination={{ ...paged }}>") == []


def test_only_paged_table_draws_the_pager() -> None:
    files = sorted(FRONTEND_SRC.rglob("*.tsx"))
    assert ALLOWED in files, "components/TablePagination.tsx moved; update this check"
    offenders = [
        f"{path.relative_to(FRONTEND_SRC)}:{line}"
        for path in files
        if path != ALLOWED
        for line in _drawn_pagers(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "These files draw <TablePagination> themselves. Use PagedTable "
        "(components/TablePagination.tsx), which draws the pager over the table "
        "and again under its last row: " + ", ".join(offenders)
    )
