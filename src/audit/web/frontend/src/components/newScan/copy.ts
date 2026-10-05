/**
 * Every word the New scan page says, in one place.
 *
 * The form used to explain itself in the vocabulary of its own internals:
 * "DOM states", "static only", "VLM", "rps". Each label here names what the
 * setting *does to the scan*, and each hint says what you gain or lose, so a
 * reviewer who has never met the engine can still choose. Feature names come
 * from `lib/labels.ts` (for example `CLICK_THROUGH`), so this page and the
 * report call a feature the same thing. Positive labels
 * only: a switch that is on means the thing happens (SC 3.3.2, and the plain
 * reading of a toggle). The `skip_*` payload fields are inverted at the edge,
 * in `scanPolicy.ts`, never in the copy.
 */

import { CLICK_THROUGH } from "../../lib/labels";
import { CHECK_LABEL } from "../../lib/terms";

export const TAB_PUBLIC = "Public website";
export const TAB_LOGIN = "Site with a sign-in or two-step sign-in (2FA)";

export const URL_COPY = {
  public: {
    label: "Website address",
    help:
      "For example, example.edu/section/. Axcess adds https:// for you, or http:// for localhost and IP addresses. The scan only visits pages under this address, so an address ending in /section/ scans only that section.",
    placeholder: "example.edu/section/",
  },
  login: {
    label: "Website address to scan after you sign in",
    help:
      "For example, umich.instructure.com/courses/. Axcess adds https:// for you. Leave out anything after a ? or #. The scan only visits pages under this address and never leaves this website.",
    placeholder: "umich.instructure.com/courses/",
  },
} as const;

export const GROUPS = {
  coverage: {
    legend: "Pages to scan",
    description: "How much of the site to visit.",
  },
  checks: {
    legend: "Checks",
    description: "What Axcess tests on each page.",
  },
  localAi: {
    legend: "AI checks on this computer",
    description:
      "AI (artificial intelligence) runs on this computer only. Axcess uploads nothing and never downloads a model by itself.",
  },
  limits: {
    legend: "Limits and rule check tool",
  },
  speed: {
    legend: "Speed and browser window",
    description:
      "How fast the scan runs, and whether you can watch it.",
  },
} as const;

/** Switch copy, keyed by the positive setting name used in `scanPolicy.ts`. */
export const SWITCHES = {
  whole_host: {
    label: "Scan the whole website",
    hint: "Ignores the path in the address above. Every page on this host (for example, lsa.umich.edu) is included.",
  },
  whole_host_login: {
    label: "Scan the whole signed-in website",
    hint: "Ignores the path in the address above, but never leaves the website you sign in to.",
  },
  include_subdomain: {
    label: "Follow links to subdomains",
    hint: "A subdomain is an address that ends in this site’s name. For example, events.lsa.umich.edu is a subdomain of lsa.umich.edu.",
  },
  ignore_robots: {
    label: "Ignore the site’s robots.txt rules",
    hint:
      "A site’s robots.txt file lists pages it asks scanners to skip. This setting visits those pages anyway. Use it only when you have permission to test. Axcess records this choice in the scan settings and the activity log (audit log).",
  },
  click_through: {
    label: `Open menus, tabs, and pop-up windows (${CLICK_THROUGH})`,
    hint:
      "Axcess opens controls on each page, then checks the content they show. This makes the scan take longer. It never submits forms, pays, or subscribes.",
  },
  keyboard: {
    label: "Check for keyboard traps",
    hint: "A keyboard trap is a control you can Tab into but not back out of. Adds 1–3 seconds per page.",
  },
  focus: {
    label: "Check that keyboard focus is never hidden",
    hint:
      "Finds the focus outline (the box that shows where the keyboard is) hidden behind sticky headers or footers. WCAG 2.4.11 is new in WCAG 2.2. A WCAG 2.1 scan reports it as Best practice.",
  },
  responsive: {
    label: "Check narrow screens and zoom",
    hint: "Checks each page at 320 pixels wide, at 200% zoom, and with wider text spacing (WCAG 1.4.4, 1.4.10, 1.4.12). Adds 1–2 seconds per page.",
  },
  skip_rendered_storage: {
    label: "Don’t keep a saved copy of each page",
    hint:
      "Keeps the stored report smaller. The Page inspector then loads the live page when you open it, instead of the saved copy. Occurrences and their evidence are saved as usual.",
  },
  ocr: {
    label: "Read text inside images (OCR)",
    hint:
      "Finds words drawn into pictures so Axcess can check them. Uses optical character recognition (OCR) on this computer. No AI model needed.",
  },
  vision: {
    label: "Compare image text with alt text (vision model)",
    hint:
      "An AI model that looks at images (vision model) checks whether the alt text matches what the image shows. Alt text is the text a screen reader reads for an image. Slower. It only looks at images where text was found.",
  },
  semantic: {
    label: "AI review of wording",
    hint:
      "An AI language model on this computer reads headings and links for their meaning, not just their code. An expert must confirm each result.",
  },
  motion: {
    label: "Check motion and animation",
    hint:
      "Finds flashing, media that plays by itself (autoplay), and layout problems that only a screenshot shows.",
  },
  static_only: {
    label: "Fast scan without a browser",
    hint:
      "Reads only the page code (HTML), 5–10 times faster. Skips every check that needs a browser: Rule check (axe), and the keyboard, zoom, and focus checks.",
  },
  show_browser: {
    label: "Show the scanning browser window",
    hint:
      "Leave this off to scan in the background while you use other apps. If you close the window, the browser checks stop.",
  },
} as const;

