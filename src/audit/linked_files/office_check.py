"""Machine checks on one Word (.docx) or PowerPoint (.pptx) file's bytes.

Our own rules, read with python-docx and python-pptx, modelled on
Microsoft's Accessibility Checker ("Rules for the Accessibility Checker",
https://support.microsoft.com/en-us/office/rules-for-the-accessibility-checker-651e08f2-0fc3-4e10-aaca-74b4a67101c1,
read 2026-11-17). Why our own and not an existing checker:
docs/internal/office-check-research.md. Built and measured on labelled
real files (tests/real_pages/office_files.json), as AGENTS.md asks.

Each check reads a fact the file states about itself. Two kinds:

**Checks that prove a barrier** (``COUNTED``): a failure is a problem a
screen reader user meets, and a machine can see it without judging
meaning. Any one makes the file "Mostly sure" (the developer's rule,
2026-11-17: only machine-checkable rules that affect a screen reader user
count).

``no_alt_text`` (Word and PowerPoint)
    A picture, chart, diagram (SmartArt) or video has no alternative text
    and is not marked decorative. Microsoft: Error, "All non-text content
    has alternative text" (paraphrased: screen readers speak the alt text to
    describe images). Text boxes and shapes holding text are text, not
    images; plain shapes with no text and no picture (lines, boxes) are not
    counted, as Microsoft's own fix for them is to mark them decorative and
    a machine cannot tell a border from an arrow that means something.
    Word: the document body only, not page headers and footers, which
    screen readers do not read as part of the text.
``table_no_header`` (Word and PowerPoint)
    A table of at least 2 rows and 2 columns has no header row. Microsoft:
    Error, "Tables specify column header information". Word: the "Header
    Row" table style option (``tblLook firstRow``), which Microsoft's own
    instructions use ("Make your Word documents accessible"), or "Repeat as
    header row" (``tblHeader``) on the first row; PowerPoint: "Header Row"
    (``a:tblPr firstRow``). Counted, the developer's decision (2026-11-19,
    after a day as a possible problem): a layout table can show "Problem
    found" on its row, but on the labelled real files every such file was
    "Mostly sure" for another real barrier, while as a possible problem the
    rule missed every file whose only barrier was an unmarked data table.
``slide_no_title`` (PowerPoint)
    A slide has no title placeholder holding text. Microsoft: Error, "All
    slides have titles" (paraphrased: titles let people navigate a deck).
``no_headings`` (Word)
    A document of more than ``HEADINGS_MIN_WORDS`` words uses no heading
    style at all, so a screen reader user cannot move between its parts.
    Microsoft: Tip, "Documents use heading styles"; counted here because
    in a long document it is a barrier (WCAG 1.3.1, 2.4.6 and technique
    G130/G141), and the threshold was tuned on real files.
``no_language`` (Word and PowerPoint)
    No language is set anywhere for the text, so a screen reader cannot
    choose a voice (WCAG 3.1.1, Language of Page, Level A). The same check
    as the PDF one, and the same words in the report.

**Possible problems**: a machine can see them, but whether they hurt a
screen reader user needs a person, so they are listed and never make a
file "Mostly sure".

``skipped_heading_level`` (Word)
    A heading more than one level deeper than the one before it (Heading 1
    then Heading 3). Microsoft's guidance: "do not skip heading levels".
``unclear_link_text`` (Word and PowerPoint)
    A link whose words are a web address or a phrase such as "click here".
    Microsoft's guidance warns against "Click here" and similar link text;
    WCAG 2.4.4 (Level A) lets the surrounding sentence give the purpose, so
    a person must judge it.
``no_title`` (Word and PowerPoint)
    No Title document property. A PDF reader shows a PDF's title (so it
    counts there); Word and PowerPoint show the file name, and Google's
    exports never have one, so here it is only a possible problem.

Not checked: reading order (Microsoft lists it as a Warning for a person to
check; the order shapes are stored in says nothing about whether it makes
sense), contrast (needs the theme and layout resolved), merged cells and
alt text quality. A file with no problem found is "Not sure", never
"accessible".

The bytes are untrusted: everything is read in a thread under a time limit
by the caller, a ZIP that would unpack past ``MAX_UNPACKED_BYTES`` is not
read, the XML parsers do not resolve entities (python-docx and python-pptx
set ``resolve_entities=False``), and every exception is "damaged".
"""

