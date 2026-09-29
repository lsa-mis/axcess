const path = require("node:path");
const packageJson = require("./package.json");
const { setupExeName } = require("./scripts/release-names.cjs");

/**
 * The Windows installer. electron-builder does not package the app: Forge
 * already did (fuses, asar integrity, bundled resources), and
 * scripts/make-windows-installer.cjs hands electron-builder that folder with
 * `prepackaged`, so Axcess.exe and app.asar reach the installer unchanged.
 *
 * NSIS replaced Squirrel.Windows, whose installer showed only an animation:
 * no text for a screen reader, no install location, no choice. The assisted
 * NSIS installer is a standard Windows wizard: it asks who to install for,
 * shows and lets people change the folder, and says when it is done. MSI
 * (Forge's maker-wix) was the other option, but an MSI cannot update itself
 * in place, and a build ships on every merge to main; NSIS updates in place
 * through electron-updater (see offerWindowsUpdate in src/main.cjs). IT can
 * still deploy it silently with `/S` (and `/allusers` for every account).
 */
module.exports = {
  appId: "edu.umich.axcess",
  productName: "Axcess",
  directories: { output: path.join("out", "make", "nsis") },
  // Only so electron-builder writes latest.yml, the update feed file the
  // publish job uploads. The build never publishes (`publish: "never"` in
  // make-windows-installer.cjs); desktop-build.yml uploads the release.
  publish: [{ provider: "github", owner: "lsa-mis", repo: "axcess" }],
  win: {
    target: [{ target: "nsis", arch: ["x64"] }],
    icon: path.join("assets", "axcess.ico"),
  },
  nsis: {
    oneClick: false,
    // Per-user by default, like the Squirrel install it replaces, so no
    // administrator is needed; the wizard also offers every account.
    perMachine: false,
    allowToChangeInstallationDirectory: true,
    artifactName: setupExeName(packageJson.version),
    shortcutName: "Axcess",
    uninstallDisplayName: "Axcess",
    // Scans live in %APPDATA%\Axcess\data, outside the install folder.
    // Uninstalling or reinstalling the app keeps them.
    deleteAppDataOnUninstall: false,
  },
};
