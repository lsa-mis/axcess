"""Checks that read a PDF's tags and page contents.

:mod:`audit.linked_files.pdf_check` runs these beside its five catalog
checks. Each counts things a screen reader or keyboard user cannot use:

``image_no_description``
    A ``Figure`` tag (after the role map) with no alternative text (``/Alt``)
    and no replacement text (``/ActualText``). PDF/UA-1 7.3; WCAG technique
    PDF1. Tagged files only. Not judged: whether a description is any good,
    or whether a figure is really decoration (a border box tagged as a
    figure fails too; a screen reader then says only "graphic").
``field_no_name``
    A form field with no name a screen reader can announce: no tooltip
    (``/TU``) and no ``/Alt`` on its tag, or a tooltip that is a script's
    placeholder ("undefined", "null"; real forms on www.dol.gov and
    hr.umich.edu have these). PDF/UA-1 7.18.1; WCAG technique PDF12. Any
    file with fields, tagged or not.
``link_no_description``
    A link a screen reader can only call "link": no ``/Contents`` on the
    link, and its ``Link`` tag holds no text, ``/Alt`` or ``/ActualText``
    (or the link is not tagged at all). Visible text inside the tag names
    the link, so a link PDF/UA faults only for a missing ``/Contents`` is
    not failed. PDF/UA-1 7.18.5; WCAG technique PDF11. Tagged files only.
``formula_no_description``
    A ``Formula`` tag with no alternative text and no replacement text, so a
    screen reader cannot read the math. PDF/UA-1 7.7. Tagged files only.
    Like images, only presence is checked, never whether the text says the
    math correctly.
``table_cells_misplaced`` and ``table_uneven_rows``
    A ``Table`` tag whose rows (``TR``, directly or in ``THead``, ``TBody``,
    ``TFoot``) cover different numbers of columns once ``ColSpan`` and
    ``RowSpan`` are counted (attributes with ``/O /Table``): PDF/UA-1 7.2,
    tests 41 to 43. Such a table fails ``table_cells_misplaced`` when a cell
    is seen on the page under another column than its tags give it (by the
    text's position against the full rows' columns), so a screen reader
    reads it under the wrong heading: a group header without its ColSpan
    (the Australian Budget, St Albans, NIST), a row a cell short in the
    middle (hr.umich.edu's 2027 Medicare plan profiles). Otherwise it fails
    ``table_uneven_rows`` only: a label row across the table tagged as one
    cell, or a table whose text could not be placed (past the pages read).
    Spans set through a class map (``/C``) are not read. Tagged files only.
``untagged_text``
    Visible text (with a letter or digit) outside every tag and every
    artifact, or marked with an MCID that no tag refers to (on the real
    WH-385 form, a section heading): a screen reader reading the tags skips
    it. Text in the top and
    bottom ``EDGE_BAND`` of the page is not counted: running headers and
    footers belong there and are decoration (artifacts) under PDF/UA, and on
    real files that is where untagged revision notes sit. Invisible text
    (render mode 3) is not counted. PDF/UA-1 7.1. Tagged files only.

Measured on real files, not only on files we wrote: see
``docs/internal/document-check.md``.

The file is untrusted. Every walk is bounded (elements, pages, nested
drawings, fields), and :func:`read_structure` never raises: on any fault it
returns None, and the caller records these checks as not run.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    IndirectObject,
    NameObject,
)

log = logging.getLogger(__name__)

#: Structure elements read. Real files reach tens of thousands (IRS
#: Publication 15-T has 57,727 in 71 pages); this stops a hostile file.
MAX_ELEMENTS = 200_000
#: Seconds the structure checks may take on one file. The whole check has a
#: limit (``tracker.CHECK_TIMEOUT_S``) that marks the file "Could not check",
#: losing the five catalog checks too; past this budget only the structure
#: checks are given up. IRS Publication 15-T took 6.8 s.
TIME_BUDGET_S = 8.0
#: Form fields read.
MAX_FIELDS = 5_000
#: Drawings (form XObjects) drawn inside drawings, followed this deep.
MAX_XOBJECT_DEPTH = 10
#: Share of the page height, at the top and at the bottom, where untagged
#: text is taken for a running header or footer. On the real hr.umich.edu
#: forms, untagged revision footers sat 0.8% to 3.4% from the bottom; the
#: one untagged body text sat at 46%.
EDGE_BAND = 0.05
#: Tooltips a script left behind instead of a name.
PLACEHOLDER_NAMES = frozenset({"undefined", "null"})

_TEXT_OPS = {b"Tj", b"TJ", b"'", b'"'}
_IDENTITY: tuple[float, ...] = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


@dataclass(frozen=True)
class StructureResult:
    tagged: bool
    images: int = 0
    images_without_description: int = 0
    fields: int = 0
    fields_without_name: int = 0
    links: int = 0
    links_without_description: int = 0
    formulas: int = 0
    formulas_without_description: int = 0
    tables: int = 0
    #: Tables with a cell seen under the wrong column, and the other tables
    #: whose rows cover different numbers of columns.
    misplaced_tables: int = 0
    uneven_tables: int = 0
    untagged_text_runs: int = 0


class _OutOfTimeError(Exception):
    pass


class _Clock:
    def __init__(self, budget_s: float) -> None:
        self._deadline = time.monotonic() + budget_s

    def check(self) -> None:
        if time.monotonic() > self._deadline:
            raise _OutOfTimeError


def read_structure(
    reader: Any, *, max_pages: int, budget_s: float = TIME_BUDGET_S
) -> StructureResult | None:
    """Count what the structure checks look for.

    None when the file could not be read, or took longer than ``budget_s``:
    the caller then records these checks as not run.
    """
    try:
        return _read(reader, max_pages, _Clock(budget_s))
    except _OutOfTimeError:
        log.info("pdf_structure.out_of_time")
        return None
    except Exception as exc:  # untrusted input, RecursionError included
        log.info("pdf_structure.unreadable: %s", type(exc).__name__)
        return None


def _read(reader: Any, max_pages: int, clock: _Clock) -> StructureResult:
    root = reader.root_object
    tree = root.get("/StructTreeRoot")
    elements = _Elements(tree.get_object(), clock) if tree is not None else None
    pages = list(reader.pages)[:max_pages]
    owners = elements.owners if elements else {}

    fields, unnamed = _fields(root, elements, owners)
    if elements is None:
        return StructureResult(tagged=False, fields=fields, fields_without_name=unnamed)

    text = _PageText(clock)
    for page in pages:
        text.read_page(reader, page)

    images = [e for e in elements.items if e.kind == "/Figure"]
    images_without = sum(1 for e in images if not e.described)
    formulas = [i for i, e in enumerate(elements.items) if e.kind == "/Formula"]
    tables = [i for i, e in enumerate(elements.items) if e.kind == "/Table"]
    faults = [elements.table_fault(i, text.boxes) for i in tables]

    links = links_without = 0
    for page in pages:
        for annot in _annotations(page):
            obj = annot.get_object()
            if obj.get("/Subtype") != "/Link" or _hidden(obj):
                continue
            links += 1
            if _text(obj.get("/Contents")):
                continue
            ref = annot.idnum if isinstance(annot, IndirectObject) else None
            owner = owners.get(ref) if ref is not None else None
            if owner is None or not elements.has_content(owner, text.mcids_with_text):
                links_without += 1

    # Text marked with an MCID no element refers to is as hidden as text
    # with none. An element with no /Pg (its own or inherited) says nothing
    # of its page, so its MCIDs match on any page.
    # Some authoring tools mark decoration with an "Artifact" element that
    # only the parent tree reaches (hr.umich.edu's repeated form title on
    # page 3): decoration by intent, so not counted.
    referenced = {m for item in elements.items for m in item.mcids}
    any_page = {mcid for page, mcid in referenced if page is None}
    orphans = [
        (key, runs)
        for key, runs in text.tagged_runs.items()
        if key not in referenced and key[1] not in any_page
    ]
    artifacts = _artifact_mcids(tree.get_object(), pages) if orphans else set()
    orphaned = sum(runs for key, runs in orphans if key not in artifacts)

    return StructureResult(
        tagged=True,
        images=len(images),
        images_without_description=images_without,
        fields=fields,
        fields_without_name=unnamed,
        links=links,
        links_without_description=links_without,
        formulas=len(formulas),
        formulas_without_description=sum(1 for i in formulas if not elements.math_described(i)),
        tables=len(tables),
        misplaced_tables=sum(1 for fault in faults if fault == "misplaced"),
        uneven_tables=sum(1 for fault in faults if fault == "uneven"),
        untagged_text_runs=text.untagged_runs + orphaned,
    )


# --- text values ------------------------------------------------------------


def _text(value: Any) -> str:
    """A PDF text value as plain text, or "" when absent or empty.

    PDF text strings are PDFDocEncoding or UTF-16BE with a byte-order mark
    (UTF-8 with one since PDF 2.0). pypdf returns bytes for one it cannot
    decode, such as hr.umich.edu's "University of Michigan logo" with a
    stray NUL at the end: that is still a description, so bytes are decoded
    leniently and NULs dropped.
    """
    if value is None:
        return ""
    if isinstance(value, IndirectObject):
        value = value.get_object()
    if isinstance(value, bytes):
        raw = bytes(value)
        if raw.startswith(b"\xfe\xff"):
            value = raw[2:].decode("utf-16-be", "replace")
        elif raw.startswith(b"\xef\xbb\xbf"):
            value = raw[3:].decode("utf-8", "replace")
        else:
            value = raw.decode("latin-1")
    return str(value).replace("\x00", "").strip()


# --- the structure tree -----------------------------------------------------


@dataclass
class _Element:
    kind: str
    described: bool
    parent: int | None
    mcids: list[tuple[int | None, int]]
    #: Content in a drawing's own stream (an MCR with /Stm); not read, so
    #: taken as content.
    stream_content: bool = False
    #: In the MathML namespace, or carries a MathML associated file (/AF).
    mathml: bool = False
    #: Table cell spans (attributes with /O /Table); 1 when not set.
    col_span: int = 1
    row_span: int = 1


class _Elements:
    """Every structure element, its marked content and the objects it owns."""

    def __init__(self, tree: DictionaryObject, clock: _Clock) -> None:
        self._clock = clock
        self.items: list[_Element] = []
        self.children: dict[int, list[int]] = {}
        #: Object number of an annotation -> the element that owns it (OBJR).
        self.owners: dict[int, int] = {}
        self._roles = _role_map(tree)
        self._walk(tree)

    def _walk(self, tree: DictionaryObject) -> None:
        seen: set[int] = set()
        stack: list[tuple[Any, int | None, int | None]] = [(tree, None, None)]
        while stack:
            if len(self.items) >= MAX_ELEMENTS:
                raise ValueError("too many structure elements")
            if len(self.items) % 1000 == 0:
                self._clock.check()
            node, parent, page = stack.pop()
            obj = node.get_object() if isinstance(node, IndirectObject) else node
            if not isinstance(obj, DictionaryObject) or id(obj) in seen:
                continue
            seen.add(id(obj))
            pg = obj.get("/Pg")
            if isinstance(pg, IndirectObject):
                page = pg.idnum
            index = parent
            if obj.get("/S") is not None and obj is not tree:
                index = len(self.items)
                self.items.append(
                    _Element(
                        kind=self._standard(str(obj["/S"])),
                        described=bool(_text(obj.get("/Alt")) or _text(obj.get("/ActualText"))),
                        parent=parent,
                        mcids=[],
                        col_span=_span(obj, "/ColSpan"),
                        row_span=_span(obj, "/RowSpan"),
                        mathml=_namespace(obj) == _MATHML_NS or _has_mathml_file(obj),
                    )
                )
                if parent is not None:
                    self.children.setdefault(parent, []).append(index)
            kids = obj.get("/K")
            if kids is None:
                continue
            kids = kids.get_object() if isinstance(kids, IndirectObject) else kids
            # Reversed onto the stack, so elements are read, and children
            # listed, in document order: a table's rows top to bottom.
            for kid in reversed(kids if isinstance(kids, ArrayObject) else [kids]):
                self._kid(kid, index, page, stack)

    def _kid(self, kid: Any, index: int | None, page: int | None, stack: list[Any]) -> None:
        obj = kid.get_object() if isinstance(kid, IndirectObject) else kid
        if isinstance(obj, int):
            if index is not None:
                self.items[index].mcids.append((page, int(obj)))
            return
        if not isinstance(obj, DictionaryObject):
            return
        kind = obj.get("/Type")
        if kind == "/MCR":
            if index is None:
                return
            if obj.get("/Stm") is not None:
                self.items[index].stream_content = True
                return
            pg = obj.get("/Pg")
            self.items[index].mcids.append(
                (pg.idnum if isinstance(pg, IndirectObject) else page, _int(obj["/MCID"]))
            )
        elif kind == "/OBJR":
            ref = obj.get("/Obj")
            if index is not None and isinstance(ref, IndirectObject):
                self.owners[ref.idnum] = index
        else:
            stack.append((kid, index, page))

    def _standard(self, kind: str) -> str:
        """Follow the role map to a standard type ("/Image" -> "/Figure")."""
        for _ in range(10):
            mapped = self._roles.get(kind)
            if mapped is None or mapped == kind:
                break
            kind = mapped
        return kind

    def math_described(self, index: int) -> bool:
        """Whether a formula has words or MathML a screen reader can use.

        Alt text or replacement text, as PDF/UA-1 asks; or MathML, the way
        PDF 2.0 and PDF/UA-2 describe maths: an associated file of type
        application/mathml+xml on the formula, or MathML elements inside it
        (both in the LaTeX Project's tagged PDFs). TeX source alone (an
        associated file of type application/x-tex) is not a description.
        """
        item = self.items[index]
        if item.described or item.mathml:
            return True
        return any(self.items[child].mathml for child in self.children.get(index, ()))

    def table_fault(
        self, index: int, boxes: dict[tuple[int | None, int], list[float]]
    ) -> str | None:
        """What is wrong with a table's rows, if anything.

        None when every row covers the same number of columns. Otherwise
        ``"misplaced"`` when a cell of a short row is seen, on the page,
        under another column than its tags put it in (a header without its
        span, a row missing a cell in the middle): a reader hears that cell,
        and often the ones after it, under the wrong heading. ``"uneven"``
        otherwise: the rows differ, which fails the rule, but no cell was
        seen out of place, either because each sits under its own column (a
        label row across the table tagged as one cell) or because its text
        could not be placed (the table is past the pages read, or its cells
        have no text). "Misplaced" is a claim that needs a cell seen out of
        place; uneven rows are a fact from the tags alone.
        """
        layout = self._table_layout(index)
        widths = {width for width, _ in layout}
        if len(widths) < 2:
            return None
        full = max(widths)
        ranges: dict[int, list[float]] = {}
        for width, cells in layout:
            if width != full:
                continue
            for cell, col, span in cells:
                box = self._box(cell, boxes) if span == 1 else None
                if box is not None:
                    have = ranges.setdefault(col, [box[0], box[1]])
                    have[0], have[1] = min(have[0], box[0]), max(have[1], box[1])
        if len(ranges) < 2:
            return "uneven"
        for width, cells in layout:
            if width == full:
                continue
            for cell, col, span in cells:
                box = self._box(cell, boxes)
                if box is None or span != 1:
                    continue
                if _column_at(box, ranges) != col:
                    return "misplaced"
        return "uneven"

    def _box(
        self, index: int, boxes: dict[tuple[int | None, int], list[float]]
    ) -> tuple[float, float] | None:
        """Left and right edge of the text inside an element, on its page."""
        left = right = None
        stack, seen = [index], set()
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            for key in self.items[i].mcids:
                box = boxes.get(key)
                if box is not None:
                    left = box[0] if left is None else min(left, box[0])
                    right = box[1] if right is None else max(right, box[1])
            stack.extend(self.children.get(i, ()))
        return None if left is None or right is None else (left, right)

    def _table_layout(self, index: int) -> list[tuple[int, list[tuple[int, int, int]]]]:
        """Each row's width and its cells as (element, first column, column span)."""
        rows: list[int] = []
        for child in self.children.get(index, ()):
            kind = self.items[child].kind
            if kind == "/TR":
                rows.append(child)
            elif kind in ("/THead", "/TBody", "/TFoot"):
                rows.extend(c for c in self.children.get(child, ()) if self.items[c].kind == "/TR")
        layout: list[tuple[int, list[tuple[int, int, int]]]] = []
        carried: dict[int, int] = {}  # column -> rows it still covers below
        for row in rows:
            cells = [c for c in self.children.get(row, ()) if self.items[c].kind in ("/TH", "/TD")]
            if not cells:
                continue
            taken = {col for col, left in carried.items() if left > 0}
            below = {col: left - 1 for col, left in carried.items() if left > 1}
            col = 0
            placed: list[tuple[int, int, int]] = []
            for cell in cells:
                while col in taken:
                    col += 1
                item = self.items[cell]
                placed.append((cell, col, item.col_span))
                for offset in range(item.col_span):
                    taken.add(col + offset)
                    if item.row_span > 1:
                        below[col + offset] = item.row_span - 1
                col += item.col_span
            carried = below
            layout.append((len(taken), placed))
        return layout

    def has_content(self, index: int, mcids_with_text: set[tuple[int | None, int]]) -> bool:
        """Whether an element or anything inside it has text or a description."""
        stack, seen = [index], set()
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            item = self.items[i]
            if item.described or item.stream_content:
                return True
            if any(m in mcids_with_text for m in item.mcids):
                return True
            stack.extend(self.children.get(i, ()))
        return False


