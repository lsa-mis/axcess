import type { DetectionPipeline, FindingStatus, ReviewLane, ScanStatus } from "../api/types";

/**
 * The words the interface uses for shared values, in one place.
 *
 * Every screen that shows a status, an issue type, or a check reads its
 * label from here, so one thing always has one name (W3C COGA: consistent
 * terms). The stored values never change; only what people see and hear.
 * See docs/plain-language.md for the full list of terms.
 */

/** An occurrence's review status, as a short label for chips and tables. */
export const STATUS_LABEL: Record<FindingStatus, string> = {
  new: "New",
  reviewing: "Reviewing",
  in_progress: "In progress",
  remediated: "Fixed",
  accepted_risk: "Accepted risk",
  false_positive: "Not a problem",
};

/** The same statuses as choices, where the longer form helps the decision. */
export const STATUS_OPTION_LABEL: Record<FindingStatus, string> = {
  ...STATUS_LABEL,
  false_positive: "Not a problem (false positive)",
};

/** The three types of issue, as the Issues table's "Type" column names them. */
export const REVIEW_TYPE_LABEL: Record<ReviewLane, string> = {
  likely_barrier: "Barrier",
  expert_review: "Needs review",
  informational: "Informational",
};

/** Each check by its interface name, with the tool in parentheses where it helps. */
export const CHECK_LABEL: Record<DetectionPipeline, string> = {
  axe: "Rule check (axe)",
  alfa: "Rule check (Alfa)",
  keyboard: "Keyboard check",
  responsive: "Zoom and layout check",
  focus: "Focus check",
  visual: "Motion and reading-order check",
  semantic: "AI review",
  image: "Image text check",
  protected_image: "Image text check",
};

/** A scan's progress, for status badges. */
export const SCAN_STATUS_LABEL: Record<ScanStatus, string> = {
  running: "Scanning",
  completed: "Complete",
  failed: "Failed",
  interrupted: "Stopped",
};
