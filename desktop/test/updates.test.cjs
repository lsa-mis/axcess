const test = require("node:test");
const assert = require("node:assert/strict");
const {
  RELEASES_API_URL,
  compareVersions,
  describeRelease,
  displayVersion,
  isNewerRelease,
  isReleaseAssetUrl,
  nextReleaseVersion,
  packageVersion,
  parseVersion,
  releaseVersion,
} = require("../src/updates.cjs");

const DOWNLOAD = "https://github.com/lsa-mis/axcess/releases/download/desktop-v0.1.57";

function release(overrides = {}) {
  return {
    tag_name: "desktop-v0.1.57",
    draft: false,
    prerelease: false,
    assets: [
      { name: "Axcess-0.1.57-Mac-Apple-Silicon.dmg", browser_download_url: `${DOWNLOAD}/Axcess-0.1.57-Mac-Apple-Silicon.dmg` },
      { name: "Axcess-darwin-arm64-0.1.57.zip", browser_download_url: `${DOWNLOAD}/Axcess-darwin-arm64-0.1.57.zip` },
      { name: "Axcess-0.1.57-Windows-Installer.exe", browser_download_url: `${DOWNLOAD}/Axcess-0.1.57-Windows-Installer.exe` },
      { name: "Axcess-0.1.57-Linux.AppImage", browser_download_url: `${DOWNLOAD}/Axcess-0.1.57-Linux.AppImage` },
      {
        name: "Axcess-0.1.57-Windows-Portable.zip",
        browser_download_url: `${DOWNLOAD}/Axcess-0.1.57-Windows-Portable.zip`,
      },
      { name: "Axcess-0.1.57-Windows-Installer.exe.blockmap", browser_download_url: `${DOWNLOAD}/Axcess-0.1.57-Windows-Installer.exe.blockmap` },
      { name: "latest.yml", browser_download_url: `${DOWNLOAD}/latest.yml` },
    ],
    ...overrides,
  };
}

test("versions parse as plain dotted numbers only", () => {
  assert.deepEqual(parseVersion("0.1.57"), [0, 1, 57]);
  assert.deepEqual(parseVersion("v0.1.57"), [0, 1, 57]);
  assert.equal(parseVersion("0.1.57-beta"), null);
  assert.equal(parseVersion(""), null);
  assert.equal(parseVersion(undefined), null);
});

test("version comparison is numeric, not lexical", () => {
  assert.equal(compareVersions("0.1.57", "0.1.0"), 1);
  assert.equal(compareVersions("0.1.9", "0.1.10"), -1);
  assert.equal(compareVersions("0.1", "0.1.0"), 0);
  assert.equal(compareVersions("1.0.0", "0.9.999"), 1);
  assert.equal(compareVersions("0.1.0", "0.1.0"), 0);
  assert.equal(compareVersions("junk", "0.1.0"), null);
});

test("release tags map to versions", () => {
  assert.equal(releaseVersion("desktop-v0.1.57"), "0.1.57");
  assert.equal(releaseVersion("v0.1.57"), "0.1.57");
  assert.equal(releaseVersion("site-2026-09"), null);
  assert.equal(releaseVersion(null), null);
});

test("only HTTPS asset downloads from this repository may be opened", () => {
  assert.equal(isReleaseAssetUrl(`${DOWNLOAD}/Axcess-0.1.57-Mac-Apple-Silicon.dmg`), true);
  assert.equal(isReleaseAssetUrl("http://github.com/lsa-mis/axcess/releases/download/x/y.dmg"), false);
  assert.equal(isReleaseAssetUrl("https://github.com/lsa-mis/axcess/releases/latest"), false);
  assert.equal(isReleaseAssetUrl("https://github.com/lsa-mis/axcess/releases/download/"), false);
  assert.equal(isReleaseAssetUrl("https://github.com/other/repo/releases/download/v1/a.dmg"), false);
  assert.equal(isReleaseAssetUrl("https://github.com.evil.example/lsa-mis/axcess/releases/download/v1/a.dmg"), false);
  assert.equal(isReleaseAssetUrl("https://evil.example/?u=https://github.com/lsa-mis/axcess/releases/download/v1/a.dmg"), false);
  assert.equal(isReleaseAssetUrl("not a url"), false);
});

test("macOS releases resolve to the DMG for the running architecture", () => {
  const described = describeRelease(release(), { platform: "darwin", arch: "arm64" });
  assert.equal(described.version, "0.1.57");
  assert.equal(described.tag, "desktop-v0.1.57");
  assert.equal(described.dmgUrl, `${DOWNLOAD}/Axcess-0.1.57-Mac-Apple-Silicon.dmg`);
  assert.equal(described.feedUrl, null);

  const intel = describeRelease(release(), { platform: "darwin", arch: "x64" });
  assert.equal(intel.dmgUrl, null, "no Intel DMG is published, so nothing to open");
});

test("a DMG hosted somewhere other than the release is ignored", () => {
  const tampered = release({
    assets: [{ name: "Axcess-0.1.57-Mac-Apple-Silicon.dmg", browser_download_url: "https://evil.example/a.dmg" }],
  });
  assert.equal(describeRelease(tampered, { platform: "darwin", arch: "arm64" }).dmgUrl, null);
});