def _artifact_mcids(tree: DictionaryObject, pages: list[Any]) -> set[tuple[int | None, int]]:
    """(page, MCID) pairs the parent tree assigns to an "/Artifact" element."""
    parent_tree = tree.get("/ParentTree")
    if parent_tree is None:
        return set()
    out: set[tuple[int | None, int]] = set()
    for page in pages:
        key = page.get("/StructParents")
        ref = page.indirect_reference
        if key is None or ref is None:
            continue
        entry = _number_tree_get(parent_tree, int(key))
        if not isinstance(entry, ArrayObject):
            continue
        for mcid, parent in enumerate(entry):
            parent = parent.get_object() if isinstance(parent, IndirectObject) else parent
            if isinstance(parent, DictionaryObject) and parent.get("/S") == "/Artifact":
                out.add((ref.idnum, mcid))
    return out


def _number_tree_get(node: Any, key: int, depth: int = 0) -> Any:
    """Look ``key`` up in a number tree (ISO 32000-1, 7.9.7), bounded."""
    node = node.get_object() if isinstance(node, IndirectObject) else node
    if not isinstance(node, DictionaryObject) or depth > 32:
        return None
    nums = node.get("/Nums")
    if nums is not None:
        nums = nums.get_object()
        for i in range(0, len(nums) - 1, 2):
            if nums[i] == key:
                value = nums[i + 1]
                return value.get_object() if isinstance(value, IndirectObject) else value
    kids = node.get("/Kids")
    for kid in kids.get_object() if kids is not None else ():
        limits = kid.get_object().get("/Limits")
        if limits is None or limits[0] <= key <= limits[1]:
            found = _number_tree_get(kid, key, depth + 1)
            if found is not None:
                return found
    return None