/** New scan's no-limit switch, beside Maximum pages (public scans only). */
export const ALL_PAGES = {
  label: "Scan every page it finds",
  hint: "No page limit. The scan ends when it has visited every page it can reach within the link depth. A large site can take many hours and use gigabytes of disk space.",
  maxPagesOff: "Off while the scan visits every page it finds.",
} as const;

export const NUMBERS = {
  max_pages: {
    label: "Maximum pages",
    hint: (max: number) =>
      `The scan stops after this many pages, or sooner when it finds no more pages to visit. Enter a whole number from 1 to ${max.toLocaleString()}.`,
  },
  max_depth: {
    label: "Maximum link depth",
    hint: (max: number) =>
      `How many clicks from the start page the scan follows. 1 means the start page and the pages it links to. 10 reaches almost every page on most sites. Enter a whole number from 1 to ${max}.`,
  },
  rps: {
    label: "Page requests per second",
    hint:
      "How quickly Axcess asks the site for pages. Higher is faster but puts more load on the site. Raise it only if the site owner agrees.",
  },
  workers: {
    label: "Pages at once (workers)",
    hint: "How many pages this computer works on at the same time. On a fast computer, such as an M4 Pro, start at 8 and go up to 32.",
  },
  workers_login: {
    label: "Signed-in tabs",
    hint:
      "How many tabs the temporary signed-in browser uses at once. Axcess recommends 2. The safe maximum is 4.",
  },
} as const;

export const STANDARD = {
  label: "Standard to check against",
  hint: (version: string) =>
    `Web Content Accessibility Guidelines (WCAG) ${version}. Most policies require Level AA. Level AAA adds the strictest rules, such as stronger color contrast (7:1).`,
} as const;

export const WCAG_VERSION = {
  label: "WCAG version",
  hint: "2.1 is the current University of Michigan (U-M) standard. 2.2 adds newer WCAG criteria, for example that keyboard focus is never hidden and that buttons and links are big enough to tap (target size).",
} as const;

export const ENGINE = {
  label: "Rule check tool",
  axe: {
    label: "axe",
    hint: "The standard rule check (axe-core). It runs in the browser Axcess already opened.",
  },
  alfa: {
    label: "Alfa",
    hint:
      "A second, separate rule check (Siteimprove Alfa). It uses ACT rules (Accessibility Conformance Testing): standard tests published by the W3C (World Wide Web Consortium). Each test checks one thing. Slower.",
  },
  both: {
    label: "Both",
    hint: "The most thorough choice. Axcess keeps the results of each tool separate.",
  },
} as const;

export const FIXED_NOTE_LOGIN =
  "Sign-in scans always work this way: they stay on this exact website, respect robots.txt, open every page in a real browser, and ask for 1 page per second.";

export const AUTHORIZATION = {
  label:
    "The site owner allows this scan, and I will sign in with a test account that has only the access it needs (least privilege).",
  hint:
    "Required. You sign in yourself, in a browser window on this computer. You type your password into the website, never into Axcess. Axcess keeps the session in memory only and deletes it when the scan ends.",
} as const;

