import type { StyleFingerprint, StyleSample } from "../api/types";

/**
 * Check a saved copy's rendering against how the page looked during the scan.
 *
 * During the scan Axcess records the computed styles of up to 40 elements,
 * read in the same moment as the page's CSS (see
 * `src/audit/crawler/style_snapshot.py`). Each sample is stored with its
 * position in one filtered element order. Here the same order is built in
 * the saved copy's frame, each sample's element is found by that position,
 * and the same styles are read and compared.
 *
 * The filter must match the capture's exactly, or every position points at
 * a different element: elements under `<body>` in document order, skipping
 * `noscript`, `script`, `style`, `template` and `link` elements and
 * everything inside them. The inspector removes `<noscript>` and, with saved
 * styles, `<style>` and `<link>` elements, so skipping them keeps the order
 * the same in the frame as on the live page.
 *
 * Only styles that do not change with the window's width are compared (first
 * font family, font weight, colour, background colour, text decoration): the
 * frame is not the scan's window. Colours are left out when the frame asks
 * for a different colour scheme from the scan's browser (a dark app theme
 * makes the frame prefer dark too) or forces colours, since a site may then
 * choose other colours on purpose.
 *
 * Kept free of React and of the frame itself, apart from the two DOM readers
 * at the bottom, so the comparison can be tested on its own.
 */

/** Below this share of matching samples, the copy is said to look different. */
export const MATCH_THRESHOLD = 0.7;

const SKIPPED = new Set(["noscript", "script", "style", "template", "link"]);

/** What the frame prefers, which decides whether colours can be compared. */
export interface FrameConditions {
  scheme: "light" | "dark";
  forcedColors: boolean;
}

export interface FingerprintResult {
  /** Samples compared. 0 means there was nothing to judge by. */
  checked: number;
  matched: number;
  /** Whether colours were part of the comparison. */
  colorsCompared: boolean;
}

/** The first family in a `font-family` value, unquoted and lowercased. */
export function firstFamily(value: string | null | undefined): string {
  const first = (value ?? "").split(",")[0] ?? "";
  return first
    .trim()
    .replace(/^["']|["']$/g, "")
    .toLowerCase();
}

/** A computed colour, so equal colours compare equal across engines. */
export function normalizeColor(value: string | null | undefined): string {
  const text = (value ?? "").trim().toLowerCase().replace(/\s+/g, " ");
  if (text === "transparent") return "rgba(0, 0, 0, 0)";
  return text.replace(/\s*,\s*/g, ", ").replace(/\(\s+/g, "(").replace(/\s+\)/g, ")");
}

function sameSample(expected: StyleSample, actual: StyleSample, colors: boolean): boolean {
  if (firstFamily(expected.fontFamily) !== firstFamily(actual.fontFamily)) return false;
  if (String(expected.fontWeight).trim() !== String(actual.fontWeight).trim()) return false;
  if ((expected.textDecorationLine ?? "").trim() !== (actual.textDecorationLine ?? "").trim()) return false;
  if (!colors) return true;
  return (
    normalizeColor(expected.color) === normalizeColor(actual.color) &&
    normalizeColor(expected.backgroundColor) === normalizeColor(actual.backgroundColor)
  );
}

/**
 * Compare the scan's samples with what the frame shows.
 *
 * ``observed`` holds the frame's sample for each expected one, by position in
 * ``expected.samples``; null when the frame has no element at that position,
 * which counts as a mismatch.
 */
export function compareFingerprint(
  expected: StyleFingerprint | null | undefined,
  observed: (StyleSample | null)[],
  frame: FrameConditions,
): FingerprintResult {
  const samples = expected?.samples ?? [];
  const colorsCompared = (expected?.scheme ?? "light") === frame.scheme && !expected?.forced_colors && !frame.forcedColors;
  let matched = 0;
  samples.forEach((sample, i) => {
    const actual = observed[i];
    if (actual && sameSample(sample, actual, colorsCompared)) matched += 1;
  });
  return { checked: samples.length, matched, colorsCompared };
}

/** Whether a result says the copy probably looks different from the scan. */
export function looksDifferent(result: FingerprintResult): boolean {
  return result.checked > 0 && result.matched / result.checked < MATCH_THRESHOLD;
}

/** The elements samples are numbered by, in the capture's order (see above). */
export function fingerprintElements(doc: Document): Element[] {
  const out: Element[] = [];
  const body = doc.body;
  if (!body) return out;
  const walker = doc.createTreeWalker(body, NodeFilter.SHOW_ELEMENT, {
    acceptNode: (node) =>
      SKIPPED.has((node as Element).localName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  let node = walker.nextNode();
  while (node) {
    out.push(node as Element);
    node = walker.nextNode();
  }
  return out;
}

/** Read the frame's samples and compare them with the scan's. */
export function checkFingerprint(doc: Document, expected: StyleFingerprint | null | undefined): FingerprintResult {
  const view = doc.defaultView;
  if (!view) return { checked: 0, matched: 0, colorsCompared: false };
  const elements = fingerprintElements(doc);
  const observed = (expected?.samples ?? []).map((sample): StyleSample | null => {
    const el = elements[sample.index];
    if (!el) return null;
    const cs = view.getComputedStyle(el);
    return {
      index: sample.index,
      fontFamily: firstFamily(cs.fontFamily),
      fontWeight: cs.fontWeight,
      color: cs.color,
      backgroundColor: cs.backgroundColor,
      textDecorationLine: cs.textDecorationLine,
    };
  });
  return compareFingerprint(expected, observed, {
    scheme: view.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
    forcedColors: view.matchMedia("(forced-colors: active)").matches,
  });
}
