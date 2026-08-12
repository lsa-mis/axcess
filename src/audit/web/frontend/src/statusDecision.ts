import type { FindingStatus } from "./api/types";

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
    `Document why ${subject} should be marked ${status.replace(/_/g, " ")}. ` +
      "Include the evidence reviewed and the basis for the decision.",
  );
  if (response === null) return null;
  const rationale = response.trim();
  if (!rationale) {
    window.alert("A decision rationale is required. No status was changed.");
    return null;
  }
  return rationale;
}
