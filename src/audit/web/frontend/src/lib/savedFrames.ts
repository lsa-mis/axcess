import type { SavedFrame } from "../api/types";

/**
 * Put each frame the scan saved back into the saved copy, and a note where
 * none was saved.
 *
 * The saved copy is the page's top document. Its `<iframe>` elements kept
 * their `src`, so they loaded live inside the copy's sandbox, where scripts
 * do not run, and an embed that draws itself with scripts (Google Sites'
 * "Custom embed", a video player, a form) showed as an empty box with no word
 * of why. Each `<iframe>` now gets the document the scan saved for it as its
 * `srcdoc`, so the copy shows what the scan saw. Frames inside frames are
 * filled the same way. A `srcdoc` frame inside the sandboxed copy inherits
 * its sandbox, so these documents run no scripts either: they are untrusted
 * scanned content, like the page.
 *
 * Which saved frame goes where: the scan recorded each frame's parent and its
 * position among that document's `<iframe>` and `<frame>` elements, in
 * document order, not counting any inside `<noscript>`
 * (`audit.crawler.frame_snapshot`). This counts the same way. Rejected:
 * marking each frame element with an attribute at scan time, which would
 * change the saved markup, and that markup is evidence.
 *
 * Where no frame was saved (a report made before frames were saved, a frame
 * over a size limit, a state reached by clicking, or a live render), the
 * frame shows a note saying what is missing and where to see it, in place of
 * an empty box or a live load. Rejected: loading the frame live as before.
 * It is not what the scan saw, and with scripts off it was mostly blank, so
 * the reader could not tell a missing part from a page that is really empty
 * (W3C COGA, "Making Content Usable", https://www.w3.org/TR/coga-usable/:
 * say what happened and what to do; repo rule: never hide a limitation).
 * `<frame>` elements (framesets) cannot take `srcdoc`, so they are left as
 * they were.
 *
 * `prepare` gets each frame's document and its address, and readies it the
 * way the page itself is readied for display (`prepareCapture`).
 */
export function withSavedFrames(
  html: string,
  frames: SavedFrame[] | undefined,
  pageUrl: string | null,
  prepare: (html: string, url: string | null) => string,
): string {
  return fill(html, frames ?? [], 0, pageUrl, prepare, 0);
}

// Deeper than any real embed (Google Sites uses three levels), and a stop for
// a saved frame list that would otherwise loop.
const MAX_DEPTH = 8;

function fill(
  html: string,
  frames: SavedFrame[],
  parentId: number,
  baseUrl: string | null,
  prepare: (html: string, url: string | null) => string,
  depth: number,
): string {
  // Most pages have no frames: leave their markup exactly as it was, rather
  // than parsing and re-serializing it for nothing.
  if (!/<iframe\b/i.test(html)) return html;
  const doc = new DOMParser().parseFromString(html, "text/html");
  const elements = Array.from(doc.querySelectorAll("iframe, frame")).filter((el) => !el.closest("noscript"));
  if (!elements.some((el) => el.tagName === "IFRAME")) return html;
  elements.forEach((el, index) => {
    if (el.tagName !== "IFRAME") return;
    const saved = depth < MAX_DEPTH ? frames.find((f) => f.parent_id === parentId && f.index === index) : undefined;
    let inner: string;
    if (saved) {
      // A frame such as about:blank has no address of its own and resolves
      // its links against the page it is in, as it did on the site.
      const url = webUrl(saved.url) ?? baseUrl;
      inner = prepare(fill(saved.html, frames, saved.frame_id, url, prepare, depth + 1), url);
    } else {
      inner = frameNote(el.getAttribute("src"), baseUrl);
    }
    el.removeAttribute("src");
    el.setAttribute("srcdoc", inner);
  });
  const doctype = doc.doctype ? new XMLSerializer().serializeToString(doc.doctype) : "";
  return doctype + doc.documentElement.outerHTML;
}

function webUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

/**
 * The note shown in place of a frame the saved copy does not include.
 *
 * It names where the part came from when the frame had a web address
 * ("comes from youtube.com"), because that is what tells the reader whether
 * it is the site's own content or another service's. A frame with no address
 * was filled in by the page's own code, so it says that instead. It points to
 * the Inspector's own "Open live page" button by its exact words, as the
 * Inspector's other messages do, rather than holding a link of its own: a
 * link inside the copy would navigate the sandboxed frame, not open the site.
 *
 * Fixed colours, not the app's theme: the note sits inside the site's page,
 * which keeps the site's colours. #1f2937 on #f3f4f6 is about 13:1 (SC 1.4.6
 * Contrast (Enhanced), Level AAA), and the dashed edge marks the box as a
 * stand-in for something missing, not part of the site's design. It names
 * its language (SC 3.1.1 Language of Page, Level A), and its text wraps in
 * a frame of any size.
 */
function frameNote(src: string | null, baseUrl: string | null): string {
  let host = "";
  if (src) {
    try {
      const url = new URL(src, baseUrl ?? undefined);
      if (url.protocol === "http:" || url.protocol === "https:") host = url.hostname.replace(/^www\./, "");
    } catch {
      host = "";
    }
  }
  const where = host
    ? `This part of the page comes from ${escapeText(host)}.`
    : "This part of the page was added by the page’s own code.";
  return (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Not in the saved copy</title></head>' +
    '<body style="margin:0;min-height:100vh;box-sizing:border-box;display:flex;align-items:center;' +
    "justify-content:center;padding:12px;background:#f3f4f6;color:#1f2937;border:2px dashed #6b7280;" +
    'font:16px/1.5 system-ui,sans-serif;text-align:center">' +
    `<p style="margin:0;max-width:35em">${where} The saved copy does not include it. ` +
    "Use “Open live page” to see it.</p></body></html>"
  );
}

function escapeText(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