_MATHML_NS = "http://www.w3.org/1998/Math/MathML"


def _column_at(box: tuple[float, float], ranges: dict[int, list[float]]) -> int:
    """The column a cell's text sits under, by the full rows' text extents.

    Text wider than every column it overlaps (a label or a header across
    several columns) is placed by its left edge, where left-aligned text
    starts; other text by its centre. Outside every column: the nearest.
    """
    left, right = box
    overlapping = [c for c, (lo, hi) in ranges.items() if left < hi and right > lo]
    extents = [ranges[c] for c in overlapping]
    wide = bool(extents) and all(right - left > hi - lo for lo, hi in extents)
    x = left if wide else (left + right) / 2
    for col, (lo, hi) in sorted(ranges.items()):
        if lo <= x <= hi:
            return col
    return min(ranges, key=lambda c: min(abs(x - ranges[c][0]), abs(x - ranges[c][1])))


def _namespace(element: DictionaryObject) -> str | None:
    ns = element.get("/NS")
    ns = ns.get_object() if isinstance(ns, IndirectObject) else ns
    if isinstance(ns, DictionaryObject):
        return _text(ns.get("/NS")) or None
    return None


def _has_mathml_file(element: DictionaryObject) -> bool:
    files = element.get("/AF")
    files = files.get_object() if isinstance(files, IndirectObject) else files
    for spec in files if isinstance(files, ArrayObject) else [files]:
        spec = spec.get_object() if isinstance(spec, IndirectObject) else spec
        if not isinstance(spec, DictionaryObject):
            continue
        embedded = spec.get("/EF")
        embedded = embedded.get_object() if isinstance(embedded, IndirectObject) else embedded
        if not isinstance(embedded, DictionaryObject):
            continue
        stream = embedded.get("/F")
        stream = stream.get_object() if isinstance(stream, IndirectObject) else stream
        subtype = str(stream.get("/Subtype", "")) if isinstance(stream, DictionaryObject) else ""
        # pypdf decodes "#2F" in a name read from a file; one built in code keeps it.
        if subtype.replace("#2F", "/").replace("#2f", "/") == "/application/mathml+xml":
            return True
    return False


