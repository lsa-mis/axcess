/**
 * Display and behaviour preferences for this browser.
 *
 * They are a person's own reading and input needs, not report data, so they
 * live in localStorage on this computer and never reach the API. Every
 * setting is applied as an attribute on <html> (see `applyPreferences`), and
 * styles.css does the rest; the few that need behaviour (page size, message
 * timing, confirmations, shortcuts) are read through `usePreferences`.
 *
 * Reads fail soft: a private window, blocked storage or a stored value from
 * an older build all fall back to the defaults for the keys they miss.
 */

export type Theme = "light" | "dark" | "system";
export type TextSize = "100" | "112" | "125";
export type LinkUnderlines = "hover" | "always";
export type Contrast = "standard" | "more" | "high";
export type ColorVision = "standard" | "protan" | "deutan" | "tritan" | "grayscale";
export type Font = "atkinson" | "system" | "serif";
export type TextSpacing = "normal" | "wide" | "wcag";
export type OnOff = "off" | "on";
export type FocusIndicator = "standard" | "strong" | "always";
export type TargetSize = "44" | "52" | "60";
export type TableDensity = "compact" | "comfortable" | "spacious";
export type Announcements = "polite" | "immediate" | "visual";
export type Hints = "hover" | "always" | "off";
export type MessageTiming = "standard" | "extended" | "never";
export type Motion = "system" | "on" | "off";
export type RowsPerPage = "10" | "25" | "50";
export type SidebarState = "open" | "collapsed";

export interface Preferences {
  theme: Theme;
  textSize: TextSize;
  linkUnderlines: LinkUnderlines;
  contrast: Contrast;
  colorVision: ColorVision;
  font: Font;
  textSpacing: TextSpacing;
  dyslexiaSpacing: OnOff;
  readingGuide: OnOff;
  focusIndicator: FocusIndicator;
  targetSize: TargetSize;
  tableDensity: TableDensity;
  announcements: Announcements;
  hints: Hints;
  shortcuts: OnOff;
  messageTiming: MessageTiming;
  confirmDelete: OnOff;
  motion: Motion;
  rowsPerPage: RowsPerPage;
  sidebar: SidebarState;
}

export const DEFAULT_PREFERENCES: Preferences = {
  theme: "light",
  textSize: "100",
  linkUnderlines: "hover",
  contrast: "standard",
  colorVision: "standard",
  font: "atkinson",
  textSpacing: "normal",
  dyslexiaSpacing: "off",
  readingGuide: "off",
  focusIndicator: "standard",
  targetSize: "44",
  tableDensity: "comfortable",
  announcements: "polite",
  hints: "hover",
  shortcuts: "on",
  messageTiming: "standard",
  confirmDelete: "on",
  motion: "system",
  rowsPerPage: "10",
  sidebar: "open",
};

/** Every allowed value per key, so a stored value from another build is checked, not trusted. */
const ALLOWED: { [K in keyof Preferences]: ReadonlyArray<Preferences[K]> } = {
  theme: ["light", "dark", "system"],
  textSize: ["100", "112", "125"],
  linkUnderlines: ["hover", "always"],
  contrast: ["standard", "more", "high"],
  colorVision: ["standard", "protan", "deutan", "tritan", "grayscale"],
  font: ["atkinson", "system", "serif"],
  textSpacing: ["normal", "wide", "wcag"],
  dyslexiaSpacing: ["off", "on"],
  readingGuide: ["off", "on"],
  focusIndicator: ["standard", "strong", "always"],
  targetSize: ["44", "52", "60"],
  tableDensity: ["compact", "comfortable", "spacious"],
  announcements: ["polite", "immediate", "visual"],
  hints: ["hover", "always", "off"],
  shortcuts: ["on", "off"],
  messageTiming: ["standard", "extended", "never"],
  confirmDelete: ["on", "off"],
  motion: ["system", "on", "off"],
  rowsPerPage: ["10", "25", "50"],
  sidebar: ["open", "collapsed"],
};

export interface Preset {
  id: string;
  label: string;
  values: Partial<Preferences>;
}

/**
 * Starting points, not profiles: a preset writes these keys and leaves the
 * rest as they were, and every one can be changed afterwards.
 */
