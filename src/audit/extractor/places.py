"""Name an element of a saved copy so the inspector's browser can find it again.

The extractors and the AI review read a page with selectolax, and the
inspector shows the same saved bytes in a browser. The two parsers agree on
the document but not on how they list it: selectolax returns a selector list
such as ``img, picture > source`` grouped by selector rather than in document
order, and it reaches into ``<template>`` content, which a browser's DOM does
not. The inspector also removes ``<noscript>`` from the copy it shows.

So an element is named the way a browser can count it: the ``index``th of the
``total`` elements a plain type selector (``img``, ``h2``) matches in the
document, in document order, leaving out elements inside a ``<template>`` or
a ``<noscript>``. The inspector checks ``total`` before it trusts ``index``: a
count that differs means it is not looking at the document that was read.
"""

from __future__ import annotations

from dataclasses import dataclass

from selectolax.parser import HTMLParser, Node

_HIDDEN_FROM_INSPECTOR = frozenset({"template", "noscript"})


@dataclass(frozen=True)
class Place:
    """The ``index``th of ``total`` elements that ``selector`` matches."""

    selector: str
    index: int
    total: int


def hidden_from_inspector(node: Node) -> bool:
    """True inside a ``<template>`` or a ``<noscript>``: no browser count includes it."""
    parent = node.parent
    while parent is not None:
        if parent.tag in _HIDDEN_FROM_INSPECTOR:
            return True
        parent = parent.parent
    return False


class Places:
    """Places of elements in one parsed document, counted once per selector."""

    def __init__(self, tree: HTMLParser, *, root: Node | None = None) -> None:
        self._root: Node | None = root if root is not None else tree.root
        # Keyed by node: selectolax hashes and compares a node by the element
        # it wraps, so two lookups of one element are one key.
        self._indexes: dict[str, dict[Node, int]] = {}
        self._totals: dict[str, int] = {}

    def of(self, node: Node, selector: str) -> Place | None:
        """Where ``node`` sits among ``selector``'s matches, or None if a browser cannot see it."""
        if selector not in self._indexes:
            live = (
                [n for n in self._root.css(selector) if not hidden_from_inspector(n)]
                if self._root is not None
                else []
            )
            self._indexes[selector] = {n: index for index, n in enumerate(live)}
            self._totals[selector] = len(live)
        index = self._indexes[selector].get(node)
        if index is None:
            return None
        return Place(selector=selector, index=index, total=self._totals[selector])
