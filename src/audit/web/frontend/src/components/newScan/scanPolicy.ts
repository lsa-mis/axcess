import type { LocalLoginScanPayload, NewScanPayload, ScanSettingsSnapshot } from "../../api/types";
import { ERRORS, FIXED_NOTE_LOGIN, NUMBERS, SUBMIT, URL_COPY } from "./copy";

/**
 * One settings model for both scan forms.
 *
 * The public and login forms used to keep two hand-written state objects
 * with different keys, different defaults, and three checkboxes the login
 * form rendered permanently disabled "for parity". `NewScanPayload` is the
 * superset, so it is the model; a `ScanPolicy` says how one mode narrows it:
 * caps, values that cannot change, and which words the URL field uses. The
 * form renders the same components under either policy and the login
 * payload is derived at submit time.
 */
export type ScanSettings = NewScanPayload;
export type ScanMode = "public" | "login";

/** "form" is a problem with no single field behind it: the server said no. */
export type FieldKey =
  | "url"
  | "max_pages"
  | "max_depth"
  | "static_only"
  | "authorized"
  | "image_ack"
  | "form";
export type FieldError = { field: FieldKey; message: string };

export type ScanPolicy = {
  mode: ScanMode;
  caps: { max_pages: number; max_depth: number; rps: number; workers: number };
  /** The scan that runs when nothing is touched; what the default card lists. */
  defaults: ScanSettings;
  /** Settings this mode pins; the form neither shows nor sends a control for them. */
  fixed: Partial<ScanSettings>;
  fixedNote: string | null;
  urlLabel: string;
  urlHelp: string;
  urlPlaceholder: string;
  submitLabel: string;
  submitPendingLabel: string;
  submitNote: string;
  /** A message for the URL field, or null when the address is usable. */
  validateUrl: (raw: string) => string | null;
};

/** Every setting the default card and `isDefault` compare; never the URL. */
const SETTING_KEYS = [
  "max_pages",
  "all_pages",
  "max_depth",
  "rps",
  "workers",
  "include_subdomain",
  "whole_host",
  "ignore_robots",
  "skip_ocr",
  "skip_vlm",
  "static_only",
  "show_browser",
  "scan_engine",
  "skip_interaction",
  "skip_keyboard",
  "skip_responsive",
  "skip_semantic",
  "skip_focus",
  "skip_visual",
  "skip_rendered_storage",
  "axe_level",
  "wcag_version",
] as const satisfies ReadonlyArray<keyof ScanSettings>;

export const PUBLIC_DEFAULTS: ScanSettings = {
  url: "",
  max_pages: 2500,
  all_pages: false,
  max_depth: 10,
  rps: 2.0,
  workers: 8,
  include_subdomain: false,
  whole_host: false,
  ignore_robots: false,
  skip_ocr: false,
  // Deterministic OCR stays on; repeated model calls stay off. They are
  // expert-review leads, not prerequisites for the report, and can dominate
  // scan time.
  skip_vlm: true,
  static_only: false,
  show_browser: false,
  scan_engine: "axe",
  skip_interaction: false,
  skip_keyboard: false,
  skip_responsive: false,
  skip_semantic: true,
  skip_focus: false,
  skip_visual: true,
  skip_rendered_storage: false,
  axe_level: "AA",
  // The current U-M standard. 2.2 is a deliberate choice, and marks the
  // settings Customized.
  wcag_version: "2.1",
};

/** The login form's own defaults, on the shared shape. */
export const LOGIN_DEFAULTS: ScanSettings = {
  ...PUBLIC_DEFAULTS,
  rps: 1,
  workers: 2,
  // A signed-in session is the only way to reach these pages; robots.txt is
  // written for anonymous crawlers, and the authorization checkbox is the
  // consent that replaces it.
  ignore_robots: true,
  // Protected images are only read after the reviewer acknowledges where
  // the evidence is stored, so image text reading starts off.
  skip_ocr: true,
};

function parseUrl(raw: string): URL | null {
  try {
    return new URL(raw.trim());
  } catch {
    return null;
  }
}

