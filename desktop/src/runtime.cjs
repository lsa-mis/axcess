const path = require("node:path");

// Chromium renders at 1.2^level, so half-steps are about 10% a press, close
// to a browser's own zoom ladder. The bounds are Chromium's usable range
// rather than arbitrary: past them the page stops reflowing usefully.
const ZOOM_STEP = 0.5;
const MIN_ZOOM_LEVEL = -6;
const MAX_ZOOM_LEVEL = 9;

function isAxcessUrl(candidate, origin) {
  try {
    const parsed = new URL(candidate);
    return parsed.origin === origin && parsed.protocol === "http:";
  } catch {
    return false;
  }
}

function isSafeExternalUrl(candidate) {
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

/**
 * The Content-Security-Policy applied to every response from the local backend.
 *
 * The Page inspector shows a scanned page's captured markup in a `srcdoc`
 * iframe, and a `srcdoc` document *inherits* the embedding document's policy —
 * it cannot be given a looser one of its own. So whatever the capture needs to
 * render has to be permitted here, on the app's own policy.
 *
 * The capture is given the scanned page's URL as `<base href>` so its relative
 * stylesheets, fonts and images resolve against the site they came from. That
 * requires `base-uri` to accept an arbitrary scanned origin, and the three
 * fetch directives to accept that site's subresources; with `base-uri 'none'`
 * the `<base>` is dropped silently and the page renders completely unstyled.
 * Loading those subresources from the live site is the inspector's documented
 * behavior, and matches how the browser build (which sets no CSP) behaves.
 *
 * `script-src 'self'` is the boundary that matters and is deliberately NOT
 * relaxed: the capture's own scripts never run, enforced both here and by the
 * iframe's `sandbox` (which withholds `allow-scripts`). `object-src`,
 * `frame-src`, `connect-src` and `form-action` stay locked down too, so the
 * untrusted markup can style itself but cannot execute, embed, phone home or
 * submit anything.
 */
function contentSecurityPolicy() {
  return [
    "default-src 'self'",
    "script-src 'self'",
    // 'unsafe-inline' covers the inspector's inline highlight styles; http:/https:
    // cover the scanned page's own stylesheets.
    "style-src 'self' 'unsafe-inline' http: https:",
    "img-src 'self' data: blob: http: https:",
    "font-src 'self' data: http: https:",
    "connect-src 'self'",
    "object-src 'none'",
    // A `srcdoc` frame is not subject to frame-src, so the inspector still
    // works while URL-based framing stays blocked.
    "frame-src 'none'",
    // Must admit the scanned page's origin for the inspector's <base href>.
    "base-uri 'self' http: https:",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

function desktopEnvironment({ userDataPath, electronExecutable, resourcesPath, packaged }) {
  const dataRoot = path.join(userDataPath, "data");
  const ocrRoot = path.join(resourcesPath, "ocr-runtime");
  const environment = {
    AUDIT_DATA_DIR: dataRoot,
    AUDIT_DB_PATH: path.join(dataRoot, "audit.db"),
    AUDIT_BLOB_DIR: path.join(dataRoot, "blobs"),
    AUDIT_LOG_DIR: path.join(dataRoot, "logs"),
    AUDIT_ACCESS_TOKEN: "",
    AUDIT_NODE_EXECUTABLE: electronExecutable,
    AUDIT_NODE_RUN_AS_NODE: "1",
    PYTHONUNBUFFERED: "1",
  };
  if (packaged) {
    environment.PLAYWRIGHT_BROWSERS_PATH = path.join(resourcesPath, "playwright-browsers");
    environment.TESSDATA_PREFIX = path.join(ocrRoot, "share", "tessdata");
    environment.PATH = [path.join(ocrRoot, "bin"), process.env.PATH || ""]
      .filter(Boolean)
      .join(path.delimiter);
  }
  return environment;
}

/**
 * Which zoom action a keystroke asks for, or null when it asks for none.
 *
 * Electron's built-in View menu binds Zoom In to `CommandOrControl+Plus`,
 * which matches only the literal "+" character -- on most layouts Shift+=.
 * Zoom Out binds `CommandOrControl+-`, a key that exists on its own. So the
 * app zoomed out but never in, and `Ctrl+=`, which every browser accepts and
 * which is what the key is actually labelled on the keyboard, did nothing.
 *
 * Zoom is not a convenience here: WCAG 2.2 expects content to survive 200%
 * (SC 1.4.4), and an accessibility tool that cannot be enlarged is failing the
 * thing it measures.
 *
 * Matching is on the character rather than the accelerator, so every way a
 * keyboard can produce it counts: "=", "+", Shift+= and the numpad's own keys.
 */
function zoomActionFor(input) {
  if (!input || input.type !== "keyDown") return null;
  // Alt is left alone: Alt reveals the hidden menu bar, and Alt+key belongs
  // to it. Either Control or Command, so one rule covers every platform.
  if (input.alt || !(input.control || input.meta)) return null;
  const key = String(input.key ?? "");
  if (key === "=" || key === "+" || key === "Add") return "in";
  if (key === "-" || key === "_" || key === "Subtract") return "out";
  if (key === "0" || key === "Insert") return "reset";
  return null;
}

/** Zoom level after applying `action`, clamped to roughly 30%-500%. */
function nextZoomLevel(current, action) {
  if (action === "reset") return 0;
  const step = action === "in" ? ZOOM_STEP : -ZOOM_STEP;
  const level = (Number.isFinite(current) ? current : 0) + step;
  return Math.max(MIN_ZOOM_LEVEL, Math.min(MAX_ZOOM_LEVEL, level));
}

module.exports = {
  MAX_ZOOM_LEVEL,
  MIN_ZOOM_LEVEL,
  ZOOM_STEP,
  contentSecurityPolicy,
  desktopEnvironment,
  isAxcessUrl,
  isSafeExternalUrl,
  nextZoomLevel,
  zoomActionFor,
};
