/**
 * Which element in a saved copy is each flagged occurrence, and marking it.
 *
 * The rule is: highlight an element only when the evidence names it and
 * nothing else. An occurrence carries a locator (a CSS selector, or an Alfa
 * XPath) and the element's markup as the scan saw it (the snippet).
 *
 * 1. The locator, checked against the markup. A selector that matches one
 *    element whose markup agrees, or that matches several of which exactly
 *    one agrees, names it. Alfa records the element itself as JSON (its tag,
 *    its attributes and an XPath) rather than as markup: the element the path
 *    lands on names it when its tag and attributes are the recorded ones, and
 *    otherwise the one element in the page with that tag and those attributes
 *    does (Alfa takes its own capture, so a path can land elsewhere in the
 *    saved copy).
 * 2. Else the markup alone, when it appears in exactly one place.
 * 3. Else nothing. Markup that appears in several places, with no locator to
 *    tell them apart, is "ambiguous", and a locator and markup that match
 *    nothing are "missing". Both are counted and said, never guessed.
 *
 * An image from the Images with text check carries no selector, and an AI
 * review finding carries one only its analyzer can read (`a[ord=6]`). The
 * saved copy is the document both read, so the server names the element by
 * its place among elements of its kind (the 3rd of 12 `img`), and it is
 * outlined only when this document has those 12 and the 3rd one is the
 * recorded element: the same address and alt text, or the same markup.
 *
 * The inspector used to take the first element whose markup looked the same
 * whenever the locator did not verify, so identical-looking elements (a row
 * of cards, a repeated link) could be outlined for an occurrence that was
 * elsewhere. Every located element is now the only candidate.
 *
 * Pure DOM, no React: the verification script in the scratch tooling and the
 * inspector run the same code.
 */

import type { ElementPlace, ImageLocator } from "../api/types";

export type Target = {
  selector: string | null;
  snippet: string | null;
  revealedBy: string | null;
  /** The captured state this finding is visible in, when one was stored. */
  stateKey: string | null;
  /** Set for an image from the Images with text check, which has no selector. */
  image?: ImageTarget;
  /** For an AI review finding, the element the server worked out it is about. */
  place?: ElementPlace | null;
  /**
   * The length the check cut its element code (the snippet) to, without
   * marking the cut: a snippet exactly this long is the start of a longer
   * element's code, and matches as a prefix. See ``snippetCutFor``.
   */
  cutAt?: number | null;
};

/**
 * How many characters of an element's code each browser check keeps
 * (``outerHTML.slice(0, n)`` in ``src/audit/analyzer/<check>/probe.py``).
 * The checks do not mark the cut, so without this a longer element's
 * snippet matched nothing, even where its selector named one element.
 */
const SNIPPET_CUTS: Record<string, number> = {
  focus: 300,
  keyboard: 240,
  responsive: 240,
  visual: 240,
};

/** The snippet length a pipeline cuts to, or null when it keeps the whole element. */
export function snippetCutFor(pipeline: string): number | null {
  return SNIPPET_CUTS[pipeline] ?? null;
}

export type ImageTarget = {
  locator: ImageLocator | null;
  /** The alt text the scan recorded: null when the attribute was missing. */
  alt: string | null;
};

export type Located =
  /** One element, or several for an Alfa record that names several. */
  | { status: "found"; elements: Element[]; how: "selector" | "xpath" | "markup" | "place" }
  | { status: "ambiguous"; candidates: number }
  | { status: "missing" };

/** One highlighted element, in document order, and the occurrences it stands for. */
export type HighlightStep = { targets: number[] };

export type HighlightResult = {
  srcDoc: string;
  /** Distinct elements highlighted. */
  found: number;
  /** Occurrences located (several can share one element). */
  located: number;
  /** Occurrences asked for. */
  total: number;
  /** Occurrences whose markup appears in several places and could not be pinned. */
  ambiguous: number;
  /** One entry per highlighted element, in document order: what Previous / Next step through. */
  steps: HighlightStep[];
};

/** Ceiling on elements examined by one markup walk: far above any real page. */
const WALK_CAP = 20_000;
/** Cheap exact-prefix check before any full markup comparison. */
const SNIPPET_HEAD = 64;
/** Snippets at the storage cap were cut mid-markup; they match by normalized prefix. */
const TRUNCATED_SNIPPET_LENGTH = 3900;
/**
 * The AI review keeps 300 characters of markup and ends a longer element's
 * with "…". No whole element's markup ends that way (it ends with a tag), so
 * such a snippet matches by prefix; a prefix this long names one element or,
 * repeated, several, which the steps above then count as ambiguous.
 */
const CUT_SNIPPET_MIN = 200;

/** The class every outlined element carries, so the frame can be walked in order. */
export const HIGHLIGHT_CLASS = "axcess-inspect-highlight";

/**
 * Every flagged element: a dashed red outline and no fill, so a page with
 * many, or with one nested in another, stays readable and no tint stacks on
 * another. The one the reader is on is set apart by `markCurrent`.
 */
const FLAGGED_OUTLINE = "#be001e";

/**
 * The one the reader is on: a solid UMich-blue outline, and over it a box
 * (`spotlight`) with a maize ring, a numbered label, and the rest of the
 * page dimmed. Blue against yellow stays distinct for red- and green-weak
 * eyes, and solid against dashed, the label and the dimming differ in shape
 * too, so colour is never the only cue.
 */
const CURRENT_OUTLINE = "#00274c";
const CURRENT_RING = "#ffcb05";
const CURRENT_DIM = "rgba(0, 39, 76, 0.3)";
/** A box at least this big, so a tiny or zero-size element still shows. */
const SPOTLIGHT_MIN = 18;
const SPOTLIGHT_ID = "axcess-spotlight";

/** Locate each target in ``doc`` by the rules above; one result per target, in order. */
export function locateTargets(doc: Document, targets: Target[]): Located[] {
  const results: (Located | null)[] = targets.map((target) =>
    target.image
      ? locateImage(doc, target.image)
      : target.place
        ? (locateByPlace(doc, target.place, target.snippet, target.cutAt) ?? locateByLocator(doc, target))
        : locateByLocator(doc, target),
  );
  // One walk serves every target the locator could not settle.
  const pending = targets
    .map((target, index) => ({ target, index }))
    .filter(({ index }) => results[index] === null);
  if (pending.length) {
    const matches = markupMatches(
      doc,
      pending.map(({ target }) => target),
    );
    pending.forEach(({ index }, i) => {
      const candidates = matches[i];
      results[index] =
        candidates.length === 1
          ? { status: "found", elements: [candidates[0]], how: "markup" }
          : candidates.length > 1
            ? { status: "ambiguous", candidates: candidates.length }
            : { status: "missing" };
    });
  }
  return results as Located[];
}

/** The located element for one target, or null: for scrolling to it without highlights. */
export function findTargetElement(doc: Document, target: Target): Element | null {
  const [located] = locateTargets(doc, [target]);
  return located.status === "found" ? located.elements[0] : null;
}

/** How many of ``targets`` are located in ``html``, without re-serializing. */
export function countFound(html: string | null, targets: Target[]): number {
  if (!html || targets.length === 0) return 0;
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    return locateTargets(doc, targets).filter((located) => located.status === "found").length;
  } catch {
    return 0;
  }
}

