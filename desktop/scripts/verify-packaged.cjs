const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

if (process.platform !== "darwin" && process.platform !== "win32") {
  console.log("Packaged runtime verification is implemented for macOS and Windows builds.");
  process.exit(0);
}

const desktopRoot = path.resolve(__dirname, "..");
const application =
  process.platform === "darwin"
    ? path.join(desktopRoot, "out", `Axcess-darwin-${process.arch}`, "Axcess.app")
    : path.join(desktopRoot, "out", `Axcess-win32-${process.arch}`);
const resources =
  process.platform === "darwin"
    ? path.join(application, "Contents", "Resources")
    : path.join(application, "resources");
const backendExecutable = process.platform === "win32" ? "axcess-server.exe" : "axcess-server";
const backend = path.join(resources, "backend-dist", "axcess-server", backendExecutable);
const electron =
  process.platform === "darwin"
    ? path.join(application, "Contents", "MacOS", "Axcess")
    : path.join(application, "Axcess.exe");
const dataRoot = fs.mkdtempSync(path.join(os.tmpdir(), "axcess-package-check-"));

try {
  const ocrRoot = path.join(resources, "ocr-runtime");
  const env = {
    ...process.env,
    AUDIT_DATA_DIR: dataRoot,
    AUDIT_DB_PATH: path.join(dataRoot, "audit.db"),
    AUDIT_BLOB_DIR: path.join(dataRoot, "blobs"),
    AUDIT_LOG_DIR: path.join(dataRoot, "logs"),
    AUDIT_ACCESS_TOKEN: "",
    AUDIT_NODE_EXECUTABLE: electron,
    AUDIT_NODE_RUN_AS_NODE: "1",
    PLAYWRIGHT_BROWSERS_PATH: path.join(resources, "playwright-browsers"),
    TESSDATA_PREFIX: path.join(ocrRoot, "share", "tessdata"),
    PATH: [path.join(ocrRoot, "bin"), "/usr/bin", "/bin"].join(path.delimiter),
  };
  const result = spawnSync(backend, ["--verify-runtime"], {
    cwd: path.dirname(backend),
    env,
    encoding: "utf8",
    timeout: 120_000,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(
      `Packaged runtime verification failed (${result.status}).\n${result.stderr || result.stdout}`,
    );
  }
  const lines = result.stdout.trim().split(/\r?\n/);
  const report = JSON.parse(lines.at(-1));
  for (const component of [
    "alfa",
    "axe_core",
    "chromium",
    "frontend",
    "python_backend",
    "reports",
    "url_scope",
  ]) {
    if (report[component] !== "available") {
      throw new Error(`Packaged ${component} verification did not pass.`);
    }
  }
  if (!String(report.ocr || "").startsWith("tesseract-")) {
    throw new Error("Packaged OCR verification did not report Tesseract.");
  }
  console.log(`Axcess packaged runtime verified: ${JSON.stringify(report)}`);
} finally {
  fs.rmSync(dataRoot, { recursive: true, force: true });
}
