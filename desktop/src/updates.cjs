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
 * - `appImageUrl` (linux): the AppImage for this CPU architecture, if published.
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

  // The file this copy can run, by the one naming rule (releaseFileName).
  const url = (name) => {
    const asset = name && assets.find((candidate) => candidate && candidate.name === name);
    return asset && isReleaseAssetUrl(asset.browser_download_url) ? asset.browser_download_url : null;
  };
  const dmgUrl = platform === "darwin" ? url(releaseFileName("mac", arch, version)) : null;
  // The portable zip, for a copy Setup did not install (windowsUpdateMethod).
  const zipUrl = platform === "win32" ? url(releaseFileName("windows-portable", arch, version)) : null;
  const appImageUrl = platform === "linux" ? url(releaseFileName("linux", arch, version)) : null;

  const feedUrl =
    platform === "win32" && names.has("latest.yml")
      ? `https://github.com/${REPOSITORY}/releases/download/${encodeURIComponent(tag)}`
      : null;

  return { tag, version, dmgUrl, zipUrl, appImageUrl, feedUrl, pageUrl: RELEASES_PAGE_URL };
}

/**
 * What a release file is called: who it is for and what it is, in words
 * people read, "Axcess-0.61-Windows-Installer.exe", not CPU codes (arm64,
 * x64, x86_64). The processor is named only where it decides whether the
 * file runs, the Mac's (Apple Silicon or Intel). Windows and Linux have one
 * build each, for 64-bit Intel and AMD processors, which the download page
 * states; a processor with no build has no name, so a copy on it is never
 * offered a file it cannot run. The site matches the part after the version
 * (data-release-file in site/build.py).
 *
 * `kind` is "mac", "windows-installer", "windows-portable" or "linux".
 * Hyphens rather than spaces: GitHub rewrites spaces in file names.
 */
function releaseFileName(kind, arch, version = null) {
  const prefix = version ? `Axcess-${version}` : "Axcess";
  if (kind === "mac") {
    const processor = { arm64: "Apple-Silicon", x64: "Intel" }[arch];
    return processor ? `${prefix}-Mac-${processor}.dmg` : null;
  }
  if (arch !== "x64") return null;
  return {
    "windows-installer": `${prefix}-Windows-Installer.exe`,
    "windows-portable": `${prefix}-Windows-Portable.zip`,
    linux: `${prefix}-Linux.AppImage`,
  }[kind] ?? null;
}

/** True when `release` (from describeRelease) is strictly newer than the running app. */
function isNewerRelease(release, currentVersion) {
  if (!release) return false;
  return compareVersions(release.version, currentVersion) === 1;
}

/**
 * Versions are semver, MAJOR.MINOR.PATCH, and read as they are: "0.2.3".
 * The team chooses the release line, MAJOR.MINOR ("0.2", config.releaseLine
 * in desktop/package.json); every release published from main counts up
 * the last part (nextReleaseVersion). Moving to 0.3.0 or 1.0.0 is a
 * deliberate one-line change there, never the side effect of a merge, and
 * each line names an audience: 0.1 developers, 0.2 the U-M ITS
 * accessibility team, 0.3 a wider pilot, 1.0 university-wide
 * (docs/internal/releases.md). The
 * scheme before this one (0.60, 0.61 ...) added 0.01 per merge, a build
 * counter that looked like a version and would have reached 1.00 by itself.
 */
function displayVersion(version) {
  const parts = parseVersion(version);
  return parts ? parts.join(".") : String(version);
}

/** The version as package.json carries it: the same three parts, checked. */
function packageVersion(version) {
  const parts = parseVersion(version);
  if (!parts || parts.length !== 3) throw new Error(`Not a three-part version: ${version}`);
  return parts.join(".");
}

/**
 * The version of the next release on `line` ("0.2"), given the release
 * tags that exist: one step after the highest "desktop-v0.2.N"
 * ("desktop-v0.2.3" -> "0.2.4"), or "0.2.0" when the line has none yet.
 * Tags of other lines, and of the schemes before (desktop-v0.63,
 * desktop-v0.1.33), do not count.
 */
function nextReleaseVersion(tags, line) {
  if (!/^\d+\.\d+$/.test(String(line))) throw new Error(`Not a release line (MAJOR.MINOR): ${line}`);
  const pattern = new RegExp(`^desktop-v${line.replace(".", "\\.")}\\.(\\d+)$`);
  let highest = null;
  for (const tag of tags) {
    const match = pattern.exec(String(tag).trim());
    if (match && (highest === null || Number(match[1]) > highest)) highest = Number(match[1]);
  }
  return `${line}.${highest === null ? 0 : highest + 1}`;
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
  releaseFileName,
  releaseVersion,
};