export const IMAGE_ACK = {
  label: "Save images from signed-in pages, and their text, on this computer",
  hintOcr:
    "Axcess saves the images and the text it reads from them (OCR) in its folder and database on this computer.",
  hintVision:
    "Axcess saves the images, the text it reads from them, and the vision model’s explanations on this computer. It sends image data only to Ollama at a checked address on this same computer (loopback).",
} as const;

export const SUBMIT = {
  public: { label: "Start scan", pending: "Starting scan…", note: "Watch the progress, or come back later. Axcess saves the report as it goes." },
  login: {
    label: "Open browser to sign in",
    pending: "Opening browser…",
    note: "A window opens for you to sign in. The scan starts when you press “I’m signed in”.",
  },
} as const;

export const ERRORS = {
  title: "The scan could not start",
  lead: "Fix these problems, then start the scan:",
  urlEmpty: "Enter a website address to start from.",
  urlNotHttp: "Use a web address, such as example.edu. Axcess only scans web pages.",
  urlNotHttps: "Start the address with https://. Sign-in scans only run over a secure connection.",
  urlHasExtras: "Remove anything after a ? or #, and any user name or password, from the address.",
  staticWithAxe:
    "Fast scan without a browser cannot run Rule check (axe). Turn off Fast scan, or choose Alfa as the rule check tool.",
  notAuthorized: "Confirm that the site owner allows this accessibility scan.",
  imageAck:
    "Before you turn on reading text inside images, confirm where Axcess saves the images and their text.",
  limitEmpty: (label: string, min: number, max: number) =>
    `${label} is empty. Enter a whole number from ${min} to ${max.toLocaleString()}.`,
  limitWhole: (label: string) => `${label} must be a whole number.`,
  limitMin: (label: string, min: number) => `${label} must be at least ${min}.`,
  limitMax: (label: string, max: number, mode: "public" | "login") =>
    `${label} can be at most ${max.toLocaleString()} for a ${mode === "login" ? "sign-in" : "public website"} scan.`,
} as const;

/**
 * The sign-in card: what New scan says while someone signs in, before any
 * scan exists. "Sign-in", not "Sign-in scan #N": there is no scan, and so no
 * number, until "I'm signed in, start scan" creates one. The limit of a kept
 * sign-in and the 30 minutes are stated, never dropped for length (rule 12
 * in docs/plain-language.md).
 */
export const SIGN_IN = {
  eyebrow: "Sign-in",
  scanEyebrow: (scanId: number) => `Sign-in scan #${scanId}`,
  site: (host: string) => `You have a sign-in in progress for ${host}.`,
  alreadyWaiting:
    "Axcess keeps one sign-in at a time, so it shows the one in progress instead of opening another window.",
  opening: {
    title: "Opening the sign-in window",
    detail: "A Chromium browser window should open on this computer.",
  },
  open: {
    title: "Sign in using the Chromium window",
    detail: "Finish every sign-in step, including two-step sign-in (2FA). Then come back here.",
  },
  closed: {
    title: "The sign-in window is closed",
    detail: "Axcess has kept your sign-in, so you can start the scan or reopen the window.",
  },
  limit:
    "Some sites tie a sign-in to the exact browser window, or end it quickly. If yours does, the site may ask you to sign in again after you reopen the window.",
  keep: (minutes: number) =>
    `Axcess keeps your sign-in in memory only. If you do not start the scan or reopen the window within ${minutes} minutes, Axcess forgets it.`,
  keepOpen: (minutes: number) =>
    `If you close the sign-in window before you start, Axcess keeps your sign-in for ${minutes} minutes, in memory only.`,
  start: "I’m signed in, start scan",
  starting: "Starting the scan…",
  reopen: "Reopen sign-in window",
  reopening: "Reopening the window…",
  cancel: "Cancel sign-in",
  cancelling: "Cancelling…",
  ended: {
    expired: (minutes: number) =>
      `Your sign-in was kept for ${minutes} minutes without use, so Axcess forgot it. Select “${SUBMIT.login.label}” to sign in again.`,
    cancelled:
      "You cancelled the sign-in. Axcess closed the sign-in window and forgot your sign-in. Your settings are still filled in.",
    failed:
      "Axcess could not open the sign-in window. Check the website address and that Chromium for Playwright is installed, then try again.",
    gone:
      "This sign-in has ended. Axcess keeps a sign-in only in memory, so it ends when Axcess quits. Sign in again to start a scan.",
  },
} as const;

