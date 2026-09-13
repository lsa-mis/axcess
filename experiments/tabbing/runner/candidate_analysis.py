"""Measured cheap-detector variants; ground-truth labels never enter discovery.

These are experimental leads, not proofs of keyboard inoperability. Keep their
names separate from the upstream candidate generators and save the observations
so every rejected candidate and newly reported lead can be audited.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from audit.analyzer.keyboard.kbdiff.taborder import compute_tab_order
from experiments.tabbing.runner import upstream_candidates as upstream
from experiments.tabbing.runner.serve import page_url
from experiments.tabbing.runner.upstream_instrument import UPSTREAM_INIT_JS

UPSTREAM_NAMES = {
    "D0": "U-D0 upstream crawler candidates",
    "D1": "U-D1 upstream tagged axe attribution",
    "D2": "U-D2 upstream inline attributes",
    "D2b": "U-D2b upstream mouse handler properties",
    "D3": "U-D3 upstream missing tabindex",
    "D4": "U-D4 upstream CSS and class tokens",
    "D5": "U-D5 upstream direct CDP listeners",
    "D6": "U-D6 upstream registration shim",
    "D7": "U-D7 upstream React mouse props",
    "D8": "U-D8 upstream pixel hover difference",
}

FEATURES_JS = r"""
() => {
  const a = window.__a11y;
  if (!a) throw new Error('upstream instrumentation is missing');
  const mouse = new Set(['click','mousedown','mouseup','mouseover','mouseenter',
                         'dblclick','pointerdown','pointerup']);
  const keys = new Set(['keydown','keyup','keypress']);
  const records = a.listeners;
  const rows = [];
  for (const el of a.allElements(true)) {
    const id = el.getAttribute('data-probe');
    if (!id) continue;
    const ancestors = new Set([document, window]);
    let inert = false, closed = false;
    for (let node = el; node; ) {
      if (node.hasAttribute && node.hasAttribute('inert')) inert = true;
      const root = node.getRootNode ? node.getRootNode() : null;
      if (root && root.mode === 'closed') closed = true;
      node = node.parentElement || (root && root.host) || null;
      if (node) ancestors.add(node);
    }
    const cs = getComputedStyle(el), box = el.getBoundingClientRect();
    const visible = a.isVisible(el);
    const x = box.x + box.width / 2, y = box.y + box.height / 2;
    let centerHit = null;
    if (visible && x >= 0 && y >= 0 && x < innerWidth && y < innerHeight) {
      const root = el.getRootNode();
      const hit = root.elementFromPoint
        ? root.elementFromPoint(x, y) : document.elementFromPoint(x, y);
      centerHit = !!hit && (hit === el || el.contains(hit));
    }
    let hasKeyHandler = ['onkeydown','onkeyup','onkeypress'].some(k => typeof el[k] === 'function');
    hasKeyHandler ||= records.some(r => r.target === el && keys.has(r.type));
    for (const key of Object.keys(el)) {
      if (!key.startsWith('__reactProps$')) continue;
      const props = el[key];
      hasKeyHandler ||= !!props && ['onKeyDown','onKeyUp','onKeyPress']
        .some(k => typeof props[k] === 'function');
    }
    const delegatedTypes = [...new Set(records
      .filter(r => ancestors.has(r.target) && mouse.has(r.type)).map(r => r.type))].sort();
    const tag = el.tagName.toLowerCase();
    const native = (tag === 'a' && el.hasAttribute('href')) ||
      ['button','input','select','textarea','summary','audio','video','iframe'].includes(tag);
    const control = tag === 'label' ? el.control : null;
    const toggle = control && control.tagName === 'INPUT'
      && ['checkbox','radio'].includes(control.type);
    rows.push({id, tag, visible, inert, closed_shadow: closed,
      pointer_events_none: cs.pointerEvents === 'none', center_hit: centerHit,
      native, has_key_handler: hasKeyHandler, delegated_types: delegatedTypes,
      label_toggle: !!toggle, control_probe: control ? control.getAttribute('data-probe') : null,
      control_disabled: control ? !!control.disabled : null,
      control_visible: control ? a.isVisible(control) : null});
  }
  return rows;
}
"""

UNION = "C1 upstream D4|D5|D6, minus Tab"
UNION_HOVER = "C2 upstream D4|D5|D6|D8, minus Tab"
POINTER_GATE = "C3 union, reject inert and pointer-events:none"
CENTER_GATE = "C4 union, additionally reject blocked center"
FOCUSABLE = "C5 focusable custom mouse control, no observed key handler"
LABEL = "C6 visible label for a toggle absent from Tab"
DELEGATED = "C7 ancestor mouse listener, minus Tab"
HYBRID = "C8 union + focusable + label + ancestor leads"
HYBRID_CENTER = "C9 combined leads, additionally reject blocked center"
VARIANT_NAMES = (
    UNION,
    UNION_HOVER,
    POINTER_GATE,
    CENTER_GATE,
    FOCUSABLE,
    LABEL,
    DELEGATED,
    HYBRID,
    HYBRID_CENTER,
)


@dataclass
class CandidateVariants:
    proposed: dict[str, set[str]] = field(default_factory=dict)
    reported: dict[str, set[str]] = field(default_factory=dict)
    unknown: dict[str, set[str]] = field(default_factory=dict)
    exclusions: dict[str, list[str]] = field(default_factory=dict)


async def collect_features(page: Any) -> dict[str, dict[str, Any]]:
    """Read every frame; a failed read raises instead of becoming no candidates."""
    result: dict[str, dict[str, Any]] = {}
    for frame in page.frames:
        rows = await frame.evaluate(FEATURES_JS)
        for row in rows:
            if row["id"] in result:
                raise ValueError(f"duplicate probe identity: {row['id']}")
            result[row["id"]] = row
    return result


def build_variants(
    proposals: dict[str, set[str]],
    features: dict[str, dict[str, Any]],
    tab_ids: set[str],
    *,
    capped: bool = False,
) -> CandidateVariants:
    """Compute predeclared variants from observations, never from truth notes.

    `proposals` uses upstream family IDs (D4, D5, D6, D8). Raw proposals are
    retained for funnel evaluation. An absent probe in a capped Tab walk or a
    closed shadow tree is uncertain for the improved variants.
    """
    result = CandidateVariants()
    base = set().union(*(proposals[k] for k in ("D4", "D5", "D6")))
    hover = base | proposals["D8"]
    visible = {pid for pid, f in features.items() if f["visible"]}
    pointer_ok = {
        pid
        for pid in visible
        if not features[pid]["inert"] and not features[pid]["pointer_events_none"]
    }
    center_ok = {pid for pid in pointer_ok if features[pid]["center_hit"] is not False}
    for pid, f in features.items():
        reasons = []
        if not f["visible"]:
            reasons.append("upstream visibility test failed")
        if f["inert"]:
            reasons.append("inert element or ancestor")
        if f["pointer_events_none"]:
            reasons.append("computed pointer-events:none")
        if f["center_hit"] is False:
            reasons.append("center hit test returned another element")
        result.exclusions[pid] = reasons

    mouse_bound = (
        proposals["D5"] | proposals["D6"] | proposals.get("D2b", set()) | proposals.get("D7", set())
    )
    focusable = {pid for pid in mouse_bound & pointer_ok & tab_ids if not features[pid]["native"]}
    focus_leads = {pid for pid in focusable if not features[pid]["has_key_handler"]}
    labels = {
        pid
        for pid in pointer_ok
        if features[pid]["label_toggle"] and not features[pid]["control_disabled"]
    }
    label_unknown = {pid for pid in labels if not features[pid]["control_probe"]}
    label_leads = {
        pid for pid in labels - label_unknown if features[pid]["control_probe"] not in tab_ids
    }
    ancestors = {
        pid
        for pid in pointer_ok
        if features[pid]["delegated_types"] and not features[pid]["native"]
    }
    result.proposed = {
        UNION: base,
        UNION_HOVER: hover,
        POINTER_GATE: base & pointer_ok,
        CENTER_GATE: base & center_ok,
        FOCUSABLE: focusable,
        LABEL: labels,
        DELEGATED: ancestors,
        HYBRID: (base & pointer_ok) | focusable | labels | ancestors,
        HYBRID_CENTER: ((base & pointer_ok) | focusable | labels | ancestors) & center_ok,
    }
    result.reported = {
        UNION: base - tab_ids,
        UNION_HOVER: hover - tab_ids,
        POINTER_GATE: (base & pointer_ok) - tab_ids,
        CENTER_GATE: (base & center_ok) - tab_ids,
        FOCUSABLE: focus_leads,
        LABEL: label_leads,
        DELEGATED: ancestors - tab_ids,
    }
    combined = result.reported[POINTER_GATE] | focus_leads | label_leads | (ancestors - tab_ids)
    result.reported[HYBRID] = combined
    result.reported[HYBRID_CENTER] = combined & center_ok
    uncertain_tab = {
        pid for pid, f in features.items() if pid not in tab_ids and (capped or f["closed_shadow"])
    }
    for name in VARIANT_NAMES:
        # The first two rows preserve the standalone upstream union, including
        # its opaque-Tab limitation. The explicitly improved rows abstain.
        uncertain = set() if name in (UNION, UNION_HOVER) else result.proposed[name] & uncertain_tab
        if name in (LABEL, HYBRID, HYBRID_CENTER):
            uncertain |= label_unknown & result.proposed[name]
            if capped:
                uncertain |= label_leads & result.proposed[name]
        result.unknown[name] = uncertain
        result.reported[name] -= uncertain
    return result


@dataclass
class CandidatePageStudy:
    proposed: dict[str, set[str]]
    reported: dict[str, set[str]]
    unknown: dict[str, set[str]]
    evidence: dict[str, Any]
    timings: dict[str, float]


async def measure_candidate_page(
    factory: Any,
    path: str,
    probe_ids: list[str],
    axe_measure: Callable[[Any], Awaitable[set[str]]],
) -> CandidatePageStudy:
    """Measure upstream rules and predeclared variants in their own context.

    Timers retain navigation, Tab traversal and shared prerequisite work. The
    whole-page duration includes every compared method; it is not the cost of
    executing only a selected union. Detector-only times must not be presented
    as a complete crawl's runtime.
    """
    started = time.monotonic()
    timings: dict[str, float] = {}
    context = await factory()

    async def timed(name: str, call: Awaitable[Any]) -> Any:
        before = time.monotonic()
        value = await call
        timings[name] = round((time.monotonic() - before) * 1000, 3)
        return value

    try:
        await context.add_init_script(UPSTREAM_INIT_JS)
        page = await context.new_page()
        await page.goto(page_url(path), wait_until="load")
        await page.wait_for_timeout(80)
        timings["candidate setup and navigation"] = round((time.monotonic() - started) * 1000, 3)
        order = await timed("candidate Tab traversal", compute_tab_order(page))
        tab_ids = set(order.index)
        cdp = await context.new_cdp_session(page)
        visible = await timed("candidate visibility", upstream.visible_probes(page))
        nodes = await timed(
            "candidate pierced resolution", upstream.resolve_probe_nodes(cdp, probe_ids, page)
        )
        raw: dict[str, set[str]] = {}
        raw["D0"] = await timed(UPSTREAM_NAMES["D0"], upstream.d0_current_crawler(page))
        survey_kinds: tuple[tuple[str, upstream.PageDetector], ...] = (
            ("D2", "attrScan"),
            ("D2b", "handlerProp"),
            ("D3", "tabindexCounter"),
            ("D4", "cssLexical"),
            ("D7", "reactProps"),
        )
        for family, kind in survey_kinds:
            raw[family] = await timed(UPSTREAM_NAMES[family], upstream.survey(page, kind))
        raw["D5"] = await timed(
            UPSTREAM_NAMES["D5"], upstream.d5_cdp_listeners(cdp, nodes, visible)
        )
        raw["D6"], provenance = await timed(
            UPSTREAM_NAMES["D6"], upstream.d6_listener_shim(page, visible)
        )
        # Save static evidence before hover or axe can change the observation
        # state. This pass reads page state and does not dispatch trial input.
        features = await timed("candidate feature evidence", collect_features(page))
        raw["D8"] = await timed(UPSTREAM_NAMES["D8"], upstream.d8_hover_diff(page, nodes))
        raw["D1"] = await timed(UPSTREAM_NAMES["D1"], axe_measure(page))
        expected = set(probe_ids)
        if set(features) != expected:
            raise ValueError(f"candidate feature coverage differs from page probes: {path}")
        if any(ids - expected for ids in raw.values()):
            raise ValueError(f"upstream candidate outside page scope: {path}")

        before = time.monotonic()
        variants = build_variants(raw, features, tab_ids, capped=order.capped)
        timings["candidate variant set operations"] = round((time.monotonic() - before) * 1000, 3)
        proposed = {UPSTREAM_NAMES[family]: ids for family, ids in raw.items()}
        reported = {
            UPSTREAM_NAMES[family]: set(ids) if family == "D1" else ids - tab_ids
            for family, ids in raw.items()
        }
        unknown = {
            UPSTREAM_NAMES[family]: (ids - tab_ids if order.capped and family != "D1" else set())
            for family, ids in raw.items()
        }
        proposed.update(variants.proposed)
        reported.update(variants.reported)
        unknown.update(variants.unknown)
        for name in reported:
            reported[name] -= unknown[name]
        timings["candidate study whole page"] = round((time.monotonic() - started) * 1000, 3)
        return CandidatePageStudy(
            proposed=proposed,
            reported=reported,
            unknown=unknown,
            timings=timings,
            evidence={
                "tab_order": {
                    "index": order.index,
                    "capped": order.capped,
                    "presses": order.presses,
                },
                "features": features,
                "exclusions": variants.exclusions,
                "listener_provenance": provenance,
                "visible_probes": sorted(visible),
                "resolver": {
                    pid: {"via": node.via, "box": node.box} for pid, node in nodes.items()
                },
                "axe_version": await page.evaluate("axe.version"),
                "upstream_proposals": {family: sorted(ids) for family, ids in raw.items()},
            },
        )
    finally:
        await context.close()
