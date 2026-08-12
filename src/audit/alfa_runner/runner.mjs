/*
 * Axcess' local Alfa adapter.
 *
 * The Python crawler remains the authority for scope, page inventory, and
 * stored evidence. This runner opens one local Chromium page for a URL that
 * Axcess already admitted to that scope, turns its DOM into Alfa's Page
 * representation via the maintained Alfa Playwright integration, then emits a
 * deliberately bounded JSON record on stdout. It never fetches arbitrary
 * follow-up URLs or contacts an external service.
 */

import { Audit, Outcome } from "@siteimprove/alfa-act";
import { Playwright as AlfaPlaywright } from "@siteimprove/alfa-playwright";
import rules from "@siteimprove/alfa-rules";
import { Criterion, Conformance } from "@siteimprove/alfa-wcag";
import { Refinement } from "@siteimprove/alfa-refinement";
import { chromium } from "playwright";
import { lookup } from "node:dns/promises";
import { chmod, mkdir, mkdtemp, readdir, rm, stat } from "node:fs/promises";
import { isIP } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";

const MAX_FINDINGS = 200;
const MAX_EVIDENCE_CHARS = 4_000;
const MAX_MESSAGE_CHARS = 2_000;
const PROFILE_ROOT = join(tmpdir(), "axcess-protected-alfa");
const PROFILE_PREFIX = "run-";
const STALE_PROFILE_MAX_AGE_MS = 6 * 60 * 60 * 1_000;
// Alfa evaluates the rendered DOM. Authenticated raster/media/font loads do
// not improve its v1 rule coverage, but can place raw protected bytes in the
// short-lived Chromium profile/cache. Keep this mirror of the primary
// protected-session resource policy so the two engines have the same default
// evidence and resource boundary.
const BLOCKED_AUTH_RESOURCE_TYPES = new Set([
  "worker",
  "sharedworker",
  "websocket",
  "eventsource",
  "image",
  "media",
  "font",
  "manifest",
  "prefetch",
]);
const WEBRTC_BLOCK_INIT_SCRIPT = `
for (const name of ["RTCPeerConnection", "webkitRTCPeerConnection", "mozRTCPeerConnection"]) {
  try {
    Object.defineProperty(globalThis, name, {
      value: undefined,
      configurable: false,
      writable: false,
    });
  } catch (_) {}
}
`;

class RunnerFailure extends Error {}

const args = process.argv.slice(2);
if (args.length !== 1 || args[0] !== "--input-stdin") {
  fail("Runner input must be supplied through stdin.");
}
const input = await readRunnerInput();
const url = input.url;
const level = input.level;
const userAgent = input.user_agent;
const auth = input.storage_state ? input : null;