/**
 * The ``srcDoc`` for the saved-copy frame with the targets outlined. The
 * outline is part of the markup, so it shows even when the sandbox makes the
 * frame's document opaque. ``steps`` lists the outlined elements in document
 * order with the occurrences each stands for, so the toolbar can say which
 * one the reader is on.
 */
export function buildHighlightedHtml(html: string | null, targets: Target[]): HighlightResult {
  const none = { found: 0, located: 0, total: targets.length, ambiguous: 0, steps: [] };
  if (!html) return { srcDoc: "", ...none };
  if (targets.length === 0) return { srcDoc: html, ...none };
  try {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const located = locateTargets(doc, targets);
    const byElement = new Map<Element, number[]>();
    located.forEach((result, index) => {
      if (result.status !== "found") return;
      for (const element of result.elements) {
        const list = byElement.get(element);
        if (list) list.push(index);
        else byElement.set(element, [index]);
      }
    });
    const ambiguous = located.filter((result) => result.status === "ambiguous").length;
    if (byElement.size === 0) return { srcDoc: html, ...none, ambiguous };
    const ordered = [...byElement.keys()].sort(documentOrder);
    for (const element of ordered) {
      if (element instanceof HTMLElement || element instanceof SVGElement) markElement(element);
    }
    return {
      srcDoc: "<!doctype html>" + doc.documentElement.outerHTML,
      found: ordered.length,
      located: located.filter((result) => result.status === "found").length,
      total: targets.length,
      ambiguous,
      steps: ordered.map((element) => ({ targets: byElement.get(element) ?? [] })),
    };
  } catch {
    return { srcDoc: html, ...none };
  }
}

/** Outline a flagged element and keep it visible whatever the page's own styles say. */
export function markElement(el: HTMLElement | SVGElement): void {
  el.classList.add(HIGHLIGHT_CLASS);
  // The whole page is not outlined: a ring round the edge of the saved copy
  // marks nothing in it (see ``spotlight``).
  if (isWholePage(el)) return;
  // Inset, not outset: a flagged element filling an `overflow: hidden`
  // ancestor (the image-tile pattern) has an outset ring drawn entirely
  // outside the clip box, so it is never painted.
  el.style.setProperty("outline", `2px dashed ${FLAGGED_OUTLINE}`, "important");
  el.style.setProperty("outline-offset", "-2px", "important");
  el.style.setProperty("scroll-margin-top", "96px", "important");
  forceVisible(el);
  // An ancestor can hide the element whatever is set on it (opacity
  // composites), so the chain is cleared too.
  let parent = el.parentElement;
  while (parent && parent !== el.ownerDocument.documentElement) {
    forceVisible(parent);
    openSection(parent, el);
    parent = parent.parentElement;
  }
}

/** Set on a ``<details>`` section the inspector opened (see ``openSection``). */
const OPENED = "data-axcess-opened";

/**
 * Open ``section`` when it is a closed ``<details>`` that hides ``el``.
 *
 * A closed section shows only its summary, so a flagged element inside it
 * has no box of its own, and the numbered box landed somewhere else. This
 * is a saved copy, not the site: opening it changes nothing a visitor sees,
 * and it is what a reader would do on the live page to reach the element.
 * The table under the toolbar says the section was opened, so the reader
 * knows the page does not start that way. Rejected: leaving it closed and
 * saying so, which shows the reader nothing. An element in the section's own
 * summary shows while it is closed, so that section stays as it is.
 */
function openSection(section: Element, el: Element): void {
  if (section.tagName.toLowerCase() !== "details" || section.hasAttribute("open")) return;
  const summary = Array.from(section.children).find((child) => child.tagName.toLowerCase() === "summary");
  if (summary?.contains(el)) return;
  section.setAttribute("open", "");
  section.setAttribute(OPENED, "");
}

/** Set the element the reader is on apart from the other flagged ones, or put it back. */
export function markCurrent(el: HTMLElement | SVGElement, current: boolean): void {
  if (current) el.setAttribute("data-axcess-current", "");
  else el.removeAttribute("data-axcess-current");
  if (isWholePage(el)) return;
  el.style.setProperty(
    "outline",
    current ? `3px solid ${CURRENT_OUTLINE}` : `2px dashed ${FLAGGED_OUTLINE}`,
    "important",
  );
  el.style.setProperty("outline-offset", current ? "-3px" : "-2px", "important");
}

function isWholePage(el: Element): boolean {
  return el === el.ownerDocument.documentElement || el === el.ownerDocument.body;
}

/**
 * Draw a box over ``el`` in its own document, labelled (``5 of 7``), with the
 * rest of the page dimmed: the "you are here" of the saved copy.
 *
 * An outline on the element itself vanished on a tiny or empty element (a
 * two-pixel link, a zero-width icon) and was clipped by `overflow: hidden`
 * ancestors, so the reader stepped to "Flagged element 5 of 7" and saw
 * nothing. The box is drawn on the page's root, over everything, at least
 * ``SPOTLIGHT_MIN`` pixels on each side and centred on the element. It is
 * checked against the element every frame, so it follows the element through
 * a resize, a late stylesheet or a scroll, and ``onPlace`` is called whenever
 * the element's size changes so a description of it can follow too. Null
 * removes it.
 *
 * An app-style page scrolls a panel of its own (a sidebar, a dialog), not the
 * window. The box once followed only a resize, so a flagged element in such a
 * panel scrolled away and left the box behind, stuck at the top or bottom of
 * the panel over something else. Now the box covers only the part of the
 * element its panels show, and is hidden while none of it is shown.
 *
 * An element with no box of its own is marked where ``boxPlace`` says, on
 * what stands for it.
 *
 * A link that wraps onto a second line gets a ring on each line, with the
 * label on the first. One rectangle around it covered both lines and the
 * words beside them, so the reader could not see which words are the link.
 * The dimming is drawn once, around all the lines: a dimmed ring per line
 * would dim the other lines, and stack. Rejected: an outline that follows
 * the text's shape exactly, which needs a drawn path per line and says no
 * more than the rings do.
 *
 * An element placed off the screen until it has focus (a skip link) is shown
 * as it looks focused (``showAsFocused``). One that stays off the screen gets
 * no box: a box off the screen shows the reader nothing.
 *
 * A part of the page that cuts off what does not fit without scrolling (a
 * carousel's window, a menu bar: ``overflow: hidden``) cuts the box too, so
 * it covers only the part that shows, and there is none when nothing shows.
 * The whole box was drawn over the slide or menu items beside it, marking
 * what the reader saw instead of the flagged element. Rejected: scrolling
 * such a part to the element, which would show the page as no visitor sees
 * it (see ``scrollPanels``), and drawing the box anyway, as before.
 *
 * The whole page (``<html>``, ``<body>``) gets no box. A box around the whole
 * document dimmed nothing, since nothing is outside it, and put its label off
 * the top of the view, so it looked like a stray frame. Rejected: a box
 * around the frame's view, which would say the element is what happens to be
 * on screen. The table under the toolbar says it is the whole page instead.
 */