from __future__ import annotations

import io
import itertools
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Literal

from audit.linked_files.formats import CheckedAs, FailedCheck
from audit.linked_files.pdf_check import ALL_CHECKS

#: What a downloaded file's bytes are, whatever its address said.
Sniffed = Literal["pdf", "docx", "pptx", "office_other", "encrypted", "old_office", "unknown"]

#: Largest unpacked size read from one file. A Word or PowerPoint file is a
#: ZIP, and a small ZIP can unpack to gigabytes (a "ZIP bomb"); a real
#: document of 10 MB, the download limit, unpacks to far less.
MAX_UNPACKED_BYTES = 200 * 1024 * 1024

_CFB = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_WORD_MAIN = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
    "application/vnd.ms-word.document.macroenabled.main+xml",
    "application/vnd.ms-word.template.macroenabledtemplate.main+xml",
)
_SLIDES_MAIN = (
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml",
    "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml",
    "application/vnd.ms-powerpoint.presentation.macroenabled.main+xml",
    "application/vnd.ms-powerpoint.slideshow.macroenabled.main+xml",
    "application/vnd.ms-powerpoint.template.macroenabled.main+xml",
)


def sniff(data: bytes) -> Sniffed:
    """What ``data`` is, from its bytes alone. Never raises.

    ``office_other`` is an Office ZIP that is neither Word nor PowerPoint
    (an Excel file); ``encrypted`` is an Office file saved with a password
    or rights management, which Office stores as an encrypted compound file;
    ``old_office`` is any other compound file (.doc, .xls, .ppt).
    """
    if b"%PDF-" in data[:1024]:
        return "pdf"
    if data[:8] == _CFB:
        # An encrypted .docx or .pptx is a compound file with streams named
        # "EncryptionInfo" and "EncryptedPackage" (MS-OFFCRYPTO 2.3.4.4); the
        # names are stored in UTF-16.
        return "encrypted" if "EncryptionInfo".encode("utf-16-le") in data else "old_office"
    if data[:4] != b"PK\x03\x04":
        return "unknown"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as package:
            types = package.read("[Content_Types].xml").decode("utf-8", "replace").lower()
    except Exception:  # untrusted bytes: not a ZIP we can read
        return "unknown"
    if any(kind in types for kind in _WORD_MAIN):
        return "docx"
    if any(kind in types for kind in _SLIDES_MAIN):
        return "pptx"
    if "officedocument" in types or "application/vnd.ms-" in types:
        return "office_other"
    return "unknown"


Outcome = Literal["checked", "damaged"]

#: A Word document longer than this with no heading style fails
#: ``no_headings``; shorter ones (a note, a one-part form) do not need any.
HEADINGS_MIN_WORDS = 400


@dataclass(frozen=True)
class OfficeCheck:
    """What the checks found in one Word or PowerPoint file."""

    outcome: Outcome
    #: Failed checks, in report order (``checks_for``).
    failed: tuple[FailedCheck, ...] = ()
    #: Slides in a PowerPoint file; None for a Word file (Word does not
    #: store a reliable page count) or when not read.
    page_count: int | None = None
    detail: str = field(default="", compare=False)

    @property
    def status(self) -> Literal["mostly_sure", "not_sure"]:
        """Mostly sure when a check that proves a barrier failed (``COUNTED``)."""
        return "mostly_sure" if any(check in COUNTED for check in self.failed) else "not_sure"


#: The checks a Word file gets, in the report's order: the ones that make a
#: file "Mostly sure" first, then the possible problems.
WORD_CHECKS: tuple[FailedCheck, ...] = (
    "no_alt_text",
    "table_no_header",
    "no_headings",
    "no_language",
    "skipped_heading_level",
    "unclear_link_text",
    "no_title",
)
SLIDES_CHECKS: tuple[FailedCheck, ...] = (
    "no_alt_text",
    "slide_no_title",
    "table_no_header",
    "no_language",
    "unclear_link_text",
    "no_title",
)
#: Checks whose failure makes a Word or PowerPoint file "Mostly sure".
COUNTED: frozenset[str] = frozenset(
    {"no_alt_text", "table_no_header", "slide_no_title", "no_headings", "no_language"}
)


