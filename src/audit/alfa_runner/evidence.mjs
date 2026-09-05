/* Bounded, location-preserving projection of Alfa outcomes. Kept separate from
 * browser launch so the exact production projection is exercised by fixtures. */
import { createHash } from "node:crypto";
import { Outcome } from "@siteimprove/alfa-act";
import { Serializable } from "@siteimprove/alfa-json";
import { Criterion } from "@siteimprove/alfa-wcag";

export const MAX_FINDINGS = 200;
export const MAX_EVIDENCE_BYTES = 4_000;

export function diagnosticMessages(value) {
  const messages = [];
  function visit(item, depth = 0) {
    if (depth > 8 || messages.length >= 8 || item == null) return;
    if (Array.isArray(item)) { item.slice(0, 12).forEach((child) => visit(child, depth + 1)); return; }
    if (typeof item !== "object") return;
    if (typeof item.message === "string" && !messages.includes(item.message)) messages.push(item.message);
    // Traverse only diagnostic containers, never arbitrary target/page content.
    for (const key of ["diagnostic", "causes", "errors", "error", "expectations"]) visit(item[key], depth + 1);
  }
  visit(value);
  return messages.map((message) => truncate(message, 400));
}

export function boundedJson(value, maximum = MAX_EVIDENCE_BYTES) {
  if (!Number.isInteger(maximum) || maximum < 20) throw new Error("Evidence bound must be at least 20 bytes");
  let cut = false;
  function compact(item, depth = 0) {
    if (typeof item === "string") { if (item.length > 400) cut = true; return truncate(item, 400); }
    if (!item || typeof item !== "object") return item ?? null;
    if (depth >= 7) { cut = true; return null; }
    if (Array.isArray(item)) { if (item.length > 8) cut = true; return item.slice(0, 8).map((v) => compact(v, depth + 1)); }
    const entries = Object.entries(item).filter(([, v]) => v !== undefined);
    if (entries.length > 16) cut = true;
    return Object.fromEntries(entries.slice(0, 16).map(([key, v]) => [key, compact(v, depth + 1)]));
  }
  const result = compact(value);
  result.truncated = cut || Boolean(value.truncated);
  // Remove whole fields/items, never bytes from serialized JSON. Preserve the
  // diagnostic strings ahead of auxiliary color pairings and node metadata.
  for (const key of ["expectations", "rule", "diagnostic", "target"]) {
    if (Buffer.byteLength(JSON.stringify(result), "utf8") <= maximum) break;
    delete result[key];
    result.truncated = true;
  }
  while (Buffer.byteLength(JSON.stringify(result), "utf8") > maximum && result.diagnostics?.length) {
    result.diagnostics.pop();
    result.truncated = true;
  }
  if (Buffer.byteLength(JSON.stringify(result), "utf8") > maximum) return '{"truncated":true}';
  return JSON.stringify(result);
}