#: Largest span read; a larger one is a broken or hostile file.
_MAX_SPAN = 1_000


def _span(element: DictionaryObject, key: str) -> int:
    """A table cell's ``ColSpan`` or ``RowSpan`` from its ``/A`` attributes.

    ``/A`` is one attribute dictionary or an array of them, each possibly
    followed by a revision number; only ``/O /Table`` ones hold spans.
    """
    attrs = element.get("/A")
    attrs = attrs.get_object() if isinstance(attrs, IndirectObject) else attrs
    for attr in attrs if isinstance(attrs, ArrayObject) else [attrs]:
        attr = attr.get_object() if isinstance(attr, IndirectObject) else attr
        if isinstance(attr, DictionaryObject) and attr.get("/O") == "/Table" and key in attr:
            try:
                return max(1, min(_int(attr[key]), _MAX_SPAN))
            except (TypeError, ValueError):
                return 1
    return 1


def _role_map(tree: DictionaryObject) -> dict[str, str]:
    roles = tree.get("/RoleMap")
    if roles is None:
        return {}
    roles = roles.get_object()
    if not isinstance(roles, DictionaryObject):
        return {}
    return {str(key): str(value) for key, value in roles.items()}


# --- form fields ------------------------------------------------------------


def _fields(
    root: DictionaryObject, elements: _Elements | None, owners: dict[int, int]
) -> tuple[int, int]:
    """``(fields, fields without a name)``, counting each field a person fills in once."""
    form = root.get("/AcroForm")
    if form is None:
        return 0, 0
    form = form.get_object()
    top = form.get("/Fields") if isinstance(form, DictionaryObject) else None
    if top is None:
        return 0, 0
    total = unnamed = 0
    seen: set[int] = set()
    stack = list(top.get_object())
    while stack and total < MAX_FIELDS:
        node = stack.pop()
        field = node.get_object()
        if not isinstance(field, DictionaryObject) or id(field) in seen:
            continue
        seen.add(id(field))
        kids = field.get("/Kids")
        kids = list(kids.get_object()) if kids is not None else []
        # A kid with its own /T is a field of its own; kids without one are
        # this field's widgets (a radio group's buttons, say).
        sub_fields = [k for k in kids if "/T" in k.get_object()]
        if sub_fields:
            stack.extend(sub_fields)
            continue
        widgets = kids or [node]
        if all(_hidden(w.get_object()) for w in widgets):
            continue
        total += 1
        if not _field_named(field, widgets, elements, owners):
            unnamed += 1
    return total, unnamed


