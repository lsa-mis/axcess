/*
 * The Alfa rules Axcess evaluates, shared by the one-page runner
 * (runner.mjs, its own browser) and the scan-long worker (worker.mjs,
 * snapshots taken in the crawler's own tab), so both select exactly the
 * same rules for one level and WCAG version.
 */

import rules from "@siteimprove/alfa-rules";
import { Criterion, Conformance } from "@siteimprove/alfa-wcag";
import { Refinement } from "@siteimprove/alfa-refinement";

/**
 * Alfa's conformance predicates default to the current Recommendation
 * (2.2); pass the scan's chosen version so a WCAG 2.1 scan selects only the
 * rules whose criteria 2.1 requires at this level.
 */
export function selectRules(level, version) {
  const conformance =
    level === "A"
      ? Conformance.isA(version)
      : level === "AAA"
        ? Conformance.isAAA(version)
        : Conformance.isAA(version);
  return rules.filter((rule) =>
    rule.hasRequirement(Refinement.and(Criterion.isCriterion, conformance)),
  );
}
