# ruff: noqa: E501 - the JS constants are transcriptions; rewrapping their lines
# would obscure the correspondence with the pinned source.
"""Upstream's candidate generators D0-D8, transcribed from the pinned source.

Ported from ``experiments/tabbing/candidates.ts`` in
`harryg02/a11y-crawler <https://github.com/harryg02/a11y-crawler>`_ at commit
``6c40f7c714ab053e40a8e0d80d33f27812403f1b``, Apache-2.0; see
``experiments/tabbing/LICENSE.upstream`` and ``NOTICE.upstream``.

**Why this module exists.** Our own detectors in
``audit.analyzer.keyboard.kbdiff.detectors`` answer the same questions but are
not the same code, and the differences are large enough to change every score:
upstream gates every survey detector on their pierced ``allElements(true)`` and
their ``isVisible``, tests seven inline attributes where we test one, five
handler properties where we test one, *excludes* any ``tabindex`` for D3 where
we propose on it, and matches their class lexicon on token boundaries where we
match substrings. Presenting our versions as replications was wrong. These are
the replications; ours are kept beside them as the comparison.

Unlike ``upstream_instrument``, this could not be extracted verbatim: their
``evaluate`` bodies carry TypeScript annotations that will not run as
JavaScript. It is therefore a hand transcription, and each rule is pinned by a
focused regression rather than asserted wholesale.

Everything here reads ``window.__a11y`` from
:data:`upstream_instrument.UPSTREAM_INIT_JS`, runs over the main frame and every
child frame as theirs does, and returns **raw proposals**: no ``- Set T``
subtraction and no scoring, so the caller decides both.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any, Literal

PageDetector = Literal["attrScan", "handlerProp", "tabindexCounter", "cssLexical", "reactProps"]

# candidates.ts `pageDetector`. The constants are theirs exactly: seven inline
# attributes, five handler properties, a token-boundary lexicon, and the native
# set whose <a> arm requires href and whose others require not-disabled.
UPSTREAM_SURVEY_JS = r"""
(kind) => {
  const a11y = window.__a11y;
  const hits = new Set();
  if (!a11y) throw new Error('upstream instrumentation is missing');

  const NATIVE = new Set(['a', 'button', 'input', 'select', 'textarea', 'summary', 'audio', 'video', 'iframe']);
  const INTERACTIVE_ROLES = new Set([
    'button', 'link', 'checkbox', 'radio', 'switch', 'tab', 'menuitem',
    'menuitemcheckbox', 'menuitemradio', 'option', 'slider', 'spinbutton', 'treeitem',
  ]);
  const LEXICON = /(^|[-_ ])(btn|button|click|clickable|toggle|tab|selected|action|menu|icon|link|card|switch|dropdown|expand|close|open|nav)([-_ ]|$)/i;
  const INLINE = ['onclick', 'onkeyup', 'onkeydown', 'onkeypress', 'onmousedown', 'onmouseup', 'onmouseover'];

  const nativelyFocusable = (el) => {
    const t = el.tagName.toLowerCase();
    if (!NATIVE.has(t)) return false;
    if (t === 'a') return el.hasAttribute('href');
    return !el.disabled;
  };

  for (const el of a11y.allElements(true)) {
    const probe = el.getAttribute ? el.getAttribute('data-probe') : null;
    if (!probe) continue;
    if (!a11y.isVisible(el)) continue;

    const role = el.getAttribute('role') || '';
    const hasTabindex = el.hasAttribute('tabindex');
    const hasInline = INLINE.some((a) => el.hasAttribute(a));
    const cls = typeof el.className === 'string' ? el.className : '';

    if (kind === 'attrScan') {
      if (hasInline && !nativelyFocusable(el) && !hasTabindex) hits.add(probe);
    } else if (kind === 'handlerProp') {
      const hasProp = ['onclick', 'onmousedown', 'onmouseup', 'onmouseover', 'ondblclick']
        .some((k) => typeof el[k] === 'function');
      if (hasProp) hits.add(probe);
    } else if (kind === 'tabindexCounter') {
      const looksInteractive = INTERACTIVE_ROLES.has(role) || hasInline ||
        el.hasAttribute('aria-expanded') || el.hasAttribute('aria-haspopup');
      if (looksInteractive && !nativelyFocusable(el) && !hasTabindex) hits.add(probe);
    } else if (kind === 'cssLexical') {
      const cs = getComputedStyle(el);
      const looks = cs.cursor === 'pointer' || LEXICON.test(cls) || INTERACTIVE_ROLES.has(role);
      if (looks) hits.add(probe);
    } else if (kind === 'reactProps') {
      for (const key of Object.keys(el)) {
        if (!key.startsWith('__reactProps$')) continue;
        const props = el[key];
        if (props && (props.onClick || props.onMouseDown || props.onMouseOver)) hits.add(probe);
      }
    }
  }
  return [...hits];
}
"""

# candidates.ts `visibleProbes`. Every generator is filtered through this, so
# none is charged with a false positive on an element none of them considered.
UPSTREAM_VISIBLE_JS = r"""
() => {
  const a11y = window.__a11y;
  if (!a11y) throw new Error('upstream instrumentation is missing');
  const res = [];
  for (const el of a11y.allElements(true)) {
    const id = el.getAttribute ? el.getAttribute('data-probe') : null;
    if (id && a11y.isVisible(el)) res.push(id);
  }
  return res;
}
"""

# candidates.ts `d0CurrentCrawler`: their crawler's own selector list and
# filters, mapped onto probes through `probeOf`, which walks up through shadow
# hosts rather than stopping at the element itself.
UPSTREAM_D0_JS = r"""
() => {
  const a11y = window.__a11y;
  if (!a11y) throw new Error('upstream instrumentation is missing');
  const candidates = document.querySelectorAll(
    'button, [role="button"], [role="tab"], [role="menuitem"], ' +
    '[role="switch"], [role="checkbox"], [role="radio"], ' +
    'details > summary, [aria-expanded], [aria-haspopup], ' +
    'select, [onclick]'
  );
  const res = [];
  for (const el of candidates) {
    if (el.closest('a')) continue;
    if (el.offsetParent === null) continue;
    if (el.tagName === 'TD' || el.tagName === 'TR' || el.tagName === 'TH') continue;
    const probe = a11y.probeOf(el);
    if (probe) res.push(probe);
  }
  return res;
}
"""

# candidates.ts `d6ListenerShim`: seven mouse types, and the target is resolved
# at read time from the recorded node, so a listener bound to document or
# window is excluded by the nodeType check rather than by its selector.
UPSTREAM_D6_JS = r"""
() => {
  const a11y = window.__a11y;
  if (!a11y) throw new Error('upstream instrumentation is missing');
  const MOUSE = ['click', 'mousedown', 'mouseup', 'mouseover', 'mouseenter', 'dblclick', 'pointerdown'];
  const out = [];
  for (const rec of a11y.listeners) {
    if (!MOUSE.includes(rec.type)) continue;
    if (!rec.target || rec.target.nodeType !== 1) continue;
    const probe = rec.target.getAttribute ? rec.target.getAttribute('data-probe') : null;
    if (probe) out.push({ probe: probe, stack: rec.stack });
  }
  return out;
}
"""

# candidates.ts D5's event set. Eight types, against our four.
UPSTREAM_MOUSE_EVENTS = frozenset(
    {
        "click",
        "mousedown",
        "mouseup",
        "mouseover",
        "mouseenter",
        "dblclick",
        "pointerdown",
        "pointerup",
    }
)

_PROBE_ATTR = "data-probe"

# Chromium's CBOR encoder refuses to serialise a response nested deeper than its
# fixed stack limit, and each DOM level costs two nesting levels (the node map
# plus its `children` array). A page nested ~150 elements deep therefore makes a
# single `depth: -1` response unserialisable:
#
#   Protocol error (DOM.getDocument): Failed to convert response to JSON:
#   CBOR: stack limit exceeded at position 53429
#
# Measured on Chromium 145 against `edgecases/pages/scale.html` (154 levels, 284
# elements): `depth: 148` encodes in 73 KB, `depth: 150` does not. It is a
# nesting limit, not a size limit, and nothing is wrong with the page or with
# the traversal -- only with asking for the whole tree in one response. So the
# unbounded call stays the primary path, byte-identical wherever it already
# worked, and the tree is fetched in bounded slices only when it raises.
_PIERCE_CHUNK = 64
_PIERCE_CALL_CAP = 4096


async def get_pierced_document(cdp: Any) -> dict[str, Any]:
    """The pierced DOM tree root, fetched in slices if one response is too deep.

    Returns the same structure ``DOM.getDocument`` returns under
    ``{"depth": -1, "pierce": True}``, so callers walk it unchanged.
    """
    # The unbounded attempt is a probe, not a measurement. If it is recovered
    # below it must not linger in a `CheckedInstrument`'s error list, where it
    # would later be reported as a silent instrument failure.
    recorded = getattr(cdp, "errors", None)
    mark = len(recorded) if isinstance(recorded, list) else None

    try:
        document = await cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
        return document.get("root", {})
    except Exception as exc:
        # Only the encoder's nesting limit is recoverable this way. A detached
        # session or an unsupported command is still a failed measurement.
        if "stack limit exceeded" not in str(exc):
            raise
        if mark is not None:
            del recorded[mark:]

    document = await cdp.send("DOM.getDocument", {"depth": _PIERCE_CHUNK, "pierce": True})
    root = document.get("root", {})

    # `DOM.describeNode` answers in its own response, so the subtree can be
    # spliced in directly; `DOM.requestChildNodes` would deliver it as an event
    # and need the DOM domain enabled and an event pump.
    #
    # It must be addressed by `backendNodeId`, not `nodeId`: nodes arriving in a
    # `describeNode` response are not registered with the frontend and come back
    # with `nodeId: 0`, so descending by `nodeId` fails one slice in with
    # "Could not find node with given id". Backend ids are always populated.
    pending = [root]
    unregistered: list[dict[str, Any]] = []
    calls = 0
    while pending:
        node = pending.pop()
        for key in ("children", "shadowRoots"):
            pending.extend(node.get(key) or [])
        for key in ("contentDocument", "templateContent"):
            child = node.get(key)
            if child:
                pending.append(child)
        if not node.get("nodeId") and node.get("backendNodeId"):
            unregistered.append(node)
        if not node.get("childNodeCount") or node.get("children"):
            continue
        if calls >= _PIERCE_CALL_CAP:
            raise RuntimeError(
                f"pierced tree exceeded {_PIERCE_CALL_CAP} slice requests; refusing to "
                "report a partial tree as a complete one"
            )
        calls += 1
        described = await cdp.send(
            "DOM.describeNode",
            {"backendNodeId": node["backendNodeId"], "depth": _PIERCE_CHUNK, "pierce": True},
        )
        filled = described.get("node") or {}
        for key in ("shadowRoots", "contentDocument", "templateContent"):
            if filled.get(key):
                node[key] = filled[key]
        # Re-queue only what the call actually produced. A node that reports
        # children but yields none would otherwise spin here forever.
        if filled.get("children"):
            node["children"] = filled["children"]
            pending.extend(filled["children"])

    # Callers pass the `nodeId` they find straight to `DOM.getBoxModel`, so a
    # spliced-in node has to carry a real one rather than the placeholder zero.
    for start in range(0, len(unregistered), 500):
        batch = unregistered[start : start + 500]
        pushed = await cdp.send(
            "DOM.pushNodesByBackendIdsToFrontend",
            {"backendNodeIds": [node["backendNodeId"] for node in batch]},
        )
        for node, node_id in zip(batch, pushed.get("nodeIds") or [], strict=False):
            node["nodeId"] = node_id
    return root


@dataclass(frozen=True)
class ProbeNode:
    """One probe located in the pierced CDP tree, as ``resolveProbeNodes`` returns."""

    probe: str
    node_id: int
    box: tuple[float, float, float, float] | None  # x, y, w, h
    via: str = "cdp"

    @property
    def centre(self) -> tuple[float, float] | None:
        """``centerOf``: no box, or a zero-sized one, has no centre."""
        if self.box is None or self.box[2] == 0 or self.box[3] == 0:
            return None
        x, y, w, h = self.box
        return (x + w / 2, y + h / 2)


async def _each_frame(page: Any, expression: str, *args: Any) -> list[Any]:
    """Evaluate in the main frame and every child frame, as upstream does."""
    results: list[Any] = []
    for frame in page.frames:
        # Deliberate reliability adaptation: upstream catches this as []. A
        # failed instrument must invalidate the measurement, not improve scores.
        results.append(await frame.evaluate(expression, *args))
    return results


async def visible_probes(page: Any) -> set[str]:
    """``visibleProbes``: the shared visibility gate every generator is filtered by."""
    out: set[str] = set()
    for ids in await _each_frame(page, UPSTREAM_VISIBLE_JS):
        out.update(ids or [])
    return out


async def survey(page: Any, kind: PageDetector) -> set[str]:
    """``pageDetector``: D2 (attrScan), D2b (handlerProp), D3 (tabindexCounter),
    D4 (cssLexical) or D7 (reactProps)."""
    out: set[str] = set()
    for ids in await _each_frame(page, UPSTREAM_SURVEY_JS, kind):
        out.update(ids or [])
    return out


async def d0_current_crawler(page: Any) -> set[str]:
    """``d0CurrentCrawler``: their crawler's own clickable collection."""
    out: set[str] = set()
    for ids in await _each_frame(page, UPSTREAM_D0_JS):
        out.update(ids or [])
    return out