export function spotlight(
  el: HTMLElement | null,
  label: string,
  doc?: Document,
  onPlace?: (el: HTMLElement) => void,
): void {
  const owner = el?.ownerDocument ?? doc;
  if (!owner) return;
  const view = owner.defaultView;
  owner.getElementById(SPOTLIGHT_ID)?.remove();
  stopFollowing.get(owner)?.();
  stopFollowing.delete(owner);
  if (!el || !view) return;

  const box = owner.createElement("div");
  box.id = SPOTLIGHT_ID;
  box.setAttribute("aria-hidden", "true");
  const tag = owner.createElement("div");
  tag.textContent = label;
  box.appendChild(tag);
  owner.documentElement.appendChild(box);
  let panelsOf: Element | null = null;
  let panels: HTMLElement[] = [];

  let lastSize: string | null = null;
  let lastPlace: string | null = null;
  let triedFocus = false;
  const place = () => {
    // Once per box, and again only when asked for (Previous, Next, Jump):
    // when a stylesheet arriving late moves it off the screen, too.
    if (!triedFocus && hidesUntilFocused(el)) {
      triedFocus = true;
      showAsFocused(el);
    }
    const own = el.getBoundingClientRect();
    const { on, lines, note } = boxPlace(el);
    const size = `${own.width},${own.height},${note}`;
    if (size !== lastSize) {
      lastSize = size;
      onPlace?.(el);
    }
    if (on !== panelsOf) {
      panelsOf = on;
      panels = scrollPanels(on);
    }
    const parts = drawsNoBox(note)
      ? []
      : lines.map((line) => shownPart(line, panels)).filter((part): part is ShownPart => part !== null);
    const where = parts.length
      ? [...parts.flatMap((part) => [part.left, part.top, part.width, part.height]), view.scrollX, view.scrollY].join()
      : "hidden";
    if (where === lastPlace) return;
    lastPlace = where;
    if (parts.length === 0) {
      box.style.setProperty("display", "none", "important");
      return;
    }
    // Page coordinates, each at least SPOTLIGHT_MIN on each side.
    const pieces = parts.map((part) => {
      let { width, height } = part;
      let left = part.left + view.scrollX;
      let top = part.top + view.scrollY;
      if (width < SPOTLIGHT_MIN) {
        left -= (SPOTLIGHT_MIN - width) / 2;
        width = SPOTLIGHT_MIN;
      }
      if (height < SPOTLIGHT_MIN) {
        top -= (SPOTLIGHT_MIN - height) / 2;
        height = SPOTLIGHT_MIN;
      }
      return { left, top, width, height };
    });
    const left = Math.min(...pieces.map((piece) => piece.left));
    const top = Math.min(...pieces.map((piece) => piece.top));
    const width = Math.max(...pieces.map((piece) => piece.left + piece.width)) - left;
    const height = Math.max(...pieces.map((piece) => piece.top + piece.height)) - top;
    const pad = 4;
    const ring = {
      "box-sizing": "border-box",
      border: `3px solid ${CURRENT_OUTLINE}`,
      "border-radius": "4px",
    };
    const single = pieces.length === 1;
    // One piece: the box is the ring. Several (a wrapped link): the box only
    // dims around them all, and each line gets a ring of its own.
    setStyles(box, {
      display: "block",
      position: "absolute",
      left: `${left - pad}px`,
      top: `${top - pad}px`,
      width: `${width + pad * 2}px`,
      height: `${height + pad * 2}px`,
      ...(single ? ring : { "box-sizing": "border-box", border: "0", "border-radius": "4px" }),
      "box-shadow": single
        ? `0 0 0 3px ${CURRENT_RING}, 0 0 0 100vmax ${CURRENT_DIM}`
        : `0 0 0 100vmax ${CURRENT_DIM}`,
      "pointer-events": "none",
      "z-index": "2147483647",
      margin: "0",
      padding: "0",
    });
    for (const old of Array.from(box.querySelectorAll("[data-axcess-line]"))) old.remove();
    if (!single) {
      // As far out as the one-piece ring, so no ring covers the text.
      const linePad = pad;
      // Inside the box, which has no border: offsets from its padding edge.
      for (const piece of pieces) {
        const line = owner.createElement("div");
        line.setAttribute("data-axcess-line", "");
        setStyles(line, {
          position: "absolute",
          left: `${piece.left - linePad - (left - pad)}px`,
          top: `${piece.top - linePad - (top - pad)}px`,
          width: `${piece.width + linePad * 2}px`,
          height: `${piece.height + linePad * 2}px`,
          ...ring,
          "box-shadow": `0 0 0 3px ${CURRENT_RING}`,
          margin: "0",
          padding: "0",
        });
        box.appendChild(line);
      }
    }
    // The label sits above the first line's box, or inside its top when that
    // is at the top of the frame's view. After the lines, so it is drawn
    // over their rings.
    const first = pieces[0];
    const above = first.top - view.scrollY - pad > 30;
    const labelLeft = single ? -3 : first.left - pad - (left - pad);
    const labelTop = single ? 0 : first.top - pad - (top - pad);
    setStyles(tag, {
      position: "absolute",
      left: `${labelLeft}px`,
      top: `${above ? labelTop - 29 : labelTop}px`,
      "z-index": "1",
      background: CURRENT_OUTLINE,
      color: "#ffffff",
      font: "600 14px/1.5 system-ui, -apple-system, 'Segoe UI', sans-serif",
      "letter-spacing": "normal",
      "text-transform": "none",
      padding: "2px 8px",
      "border-radius": "3px",
      "white-space": "nowrap",
      "box-shadow": `0 0 0 2px ${CURRENT_RING}`,
    });
  };
  // Every frame, not on events: a panel's scroll, a reflow when the live
  // site's stylesheets and fonts arrive, and an animation all move the
  // element, and no single event reports them all. Nothing is written unless
  // the element moved. The frames are the inspector's own: the saved copy is
  // sandboxed without scripts, so nothing scheduled on its window ever runs.
  // It stops once the saved copy is replaced or closed (it has no window).
  let frame = 0;
  const follow = () => {
    if (!owner.defaultView || !el.isConnected || !box.isConnected) return;
    place();
    frame = requestAnimationFrame(follow);
  };
  follow();
  stopFollowing.set(owner, () => {
    cancelAnimationFrame(frame);
    undoFocusStyle(el);
  });
}

const stopFollowing = new WeakMap<Document, () => void>();

/**
 * The elements between ``el`` and the page that scroll on their own (a
 * sidebar, a dialog, a table), innermost first. The window is not one: the
 * frame scrolls that itself. Only ``auto`` and ``scroll`` count, the panels a
 * reader can scroll; a ``hidden`` one is often a closed menu or a slider,
 * and scrolling it would show the page as no visitor sees it.
 */
export function scrollPanels(el: Element): HTMLElement[] {
  const doc = el.ownerDocument;
  const view = doc.defaultView;
  if (!view) return [];
  const panels: HTMLElement[] = [];
  const scrolls = (style: CSSStyleDeclaration) =>
    /(auto|scroll|overlay)/.test(`${style.overflowX} ${style.overflowY}`);
  // The body's overflow scrolls the window unless the root sets its own.
  const bodyScrolls = view.getComputedStyle(doc.documentElement).overflow !== "visible";
  if (view.getComputedStyle(el).position === "fixed") return panels;
  for (let node = el.parentElement; node && node !== doc.documentElement; node = node.parentElement) {
    if (node === doc.body && !bodyScrolls) break;
    const style = view.getComputedStyle(node);
    if (scrolls(style)) panels.push(node);
    // A fixed element is out of every panel above it.
    if (style.position === "fixed") break;
  }
  return panels;
}

