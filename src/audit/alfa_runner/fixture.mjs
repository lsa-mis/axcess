/* Real browser fixture: fulfills the one document in memory and aborts every
 * other request. No listener, external crawl, or model is used. */
import { readFile } from "node:fs/promises";
import { chromium } from "playwright";
import { Playwright as AlfaPlaywright } from "@siteimprove/alfa-playwright";
import { Audit } from "@siteimprove/alfa-act";
import rules from "@siteimprove/alfa-rules";
import { collectOutcomes, boundedJson } from "./evidence.mjs";

const browser = await chromium.launch({headless: true, executablePath: process.env.ALFA_CHROMIUM_PATH});
try {
  const context = await browser.newContext({ serviceWorkers: "block" });
  await context.routeWebSocket("**/*", async (route) => route.close());
  let fixture = "";
  await context.route("**/*", (route) => route.request().url() === "http://alfa-fixture.invalid/"
    ? route.fulfill({ status: 200, contentType: "text/html", body: fixture })
    : route.abort("blockedbyclient"));
  const page = await context.newPage();
  const results = {};
  const scenarios = {
    pass: '<p style="color:#111;background:#fff">Readable contrast</p><button>Save</button>',
    fail: '<p style="color:#ddd;background:#fff">Low contrast</p><button></button>',
    gradient: '<p style="color:#333;background:linear-gradient(#fff,#999);background-size:50% 50%">Sized gradient</p>',
    repeated: '<p style="color:#ddd;background:#fff">Same text</p><p style="color:#ddd;background:#fff">Same text</p>',
    shadow: '<div id="one"></div><div id="two"></div><script>for (const id of ["one","two"]) document.getElementById(id).attachShadow({mode:"open"}).innerHTML = `<p style="color:#ddd;background:#fff">Same text</p>`;</script>',
    cap: '<p style="background:linear-gradient(#fff,#999);background-size:50% 50%">Uncertain contrast</p>'.repeat(205) + '<button></button>',
  };
  const selected = rules.filter((rule) => ["sia-r69", "sia-r12"].some((id) => rule.uri.endsWith(`/${id}`)));
  for (const [name, markup] of Object.entries(scenarios)) {
    fixture = `<!doctype html><html lang="en"><head><title>Alfa test</title></head><body><main>${markup}</main></body></html>`;
    await page.goto("http://alfa-fixture.invalid/");
    const handle = await page.evaluateHandle(() => document);
    const alfaPage = await AlfaPlaywright.toPage(handle);
    await handle.dispose();
    const outcomes = await Audit.of(alfaPage, selected).evaluate();
    results[name] = collectOutcomes(outcomes);
    // A local, bundled axe build independently observes the same DOM.
    const axe = await readFile(new URL("../web/static/axe.min.js", import.meta.url), "utf8");
    await page.evaluate(axe);
    results[name].axe = await page.evaluate(async () => {
      const result = await window.axe.run({runOnly: ["color-contrast", "button-name"]});
      return Object.fromEntries(["violations", "incomplete", "passes"].map((key) => [key, result[key].map((r) => ({id:r.id, count:r.nodes.length}))]));
    });
  }
  results.large = boundedJson({diagnostics:["Diagnostic"],diagnostic:{message:"Diagnostic",errors:Array.from({length:100}, () => ({message:"x".repeat(10000),element:{name:"p"}}))},target:{type:"text",data:"same"}});
  results.bounds = ["😀".repeat(5000), '\\"\n'.repeat(5000)].map((text) => boundedJson({diagnostics:Array(8).fill(text),target:{type:"text",data:text}}));
  process.stdout.write(JSON.stringify(results));
} finally { await browser.close(); }
