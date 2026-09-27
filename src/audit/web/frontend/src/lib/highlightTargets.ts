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
    parent = parent.parentElement;
  }
}

/** Set the element the reader is on apart from the other flagged ones, or put it back. */
export function markCurrent(el: HTMLElement | SVGElement, current: boolean): void {
  el.style.setProperty(
    "outline",
    current ? `3px solid ${CURRENT_OUTLINE}` : `2px dashed ${FLAGGED_OUTLINE}`,
    "important",
  );
  el.style.setProperty("outline-offset", current ? "-3px" : "-2px", "important");
  if (current) el.setAttribute("data-axcess-current", "");
  else el.removeAttribute("data-axcess-current");
}

/**
 * Draw a box over ``el`` in its own document, labelled (``5 of 7``), with the
 * rest of the page dimmed: the "you are here" of the saved copy.
 *
 * An outline on the element itself vanished on a tiny or empty element (a
 * two-pixel link, a zero-width icon) and was clipped by `overflow: hidden`
 * ancestors, so the reader stepped to "Flagged element 5 of 7" and saw
 * nothing. The box is drawn on the page's root, over everything, at least
 * ``SPOTLIGHT_MIN`` pixels on each side and centred on the element, and it
 * follows the element when the frame is resized, calling ``onPlace`` each
 * time so a description of the element can follow too. Null removes it.
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
  const listeners = resizeListeners.get(owner);
  if (listeners && view) view.removeEventListener("resize", listeners);
  resizeListeners.delete(owner);
  if (!el || !view) return;

  const box = owner.createElement("div");
  box.id = SPOTLIGHT_ID;
  box.setAttribute("aria-hidden", "true");
  const tag = owner.createElement("div");
  tag.textContent = label;
  box.appendChild(tag);
  owner.documentElement.appendChild(box);

  const place = () => {
    const rect = el.getBoundingClientRect();
    let { width, height } = rect;
    let left = rect.left + view.scrollX;
    let top = rect.top + view.scrollY;
    if (width < SPOTLIGHT_MIN) {
      left -= (SPOTLIGHT_MIN - width) / 2;
      width = SPOTLIGHT_MIN;
    }
    if (height < SPOTLIGHT_MIN) {
      top -= (SPOTLIGHT_MIN - height) / 2;
      height = SPOTLIGHT_MIN;
    }
    const pad = 4;
    setStyles(box, {
      position: "absolute",
      left: `${left - pad}px`,
      top: `${top - pad}px`,
      width: `${width + pad * 2}px`,
      height: `${height + pad * 2}px`,
      "box-sizing": "border-box",
      border: `3px solid ${CURRENT_OUTLINE}`,
      "border-radius": "4px",
      "box-shadow": `0 0 0 3px ${CURRENT_RING}, 0 0 0 100vmax ${CURRENT_DIM}`,
      "pointer-events": "none",
      "z-index": "2147483647",
      margin: "0",
      padding: "0",
    });
    // The label sits above the box, or inside its top when the element is
    // at the very top of the page.
    const above = top - pad > 30;
    setStyles(tag, {
      position: "absolute",
      left: "-3px",
      top: above ? "-29px" : "0",
      background: CURRENT_OUTLINE,
      color: "#ffffff",
      font: "600 13px/1.5 system-ui, -apple-system, 'Segoe UI', sans-serif",
      "letter-spacing": "normal",
      "text-transform": "none",
      padding: "2px 8px",
      "border-radius": "3px",
      "white-space": "nowrap",
      "box-shadow": `0 0 0 2px ${CURRENT_RING}`,
    });
    onPlace?.(el);
  };
  place();
  view.addEventListener("resize", place);
  resizeListeners.set(owner, place);
}

const resizeListeners = new WeakMap<Document, () => void>();

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
    kind,
    text: text.length > 80 ? `${text.slice(0, 79).trimEnd()}…` : text,
    width: Math.round(rect.width),
    height: Math.round(rect.height),
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
