import type {
  AiInstallState,
  AiInstallStep,
  AiTierId,
  AxeImpact,
  DetectionPipeline,
  ExportFormat,
  FindingStatus,
  LinkedFileCheck,
  LinkedFileReason,
  LinkedFileRefKind,
  LinkedFileStatus,
  LinkedFileType,
  ReviewDecision,
  ReviewLane,
  RuleCheck,
  ScanStatus,
  SuggestionAudience,
  SuggestionCheckOutcome,
  SuggestionErrorCode,
  SuggestionStatus,
} from "../api/types";
import { isDesktopApp } from "../hooks/useSwipeNavigation";

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
 * The Documents tab's three "How sure" values: how sure Axcess is that a
 * linked file (a PDF, Word, Excel or Google file) has accessibility
 * problems.
 *
 * The first two are the same words as the Issues table's (REVIEW_TYPE_LABEL)
 * because they mean the same thing: "Mostly sure" is a machine check that
 * proves a problem, "Not sure" needs a person. One word for one thing (W3C
 * COGA "Making Content Usable", https://www.w3.org/TR/coga-usable/,
 * paraphrased: use the same word for the same thing). The third differs on
 * purpose: Issues' "For information" is a result, and here Axcess has no
 * result at all, so the words say that. There is no "Accessible" value: a
 * machine check cannot prove a file is accessible (AGENTS.md, Interface
 * language rule 4).
 */
export const LINKED_FILE_STATUS_LABEL: Record<LinkedFileStatus, string> = {
  mostly_sure: "Mostly sure",
  not_sure: "Not sure",
  could_not_check: "Could not check",
};

/** What each value means, in one sentence: the hover hint and the page's key. */
export const LINKED_FILE_STATUS_HELP: Record<LinkedFileStatus, string> = {
  mostly_sure: "A machine check found a problem that makes the file hard or impossible to use with a screen reader.",
  not_sure:
    "The file passed the machine checks. A person must still check it: the reading order, the image descriptions (alt text) and the table headers.",
  could_not_check: "Axcess could not check the file. The row says why.",
};

/** A linked file's type: the plain name first, the file extension after. */
export const LINKED_FILE_TYPE_LABEL: Record<LinkedFileType, string> = {
  pdf: "PDF",
  docx: "Word (.docx)",
  doc: "Word, old format (.doc)",
  pptx: "PowerPoint (.pptx)",
  ppt: "PowerPoint, old format (.ppt)",
  xlsx: "Excel (.xlsx)",
  xls: "Excel, old format (.xls)",
  odt: "OpenDocument text (.odt)",
  odp: "OpenDocument slides (.odp)",
  ods: "OpenDocument spreadsheet (.ods)",
  rtf: "Rich Text Format (.rtf)",
  google_doc: "Google Docs",
  google_sheet: "Google Sheets",
  google_slides: "Google Slides",
  google_drive: "Google Drive file",
};

/**
 * Why a file could not be checked. Two groups read differently on purpose,
 * as the developer asked: "does not check this file type yet" (a later
 * version may) and "cannot check" (no machine check can read it). A
 * reason that names a server answer gets its status code added by
 * ``linkedFileReasonText``.
 */
export const LINKED_FILE_REASON_TEXT: Record<LinkedFileReason, string> = {
  type_not_checked_yet: "Axcess does not check this file type yet. Only PDF files are checked.",
  old_format:
    "Axcess cannot check this file type. Old Office files (.doc, .xls, .ppt) do not store the structure that a check needs.",
  google_file: "Axcess cannot check files kept in Google Docs, Sheets, Slides or Drive. It cannot download them.",
  broken_link: "Broken link: the file could not be downloaded.",
  http_error: "Broken link: the site answered with an error",
  password: "The file needs a password to open.",
  too_large: "The file is larger than 10 MB, the most Axcess downloads.",
  timed_out: "Downloading or checking the file took too long.",
  not_a_pdf: "The link did not lead to a PDF file. The site sent something else, such as a web page.",
  damaged: "Axcess could not read the file. It may be damaged.",
  robots: "The site asks scanners not to open this file (in its robots.txt file).",
  blocked: "The scan's settings say not to visit this address.",
  limit: "The scan reached its limit of 200 files to download.",
  not_checked: "The scan stopped before Axcess checked this file.",
};

/** The reason in words, with the server's status code where there is one. */
export function linkedFileReasonText(reason: LinkedFileReason, httpStatus: number | null): string {
  if (reason === "http_error") {
    return `${LINKED_FILE_REASON_TEXT.http_error}${httpStatus != null ? ` (HTTP ${httpStatus})` : ""}.`;
  }
  return LINKED_FILE_REASON_TEXT[reason];
}