let browser;
let context;
let profileDir;
try {
  const browserArgs = [
    "--incognito",
    "--disable-quic",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--disk-cache-size=1",
    "--media-cache-size=1",
  ];
  const contextOptions = {
    userAgent,
    viewport: { width: 1440, height: 900 },
    // The authenticated Alfa bridge never needs a download or a service
    // worker. Blocking both prevents session-bearing background work from
    // outliving the one-use in-memory runner context.
    acceptDownloads: false,
    serviceWorkers: "block",
    ...(auth?.egress_proxy ? { proxy: { server: auth.egress_proxy, bypass: "" } } : {}),
    ...(auth?.storage_state ? { storageState: auth.storage_state } : {}),
  };
  if (auth) {
    // Chromium keeps authenticated cookies/cache in its user-data directory
    // even when we never call storageState() on disk. Put that short-lived
    // profile in one private temp directory and remove it on every exit;
    // startup removes only Axcess-owned stale siblings after a crash.
    profileDir = await createEphemeralProfileDir();
    context = await chromium.launchPersistentContext(profileDir, {
      headless: true,
      executablePath: process.env.ALFA_CHROMIUM_PATH || undefined,
      args: browserArgs,
      ...contextOptions,
    });
  } else {
    browser = await chromium.launch({
      headless: true,
      executablePath: process.env.ALFA_CHROMIUM_PATH || undefined,
      args: browserArgs,
    });
    context = await browser.newContext(contextOptions);
  }
  await context.addInitScript(WEBRTC_BLOCK_INIT_SCRIPT);
  if (auth) {
    await installReadOnlyRoute(context, auth.allowed_origins, auth.target_origins);
  }
  const page = await context.newPage();
  installNoArtifactHandlers(context, page);
  const response = await page.goto(url, { waitUntil: "load", timeout: 30_000 });
  await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => undefined);
  if (auth) await assertSafeAllowedDocument(page.url(), new Set(auth.target_origins));

  const status = response?.status() ?? 0;
  const contentType = response?.headers()["content-type"] ?? "text/html";
  if (auth && (status === 401 || status === 403 || await looksLikeAuthenticationPage(page))) {
    emit({
      protocol_version: 1,
      engine: "alfa",
      url: page.url(),
      status,
      content_type: contentType,
      authentication_required: true,
      outcome_counts: emptyCounts(),
      findings: [],
    });
  } else if (status < 200 || status >= 300 || !contentType.toLowerCase().includes("html")) {
    emit({
      protocol_version: 1,
      engine: "alfa",
      url: page.url(),
      status,
      content_type: contentType,
      outcome_counts: emptyCounts(),
      findings: [],
    });
  } else {
    const document = await page.evaluateHandle(() => window.document);
    const alfaPage = await AlfaPlaywright.toPage(document);
    await document.dispose();

    const conformance =
      level === "A"
        ? Conformance.isA()
        : level === "AAA"
          ? Conformance.isAAA()
          : Conformance.isAA();
    const selectedRules = rules.filter((rule) =>
      rule.hasRequirement(Refinement.and(Criterion.isCriterion, conformance)),
    );
    const outcomes = await Audit.of(alfaPage, selectedRules).evaluate();
    const counts = emptyCounts();
    const findings = [];
    for (const outcome of outcomes) {
      if (Outcome.isFailed(outcome)) {
        counts.failed += 1;
      } else if (Outcome.isCantTell(outcome)) {
        counts.cantTell += 1;
      } else if (Outcome.isPassed(outcome)) {
        counts.passed += 1;
      } else {
        counts.inapplicable += 1;
      }
      if ((Outcome.isFailed(outcome) || Outcome.isCantTell(outcome)) && findings.length < MAX_FINDINGS) {
        findings.push(toFinding(outcome));
      }
    }
    emit({
      protocol_version: 1,
      engine: "alfa",
      url: page.url(),
      status,
      content_type: contentType,
      outcome_counts: counts,
      findings,
      findings_truncated: counts.failed + counts.cantTell > findings.length,
    });
  }
} catch (error) {
  if (error instanceof RunnerFailure) throw error;
  // Playwright/browser exceptions frequently include a URL or response
  // diagnostic.  Protected-mode stderr is deliberately generic so neither
  // the local child nor a parent error path turns it into report/log data.
  fail("Alfa could not evaluate the approved page.");
} finally {
  await context?.close().catch(() => undefined);
  await browser?.close().catch(() => undefined);
  if (profileDir) await rm(profileDir, { recursive: true, force: true, maxRetries: 1 }).catch(() => undefined);
}

function toFinding(outcome) {
  const rule = outcome.rule;
  const ruleJson = rule.toJSON();
  const requirements = Array.isArray(ruleJson.requirements) ? ruleJson.requirements : [];
  const criteria = requirements.filter((requirement) => requirement?.type === "criterion");
  const ruleCriteria = rule.requirements.filter(Criterion.isCriterion);
  const wcagScs = criteria
    .map((criterion) => String(criterion.chapter || ""))
    .filter(Boolean);
  const primary = criteria[0] || null;
  const outcomeJson = outcome.toJSON();
  const sarif = outcome.toSARIF();
  const message = truncate(
    sarif?.message?.text || outcomeJson?.diagnostic?.message || "Alfa requires expert review.",
    MAX_MESSAGE_CHARS,
  );
  const targetEvidence = compactJson(summarizeTarget(outcomeJson?.target));
  return {
    rule_id: rule.uri.split("/").filter(Boolean).pop() || rule.uri,
    rule_uri: rule.uri,
    outcome: Outcome.isFailed(outcome) ? "failed" : "cantTell",
    mode: outcome.mode,
    wcag_sc: primary?.chapter || null,
    wcag_scs: wcagScs,
    wcag_level: ruleCriteria[0] ? criterionLevel(ruleCriteria[0]) : null,
    help: primary
      ? `WCAG ${primary.chapter}: ${primary.title || "Alfa ACT rule"}`
      : "Alfa ACT rule requires expert review",
    failure_summary: message,
    target_hint: targetEvidence || "Alfa target unavailable; see the rule evidence.",
    evidence: compactJson({
      diagnostic: outcomeJson?.diagnostic,
      expectations: outcomeJson?.expectations,
      mode: outcome.mode,
      outcome: outcome.outcome,
      rule: { uri: rule.uri, requirements: criteria },
      target: summarizeTarget(outcomeJson?.target),
    }),
  };
}