/**
 * Why the box is not simply around the flagged element itself, for the table
 * under the toolbar. Null when it is.
 *
 * - ``contents``: styled ``display: contents``, so only what it holds is
 *   drawn. The box goes around that.
 * - ``list-box``: an ``<option>`` of a closed list box (``<select>``). The box
 *   goes on the list box.
 * - ``image-map``: an ``<area>`` of an image map. The box goes on the part of
 *   its image the area covers.
 * - ``whole-page``: ``<html>`` or ``<body>``, as for a rule about the page
 *   itself (axe's html-has-lang). No box and no dimming (see ``spotlight``).
 * - ``focus-only``: off the screen until it has focus, as a skip link is.
 *   Shown, and boxed, as it looks focused (``showAsFocused``).
 * - ``off-screen``: off the screen, and focus does not bring it back. No box.
 * - ``part-clipped``: a part of the page around it that does not scroll (a
 *   carousel, a menu bar) cuts part of it off. The box covers what shows.
 * - ``clipped``: such a part cuts all of it off. No box.
 * - ``opened``: it is inside a closed ``<details>`` section, which the
 *   inspector opened in the saved copy (see ``openSection``).
 * - ``hidden``: not displayed in the saved copy (``display: none``), as in a
 *   tab that was not open. No box: it has no place on the page to mark, and
 *   showing it would change the page around it. Its page states may show it.
 */
export type BoxNote =
  | "contents"
  | "list-box"
  | "image-map"
  | "whole-page"
  | "focus-only"
  | "off-screen"
  | "part-clipped"
  | "clipped"
  | "opened"
  | "hidden";

/** The notes for which no box is drawn at all. */
export function drawsNoBox(note: BoxNote | null): boolean {
  return note === "whole-page" || note === "off-screen" || note === "clipped" || note === "hidden";
}

/** A rectangle in the frame's view. */
export type BoxRect = { left: number; top: number; right: number; bottom: number; width: number; height: number };

/**
 * Where the numbered box goes for ``el``: the element it is drawn over (the
 * flagged one, or what shows for it), the rectangle, and why when it is not
 * the element's own.
 *
 * An element without a box of its own reports an empty rectangle at the top
 * left of the frame, and the box used to jump there, over whatever the page
 * had in that corner. Rejected: drawing no box for these. The reader can see
 * what stands for each one (the buttons a ``display: contents`` wrapper holds,
 * the list box an option is in, the hotspot of an image map), so the box goes
 * there and the table says so in words. Not colour or position alone: WCAG
 * 2.2 SC 1.3.3 Sensory Characteristics (Level A), paraphrased, says
 * instructions do not rely on shape or location alone.
 */
export function boxPlace(el: Element): BoxPlace {
  const placed = boxPlaceOf(el);
  const lines = placed.lines ?? [placed.rect];
  if (drawsNoBox(placed.note)) return { ...placed, lines };
  // Cut to what the parts of the page around it show (see ``clippingParts``).
  const parts = clippingParts(placed.on);
  if (parts.length === 0) return { ...placed, lines };
  const shown = lines.map((line) => clipTo(line, parts)).filter((line): line is BoxRect => line !== null);
  if (shown.length === 0) return { ...placed, lines: [], note: "clipped" };
  const rect = clipTo(placed.rect, parts) ?? shown[0];
  const cut = rect.width < placed.rect.width - 0.5 || rect.height < placed.rect.height - 0.5;
  return { ...placed, rect, lines: shown, note: placed.note ?? (cut ? "part-clipped" : null) };
}

/**
 * The parts of the page around ``el`` that cut it off without scrolling
 * (``overflow: hidden`` or ``clip``), and on which axes. Only those that
 * cut it off in the browser: an element placed by ``position: absolute`` is
 * cut off only by its positioned ancestor (its containing block) and those
 * above it, and one placed by ``position: fixed`` by none. The body's
 * overflow belongs to the window unless the root sets its own.
 *
 * Only those inside the nearest panel that scrolls (see ``scrollPanels``):
 * what a part outside it cuts off (an app's page, fixed to the window's
 * height, around its scrolling sidebar) comes into view as the panel
 * scrolls, as it would in the window.
 */
function clippingParts(el: Element): { node: Element; x: boolean; y: boolean }[] {
  const doc = el.ownerDocument;
  const view = doc.defaultView;
  if (!view) return [];
  const parts: { node: Element; x: boolean; y: boolean }[] = [];
  const bodyIsWindow = view.getComputedStyle(doc.documentElement).overflow === "visible";
  let position = view.getComputedStyle(el).position;
  if (position === "fixed") return parts;
  let placedAbove = position === "absolute";
  for (let node = el.parentElement; node && node !== doc.documentElement; node = node.parentElement) {
    const style = view.getComputedStyle(node);
    if (placedAbove) {
      if (!holdsPlacedElements(style)) continue;
      placedAbove = false;
    }
    if (node === doc.body && bodyIsWindow) break;
    const x = /hidden|clip/.test(style.overflowX);
    const y = /hidden|clip/.test(style.overflowY);
    if (x || y) parts.push({ node, x, y });
    // A panel that scrolls on one axis can still cut off on the other.
    if (/(auto|scroll|overlay)/.test(`${style.overflowX} ${style.overflowY}`)) break;
    position = style.position;
    if (position === "fixed") break;
    if (position === "absolute") placedAbove = true;
  }
  return parts;
}

/** True when an element is the containing block of absolutely placed elements inside it. */
function holdsPlacedElements(style: CSSStyleDeclaration): boolean {
  return (
    style.position !== "static" ||
    style.transform !== "none" ||
    style.perspective !== "none" ||
    style.filter !== "none" ||
    /paint|layout|strict|content/.test(style.contain) ||
    /transform|perspective|filter/.test(style.willChange)
  );
}

/** ``rect`` cut to each part's inside (its padding box), or null when nothing is left. */
function clipTo(rect: BoxRect, parts: { node: Element; x: boolean; y: boolean }[]): BoxRect | null {
  let { left, top, right, bottom } = rect;
  for (const { node, x, y } of parts) {
    const outer = node.getBoundingClientRect();
    const insideLeft = outer.left + node.clientLeft;
    const insideTop = outer.top + node.clientTop;
    if (x) {
      left = Math.max(left, insideLeft);
      right = Math.min(right, insideLeft + node.clientWidth);
    }
    if (y) {
      top = Math.max(top, insideTop);
      bottom = Math.min(bottom, insideTop + node.clientHeight);
    }
  }
  // Equal edges still count: an empty element is shown where it sits.
  if (right < left || bottom < top) return null;
  return plainRect({ left, top, right, bottom });
}

/**
 * Where the box goes: the element it is drawn over, the whole rectangle, one
 * rectangle per line for an inline element that wraps (see ``spotlight``),
 * and why when it is not simply the element's own box.
 */
export type BoxPlace = { on: Element; rect: BoxRect; lines: BoxRect[]; note: BoxNote | null };