/** A failed machine check, as the problem it causes for a reader. */
export const LINKED_FILE_CHECK_TEXT: Record<LinkedFileCheck, string> = {
  not_tagged: "Not tagged: a screen reader cannot tell its headings, lists and tables apart.",
  no_text: "No text a screen reader can read: the pages are pictures only, as in a scan.",
  blocks_assistive_tech: "Its security settings stop screen readers from reading it.",
  no_title: "No document title.",
  no_language: "No language set, so a screen reader may read it in the wrong voice.",
};

/** How a page shows a file other than by a plain link. A plain link needs no note. */
export const LINKED_FILE_REF_LABEL: Record<Exclude<LinkedFileRefKind, "link" | "revealed_link">, string> = {
  iframe: "Shown inside the page (in a frame)",
  object: "Shown inside the page (as an object)",
  embed: "Shown inside the page (embedded)",
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
  forms: "Form error check",
  markup: "Page code check",
  semantic: "AI review",
  image: "Image text check",
  protected_image: "Image text check",
};

/**
 * What a person decided about an element in the page inspector, the
 * "Checked by a person" choice. "none" is not checked yet, the starting
 * choice: a radio cannot be cleared, so it is also how a reviewer takes a
 * decision back. Which elements are repeats is the person's call.
 */
export const REVIEW_DECISION_LABEL: Record<ReviewDecision | "none", string> = {
  none: "Not checked yet",
  report: "Checked: a problem to report",
  repeat: "Checked: a repeat of one already reported",
};

export const REVIEW_DECISION_HELP: Record<ReviewDecision | "none", string> = {
  none: "",
  report: "You looked at it, and it is a real problem.",
  repeat:
    "A real problem, but the same as one you already reported, such as the same menu on another page.",
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
  its: "ITS technical review (Excel)",
  audit: "Written report (Markdown)",
  brief: "Fix brief for a coding agent (Markdown)",
  csv: "Occurrence list (CSV)",
  json: "All report data (JSON)",
};

