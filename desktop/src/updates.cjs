/**
 * Pure helpers behind the launch-time update check. Nothing here touches
 * Electron so the decisions can be unit-tested with plain Node.
 *
 * Every push to `main` publishes a GitHub Release tagged with the next
 * two-part version, `desktop-v0.61` after `desktop-v0.60` (see
 * .github/workflows/desktop-build.yml and `nextReleaseVersion`). The packaged app asks the GitHub
 * API for the latest release once per launch and compares it with its own
 * stamped version. What it can do with a newer release depends on the
 * platform: on Windows electron-updater installs it in place from the
 * release's asset directory, while macOS only opens the DMG download because
 * Squirrel.Mac refuses to update an app that is not Developer ID signed.
 */
const REPOSITORY = "lsa-mis/axcess";
const RELEASES_API_URL = `https://api.github.com/repos/${REPOSITORY}/releases/latest`;
const RELEASES_PAGE_URL = `https://github.com/${REPOSITORY}/releases/latest`;
const RELEASE_DOWNLOAD_PATH = `/${REPOSITORY}/releases/download/`;

/** Split "0.1.57" into [0, 1, 57]; returns null for anything else. */
function parseVersion(text) {
  if (typeof text !== "string") return null;
  const trimmed = text.trim().replace(/^v/, "");
  if (!/^\d+(\.\d+)*$/.test(trimmed)) return null;
  return trimmed.split(".").map(Number);
}

/**
 * Numeric dotted-version comparison; missing trailing components count as 0,
 * so "0.1" equals "0.1.0". Returns -1, 0 or 1, or null when either side is
 * not a plain dotted version.
 */
function compareVersions(left, right) {
  const a = parseVersion(left);
  const b = parseVersion(right);
  if (!a || !b) return null;
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    const difference = (a[index] || 0) - (b[index] || 0);
    if (difference !== 0) return difference < 0 ? -1 : 1;
  }
  return 0;
}

/**
 * The only URLs the updater will ever hand to the system browser: an HTTPS
 * asset download under this repository's releases. Rejects other hosts, other
 * repositories, and release pages that are not asset downloads.
 */
function isReleaseAssetUrl(candidate) {
  try {
    const parsed = new URL(candidate);
    return (
      parsed.protocol === "https:" &&
      parsed.hostname === "github.com" &&
      parsed.pathname.startsWith(RELEASE_DOWNLOAD_PATH) &&
      parsed.pathname.length > RELEASE_DOWNLOAD_PATH.length
    );
  } catch {
    return false;
  }
}

/** The version a release tag carries: "desktop-v0.1.57" and "v0.1.57" -> "0.1.57". */
function releaseVersion(tag) {
  if (typeof tag !== "string") return null;
  const version = tag.replace(/^desktop-v/, "").replace(/^v/, "");
  return parseVersion(version) ? version : null;
}

/**
 * Reduce a GitHub "latest release" payload to what the launcher needs for the
 * running platform. Returns null when the payload is not a usable release.
 *
 * - `dmgUrl` (darwin): the DMG built for this CPU architecture, if published.
 * - `zipUrl` (win32): the portable zip for this CPU architecture, if published.
 * - `feedUrl` (win32): the release's asset directory, which electron-updater
 *   reads `latest.yml` and the NSIS installer it names from. Only set when
 *   the release actually carries a `latest.yml` file.
 */
function describeRelease(release, { platform, arch }) {
  if (!release || typeof release !== "object" || release.draft || release.prerelease) return null;
  const tag = release.tag_name;
  const version = releaseVersion(tag);
  if (!version) return null;
  const assets = Array.isArray(release.assets) ? release.assets : [];
  const names = new Set(assets.map((asset) => asset && asset.name));

  let dmgUrl = null;
  if (platform === "darwin") {
    const dmg = assets.find(
      (asset) =>
        asset &&
        typeof asset.name === "string" &&
        asset.name.endsWith(`-${arch}.dmg`) &&
        isReleaseAssetUrl(asset.browser_download_url),
    );
    dmgUrl = dmg ? dmg.browser_download_url : null;
  }

  // The portable zip for a copy Setup did not install (windowsUpdateMethod).
  let zipUrl = null;
  if (platform === "win32") {
    const zip = assets.find(
      (asset) =>
        asset &&
        asset.name === `Axcess-${version}-Windows-${arch}-portable.zip` &&
        isReleaseAssetUrl(asset.browser_download_url),
    );
    zipUrl = zip ? zip.browser_download_url : null;
  }

  const feedUrl =
    platform === "win32" && names.has("latest.yml")
      ? `https://github.com/${REPOSITORY}/releases/download/${encodeURIComponent(tag)}`
      : null;

  return { tag, version, dmgUrl, zipUrl, feedUrl, pageUrl: RELEASES_PAGE_URL };
}

/** True when `release` (from describeRelease) is strictly newer than the running app. */
function isNewerRelease(release, currentVersion) {
  if (!release) return false;
  return compareVersions(release.version, currentVersion) === 1;
}

/**
 * How a version reads to people: two parts, "0.61", with two digits after
 * the point, so 0.69 is followed by 0.70 and 0.99 by 1.00. npm and
 * electron-updater need three-part semver, so the package itself carries
 * "0.61.0" (and "1.0.0" for 1.00); this drops the ".0" again. A version
 * from before the two-part scheme ("0.1.33") is shown as it is.
 */
function displayVersion(version) {
  const parts = parseVersion(version);
  if (!parts) return String(version);
  if (parts.length === 3 && parts[2] !== 0) return parts.join(".");
  return `${parts[0]}.${String(parts[1] ?? 0).padStart(2, "0")}`;
}

/** The semver a two-part version is packaged as: "0.61" -> "0.61.0", "1.00" -> "1.0.0". */
function packageVersion(version) {
  const parts = parseVersion(version);
  if (!parts || parts.length !== 2) throw new Error(`Not a two-part version: ${version}`);
  return `${parts[0]}.${parts[1]}.0`;
}

/**
 * The version of the next release, given the release tags that exist: one
 * step after the highest two-part tag ("desktop-v0.60" -> "0.61",
 * "desktop-v0.99" -> "1.00"), or `first` when there is none yet. Tags of
 * the old three-part scheme ("desktop-v0.1.33") do not count.
 */
function nextReleaseVersion(tags, first = "0.60") {
  let highest = null;
  for (const tag of tags) {
    const match = /^desktop-v(\d+)\.(\d{2})$/.exec(String(tag).trim());
    if (!match) continue;
    const step = Number(match[1]) * 100 + Number(match[2]);
    if (highest === null || step > highest) highest = step;
  }
  if (highest === null) return first;
  const next = highest + 1;
  return `${Math.floor(next / 100)}.${String(next % 100).padStart(2, "0")}`;
}

module.exports = {
  RELEASES_API_URL,
  RELEASES_PAGE_URL,
  compareVersions,
  describeRelease,
  displayVersion,
  isNewerRelease,
  isReleaseAssetUrl,
  nextReleaseVersion,
  packageVersion,
  parseVersion,
  releaseVersion,
};
