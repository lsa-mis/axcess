import { AlertTriangle } from "lucide-react";
import type { AxeImpact, Severity } from "../api/types";
import { IMPACT_LABEL } from "../lib/terms";

/**
 * An axe impact rating as a small chip, on the Rule check issues views.
 *
 * axe's four levels map to the app's severity colours (critical -> critical,
 * serious -> major, moderate -> minor, minor -> info), each as its pair: the
 * dark text colour on its own pale background, as every other severity chip
 * in the app. Two copies of this chip, in A11y.tsx and A11yByRule.tsx, used
 * white text on the pale background, 1.16:1 for "serious" (SC 1.4.3 Contrast
 * (Minimum), Level AA; found by the October 2026 AAA audit). One component
 * now, so the two views cannot drift apart again. The dark-on-pale pairs
 * clear 7:1 in both themes (SC 1.4.6 Contrast (Enhanced), Level AAA). The
 * critical chip also carries an icon, so its weight is not shown by colour
 * alone (SC 1.4.1 Use of Color, Level A). The words are the shared labels
 * (IMPACT_LABEL in lib/terms.ts), never axe's raw values.
 */
const TONE: Record<AxeImpact, Severity> = {
  critical: "critical",
  serious: "major",
  moderate: "minor",
  minor: "info",
};

const CLASSES: Record<Severity, string> = {
  critical: "bg-sev-critical-bg text-sev-critical",
  major: "bg-sev-major-bg text-sev-major",
  minor: "bg-sev-minor-bg text-sev-minor",
  info: "bg-sev-info-bg text-sev-info",
};

export default function ImpactChip({ value }: { value: AxeImpact }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-xs px-1.5 py-0.5 text-2xs font-semibold ${CLASSES[TONE[value]]}`}
    >
      {value === "critical" && <AlertTriangle className="h-3 w-3" aria-hidden />}
      {IMPACT_LABEL[value]}
    </span>
  );
}