function boxPlaceOf(el: Element): Omit<BoxPlace, "lines"> & { lines?: BoxRect[] } {
  const doc = el.ownerDocument;
  const tag = el.tagName.toLowerCase();
  if (isWholePage(el)) {
    return { on: el, rect: plainRect(el.getBoundingClientRect()), note: "whole-page" };
  }
  if (tag === "area") {
    const image = mapImage(el);
    if (image) return { on: image, rect: areaRect(el, image), note: "image-map" };
  }
  if (el.getClientRects().length === 0) {
    if (doc.defaultView?.getComputedStyle(el).display === "contents") {
      // A range over its children is the box every one of them draws.
      const range = doc.createRange();
      range.selectNodeContents(el);
      const rect = range.getBoundingClientRect();
      if (rect.width > 0 || rect.height > 0) return { on: el, rect: plainRect(rect), note: "contents" };
    }
    if (tag === "option" || tag === "optgroup") {
      const select = el.closest("select");
      if (select && select.getClientRects().length > 0) {
        return { on: select, rect: plainRect(select.getBoundingClientRect()), note: "list-box" };
      }
    }
    if (notDisplayed(el)) return { on: el, rect: plainRect(el.getBoundingClientRect()), note: "hidden" };
  }
  if (el.hasAttribute(FOCUS_STYLED)) return { on: el, rect: plainRect(el.getBoundingClientRect()), note: "focus-only" };
  if (isOffScreen(el)) return { on: el, rect: plainRect(el.getBoundingClientRect()), note: "off-screen" };
  const note = el.parentElement?.closest(`details[${OPENED}]`) ? "opened" : null;
  return { on: el, rect: plainRect(el.getBoundingClientRect()), lines: lineRects(el), note };
}

/** True when ``el`` or an element around it is ``display: none``. */
function notDisplayed(el: Element): boolean {
  const view = el.ownerDocument.defaultView;
  if (!view) return false;
  for (let node: Element | null = el; node; node = node.parentElement) {
    if (view.getComputedStyle(node).display === "none") return true;
  }
  return false;
}

/**
 * The lines an inline element (a link in a sentence) is drawn on, when it
 * wraps onto more than one; else undefined. Empty fragments at a line's end
 * are left out.
 */
function lineRects(el: Element): BoxRect[] | undefined {
  if (el.ownerDocument.defaultView?.getComputedStyle(el).display !== "inline") return undefined;
  const lines = Array.from(el.getClientRects()).filter((rect) => rect.width > 0 && rect.height > 0);
  return lines.length > 1 ? lines.map(plainRect) : undefined;
}

/**
 * True when ``el`` lies wholly above or left of the page, where no scrolling
 * reaches (``left: -9999px``, the usual way to hide a skip link).
 */
function isOffScreen(el: Element): boolean {
  const view = el.ownerDocument.defaultView;
  if (!view) return false;
  const rect = el.getBoundingClientRect();
  // An empty element at the page's top left is where it sits, not off it.
  return (rect.left < 0 && rect.right + view.scrollX <= 0) || (rect.top < 0 && rect.bottom + view.scrollY <= 0);
}

/**
 * True when ``el`` may be one of the elements a page hides until it has
 * focus: off the screen, or cut to nothing by its own ``clip`` or
 * ``clip-path`` (the "visually hidden until focused" pattern).
 */
function hidesUntilFocused(el: Element): boolean {
  if (el.hasAttribute(FOCUS_STYLED) || isWholePage(el)) return false;
  const style = el.ownerDocument.defaultView?.getComputedStyle(el);
  if (!style) return false;
  return isOffScreen(el) || (style.clip !== "auto" && style.clip !== "") || style.clipPath !== "none";
}

/** Set on an element while it is shown with its focus styles. */
const FOCUS_STYLED = "data-axcess-focus-style";
/** Each such element's own inline styles before, to put back. */
const focusStyleUndo = new WeakMap<Element, { name: string; value: string; priority: string }[]>();

/**
 * Show ``el`` as it looks when it has focus, so the box can go where a
 * keyboard user sees it. True when that brings it on screen.
 *
 * A skip link is placed off the screen until it has keyboard focus, and the
 * box followed it there, so the reader saw nothing. The saved copy runs no
 * scripts, but the inspector can still call ``focus()`` on its elements.
 * Focus alone was rejected: it stays only while the saved copy has the
 * reader's focus, so it would have to take their focus from the inspector
 * and keep it, and a keyboard or screen reader user would find themselves
 * inside the saved copy without having moved there. No WCAG criterion is
 * about a tool moving focus by itself; it would break the order the reader
 * moves through the inspector in (SC 2.4.3 Focus Order, Level A,
 * paraphrased). Instead, in one step with no drawing
 * in between: note where the reader's focus is, focus the element, read
 * which of its styles focus changes, and put the reader's focus straight
 * back. The changed styles are then set on the element itself, so it stays
 * as it looks focused while the box is on it, and is put back when the box
 * moves on. Only the element's own styles are copied, not those focus
 * changes on its parents (``:focus-within``). The table under the toolbar
 * says it shows only with keyboard focus.
 *
 * Focus still moves for that instant, so the inspector's focused control
 * gets blur and focus events; nothing is done while the reader types in a
 * field or has a list open, which a blur would close.
 *
 * Rejected, too: saying it is off the screen and drawing no box. That tells
 * the reader nothing about where a keyboard user meets it, and it is used
 * only when focus does not bring the element on screen.
 */
function showAsFocused(el: Element): boolean {
  const doc = el.ownerDocument;
  const view = doc.defaultView;
  if (!view || !("focus" in el)) return false;
  const focusable = el as HTMLElement;
  const host = view.frameElement?.ownerDocument ?? null;
  const hostFocus = host?.activeElement ?? null;
  // Not while the reader is typing or has a list open: taking focus, even for
  // an instant, would close the list. The next Previous, Next or Jump tries
  // again.
  if (hostFocus && (hostFocus.getAttribute("aria-expanded") === "true" || isEditable(hostFocus))) return false;
  const frameFocus = doc.activeElement;
  const before = styleSnapshot(view.getComputedStyle(el));
  let after: Map<string, string> | null = null;
  try {
    // focusVisible asks for the page's :focus-visible styles too, where the
    // browser supports it.
    focusable.focus({ preventScroll: true, focusVisible: true } as FocusOptions);
    if (doc.activeElement === el) after = styleSnapshot(view.getComputedStyle(el));
  } finally {
    focusable.blur();
    if (frameFocus instanceof view.HTMLElement && frameFocus !== doc.body && frameFocus !== el) {
      frameFocus.focus({ preventScroll: true });
    }
    if (host) {
      if (hostFocus && hostFocus !== host.body && "focus" in hostFocus) {
        (hostFocus as HTMLElement).focus({ preventScroll: true });
      } else if (host.activeElement && host.activeElement !== host.body && "blur" in host.activeElement) {
        (host.activeElement as HTMLElement).blur();
      }
    }
  }
  if (!after) return false;
  const style = (el as HTMLElement | SVGElement).style;
  const undo: { name: string; value: string; priority: string }[] = [];
  for (const [name, value] of after) {
    // The outline is the inspector's own mark; a transition would only
    // replay the change.
    if (before.get(name) === value || name.startsWith("outline") || name.startsWith("transition")) continue;
    undo.push({ name, value: style.getPropertyValue(name), priority: style.getPropertyPriority(name) });
    style.setProperty(name, value, "important");
  }
  if (undo.length === 0) return false;
  focusStyleUndo.set(el, undo);
  el.setAttribute(FOCUS_STYLED, "");
  if (isOffScreen(el)) {
    undoFocusStyle(el);
    return false;
  }
  return true;
}

function isEditable(el: Element): boolean {
  const tag = el.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || (el as HTMLElement).isContentEditable === true;
}

/** Put back the element's own styles after ``showAsFocused``. */
function undoFocusStyle(el: Element): void {
  const undo = focusStyleUndo.get(el);
  if (!undo) return;
  const style = (el as HTMLElement | SVGElement).style;
  for (const { name, value, priority } of undo) {
    if (value) style.setProperty(name, value, priority);
    else style.removeProperty(name);
  }
  focusStyleUndo.delete(el);
  el.removeAttribute(FOCUS_STYLED);
}

