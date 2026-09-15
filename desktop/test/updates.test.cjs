const test = require("node:test");
const assert = require("node:assert/strict");
const {
  RELEASES_API_URL,
  compareVersions,
  describeRelease,
  isNewerRelease,
  isReleaseAssetUrl,
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
      { name: "Axcess-0.1.57-arm64.dmg", browser_download_url: `${DOWNLOAD}/Axcess-0.1.57-arm64.dmg` },
      { name: "Axcess-darwin-arm64-0.1.57.zip", browser_download_url: `${DOWNLOAD}/Axcess-darwin-arm64-0.1.57.zip` },
      { name: "Axcess-0.1.57-Setup.exe", browser_download_url: `${DOWNLOAD}/Axcess-0.1.57-Setup.exe` },
      { name: "RELEASES", browser_download_url: `${DOWNLOAD}/RELEASES` },
      { name: "Axcess-0.1.57-full.nupkg", browser_download_url: `${DOWNLOAD}/Axcess-0.1.57-full.nupkg` },
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
  assert.equal(isReleaseAssetUrl(`${DOWNLOAD}/Axcess-0.1.57-arm64.dmg`), true);
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
  assert.equal(described.dmgUrl, `${DOWNLOAD}/Axcess-0.1.57-arm64.dmg`);
  assert.equal(described.feedUrl, null);

  const intel = describeRelease(release(), { platform: "darwin", arch: "x64" });
  assert.equal(intel.dmgUrl, null, "no Intel DMG is published, so nothing to open");
});

test("a DMG hosted somewhere other than the release is ignored", () => {
  const tampered = release({
    assets: [{ name: "Axcess-0.1.57-arm64.dmg", browser_download_url: "https://evil.example/a.dmg" }],
  });
  assert.equal(describeRelease(tampered, { platform: "darwin", arch: "arm64" }).dmgUrl, null);
});

test("Windows releases resolve to the Squirrel feed directory", () => {
  const described = describeRelease(release(), { platform: "win32", arch: "x64" });
  assert.equal(described.feedUrl, DOWNLOAD);
  assert.equal(described.dmgUrl, null);

  const withoutFeed = release({ assets: release().assets.filter((asset) => asset.name !== "RELEASES") });
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
