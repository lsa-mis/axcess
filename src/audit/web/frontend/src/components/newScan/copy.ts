/**
 * Every word the New scan page says, in one place.
 *
 * The form used to explain itself in the vocabulary of its own internals:
 * "DOM states", "static only", "VLM", "rps". Each label here names what the
 * setting *does to the scan*, and each hint says what you gain or lose, so a
 * reviewer who has never met the engine can still choose. Positive labels
 * only: a switch that is on means the thing happens (SC 3.3.2, and the plain
 * reading of a toggle). The `skip_*` payload fields are inverted at the edge,
 * in `scanPolicy.ts`, never in the copy.
 */

export const TAB_PUBLIC = "Public website";
export const TAB_LOGIN = "Site with a login or 2FA";

export const URL_COPY = {
  public: {
    label: "Site URL",
    help:
      "Start with https:// . The scan stays under this address’s path, so /section/ only follows that section.",
    placeholder: "https://example.edu/section/",
  },
  login: {
    label: "Page to scan after you sign in",
    help:
      "Start with https:// and no query string. The scan stays under this address’s path and never leaves this website.",
    placeholder: "https://umich.instructure.com/courses/",
  },
} as const;

export const DEFAULTS_CARD = {
  title: "Default scan settings",
  selected: "Selected",
  customized: "Customized",
  leadDefault:
    "This is what runs unless you change something under Advanced settings.",
  leadCustom:
    "You changed something under Advanced settings. Crossed-out lines are no longer part of this scan.",
  reset: "Reset to default",
} as const;

export const GROUPS = {
  coverage: {
    legend: "Coverage",
    description: "How much of the site to visit.",
  },
  checks: {
    legend: "Checks",
    description: "What each page is tested for.",
  },
  localAi: {
    legend: "Local AI",
    description:
      "Runs on this computer only. Nothing is uploaded, and no model is downloaded automatically.",
  },
  speed: {
    legend: "Speed and debugging",
    description:
      "How hard the crawler works, and whether you can watch it.",
  },
} as const;

/** Switch copy, keyed by the positive setting name used in `scanPolicy.ts`. */
export const SWITCHES = {
  whole_host: {
    label: "Crawl the entire host",
    hint: "Ignores the path above; every page on the host is in scope.",
  },
  whole_host_login: {
    label: "Crawl the entire approved host",
    hint: "Ignores the path above, but never leaves the signed-in website.",
  },
  include_subdomain: {
    label: "Follow links to subdomains",
    hint: "For example from lsa.umich.edu to events.lsa.umich.edu.",
  },
  ignore_robots: {
    label: "Ignore the site’s robots.txt rules",
    hint:
      "Visits pages the site asks crawlers to skip. Authorized testing only; the scan is flagged in its config and audit log.",
  },
  click_through: {
    label: "Click through menus, tabs and dialogs",
    hint:
      "Opens controls on each page and checks the content they reveal, then re-runs the checks there. Adds scan time. Never submits forms, pays, or subscribes.",
  },
  keyboard: {
    label: "Check for keyboard traps",
    hint: "Can you Tab into and back out of every control? Adds 1–3 seconds per page.",
  },
  focus: {
    label: "Check that focus is never hidden",
    hint: "Catches keyboard focus tucked behind sticky headers and footers (SC 2.4.11).",
  },
  responsive: {
    label: "Check narrow screens and zoom",
    hint: "320 px wide, 200% zoom and wider text spacing (SC 1.4.4, 1.4.10, 1.4.12). Adds 1–2 seconds per page.",
  },
  skip_rendered_storage: {
    label: "Don’t store rendered pages",
    hint:
      "Keeps the report database smaller. The Page inspector then re-renders the live page on demand instead of opening the stored capture; findings and evidence are stored exactly as before.",
  },
  ocr: {
    label: "Read text inside images (OCR)",
    hint:
      "Finds words drawn into pictures so they can be checked. Runs locally; no model needed.",
  },
  vision: {
    label: "Review image text with a local vision model",
    hint:
      "Judges whether an image’s alt text matches what it shows. Slower; only reviews images where OCR found text.",
  },
  semantic: {
    label: "Review wording with local AI",
    hint:
      "A language model on this computer reads headings and links for meaning, not just markup. Results need an expert to confirm.",
  },
  motion: {
    label: "Check motion and animation",
    hint:
      "Flags flashing, autoplay and layout that only a screenshot shows.",
  },
  static_only: {
    label: "Fast crawl without a browser",
    hint:
      "Fetches page HTML only, 5–10× faster. Skips every check that needs a rendered page: axe-core, keyboard, zoom and focus.",
  },
  show_browser: {
    label: "Show the scanning browser window",
    hint:
      "Leave off to scan in the background while you use other apps. Closing the window stops browser-based checks.",
  },
} as const;