function styleSnapshot(style: CSSStyleDeclaration): Map<string, string> {
  const out = new Map<string, string>();
  for (let i = 0; i < style.length; i += 1) {
    const name = style[i];
    out.set(name, style.getPropertyValue(name));
  }
  return out;
}

function plainRect(rect: DOMRect | Omit<BoxRect, "width" | "height">): BoxRect {
  const { left, top, right, bottom } = rect;
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

/** The image an ``<area>``'s map belongs to (``<img usemap="#name">``), or null. */
function mapImage(area: Element): Element | null {
  const map = area.closest("map");
  const name = map?.getAttribute("name") || map?.id;
  if (!map || !name) return null;
  const images = Array.from(map.ownerDocument.querySelectorAll("img[usemap], object[usemap]"));
  // HTML compares the name after the "#" without regard to ASCII case.
  const wanted = `#${name.toLowerCase()}`;
  return images.find((image) => image.getAttribute("usemap")?.trim().toLowerCase() === wanted) ?? null;
}

/**
 * The part of ``image`` an ``<area>`` covers: the bounding box of its shape,
 * in the image's own pixels from its top left, kept inside the image. The
 * whole image for ``default``, and for coordinates it cannot read.
 */
function areaRect(area: Element, image: Element): BoxRect {
  const outer = image.getBoundingClientRect();
  const style = image.ownerDocument.defaultView?.getComputedStyle(image);
  const left = outer.left + image.clientLeft + parseFloat(style?.paddingLeft ?? "0");
  const top = outer.top + image.clientTop + parseFloat(style?.paddingTop ?? "0");
  const whole = plainRect(outer);
  const shape = (area.getAttribute("shape") ?? "rect").trim().toLowerCase();
  const coords = (area.getAttribute("coords") ?? "")
    .split(/[\s,]+/)
    .filter(Boolean)
    .map(Number);
  if (coords.some((n) => !Number.isFinite(n))) return whole;
  let box: [number, number, number, number] | null = null;
  if ((shape === "rect" || shape === "rectangle") && coords.length >= 4) {
    const [x1, y1, x2, y2] = coords;
    box = [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)];
  } else if ((shape === "circle" || shape === "circ") && coords.length >= 3) {
    box = [coords[0] - coords[2], coords[1] - coords[2], coords[0] + coords[2], coords[1] + coords[2]];
  } else if ((shape === "poly" || shape === "polygon") && coords.length >= 6) {
    const xs = coords.filter((_, i) => i % 2 === 0);
    const ys = coords.filter((_, i) => i % 2 === 1);
    box = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  }
  if (!box) return whole;
  const clamp = (n: number, low: number, high: number) => Math.min(Math.max(n, low), high);
  return plainRect({
    left: clamp(left + box[0], whole.left, whole.right),
    top: clamp(top + box[1], whole.top, whole.bottom),
    right: clamp(left + box[2], whole.left, whole.right),
    bottom: clamp(top + box[3], whole.top, whole.bottom),
  });
}

type ShownPart = { left: number; top: number; width: number; height: number };

/** The part of ``rect`` that its scrolling ``panels`` show, or null when none of it is shown. */
function shownPart(rect: BoxRect, panels: HTMLElement[]): ShownPart | null {
  let { left, top, right, bottom } = rect;
  for (const panel of panels) {
    if (!panel.isConnected) continue;
    const outer = panel.getBoundingClientRect();
    const panelLeft = outer.left + panel.clientLeft;
    const panelTop = outer.top + panel.clientTop;
    left = Math.max(left, panelLeft);
    top = Math.max(top, panelTop);
    right = Math.min(right, panelLeft + panel.clientWidth);
    bottom = Math.min(bottom, panelTop + panel.clientHeight);
  }
  // Equal edges still count: an empty element is shown where it sits.
  if (right < left || bottom < top) return null;
  return { left, top, width: right - left, height: bottom - top };
}

function setStyles(el: HTMLElement, styles: Record<string, string>): void {
  for (const [name, value] of Object.entries(styles)) el.style.setProperty(name, value, "important");
}

/** What a highlighted element is, in words, for the line under the toolbar. */
export type ElementDescription = {
  /** "Link", "Button", "Heading level 2", or the tag for anything else. */
  kind: string;
  /** Its name or text, cut short; empty when it has neither. */
  text: string;
  width: number;
  height: number;
  /** Why the box is somewhere other than around it, or null. */
  where: BoxNote | null;
};

export function describeElement(el: Element): ElementDescription {
  const tag = el.tagName.toLowerCase();
  const role = el.getAttribute("role");
  const input = tag === "input" ? (el.getAttribute("type") ?? "text").toLowerCase() : null;
  const kind =
    role === "button" || tag === "button" || input === "button" || input === "submit"
      ? "Button"
      : role === "link" || tag === "a"
        ? "Link"
        : tag === "img" || role === "img"
          ? "Image"
          : /^h[1-6]$/.test(tag)
            ? `Heading level ${tag[1]}`
            : input === "checkbox"
              ? "Checkbox"
              : input === "radio"
                ? "Radio button"
                : input !== null || tag === "textarea"
                  ? "Text field"
                  : tag === "select"
                    ? "List box"
                    : tag === "svg"
                      ? "Graphic"
                      : tag === "iframe"
                        ? "Frame"
                        : `<${tag}> element`;
  const text = normalizeWhitespace(nameOrText(el));
  const rect = el.getBoundingClientRect();
  return {
    kind: isWholePage(el) ? `The whole page (<${tag}> element)` : kind,
    text: text.length > 80 ? `${text.slice(0, 79).trimEnd()}…` : text,
    width: Math.round(rect.width),
    height: Math.round(rect.height),
    where: boxPlace(el).note,
  };
}

/**
 * The words that name an element, in roughly the order a browser picks its
 * accessible name: the elements ``aria-labelledby`` points to, ``aria-label``,
 * a ``<label>``, alt text, a button input's value, its own text, the alt text
 * or SVG title of an image inside it (an image link), then ``title`` and
 * ``placeholder``. Not the full algorithm, but it no longer calls a labelled
 * field or an image link nameless. Duck-typed, because the element can
 * belong to the saved copy's frame, whose constructors are not this page's.
 */
function nameOrText(el: Element): string {
  const doc = el.ownerDocument;
  const pick = (value: string | null | undefined) => (value && value.trim() ? value : "");
  const labelledBy = el.getAttribute("aria-labelledby");
  const fromIds = labelledBy
    ? labelledBy
        .split(/\s+/)
        .map((id) => (id ? (doc.getElementById(id)?.textContent ?? "") : ""))
        .join(" ")
    : "";
  const labels = "labels" in el ? (el as HTMLInputElement).labels : null;
  const fromLabels = labels ? Array.from(labels, (label) => label.textContent ?? "").join(" ") : "";
  const tag = el.tagName.toLowerCase();
  const inputType = (el.getAttribute("type") ?? "").toLowerCase();
  const buttonValue =
    tag === "input" && ["button", "submit", "reset"].includes(inputType) ? el.getAttribute("value") : null;
  const innerImage = el.querySelector("img[alt]");
  const innerSvgTitle = el.querySelector("svg title");
  return (
    pick(fromIds) ||
    pick(el.getAttribute("aria-label")) ||
    pick(fromLabels) ||
    pick(el.getAttribute("alt")) ||
    pick(buttonValue) ||
    pick((el as HTMLElement).innerText) ||
    pick(el.textContent) ||
    pick(innerImage?.getAttribute("alt")) ||
    pick(innerSvgTitle?.textContent) ||
    pick(el.getAttribute("title")) ||
    pick(el.getAttribute("placeholder"))
  );
}

