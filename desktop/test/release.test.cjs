const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { appImageName, dmgName, portableZipName, setupExeName } = require("../scripts/release-names.cjs");
const { stamp } = require("../scripts/stamp-version.cjs");

test("release files are named in plain words, with the version people see", () => {
  assert.equal(dmgName("0.61.0", "arm64"), "Axcess-0.61-Mac-Apple-Silicon.dmg");
  assert.equal(dmgName("0.61.0", "x64"), "Axcess-0.61-Mac-Intel.dmg");
  assert.equal(setupExeName("0.61.0"), "Axcess-0.61-Windows-Installer.exe");
  assert.equal(setupExeName("1.0.0"), "Axcess-1.00-Windows-Installer.exe");
  assert.equal(portableZipName("0.61.0"), "Axcess-0.61-Windows-Portable.zip");
  assert.equal(appImageName("0.61.0"), "Axcess-0.61-Linux.AppImage");
  // No CPU codes in any of them.
  for (const name of [dmgName("0.61.0", "arm64"), setupExeName("0.61.0"), portableZipName("0.61.0"), appImageName("0.61.0")]) {
    assert.doesNotMatch(name, /arm64|x64|x86_64|aarch64|darwin|win32/);
  }
  // A processor with no build has no file.
  assert.equal(portableZipName("0.61.0", "arm64"), null);
  assert.equal(appImageName("0.61.0", "arm64"), null);
});

function packageFolder(version) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "axcess-stamp-"));
  fs.writeFileSync(path.join(root, "package.json"), `${JSON.stringify({ name: "axcess", version }, null, 2)}\n`);
  fs.writeFileSync(
    path.join(root, "package-lock.json"),
    `${JSON.stringify({ name: "axcess", version, packages: { "": { version } } }, null, 2)}\n`,
  );
  return root;
}

test("stamping the version a package already has succeeds", () => {
  // npm version stopped here ("Version not changed") on the first 0.60 build.
  const root = packageFolder("0.60.0");
  stamp(root, "0.60.0", "abcdef1234567");
  const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
  assert.equal(pkg.version, "0.60.0");
  assert.equal(pkg.config.buildCommit, "abcdef1234567");
});

test("stamping a new version updates the package and its lock file", () => {
  const root = packageFolder("0.60.0");
  stamp(root, "0.61.0");
  const lock = JSON.parse(fs.readFileSync(path.join(root, "package-lock.json"), "utf8"));
  assert.equal(JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8")).version, "0.61.0");
  assert.equal(lock.version, "0.61.0");
  assert.equal(lock.packages[""].version, "0.61.0");
});

test("a two-part or malformed version is refused", () => {
  const root = packageFolder("0.60.0");
  assert.throws(() => stamp(root, "0.61"), /three-part/);
  assert.throws(() => stamp(root, "0.061.0"), /three-part/);
});