export const NUMBERS = {
  max_pages: { label: "Max pages" },
  max_depth: {
    label: "Max link depth",
    hint: "How many clicks from the start page. 10 reaches nearly everything on most sites.",
  },
  rps: {
    label: "Requests per second",
    hint:
      "How quickly Axcess asks the site for pages. Higher is faster but adds load; raise it only with the site owner’s agreement.",
  },
  workers: {
    label: "Parallel workers",
    hint: "How many pages this computer works on at once. An M4 Pro can start at 8 and scale to 32.",
  },
  workers_login: {
    label: "Signed-in tabs",
    hint:
      "Concurrent tabs inside the same temporary signed-in browser. Two is recommended; four is the safety maximum.",
  },
} as const;

export const STANDARD = {
  label: "Standard to check against",
  hint: "WCAG 2.2. AA is what most policies require; AAA adds the strictest rules, such as 7:1 contrast.",
} as const;

export const ENGINE = {
  label: "Rule engine",
  axe: {
    label: "axe-core",
    hint: "The standard checker. Runs in the browser Axcess already opened.",
  },
  alfa: {
    label: "Siteimprove Alfa",
    hint:
      "An independent second checker using ACT rules — standard tests published by the W3C, one condition each. Slower.",
  },
  both: {
    label: "Both",
    hint: "The most thorough option. Evidence from each engine is kept separately.",
  },
} as const;

export const FIXED_NOTE_LOGIN =
  "Fixed for login scans: the scan stays on this exact website, respects robots.txt, always renders pages in a real browser, and runs at 1 request per second.";

export const AUTHORIZATION = {
  label:
    "I have authorization from the site owner and will use a least-privilege test account.",
  hint:
    "Required. You sign in yourself in a browser window on this computer; your password is typed into the site, never into Axcess. The session stays in memory and is destroyed when the scan ends.",
} as const;

export const IMAGE_ACK = {
  label: "Store protected image-analysis evidence locally",
  hintOcr:
    "Protected image blobs and extracted OCR text will be stored in this computer’s local Axcess evidence directory and database.",
  hintVision:
    "Protected image blobs, OCR text and vision-model rationale will be stored locally. Image data is sent only to the verified loopback Ollama endpoint.",
} as const;

export const SUBMIT = {
  public: { label: "Start scan", pending: "Starting scan…", note: "Watch progress or come back later; the report saves as it goes." },
  login: {
    label: "Open browser to sign in",
    pending: "Opening browser…",
    note: "A window opens for you to sign in; the scan starts when you press “I’m signed in”.",
  },
} as const;

export const ERRORS = {
  title: "The scan could not start",
  lead: "Fix these before starting:",
  urlEmpty: "Enter the page to start from.",
  urlNotHttp: "Add https:// at the start. Axcess only scans web addresses.",
  urlNotHttps: "Use https:// . Login scans only run over a secure connection.",
  urlHasExtras: "Remove the query string, fragment or credentials from the address.",
  staticWithAxe:
    "Fast crawl without a browser cannot run with axe-core. Turn off Fast crawl, or choose Siteimprove Alfa as the rule engine.",
  notAuthorized: "Confirm that the site owner authorized this accessibility scan.",
  imageAck:
    "Confirm how protected images and extracted text will be stored before turning on image text reading.",
} as const;

export const SUMMARY = {
  title: "What this scan will do",
  site: "Site",
  siteEmpty: "Enter a site URL to see the scope.",
  coverage: "Coverage",
  checks: "Checks",
  localAi: "Local AI",
  storage: "Storage",
  notIncluded: "Not included",
  footnote:
    "Automated checks find roughly a third of accessibility problems. The report says what still needs a person.",
} as const;
