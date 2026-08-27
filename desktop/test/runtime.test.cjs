const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const { desktopEnvironment, isAxcessUrl, isSafeExternalUrl } = require("../src/runtime.cjs");

test("navigation remains on the exact loopback origin", () => {
  const origin = "http://127.0.0.1:43125";
  assert.equal(isAxcessUrl(`${origin}/app/scans/1`, origin), true);
  assert.equal(isAxcessUrl("http://127.0.0.1:43126/app/", origin), false);
  assert.equal(isAxcessUrl("https://127.0.0.1:43125/app/", origin), false);
  assert.equal(isAxcessUrl("javascript:alert(1)", origin), false);
});

test("only web URLs may leave the desktop shell", () => {
  assert.equal(isSafeExternalUrl("https://www.w3.org/WAI/"), true);
  assert.equal(isSafeExternalUrl("http://example.test/page"), true);
  assert.equal(isSafeExternalUrl("file:///etc/passwd"), false);
  assert.equal(isSafeExternalUrl("mailto:test@example.com"), false);
  assert.equal(isSafeExternalUrl("custom-protocol://payload"), false);
});

test("desktop evidence uses the operating system application-data directory", () => {
  const env = desktopEnvironment({
    userDataPath: path.join("tmp", "Axcess User"),
    electronExecutable: path.join("Applications", "Axcess"),
    resourcesPath: path.join("Applications", "Axcess Resources"),
    packaged: true,
  });
  assert.equal(env.AUDIT_DB_PATH, path.join("tmp", "Axcess User", "data", "audit.db"));
  assert.equal(env.AUDIT_ACCESS_TOKEN, "");
  assert.equal(
    env.PLAYWRIGHT_BROWSERS_PATH,
    path.join("Applications", "Axcess Resources", "playwright-browsers"),
  );
  assert.equal(
    env.TESSDATA_PREFIX,
    path.join("Applications", "Axcess Resources", "ocr-runtime", "share", "tessdata"),
  );
  assert.ok(
    env.PATH.startsWith(
      path.join("Applications", "Axcess Resources", "ocr-runtime", "bin") + path.delimiter,
    ),
  );
});
