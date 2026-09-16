const path = require("node:path");

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
 * Keeps the most recent lines of the backend's output so a startup failure
 * can show what the sidecar actually said instead of a generic message.
 * Packaged builds have no terminal, so without this the reason is lost.
 */
class OutputTail {
  constructor(limit = 40) {
    this.limit = limit;
    this.lines = [];
    this.partial = "";
  }

  push(chunk) {
    const text = this.partial + String(chunk);
    const parts = text.split(/\r?\n/);
    this.partial = parts.pop() || "";
    for (const line of parts) {
      if (line.trim() === "") continue;
      this.lines.push(line);
      if (this.lines.length > this.limit) this.lines.shift();
    }
  }

  text() {
    const lines = this.partial.trim() ? [...this.lines, this.partial] : this.lines;
    return lines.join("\n");
  }
}

/**
 * The details shown on the "could not start" page. The message is the
 * launcher's own diagnosis; the output is the backend's last lines, which is
 * where an import error, a missing bundled file, or a migration failure
 * actually appears.
 */
function startupFailureDetails({ error, backendOutput, exitCode, logPath, packaged }) {
  const parts = [];
  if (error && error.message) parts.push(error.message);
  if (typeof exitCode === "number") parts.push(`The local service exited with code ${exitCode}.`);
  else if (exitCode !== undefined && exitCode !== null) {
    parts.push(`The local service was stopped by signal ${exitCode}.`);
  }
  return {
    reason: parts.join(" ") || "The local service did not become ready.",
    output: backendOutput ? String(backendOutput).trim() : "",
    logPath: logPath || "",
    packaged: Boolean(packaged),
  };
}

module.exports = {
  OutputTail,
  contentSecurityPolicy,
  desktopEnvironment,
  isAxcessUrl,
  isSafeExternalUrl,
  startupFailureDetails,
};
