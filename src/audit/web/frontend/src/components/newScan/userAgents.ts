/**
 * The browser names (user agents) New scan offers, and the exact string each
 * one sends.
 *
 * Checked on 2026-11-13 against the browsers' current stable releases:
 * Chrome 157 (chromereleases.googleblog.com), Edge 157 (Microsoft's Edge
 * stable release notes), Firefox 160 (released 2026-11-10, firefox.com
 * release notes) and Safari 27.2 (Apple's Safari release notes, 2026-10-26).
 * Update the version numbers here when they fall behind; nothing else
 * needs to change. A scan run again from an old report picks up the strings
 * here, so it sends the browser as it is now, not as it was then.
 *
 * Several parts of these strings are frozen by the browser makers, so only
 * the version number moves:
 * - Chrome and Edge send only the major version ("157.0.0.0"), always
 *   "Windows NT 10.0", "Intel Mac OS X 10_15_7", and "Android 10; K" for
 *   every phone (Chromium "User-Agent Reduction",
 *   https://www.chromium.org/updates/ua-reduction/).
 * - Firefox reports every Mac as "Intel Mac OS X 10.15" (MDN, "Firefox user
 *   agent string reference").
 * - Safari reports every Mac as "Intel Mac OS X 10_15_7", and since Safari 26
 *   every iPhone as "iPhone OS 18_7" (earlier releases froze it at 18_6). The
 *   real version is in "Version/27.2".
 *
 * Labels name the browser and the device, not the version: the version is
 * in the string shown under the choice, and a label with a number in it goes
 * stale between releases.
 */

export type UserAgentPreset = {
  id: string;
  label: string;
  value: string;
  /** A phone browser: the form says the window stays computer-sized. */
  phone?: true;
};

/** Sends Axcess's own name, the server's `user_agent` setting. */
export const DEFAULT_USER_AGENT_CHOICE = "axcess";
/** The person types the string. */
export const CUSTOM_USER_AGENT_CHOICE = "custom";

const CHROME = "157";
const EDGE = "157";
const FIREFOX = "160";
const SAFARI = "27.2";

export const USER_AGENT_PRESETS: readonly UserAgentPreset[] = [
  {
    id: "chrome_windows",
    label: "Chrome on Windows",
    value: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${CHROME}.0.0.0 Safari/537.36`,
  },
  {
    id: "chrome_mac",
    label: "Chrome on Mac",
    value: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${CHROME}.0.0.0 Safari/537.36`,
  },
  {
    id: "chrome_android",
    label: "Chrome on an Android phone",
    phone: true,
    value: `Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${CHROME}.0.0.0 Mobile Safari/537.36`,
  },
  {
    id: "edge_windows",
    label: "Edge on Windows",
    value: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${EDGE}.0.0.0 Safari/537.36 Edg/${EDGE}.0.0.0`,
  },
  {
    id: "firefox_windows",
    label: "Firefox on Windows",
    value: `Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:${FIREFOX}.0) Gecko/20100101 Firefox/${FIREFOX}.0`,
  },
  {
    id: "firefox_mac",
    label: "Firefox on Mac",
    value: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:${FIREFOX}.0) Gecko/20100101 Firefox/${FIREFOX}.0`,
  },
  {
    id: "safari_mac",
    label: "Safari on Mac",
    value: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/${SAFARI} Safari/605.1.15`,
  },
  {
    id: "safari_iphone",
    label: "Safari on iPhone",
    phone: true,
    value: `Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/${SAFARI} Mobile/15E148 Safari/604.1`,
  },
];

/** The same limit the server applies (`audit.crawler.user_agent`). */
export const MAX_USER_AGENT_LENGTH = 512;

export function presetFor(choice: string): UserAgentPreset | undefined {
  return USER_AGENT_PRESETS.find((preset) => preset.id === choice);
}

/** True for a choice this version of the form can show. */
export function knownChoice(choice: string): boolean {
  return choice === DEFAULT_USER_AGENT_CHOICE || choice === CUSTOM_USER_AGENT_CHOICE || Boolean(presetFor(choice));
}

/**
 * The string a scan will send, or null for Axcess's own name (which only
 * the server knows: it is a server setting).
 */
export function userAgentToSend(choice: string, typed: string): string | null {
  if (choice === CUSTOM_USER_AGENT_CHOICE) return typed.trim();
  return presetFor(choice)?.value ?? null;
}
