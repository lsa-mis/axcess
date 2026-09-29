/**
 * Print the version the next desktop release takes, for the build workflow.
 *
 * Reads release tag names on stdin, one per line (`git ls-remote --tags`
 * output works too), and writes GitHub Actions output lines:
 *
 *   version=0.61
 *   package_version=0.61.0
 *
 * `version` is what people see: the tag (`desktop-v0.61`), the release
 * title and the installer names. `package_version` is the semver npm and
 * electron-updater need in package.json.
 */
const { nextReleaseVersion, packageVersion } = require("../src/updates.cjs");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", () => {
  const tags = input
    .split("\n")
    .map((line) => line.trim().split(/\s+/).pop() || "")
    .map((ref) => ref.replace(/^refs\/tags\//, ""))
    .filter(Boolean);
  const version = nextReleaseVersion(tags);
  process.stdout.write(`version=${version}\npackage_version=${packageVersion(version)}\n`);
});
