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
  changed locator no longer finds the element. The redactor works on the
  finished file, where a locator is only text, so the route passes it the
  locators the scan recorded (:func:`scan_locators`) and those exact strings
  are held back from every pass. The same value anywhere else (element code,
  a note, a link) is still replaced. The notice says so, because a kept
  locator can quote a private value.
* **Evidence is redacted with its context, before text is made from it.**
  A form value is recognizable inside element code (``<textarea>``) or
  structured evidence (``{"name": "value", "value": ...}``), but not once a
  renderer has turned it into a sentence ("text area containing ..."). So a
  renderer that writes such sentences redacts an export-only copy of the
  evidence first (:func:`redact_evidence`), and the pass over the finished
  file stays as the net for everything else.

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
import html
import io
import json
import re
from collections.abc import Callable, Iterable
from functools import lru_cache
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
_NOTICE_WHAT = (
    "Axcess replaced likely private details with [redacted] in this file: "
    "form field values, email addresses, phone numbers, card and ID numbers, "
    "and secret codes (tokens) in web addresses and page code. "
    "This is best effort. It can miss names and other private text, and it "
    "does not change text inside images."
)
_NOTICE_LOCATORS = (
    "Element locators (CSS selectors) are kept whole, so that they still find "
    "the element, even when one quotes a value from the page."
)
_NOTICE_REST = (
    "Screenshots are left out. Links back "
    "to Axcess open the full report, which is not redacted. "
    "Check the file before you share it."
)
REDACTION_NOTICE = f"{_NOTICE_WHAT} {_NOTICE_LOCATORS} {_NOTICE_REST}"
#: The notice for a file that redacts inside element locators too. The fix
#: brief does (it tells the agent when a locator is no longer exact), so the
#: sentence about kept locators would be false there.
REDACTION_NOTICE_LOCATORS_REDACTED = f"{_NOTICE_WHAT} {_NOTICE_REST}"
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
    # Element code cut short inside a value: the quote never closes, so the
    # value is everything that is left. The alternative above has already
    # taken every value whose quote does close, so this one may hold the
    # other kind of quote (value="Jane's note) without ending early.
    r"|(?P<oq>\\?[\"'])(?P<open>.*)\Z"
    r"|(?P<bare>[^\s>\"'\\`]+))",
    re.DOTALL,
)
# An opening tag. A ">" inside a quoted value does not end it
# (title="a > b"). Element code in a report is often cut short, so a tag may
# end at the end of the text instead of at ">", and a quote that never closes
# runs to the end of the text too. The "+" after each repeat (possessive)
# means the pattern never gives characters back to try again: each piece is
# one maximal run, so a long text with many "<" is still read once.
_TAG = re.compile(r"<[A-Za-z](?:\"[^\"]*+(?:\"|\Z)|'[^']*+(?:'|\Z)|[^<>\"']++)*+(?:>|\Z)")
# A text box's typed text. Element code is often cut short, so a text box
# whose closing tag was cut off runs to the end of the text, and all of it is
# replaced: without the closing tag there is no telling where the typed text
# stops, and keeping it would leak it.
_TEXTAREA = re.compile(r"(?is)(<textarea\b[^>]*>)(.*?)(</textarea\s*>|\Z)")
# Attributes whose value is a link: keep the link, redact its secrets.
_URL_ATTRIBUTES = frozenset({"href", "src", "action", "formaction", "poster", "cite", "data"})
# Attributes that are filled-in or secret by nature.
_VALUE_ATTRIBUTES = frozenset({"value", "data-value", "nonce", "integrity"})
# The same attribute written as a locator-shaped label, as Alfa's structured
# target is shown: [value="..."], or [@value="..."] in an XPath. A locator the
# scan recorded is held back before this runs, so what is left is evidence,
# not a locator.
_BRACKET_ATTRIBUTE = re.compile(
    r"\[(?P<at>@?)(?P<name>[A-Za-z_:][\w:.-]*)(?P<op>[~|^$*]?=)"
    r"(?P<q>\\?[\"'])(?P<val>.*?)(?P=q)(?P<end>\s*[iIsS]?\])"
)
# An attribute inside structured evidence that is still JSON text: one that
# was cut short and no longer parses, or one quoted in a sentence. Parsed
# JSON is handled with its structure in :meth:`_Redactor.json_value`.
_JSON_ATTRIBUTE = re.compile(
    r"(?P<q>\\?\")name(?P=q)\s*:\s*(?P=q)(?P<name>[^\"\\]{1,80})(?P=q)\s*,\s*"
    r"(?P=q)value(?P=q)\s*:\s*(?P=q)(?P<val>(?:(?!(?P=q))\\.|(?!(?P=q)).)*)(?P<end>(?P=q)|\Z)",
    re.DOTALL,
)
# Where one piece of scanned content stops inside a longer text.
_FENCE = re.compile(r"^ {0,3}(?:> ?)*(?P<fence>`{3,}|~{3,})")
# A string in a spreadsheet formula. A quote inside it is written twice.
_FORMULA_STRING = re.compile(r'"((?:[^"]|"")*)"')
# Held-back locators are swapped for private-use characters while the passes
# run: no pattern matches them, and no page is likely to contain them.
_HOLD_OPEN = "\ue000"
_HOLD_CLOSE = "\ue001"
_HOLD_BASE = 0xE100
_HOLD_MAX = 0x1000
_HOLD = re.compile(f"{_HOLD_OPEN}(.){_HOLD_CLOSE}", re.DOTALL)
# A quick first look at a locator: could any pass above change it? Most
# locators ("main > div:nth-child(3) a.btn") cannot, and a scan can have
# thousands, so this spares running every pass on each. It must match
# whatever a pass could change. Matching too much only costs time; matching
# too little would let a locator be redacted, and
# ``test_a_locator_quoting_any_kind_of_private_value_is_kept`` fails then.
_MAY_CHANGE = re.compile(
    r"[@=<]|://|eyJ|[0-9A-Fa-f]{8}-|\d{3}-\d{2}-\d{4}|\d{3}[ .-]\d{4}|(?:\d[ -]?){13}"
    r"|[A-Za-z0-9_+/-]{32}|(?i:bearer|basic)\s"
)


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

    # The scheme's credential first: "Authorization: Bearer <token>" would
    # otherwise have only the word "Bearer" taken as the header's value,
    # leaving a token that is not a JWT behind.
    result = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    result = _HEADER.sub(lambda m: f"{m.group(1)}{REDACTED}", result)
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
        # A link copied out of element code separates its parts with
        # "&amp;", which leaves "amp;" on the front of the next name.
        key = name[4:] if name[:4].lower() == "amp;" else name
        if value and (is_sensitive_key(key) or _redact_patterns(decoded) != decoded):
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
        # Element code writes "&" as "&amp;". Read the link as the browser
        # would, so "?tab=2&amp;session_id=..." is seen as two parts, and
        # write it back escaped. A link with nothing to redact keeps its
        # exact characters.
        decoded = html.unescape(raw)
        replacement = redact_url(decoded)
        if replacement == decoded:
            return match.group(0)
        if decoded != raw:
            replacement = html.escape(replacement, quote=True)
    else:
        return match.group(0)
    if match.group("oq") is not None:
        return f"{name}{match.group('eq')}{match.group('oq')}{replacement}"
    if quote is None:
        return f'{name}{match.group("eq")}"{replacement}"'
    return f"{name}{match.group('eq')}{quote}{replacement}{quote}"