def checks_for(checked_as: CheckedAs | None) -> tuple[FailedCheck, ...]:
    """Every check that ran on a file read as ``checked_as``, in report order."""
    if checked_as == "pdf":
        return ALL_CHECKS
    if checked_as == "docx":
        return WORD_CHECKS
    if checked_as == "pptx":
        return SLIDES_CHECKS
    return ()


def counts(checked_as: CheckedAs | None, check: str) -> bool:
    """Whether failing ``check`` makes a file read as ``checked_as`` "Mostly sure".

    Every PDF check does (pdf_check.py); of the Word and PowerPoint checks,
    only ``COUNTED``.
    """
    return checked_as == "pdf" or check in COUNTED


# ---------------------------------------------------------------------------
# Reading the package


_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
_V = "urn:schemas-microsoft-com:vml"
_O = "urn:schemas-microsoft-com:office:office"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
_CORE_PROPERTIES = "application/vnd.openxmlformats-package.core-properties+xml"
#: Office's "Mark as decorative" (an ``adec:decorative val="1"`` extension).
_DECORATIVE = "http://schemas.microsoft.com/office/drawing/2017/decorative"
#: graphicData kinds that are images, charts or diagrams, never text.
_NON_TEXT_GRAPHICS = (
    "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "http://schemas.openxmlformats.org/drawingml/2006/chart",
    "http://schemas.openxmlformats.org/drawingml/2006/diagram",
    "http://schemas.microsoft.com/office/drawing/2014/chartex",
)
_FILE_NAME = re.compile(r"^\S+\.(png|jpe?g|gif|bmp|tiff?|emf|wmf|svg|webp|heic)$", re.IGNORECASE)
#: Link words that do not say where a link goes, compared without case and
#: closing punctuation. Microsoft's guidance names "Click here", "See this
#: page", "Go here" and "Learn more".
_VAGUE_LINKS = frozenset(
    {
        "click here",
        "click",
        "here",
        "link",
        "this link",
        "more",
        "read more",
        "learn more",
        "more info",
        "more information",
        "this",
        "this page",
        "see this page",
        "go here",
    }
)
#: A web address as link text: with a scheme or "www.", or a bare domain
#: with or without a path ("hr.umich.edu/benefits"). Not an email address:
#: its words name the mailbox the link writes to.
_URL_TEXT = re.compile(r"^((https?://|www\.)\S+|([a-z0-9-]+\.)+[a-z]{2,}(/\S*)?)$", re.IGNORECASE)


def _q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _text(element: Any) -> str:
    return "".join(node.text or "" for node in element.iter(_q(_W, "t"), _q(_A, "t")) if node.text)


#: Names Office and Google give objects by themselves ("Picture 3",
#: "Google Shape;55;p13"): alt text that is one of these says nothing.
_DEFAULT_NAME = re.compile(r"^((picture|image|graphic)\s*\d+|google shape;[\w;]*)$", re.IGNORECASE)


def _has_alt(props: Any) -> bool:
    """A ``docPr``/``cNvPr`` that has alt text or is marked decorative.

    Alt text that is only a file name ("image1.png") or a default object
    name ("Picture 3") counts as none.
    """
    if props is None:
        return False
    for node in props.iter(_q(_DECORATIVE, "decorative")):
        if (node.get("val") or "").lower() in {"1", "true", "on"}:
            return True
    for attribute in ("descr", "title"):
        value = (props.get(attribute) or "").strip()
        if value and not _FILE_NAME.match(value) and not _DEFAULT_NAME.match(value):
            return True
    return False


def _unclear_link(text: str) -> bool:
    words = " ".join(text.split()).strip().rstrip(".:!").lower()
    return words in _VAGUE_LINKS or bool(_URL_TEXT.match(words))


def _unpacked_size_ok(data: bytes) -> bool:
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        return sum(info.file_size for info in package.infolist()) <= MAX_UNPACKED_BYTES


def check_office(data: bytes, kind: str) -> OfficeCheck:
    """Run every check for ``kind`` ("docx" or "pptx") on ``data``. Never raises."""
    try:
        if not _unpacked_size_ok(data):
            return OfficeCheck(outcome="damaged", detail="unpacks too large")
        if kind == "docx":
            return _check_word(data)
        if kind == "pptx":
            return _check_slides(data)
        return OfficeCheck(outcome="damaged", detail=f"not word or powerpoint: {kind}")
    except Exception as exc:  # untrusted input, RecursionError included: "damaged"
        return OfficeCheck(outcome="damaged", detail=type(exc).__name__)