def _field_named(
    field: DictionaryObject, widgets: list[Any], elements: _Elements | None, owners: dict[int, int]
) -> bool:
    tooltip = _text(field.get("/TU"))
    if tooltip:
        return tooltip.lower() not in PLACEHOLDER_NAMES
    if elements is None:
        return False
    for widget in widgets:
        if isinstance(widget, IndirectObject):
            owner = owners.get(widget.idnum)
            if owner is not None and elements.items[owner].described:
                return True
    return False


def _hidden(annotation: DictionaryObject) -> bool:
    try:
        return bool(int(annotation.get("/F", 0)) & 2)
    except (TypeError, ValueError):
        return False


def _annotations(page: Any) -> list[Any]:
    annots = page.get("/Annots")
    if annots is None:
        return []
    annots = annots.get_object()
    return list(annots) if isinstance(annots, ArrayObject) else []


# --- page contents ----------------------------------------------------------


def _mul(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    )


def _translate(x: float, y: float) -> tuple[float, ...]:
    return (1.0, 0.0, 0.0, 1.0, x, y)


class _PageText:
    """Reads page contents one operator at a time.

    pypdf's own text extraction hands text to a visitor in batches, after
    the marked-content sequence that held it may have closed, so it cannot
    say which tag text belongs to. This follows ``BDC``/``EMC`` itself and
    decodes only what it needs: whether a run of text has a letter or digit.
    """

    def __init__(self, clock: _Clock) -> None:
        self._clock = clock
        #: (page object number, MCID) of marked content that shows text.
        self.mcids_with_text: set[tuple[int | None, int]] = set()
        #: Left and right edge of the text in each (page, MCID), for tables.
        self.boxes: dict[tuple[int | None, int], list[float]] = {}
        #: Runs of text outside the edge bands, by (page, MCID).
        self.tagged_runs: dict[tuple[int | None, int], int] = {}
        self.untagged_runs = 0

    def read_page(self, reader: Any, page: Any) -> None:
        contents = page.get_contents()
        if contents is None:
            return
        box = page.cropbox
        ref = page.indirect_reference
        self._page = ref.idnum if ref is not None else None
        self._bottom = float(box.bottom)
        self._height = float(box.height) or 1.0
        self._left = float(box.left)
        self._right = float(box.right)
        self._stream(reader, contents, page.get("/Resources"), [], _IDENTITY, 0, set())

    def _stream(
        self,
        reader: Any,
        content: Any,
        resources: Any,
        inherited: list[tuple[str | None, int | None]],
        ctm: tuple[float, ...],
        depth: int,
        drawing: set[int],
    ) -> None:
        resources = resources.get_object() if resources is not None else DictionaryObject()
        fonts = _dict(resources.get("/Font"))
        xobjects = _dict(resources.get("/XObject"))
        properties = _dict(resources.get("/Properties"))
        font_cache: dict[str, Any] = {}
        # Each open marked-content sequence: ("tag" | "art" | None, MCID).
        marks = list(inherited)
        font = None
        size = 1.0
        render = 0
        saved: list[tuple[int, tuple[float, ...]]] = []
        tm = tlm = _IDENTITY
        leading = 0.0
        stream = content if isinstance(content, ContentStream) else ContentStream(content, reader)
        self._clock.check()
        for count, (operands, op) in enumerate(stream.operations):
            if count % 5000 == 0:
                self._clock.check()
            if op in (b"BDC", b"BMC"):
                marks.append(_mark(operands, properties))
            elif op == b"EMC":
                if len(marks) > len(inherited):
                    marks.pop()
            elif op == b"q":
                saved.append((render, ctm))
            elif op == b"Q":
                if saved:
                    render, ctm = saved.pop()
            elif op == b"cm" and len(operands) == 6:
                ctm = _mul(tuple(float(v) for v in operands), ctm)
            elif op == b"BT":
                tm = tlm = _IDENTITY
            elif op == b"Tm" and len(operands) == 6:
                tm = tlm = tuple(float(v) for v in operands)
            elif op in (b"Td", b"TD") and len(operands) == 2:
                if op == b"TD":
                    leading = -float(operands[1])
                tm = tlm = _mul(_translate(float(operands[0]), float(operands[1])), tlm)
            elif op == b"TL" and operands:
                leading = float(operands[0])
            elif op == b"T*":
                tm = tlm = _mul(_translate(0.0, -leading), tlm)
            elif op == b"Tr" and operands:
                render = int(operands[0])
            elif op == b"Tf" and operands:
                font = _font(fonts, str(operands[0]), font_cache)
                size = float(operands[1]) if len(operands) > 1 else 1.0
            elif op in _TEXT_OPS:
                if op in (b"'", b'"'):
                    tm = tlm = _mul(_translate(0.0, -leading), tlm)
                words = None if render == 3 else _words(op, operands, font)
                if words is None:
                    continue
                matrix = _mul(tm, ctm)
                width = _text_width(words, font) * size * matrix[0]
                self._text_run(marks, depth, matrix[5], (matrix[4], matrix[4] + width))
            elif op == b"Do" and operands and depth < MAX_XOBJECT_DEPTH:
                ref = xobjects.get(operands[0])
                if not isinstance(ref, IndirectObject) or ref.idnum in drawing:
                    continue
                xobj: Any = ref.get_object()
                if xobj.get("/Subtype") != "/Form":
                    continue
                matrix = tuple(float(v) for v in xobj.get("/Matrix", _IDENTITY))
                self._stream(
                    reader,
                    xobj,
                    xobj.get("/Resources") or resources,
                    marks,
                    _mul(matrix, ctm),
                    depth + 1,
                    drawing | {ref.idnum},
                )

    def _text_run(
        self,
        marks: list[tuple[str | None, int | None]],
        depth: int,
        y: float,
        span: tuple[float, float],
    ) -> None:
        if any(kind == "art" for kind, _ in marks):
            return
        tagged = [mcid for kind, mcid in marks if kind == "tag" and mcid is not None]
        share = (y - self._bottom) / self._height
        in_body = EDGE_BAND <= share <= 1 - EDGE_BAND
        if tagged:
            # An MCID inside a drawing belongs to the drawing's own stream,
            # not to the page; it still means the text is tagged.
            if depth == 0:
                key = (self._page, tagged[-1])
                self.mcids_with_text.add(key)
                # Widths are estimated from the font; clamped to the page so
                # one bad estimate cannot stretch a column (seen on Pew
                # Research's topline: a run "ending" at x 1626 on a 612 pt page).
                left = max(min(span), self._left)
                right = min(max(span), self._right)
                box = self.boxes.setdefault(key, [left, right])
                box[0], box[1] = min(box[0], left), max(box[1], right)
                if in_body:
                    self.tagged_runs[key] = self.tagged_runs.get(key, 0) + 1
            return
        if in_body:
            self.untagged_runs += 1


