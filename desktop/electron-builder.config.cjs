const path = require("node:path");
const packageJson = require("./package.json");
const { appImageName, setupExeName } = require("./scripts/release-names.cjs");

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
  toolsets: {
    // The static AppImage runtime, not the default legacy one (0.0.0): it
    // needs no libfuse2, which current Fedora and Ubuntu leave out, and its
    // AppRun turns Chromium's sandbox off only where the kernel blocks the
    // user namespaces it needs (Ubuntu 23.10 and later), after probing with
    // `unshare -Ur true`. The legacy toolset's desktop entry always passed
    // --no-sandbox. Chosen with the developer: sandboxed wherever it works.
    appimage: "1.0.3",
  },
  linux: {
    target: [{ target: "AppImage", arch: ["x64"] }],
    icon: path.join("assets", "axcess.png"),
    // Forge's executable name; electron-builder would guess the package name.
    executableName: "Axcess",
    category: "Development",
    // The desktop entry's Comment, shown in app menus; the default would
    // be package.json's "Local-first accessibility auditing workbench".
    description: "Check websites for accessibility problems, on your computer",
  },
  appImage: {
    artifactName: appImageName(packageJson.version),
  },
  win: {
    target: [{ target: "nsis", arch: ["x64"] }],
    icon: path.join("assets", "axcess.ico"),
  },
  nsis: {
    oneClick: false,
    // Per-user by default, like the Squirrel install it replaces, so no
    // administrator is needed; the wizard also offers every account.
    perMachine: false,
    // Off: not because the folder is fixed, but because NSIS's own folder
    // page left its field without an accessible name (Axe.Windows, SC
    // 4.1.2). installer/installer.nsh adds a folder screen in its place,
    // with a labelled field and Browse (customPageAfterChangeDir).
    allowToChangeInstallationDirectory: false,
    artifactName: setupExeName(packageJson.version),
    shortcutName: "Axcess",
    uninstallDisplayName: "Axcess",
    // Scans live in %APPDATA%\Axcess\data, outside the install folder.
    // Uninstalling or reinstalling the app keeps them.
    deleteAppDataOnUninstall: false,
    // Every word the wizard, its messages and the uninstaller show, in
    // plain language (docs/plain-language.md). See the file for why.
    include: path.join("installer", "installer.nsh"),
    // English only, like the app. electron-builder's default builds 26
    // languages and Windows picks one by its display language, but only the
    // NSIS page text is translated: on a German Windows the wizard mixed
    // German with electron-builder's own English, and none of the wording
    // in installer.nsh reached it.
    multiLanguageInstaller: false,
  },
};