UPSTREAM_SHIM_RESOLVE_JS = r"""
(id) => {
  if (!window.__a11y) throw new Error('upstream instrumentation is missing');
  const el = window.__a11y.findProbe(id, true);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  let ox = 0, oy = 0, win = window;
  while (win !== win.parent) {
    const fe = win.frameElement;
    if (!fe) break;
    const fr = fe.getBoundingClientRect();
    ox += fr.x; oy += fr.y; win = win.parent;
  }
  return {box: r.width || r.height ? [r.x + ox, r.y + oy, r.width, r.height] : null};
}
"""


async def resolve_probe_nodes(
    cdp: Any, only: list[str] | None = None, page: Any = None
) -> dict[str, ProbeNode]:
    """``resolveProbeNodes``: walk the pierced tree, then take each border box.

    Pierced means shadow roots, closed ones included, plus frame content
    documents and template contents — reach a Playwright locator does not have.
    """
    document = await get_pierced_document(cdp)

    found: dict[str, int] = {}

    def walk(node: dict[str, Any]) -> None:
        attributes = node.get("attributes") or []
        for i in range(0, len(attributes) - 1, 2):
            if attributes[i] == _PROBE_ATTR and attributes[i + 1] not in found:
                found[attributes[i + 1]] = node["nodeId"]
        for key in ("children", "shadowRoots"):
            for child in node.get(key) or []:
                walk(child)
        for key in ("contentDocument", "templateContent"):
            child = node.get(key)
            if child:
                walk(child)

    walk(document)

    nodes: dict[str, ProbeNode] = {}
    wanted = set(only) if only is not None else None
    for probe, node_id in found.items():
        box: tuple[float, float, float, float] | None = None
        if wanted is not None and probe not in wanted:
            nodes[probe] = ProbeNode(probe=probe, node_id=node_id, box=None)
            continue
        try:
            model = (await cdp.send("DOM.getBoxModel", {"nodeId": node_id})).get("model") or {}
            border = model.get("border") or []
            if len(border) >= 8:
                xs, ys = border[0:8:2], border[1:8:2]
                x, y = min(xs), min(ys)
                box = (x, y, max(xs) - x, max(ys) - y)
        except Exception as exc:
            # Normal absence of layout is an upstream exclusion. A detached
            # session or unsupported command is a failed measurement.
            if "Could not compute box model" not in str(exc):
                raise
            box = None
        nodes[probe] = ProbeNode(probe=probe, node_id=node_id, box=box)
    if page is not None:
        for probe in only or []:
            if probe in nodes:
                continue
            for frame in page.frames:
                info = await frame.evaluate(UPSTREAM_SHIM_RESOLVE_JS, probe)
                if info is None:
                    continue
                values = info["box"]
                box = None if values is None else (values[0], values[1], values[2], values[3])
                nodes[probe] = ProbeNode(probe=probe, node_id=-1, box=box, via="shim")
                break
    return nodes