def _int(value: Any) -> int:
    return int(value)


def _dict(value: Any) -> DictionaryObject:
    value = value.get_object() if value is not None else None
    return value if isinstance(value, DictionaryObject) else DictionaryObject()


def _mark(operands: list[Any], properties: DictionaryObject) -> tuple[str | None, int | None]:
    tag = operands[0] if operands else None
    if tag == "/Artifact":
        return ("art", None)
    props = operands[1] if len(operands) > 1 else None
    if isinstance(props, NameObject):
        props = properties.get(props)
    props = props.get_object() if props is not None else None
    if isinstance(props, DictionaryObject) and props.get("/MCID") is not None:
        return ("tag", _int(props["/MCID"]))
    return (None, None)


def _font(fonts: DictionaryObject, name: str, cache: dict[str, Any]) -> Any:
    if name not in cache:
        # pypdf's Font is in a private module; the version is pinned in
        # uv.lock, and a font it cannot read is simply not decoded.
        from pypdf.generic._font import Font

        try:
            resource: Any = fonts[name].get_object()
            cache[name] = Font.from_font_resource(resource)
        except Exception:
            cache[name] = None
    return cache[name]


def _text_width(text: str, font: Any) -> float:
    """Width of ``text`` in text space units per point of font size.

    From the font's own glyph widths (thousandths of an em); good enough to
    say which column a cell's text sits under, not for layout.
    """
    widths = getattr(font, "character_widths", None) or {}
    default = float(widths.get("default", 500))
    return sum(float(widths.get(ch, default)) for ch in text) / 1000


