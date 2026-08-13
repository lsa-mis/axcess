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

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { stdio: "inherit", ...options });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} exited with status ${result.status}`);
}

function verifyPortableSymlinks(root) {
  const pending = [root];
  while (pending.length > 0) {
    const current = pending.pop();
    const entry = fs.lstatSync(current);
    if (entry.isSymbolicLink()) {
      const target = fs.readlinkSync(current);
      if (path.isAbsolute(target)) {
        throw new Error(`Application contains a non-portable absolute symlink: ${current} -> ${target}`);
      }
      if (!fs.existsSync(path.resolve(path.dirname(current), target))) {
        throw new Error(`Application contains a broken symlink: ${current} -> ${target}`);
      }
      continue;
    }
    if (entry.isDirectory()) {
      for (const child of fs.readdirSync(current)) pending.push(path.join(current, child));
    }
  }
}

fs.mkdirSync(path.dirname(output), { recursive: true });
const staging = fs.mkdtempSync(path.join(os.tmpdir(), "axcess-dmg-"));
try {
  // macOS framework bundles depend on relative symlinks. Node's default
  // fs.cpSync behavior resolves them and can recreate absolute links back to
  // the build machine, producing an installer that looks complete but cannot
  // pass codesign or launch after being copied elsewhere. ditto is the native
  // bundle-aware copier and preserves those links and extended attributes.
  const stagedApplication = path.join(staging, "Axcess.app");
  run("ditto", [application, stagedApplication]);
  verifyPortableSymlinks(stagedApplication);
  run("codesign", ["--verify", "--deep", "--strict", stagedApplication]);
  fs.symlinkSync("/Applications", path.join(staging, "Applications"));
  run(
    "hdiutil",
    ["create", "-volname", "Axcess", "-srcfolder", staging, "-ov", "-format", "UDZO", output],
  );
} finally {
  fs.rmSync(staging, { recursive: true, force: true });
}

// Validate what users receive, not only Electron Forge's source app. This
// catches copy/image transformations that would otherwise escape the packaged
// runtime check and fail only after installation.
const mountPoint = fs.mkdtempSync(path.join(os.tmpdir(), "axcess-dmg-mount-"));
let attached = false;
try {
  run("hdiutil", ["attach", output, "-nobrowse", "-readonly", "-mountpoint", mountPoint]);
  attached = true;
  const mountedApplication = path.join(mountPoint, "Axcess.app");
  verifyPortableSymlinks(mountedApplication);
  run("codesign", ["--verify", "--deep", "--strict", mountedApplication]);
} finally {
  if (attached) {
    const result = spawnSync("hdiutil", ["detach", mountPoint], { stdio: "inherit" });
    if (result.error || result.status !== 0) {
      spawnSync("hdiutil", ["detach", "-force", mountPoint], { stdio: "inherit" });
    }
  }
  fs.rmSync(mountPoint, { recursive: true, force: true });
}