def _attribute_value(name: str, value: str) -> str | None:
    """A named attribute's value, redacted by what the attribute is.

    ``None`` means the name says nothing about the value, and the caller
    redacts it as ordinary text.
    """

    lowered = name.strip().lower()
    if not value.strip():
        return value
    if lowered in _VALUE_ATTRIBUTES or is_sensitive_key(lowered):
        return REDACTED
    if lowered in _URL_ATTRIBUTES:
        return redact_url(value)
    return None


def _redact_bracket_attribute(match: re.Match[str]) -> str:
    replacement = _attribute_value(match.group("name"), match.group("val"))
    if replacement is None:
        return match.group(0)
    quote = match.group("q")
    head = f"[{match.group('at')}{match.group('name')}{match.group('op')}"
    return f"{head}{quote}{replacement}{quote}{match.group('end')}"


def _redact_json_attribute(match: re.Match[str]) -> str:
    replacement = _attribute_value(match.group("name"), match.group("val"))
    if replacement is None or replacement == match.group("val"):
        return match.group(0)
    return (
        f"{match.group(0)[: match.start('val') - match.start()]}{replacement}{match.group('end')}"
    )


def _redact_textareas(text: str) -> str:
    return _TEXTAREA.sub(
        lambda m: f"{m.group(1)}{REDACTED if m.group(2).strip() else m.group(2)}{m.group(3)}",
        text,
    )