export const PUBLIC_POLICY: ScanPolicy = {
  mode: "public",
  caps: { max_pages: 10000, max_depth: 20, rps: 50, workers: 32 },
  defaults: PUBLIC_DEFAULTS,
  fixed: {},
  fixedNote: null,
  urlLabel: URL_COPY.public.label,
  urlHelp: URL_COPY.public.help,
  urlPlaceholder: URL_COPY.public.placeholder,
  submitLabel: SUBMIT.public.label,
  submitPendingLabel: SUBMIT.public.pending,
  submitNote: SUBMIT.public.note,
  validateUrl: (raw) => {
    if (!raw.trim()) return ERRORS.urlEmpty;
    const url = parseUrl(raw);
    if (!url || (url.protocol !== "http:" && url.protocol !== "https:")) {
      return ERRORS.urlNotHttp;
    }
    return null;
  },
};

export const LOGIN_POLICY: ScanPolicy = {
  mode: "login",
  caps: { max_pages: 2500, max_depth: 20, rps: 5, workers: 4 },
  defaults: LOGIN_DEFAULTS,
  fixed: {
    // A signed-in session keeps its page cap: an unbounded crawl behind a
    // sign-in is a load the session and the site owner did not agree to.
    all_pages: false,
    include_subdomain: false,
    static_only: false,
    ignore_robots: true,
    // Not offered for signed-in scans; the login payload has no field for
    // them, so they stay at their defaults and are dropped at submit.
    skip_semantic: true,
    skip_focus: false,
    skip_visual: true,
  },
  fixedNote: FIXED_NOTE_LOGIN,
  urlLabel: URL_COPY.login.label,
  urlHelp: URL_COPY.login.help,
  urlPlaceholder: URL_COPY.login.placeholder,
  submitLabel: SUBMIT.login.label,
  submitPendingLabel: SUBMIT.login.pending,
  submitNote: SUBMIT.login.note,
  validateUrl: (raw) => {
    if (!raw.trim()) return ERRORS.urlEmpty;
    const url = parseUrl(raw);
    if (!url) return ERRORS.urlNotHttp;
    if (url.protocol !== "https:") return ERRORS.urlNotHttps;
    if (url.username || url.password || url.search || url.hash) {
      return ERRORS.urlHasExtras;
    }
    return null;
  },
};

export function policyFor(mode: ScanMode): ScanPolicy {
  return mode === "login" ? LOGIN_POLICY : PUBLIC_POLICY;
}

export function isFixed(policy: ScanPolicy, key: keyof ScanSettings): boolean {
  return key in policy.fixed;
}

/** Apply a mode's pinned values; used when settings are created or a mode changes. */
export function applyPolicy(settings: ScanSettings, policy: ScanPolicy): ScanSettings {
  return { ...settings, ...policy.fixed };
}

/** True when every non-URL setting still matches the mode's defaults. */
export function isDefault(settings: ScanSettings, policy: ScanPolicy): boolean {
  return SETTING_KEYS.every((key) => settings[key] === policy.defaults[key]);
}

/** The smallest value either limit accepts; the largest is the mode's cap. */
export const LIMIT_MIN = 1;

/** A limit as the cards print it; "?" while its box is empty. */
export function limitText(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString() : "?";
}

/**
 * A message for Max pages or Max link depth, or null when the value is
 * usable. The number field hands over `NaN` for an empty box, so "empty"
 * is its own message rather than a silent 0 or a silent default. Nothing is
 * clamped: a value outside the range is named, with the range, so the
 * reader decides what they meant.
 */
export function limitError(
  key: "max_pages" | "max_depth",
  value: number,
  policy: ScanPolicy,
): string | null {
  const { label } = NUMBERS[key];
  const max = policy.caps[key];
  if (!Number.isFinite(value)) return ERRORS.limitEmpty(label, LIMIT_MIN, max);
  if (!Number.isInteger(value)) return ERRORS.limitWhole(label);
  if (value < LIMIT_MIN) return ERRORS.limitMin(label, LIMIT_MIN);
  if (value > max) return ERRORS.limitMax(label, max, policy.mode);
  return null;
}

