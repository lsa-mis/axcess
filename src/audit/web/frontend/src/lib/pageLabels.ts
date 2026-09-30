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
