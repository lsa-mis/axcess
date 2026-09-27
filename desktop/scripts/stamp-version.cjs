/**
 * Stamp desktop/package.json with a release's version and commit, as a
 * release build does before packaging.
 *
 *   node scripts/stamp-version.cjs <semver> [commit]
 *
 * Sets `version` (and the lock file's, as `npm version` would) and, when a
 * commit is given, `config.buildCommit`. It replaces `npm version`, which
 * stops with "Version not changed" when asked to set the version a package
 * already has: the first two-part release, 0.60, is exactly that. The
 * release workflow and CI's release dry run both call this, so a pull
 * request runs the same stamp a release does.
 */
const fs = require("node:fs");
const path = require("node:path");

const SEMVER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

function update(file, change) {
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  change(data);
  fs.writeFileSync(file, `${JSON.stringify(data, null, 2)}\n`);
}

/** Stamp the package in `root` (the desktop folder); throws on a bad version. */
function stamp(root, version, commit) {
  if (!SEMVER.test(version || "")) throw new Error(`Not a three-part package version: ${version}`);
  update(path.join(root, "package.json"), (pkg) => {
    pkg.version = version;
    if (commit) pkg.config = { ...pkg.config, buildCommit: commit };
  });
  const lock = path.join(root, "package-lock.json");
  if (fs.existsSync(lock)) {
    update(lock, (data) => {
      data.version = version;
      if (data.packages && data.packages[""]) data.packages[""].version = version;
    });
  }
}

module.exports = { stamp };

if (require.main === module) {
  const [version, commit] = process.argv.slice(2);
  try {
    stamp(path.join(__dirname, ".."), version, commit);
  } catch (error) {
    console.error(error.message);
    process.exit(1);
  }
  console.log(`Stamped desktop ${version}${commit ? ` (${commit.slice(0, 7)})` : ""}`);
}
