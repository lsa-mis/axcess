/**
 * The installer names a desktop release publishes.
 *
 * forge.config.cjs names the Windows Setup.exe and make-macos-dmg.cjs the
 * DMG with these, from the packaged version (0.61.0 reads as 0.61). The
 * publish job in desktop-build.yml then requires `Axcess-$VERSION-arm64.dmg`
 * and `Axcess-$VERSION-Setup.exe`, where $VERSION is the two-part version
 * the version job picked. CI's release dry run runs this with
 * `--expect <version>` to check the two agree before anything merges.
 *
 *   node scripts/release-names.cjs                 # print the names
 *   node scripts/release-names.cjs --expect 0.61   # exit 1 if they differ
 */
const fs = require("node:fs");
const path = require("node:path");
const { displayVersion } = require("../src/updates.cjs");

function dmgName(packageVersion, arch) {
  return `Axcess-${displayVersion(packageVersion)}-${arch}.dmg`;
}

function setupExeName(packageVersion) {
  return `Axcess-${displayVersion(packageVersion)}-Setup.exe`;
}

module.exports = { dmgName, setupExeName };

if (require.main === module) {
  const args = process.argv.slice(2);
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8"));
  const names = [dmgName(pkg.version, "arm64"), setupExeName(pkg.version)];
  const at = args.indexOf("--expect");
  if (at === -1) {
    console.log(names.join("\n"));
  } else {
    const version = args[at + 1];
    // The publish job's own patterns, in desktop-build.yml.
    const wanted = [`Axcess-${version}-arm64.dmg`, `Axcess-${version}-Setup.exe`];
    const wrong = wanted.filter((name, index) => name !== names[index]);
    if (wrong.length) {
      console.error(
        `The build would name its installers ${names.join(", ")}, ` +
          `but the publish job looks for ${wanted.join(", ")}.`,
      );
      process.exit(1);
    }
    console.log(`Installer names match release ${version}: ${names.join(", ")}`);
  }
}
