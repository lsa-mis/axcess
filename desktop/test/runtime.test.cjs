const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const {
  contentSecurityPolicy,
  desktopEnvironment,
  isAxcessUrl,
  isSafeExternalUrl,
  nextZoomLevel,
  zoomActionFor,
  MAX_ZOOM_LEVEL,
  MIN_ZOOM_LEVEL,
  ZOOM_STEP,
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

test("Ctrl+= zooms in, which the View menu's accelerator never matched", () => {
  // `CommandOrControl+Plus` matches a literal "+", so the key labelled "+" on
  // the keyboard -- which reports as "=" until Shift is held -- did nothing,
  // while Ctrl+- worked because "-" is a key in its own right.
  for (const key of ["=", "+", "Add"]) {
    assert.equal(zoomActionFor({ type: "keyDown", control: true, key }), "in", key);
  }
  for (const key of ["-", "_", "Subtract"]) {
    assert.equal(zoomActionFor({ type: "keyDown", control: true, key }), "out", key);
  }
  assert.equal(zoomActionFor({ type: "keyDown", control: true, key: "0" }), "reset");
});

test("zoom follows Command on macOS and ignores Alt", () => {
  assert.equal(zoomActionFor({ type: "keyDown", meta: true, key: "=" }), "in");
  // Alt opens the hidden menu bar; Alt+key belongs to it, not to zoom.
  assert.equal(zoomActionFor({ type: "keyDown", control: true, alt: true, key: "=" }), null);
  // A bare keystroke must reach the page: "-" is ordinary typing.
  assert.equal(zoomActionFor({ type: "keyDown", key: "-" }), null);
  // Only the press, or one tap would zoom twice.
  assert.equal(zoomActionFor({ type: "keyUp", control: true, key: "=" }), null);
});

test("zoom steps stay inside a range the page can still reflow in", () => {
  assert.equal(nextZoomLevel(0, "in"), ZOOM_STEP);
  assert.equal(nextZoomLevel(0, "out"), -ZOOM_STEP);
  assert.equal(nextZoomLevel(4.5, "reset"), 0);
  assert.equal(nextZoomLevel(MAX_ZOOM_LEVEL, "in"), MAX_ZOOM_LEVEL, "clamped at the top");
  assert.equal(nextZoomLevel(MIN_ZOOM_LEVEL, "out"), MIN_ZOOM_LEVEL, "clamped at the bottom");
  // Chromium hands back NaN for a window that has gone away.
  assert.equal(nextZoomLevel(Number.NaN, "in"), ZOOM_STEP);
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