def redact_text(text: str) -> str:
    """Redact one text value: a cell, a JSON string, or a Markdown line.

    Order matters. Element code comes first, so a form field's ``value`` is
    replaced whole before the pattern pass could leave half of it. Links
    come next, so a token in a query is redacted with its name kept. The
    remaining text then gets the identifier patterns. Every marker is
    immune to every pattern, so running this twice changes nothing.

    Nothing is held back here: an element locator is redacted like any other
    text. :func:`redact_export` is the caller that keeps locators whole.
    """

    if not text:
        return text
    result = _redact_textareas(text)
    if "<" in result and "=" in result:
        # Attributes only inside a tag: "?value=x" in a sentence's link is a
        # query, handled by the link pass, not an attribute.
        result = _TAG.sub(lambda m: _ATTRIBUTE.sub(_redact_attribute, m.group(0)), result)
    if "[" in result and "=" in result:
        result = _BRACKET_ATTRIBUTE.sub(_redact_bracket_attribute, result)
    if '"name' in result and '"value' in result:
        result = _JSON_ATTRIBUTE.sub(_redact_json_attribute, result)
    result = _URL.sub(lambda m: redact_url(m.group(0)), result)
    return _redact_patterns(result)


def _is_structured(value: str) -> bool:
    """Whether a stored target is structured evidence (JSON), not a locator."""

    if value.lstrip()[:1] not in {"{", "["}:
        return False
    try:
        parsed = json.loads(value)
    except ValueError:
        return False
    return isinstance(parsed, (dict, list))


def scan_locators(findings: Iterable[Any]) -> frozenset[str]:
    """The element locators a scan recorded, for :func:`redact_export` to keep.

    A locator is the ``target_selector`` a check saved as text (a CSS
    selector or an XPath). Structured targets (the JSON a rule check such as
    Alfa saves) are evidence, not locators: their values are redacted, and
    the label made from them is too. ``target_display`` counts only when it
    is the same text as the locator; otherwise it is a label built from
    evidence.
    """

    locators: set[str] = set()
    for finding in findings:
        selector = str(getattr(finding, "target_selector", "") or "")
        if selector and not _is_structured(selector):
            locators.add(selector)
    return frozenset(locators)


@lru_cache(maxsize=65536)
def _redaction_changes(locator: str) -> bool:
    """Whether a locator would come out of :func:`redact_text` changed.

    Remembered, because one scan's locators are asked about once for each
    file: the Export panel sizes every format before a download.
    """

    may_change = _MAY_CHANGE.search(locator) or _HEADER.search(locator)
    return may_change is not None and redact_text(locator) != locator


# A field name is asked about once for every value in the JSON file.
_is_secret_field = lru_cache(maxsize=4096)(is_sensitive_key)


