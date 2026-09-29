/**
 * Build the Linux AppImage from the app Forge already packaged
 * (`npm run package` writes out/Axcess-linux-<arch>). electron-builder only
 * wraps that folder, as it does for the Windows installer; see
 * electron-builder.config.cjs for the AppImage toolset and why. Writes
 * out/make/appimage/Axcess-<version>-x86_64.AppImage.
 *
 * Runs on Linux. The release builds it on the oldest Ubuntu it supports:
 * the AppImage runs on distros with that glibc or newer.
 */
const fs = require("node:fs");
const path = require("node:path");

if (process.platform !== "linux") {
  console.log("The AppImage is built on Linux.");
  process.exit(0);
}

const { Platform, build } = require("electron-builder");
const config = require("../electron-builder.config.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const arch = process.env.AXCESS_LINUX_ARCH || process.arch;
const prepackaged = path.join(desktopRoot, "out", `Axcess-linux-${arch}`);
if (!fs.existsSync(path.join(prepackaged, "Axcess"))) {
  throw new Error(`Packaged application is missing: ${prepackaged}. Run \`npm run package\` first.`);
}

build({
  projectDir: desktopRoot,
  targets: Platform.LINUX.createTarget("AppImage", arch),
  prepackaged,
  config: {
    ...config,
    // No update feed: a Linux copy is offered the new AppImage to download.
    publish: null,
    directories: { output: path.join("out", "make", "appimage") },
  },
  publish: "never",
}).then(
  (artifacts) => console.log(`AppImage built:\n${artifacts.join("\n")}`),
  (error) => {
    console.error(error);
    process.exit(1);
  },
);