def _words(op: bytes, operands: list[Any], font: Any) -> str | None:
    """The text a text operator shows, when it has a letter or digit.

    Text that cannot be decoded is not counted: this check would rather miss
    some untagged text than report text that is not there.
    """
    if not operands:
        return None
    parts: list[Any]
    if op == b"TJ":
        parts = [p for p in operands[0] if isinstance(p, (bytes, str))]
    elif op == b'"':
        parts = operands[2:3]
    else:
        parts = operands[:1]
    if font is None:
        return None
    decoded: list[str] = []
    for part in parts:
        try:
            raw = part.get_original_bytes() if hasattr(part, "get_original_bytes") else bytes(part)
            text = _decode(bytes(raw), font)
        except Exception:  # noqa: S112 - undecodable text is not counted (docstring)
            continue
        decoded.append(text)
    joined = "".join(decoded)
    return joined if any(ch.isalnum() for ch in joined) else None


def _decode(raw: bytes, font: Any) -> str:
    """Decode a text string the way pypdf's text extraction does."""
    if isinstance(font.encoding, str):
        text = raw.decode(font.encoding, "surrogatepass")
    else:
        text = "".join(font.encoding.get(b, chr(b)) for b in raw)
    return "".join(font.character_map.get(ch, ch) for ch in text)
