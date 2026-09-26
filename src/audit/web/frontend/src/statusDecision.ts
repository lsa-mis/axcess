import type { FindingStatus } from "./api/types";
import { STATUS_LABEL } from "./lib/terms";

export const RATIONALE_REQUIRED_STATUSES = new Set<FindingStatus>([
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
]);

/**
 * Compatibility prompt for specialized evidence drill-downs.
 *
 * The expert-first Review queue uses a full inline rationale field. Older
 * drill-downs still need a bounded way to satisfy the same audit-history
 * contract without silently failing their existing status controls.
 */
export function requestStatusRationale(
  status: FindingStatus,
  subject: string,
): string | null {
  if (!RATIONALE_REQUIRED_STATUSES.has(status)) return "";
  const response = window.prompt(
    `Explain why ${subject} should be marked “${STATUS_LABEL[status]}”. ` +
      "Say what evidence you looked at and why you decided this.",
  );
  if (response === null) return null;
  const rationale = response.trim();
  if (!rationale) {
    window.alert("You need to give a reason. The status was not changed.");
    return null;
  }
  return rationale;
}
