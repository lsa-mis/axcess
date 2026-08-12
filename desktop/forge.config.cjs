const fs = require("node:fs");
const path = require("node:path");
const { FuseV1Options, FuseVersion } = require("@electron/fuses");

const resources = ["backend-dist", "playwright-browsers"]
  .map((name) => path.join(__dirname, name))
  .filter((candidate) => fs.existsSync(candidate));
const macSigningIdentity = process.env.AXCESS_MAC_SIGN_IDENTITY || "-";

module.exports = {
  packagerConfig: {
    asar: true,
    appBundleId: "edu.umich.axcess",
    appCategoryType: "public.app-category.developer-tools",
    executableName: "Axcess",
    extraResource: resources,
    ignore: [
      /\/backend-dist(?:\/|$)/,
      /\/playwright-browsers(?:\/|$)/,
      /\/out(?:\/|$)/,
      /\/test(?:\/|$)/,
    ],
    osxSign:
      process.platform === "darwin"
        ? {
            identity: macSigningIdentity,
            identityValidation: macSigningIdentity !== "-",
            optionsForFile: () => ({ hardenedRuntime: macSigningIdentity !== "-" }),
          }
        : undefined,
  },
  rebuildConfig: {},
  makers: [
    { name: "@electron-forge/maker-zip", platforms: ["darwin"] },
    { name: "@electron-forge/maker-squirrel", platforms: ["win32"] },
    {
      name: "@electron-forge/maker-deb",
      platforms: ["linux"],
      config: { options: { bin: "Axcess" } },
    },
    {
      name: "@electron-forge/maker-rpm",
      platforms: ["linux"],
      config: { options: { bin: "Axcess" } },
    },
  ],
  plugins: [
    {
      name: "@electron-forge/plugin-fuses",
      config: {
        version: FuseVersion.V1,
        [FuseV1Options.RunAsNode]: true,
        [FuseV1Options.EnableCookieEncryption]: true,
        [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,
        [FuseV1Options.EnableNodeCliInspectArguments]: false,
        [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: true,
        [FuseV1Options.OnlyLoadAppFromAsar]: true,
      },
    },
  ],
};
