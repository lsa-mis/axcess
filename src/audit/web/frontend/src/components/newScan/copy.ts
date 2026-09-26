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
export const TAB_LOGIN = "Site with a sign-in or two-step sign-in (2FA)";

export const URL_COPY = {
  public: {
    label: "Website address",
    help:
      "Start with https://. The scan only visits pages under this address. For example, an address ending in /section/ scans only that section.",
    placeholder: "https://example.edu/section/",
  },
  login: {
    label: "Website address to scan after you sign in",
    help:
      "Start with https://. Leave out anything after a ? or #. The scan only visits pages under this address and never leaves this website.",
    placeholder: "https://umich.instructure.com/courses/",
  },
} as const;

export const DEFAULTS_CARD = {
  title: "Default scan settings",
  selected: "Selected",
  customized: "Customized",
  leadDefault:
    "Axcess uses these settings unless you change something under Advanced settings.",
  leadCustom:
    "You changed something under Advanced settings. Crossed-out lines will not run in this scan.",
  reset: "Reset to default settings",
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
    label: "Open menus, tabs, and pop-up windows (dialogs)",
    hint:
      "Axcess opens controls on each page, then checks the content they show. This makes the scan take longer. It never submits forms, pays, or subscribes.",
  },
  keyboard: {
    label: "Check for keyboard traps",
    hint: "A keyboard trap is a control you can Tab into but not back out of. Adds 1–3 seconds per page.",
  },
  focus: {
    label: "Check that keyboard focus is never hidden",
    hint: "Finds the focus outline (the box that shows where the keyboard is) hidden behind sticky headers or footers. WCAG 2.4.11.",
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

export const NUMBERS = {
  max_pages: { label: "Maximum pages" },
  max_depth: {
    label: "Maximum link depth",
    hint: "How many clicks from the start page. 10 reaches almost every page on most sites.",
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
  hint: "Web Content Accessibility Guidelines (WCAG) 2.2. Most policies require Level AA. Level AAA adds the strictest rules, such as stronger color contrast (7:1).",
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
  urlNotHttp: "Add https:// at the start. Axcess only scans web addresses.",
  urlNotHttps: "Start the address with https://. Sign-in scans only run over a secure connection.",
  urlHasExtras: "Remove anything after a ? or #, and any user name or password, from the address.",
  staticWithAxe:
    "Fast scan without a browser cannot run Rule check (axe). Turn off Fast scan, or choose Alfa as the rule check tool.",
  notAuthorized: "Confirm that the site owner allows this accessibility scan.",
  imageAck:
    "Before you turn on reading text inside images, confirm where Axcess saves the images and their text.",
} as const;

export const SUMMARY = {
  title: "What this scan will do",
  site: "Website",
  siteEmpty: "Enter a website address to see what will be scanned.",
  coverage: "Pages to scan",
  checks: "Checks",
  localAi: "AI checks on this computer",
  storage: "What is saved",
  notIncluded: "Not included",
  footnote:
    "Automated checks find only about a third of accessibility problems. The report shows what a person still needs to check.",
} as const;
