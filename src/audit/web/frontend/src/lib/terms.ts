import type { AxeImpact, DetectionPipeline, FindingStatus, ReviewLane, ScanStatus } from "../api/types";

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

/**
 * What each status means, for the hover hint on its chip. A status is a
 * person's decision; Axcess checks none of them, so "Fixed" says so.
 */
export const STATUS_HELP: Record<FindingStatus, string> = {
  new: "No one has set a status for it in this report yet.",
  reviewing: "Someone is checking whether it is a real problem.",
  in_progress: "Someone confirmed it is a real problem, and a fix is planned or under way.",
  remediated: "Someone marked it as fixed. Axcess does not check this: scan again to see if it is still found.",
  accepted_risk: "A known problem that your team chose not to fix for now.",
  false_positive: "Someone checked it and found it is not a real problem (a false positive).",
};

/** The same statuses as choices, where the longer form helps the decision. */
export const STATUS_OPTION_LABEL: Record<FindingStatus, string> = {
  ...STATUS_LABEL,
  false_positive: "Not a problem (false positive)",
};

/**
 * The three types of issue, as the Issues table's "How sure" column names
 * them: how sure Axcess is that the issue is a real problem.
 *
 * "Mostly sure" and "Not sure" are opposites in short, common words, so the
 * two cannot be read as the same thing (SC 3.1.5 Reading Level, Level AAA).
 * Rejected: "Barrier" and "Needs review" (a column called "Type", jargon,
 * and no "who reviews"); "Likely problem" and "Possible problem" (both mean
 * "maybe", and readers could not tell them apart); "Fairly certain" and
 * "Pretty certain" (longer words, and "fairly" and "pretty" have other
 * meanings that trip up translation). Not "Very sure" or "Sure": a fixed
 * rule can still be wrong about a page, so each one is still checked on the
 * page (docs/glossary.md, "Zero false positive goal"), and "Very sure"
 * invites skipping that check. "For information", not
 * "Not a problem": that is already the false positive status above, and one
 * phrase names one thing (W3C COGA "Making Content Usable",
 * https://www.w3.org/TR/coga-usable/: use the same word for the same thing;
 * docs/plain-language.md). The full reasoning is in docs/plain-language.md,
 * "Why Mostly sure, Not sure, and For information".
 */
export const REVIEW_TYPE_LABEL: Record<ReviewLane, string> = {
  likely_barrier: "Mostly sure",
  expert_review: "Not sure",
  informational: "For information",
};

/**
 * An issue's impact rating, in the glossary's words ("Impact"), not axe's
 * raw lower-case values.
 */
export const IMPACT_LABEL: Record<AxeImpact, string> = {
  critical: "Critical",
  serious: "Serious",
  moderate: "Moderate",
  minor: "Minor",
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