async def d5_cdp_listeners(
    cdp: Any, nodes: dict[str, ProbeNode], visible: set[str] | None = None
) -> set[str]:
    """``d5CdpListeners``: pierced ``DOM.resolveNode``, ``depth: 0``, eight mouse types.

    Ours resolves through a page-script ``querySelector`` walk, which cannot see
    a closed shadow root, and asks for ``depth: 1``, which reports listeners on
    descendants as if they were on the element.
    """
    hits: set[str] = set()
    for node in nodes.values():
        if visible is not None and node.probe not in visible:
            continue
        if node.via == "shim":
            # Upstream tries nodeId=-1 and catches the resolution error. The
            # shim supplies geometry, not a CDP listener object; D6 can see it.
            continue
        resolved = await cdp.send("DOM.resolveNode", {"nodeId": node.node_id})
        object_id = (resolved.get("object") or {}).get("objectId")
        if not object_id:
            raise RuntimeError(f"CDP returned no object for {node.probe}")
        try:
            listeners = await cdp.send(
                "DOMDebugger.getEventListeners",
                {"objectId": object_id, "depth": 0, "pierce": True},
            )
            for entry in listeners.get("listeners") or []:
                if entry.get("type") in UPSTREAM_MOUSE_EVENTS:
                    hits.add(node.probe)
                    break
        finally:
            with contextlib.suppress(Exception):
                await cdp.send("Runtime.releaseObject", {"objectId": object_id})
    return hits


