/**
 * Turning a stored finding target into something a person can go and look at.
 *
 * Two shapes reach the UI. Browser-based probes (axe, keyboard, focus,
 * responsive) store a CSS selector. Alfa stores a JSON descriptor of the node
 * it judged, most often a text node, e.g.
 * ``{"type":"text","data":"Free and open source"}``, because ACT rules are
 * evaluated against a serialized page, not a live DOM.
 *
 * The JSON shape is unreadable in a UI and, worse, un-followable: a reader
 * given `{"type":"text","data":"…"}` has no way to find the thing on the real
 * page. So for text targets we build a **text fragment** URL
 * (``#:~:text=…``), which Chrome, Edge and Safari resolve by scrolling the
 * live page to that exact text and highlighting it. That is the closest thing
 * to "point at it" available for findings that have no screenshot, which is
 * every Alfa finding, Alfa evaluates in its own browser subprocess, so the
 * crawler never has its element on screen to photograph.
 */
export interface FindingLocation {
  /** Human-readable description of the element. */
  label: string;
  /** The raw stored target, for developers. */
  raw: string;
  /** A URL that scrolls the live page to this exact text, when we can build one. */
  deepLink: string | null;
}

/** Text fragments match a literal substring; a long one is fragile (any stray
 *  whitespace difference breaks the match) so we anchor on a generous prefix. */
const FRAGMENT_MAX = 100;

export function findingLocation(
  pageUrl: string,
  targetSelector: string,
  targetDisplay?: string,
): FindingLocation {
  const raw = targetSelector;
  const text = textTargetOf(targetSelector);
  return {
    label: targetDisplay || (text ? `Text “${text}”` : targetSelector),
    raw,
    deepLink: text ? textFragmentUrl(pageUrl, text) : null,
  };
}

/** The literal text Alfa judged, or null when the target is a CSS selector. */
function textTargetOf(targetSelector: string): string | null {
  const trimmed = targetSelector.trim();
  if (!trimmed.startsWith("{")) return null;
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      (parsed as { type?: unknown }).type === "text" &&
      typeof (parsed as { data?: unknown }).data === "string"
    ) {
      const data = (parsed as { data: string }).data.trim();
      return data.length > 0 ? data : null;
    }
  } catch {
    // A target that does not parse is just a selector we cannot deep-link.
  }
  return null;
}

export function textFragmentUrl(pageUrl: string, text: string): string | null {
  // Collapse runs of whitespace: the stored text keeps the source's line
  // breaks and indentation, which never match the rendered text node.
  const normalized = text.replace(/\s+/g, " ").trim().slice(0, FRAGMENT_MAX);
  if (normalized.length < 4) return null;
  try {
    const url = new URL(pageUrl);
    // Strip any existing fragment, a directive must be the whole hash.
    url.hash = "";
    return `${url.toString()}#:~:text=${encodeURIComponent(normalized)}`;
  } catch {
    return null;
  }
}
