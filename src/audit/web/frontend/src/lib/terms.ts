import type {
  AxeImpact,
  DetectionPipeline,
  ExportFormat,
  FindingStatus,
  ReviewLane,
  RuleCheck,
  ScanStatus,
} from "../api/types";

/**
 * The words the interface uses for shared values, in one place.
 *
 * Every screen that shows a status, a "How sure" value, or a check reads its
 * label from here, so one thing always has one name (W3C COGA: consistent
 * terms). The stored values never change; only what people see and hear.
 * See docs/plain-language.md for the full list of terms.
 */

/** An occurrence's review status (one place on a page), as a short label for chips and tables. */
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
 * The three "How sure" values, as the Issues table's "How sure" column names
 * them: how sure Axcess is that an issue type is a real problem. (They were
 * once called the three types of issue; "type" is not used for them now.)
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
 * An issue type's impact rating, in the glossary's words ("Impact"), not axe's
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

/**
 * A rule check by its tool's name alone, for a column already headed "Rule
 * check" (Reports), where "Rule check (axe)" would say "rule check" twice.
 * Elsewhere the full name in CHECK_LABEL is used.
 */
export const RULE_CHECK_TOOL: Record<RuleCheck, string> = {
  axe: "axe",
  alfa: "Alfa",
};

/** The rule checks a scan ran, in words: "axe", "axe and Alfa", "None". */
export function ruleChecksText(checks: readonly RuleCheck[]): string {
  return checks.length === 0 ? "None" : checks.map((check) => RULE_CHECK_TOOL[check]).join(" and ");
}

/**
 * The Export panel's files, by name. Each name says what the file holds and,
 * in parentheses, its format, so two Markdown files cannot be mistaken for
 * each other. The workbook's index has one row per issue type (one per Issues
 * table row); the CSV has one row per occurrence (one place). The workbook's
 * label changed on 2026-10-26 with the terms; the CSV was "Issue list (CSV)"
 * from then until 2026-10-28, when "occurrence" came back. See
 * docs/plain-language.md, "Why "occurrence" and "issue type"".
 */
export const EXPORT_FORMAT_LABEL: Record<ExportFormat, string> = {
  xlsx: "Issue types with fixes (Excel)",
  audit: "Written report (Markdown)",
  brief: "Fix brief for a coding agent (Markdown)",
  csv: "Occurrence list (CSV)",
  json: "All report data (JSON)",
};

/** One line under each Export panel file: what it is for. */
export const EXPORT_FORMAT_HINT: Record<ExportFormat, string> = {
  xlsx: "One row for each issue type, with how to fix it",
  audit: "The whole report as readable text",
  brief:
    "Open issue types with where and how to fix them, for Claude Code or another coding agent. Always removes likely private details, as best effort.",
  csv: "One row for each occurrence: one place on one page",
  json: "Every detail the scan saved, for developers",
};

/**
 * The Export panel's one-click copy of the fix brief: the button, and what
 * it says once the brief is on the clipboard. A verb and an object, so the
 * button says what it copies (docs/plain-language.md rule 8).
 */
export const COPY_FIX_BRIEF_LABEL = "Copy fix brief";
export const COPY_FIX_BRIEF_HINT =
  "Puts the same Markdown on your clipboard, to paste into Claude Code or another coding agent.";
export const COPY_FIX_BRIEF_DONE = "Copied the fix brief. Paste it into your coding agent.";

/**
 * The fix brief's redaction limits, shown in the Export panel whether or not
 * "Remove private details" is ticked, because the brief is always redacted
 * and is made to leave Axcess. It says "best effort" and keeps every limit
 * that applies to the brief (AGENTS.md, Interface language rule 4): what
 * redaction can miss, and that its links open the full report. The brief has
 * no screenshots, so the image limit of the other files does not apply.
 * Never "always removed": the redactor matches patterns and cannot know a
 * name (PR #60 review).
 */
export const FIX_BRIEF_REDACTION_LIMITS =
  "The fix brief is always a redacted copy. Removing private details is best effort: it can miss names and other private text, and the brief's links back to Axcess open the full report. Check the brief before you share it or paste it into a coding agent.";

/** A scan's progress, for status badges. */
export const SCAN_STATUS_LABEL: Record<ScanStatus, string> = {
  running: "Scanning",
  completed: "Complete",
  failed: "Failed",
  interrupted: "Stopped",
};
