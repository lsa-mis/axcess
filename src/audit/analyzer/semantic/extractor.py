"""Per-criterion element extraction.

GenA11y's central insight: feeding the model the whole page is worse
than feeding it the focused slice relevant to one criterion. So for
each WCAG SC the semantic pipeline targets, we extract only the
elements that criterion cares about — usually a list of dicts the
model can read directly.

Each extractor returns JSON-friendly data (dict-of-strings,
list-of-dicts) so the per-criterion prompt template can interpolate
it without bespoke serialization. The static surface uses selectolax
(fast, zero-copy); the computed-style surface (not yet implemented;
SC 1.4.3 will need it in a later phase) will use Playwright
``page.evaluate()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from selectolax.parser import HTMLParser, Node

# How deep up the ancestor chain we capture context for an element.
# GenA11y's paper uses 5; the value is in one place so a future tuning
# doesn't require sweeping the codebase.
ANCESTOR_DEPTH = 5

# Schemes that are technically <a href> but never carry a navigable
# destination we'd flag for "purpose unclear." Mailto/tel are
# self-describing once you read the href; javascript: is a no-op or
# in-page action with its own a11y rules (button semantics instead);
# fragment-only is an in-page jump (its purpose is the section anchor
# it points at, not the link's text). We skip them at extraction time
# to keep prompt size + false-positive rate down.
_SKIP_SCHEMES = ("javascript:", "mailto:", "tel:", "sms:")


@dataclass(frozen=True, slots=True)
class LinkRecord:
    """One ``<a>`` element ready for prompt injection.

    Shape mirrors the GenA11y paper's link-extraction schema:
    accessible name + href + ancestor textual context. ``selector``
    is a stable CSS path the runner uses to round-trip findings back
    to the DOM (and as part of the dedupe ``target_hash``).
    """

    selector: str
    href: str
    accessible_name: str  # visible text / aria-label / aria-labelledby / img alt
    # One of: text | aria-label | aria-labelledby | img-alt | svg-title |
    # title | empty. See _accessible_name() for the precedence rules.
    accessible_name_source: str
    aria_label: str | None
    title: str | None
    ancestors: list[str] = field(default_factory=list)
    snippet: str = ""  # outerHTML, truncated


def extract_links(body: bytes, *, ancestor_depth: int = ANCESTOR_DEPTH) -> list[LinkRecord]:
    """Pull every meaningful ``<a href>`` from ``body`` for SC 2.4.4 analysis.

    Skipped:

    * Empty / whitespace-only ``href``.
    * Schemes in ``_SKIP_SCHEMES`` — they have their own a11y semantics
      that don't fit the "is this link descriptive?" question.
    * Fragment-only links (``href="#section"``) — the destination IS the
      anchor; SC 2.4.4 doesn't apply the same way.

    Note: we deliberately **do not** dedupe by URL. Two ``<a>`` elements
    pointing at the same href with different visible text are two
    distinct findings (one might be descriptive, the other not).
    """
    try:
        tree = HTMLParser(body)
    except Exception:
        # selectolax is permissive but can raise on truly garbage input
        # (e.g. binary blobs accidentally routed here). Better to return
        # nothing than crash the per-page analyzer.
        return []

    out: list[LinkRecord] = []
    for idx, anchor in enumerate(tree.css("a")):
        href_raw = anchor.attributes.get("href")
        if href_raw is None:
            # `<a name="...">` placeholder anchors aren't navigation
            # targets and don't carry SC 2.4.4 obligations.
            continue
        href = href_raw.strip()
        if not href:
            continue
        if href.startswith("#"):
            continue
        if any(href.lower().startswith(s) for s in _SKIP_SCHEMES):
            continue

        name, source = _accessible_name(anchor)
        out.append(
            LinkRecord(
                selector=_stable_selector(anchor, idx),
                href=href,
                accessible_name=name,
                accessible_name_source=source,
                aria_label=anchor.attributes.get("aria-label"),
                title=anchor.attributes.get("title"),
                ancestors=_ancestor_texts(anchor, depth=ancestor_depth),
                snippet=_truncated_html(anchor, limit=300),
            )
        )
    return out


# --------------------------------------------------------------------
# Accessible name resolution.
# --------------------------------------------------------------------
#
# We follow the HTML Accessibility API Mappings (HTML-AAM) precedence
# in spirit, but compressed: aria-labelledby > aria-label > visible
# text > nested img alt > title > empty. This is not the full ARIA
# accessible-name algorithm (that's recursive and considers
# pseudo-elements + label CSS content); for SC 2.4.4 the model wants
# "what does a screen-reader user hear?" — the compressed version
# captures the cases that matter in practice.
# --------------------------------------------------------------------


def _accessible_name(node: Node) -> tuple[str, str]:
    """Return ``(accessible_name, source_label)`` for an anchor."""
    # aria-labelledby — references another element by id. We resolve
    # against the document root so the lookup hits any element.
    labelledby = node.attributes.get("aria-labelledby")
    if labelledby:
        names: list[str] = []
        for ref_id in labelledby.split():
            referent = _find_by_id(node, ref_id)
            if referent is not None:
                text = _collapse(referent.text() or "")
                if text:
                    names.append(text)
        if names:
            return " ".join(names), "aria-labelledby"

    aria_label = node.attributes.get("aria-label")
    if aria_label and aria_label.strip():
        return _collapse(aria_label), "aria-label"

    visible = _collapse(node.text() or "")
    if visible:
        return visible, "text"

    # Icon-only links commonly use <img alt="..."> or <svg><title>...
    # as their accessible name. We check both, taking the first non-
    # empty value.
    for img in node.css("img"):
        alt = img.attributes.get("alt")
        if alt and alt.strip():
            return _collapse(alt), "img-alt"
    for svg_title in node.css("title"):
        text = _collapse(svg_title.text() or "")
        if text:
            return text, "svg-title"

    title = node.attributes.get("title")
    if title and title.strip():
        return _collapse(title), "title"

    return "", "empty"


def _find_by_id(start: Node, target_id: str) -> Node | None:
    """Walk to the document root, then look up an element by id.

    selectolax doesn't expose ``getElementById`` directly; we walk
    up to the root and query the whole subtree.
    """
    root = start
    while root.parent is not None:
        root = root.parent
    return root.css_first(f"#{target_id}")


def _ancestor_texts(node: Node, *, depth: int) -> list[str]:
    """Collect collapsed text of up to ``depth`` ancestors, root-most last.

    SC 2.4.4 says a link's purpose can be derived from "the link text
    *together with its programmatically determined link context*."
    The model wants the ancestor section / paragraph / list item /
    figure-caption / heading text — pretty much anything close enough
    to disambiguate "read more" links. We collapse whitespace and
    truncate per ancestor so the prompt doesn't explode on
    document-length ancestors (e.g. <body>).
    """
    out: list[str] = []
    cur = node.parent
    for _ in range(depth):
        if cur is None:
            break
        text = _collapse(cur.text() or "")
        if text:
            out.append(text[:200])
        cur = cur.parent
    return out


def _stable_selector(node: Node, ordinal: int) -> str:
    """Construct a CSS selector the operator can paste into devtools.

    Preference order: id → class chain → tag + ordinal. The ordinal
    is the document-order index of *this* anchor (not "nth-of-type")
    because the model sees the index in the input list and must be
    able to map back. The actual UI doesn't depend on this selector
    being unique; it's a hint for the human reviewer.
    """
    id_attr = node.attributes.get("id")
    if id_attr:
        return f"a#{id_attr}"
    klass = node.attributes.get("class")
    if klass:
        # First class only — multi-class selectors get ugly in reports
        # and the index is what actually disambiguates.
        first = klass.split()[0]
        return f"a.{first}[ord={ordinal}]"
    return f"a[ord={ordinal}]"


def _truncated_html(node: Node, *, limit: int) -> str:
    """Best-effort outerHTML, capped to ``limit`` chars.

    Used in the model prompt and the persisted ``html_snippet`` field.
    selectolax decodes the source as UTF-8 lazily; on a non-UTF-8 body
    ``node.html`` can raise ``UnicodeDecodeError``. We swallow it and
    return an empty snippet rather than crash the analyzer — a page
    in the wrong encoding shouldn't lose its links entirely.
    """
    try:
        raw = node.html or ""
    except UnicodeDecodeError:
        return ""
    if len(raw) <= limit:
        return raw
    return raw[:limit] + "…"


def _collapse(text: str) -> str:
    """Squeeze whitespace runs into single spaces, trim, return ASCII-ish."""
    return " ".join(text.split())


# --------------------------------------------------------------------
# Headings (SC 2.4.6 — Headings and Labels).
# --------------------------------------------------------------------

_HEADING_SELECTOR = "h1, h2, h3, h4, h5, h6, [role=heading]"

# How much of the content a heading introduces to feed the model. Enough to
# judge "does this heading describe what follows?" without bloating the prompt.
_SECTION_TEXT_LIMIT = 400


@dataclass(frozen=True, slots=True)
class HeadingRecord:
    """One heading element ready for SC 2.4.6 (descriptiveness) analysis."""

    selector: str
    level: int  # 1-6 (or aria-level); 0 if a role=heading with no level
    text: str  # the heading's own text
    following_text: str  # the content it introduces (next siblings' text)
    ancestors: list[str] = field(default_factory=list)
    snippet: str = ""


def extract_headings(body: bytes, *, ancestor_depth: int = ANCESTOR_DEPTH) -> list[HeadingRecord]:
    """Pull every non-empty heading + the content it introduces.

    SC 2.4.6 asks whether headings *describe topic or purpose*. Empty
    headings are a different failure (axe covers those), so we skip them —
    this analyzer judges descriptiveness, which needs heading text to judge.
    """
    try:
        tree = HTMLParser(body)
    except Exception:
        return []

    out: list[HeadingRecord] = []
    for idx, node in enumerate(tree.css(_HEADING_SELECTOR)):
        text = _collapse(node.text() or "")
        if not text:
            continue
        out.append(
            HeadingRecord(
                selector=_stable_selector_for(node, "h", idx),
                level=_heading_level(node),
                text=text,
                following_text=_following_section_text(node),
                ancestors=_ancestor_texts(node, depth=ancestor_depth),
                snippet=_truncated_html(node, limit=300),
            )
        )
    return out


def _heading_level(node: Node) -> int:
    """Heading level from the tag (h1-h6) or aria-level; 0 if unknown."""
    tag = (node.tag or "").lower()
    if len(tag) == 2 and tag[0] == "h" and tag[1].isdigit():
        return int(tag[1])
    aria_level = node.attributes.get("aria-level")
    if aria_level and aria_level.strip().isdigit():
        return int(aria_level.strip())
    return 0


def _following_section_text(node: Node) -> str:
    """Text of the siblings a heading introduces, up to the next heading.

    Walks forward over next siblings, accumulating their text, and stops at
    the next heading (its content belongs to that heading, not this one).
    """
    parts: list[str] = []
    cur = node.next
    total = 0
    while cur is not None and total < _SECTION_TEXT_LIMIT:
        tag = (cur.tag or "").lower()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            break
        if cur.attributes.get("role") == "heading":
            break
        text = _collapse(cur.text() or "")
        if text:
            parts.append(text)
            total += len(text)
        cur = cur.next
    return _collapse(" ".join(parts))[:_SECTION_TEXT_LIMIT]


def _stable_selector_for(node: Node, tag_hint: str, ordinal: int) -> str:
    """Like ``_stable_selector`` but for non-anchor elements.

    Uses the element's real tag (``node.tag``) when available so the hint
    reads naturally in a report (``h2#intro`` rather than ``a#intro``).
    """
    tag = (node.tag or tag_hint).lower()
    id_attr = node.attributes.get("id")
    if id_attr:
        return f"{tag}#{id_attr}"
    klass = node.attributes.get("class")
    if klass:
        return f"{tag}.{klass.split()[0]}[ord={ordinal}]"
    return f"{tag}[ord={ordinal}]"


__all__ = [
    "ANCESTOR_DEPTH",
    "HeadingRecord",
    "LinkRecord",
    "extract_headings",
    "extract_links",
]