/** Everything the form validates before it lets a scan start. */
export function validateScan(
  settings: ScanSettings,
  policy: ScanPolicy,
  extras: { authorized?: boolean; imageAck?: boolean } = {},
): FieldError[] {
  const errors: FieldError[] = [];
  const urlMessage = policy.validateUrl(settings.url);
  if (urlMessage) errors.push({ field: "url", message: urlMessage });
  for (const key of ["max_pages", "max_depth"] as const) {
    // With no page limit the Maximum pages box is off, so its value is not checked.
    if (key === "max_pages" && settings.all_pages && !isFixed(policy, "all_pages")) continue;
    const message = limitError(key, settings[key], policy);
    if (message) errors.push({ field: key, message });
  }
  if (settings.static_only && settings.scan_engine !== "alfa") {
    errors.push({ field: "static_only", message: ERRORS.staticWithAxe });
  }
  if (policy.mode === "login") {
    if (!extras.authorized) {
      errors.push({ field: "authorized", message: ERRORS.notAuthorized });
    }
    if (!settings.skip_ocr && !extras.imageAck) {
      errors.push({ field: "image_ack", message: ERRORS.imageAck });
    }
  }
  return errors;
}

/** The subset the local-login API accepts, with the URL normalized. */
export function toLocalLoginPayload(
  settings: ScanSettings,
  extras: { imageAck: boolean },
): LocalLoginScanPayload {
  const seed = parseUrl(settings.url);
  return {
    search: settings.search ?? null,
    seed_url: seed ? seed.toString() : settings.url.trim(),
    approved_auth_origins: [],
    authorization_acknowledged: true,
    max_pages: settings.max_pages,
    max_depth: settings.max_depth,
    rps: settings.rps,
    workers: settings.workers,
    whole_host: settings.whole_host,
    show_browser: settings.show_browser,
    scan_engine: settings.scan_engine,
    axe_level: settings.axe_level,
    wcag_version: settings.wcag_version,
    skip_interaction: settings.skip_interaction,
    skip_keyboard: settings.skip_keyboard,
    skip_responsive: settings.skip_responsive,
    skip_ocr: settings.skip_ocr,
    skip_vlm: settings.skip_vlm,
    skip_rendered_storage: settings.skip_rendered_storage,
    image_analysis_acknowledged: extras.imageAck,
  };
}

/**
 * The positive switches the groups render, and the payload field each one
 * writes. `on` reads the setting the way the label says it; `set` writes
 * the field the API expects, inverting the `skip_*` ones here and nowhere
 * else.
 */
export type SwitchKey =
  | "whole_host"
  | "include_subdomain"
  | "ignore_robots"
  | "click_through"
  | "keyboard"
  | "focus"
  | "responsive"
  | "skip_rendered_storage"
  | "ocr"
  | "vision"
  | "semantic"
  | "motion"
  | "static_only"
  | "show_browser";

const SWITCH_FIELDS: Record<SwitchKey, { field: keyof ScanSettings; inverted: boolean }> = {
  whole_host: { field: "whole_host", inverted: false },
  include_subdomain: { field: "include_subdomain", inverted: false },
  ignore_robots: { field: "ignore_robots", inverted: false },
  click_through: { field: "skip_interaction", inverted: true },
  keyboard: { field: "skip_keyboard", inverted: true },
  focus: { field: "skip_focus", inverted: true },
  responsive: { field: "skip_responsive", inverted: true },
  skip_rendered_storage: { field: "skip_rendered_storage", inverted: false },
  ocr: { field: "skip_ocr", inverted: true },
  vision: { field: "skip_vlm", inverted: true },
  semantic: { field: "skip_semantic", inverted: true },
  motion: { field: "skip_visual", inverted: true },
  static_only: { field: "static_only", inverted: false },
  show_browser: { field: "show_browser", inverted: false },
};

export function switchField(key: SwitchKey): keyof ScanSettings {
  return SWITCH_FIELDS[key].field;
}

