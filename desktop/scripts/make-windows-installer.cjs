/**
 * Build the Windows installer and the portable zip from the app Forge
 * already packaged (`npm run package` writes out/Axcess-win32-<arch>).
 * electron-builder only wraps that folder; see electron-builder.config.cjs
 * for why. Writes out/make/nsis/Axcess-<version>-Setup.exe, its .blockmap
 * and latest.yml, then out/make/zip/Axcess-<version>-Windows-<arch>-portable.zip:
 * the same app with an "Axcess data" folder beside Axcess.exe, which puts it
 * in portable mode (portableDataDir in src/runtime.cjs).
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
const packageJson = require("../package.json");
const { PORTABLE_DATA_FOLDER } = require("../src/runtime.cjs");
const { portableZipName } = require("./release-names.cjs");

const desktopRoot = path.resolve(__dirname, "..");
const arch = process.env.AXCESS_WINDOWS_ARCH || (process.platform === "win32" ? process.arch : "x64");
const prepackaged = path.join(desktopRoot, "out", `Axcess-win32-${arch}`);
if (!fs.existsSync(path.join(prepackaged, "Axcess.exe"))) {
  throw new Error(`Packaged application is missing: ${prepackaged}. Run \`npm run package\` first.`);
}

// Shown to anyone who opens the data folder of the zip.
const PORTABLE_README = `Axcess keeps everything here: your reports, settings and logs.

Keep this folder next to Axcess.exe. To move Axcess, move the whole folder
that holds Axcess.exe and this one. To update, unzip the new version and move
this folder into it, replacing the one there.

Do not put this folder on a network drive: the reports database needs a
local drive. A USB drive works; do not unplug it while Axcess is open.
Reports can hold screenshots of the pages you scanned, so keep the folder
as safe as those pages.
`;

// Windows Explorer's "Extract all" fails on paths over 260 characters. A
// path inside the zip longer than this leaves under 80 for the folder it
// is unzipped into, such as C:\Users\<name>\Downloads\Axcess-0.61-...\.
const LONGEST_PATH_IN_ZIP = 180;

function longestPath(folder, prefix = "") {
  let longest = "";
  for (const entry of fs.readdirSync(folder, { withFileTypes: true })) {
    const relative = prefix ? `${prefix}\\${entry.name}` : entry.name;
    const candidate = entry.isDirectory() ? longestPath(path.join(folder, entry.name), relative) : relative;
    if (candidate.length > longest.length) longest = candidate;
  }
  return longest;
}

async function main() {
  const longest = longestPath(prepackaged);
  if (longest.length > LONGEST_PATH_IN_ZIP) {
    throw new Error(`A path in the app is ${longest.length} characters, over ${LONGEST_PATH_IN_ZIP}: ${longest}`);
  }
  console.log(`Longest path in the app: ${longest.length} characters (${longest}).`);
  const installer = await build({
    projectDir: desktopRoot,
    targets: Platform.WINDOWS.createTarget("nsis", arch),
    prepackaged,
    config,
    publish: "never",
  });
  // The zip is the same folder with the data folder added; it is removed
  // again so the installer build and verify-packaged see the app as is.
  const dataFolder = path.join(prepackaged, PORTABLE_DATA_FOLDER);
  fs.mkdirSync(dataFolder, { recursive: true });
  fs.writeFileSync(path.join(dataFolder, "About this folder.txt"), PORTABLE_README.replace(/\n/g, "\r\n"));
  try {
    const zip = await build({
      projectDir: desktopRoot,
      targets: Platform.WINDOWS.createTarget("zip", arch),
      prepackaged,
      config: {
        ...config,
        // No update feed from the zip build: latest.yml is the installer's.
        publish: null,
        directories: { output: path.join("out", "make", "zip") },
        win: { ...config.win, artifactName: portableZipName(packageJson.version, arch) },
      },
      publish: "never",
    });
    console.log(`Windows installer and portable zip built:\n${[...installer, ...zip].join("\n")}`);
  } finally {
    fs.rmSync(dataFolder, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
