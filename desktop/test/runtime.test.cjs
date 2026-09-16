const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const {
  contentSecurityPolicy,
  desktopEnvironment,
  isAxcessUrl,
  isSafeExternalUrl,
} = require("../src/runtime.cjs");

/** Read one directive's source list out of the policy string. */
function directive(name) {
  const found = contentSecurityPolicy()
    .split(";")
    .map((part) => part.trim())
    .find((part) => part === name || part.startsWith(`${name} `));
  assert.ok(found, `policy is missing the ${name} directive`);
  return found.slice(name.length).trim().split(/\s+/).filter(Boolean);
}

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

test("the page inspector's capture can resolve and style itself", () => {
  // A `srcdoc` frame inherits this policy, so the capture's <base href> and the
  // scanned site's stylesheets, fonts and images must all be permitted here.
  // `base-uri 'none'` silently dropped the <base>, which left every inspected
  // page unstyled and its highlighted element collapsed out of view.
  for (const source of ["http:", "https:"]) {
    assert.ok(
      directive("base-uri").includes(source),
      `base-uri must admit ${source} so the capture's <base href> survives`,
    );
    for (const name of ["style-src", "img-src", "font-src"]) {
      assert.ok(
        directive(name).includes(source),
        `${name} must admit ${source} so the capture loads the live site's assets`,
      );
    }
  }
  assert.ok(
    !directive("base-uri").includes("'none'"),
    "base-uri 'none' drops the inspector's <base href>",
  );
  // The inspector outlines the flagged element with inline styles.
  assert.ok(directive("style-src").includes("'unsafe-inline'"));
});

test("relaxing the inspector's styling does not loosen script execution", () => {
  // The capture is untrusted scanned markup. It may style itself; it may never
  // execute, embed, call out or submit.
  assert.deepEqual(directive("script-src"), ["'self'"]);
  assert.deepEqual(directive("object-src"), ["'none'"]);
  assert.deepEqual(directive("frame-src"), ["'none'"]);
  assert.deepEqual(directive("connect-src"), ["'self'"]);
  assert.deepEqual(directive("form-action"), ["'self'"]);
  assert.deepEqual(directive("frame-ancestors"), ["'none'"]);
  assert.deepEqual(directive("default-src"), ["'self'"]);
  assert.ok(!contentSecurityPolicy().includes("unsafe-eval"));
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

const { OutputTail, startupFailureDetails } = require("../src/runtime.cjs");

test("the output tail keeps the backend's last lines across chunk boundaries", () => {
  const tail = new OutputTail(3);
  tail.push("first\nsec");
  tail.push("ond\nthird\n");
  assert.equal(tail.text(), "first\nsecond\nthird");
  tail.push("fourth\n\n");
  assert.equal(tail.text(), "second\nthird\nfourth");
  tail.push("Traceback (most recent");
  assert.equal(tail.text(), "second\nthird\nfourth\nTraceback (most recent");
});

test("a startup failure reports the launcher's reason and the backend's output", () => {
  const details = startupFailureDetails({
    error: new Error("Axcess backend stopped unexpectedly."),
    backendOutput: "ModuleNotFoundError: No module named 'audit.analyzer'\n",
    exitCode: 1,
    logPath: "/tmp/launcher.log",
    packaged: true,
  });
  assert.equal(
    details.reason,
    "Axcess backend stopped unexpectedly. The local service exited with code 1.",
  );
  assert.equal(details.output, "ModuleNotFoundError: No module named 'audit.analyzer'");
  assert.equal(details.logPath, "/tmp/launcher.log");
  assert.equal(details.packaged, true);
});

test("a startup failure without detail keeps the generic message", () => {
  const details = startupFailureDetails({ backendOutput: "", exitCode: null });
  assert.equal(details.reason, "The local service did not become ready.");
  assert.equal(details.output, "");
  assert.equal(details.packaged, false);
});

test("a signal-killed backend is named as such", () => {
  const details = startupFailureDetails({ exitCode: "SIGKILL" });
  assert.equal(details.reason, "The local service was stopped by signal SIGKILL.");
});