export function switchOn(settings: ScanSettings, key: SwitchKey): boolean {
  const { field, inverted } = SWITCH_FIELDS[key];
  const value = Boolean(settings[field]);
  return inverted ? !value : value;
}

/** The patch that turns a switch on or off, plus the consequences the old
 *  handlers applied by hand (OCR off turns the vision model off, and so on). */
export function switchPatch(
  settings: ScanSettings,
  key: SwitchKey,
  on: boolean,
): Partial<ScanSettings> {
  const { field, inverted } = SWITCH_FIELDS[key];
  const patch: Partial<ScanSettings> = { [field]: inverted ? !on : on };
  if (key === "ocr" && !on) patch.skip_vlm = true;
  if (key === "static_only" && on) patch.skip_interaction = true;
  void settings;
  return patch;
}

/**
 * The checks a scan runs on each page, and whether each one will run.
 *
 * Every "N of M on" on the page is counted from this one list: the Checks
 * and Local AI headers each count their own group, and the summary rail
 * counts both, so the three numbers always add up. A check counts as on
 * only when it will actually run, so a switch that is still on but cannot
 * work (a browser check under Fast crawl) is off here, and a check this
 * mode does not offer is not counted at all. Click-Through, the scope
 * switches and storage are not checks: they change which pages and states
 * are covered, and the Coverage header describes them instead.
 */
export type CheckGroup = "checks" | "localAi";
export type CheckItem = { key: SwitchKey; group: CheckGroup; label: string; on: boolean };

const CHECKS: ReadonlyArray<{ key: SwitchKey; group: CheckGroup; label: string; needsBrowser?: true }> = [
  { key: "keyboard", group: "checks", label: "Keyboard traps", needsBrowser: true },
  { key: "focus", group: "checks", label: "Focus visibility", needsBrowser: true },
  { key: "responsive", group: "checks", label: "Responsive & zoom", needsBrowser: true },
  { key: "ocr", group: "localAi", label: "Image text (OCR)" },
  { key: "vision", group: "localAi", label: "Vision model" },
  { key: "semantic", group: "localAi", label: "Wording review" },
  { key: "motion", group: "localAi", label: "Motion & animation" },
];

export function checkInventory(settings: ScanSettings, policy: ScanPolicy): CheckItem[] {
  return CHECKS.filter((check) => !isFixed(policy, switchField(check.key))).map((check) => ({
    key: check.key,
    group: check.group,
    label: check.label,
    on:
      switchOn(settings, check.key) &&
      !(check.needsBrowser && settings.static_only) &&
      // The vision model only reviews images OCR found text in.
      !(check.key === "vision" && !switchOn(settings, "ocr")),
  }));
}

/** "N of M on" for one group, or for every check when `group` is omitted. */
export function checkCount(
  settings: ScanSettings,
  policy: ScanPolicy,
  group?: CheckGroup,
): { on: number; total: number } {
  const items = checkInventory(settings, policy).filter((item) => !group || item.group === group);
  return { on: items.filter((item) => item.on).length, total: items.length };
}

/**
 * What "Quick retry" on a failed scan runs: the public defaults with
 * Click-Through off, so it finishes fast enough to show whether the site
 * can be scanned at all. It keeps only the address and the WCAG version of
 * the scan it retries; "Edit settings and retry" is the path that keeps
 * everything else.
 */
export function quickRetrySettings(url: string, wcagVersion: ScanSettings["wcag_version"]): ScanSettings {
  return { ...PUBLIC_DEFAULTS, url, wcag_version: wcagVersion, skip_interaction: true };
}

/**
 * A previous scan's settings, laid over this mode's defaults. The snapshot
 * holds scan settings only (the server builds it from an allow-list); the
 * authorization and image-storage confirmations and any sign-in stay with
 * the person, who gives them again. Out-of-range values are kept as they
 * were so validation can name them instead of silently changing them.
 */
export function settingsFromSnapshot(snapshot: ScanSettingsSnapshot, policy: ScanPolicy): ScanSettings {
  return applyPolicy({ ...policy.defaults, ...snapshot.settings }, policy);
}
