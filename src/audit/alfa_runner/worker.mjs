/*
 * Axcess' scan-long Alfa worker.
 *
 * runner.mjs opens its own browser for one page and checks the page as it
 * loads. This worker opens no browser at all. The crawler takes Alfa's
 * snapshot of the page inside its own tab (the script it runs there is sent
 * in the handshake below, so the snapshot and the rules always come from
 * the same pinned Alfa packages), at load and in every page state
 * Click-Through opens, and sends each snapshot here. That lets Alfa check
 * the same page states axe checks, in the same page.
 *
 * Protocol, one JSON object per line on stdin and stdout:
 *   worker -> {"ready": true, "protocol_version": 1, "snapshot_script": "..."}
 *   crawler -> {"id": 1, "level": "AA", "version": "2.1",
 *               "snapshot": {"url": "...", "node": {...}, "device": {...}}}
 *   worker -> {"id": 1, "protocol_version": 1, "engine": "alfa", ...outcomes}
 *          or {"id": 1, "error": "..."}
 * Requests are evaluated one at a time, in order. The worker ends when its
 * stdin closes. It never opens a network connection or a file.
 */

import { Audit } from "@siteimprove/alfa-act";
import { Device } from "@siteimprove/alfa-device";
import * as deviceNative from "@siteimprove/alfa-device/native";
import { Document, Node } from "@siteimprove/alfa-dom";
import * as domNative from "@siteimprove/alfa-dom/native";
import { Header, Headers, Request, Response } from "@siteimprove/alfa-http";
import { URL } from "@siteimprove/alfa-url";
import { Page } from "@siteimprove/alfa-web";
import { createInterface } from "node:readline";

import { collectOutcomes } from "./evidence.mjs";
import { selectRules } from "./rules.mjs";

// Alfa's own in-page serializers, the ones its Playwright integration runs
// in the page (Playwright.toPage). Both are self-contained functions (no
// imports), which is why they can be sent as source. The page's document is
// passed explicitly: called through a script string, the default parameter
// is not applied. JSON.stringify in the page hands the crawler one string,
// so it never decodes and re-encodes a large snapshot.
const SNAPSHOT_SCRIPT = `async () => {
  const fromNode = ${domNative.Native.fromNode.toString()};
  const fromWindow = ${deviceNative.Native.fromWindow.toString()};
  const node = await fromNode(document, {});
  return JSON.stringify({ url: location.href, node, device: fromWindow(window) });
}`;

const ruleCache = new Map();

function rulesFor(level, version) {
  const key = `${level}|${version}`;
  if (!ruleCache.has(key)) ruleCache.set(key, selectRules(level, version));
  return ruleCache.get(key);
}

function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function toPage(snapshot) {
  const device = Device.from(snapshot.device);
  // A frame's address can be about:srcdoc or about:blank; both parse.
  const url = URL.parse(String(snapshot.url || "about:blank")).getOr(
    URL.parse("about:blank").getUnsafe(),
  );
  // As Alfa's Playwright integration does: the crawler already checked
  // the response, so a 200 HTML response stands in for it.
  const request = Request.of("GET", url);
  const response = Response.of(url, 200, Headers.of([Header.of("Content-Type", "text/html")]));
  const json = snapshot.node;
  const node = json.type === "document" ? Node.from(json, device) : Document.of([Node.from(json, device)]);
  return Page.of(request, response, node, device);
}

async function handle(line) {
  let id = null;
  try {
    const request = JSON.parse(line);
    id = request.id;
    if (!["A", "AA", "AAA"].includes(request.level)) throw new Error("unsupported WCAG level");
    if (!["2.1", "2.2"].includes(request.version)) throw new Error("unsupported WCAG version");
    if (!request.snapshot || typeof request.snapshot !== "object") throw new Error("snapshot missing");
    const page = toPage(request.snapshot);
    const outcomes = await Audit.of(page, rulesFor(request.level, request.version)).evaluate();
    emit({
      id,
      protocol_version: 1,
      engine: "alfa",
      url: String(request.snapshot.url || ""),
      status: 200,
      content_type: "text/html",
      ...collectOutcomes(outcomes, request.version),
    });
  } catch (error) {
    // The message names what failed (a parse error, an Alfa exception), not
    // page content, but the crawler still withholds it in a sign-in scan.
    const message = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    emit({ id, error: message.replace(/\s+/g, " ").slice(0, 500) });
  }
}

emit({ ready: true, protocol_version: 1, snapshot_script: SNAPSHOT_SCRIPT });
const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  if (line.trim()) await handle(line);
}