function summarizeTarget(target) {
  if (Array.isArray(target)) return target.slice(0, 3).map(summarizeTarget);
  if (!target || typeof target !== "object") return target ?? null;
  const type = String(target.type || "");
  if (type === "document") return { type: "document" };
  if (type === "text") {
    return { type, data: truncate(String(target.data || "").replace(/\s+/g, " ").trim(), 160) };
  }
  if (type === "attribute") {
    return { type, name: target.name || null, value: truncate(String(target.value || ""), 160) };
  }
  if (type === "element") {
    const attributes = Array.isArray(target.attributes)
      ? target.attributes.slice(0, 12).map((attribute) => ({
          type: "attribute",
          name: attribute?.name || null,
          value: truncate(String(attribute?.value || ""), 160),
        }))
      : [];
    const text = Array.isArray(target.children)
      ? target.children
          .filter((child) => child?.type === "text")
          .map((child) => String(child.data || ""))
          .join(" ")
          .replace(/\s+/g, " ")
          .trim()
      : "";
    return { type, name: target.name || null, attributes, text: truncate(text, 240) };
  }
  return { type: type || "node" };
}

function criterionLevel(requirement) {
  // Alfa's Criterion keeps versioned levels. The 2.2 branch is the report
  // target; a rule may be Level A even in an AA scan.
  let found = null;
  requirement.level?.some((value, versions) => {
    if ([...versions].includes("2.2")) found = value;
  });
  return found;
}

function emptyCounts() {
  return { failed: 0, cantTell: 0, passed: 0, inapplicable: 0 };
}

function compactJson(value) {
  if (value === undefined || value === null) return "";
  try {
    return truncate(JSON.stringify(value), MAX_EVIDENCE_CHARS);
  } catch {
    return "";
  }
}

function truncate(value, max) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function fail(message) {
  process.stderr.write(`Axcess Alfa runner: ${message}\n`);
  // ``process.exitCode`` alone lets synchronous parsing continue after a
  // rejected authenticated state. Throw so no browser context is created
  // with malformed or incomplete scope data; the surrounding ``finally``
  // still closes a browser that was already started.
  process.exitCode = 2;
  throw new RunnerFailure(message);
}

async function readRunnerInput() {
  const chunks = [];
  let bytes = 0;
  for await (const chunk of process.stdin) {
    const buffer = Buffer.from(chunk);
    bytes += buffer.length;
    if (bytes > 1_500_000) fail("Runner input exceeds the safe bound.");
    chunks.push(buffer);
  }
  let parsed;
  try {
    parsed = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    fail("Runner input was malformed.");
  }
  if (!parsed || typeof parsed !== "object" || typeof parsed.url !== "string" || !parsed.url) {
    fail("Runner input was incomplete.");
  }
  if (!['A', 'AA', 'AAA'].includes(parsed.level)) fail("Unsupported WCAG level.");
  if (typeof parsed.user_agent !== "string" || !parsed.user_agent) fail("Runner input was incomplete.");
  if (!parsed.storage_state) {
    return { url: parsed.url, level: parsed.level, user_agent: parsed.user_agent };
  }
  const origins = Array.isArray(parsed.allowed_origins)
    ? parsed.allowed_origins.filter((origin) => typeof origin === "string")
    : [];
  const targetOrigins = Array.isArray(parsed.target_origins)
    ? parsed.target_origins.filter((origin) => typeof origin === "string")
    : [];
  if (!origins.length || !targetOrigins.length) {
    fail("Authenticated Alfa requires approved target and resource origins.");
  }
  if (!isLoopbackProxy(parsed.egress_proxy)) {
    fail("Authenticated Alfa requires the companion loopback egress proxy.");
  }
  return {
    url: parsed.url,
    level: parsed.level,
    user_agent: parsed.user_agent,
    storage_state: parsed.storage_state,
    allowed_origins: origins,
    target_origins: targetOrigins,
    egress_proxy: parsed.egress_proxy,
  };
}