/** A locator as a reader can use it: the CSS selector, or an Alfa record's XPath. */
export function readableLocator(selector: string | null): string | null {
  if (!selector) return null;
  if (!isAlfaJsonSelector(selector)) return selector;
  try {
    const parsed = JSON.parse(selector) as unknown;
    const first = (Array.isArray(parsed) ? parsed[0] : parsed) as { path?: unknown } | undefined;
    return typeof first?.path === "string" ? first.path : null;
  } catch {
    return null;
  }
}

function forceVisible(el: HTMLElement | SVGElement): void {
  el.style.setProperty("opacity", "1", "important");
  el.style.setProperty("visibility", "visible", "important");
  el.style.setProperty("animation", "none", "important");
  el.style.setProperty("transition", "none", "important");
}

function documentOrder(a: Element, b: Element): number {
  if (a === b) return 0;
  return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
}

/**
 * Step 1: the locator, checked against the markup. Returns a result when the
 * locator settles it, or null to fall through to the markup walk.
 */
function locateByLocator(doc: Document, target: Target): Located | null {
  const { selector, snippet } = target;
  if (!selector) return null;
  if (isAlfaJsonSelector(selector)) return locateAlfa(doc, selector);
  let matches: Element[];
  try {
    matches = Array.from(doc.querySelectorAll(selector));
  } catch {
    return null; // not a selector this document understands; try the markup
  }
  if (matches.length === 0) return null;
  if (!snippet) {
    // No markup to check against: only a selector that names one element.
    return matches.length === 1
      ? { status: "found", elements: [matches[0]], how: "selector" }
      : { status: "ambiguous", candidates: matches.length };
  }
  const agreeing = matches.filter((el) => snippetMatches(el, snippet, target.cutAt));
  if (agreeing.length === 1) return { status: "found", elements: [agreeing[0]], how: "selector" };
  // None agree (the page changed there, or a generic selector hit the wrong
  // element), or several do (identical elements the selector cannot tell
  // apart): the markup walk decides, and says "ambiguous" when it cannot.
  return null;
}

/** The elements an image locator counts, by kind. */
const IMAGE_KINDS: Record<ImageLocator["kind"], string> = {
  img: "img",
  source: "picture > source",
  svg: "svg",
};

/**
 * An image named by its place among elements of its kind. Found only when the
 * document has exactly as many of them as the scan's copy did and the one in
 * that place has the recorded address and alt text (or, for an inline SVG,
 * the recorded text). Anything else is missing: a count that differs means
 * this is not the document the check read, and no neighbour is taken instead.
 */
function locateImage(doc: Document, { locator, alt }: ImageTarget): Located {
  if (!locator || !doc.body) return { status: "missing" };
  const elements = countedMatches(doc.body, IMAGE_KINDS[locator.kind]);
  const el = elements?.length === locator.total ? elements[locator.index] : undefined;
  if (!el) return { status: "missing" };
  if (locator.kind === "svg") {
    return svgText(el) === locator.text ? { status: "found", elements: [el], how: "place" } : { status: "missing" };
  }
  if (locator.candidate === null || !imageAddresses(el).includes(locator.candidate)) return { status: "missing" };
  if (locator.kind === "img") {
    if ((el.hasAttribute("alt") ? el.getAttribute("alt") : null) !== alt) return { status: "missing" };
    return { status: "found", elements: [el], how: "place" };
  }
  // A <source> is never drawn itself: its picture's image is what shows.
  const picture = el.parentElement;
  const shown = picture?.querySelector(":scope > img") ?? picture;
  return shown ? { status: "found", elements: [shown], how: "place" } : { status: "missing" };
}

/**
 * An element named by its place among its tag's elements, found only when
 * the document has as many of them as the scan's copy did and the one there
 * has the recorded markup. Else it falls through to the selector and markup
 * steps, which say "missing" or "ambiguous" rather than take a neighbour.
 */
function locateByPlace(
  doc: Document,
  place: ElementPlace,
  snippet: string | null,
  cutAt: number | null | undefined,
): Located | null {
  const elements = countedMatches(doc, place.selector);
  const el = elements?.length === place.total ? elements[place.index] : undefined;
  if (!el || (snippet !== null && !snippetMatches(el, snippet, cutAt))) return null;
  return { status: "found", elements: [el], how: "place" };
}

/**
 * ``selector``'s matches as the server counts them: in document order, less
 * any inside a ``<noscript>``. The page view removes those blocks before it
 * parses; the Page code (DOM) tab parses them as elements. (A browser never
 * lists ``<template>`` content, which the server leaves out too.) Null for a
 * selector this document cannot read.
 */
function countedMatches(root: ParentNode, selector: string): Element[] | null {
  try {
    return Array.from(root.querySelectorAll(selector)).filter((el) => !el.closest("noscript"));
  } catch {
    return null;
  }
}

/** An image element's addresses as written: its src, then each srcset candidate. */
function imageAddresses(el: Element): string[] {
  const out: string[] = [];
  const src = el.getAttribute("src")?.trim();
  if (src) out.push(src);
  for (const part of (el.getAttribute("srcset") ?? "").trim().split(/,\s*/)) {
    const url = part.trim().split(/\s+/)[0];
    if (url) out.push(url);
  }
  return out;
}

/** An inline SVG's drawn text, as the scan collected it. */
function svgText(el: Element): string {
  return Array.from(el.querySelectorAll("text"))
    .map((node) => normalizeWhitespace(node.textContent ?? ""))
    .filter(Boolean)
    .join(" ");
}

/**
 * Step 2: every element whose markup is each snippet, in one document-order
 * walk. Elements are compared only against snippets of their own tag, with an
 * exact-prefix gate before any full comparison. A null snippet matches nothing.
 */
function markupMatches(doc: Document, targets: Pick<Target, "snippet" | "cutAt">[]): Element[][] {
  const results: Element[][] = targets.map(() => []);
  const buckets = new Map<string, { index: number; raw: string; needle: string; head: string; prefix: boolean }[]>();
  targets.forEach(({ snippet, cutAt }, index) => {
    if (!snippet) return;
    const needle = normalizeWhitespace(snippet);
    if (!needle) return;
    const tag = firstTagName(snippet) ?? "";
    const entry = {
      index,
      raw: snippet,
      needle,
      head: snippet.slice(0, SNIPPET_HEAD),
      prefix: matchesAsPrefix(snippet, cutAt),
    };
    const bucket = buckets.get(tag);
    if (bucket) bucket.push(entry);
    else buckets.set(tag, [entry]);
  });
  if (buckets.size === 0) return results;
  const walker = doc.createTreeWalker(doc.documentElement, NodeFilter.SHOW_ELEMENT);
  let node = walker.nextNode();
  let visited = 0;
  while (node) {
    visited += 1;
    if (visited > WALK_CAP) break;
    const el = node as Element;
    const bucket = buckets.get(el.tagName.toLowerCase());
    if (bucket) {
      const raw = el.outerHTML;
      for (const entry of bucket) {
        if (
          raw === entry.raw ||
          (raw.startsWith(entry.head) &&
            (normalizeWhitespace(raw) === entry.needle ||
              (entry.prefix && normalizeWhitespace(raw).startsWith(entry.needle)) ||
              truncatedSnippetMatches(raw, entry.needle)))
        ) {
          results[entry.index].push(el);
        }
      }
    }
    node = walker.nextNode();
  }
  return results;
}

