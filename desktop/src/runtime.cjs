const path = require("node:path");

function isAxcessUrl(candidate, origin) {
  try {
    const parsed = new URL(candidate);
    return parsed.origin === origin && parsed.protocol === "http:";
  } catch {
    return false;
  }
}

function isSafeExternalUrl(candidate) {
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

function desktopEnvironment({ userDataPath, electronExecutable, resourcesPath, packaged }) {
  const dataRoot = path.join(userDataPath, "data");
  const ocrRoot = path.join(resourcesPath, "ocr-runtime");
  const environment = {
    AUDIT_DATA_DIR: dataRoot,
    AUDIT_DB_PATH: path.join(dataRoot, "audit.db"),
    AUDIT_BLOB_DIR: path.join(dataRoot, "blobs"),
    AUDIT_LOG_DIR: path.join(dataRoot, "logs"),
    AUDIT_ACCESS_TOKEN: "",
    AUDIT_NODE_EXECUTABLE: electronExecutable,
    AUDIT_NODE_RUN_AS_NODE: "1",
    PYTHONUNBUFFERED: "1",
  };
  if (packaged) {
    environment.PLAYWRIGHT_BROWSERS_PATH = path.join(resourcesPath, "playwright-browsers");
    environment.TESSDATA_PREFIX = path.join(ocrRoot, "share", "tessdata");
    environment.PATH = [path.join(ocrRoot, "bin"), process.env.PATH || ""]
      .filter(Boolean)
      .join(path.delimiter);
  }
  return environment;
}

module.exports = { desktopEnvironment, isAxcessUrl, isSafeExternalUrl };