test("Windows releases resolve to the electron-updater feed directory", () => {
  const described = describeRelease(release(), { platform: "win32", arch: "x64" });
  assert.equal(described.feedUrl, DOWNLOAD);
  assert.equal(described.dmgUrl, null);

  const withoutFeed = release({ assets: release().assets.filter((asset) => asset.name !== "latest.yml") });
  assert.equal(describeRelease(withoutFeed, { platform: "win32", arch: "x64" }).feedUrl, null);
});

test("drafts, prereleases, and foreign tags are not update candidates", () => {
  const options = { platform: "darwin", arch: "arm64" };
  assert.equal(describeRelease(release({ draft: true }), options), null);
  assert.equal(describeRelease(release({ prerelease: true }), options), null);
  assert.equal(describeRelease(release({ tag_name: "site-2026-09" }), options), null);
  assert.equal(describeRelease(null, options), null);
  assert.equal(describeRelease("nope", options), null);
});

test("an update is only offered for a strictly newer release", () => {
  const described = describeRelease(release(), { platform: "darwin", arch: "arm64" });
  assert.equal(isNewerRelease(described, "0.1.0"), true, "local builds are 0.1.0");
  assert.equal(isNewerRelease(described, "0.1.56"), true);
  assert.equal(isNewerRelease(described, "0.1.57"), false);
  assert.equal(isNewerRelease(described, "0.1.58"), false);
  assert.equal(isNewerRelease(null, "0.1.0"), false);
});

test("the release lookup targets this repository over HTTPS", () => {
  assert.equal(RELEASES_API_URL, "https://api.github.com/repos/lsa-mis/axcess/releases/latest");
});

test("versions are three-part semver and read as they are", () => {
  assert.equal(displayVersion("0.2.0"), "0.2.0");
  assert.equal(displayVersion("0.2.13"), "0.2.13");
  assert.equal(displayVersion("1.0.0"), "1.0.0");
});

test("the package carries the same three-part version", () => {
  assert.equal(packageVersion("0.2.4"), "0.2.4");
  assert.throws(() => packageVersion("0.61"), /three-part/);
});

test("each release counts up the last part of the chosen line", () => {
  // No release on the line yet: it starts at .0, whatever older tags exist.
  assert.equal(nextReleaseVersion([], "0.2"), "0.2.0");
  assert.equal(nextReleaseVersion(["desktop-v0.63", "desktop-v0.1.34"], "0.2"), "0.2.0");
  assert.equal(nextReleaseVersion(["desktop-v0.2.0"], "0.2"), "0.2.1");
  // Numbers, not text: 0.2.10 is after 0.2.9.
  assert.equal(nextReleaseVersion(["desktop-v0.2.9", "desktop-v0.2.10", "desktop-v0.2.2"], "0.2"), "0.2.11");
  // Another line's tags do not count; moving on is a deliberate change.
  assert.equal(nextReleaseVersion(["desktop-v0.2.7", "desktop-v0.3.1"], "0.3"), "0.3.2");
  assert.equal(nextReleaseVersion(["desktop-v0.2.7", "v0.2.9", "desktop-v0.22.1"], "0.2"), "0.2.8");
  assert.throws(() => nextReleaseVersion([], "0.2.0"), /release line/);
});

test("the chosen line is set in one place, package.json", () => {
  const pkg = require("../package.json");
  assert.match(pkg.config.releaseLine, /^\d+\.\d+$/);
  assert.ok(pkg.version.startsWith(`${pkg.config.releaseLine}.`));
});

test("versions compare as numbers across the schemes", () => {
  assert.equal(releaseVersion("desktop-v0.2.3"), "0.2.3");
  assert.equal(compareVersions("0.2.10", "0.2.9"), 1);
  assert.equal(compareVersions("0.2.0", "0.1.34"), 1);
  // Copies of the old previews (0.60 to 0.63) are not offered 0.2.x.
  assert.equal(compareVersions("0.2.0", "0.63.0"), -1);
});

test("a release with only the old Squirrel feed is not a Windows update", () => {
  const squirrelOnly = release({
    assets: [
      ...release().assets.filter((asset) => asset.name !== "latest.yml"),
      { name: "RELEASES", browser_download_url: `${DOWNLOAD}/RELEASES` },
    ],
  });
  assert.equal(describeRelease(squirrelOnly, { platform: "win32", arch: "x64" }).feedUrl, null);
});

test("Windows releases name the portable zip for a copy Setup did not install", () => {
  const described = describeRelease(release(), { platform: "win32", arch: "x64" });
  assert.equal(described.zipUrl, `${DOWNLOAD}/Axcess-0.1.57-Windows-Portable.zip`);
  assert.equal(describeRelease(release(), { platform: "win32", arch: "arm64" }).zipUrl, null);
  assert.equal(describeRelease(release(), { platform: "darwin", arch: "arm64" }).zipUrl, null);
  const elsewhere = release({
    assets: [{ name: "Axcess-0.1.57-Windows-Portable.zip", browser_download_url: "https://evil.example/a.zip" }],
  });
  assert.equal(describeRelease(elsewhere, { platform: "win32", arch: "x64" }).zipUrl, null);
});

test("Linux releases resolve to the AppImage for the running architecture", () => {
  const described = describeRelease(release(), { platform: "linux", arch: "x64" });
  assert.equal(described.appImageUrl, `${DOWNLOAD}/Axcess-0.1.57-Linux.AppImage`);
  assert.equal(described.zipUrl, null);
  assert.equal(describeRelease(release(), { platform: "linux", arch: "arm64" }).appImageUrl, null);
  assert.equal(describeRelease(release(), { platform: "win32", arch: "x64" }).appImageUrl, null);
});

