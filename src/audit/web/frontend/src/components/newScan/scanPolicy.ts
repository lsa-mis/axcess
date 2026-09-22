import type { LocalLoginScanPayload, NewScanPayload } from "../../api/types";
import { ERRORS, FIXED_NOTE_LOGIN, SUBMIT, URL_COPY } from "./copy";

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
export type FieldKey = "url" | "static_only" | "authorized" | "image_ack" | "form";
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
] as const satisfies ReadonlyArray<keyof ScanSettings>;

export const PUBLIC_DEFAULTS: ScanSettings = {
  url: "",
  max_pages: 2500,
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
    include_subdomain: false,
    static_only: false,
    ignore_robots: true,
    show_browser: false,
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

/** Everything the form validates before it lets a scan start. */
export function validateScan(
  settings: ScanSettings,
  policy: ScanPolicy,
  extras: { authorized?: boolean; imageAck?: boolean } = {},
): FieldError[] {
  const errors: FieldError[] = [];
  const urlMessage = policy.validateUrl(settings.url);
  if (urlMessage) errors.push({ field: "url", message: urlMessage });
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
    scan_engine: settings.scan_engine,
    axe_level: settings.axe_level,
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