export const PRESETS: ReadonlyArray<Preset> = [
  {
    id: "low-vision",
    label: "Low vision",
    values: { textSize: "125", contrast: "high", linkUnderlines: "always", focusIndicator: "strong", tableDensity: "spacious" },
  },
  {
    id: "motor",
    label: "Motor / tremor",
    values: { targetSize: "60", tableDensity: "spacious", confirmDelete: "on", messageTiming: "never", focusIndicator: "strong" },
  },
  {
    id: "reading",
    label: "Reading / focus",
    values: { textSpacing: "wide", dyslexiaSpacing: "on", readingGuide: "on", motion: "off", messageTiming: "extended" },
  },
  {
    id: "screen-reader",
    label: "Screen reader",
    values: { announcements: "polite", shortcuts: "off", hints: "always", motion: "off", messageTiming: "never" },
  },
];

/**
 * A preset is on while every key it sets still has its value, so changing
 * one of those settings by hand turns it off, and applying it again or
 * setting them back turns it on. Nothing is stored beyond the settings.
 */
export function presetIsOn(prefs: Preferences, preset: Preset): boolean {
  return (Object.keys(preset.values) as Array<keyof Preferences>).every(
    (key) => prefs[key] === preset.values[key],
  );
}

/**
 * The changes that turn a preset off: each of its keys goes back to the
 * default, except where another preset that is on sets the same key, so
 * turning Low vision off leaves Motor's bolder focus outline alone.
 */
export function presetOffValues(prefs: Preferences, preset: Preset): Partial<Preferences> {
  const others = PRESETS.filter((other) => other.id !== preset.id && presetIsOn(prefs, other));
  const off: Partial<Preferences> = {};
  for (const key of Object.keys(preset.values) as Array<keyof Preferences>) {
    if (others.some((other) => key in other.values)) continue;
    (off as Record<string, unknown>)[key] = DEFAULT_PREFERENCES[key];
  }
  return off;
}

const STORAGE_KEY = "axcess.preferences";
/** AppShell's older key for the sidebar; still honoured so nobody's rail flips open. */
const LEGACY_SIDEBAR_KEY = "axcess.sidebar.collapsed";

export function loadPreferences(): Preferences {
  const prefs: Preferences = { ...DEFAULT_PREFERENCES };
  let stored: Record<string, unknown> = {};
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) stored = JSON.parse(raw) as Record<string, unknown>;
    else if (localStorage.getItem(LEGACY_SIDEBAR_KEY) === "1") stored = { sidebar: "collapsed" };
  } catch {
    return prefs;
  }
  for (const key of Object.keys(ALLOWED) as Array<keyof Preferences>) {
    const value = stored[key];
    if ((ALLOWED[key] as ReadonlyArray<unknown>).includes(value)) {
      (prefs as unknown as Record<string, unknown>)[key] = value;
    }
  }
  return prefs;
}

export function savePreferences(prefs: Preferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    localStorage.setItem(LEGACY_SIDEBAR_KEY, prefs.sidebar === "collapsed" ? "1" : "0");
  } catch {
    // Storage unavailable: the change still applies for this session.
  }
}

const darkQuery = (): MediaQueryList | null =>
  typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

export function resolvedTheme(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  return darkQuery()?.matches ? "dark" : "light";
}

/** Follow the OS while Theme is System. Returns the unsubscribe. */
export function watchSystemTheme(onChange: () => void): () => void {
  const query = darkQuery();
  if (!query) return () => {};
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/**
 * Write the preferences onto <html>. Pure DOM, no React, so main.tsx can run
 * it before the first render and the page never flashes the defaults.
 */
export function applyPreferences(prefs: Preferences, root: HTMLElement = document.documentElement): void {
  const theme = resolvedTheme(prefs.theme);
  root.dataset.theme = theme;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
  root.dataset.contrast = prefs.contrast;
  root.dataset.colorVision = prefs.colorVision;
  root.dataset.font = prefs.font;
  root.dataset.textSpacing = prefs.textSpacing;
  root.dataset.dyslexia = prefs.dyslexiaSpacing;
  root.dataset.links = prefs.linkUnderlines;
  root.dataset.focus = prefs.focusIndicator;
  root.dataset.density = prefs.tableDensity;
  root.dataset.motion = prefs.motion;
  root.style.fontSize = prefs.textSize === "100" ? "" : prefs.textSize === "112" ? "112.5%" : "125%";
  root.style.setProperty("--target", `${prefs.targetSize}px`);
}

/** How long a transient message stays, in ms; null means until dismissed. */
export function messageDuration(timing: MessageTiming, standardMs: number): number | null {
  if (timing === "never") return null;
  return timing === "extended" ? standardMs * 5 : standardMs;
}