function isLoopbackProxy(value) {
  try {
    const parsed = new URL(value);
    return (
      parsed.protocol === "http:" &&
      ["127.0.0.1", "[::1]", "::1"].includes(parsed.hostname) &&
      !parsed.username && !parsed.password && !parsed.search && !parsed.hash
    );
  } catch {
    return false;
  }
}

async function installReadOnlyRoute(context, allowedOrigins, targetOrigins) {
  const allowed = new Set(allowedOrigins.map((origin) => new URL(origin).origin));
  const targets = new Set(targetOrigins.map((origin) => new URL(origin).origin));
  // ``context.route`` does not reliably intercept WebSocket handshakes.
  // A connected WebSocket would be an authenticated long-lived channel even
  // though its initiating page is otherwise read-only, so deny it through
  // Playwright's dedicated WebSocket route before any page is created.
  await context.routeWebSocket("**/*", async (route) => {
    await route.close().catch(() => undefined);
  });
  await context.route("**/*", async (route) => {
    const request = route.request();
    if (!["GET", "HEAD"].includes(request.method())) {
      await route.abort("blockedbyclient");
      return;
    }
    if (BLOCKED_AUTH_RESOURCE_TYPES.has(request.resourceType())) {
      await route.abort("blockedbyclient");
      return;
    }
    try {
      if (request.resourceType() === "document") {
        await assertSafeAllowedDocument(request.url(), targets);
      } else {
        await assertSafeAllowedRequest(request.url(), allowed);
      }
    } catch {
      await route.abort("blockedbyclient");
      return;
    }
    // Do not use route.fetch()/fulfill() for authenticated resources:
    // Playwright retains APIResponse bodies until disposed, which would turn
    // every script/font/image into an unbounded in-process buffer. Native
    // continuation streams through Chromium. Each routed request is still
    // checked here, and the companion's loopback CONNECT proxy independently
    // validates every actual destination origin and freshly resolved IP.
    await route.continue();
  });
}

async function looksLikeAuthenticationPage(page) {
  try {
    const path = new URL(page.url()).pathname.toLowerCase();
    if (["/login", "/sign-in", "/signin", "/sso", "/mfa", "/verify"].some((segment) => path.includes(segment))) {
      return true;
    }
    const count = await page.locator(
      'input[type="password"], input[autocomplete="current-password"], input[autocomplete="one-time-code"], input[autocomplete="webauthn"]',
    ).count();
    return count > 0;
  } catch {
    // A failed marker inspection is not safe evidence of an authenticated
    // document. The Python companion will stop and require a manual handoff.
    return true;
  }
}

async function createEphemeralProfileDir() {
  await mkdir(PROFILE_ROOT, { recursive: true, mode: 0o700 });
  await chmod(PROFILE_ROOT, 0o700).catch(() => undefined);
  await clearStaleProfileDirs();
  const directory = await mkdtemp(join(PROFILE_ROOT, PROFILE_PREFIX));
  await chmod(directory, 0o700).catch(() => undefined);
  return directory;
}

async function clearStaleProfileDirs() {
  let entries;
  try {
    entries = await readdir(PROFILE_ROOT, { withFileTypes: true });
  } catch {
    return;
  }
  const now = Date.now();
  await Promise.all(entries.map(async (entry) => {
    if (!entry.isDirectory() || !entry.name.startsWith(PROFILE_PREFIX)) return;
    const candidate = join(PROFILE_ROOT, entry.name);
    try {
      const details = await stat(candidate);
      if (now - details.mtimeMs > STALE_PROFILE_MAX_AGE_MS) {
        await rm(candidate, { recursive: true, force: true, maxRetries: 1 });
      }
    } catch {}
  }));
}

