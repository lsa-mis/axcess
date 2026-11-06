/** Plain-language labels for crawler implementation values shown to auditors. */
export function httpStatusLabel(status: number | null): string {
  if (status == null) return "Load result not recorded";
  if (status >= 200 && status < 300) return `Loaded successfully (HTTP ${status})`;
  if (status >= 300 && status < 400) return `Sent to another address (redirect, HTTP ${status})`;
  if (status === 401) return "Sign-in required (HTTP 401)";
  if (status === 403) return "Access blocked (HTTP 403)";
  if (status === 404) return "Page not found (HTTP 404)";
  if (status >= 400 && status < 500) return `Page could not be loaded (HTTP ${status})`;
  if (status >= 500) return `The website’s server had an error (HTTP ${status})`;
  return `Server response code ${status} (HTTP)`;
}

export function renderModeLabel(mode: string): string {
  if (mode === "js") return "Opened in a real browser";
  if (mode === "static") return "Page code read without a browser (fast scan)";
  return mode ? `How it was loaded: ${mode}` : "How it was loaded is not recorded";
}

/**
 * How one visited page loaded, for the Pages visited list.
 *
 * `not_loaded` is a page whose fetch failed: the crawler stores no status
 * for it (orchestrator `_record_page` with no result), so it reads "Could
 * not be loaded", the words the report summary uses for the same pages
 * ("3 pages could not be loaded"). Any other page shows the server's answer,
 * in the words Page details uses for it.
 */
export function pageLoadLabel(loadResult: "loaded" | "error_status" | "not_loaded", status: number | null): string {
  if (loadResult === "not_loaded") return "Could not be loaded";
  return httpStatusLabel(status);
}
