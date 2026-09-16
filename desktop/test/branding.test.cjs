const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createRequire } = require("node:module");

const root = path.resolve(__dirname, "..");
const asset = (extension) => path.join(root, "assets", `axcess.${extension}`);
const pngSignature = Buffer.from("89504e470d0a1a0a", "hex");

function configFor(platform) {
  const filename = path.join(root, "forge.config.cjs");
  const context = {
    require: createRequire(filename),
    __dirname: root,
    process: { platform, env: {} },
    module: { exports: {} },
  };
  vm.runInNewContext(fs.readFileSync(filename, "utf8"), context, { filename });
  return context.module.exports;
}

test("native icon assets include high-resolution PNG, multi-size ICO, and ICNS", () => {
  const png = fs.readFileSync(asset("png"));
  assert.deepEqual(png.subarray(0, 8), pngSignature);
  assert.equal(png.readUInt32BE(16), 1024);
  assert.equal(png.readUInt32BE(20), 1024);
  assert.equal(png[25], 6, "PNG must preserve RGBA transparency");

  const ico = fs.readFileSync(asset("ico"));
  assert.equal(ico.readUInt16LE(0), 0);
  assert.equal(ico.readUInt16LE(2), 1);
  const sizes = [];
  for (let i = 0; i < ico.readUInt16LE(4); i++) {
    const entry = 6 + i * 16;
    const size = ico[entry] || 256;
    assert.equal(ico[entry + 1] || 256, size);
    sizes.push(size);
    const length = ico.readUInt32LE(entry + 8);
    const offset = ico.readUInt32LE(entry + 12);
    assert.ok(offset + length <= ico.length);
    assert.deepEqual(ico.subarray(offset, offset + 8), pngSignature);
    assert.equal(ico.readUInt32BE(offset + 16), size);
  }
  assert.deepEqual(sizes, [16, 24, 32, 48, 64, 128, 256]);

  const icns = fs.readFileSync(asset("icns"));
  assert.equal(icns.toString("ascii", 0, 4), "icns");
  assert.equal(icns.readUInt32BE(4), icns.length);
  const types = [];
  let offset = 8;
  while (offset < icns.length) {
    types.push(icns.toString("ascii", offset, offset + 4));
    const length = icns.readUInt32BE(offset + 4);
    assert.ok(length >= 8 && offset + length <= icns.length);
    offset += length;
  }
  assert.equal(offset, icns.length);
  for (const type of ["ic07", "ic08", "ic09", "ic10"]) assert.ok(types.includes(type));
});

test("every desktop packaging target uses the Axcess assets", () => {
  for (const platform of ["darwin", "win32", "linux"]) {
    const config = configFor(platform);
    assert.equal(config.packagerConfig.icon, path.join(root, "assets", "axcess"));
    const makers = config.makers;
    assert.equal(makers.find((m) => m.name.endsWith("maker-squirrel")).config.setupIcon, asset("ico"));
    for (const maker of ["maker-deb", "maker-rpm"]) {
      assert.equal(makers.find((m) => m.name.endsWith(maker)).config.options.icon, asset("png"));
    }
    for (const extension of ["svg", "png", "ico", "icns"]) {
      assert.ok(!config.packagerConfig.ignore.some((pattern) => pattern.test(asset(extension))));
    }
  }
});

const startupScreen = (screen) =>
  fs.readFileSync(path.join(root, "static", `${screen}.html`), "utf8");

test("the error screen references the bundled logo without redundant accessible text", () => {
  const html = startupScreen("error");
  assert.match(html, /img-src 'self'/);
  assert.match(html, /<img[^>]+src="\.\.\/assets\/axcess.svg"[^>]+alt=""/);
});

// The loading screen draws the mark inline instead, because only part of it
// moves: an <img> is an opaque document, so the ring inside it cannot be
// animated on its own. Inline markup is not a fetch, so the screen needs no
// img-src at all and keeps 'none' as its default.
test("the loading screen inlines the mark and fetches nothing", () => {
  const html = startupScreen("loading");
  assert.doesNotMatch(html, /<img\b/);
  assert.doesNotMatch(html, /img-src/);
  assert.match(html, /<svg[^>]+aria-hidden="true"/);
  // The ring and its node spin; the 'a' must stay out of the rotating group.
  const ring = html.match(/<g class="ring">([\s\S]*?)<\/g>/);
  assert.ok(ring, "expected a .ring group to rotate");
  assert.match(ring[1], /A 12\.6 12\.6/);
  assert.match(ring[1], /<circle/);
  assert.doesNotMatch(ring[1], /C 16\.989/);
  // Rotating about the viewBox centre (16,16) rather than the group's own
  // bounding box is what keeps the ring on-axis.
  assert.match(html, /transform-box: view-box/);
  assert.match(html, /prefers-reduced-motion/);
});

test("the bundled logo carries no text, raster, script, or remote import", () => {
  const svg = fs.readFileSync(asset("svg"), "utf8");
  assert.doesNotMatch(svg, /<text\b|<image\b|<script\b|@import/);
});