def _ordered(failed: set[str], order: tuple[FailedCheck, ...]) -> tuple[FailedCheck, ...]:
    return tuple(check for check in order if check in failed)


# ---------------------------------------------------------------------------
# Word


def _check_word(data: bytes) -> OfficeCheck:
    from docx.package import Package

    # Package.open, not docx.Document: Document refuses a macro-enabled
    # file or a template, which hold the same parts.
    package = Package.open(io.BytesIO(data))
    part = package.main_document_part
    body = part.document.element.body
    _drop_fallbacks(body)
    failed: set[str] = set()

    if not _core_title(package):
        failed.add("no_title")
    if not _word_has_language(part, body):
        failed.add("no_language")
    if _word_images_without_alt(body):
        failed.add("no_alt_text")
    if _word_tables_without_header(body):
        failed.add("table_no_header")

    levels = _word_heading_levels(part, body)
    words = len(_text(body).split())
    if not levels and words > HEADINGS_MIN_WORDS:
        failed.add("no_headings")
    if any(level > before + 1 for before, level in itertools.pairwise(levels)):
        failed.add("skipped_heading_level")
    if any(_unclear_link(_text(link)) for link in body.iter(_q(_W, "hyperlink"))):
        failed.add("unclear_link_text")
    return OfficeCheck(outcome="checked", failed=_ordered(failed, WORD_CHECKS))


def _core_title(package: Any) -> str:
    """The Title document property, or "" when the file has none.

    Read from the core properties part itself: python-docx and python-pptx
    make up a default one ("Word Document", "PowerPoint Presentation") for a
    file that has none, as every Google export does.
    """
    for part in package.iter_parts():
        if part.content_type == _CORE_PROPERTIES:
            # python-docx's part holds a CoreProperties; python-pptx's part is one.
            properties = getattr(part, "core_properties", part)
            return (properties.title or "").strip()
    return ""


def _drop_fallbacks(root: Any) -> None:
    """Remove ``mc:Fallback`` copies (in memory only).

    Word saves a shape or text box twice, as DrawingML and as an older VML
    copy for old readers (``mc:AlternateContent``). Readers use the first;
    checking the copy too would count its tables twice and its pictures,
    which carry no alt text of their own, as missing it.
    """
    for fallback in list(root.iter(_q(_MC, "Fallback"))):
        parent = fallback.getparent()
        if parent is not None:
            parent.remove(fallback)


def _word_has_language(part: Any, body: Any) -> bool:
    """A ``w:lang`` with a value in the style defaults, any style, or any run."""
    roots = [body]
    styles = getattr(part, "_styles_part", None) or _styles_part(part)
    if styles is not None:
        roots.append(styles.element)
    for root in roots:
        for node in root.iter(_q(_W, "lang")):
            if any((node.get(_q(_W, name)) or "").strip() for name in ("val", "eastAsia", "bidi")):
                return True
    return False


def _styles_part(part: Any) -> Any:
    try:
        return part.part_related_by(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
        )
    except KeyError:
        return None


def _word_images_without_alt(body: Any) -> bool:
    """A picture, chart, diagram or VML image in the body with no alt text."""
    for wrapper in (*body.iter(_q(_WP, "inline")), *body.iter(_q(_WP, "anchor"))):
        uris = {node.get("uri") for node in wrapper.iter(_q(_A, "graphicData"))}
        if not uris.intersection(_NON_TEXT_GRAPHICS):
            # Only text boxes and plain shapes: text, or nothing to describe.
            continue
        if not _has_alt(wrapper.find(_q(_WP, "docPr"))):
            return True
    # Older VML pictures (Word 2003 and earlier files saved again as .docx).
    for image in body.iter(_q(_V, "imagedata")):
        shape = image.getparent()
        if shape is None or shape.find(_q(_V, "textbox")) is not None:
            continue
        alt = (shape.get("alt") or image.get(_q(_O, "title")) or "").strip()
        if not alt or _FILE_NAME.match(alt):
            return True
    return False