async def d6_listener_shim(
    page: Any, visible: set[str] | None = None
) -> tuple[set[str], dict[str, str]]:
    """``d6ListenerShim``: the registry, plus the stack that proves where it came from.

    Returns the hits and their provenance. Upstream keeps the stack because a
    finding a developer cannot locate is a finding they will mute.
    """
    hits: set[str] = set()
    provenance: dict[str, str] = {}
    for records in await _each_frame(page, UPSTREAM_D6_JS):
        for record in records or []:
            probe = record.get("probe")
            if not probe or (visible is not None and probe not in visible):
                continue
            hits.add(probe)
            provenance.setdefault(probe, record.get("stack") or "")
    return hits, provenance


async def d1_axe(page: Any, axe_source: str) -> set[str]:
    """Upstream's three tags and ANY violation -> nearest labelled ancestor.

    Uses Axcess's pinned local axe bundle with direct injection into all frames,
    not Node's AxeBuilder package. The tag set and main-document selector
    attribution are transcribed; engine/version and integration parity are not
    claimed. No candidate-minus-Tab subtraction belongs to this detector.
    """
    for frame in page.frames:
        await frame.evaluate(axe_source)
    violations = await page.evaluate(
        """async () => (await axe.run(document, {
          runOnly: {type:'tag', values:['wcag2a','wcag2aa','wcag21aa']}
        })).violations"""
    )
    hits: set[str] = set()
    for violation in violations:
        for node in violation["nodes"]:
            probe = await page.evaluate(
                """selectors => {
                  if (!window.__a11y) throw new Error('upstream instrumentation is missing');
                  let el;
                  try { el = document.querySelector(selectors.join(' ')); }
                  catch (e) { if (e.name === 'SyntaxError') return null; throw e; }
                  return el ? window.__a11y.probeOf(el) : null;
                }""",
                node["target"],
            )
            if probe:
                hits.add(probe)
    return hits