export function toFinding(outcome) {
  const rule = outcome.rule;
  const requirements = rule.toJSON().requirements || [];
  const criteria = requirements.filter((requirement) => requirement?.type === "criterion");
  const ruleCriteria = rule.requirements.filter(Criterion.isCriterion);
  const primary = criteria[0];
  // Low verbosity supplies composedNested XPath identity (including shadow and
  // frame boundaries) without recursively serializing the entire document.
  const outcomeJson = outcome.toJSON({ verbosity: Serializable.Verbosity.Low });
  const diagnostics = diagnosticMessages({ diagnostic: outcomeJson.diagnostic, expectations: outcomeJson.expectations });
  const targetState = { truncated: false };
  const target = summarizeTarget(outcomeJson.target, outcome.target, targetState);
  const targetHint = boundedTargetJson(target, targetState);
  const paths = targetPaths(outcomeJson.target);
  const identity = createHash("sha256").update(JSON.stringify(paths.length ? paths : outcomeJson.target)).digest("hex");
  const summary = diagnostics.join("; ") || outcome.toSARIF()?.message?.text || "Alfa requires expert review.";
  return {
    rule_id: rule.uri.split("/").filter(Boolean).pop() || rule.uri,
    rule_uri: rule.uri,
    outcome: Outcome.isFailed(outcome) ? "failed" : "cantTell",
    mode: outcome.mode,
    wcag_sc: primary?.chapter || null,
    wcag_scs: criteria.map((criterion) => String(criterion.chapter || "")).filter(Boolean),
    wcag_level: ruleCriteria[0] ? criterionLevel(ruleCriteria[0]) : null,
    help: primary ? `WCAG ${primary.chapter}: ${primary.title || "Alfa ACT rule"}` : "Alfa ACT rule requires expert review",
    failure_summary: truncate(summary, 2_000),
    target_hint: targetHint,
    target_identity: identity,
    evidence: boundedJson({
      diagnostics, diagnostic: outcomeJson.diagnostic, expectations: outcomeJson.expectations,
      mode: outcome.mode, outcome: outcome.outcome, target_identity: identity,
      rule: { uri: rule.uri, requirements: criteria }, target, truncated: targetState.truncated,
    }),
  };
}

export function collectOutcomes(outcomes) {
  const counts = { failed: 0, cantTell: 0, passed: 0, inapplicable: 0 };
  const failed = [], review = [];
  for (const outcome of outcomes) {
    if (Outcome.isFailed(outcome)) { counts.failed++; if (failed.length < MAX_FINDINGS) failed.push(outcome); }
    else if (Outcome.isCantTell(outcome)) { counts.cantTell++; if (review.length < MAX_FINDINGS) review.push(outcome); }
    else if (Outcome.isPassed(outcome)) counts.passed++;
    else counts.inapplicable++;
  }
  const findings = [...failed, ...review].slice(0, MAX_FINDINGS).map(toFinding);
  return { outcome_counts: counts, findings, findings_truncated: counts.failed + counts.cantTell > findings.length };
}

function targetPaths(target) {
  if (Array.isArray(target)) return target.flatMap(targetPaths);
  return target?.path ? [target.path] : [];
}

function summarizeTarget(target, live, state) {
  function text(value, maximum) {
    if (String(value || "").length > maximum) state.truncated = true;
    return truncate(value, maximum);
  }
  if (Array.isArray(target)) {
    if (target.length > 3) state.truncated = true;
    return target.slice(0, 3).map((item, index) => summarizeTarget(item, live?.[index], state));
  }
  if (!target || typeof target !== "object") return text(target, 160);
  const result = { type: target.type || "node" };
  for (const key of ["path", "name", "data", "value"]) {
    const value = target[key] ?? live?.[key];
    if (value) result[key] = text(value, key === "path" ? 400 : 160);
  }
  const attributes = target.attributes ?? (live?.attributes ? [...live.attributes] : []);
  const selected = attributes.filter((a) => ["id", "class", "name", "role", "type", "href", "src"].includes(a?.name));
  if (selected.length > 2) state.truncated = true;
  if (selected.length) result.attributes = selected.slice(0, 2).map((a) => ({ name: a.name, value: text(a.value, 120) }));
  return result;
}

function boundedTargetJson(target, state) {
  while (Buffer.byteLength(JSON.stringify(target), "utf8") > 3_000) {
    state.truncated = true;
    if (Array.isArray(target)) { target.pop(); continue; }
    if (target.attributes?.length) { target.attributes.pop(); continue; }
    const key = ["data", "value", "name", "path"].find((key) => typeof target[key] === "string" && target[key].length > 8);
    if (!key) return '{"type":"node","truncated":true}';
    target[key] = truncate(target[key], Math.floor(target[key].length / 2));
  }
  return JSON.stringify(target);
}

function criterionLevel(requirement) {
  let found = null;
  requirement.level?.some((value, versions) => { if ([...versions].includes("2.2")) found = value; });
  return found;
}
function truncate(value, maximum) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= maximum ? text : `${text.slice(0, maximum - 1)}…`;
}
