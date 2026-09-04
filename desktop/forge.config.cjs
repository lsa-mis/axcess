const fs = require("node:fs");
const path = require("node:path");
const { FuseV1Options, FuseVersion } = require("@electron/fuses");

const resources = ["backend-dist", "playwright-browsers", "ocr-runtime"]
  .map((name) => path.join(__dirname, name))
  .filter((candidate) => fs.existsSync(candidate));
const macSigningIdentity = process.env.AXCESS_MAC_SIGN_IDENTITY || "-";
const isReleaseSigned = macSigningIdentity !== "-";

function complete(values) {
  return values.every((value) => Boolean(value));
}

function any(values) {
  return values.some((value) => Boolean(value));
}

function macNotarization() {
  const keychainProfile = process.env.APPLE_NOTARY_KEYCHAIN_PROFILE;
  const appleIdValues = [
    process.env.APPLE_ID,
    process.env.APPLE_APP_SPECIFIC_PASSWORD,
    process.env.APPLE_TEAM_ID,
  ];
  const apiKeyValues = [
    process.env.APPLE_API_KEY,
    process.env.APPLE_API_KEY_ID,
    process.env.APPLE_API_ISSUER,
  ];

  if (keychainProfile) {
    return {
      keychainProfile,
      ...(process.env.APPLE_NOTARY_KEYCHAIN
        ? { keychain: process.env.APPLE_NOTARY_KEYCHAIN }
        : {}),
    };
  }
  if (complete(apiKeyValues)) {
    return {
      appleApiKey: apiKeyValues[0],
      appleApiKeyId: apiKeyValues[1],
      appleApiIssuer: apiKeyValues[2],
    };
  }
  if (complete(appleIdValues)) {
    return {
      appleId: appleIdValues[0],
      appleIdPassword: appleIdValues[1],
      teamId: appleIdValues[2],
    };
  }
  if (any([...appleIdValues, ...apiKeyValues])) {
    throw new Error("Incomplete Apple notarization credentials.");
  }
  return undefined;
}

const osxNotarize = process.platform === "darwin" ? macNotarization() : undefined;
if (osxNotarize && !isReleaseSigned) {
  throw new Error(
    "Notarization credentials require AXCESS_MAC_SIGN_IDENTITY to name a Developer ID Application certificate.",
  );
}
if (
  isReleaseSigned &&
  !macSigningIdentity.startsWith("Developer ID Application:")
) {
  throw new Error(
    "Direct distribution requires a Developer ID Application identity; Apple Development certificates are not distributable.",
  );
}
if (process.env.AXCESS_REQUIRE_NOTARIZATION === "1" && !osxNotarize) {
  throw new Error("AXCESS_REQUIRE_NOTARIZATION=1 but no Apple notarization credentials are configured.");
}

module.exports = {
  packagerConfig: {
    asar: true,
    appBundleId: "edu.umich.axcess",
    appCategoryType: "public.app-category.developer-tools",
    executableName: "Axcess",
    // Packager selects .icns or .ico for the target platform.
    icon: path.join(__dirname, "assets", "axcess"),
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
            identityValidation: isReleaseSigned,
            optionsForFile: () => ({ hardenedRuntime: isReleaseSigned }),
          }
        : undefined,
    osxNotarize,
  },
  rebuildConfig: {},
  makers: [
    { name: "@electron-forge/maker-zip", platforms: ["darwin"] },
    {
      name: "@electron-forge/maker-squirrel",
      platforms: ["win32"],
      config: { setupIcon: path.join(__dirname, "assets", "axcess.ico") },
    },
    {
      name: "@electron-forge/maker-deb",
      platforms: ["linux"],
      config: { options: { bin: "Axcess", icon: path.join(__dirname, "assets", "axcess.png") } },
    },
    {
      name: "@electron-forge/maker-rpm",
      platforms: ["linux"],
      config: { options: { bin: "Axcess", icon: path.join(__dirname, "assets", "axcess.png") } },
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