async def d8_hover_diff(page: Any, nodes: dict[str, ProbeNode]) -> set[str]:
    """``d8HoverDiff``: two clipped screenshots, compared as bytes.

    Ours digests whole-document geometry and colour instead, which is a
    different question: this asks whether *these pixels* changed when the
    pointer arrived. The clip reaches 200px below the box because a hover often
    reveals a submenu outside it, and the 60/120 ms waits are theirs.
    """
    hits: set[str] = set()
    viewport = page.viewport_size or {"width": 1280, "height": 720}
    park_x, park_y = viewport["width"] - 2, viewport["height"] - 2

    for node in nodes.values():
        centre = node.centre
        if centre is None or node.box is None:
            continue
        if not (0 <= centre[0] <= viewport["width"] and 0 <= centre[1] <= viewport["height"]):
            continue
        x, y, w, h = node.box
        clip = {
            "x": max(0, x - 8),
            "y": max(0, y - 8),
            "width": min(viewport["width"] - max(0, x - 8), w + 16),
            "height": min(viewport["height"] - max(0, y - 8), h + 200),
        }
        if clip["width"] < 1 or clip["height"] < 1:
            continue
        await page.mouse.move(park_x, park_y)
        await page.wait_for_timeout(60)
        rest = await page.screenshot(clip=clip)
        await page.mouse.move(centre[0], centre[1])
        await page.wait_for_timeout(120)
        hovered = await page.screenshot(clip=clip)
        if rest and hovered and rest != hovered:
            hits.add(node.probe)

    await page.mouse.move(park_x, park_y)
    return hits