/** True when ``el``'s serialization is the snippet's element (any whitespace). */
function snippetMatches(el: Element, snippet: string, cutAt?: number | null): boolean {
  const needle = normalizeWhitespace(snippet);
  if (!needle) return false;
  const raw = el.outerHTML;
  return (
    raw === snippet ||
    normalizeWhitespace(raw) === needle ||
    (matchesAsPrefix(snippet, cutAt) && normalizeWhitespace(raw).startsWith(needle)) ||
    truncatedSnippetMatches(raw, needle)
  );
}

/**
 * True when a snippet is only the start of its element's code: a bare start
 * tag (below), or code a check cut at its length (``SNIPPET_CUTS``).
 */
function matchesAsPrefix(snippet: string, cutAt: number | null | undefined): boolean {
  return isStartTagOnly(snippet) || (cutAt != null && snippet.length === cutAt);
}

/**
 * True when `snippet` is a bare start tag: one tag, nothing inside it, no
 * closing tag. axe reports a container as its start tag alone, which no
 * non-empty element's `outerHTML` can equal, so it matches as a prefix. A
 * complete start tag carries the element's whole attribute list.
 */
function isStartTagOnly(snippet: string): boolean {
  const trimmed = snippet.trim();
  return trimmed.length > 2 && trimmed.startsWith("<") && trimmed.endsWith(">") && trimmed.indexOf("<", 1) === -1;
}

function truncatedSnippetMatches(raw: string, needle: string): boolean {
  if (needle.endsWith("…")) {
    const head = needle.slice(0, -1).trimEnd();
    return head.length >= CUT_SNIPPET_MIN && normalizeWhitespace(raw).startsWith(head);
  }
  if (needle.length < TRUNCATED_SNIPPET_LENGTH) return false;
  return normalizeWhitespace(raw).startsWith(needle);
}

/**
 * One Alfa record: an element (its tag, its attributes and an XPath) or a
 * text node (its text and an XPath). Alfa shortens a long value and ends it
 * with "…", which then matches as a prefix.
 */
type AlfaRecord = {
  type: string;
  path: string | null;
  name: string | null;
  attributes: { name: string; value: string }[];
  data: string | null;
};

/**
 * Locate an Alfa record, or a list of them (one occurrence can name several
 * elements, such as identical links). Each record is taken where its path
 * lands when that node is the recorded one, else where the recorded element
 * or text is the only one of its kind; a list highlights every record that
 * resolves.
 */
function locateAlfa(doc: Document, json: string): Located {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return { status: "missing" };
  }
  const records = (Array.isArray(parsed) ? parsed : [parsed])
    .map(toAlfaRecord)
    .filter((record): record is AlfaRecord => record !== null);
  if (records.length === 0) return { status: "missing" };
  const results = records.map((record) => locateAlfaRecord(doc, record));
  const elements = results.flatMap((result) => (result.status === "found" ? result.elements : []));
  if (elements.length > 0) {
    const byPath = results.every((result) => result.status !== "found" || result.how === "xpath");
    return { status: "found", elements: [...new Set(elements)], how: byPath ? "xpath" : "markup" };
  }
  return results.find((result) => result.status === "ambiguous") ?? { status: "missing" };
}

function toAlfaRecord(value: unknown): AlfaRecord | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as { type?: unknown; path?: unknown; name?: unknown; attributes?: unknown; data?: unknown };
  const attributes = Array.isArray(record.attributes)
    ? record.attributes.filter(
        (a): a is { name: string; value: string } =>
          typeof a === "object" && a !== null && typeof a.name === "string" && typeof a.value === "string",
      )
    : [];
  return {
    type: typeof record.type === "string" ? record.type : "element",
    path: typeof record.path === "string" && record.path ? record.path : null,
    name: typeof record.name === "string" && record.name ? record.name.toLowerCase() : null,
    attributes,
    data: typeof record.data === "string" ? record.data : null,
  };
}

function locateAlfaRecord(doc: Document, record: AlfaRecord): Located {
  const node = record.path ? nodeAt(doc, record.path) : null;
  if (record.type === "text") {
    if (record.data === null) return { status: "missing" };
    const data = record.data;
    if (node && node.nodeType === Node.TEXT_NODE && textMatches(node.textContent ?? "", data) && node.parentElement) {
      return { status: "found", elements: [node.parentElement], how: "xpath" };
    }
    // Else the one text node that says exactly the recorded text.
    const walker = doc.createTreeWalker(doc.body ?? doc.documentElement, NodeFilter.SHOW_TEXT);
    const holders: Element[] = [];
    for (let text = walker.nextNode(); text; text = walker.nextNode()) {
      if (textMatches(text.textContent ?? "", data) && text.parentElement) holders.push(text.parentElement);
      if (holders.length > 1) break;
    }
    return holders.length === 1
      ? { status: "found", elements: holders, how: "markup" }
      : holders.length > 1
        ? { status: "ambiguous", candidates: holders.length }
        : { status: "missing" };
  }
  // A path ending in a text node inside an element record names its element.
  const element = node?.nodeType === Node.TEXT_NODE ? (node as Text).parentElement : (node as Element | null);
  if (record.name === null) {
    // Nothing recorded to recognise it by, elsewhere or here: the path alone.
    return element ? { status: "found", elements: [element], how: "xpath" } : { status: "missing" };
  }
  if (element && elementMatchesRecord(element, record)) {
    return { status: "found", elements: [element], how: "xpath" };
  }
  const candidates = Array.from(doc.getElementsByTagName(record.name)).filter((candidate) =>
    elementMatchesRecord(candidate, record),
  );
  return candidates.length === 1
    ? { status: "found", elements: candidates, how: "markup" }
    : candidates.length > 1
      ? { status: "ambiguous", candidates: candidates.length }
      : { status: "missing" };
}

/** True when ``el`` has the record's tag and every recorded attribute value. */
function elementMatchesRecord(el: Element, record: AlfaRecord): boolean {
  if (record.name && el.tagName.toLowerCase() !== record.name) return false;
  return record.attributes.every((attribute) => {
    const value = el.getAttribute(attribute.name);
    return value !== null && textMatches(value, attribute.value);
  });
}

/** Equal after collapsing whitespace, or a prefix when Alfa cut the recorded value with "…". */
function textMatches(actual: string, recorded: string): boolean {
  const have = normalizeWhitespace(actual);
  const want = normalizeWhitespace(recorded);
  if (want.endsWith("…")) return have.startsWith(want.slice(0, -1).trimEnd());
  return have === want;
}

function nodeAt(doc: Document, path: string): Node | null {
  try {
    return doc.evaluate(path, doc, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
  } catch {
    return null;
  }
}

function isAlfaJsonSelector(selector: string): boolean {
  const s = selector.trim();
  return (s.startsWith("{") || s.startsWith("[")) && s.includes('"path"');
}

export function normalizeWhitespace(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

function firstTagName(markup: string): string | null {
  const m = /^\s*<([a-zA-Z][a-zA-Z0-9-]*)/.exec(markup);
  return m ? m[1].toLowerCase() : null;
}
