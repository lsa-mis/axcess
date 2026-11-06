"""Find the addresses a page leads to, from its HTML alone.

The crawl used to read only ``<a href>``. Two common ways a page leads
somewhere else were invisible to it:

* image maps, ``<area href>``, which are links in every way but their tag;
* buttons. A ``<button onclick="location.href='/next.html'">`` and a form
  that is nothing but a button (``<form action="/results.html"><button>``)
  both take the user to another page, and a scan that ignores them misses it.

This reads those too, from the static HTML or the rendered page, without
running scripts. It reads only literal addresses: a handler that builds the
address in code is still found only by Click-Through, which operates the
control in a browser.

A form counts only when submitting it sends the user nowhere but its action
address: method GET, and no field a person types into or chooses. A search
box or a sign-in form is left alone, and a POST form never counts, because
submitting one can change data on the site.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from selectolax.parser import HTMLParser, Node

# location = '…', location.href = '…', location.assign('…'),
# location.replace('…') and window.open('…'), with a literal address.
_ONCLICK_URL = re.compile(
    r"""(?:location(?:\.href)?\s*=\s*|location\.(?:assign|replace)\s*\(\s*|window\.open\s*\(\s*)"""
    r"""(['"])(?P<url>[^'"]+)\1""",
)

# Input types that a person does not type into or choose: a form holding only
# these goes to one fixed address when its button is pressed.
_FIXED_INPUT_TYPES = frozenset({"hidden", "submit", "button", "image", "reset"})

_SELECTOR = "a[href], area[href], [onclick], form"


def discover_links(base_url: str, body: bytes | str) -> list[str]:
    """Absolute addresses the page leads to, in document order, unnormalized.

    Returns an empty list for a body the parser cannot read. Callers still
    normalize, scope-check and deduplicate each address.
    """
    try:
        tree = HTMLParser(body)
    except Exception:  # selectolax can raise on exotic inputs
        return []
    found: list[str] = []
    for node in tree.css(_SELECTOR):
        for raw in _addresses(node):
            try:
                found.append(urljoin(base_url, raw))
            except ValueError:
                continue
    return found


def _addresses(node: Node) -> list[str]:
    out: list[str] = []
    tag = node.tag
    attrs = node.attributes
    if tag in ("a", "area"):
        href = attrs.get("href")
        if href and not href.lower().startswith("javascript:"):
            out.append(href)
    onclick = attrs.get("onclick")
    if onclick:
        out.extend(match.group("url") for match in _ONCLICK_URL.finditer(onclick))
    if tag == "form":
        action = _button_only_form_action(node)
        if action is not None:
            out.append(action)
    return out


def _button_only_form_action(form: Node) -> str | None:
    """The address a GET form with no user fields goes to, else None."""
    method = (form.attributes.get("method") or "get").strip().lower()
    action = (form.attributes.get("action") or "").strip()
    if method != "get" or not action:
        return None
    if form.css_first("select, textarea") is not None:
        return None
    pairs: list[tuple[str, str]] = []
    for field in form.css("input"):
        kind = (field.attributes.get("type") or "text").strip().lower()
        if kind not in _FIXED_INPUT_TYPES:
            return None
        name = field.attributes.get("name")
        if kind == "hidden" and name:
            pairs.append((name, field.attributes.get("value") or ""))
    # A GET submission replaces the action's query with the form's fields.
    parts = urlsplit(action)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), ""))