class _Redactor:
    """One redaction run over a file, holding back the locators to keep."""

    def __init__(self, locators: Iterable[str] = ()) -> None:
        # Only locators that redaction would change need holding back, and
        # the longest first, so a locator inside a longer one cannot split it.
        kept = sorted(
            {locator for locator in locators if locator and _redaction_changes(locator)},
            key=len,
            reverse=True,
        )
        self._kept = re.compile("|".join(re.escape(locator) for locator in kept)) if kept else None

    def text(self, text: str) -> str:
        """Redact one text value, leaving each known locator as it is."""

        if not text or self._kept is None or _HOLD_OPEN in text:
            # A text that already holds the stand-in character cannot be
            # told apart from one we put there, so nothing is held back.
            return redact_text(text)
        held: list[str] = []

        def hold(match: re.Match[str]) -> str:
            if len(held) >= _HOLD_MAX:
                return match.group(0)
            held.append(match.group(0))
            return f"{_HOLD_OPEN}{chr(_HOLD_BASE + len(held) - 1)}{_HOLD_CLOSE}"

        marked = self._kept.sub(hold, text)
        if not held:
            return redact_text(text)

        def restore(match: re.Match[str]) -> str:
            index = ord(match.group(1)) - _HOLD_BASE
            return held[index] if 0 <= index < len(held) else match.group(0)

        return _HOLD.sub(restore, redact_text(marked))

    def block(self, text: str, *, by_line: bool) -> str:
        """Redact a text of several lines, one piece of scanned content at a time.

        A fenced block (three or more backticks or tildes) is one piece, so a
        text box that spans its lines is seen whole, and element code that was
        cut short cannot take the text after the fence with it. Outside a
        fence, ``by_line`` says how the rest is read. A Markdown report is
        read a line at a time, as it is written; a text box that starts on
        one line and ends on a later one is still redacted, up to the next
        blank line. A cell is read as one piece.
        """

        if "\n" not in text:
            return self.text(text)
        lines = text.split("\n")
        out: list[str] = []
        loose: list[str] = []

        def flush() -> None:
            if not loose:
                return
            if by_line:
                for paragraph in _paragraphs(loose):
                    joined = "\n".join(paragraph)
                    if len(paragraph) > 1 and "<textarea" in joined.lower():
                        paragraph = _redact_textareas(joined).split("\n")
                    out.extend(self.text(line) for line in paragraph)
            else:
                out.append(self.text("\n".join(loose)))
            loose.clear()

        index = 0
        while index < len(lines):
            opening = _FENCE.match(lines[index])
            close = _fence_end(lines, index, opening.group("fence")) if opening else None
            if close is None:
                loose.append(lines[index])
                index += 1
                continue
            flush()
            out.append(self.text(lines[index]))
            if close > index + 1:
                out.append(self.text("\n".join(lines[index + 1 : close])))
            out.append(lines[close])
            index = close + 1
        flush()
        return "\n".join(out)

    def field(self, value: str) -> str:
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
                return self.block(value, by_line=False)
            if isinstance(parsed, (dict, list)):
                return json.dumps(self.json_value(parsed), ensure_ascii=False)
        return self.block(value, by_line=False)

    def json_value(self, value: Any) -> Any:
        """Redact a JSON value; keys and numbers are kept.

        Structure is used where it says what a string is. A node with a
        ``name`` and a ``value`` is an attribute, so ``value`` is redacted by
        the attribute's name (a form field's ``value``, a link's ``href``). A
        text box's child text is what a person typed. A field whose own name
        is a secret's (``token``, ``password``) loses its value. Without
        this, ``"private_suffix"`` in a structured ``value`` attribute is
        just a word, and no pattern would catch it.
        """

        if isinstance(value, str):
            return self.field(value)
        if isinstance(value, list):
            return [self.json_value(item) for item in value]
        if not isinstance(value, dict):
            return value
        name = value.get("name")
        is_attribute = isinstance(name, str) and isinstance(value.get("value"), str)
        is_text_box = isinstance(name, str) and name.lower() == "textarea"
        out: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(item, str) and item.strip():
                by_name = (
                    _attribute_value(str(name), item) if is_attribute and key == "value" else None
                )
                if by_name is not None:
                    out[key] = by_name
                    continue
                if _is_secret_field(str(key)):
                    out[key] = REDACTED
                    continue
            if is_text_box and key == "children" and isinstance(item, list):
                out[key] = [_redact_typed_text(self.json_value(child)) for child in item]
                continue
            out[key] = self.json_value(item)
        return out


def _redact_typed_text(node: Any) -> Any:
    """A text box's child text node, with what was typed replaced."""

    if isinstance(node, dict) and node.get("type") == "text":
        data = node.get("data")
        if isinstance(data, str) and data.strip():
            return {**node, "data": REDACTED}
    return node


def _paragraphs(lines: list[str]) -> list[list[str]]:
    """Runs of lines, split after each blank line; every line is kept."""

    runs: list[list[str]] = [[]]
    for line in lines:
        if not line.strip():
            runs.append([line])
            runs.append([])
        else:
            runs[-1].append(line)
    return [run for run in runs if run]


def _fence_end(lines: list[str], start: int, fence: str) -> int | None:
    """The line that closes the fence opened at ``start``, if one does."""

    for index in range(start + 1, len(lines)):
        closing = _FENCE.match(lines[index])
        if (
            closing
            and closing.group("fence")[0] == fence[0]
            and len(closing.group("fence")) >= len(fence)
            and not lines[index][closing.end() :].strip()
        ):
            return index
    return None


_PLAIN = _Redactor()


def redact_field(value: str) -> str:
    """Redact a field that may itself hold JSON; no locator is held back."""

    return _PLAIN.field(value)


def redact_json_value(value: Any) -> Any:
    """Redact a JSON value with its structure; no locator is held back."""

    return _PLAIN.json_value(value)