def _word_tables_without_header(body: Any) -> bool:
    for table in body.iter(_q(_W, "tbl")):
        rows = table.findall(_q(_W, "tr"))
        if len(rows) < 2 or max(len(row.findall(_q(_W, "tc"))) for row in rows) < 2:
            continue
        if not (_word_look_first_row(table) or _word_repeats_first_row(rows[0])):
            return True
    return False


def _on(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "on"}


def _word_look_first_row(table: Any) -> bool:
    """The "Header Row" table style option: ``firstRow``, or bit 0x0020 of the older hex ``val``."""
    look = table.find(f"{_q(_W, 'tblPr')}/{_q(_W, 'tblLook')}")
    if look is None:
        return False
    first = look.get(_q(_W, "firstRow"))
    if first is not None:
        return _on(first)
    try:
        return bool(int(look.get(_q(_W, "val")) or "0", 16) & 0x0020)
    except ValueError:
        return False


def _word_repeats_first_row(row: Any) -> bool:
    """ "Repeat as header row" on the first row (``w:tblHeader``, on unless val is off)."""
    marker = row.find(f"{_q(_W, 'trPr')}/{_q(_W, 'tblHeader')}")
    if marker is None:
        return False
    value = marker.get(_q(_W, "val"))
    return value is None or _on(value)


def _word_heading_levels(part: Any, body: Any) -> list[int]:
    """The level (1-9) of every heading paragraph with text, in order.

    A heading is a paragraph whose style is a built-in heading ("heading 1"
    to "heading 9") or that has an outline level, set on the paragraph or
    on its style (or a style it is based on). Title and body text are not.
    """
    styles = _style_levels(part)
    levels: list[int] = []
    for paragraph in body.iter(_q(_W, "p")):
        props = paragraph.find(_q(_W, "pPr"))
        level = None
        if props is not None:
            outline = props.find(_q(_W, "outlineLvl"))
            style = props.find(_q(_W, "pStyle"))
            if outline is not None:
                level = _outline(outline.get(_q(_W, "val")))
            elif style is not None:
                level = styles.get(style.get(_q(_W, "val")) or "")
        if level is not None and _text(paragraph).strip():
            levels.append(level)
    return levels


def _outline(value: str | None) -> int | None:
    """``w:outlineLvl`` 0-8 is heading level 1-9; 9 is body text."""
    try:
        number = int(value or "")
    except ValueError:
        return None
    return number + 1 if 0 <= number <= 8 else None


def _style_levels(part: Any) -> dict[str, int]:
    """Each paragraph style's heading level, following ``basedOn``."""
    styles = _styles_part(part)
    if styles is None:
        return {}
    own: dict[str, int | None] = {}
    based: dict[str, str] = {}
    for style in styles.element.iter(_q(_W, "style")):
        style_id = style.get(_q(_W, "styleId")) or ""
        name = style.find(_q(_W, "name"))
        named = re.fullmatch(
            r"heading ([1-9])",
            ((name.get(_q(_W, "val")) if name is not None else "") or "").lower(),
        )
        outline = style.find(f"{_q(_W, 'pPr')}/{_q(_W, 'outlineLvl')}")
        if outline is not None:
            own[style_id] = _outline(outline.get(_q(_W, "val")))
        elif named:
            own[style_id] = int(named.group(1))
        parent = style.find(_q(_W, "basedOn"))
        if parent is not None:
            based[style_id] = parent.get(_q(_W, "val")) or ""
    levels: dict[str, int] = {}
    for style_id in {*own, *based}:
        seen: set[str] = set()
        current = style_id
        while current and current not in seen:
            seen.add(current)
            if current in own:
                level = own[current]
                if level is not None:
                    levels[style_id] = level
                break
            current = based.get(current, "")
    return levels


# ---------------------------------------------------------------------------
# PowerPoint


_TITLE_PLACEHOLDERS = frozenset({"title", "ctrTitle"})
_TABLE_GRAPHIC = "http://schemas.openxmlformats.org/drawingml/2006/table"