/**
 * Starting again after a scan failed or was stopped. Settings come back;
 * sign-in and the confirmations never do, and the notice says so.
 */
export const RECOVERY = {
  loading: (id: number) => `Loading the settings from scan ${id}…`,
  loaded: (id: number) => `Axcess copied the settings from scan ${id}. Check them, then start the scan again.`,
  loadedLogin:
    "Axcess never saves your sign-in. Sign in again in the browser window, and confirm again below that the site owner allows this scan.",
  failed: (id: number) =>
    `Axcess could not load the settings from scan ${id}. The form shows the default settings instead.`,
} as const;

/**
 * The two ways back from a failed or stopped scan. "Scan again with faster
 * settings" is `quickRetrySettings`: the defaults (vision model, AI review
 * and the motion check off) with Click-Through off too.
 */
export const RETRY = {
  edit: "Change settings first",
  editHint:
    "Opens New scan with this scan’s settings filled in. Change what went wrong, then start the scan again. Axcess never saves your sign-in.",
  quick: "Scan again with faster settings",
  quickPending: "Starting the scan again…",
  quickHint:
    `Scans the same address again right away, with the default settings. It does not open menus or pop-up windows (${CLICK_THROUGH}), so it finishes sooner. That shows quickly whether Axcess can scan the site. It keeps only this scan’s address and its Web Content Accessibility Guidelines (WCAG) version.`,
} as const;

export const SUMMARY = {
  title: "What this scan will do",
  site: "Website",
  siteEmpty: "Enter a website address to see what will be scanned.",
  coverage: "Pages to scan",
  standard: "Standard",
  checks: "Checks that run",
  notIncluded: "Not included",
  nothingLeftOut: "Nothing: every option is on.",
  /** Listed under Not included when the saved page copies are skipped. */
  noRenderedCopies: "Saved copy of each page",
  /**
   * Also listed for a sign-in scan: its screenshots are cut from the same
   * signed-in pages, so the one switch drops both (server.py, the
   * capture_screenshots / store_rendered_html pair).
   */
  noScreenshots: "Screenshots of occurrences",
  /** For a public scan: it never signs in. */
  noSignIn: "Pages behind a sign-in",
  /** For a sign-in scan: it never leaves the approved website. */
  noOtherSites: "Pages on any other website",
  /** A Pages to scan line during a Fast scan. */
  htmlOnly: "Page code (HTML) only, no browser",
  loginPrivacy: "Axcess uploads nothing. It deletes the sign-in cookie (session cookie) when the scan ends.",
  localModels:
    "Uses only AI models already installed in Ollama on this computer. Axcess downloads nothing, and no image leaves this computer. Ollama may use several gigabytes (GB) of memory while it runs.",
  defaultState: "Default settings",
  customized: "Customized",
  reset: "Reset to default settings",
  footnote:
    "Automated checks find only about a third of accessibility problems. The report shows what a person still needs to check.",
} as const;

/**
 * Short names for the summary rail's two lists, one per switch. The rail
 * is read at a glance, so each is a few words in plain language; the
 * switch it stands for carries the full explanation.
 */
export const RAIL_LABELS = {
  whole_host: "Whole website",
  whole_host_login: "Whole signed-in website",
  include_subdomain: "Subdomains",
  click_through: `Opens menus and pop-up windows (${CLICK_THROUGH})`,
  keyboard: CHECK_LABEL.keyboard,
  focus: CHECK_LABEL.focus,
  responsive: CHECK_LABEL.responsive,
  ocr: CHECK_LABEL.image,
  vision: "Vision model review",
  semantic: CHECK_LABEL.semantic,
  motion: CHECK_LABEL.visual,
} as const;

/**
 * Click-Through wording outside its switch: why the switch can be
 * unavailable.
 */
export const CLICK_THROUGH_COPY = {
  /** Replaces the switch hint while the switch is disabled. */
  unavailableStatic: "Not available with Fast scan. Opening controls needs a browser.",
  unavailableAlfa:
    "Choose axe or Both as the rule check tool. Axcess checks the content that opens with Rule check (axe).",
} as const;
