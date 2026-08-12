const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.resolve(__dirname, "..");

function requirePath(candidate, label) {
  if (!fs.existsSync(candidate)) throw new Error(`${label} is missing: ${candidate}`);
}

const backendName = process.platform === "win32" ? "axcess-server.exe" : "axcess-server";
const backendRoot = path.join(desktopRoot, "backend-dist", "axcess-server");
requirePath(path.join(backendRoot, backendName), "Frozen Python backend");
requirePath(
  path.join(backendRoot, "_internal", "audit", "web", "frontend", "dist", "index.html"),
  "Built React application",
);
requirePath(
  path.join(
    backendRoot,
    "_internal",
    "audit",
    "alfa_runner",
    "node_modules",
    "@siteimprove",
    "alfa-act",
  ),
  "Siteimprove Alfa dependencies",
);

const browserRoot = path.join(desktopRoot, "playwright-browsers");
requirePath(browserRoot, "Playwright browser bundle");
if (!fs.readdirSync(browserRoot).some((name) => name.startsWith("chromium-"))) {
  throw new Error(`Playwright Chromium is missing from ${browserRoot}`);
}

if (process.platform === "darwin") {
  const ocrRoot = path.join(desktopRoot, "ocr-runtime");
  requirePath(path.join(ocrRoot, "bin", "tesseract"), "Tesseract executable");
  requirePath(
    path.join(ocrRoot, "share", "tessdata", "eng.traineddata"),
    "Tesseract English language data",
  );
}

console.log("Axcess desktop build resources are complete.");