async function assertSafeAllowedDocument(value, targets) {
  await assertSafeAllowedRequest(value, targets);
}

function installNoArtifactHandlers(context, primaryPage) {
  primaryPage.on("popup", (popup) => popup.close({ runBeforeUnload: false }).catch(() => undefined));
  primaryPage.on("download", (download) => download.cancel().catch(() => undefined));
  context.on("page", (page) => {
    if (page === primaryPage) return;
    page.close({ runBeforeUnload: false }).catch(() => undefined);
  });
}

async function assertSafeAllowedRequest(value, allowed) {
  const parsed = new URL(value);
  if (
    parsed.protocol !== "https:" ||
    parsed.username ||
    parsed.password ||
    !allowed.has(parsed.origin) ||
    hasSensitiveQuery(parsed.search)
  ) {
    throw new RunnerFailure("The requested origin is not approved.");
  }
  const addresses = await lookup(parsed.hostname, { all: true, verbatim: true });
  if (!addresses.length || addresses.some((answer) => !isPublicAddress(answer.address))) {
    throw new RunnerFailure("The requested host is not publicly routable.");
  }
}

function hasSensitiveQuery(search) {
  if (!search) return false;
  for (const part of search.slice(1).split(/[&;]/)) {
    const rawKey = part.split("=", 1)[0] || "";
    let key = rawKey;
    for (let i = 0; i < 3; i += 1) {
      try {
        const decoded = decodeURIComponent(key.replace(/\+/g, " "));
        if (decoded === key) break;
        key = decoded;
      } catch {
        return true;
      }
    }
    const normalized = key.replace(/[-_.\s]/g, "").toLowerCase();
    if (
      new Set([
        "accesstoken", "apikey", "assertion", "auth", "authorization", "clientsecret",
        "code", "credential", "idtoken", "jwt", "key", "oauthtoken", "password",
        "refresh_token", "relaystate", "samlrequest", "samlresponse", "secret", "session",
        "sessionid", "sid", "sig", "signature", "state", "ticket", "token",
        "xamzcredential", "xamzsecuritytoken", "xamzsignature", "xgoogsignature",
        "xgoogcredential", "xmssignature",
      ].map((item) => item.replace(/[-_.\s]/g, "")),
      ).has(normalized) ||
      /(?:token|secret|password|credential|assertion)$/.test(normalized)
    ) {
      return true;
    }
  }
  return false;
}

function isPublicAddress(address) {
  const version = isIP(address);
  if (version === 4) return isPublicIPv4(address);
  if (version === 6) return isPublicIPv6(address);
  return false;
}

function isPublicIPv4(address) {
  const octets = address.split(".").map(Number);
  if (octets.length !== 4 || octets.some((octet) => !Number.isInteger(octet) || octet < 0 || octet > 255)) {
    return false;
  }
  const [a, b, c] = octets;
  if (a === 0 || a === 10 || a === 127 || a >= 224) return false;
  if (a === 100 && b >= 64 && b <= 127) return false;
  if (a === 169 && b === 254) return false;
  if (a === 172 && b >= 16 && b <= 31) return false;
  if (a === 192 && (b === 168 || (b === 0 && c === 0) || (b === 0 && c === 2))) return false;
  if (a === 198 && (b === 18 || b === 19 || (b === 51 && c === 100))) return false;
  if (a === 203 && b === 0 && c === 113) return false;
  return true;
}

function isPublicIPv6(address) {
  const normalized = address.toLowerCase();
  if (normalized === "::" || normalized === "::1") return false;
  if (normalized.startsWith("::ffff:")) return isPublicIPv4(normalized.slice(7));
  if (
    normalized.startsWith("fc") ||
    normalized.startsWith("fd") ||
    normalized.startsWith("fe8") ||
    normalized.startsWith("fe9") ||
    normalized.startsWith("fea") ||
    normalized.startsWith("feb") ||
    normalized.startsWith("ff") ||
    normalized.startsWith("2001:db8:") ||
    normalized.startsWith("2002:") ||
    normalized.startsWith("64:ff9b:")
  ) {
    return false;
  }
  return true;
}
