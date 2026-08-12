const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

if (process.platform !== "darwin") process.exit(0);

const packageJson = require("../package.json");
const application = path.join(
  __dirname,
  "..",
  "out",
  `Axcess-darwin-${process.arch}`,
  "Axcess.app",
);
const output = path.join(
  __dirname,
  "..",
  "out",
  "make",
  `Axcess-${packageJson.version}-${process.arch}.dmg`,
);

if (!fs.existsSync(application)) {
  throw new Error(`Packaged application is missing: ${application}`);
}

fs.mkdirSync(path.dirname(output), { recursive: true });
const staging = fs.mkdtempSync(path.join(os.tmpdir(), "axcess-dmg-"));
try {
  fs.cpSync(application, path.join(staging, "Axcess.app"), { recursive: true });
  fs.symlinkSync("/Applications", path.join(staging, "Applications"));
  const result = spawnSync(
    "hdiutil",
    ["create", "-volname", "Axcess", "-srcfolder", staging, "-ov", "-format", "UDZO", output],
    { stdio: "inherit" },
  );
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`hdiutil exited with status ${result.status}`);
} finally {
  fs.rmSync(staging, { recursive: true, force: true });
}