/** One line under each Export panel file: what it is for. */
export const EXPORT_FORMAT_HINT: Record<ExportFormat, string> = {
  xlsx: "One row for each issue type, with how to fix it",
  its: "The University of Michigan Information and Technology Services (ITS) Accessibility Team's form, with only the elements checked as a problem to report",
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

/**
 * The limits when "Remove private details" is ticked, for every file. It
 * keeps each fact of the notice written into the files (AGENTS.md, Interface
 * language rule 4), including one added in PR #58 review: the files keep
 * element locators whole, so a locator that quotes a value from the page
 * still shows it. The fix brief is the exception, and the sentence says so:
 * it redacts inside locators and tells the coding agent when one is no
 * longer exact.
 */
export const REDACTION_LIMITS =
  "Removing private details is best effort. It can miss names and other private text, and it does not change text inside images, so screenshots are left out. Every file except the fix brief keeps element locators (CSS selectors) whole, so they still find the element, even when one quotes a value from the page. The links back to Axcess open the full report. Check each file before you share it.";

/**
 * What the fix brief leaves out, shown beside the note that the files cover
 * the whole report. The brief does not: it lists open issue types only,
 * stops at a limit, and shows a few places for each. No numbers here, so
 * the text cannot drift from the limits in `exports/fix_brief.py`; the
 * brief itself gives the exact counts ("What this brief covers").
 */
export const FIX_BRIEF_SCOPE_NOTE =
  "The fix brief is not the whole report. It lists open issue types only, most important first, stops at a limit, and shows a few places for each. It says what it left out.";

/** A scan's progress, for status badges. */
export const SCAN_STATUS_LABEL: Record<ScanStatus, string> = {
  running: "Scanning",
  completed: "Complete",
  failed: "Failed",
  interrupted: "Stopped",
};

/** The feature's one name, on its button and in its heading. */
export const AI_SUGGESTION = "AI suggestion";

/** Where an AI suggestion is in its queue, for its status line. */
export const SUGGESTION_STATUS_LABEL: Record<SuggestionStatus, string> = {
  queued: "Waiting to start",
  running: "Writing the fix",
  ready: "Ready",
  failed: "Could not write a suggestion",
  cancelled: "Stopped",
};

/** Who an AI suggestion is written for. */
export const SUGGESTION_AUDIENCE_LABEL: Record<SuggestionAudience, string> = {
  developer: "For developers",
  editor: "For content editors",
};

/**
 * What Axcess saw when it re-ran the one rule check on the suggested code.
 * A pass checks one rule only, so it never says the page now passes.
 */
export const SUGGESTION_CHECK_LABEL: Record<SuggestionCheckOutcome, string> = {
  passed: "The rule check passed on the suggested code",
  still_fails: "The rule check still fails on the suggested code",
  not_checked: "Axcess could not check this suggestion",
};

/** Two code choices: the smaller change is always first. */
export const SUGGESTION_OPTION_LABEL = {
  minimal: "Option 1: Smallest change",
  matches_pattern: "Option 2: Matches nearby code",
};

/** Desktop AI setup: what the download is doing now. */
export const AI_INSTALL_STEP_LABEL: Record<AiInstallStep, string> = {
  program: "Downloading the Ollama program",
  starting: "Starting Ollama",
  text_model: "Downloading the text model",
  vision_model: "Downloading the image model",
  finishing: "Finishing setup",
};

/** Desktop AI setup: where the download stands. */
export const AI_INSTALL_STATE_LABEL: Record<AiInstallState, string> = {
  idle: "Not set up",
  running: "Downloading",
  paused: "Paused",
  failed: "Stopped with a problem",
  done: "Ready",
};

/** Saved desktop AI choice, separate from whether models are ready. */
export const AI_FEATURE_STATE_LABEL = {
  on: "AI features are on",
  off: "AI features are off",
};

/** Desktop AI setup: the size of the AI models. */
export const AI_TIER_LABEL: Record<AiTierId, string> = {
  small: "Small",
  standard: "Standard",
  large: "Large",
};

/** Why a suggestion failed, in words that say what to do next. */
export const SUGGESTION_ERROR_LABEL: Record<SuggestionErrorCode, string> = {
  model_unavailable: "The local AI service (Ollama) is not running. Start it, then try again.",
  model_missing: "The AI model is not installed in Ollama. Install it with ollama pull, then try again.",
  timeout: "The AI model took too long to answer. Try again when the computer is less busy.",
  no_change: "The AI did not suggest a real change to the code, even when asked twice, so nothing is shown. A bigger AI model in Settings may do better. You can also fix it by hand with the rule guidance.",
  bad_answer: "The AI wrote an answer Axcess could not show safely, even when asked twice, so nothing is shown. A bigger AI model in Settings may do better. You can also fix it by hand with the rule guidance.",
  restarted: "Axcess restarted before the suggestion was finished. Try again.",
  occurrence_gone: "This occurrence is no longer in the report.",
  internal: "Something went wrong in Axcess. Try again.",
};

export const AI_RUNTIME_START_LABEL: Record<import("../api/types").AiRuntimeStartState, string> = {
  started: "AI service started. It is isolated and stays on this computer.",
  already_running: "AI service: isolated, local only.",
  model_missing: "The private AI program or models are missing. Choose a size and confirm its download below.",
  not_isolated: "AI was not started because Axcess could not keep it isolated.",
  system_ollama_not_managed: "This is your own Ollama. Axcess does not start, stop or isolate it. Choose a private download for isolated AI.",
  ai_off: "AI features are off. Turn them on before starting the service.",
  not_desktop: "Starting AI is available only in the Axcess desktop app.",
  busy: "Finish or stop current work before starting the AI service.",
};
export const AI_ISOLATION_REASON_LABEL: Record<string, string> = {
  sandbox_unavailable: "This computer cannot isolate the AI service. AI was not started. Saved results still work.",
  network_test_failed: "The isolation check could not prove that outside connections are blocked. AI was not started.",
  namespace_unreachable: "Axcess cannot reach the AI service inside its private network on this computer. AI was not started.",
  runtime_failed: "The isolated AI service could not start. Check the application log.",
  system_ollama_not_managed: "Your own Ollama is not isolated by Axcess. Axcess never starts or stops it.",
};

/**
 * What happens when someone opens a link to another website, for the
 * screen-reader note and visible text on every external link.
 *
 * In a browser the link opens a new tab. In the desktop app, the app
 * (desktop/src/main.cjs) blocks the new window and opens the address in
 * the person's default web browser, so "new tab" would be wrong there.
 * Rejected: keeping one wording everywhere, because it would describe
 * something that does not happen in the app. People need to hear where
 * a link takes them before they use it (WCAG 2.2 SC 3.2.5 Change on
 * Request, Level AAA). Text must also match what the code does (repo
 * plain-language rules), and one shared phrase keeps every link the same
 * (SC 3.2.4 Consistent Identification, Level AA).
 */
export const OPENS_NEW_WINDOW = isDesktopApp()
  ? "opens in your web browser"
  : "opens in a new tab";
