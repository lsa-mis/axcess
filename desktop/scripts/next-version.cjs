/**
 * Print the version the next desktop release takes, for the build workflow.
 *
 * Reads release tag names on stdin, one per line (`git ls-remote --tags`
 * output works too), and the release line the team chose from
 * desktop/package.json (config.releaseLine, "0.2"), and writes GitHub
 * Actions output lines:
 *
 *   version=0.2.4
 *   package_version=0.2.4
 *
 * The line says who a release is for: 0.1 developers (branch builds only),
 * 0.2 the U-M ITS accessibility team, 0.3 a wider pilot, 1.0 university-wide
 * (docs/internal/releases.md, "Version numbers and tags"). Changing it is a
 * decision about the audience, made by hand.
 *
 * The two are the same now that versions are three-part semver; both stay
 * so the workflow's steps keep their inputs. `version` names the tag
 * (`desktop-v0.2.4`), the release title and the files.
 */
const packageJson = require("../package.json");
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
  const version = nextReleaseVersion(tags, packageJson.config.releaseLine);
  process.stdout.write(`version=${version}\npackage_version=${packageVersion(version)}\n`);
});
