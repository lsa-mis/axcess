/**
 * Build the Windows NSIS installer from the app Forge already packaged
 * (`npm run package` writes out/Axcess-win32-<arch>). electron-builder only
 * wraps that folder; see electron-builder.config.cjs for why. Writes
 * out/make/nsis/Axcess-<version>-Setup.exe, its .blockmap, and latest.yml.
 *
 * Runs on Windows. With AXCESS_CROSS_BUILD_WINDOWS=1 it also runs on Linux
 * or macOS, which is enough to check the installer is assembled; the
 * packaged app itself can only be verified on Windows.
 */
const fs = require("node:fs");
const path = require("node:path");

if (process.platform !== "win32" && process.env.AXCESS_CROSS_BUILD_WINDOWS !== "1") {
  console.log("The Windows installer is built on Windows.");
  process.exit(0);
}

const { Platform, build } = require("electron-builder");
const config = require("../electron-builder.config.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const arch = process.env.AXCESS_WINDOWS_ARCH || (process.platform === "win32" ? process.arch : "x64");
const prepackaged = path.join(desktopRoot, "out", `Axcess-win32-${arch}`);
if (!fs.existsSync(path.join(prepackaged, "Axcess.exe"))) {
  throw new Error(`Packaged application is missing: ${prepackaged}. Run \`npm run package\` first.`);
}

build({
  projectDir: desktopRoot,
  targets: Platform.WINDOWS.createTarget("nsis", arch),
  prepackaged,
  config,
  publish: "never",
}).then(
  (artifacts) => console.log(`Windows installer built:\n${artifacts.join("\n")}`),
  (error) => {
    console.error(error);
    process.exit(1);
  },
);
