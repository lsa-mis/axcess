// Writes src/audit/rules/axe_rules.json from the axe-core bundle Axcess ships
// (src/audit/web/static/axe.min.js), so rule counts and rule kinds on the
// Coverage page match the rules a scan really runs. Run it again whenever the
// bundle changes:  node scripts/build_axe_rule_catalog.mjs
import { createRequire } from "node:module";
import { writeFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const axe = require("../src/audit/web/static/axe.min.js");

const criteriaOf = (tags) =>
  tags
    .filter((t) => /^wcag\d{3,4}$/.test(t))
    .map((t) => `${t[4]}.${t[5]}.${t.slice(6)}`);

const rules = axe
  .getRules()
  .map((r) => ({
    id: r.ruleId,
    help: r.help,
    description: r.description,
    help_url: r.helpUrl.split("?")[0],
    category: (r.tags.find((t) => t.startsWith("cat.")) || "cat.other").slice(4),
    criteria: criteriaOf(r.tags),
    tags: r.tags.filter((t) => /^(wcag2a|wcag2aa|wcag2aaa|wcag21a|wcag21aa|wcag22a|wcag22aa|best-practice|experimental|deprecated)$/.test(t)),
  }))
  .sort((a, b) => a.id.localeCompare(b.id));

writeFileSync(
  new URL("../src/audit/rules/axe_rules.json", import.meta.url),
  JSON.stringify({ axe_version: axe.version, rules }, null, 1) + "\n",
);
console.log(`axe-core ${axe.version}: ${rules.length} rules`);