def _check_slides(data: bytes) -> OfficeCheck:
    from pptx.package import Package

    # Package.open, not pptx.Presentation: the same parts, without
    # refusing a slide show (.ppsx) or a template.
    package = Package.open(io.BytesIO(data))
    presentation = package.main_document_part.presentation
    failed: set[str] = set()

    if not _core_title(package):
        failed.add("no_title")
    if not _slides_have_language(package):
        failed.add("no_language")
    slides = list(presentation.slides)
    for slide in slides:
        tree = slide.shapes._spTree
        _drop_fallbacks(tree)
        if not _slide_has_title(tree):
            failed.add("slide_no_title")
        if _slide_images_without_alt(tree):
            failed.add("no_alt_text")
        if _slide_tables_without_header(tree):
            failed.add("table_no_header")
        if _slide_has_unclear_link(tree):
            failed.add("unclear_link_text")
    return OfficeCheck(
        outcome="checked", failed=_ordered(failed, SLIDES_CHECKS), page_count=len(slides)
    )


def _slide_has_title(tree: Any) -> bool:
    """A title placeholder (``title``, ``ctrTitle``) holding text. Microsoft:
    "All slides have titles"; a title moved off the slide still counts."""
    for shape in tree.iter(_q(_P, "sp")):
        placeholder = shape.find(f"{_q(_P, 'nvSpPr')}/{_q(_P, 'nvPr')}/{_q(_P, 'ph')}")
        if (
            placeholder is not None
            and placeholder.get("type") in _TITLE_PLACEHOLDERS
            and _text(shape).strip()
        ):
            return True
    return False


def _slide_images_without_alt(tree: Any) -> bool:
    """A picture, chart or diagram on the slide with no alt text.

    A group with alt text covers what is inside it. Tables, text and
    plain shapes are not images (see the module docstring).
    """
    covered = {
        id(node)
        for group in tree.iter(_q(_P, "grpSp"))
        if _has_alt(group.find(f"{_q(_P, 'nvGrpSpPr')}/{_q(_P, 'cNvPr')}"))
        for node in group.iter()
    }
    for picture in tree.iter(_q(_P, "pic")):
        if id(picture) in covered:
            continue
        if not _has_alt(picture.find(f"{_q(_P, 'nvPicPr')}/{_q(_P, 'cNvPr')}")):
            return True
    for frame in tree.iter(_q(_P, "graphicFrame")):
        if id(frame) in covered:
            continue
        uris = {node.get("uri") for node in frame.iter(_q(_A, "graphicData"))}
        if not uris.intersection(_NON_TEXT_GRAPHICS):
            continue
        if not _has_alt(frame.find(f"{_q(_P, 'nvGraphicFramePr')}/{_q(_P, 'cNvPr')}")):
            return True
    return False


def _slide_tables_without_header(tree: Any) -> bool:
    """A table of 2+ rows and 2+ columns without "Header Row" (``firstRow``)."""
    for table in tree.iter(_q(_A, "tbl")):
        rows = table.findall(_q(_A, "tr"))
        if len(rows) < 2 or max(len(row.findall(_q(_A, "tc"))) for row in rows) < 2:
            continue
        props = table.find(_q(_A, "tblPr"))
        if props is None or not _on(props.get("firstRow")):
            return True
    return False


def _slide_has_unclear_link(tree: Any) -> bool:
    """A link whose words, read together, are a web address or "click here".

    PowerPoint and Google split one link into several runs; consecutive
    runs of a paragraph with the same link are read as one.
    """
    for paragraph in tree.iter(_q(_A, "p")):
        current: str | None = None
        words: list[str] = []
        for run in paragraph.findall(_q(_A, "r")):
            link = run.find(f"{_q(_A, 'rPr')}/{_q(_A, 'hlinkClick')}")
            target = link.get(_q(_R, "id")) if link is not None else None
            if target != current and current and _unclear_link("".join(words)):
                return True
            if target != current:
                words = []
            current = target
            if target:
                words.append(_text(run))
        if current and _unclear_link("".join(words)):
            return True
    return False


def _slides_have_language(package: Any) -> bool:
    """A ``lang`` on any text run or text default, in the slides, layouts,
    masters or the presentation's own defaults."""
    for part in package.iter_parts():
        if "presentationml" not in part.content_type:
            continue
        element = getattr(part, "_element", None)
        if element is None:
            continue
        for node in element.iter(_q(_A, "rPr"), _q(_A, "endParaRPr"), _q(_A, "defRPr")):
            if (node.get("lang") or "").strip():
                return True
    return False
