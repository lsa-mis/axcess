/**
 * The file names a desktop release publishes, from the packaged version
 * (0.61.0 reads as 0.61): make-macos-dmg.cjs names the DMG,
 * electron-builder.config.cjs the Windows installer and the AppImage, and
 * make-windows-installer.cjs the portable zip, all with these. The publish
 * job in desktop-build.yml then requires
 * `Axcess-$VERSION-Mac-Apple-Silicon.dmg`, `Axcess-$VERSION-Windows-Installer.exe`,
 * `Axcess-$VERSION-Windows-Portable.zip` and `Axcess-$VERSION-Linux.AppImage`,
 * where $VERSION is the two-part version the version job picked. CI's
 * release dry run runs this with `--expect <version>` to check they agree
 * before anything merges.
 *
 *   node scripts/release-names.cjs                 # print the names
 *   node scripts/release-names.cjs --expect 0.61   # exit 1 if they differ
 */
const fs = require("node:fs");
const path = require("node:path");
const { displayVersion, releaseFileName } = require("../src/updates.cjs");

// The names come from releaseFileName in src/updates.cjs, the rule the
// installed app also uses to find its next file, so they cannot drift.
function dmgName(packageVersion, arch) {
  return releaseFileName("mac", arch, displayVersion(packageVersion));
}

function setupExeName(packageVersion) {
  return releaseFileName("windows-installer", "x64", displayVersion(packageVersion));
}

/** The Windows zip that runs without installing (portable mode). */
function portableZipName(packageVersion, arch = "x64") {
  return releaseFileName("windows-portable", arch, displayVersion(packageVersion));
}

/** The Linux AppImage. */
function appImageName(packageVersion, arch = "x64") {
  return releaseFileName("linux", arch, displayVersion(packageVersion));
}

module.exports = { appImageName, dmgName, portableZipName, setupExeName };

if (require.main === module) {
  const args = process.argv.slice(2);
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "package.json"), "utf8"));
  const names = [
    dmgName(pkg.version, "arm64"),
    setupExeName(pkg.version),
    portableZipName(pkg.version),
    appImageName(pkg.version),
  ];
  const at = args.indexOf("--expect");
  if (at === -1) {
    console.log(names.join("\n"));
  } else {
    const version = args[at + 1];
    // The publish job's own patterns, in desktop-build.yml.
    const wanted = [
      `Axcess-${version}-Mac-Apple-Silicon.dmg`,
      `Axcess-${version}-Windows-Installer.exe`,
      `Axcess-${version}-Windows-Portable.zip`,
      `Axcess-${version}-Linux.AppImage`,
    ];
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
