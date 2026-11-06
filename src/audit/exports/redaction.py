"""Best-effort removal of private details from a downloaded report.

Why this exists: a scan of a site behind a sign-in (one-step or two-step)
saves page content that can hold a person's own data: a filled-in form
field, an email address in a greeting, an account number in a link. The
report keeps that evidence so a reviewer can see exactly what was found.
A file that leaves Axcess, though, is often sent to a developer or a vendor
who needs the fix, not the data. This module makes a redacted copy of an
export for that hand-off.

Scope, as decided on the task board (Asana 1218150268010184):

* **Export only.** Scanning, the stored evidence and the in-app display are
  unchanged. Only the bytes of a requested download are rewritten.
* **Rendered output, not the collector.** The audit report and the workbook
  read much of their text straight from the database (issue details,
  locations, review notes), so redacting :class:`ExportScan` alone would
  miss it. Instead every format is parsed after rendering and each text
  value (CSV cell, JSON string, workbook cell, Markdown line) is redacted.
  That covers every field whatever its source, and keeps each file valid.
* **Keep what a fix needs.** Element locators (CSS selectors), check names,
  WCAG criteria, page paths and the element's code (HTML) structure stay.
  Only the values inside them are replaced: ``value="jane@x.com"`` becomes
  ``value="[redacted]"``, a ``?token=`` query value becomes ``[redacted]``.
  Element locators are left whole even when they quote a value, because a
  changed locator no longer finds the element.

What it cannot do is listed in :data:`REDACTION_NOTICE` and written into
every redacted file: names and other free text are not recognized, text
inside images is not changed, and a link back to Axcess opens the full
report. The notice is never dropped to make a file shorter.

The ``[redacted …]`` markers use square brackets on purpose. The protected
report's ``<redacted>`` markers would be read as HTML tags by a Markdown
viewer and disappear, hiding the fact that anything was removed.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote_plus

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from audit.protected.redaction import is_sensitive_key

REDACTED = "[redacted]"
REDACTED_EMAIL = "[redacted email]"
REDACTED_PHONE = "[redacted phone number]"
REDACTED_ID_NUMBER = "[redacted ID number]"
REDACTED_CARD = "[redacted card number]"
REDACTED_ID = "[redacted ID]"

REDACTION_TITLE = "REDACTED COPY: LIKELY PRIVATE DETAILS REMOVED"
#: Plain-language limits of the redaction, written into every redacted file.
#: Keep each fact; shorten the words, never the list (AGENTS.md, Interface
#: language rule 4).
REDACTION_NOTICE = (
    "Axcess replaced likely private details with [redacted] in this file: "
    "form field values, email addresses, phone numbers, card and ID numbers, "
    "and secret codes (tokens) in web addresses and page code. "
    "This is best effort. It can miss names and other private text, and it "
    "does not change text inside images. Screenshots are left out. Links back "
    "to Axcess open the full report, which is not redacted. "
    "Check the file before you share it."
)
#: The added CSV column's header carries the whole notice once, because a
#: CSV has no place for a preamble that importers would not read as a row.
REDACTION_CSV_COLUMN = f"Axcess redaction: {REDACTION_NOTICE}"
REDACTION_CSV_VALUE = "Redacted (best effort)"

# --- Text patterns ---------------------------------------------------------

# A URL ends at whitespace, a quote, an angle bracket, or the brackets that
# close a Markdown link, so "[text](https://x/?a=1)" keeps its ")".
_URL = re.compile(r"https?://[^\s\"'<>()\[\]]+", re.IGNORECASE)
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SSN = re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])")
_PHONE = re.compile(
    r"(?<![\d.-])(?:\+?1[ .-]?)?(?:\(\d{3}\)\s?|\d{3}[ .-])\d{3}[ .-]\d{4}(?!\d|[.-]\d)"
)
# Not after or before a decimal point, so a long decimal such as a
# confidence score is never read as a card number.
_CARD_CANDIDATE = re.compile(r"(?<![\d.,-])\d(?:[ -]?\d){12,18}(?!\d|[.,]\d|-)")
_UUID = re.compile(
    r"(?i)(?<![0-9a-f-])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f-])"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/-]{8,}=*")
_HEADER = re.compile(
    r"(?im)\b((?:authorization|cookie|set-cookie|x-api-key|x-auth-token|x-csrf-token|"
    r"api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret)"
    r"\s*[:=]\s*)([^\s\"'<>,;&]+)"
)
_TOKEN_CANDIDATE = re.compile(
    r"(?<![A-Za-z0-9_+/=-])[A-Za-z0-9_+/-]{32,}={0,2}(?![A-Za-z0-9_+/=-])"
)
_ALNUM_RUN = re.compile(r"[A-Za-z0-9]+")

# --- Element code (HTML) patterns --------------------------------------------

# One attribute with a value. The value may be double-quoted, single-quoted,
# quoted with escaped quotes (HTML inside a JSON string), or bare. The
# closing quote must match the opening one.
_ATTRIBUTE = re.compile(
    r"(?P<name>(?<![\w:-])[A-Za-z_:][\w:.-]*)(?P<eq>\s*=\s*)"
    r"(?:(?P<q>\\?[\"'])(?P<val>.*?)(?P=q)"
    # Element code cut short inside a value: the quote never closes.
    r"|(?P<oq>\\?[\"'])(?P<open>[^\"'\\]*)\Z"
    r"|(?P<bare>[^\s>\"'\\`]+))",
    re.DOTALL,
)
# An opening tag. Element code in a report is often cut short, so a tag
# may end at the end of the text instead of at ">".
_TAG = re.compile(r"<[A-Za-z][^<>]*(?:>|$)")
_TEXTAREA = re.compile(r"(?is)(<textarea\b[^>]*>)(.*?)(</textarea\s*>)")
# Attributes whose value is a link: keep the link, redact its secrets.
_URL_ATTRIBUTES = frozenset({"href", "src", "action", "formaction", "poster", "cite", "data"})
# Attributes that are filled-in or secret by nature.
_VALUE_ATTRIBUTES = frozenset({"value", "data-value", "nonce", "integrity"})


def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def _redact_card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return REDACTED_CARD if 13 <= len(digits) <= 19 and _luhn_ok(digits) else match.group(0)


def _redact_token(match: re.Match[str]) -> str:
    """Replace a long secret-looking string, but not a hash or a slug.

    A token mixes upper case, lower case and digits, with a long unbroken
    run. A page slug ("2026-annual-report-for-the-board") is split by
    hyphens into short words, and Axcess's own evidence hashes are lower-case
    hex; both are kept, because a developer needs them to find the page or
    the screenshot.
    """

    text = match.group(0)
    has_upper = any(c.isupper() for c in text)
    has_lower = any(c.islower() for c in text)
    has_digit = any(c.isdigit() for c in text)
    longest_run = max((len(run) for run in _ALNUM_RUN.findall(text)), default=0)
    if has_upper and has_lower and has_digit and longest_run >= 24:
        return REDACTED
    return text


def _redact_patterns(text: str) -> str:
    """Redact identifiers and secrets in plain text (no URL handling)."""

    result = _HEADER.sub(lambda m: f"{m.group(1)}{REDACTED}", text)
    result = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", result)
    result = _JWT.sub(REDACTED, result)
    result = _EMAIL.sub(REDACTED_EMAIL, result)
    result = _UUID.sub(REDACTED_ID, result)
    result = _SSN.sub(REDACTED_ID_NUMBER, result)
    result = _CARD_CANDIDATE.sub(_redact_card, result)
    result = _PHONE.sub(REDACTED_PHONE, result)
    return _TOKEN_CANDIDATE.sub(_redact_token, result)


def _redact_query(query: str) -> str:
    """Redact query or fragment values, keeping every name and the encoding.

    The string is edited in place rather than parsed and re-encoded, so a
    harmless link keeps its exact bytes and still matches the page URL in
    the report.
    """

    parts = []
    for part in query.split("&"):
        name, sep, value = part.partition("=")
        if not sep:
            parts.append(_redact_patterns(part))
            continue
        decoded = unquote_plus(value)
        if value and (is_sensitive_key(name) or _redact_patterns(decoded) != decoded):
            parts.append(f"{name}={REDACTED}")
        else:
            parts.append(part)
    return "&".join(parts)


def redact_url(url: str) -> str:
    """Keep a link usable for finding the page, without its secrets.

    The scheme, host and path stay, so the developer can open the page
    template. Removed: a user name or password before the host, secret or
    identifying query values, a fragment that carries values (a sign-in
    callback's ``#access_token=``), and identifiers inside the path, such as
    an email address or a record's UUID (``/orders/[redacted ID]/edit``).
    """

    match = re.match(r"(?i)^(https?://)([^/?#]*)(.*)$", url)
    if match is None:
        # A relative link from element code, such as "/account?token=...".
        scheme, authority, rest = "", "", url
    else:
        scheme, authority, rest = match.groups()
    if "@" in authority:
        authority = f"{REDACTED}@{authority.rsplit('@', 1)[1]}"
    path, hash_sep, fragment = rest.partition("#")
    path, query_sep, query = path.partition("?")
    path = _redact_patterns(path)
    if query_sep:
        query = _redact_query(query)
    if hash_sep:
        fragment = _redact_query(fragment) if "=" in fragment else _redact_patterns(fragment)
    return f"{scheme}{authority}{path}{query_sep}{query}{hash_sep}{fragment}"


def _redact_attribute(match: re.Match[str]) -> str:
    name = match.group("name")
    lowered = name.lower()
    quote = match.group("q")
    if match.group("oq") is not None:
        raw = match.group("open")
    else:
        raw = match.group("val") if quote is not None else match.group("bare")
    if not raw:
        return match.group(0)
    if lowered in _VALUE_ATTRIBUTES or is_sensitive_key(lowered):
        replacement = REDACTED
    elif lowered in _URL_ATTRIBUTES:
        replacement = redact_url(raw)
    else:
        return match.group(0)
    if match.group("oq") is not None:
        return f"{name}{match.group('eq')}{match.group('oq')}{replacement}"
    if quote is None:
        return f'{name}{match.group("eq")}"{replacement}"'
    return f"{name}{match.group('eq')}{quote}{replacement}{quote}"


def redact_text(text: str) -> str:
    """Redact one text value: a cell, a JSON string, or a Markdown line.

    Order matters. Element code comes first, so a form field's ``value`` is
    replaced whole before the pattern pass could leave half of it. Links
    come next, so a token in a query is redacted with its name kept. The
    remaining text then gets the identifier patterns. Every marker is
    immune to every pattern, so running this twice changes nothing.
    """

    if not text:
        return text
    result = _TEXTAREA.sub(
        lambda m: f"{m.group(1)}{REDACTED if m.group(2).strip() else m.group(2)}{m.group(3)}",
        text,
    )
    if "<" in result and "=" in result:
        # Attributes only inside a tag: "?value=x" in a sentence's link is a
        # query, handled by the link pass, not an attribute.
        result = _TAG.sub(lambda m: _ATTRIBUTE.sub(_redact_attribute, m.group(0)), result)
    result = _URL.sub(lambda m: redact_url(m.group(0)), result)
    return _redact_patterns(result)


def redact_field(value: str) -> str:
    """Redact a field that may itself hold JSON (stored check evidence).

    Some fields, such as the rule check's evidence, are JSON text inside a
    cell or inside the JSON export. Redacting that as plain text would put
    unescaped quotes into it and break it, so it is parsed, redacted value
    by value, and written back.
    """

    stripped = value.lstrip()
    if stripped[:1] in {"{", "["}:
        try:
            parsed = json.loads(value)
        except ValueError:
            return redact_text(value)
        return json.dumps(redact_json_value(parsed), ensure_ascii=False)
    return redact_text(value)


def redact_json_value(value: Any) -> Any:
    """Redact every string in a JSON value; keys and numbers are kept."""

    if isinstance(value, str):
        return redact_field(value)
    if isinstance(value, list):
        return [redact_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_json_value(item) for key, item in value.items()}
    return value


# --- Formats -----------------------------------------------------------------


def _redact_markdown(rendered: str) -> str:
    notice = f"> **{REDACTION_TITLE}**\n>\n> {REDACTION_NOTICE}\n\n"
    return notice + "\n".join(redact_text(line) for line in rendered.split("\n"))


def _redact_json(rendered: str) -> str:
    payload = json.loads(rendered)
    if not isinstance(payload, dict):
        raise ValueError("Public JSON export must contain an object")
    redacted = redact_json_value(payload)
    redacted["redaction_notice"] = {
        "label": REDACTION_TITLE,
        "redacted": True,
        "best_effort": True,
        "warning": REDACTION_NOTICE,
        "marker": REDACTED,
    }
    return json.dumps(redacted, indent=2, sort_keys=True, ensure_ascii=False)


def _redact_csv(rendered: str) -> str:
    """Redact every cell and add one column that says the file is redacted.

    A new column, like the draft column, keeps the file rectangular and
    valid for importers, which can map or ignore it.
    """

    rows = list(csv.reader(io.StringIO(rendered, newline="")))
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    if not rows:
        writer.writerow([REDACTION_CSV_COLUMN])
        writer.writerow([REDACTION_CSV_VALUE])
        return output.getvalue()
    writer.writerow([*rows[0], REDACTION_CSV_COLUMN])
    for row in rows[1:]:
        writer.writerow([*(redact_field(cell) for cell in row), REDACTION_CSV_VALUE])
    return output.getvalue()


def _redact_workbook(rendered: bytes) -> bytes:
    """Redact every text cell and link, remove pictures, add a notice sheet.

    Pictures are screenshots of the page as the scanner saw it, and text in
    an image cannot be redacted, so they are removed rather than shipped.
    The route also renders a redacted workbook without them; this removal
    is the second line of defence.
    """

    workbook = load_workbook(io.BytesIO(rendered))
    for sheet in workbook.worksheets:
        # openpyxl has no public API for removing a sheet's pictures.
        sheet._images = []
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and not cell.value.startswith("="):
                    cell.value = redact_field(cell.value)
                elif isinstance(cell.value, str):
                    # A formula keeps its function call; only links and
                    # identifiers inside its quoted text are redacted.
                    cell.value = _URL.sub(lambda m: redact_url(m.group(0)), cell.value)
                if cell.hyperlink is not None and cell.hyperlink.target:
                    cell.hyperlink.target = redact_url(cell.hyperlink.target)
    notice = workbook.create_sheet("REDACTION NOTICE", 0)
    notice.sheet_view.showGridLines = False
    notice.sheet_properties.tabColor = "1F3B73"
    notice.merge_cells("A1:F1")
    notice["A1"] = REDACTION_TITLE
    notice["A1"].font = Font(bold=True, size=16, color="FFFFFF")
    notice["A1"].fill = PatternFill("solid", fgColor="1F3B73")
    notice["A1"].alignment = Alignment(vertical="center")
    notice.row_dimensions[1].height = 30
    notice["A3"] = "What changed"
    notice["A3"].font = Font(bold=True)
    notice.merge_cells("B3:F8")
    notice["B3"] = REDACTION_NOTICE
    notice["B3"].alignment = Alignment(wrap_text=True, vertical="top")
    notice.column_dimensions["A"].width = 18
    notice.column_dimensions["B"].width = 38
    for column in ("C", "D", "E", "F"):
        notice.column_dimensions[column].width = 14
    workbook.active = 0
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


_FORMAT_REDACTORS: dict[str, Callable[[Any], str | bytes]] = {
    "audit": _redact_markdown,
    "markdown": _redact_markdown,
    "json": _redact_json,
    "csv": _redact_csv,
    "jira": _redact_csv,
    "xlsx": _redact_workbook,
}


def redact_export(rendered: str | bytes, *, export_format: str) -> str | bytes:
    """Return a redacted copy of one rendered export, with its notice inside.

    Raises ``ValueError`` for a format this module does not know, so a new
    export format can never be served as "redacted" without being redacted.
    """

    redactor = _FORMAT_REDACTORS.get(export_format)
    if redactor is None:
        raise ValueError(f"Redaction is not available for the {export_format!r} format")
    if export_format == "xlsx":
        if not isinstance(rendered, bytes):
            raise TypeError("XLSX exports must be bytes")
    elif not isinstance(rendered, str):
        raise TypeError(f"{export_format} exports must be text")
    return redactor(rendered)