def redact_evidence(finding: dict[str, Any]) -> dict[str, Any]:
    """An export-only copy of one stored occurrence, its evidence redacted.

    For a renderer that writes a sentence from evidence. The written report
    turns ``<textarea>My loan was declined</textarea>`` into "text area
    containing ...", and once that is a sentence nothing marks the words as
    a form value, so the pass over the finished file cannot find them. Here
    the element code and the structured evidence still have their context.

    The stored row is not changed; a new dict is returned. An element locator
    (a ``target_selector`` that is text, not JSON) is left as it is, because a
    changed locator no longer finds its element. Other text fields, such as
    the check's own summary, are left to the pass over the finished file.
    """

    copy = dict(finding)
    for key in ("html_snippet", "engine_evidence_json"):
        if copy.get(key):
            copy[key] = redact_field(str(copy[key]))
    selector = str(copy.get("target_selector") or "")
    if selector and _is_structured(selector):
        copy["target_selector"] = redact_field(selector)
    return copy


# --- Formats -----------------------------------------------------------------


def _redact_markdown(rendered: str, redactor: _Redactor) -> str:
    notice = f"> **{REDACTION_TITLE}**\n>\n> {REDACTION_NOTICE}\n\n"
    return notice + redactor.block(rendered, by_line=True)


def _redact_json(rendered: str, redactor: _Redactor) -> str:
    payload = json.loads(rendered)
    if not isinstance(payload, dict):
        raise ValueError("Public JSON export must contain an object")
    redacted = redactor.json_value(payload)
    redacted["redaction_notice"] = {
        "label": REDACTION_TITLE,
        "redacted": True,
        "best_effort": True,
        "warning": REDACTION_NOTICE,
        "marker": REDACTED,
    }
    return json.dumps(redacted, indent=2, sort_keys=True, ensure_ascii=False)


def _redact_csv(rendered: str, redactor: _Redactor) -> str:
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
        writer.writerow([*(redactor.field(cell) for cell in row), REDACTION_CSV_VALUE])
    return output.getvalue()


def _redact_formula(formula: str, redactor: _Redactor) -> str:
    """Redact a spreadsheet formula, keeping it a formula.

    Text that came from the report can sit in a formula: a note that starts
    with "=", or the label of ``=HYPERLINK("https://...", "jane@example.com")``.
    Each quoted string is redacted as text, with its doubled quotes read and
    written back. What is outside the strings (function names, cell
    references) only gets the link and identifier patterns, which match
    nothing a working formula holds.
    """

    def outside(part: str) -> str:
        return _redact_patterns(_URL.sub(lambda m: redact_url(m.group(0)), part))

    out: list[str] = []
    position = 0
    for match in _FORMULA_STRING.finditer(formula):
        out.append(outside(formula[position : match.start()]))
        literal = redactor.text(match.group(1).replace('""', '"'))
        out.append('"' + literal.replace('"', '""') + '"')
        position = match.end()
    out.append(outside(formula[position:]))
    return "".join(out)


def _redact_workbook(rendered: bytes, redactor: _Redactor) -> bytes:
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
                    cell.value = redactor.field(cell.value)
                elif isinstance(cell.value, str):
                    cell.value = _redact_formula(cell.value, redactor)
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
    notice.merge_cells("B3:F9")
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


_TEXT_REDACTORS: dict[str, Callable[[str, _Redactor], str]] = {
    "audit": _redact_markdown,
    "markdown": _redact_markdown,
    "json": _redact_json,
    "csv": _redact_csv,
    "jira": _redact_csv,
}


def redact_export(
    rendered: str | bytes,
    *,
    export_format: str,
    locators: Iterable[str] = (),
) -> str | bytes:
    """Return a redacted copy of one rendered export, with its notice inside.

    ``locators`` are the element locators the scan recorded
    (:func:`scan_locators`). Each is left whole wherever it appears in the
    file, so it still finds its element; the notice in the file says so.

    Raises ``ValueError`` for a format this module does not know, so a new
    export format can never be served as "redacted" without being redacted.
    """

    redactor = _Redactor(locators)
    # Both workbooks: the issue workbook, and the U-M ITS technical review
    # (its = the ITS team's template, filled in). The pass is the same for
    # any workbook: every text cell and link, pictures removed, a notice
    # sheet first.
    if export_format in ("xlsx", "its"):
        if not isinstance(rendered, bytes):
            raise TypeError("XLSX exports must be bytes")
        return _redact_workbook(rendered, redactor)
    redact = _TEXT_REDACTORS.get(export_format)
    if redact is None:
        raise ValueError(f"Redaction is not available for the {export_format!r} format")
    if not isinstance(rendered, str):
        raise TypeError(f"{export_format} exports must be text")
    return redact(rendered, redactor)
