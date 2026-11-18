import type {
  AiInstallState,
  AiInstallStep,
  AiTierId,
  AltVerdict,
  AltVerdictSource,
  AxeImpact,
  CheckMethod,
  DetectionPipeline,
  ExportFormat,
  FindingStatus,
  FoundLayer,
  ImageGroup,
  LinkedFileCheck,
  LinkedFileReason,
  LinkedFileRefKind,
  LinkedFileStatus,
  LinkedFileType,
  ReviewDecision,
  ReviewLane,
  RuleCheck,
  ScanEndReason,
  ScanStatus,
  StudyCheck,
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
 *
 * "Measured" (2026-11-10) is the level between Mostly sure and Not sure: a
 * browser check measured the page and no AI model judged it. The word says
 * what happened, not how likely the problem is, so it cannot be confused
 * with the two "sure" words. Rejected: "Likely", which the pair "Likely
 * problem" / "Possible problem" above already showed readers cannot rank
 * against "Mostly sure"; and "Sure" for the rule checks with "Mostly sure"
 * here, which claims more than a rule check can show (the developer chose
 * to keep "Mostly sure" on top). A Measured row still says "check before
 * you report" wherever it is shown (REVIEW_LANE_HELP in labels.ts).
 */
export const REVIEW_TYPE_LABEL: Record<ReviewLane, string> = {
  likely_barrier: "Mostly sure",
  measured: "Measured",
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

/**
 * Each value finished as a sentence about the file, for the summary numbers
 * on the Documents tab, where the value stands without its column's
 * question ("Accessibility problems?"): "Mostly sure" / "it has
 * accessibility problems". Each phrase fits its value's grammar, so the
 * pair reads as one plain statement.
 */
export const LINKED_FILE_STATUS_NOTE: Record<LinkedFileStatus, string> = {
  mostly_sure: "it has accessibility problems",
  not_sure: "if it has accessibility problems",
  could_not_check: "for accessibility problems",
};

/** What each value means, in one sentence: the hover hint and the page's key. */
export const LINKED_FILE_STATUS_HELP: Record<LinkedFileStatus, string> = {
  mostly_sure: "A machine check found a problem that makes the file hard or impossible to use with a screen reader.",
  not_sure:
    "The file passed the machine checks. A person must still check it: the reading order, the image descriptions (alt text) and the table headers.",
  could_not_check: "Axcess could not check the file. The row says why.",
};

/** The Documents tab's Type filter groups: one per program, every format of it together. */
export type LinkedFileKind = "pdf" | "word" | "excel" | "powerpoint" | "opendocument" | "rtf" | "google";

/**
 * Each Type filter group's name. The program's plain name, without the
 * extensions the table's Type column adds (a filter for "Word" takes both
 * .docx and .doc). Google's four kinds of file are one group: Axcess cannot
 * check any of them, for the same reason.
 */
export const LINKED_FILE_KIND_LABEL: Record<LinkedFileKind, string> = {
  pdf: "PDF",
  word: "Word",
  excel: "Excel",
  powerpoint: "PowerPoint",
  opendocument: "OpenDocument",
  rtf: "Rich Text Format (RTF)",
  google: "Google Docs, Sheets, Slides and Drive",
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

/**
 * The five machine checks Axcess runs on every PDF it can open, most
 * serious first: the order the report ranks them in (SEVERE_CHECKS in
 * audit/linked_files/formats.py) and the order the server returns a file's
 * failed checks in (ALL_CHECKS in pdf_check.py). Every check runs on every
 * PDF Axcess opens, so a check a file did not fail found no problem.
 */
export const LINKED_FILE_CHECKS: readonly LinkedFileCheck[] = [
  "not_tagged",
  "no_text",
  "blocks_assistive_tech",
  "no_title",
  "no_language",
];

/**
 * A failed check, as a short name for the Documents table's "What Axcess
 * found" column: a few words, so a column of hundreds of files can be
 * scanned. Why each one matters is on the document's own page
 * (LINKED_FILE_CHECK_WHY). Until 2026-11-14 the cell held name and reason
 * in one sentence ("Not tagged: a screen reader cannot tell…"), which was
 * hard to scan in a narrow column (the developer's choice).
 */
export const LINKED_FILE_CHECK_PROBLEM: Record<LinkedFileCheck, string> = {
  not_tagged: "Not tagged",
  no_text: "No text a screen reader can read",
  blocks_assistive_tech: "Security settings block screen readers",
  no_title: "No document title",
  no_language: "No language set",
};

/** What each check looks at, for the "Check" column on a document's page. */
export const LINKED_FILE_CHECK_NAME: Record<LinkedFileCheck, string> = {
  not_tagged: "Tags",
  no_text: "Text a screen reader can read",
  blocks_assistive_tech: "Security settings",
  no_title: "Document title",
  no_language: "Language",
};

/** Why each check matters to a reader, in one sentence, for a document's page. */
export const LINKED_FILE_CHECK_WHY: Record<LinkedFileCheck, string> = {
  not_tagged: "Tags mark the headings, lists and tables, so a screen reader can tell them apart.",
  no_text:
    "A file whose pages are only pictures, as in a scan, has no text a screen reader can read. Axcess looks at the first 50 pages.",
  blocks_assistive_tech: "Some security settings stop screen readers from reading the file.",
  no_title: "A title tells people which file they have open.",
  no_language: "The language tells a screen reader which voice to read the file in.",
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

/**
 * How a scan ended, said as what happened to its coverage, for the report's
 * "Pages visited" line and "How this scan ran". This replaces calling a
 * stopped scan a "partial report": a scan stopped after 100 pages covers more
 * than one that completed at a 10-page limit, so the words say what the scan
 * did, and the numbers beside them say how far it got.
 *
 * "Stopped" cannot say who stopped it: the status is the same when someone
 * pressed Stop and when Axcess closed while the scan ran, so the words do not
 * claim either.
 */
export const SCAN_END_LABEL: Record<ScanEndReason, string> = {
  running: "Still scanning",
  all_found: "Visited every page it found",
  page_limit: "Stopped at its page limit",
  stopped: "Stopped before the scan finished",
  failed: "Failed before the scan finished",
};

/**
 * Whether a scan has a report to open: it completed, or it ended with pages
 * saved, however it ended (a running scan's stored page count stays 0 until
 * it ends). The server uses the same rule (sites.py, comparison.py).
 */
export function isReport(scan: { status: ScanStatus; page_count: number }): boolean {
  return scan.status === "completed" || scan.page_count > 0;
}

/** A scan's progress, for status badges. */
export const SCAN_STATUS_LABEL: Record<ScanStatus, string> = {
  running: "Scanning",
  completed: "Complete",
  failed: "Failed",
  interrupted: "Stopped",
};

/**
 * The Images tab's groups (routes/Images.tsx). Each is a question asked of
 * the report's images, so an image can be in two: "Images with text" and
 * one of the other two.
 */
export const IMAGE_GROUP_LABEL: Record<ImageGroup, string> = {
  with_text: "Images with text",
  missing_alt: "Images without alt text",
  with_alt: "Images with alt text",
};

/**
 * One verdict on an image's alt text (the text a screen reader reads for
 * an image). "Needs alt text" and "Needs better alt text" are two verdicts,
 * not one (the developer's call, 2026-11-13): an image with no alt text has
 * nothing to improve, it needs alt text written. "Needs a person to check",
 * not "Adequate": the text match cannot judge an image with no text in it, and
 * a word that sounds like a pass would claim a check that did not run. It
 * was "Not checked yet" until 2026-11-16, when the developer renamed it to
 * say who acts: most of a report's images land here, and "not checked yet"
 * read as Axcess still working on them. The new words also part it from the
 * "Checked by a person" value "Not checked yet" (REVIEW_DECISION_LABEL),
 * which is about an occurrence, not an image.
 * Rejected: "Bad alt text", which blames, and says less than "needs better".
 */
export const ALT_VERDICT_LABEL: Record<AltVerdict, string> = {
  needs_alt: "Needs alt text",
  needs_better: "Needs better alt text",
  not_checked: "Needs a person to check",
  good: "Good alt text",
};

/**
 * The same verdicts under a count of more than one image, as the Images
 * tab's numbers show them ("41 / Need alt text"): the verb agrees with the
 * number. One image takes ``ALT_VERDICT_LABEL``.
 */
export const ALT_VERDICT_COUNT_LABEL: Record<AltVerdict, string> = {
  needs_alt: "Need alt text",
  needs_better: "Need better alt text",
  not_checked: "Need a person to check",
  good: "Good alt text",
};

/** What decided a verdict, said plainly, for the line under the verdict. */
export const ALT_VERDICT_SOURCE_LABEL: Record<AltVerdictSource, string> = {
  page_code: "From the page code",
  text_match: "Compared with the text in the image",
  local_model: "Local AI model: check before you rely on it",
};

/**
 * How Axcess checks a WCAG criterion (Coverage page), said as what it means
 * for the person testing. The technical name follows in CHECK_METHOD_TECH, in
 * smaller text, for developers (docs/plain-language.md rule 3).
 */
export const CHECK_METHOD_LABEL: Record<CheckMethod, string> = {
  automated: "Axcess checks",
  partial: "Axcess partly checks",
  "ai-assisted": "AI gives hints",
  manual: "You check",
  not_needed: "No longer needed",
};

export const CHECK_METHOD_TECH: Record<CheckMethod, string> = {
  automated: "Automated",
  partial: "Partly automated",
  "ai-assisted": "AI-assisted",
  manual: "Manual only",
  not_needed: "4.1.1 Parsing",
};

export const CHECK_METHOD_BLURB: Record<CheckMethod, string> = {
  // Not "a full test": each of these still has a part only a person can
  // judge (a title's meaning, nothing lost at 200% zoom), shown in the
  // criterion's "You check" line (AGENTS.md, Interface language rule 4).
  automated: "Tests it on every page. You still confirm the result.",
  partial: "Finds some problems. You test the rest.",
  "ai-assisted": "Points to possible problems. You decide.",
  // "No proven check", not "can't test": a trial check may run but not count
  // yet (3.3.1's form error check).
  manual: "No proven check yet. You test these.",
  not_needed: "Removed in WCAG 2.2. Today's HTML always meets it.",
};

/** Where an occurrence came from, for the Coverage page's count by check. */
export const FOUND_LAYER_LABEL: Record<FoundLayer, string> = {
  axe_loaded: "Rule check (axe), page as loaded",
  axe_click_through: "Rule check (axe), after Click-Through",
  alfa: "Rule check (Alfa)",
  probes: "Browser checks: keyboard, zoom, focus, motion, forms and page code",
  image: "Image text check",
  semantic: "AI review",
};

/** The checks a study row credits beyond the rule check (Coverage page). */
export const STUDY_CHECK_LABEL: Record<StudyCheck, string> = {
  click_through: "Click-Through",
  image: CHECK_LABEL.image,
  focus: CHECK_LABEL.focus,
  keyboard: CHECK_LABEL.keyboard,
  visual: CHECK_LABEL.visual,
  semantic: CHECK_LABEL.semantic,
  responsive: CHECK_LABEL.responsive,
};

/**
 * axe-core's own kinds of problem (its ``cat.*`` rule tags), in plain words.
 * An unknown kind falls back to "Other" where it is read.
 */
export const AXE_CATEGORY_LABEL: Record<string, string> = {
  color: "Colour and contrast",
  "name-role-value": "Names, roles and values",
  aria: "ARIA attributes and roles",
  forms: "Forms",
  "text-alternatives": "Text alternatives",
  structure: "Page structure",
  semantics: "Headings and landmarks",
  keyboard: "Keyboard",
  language: "Language",
  tables: "Tables",
  parsing: "Page code errors",
  "time-and-media": "Time and media",
  "sensory-and-visual-cues": "Size, zoom and visual cues",
  other: "Other",
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
  program: "Downloading the AI program",
  starting: "Starting the private AI service",
  model: "Downloading the AI model",
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

/**
 * Desktop AI: the one state a person sees. It combines three facts that
 * used to be shown one by one (the on/off choice, whether the models are
 * downloaded, whether the AI service runs), which made people work out for
 * themselves which button could do anything (developer, 2026-11-18).
 */
export type AiStateKind = "not_set_up" | "off" | "starting" | "on" | "stopped";
export const AI_STATE_LABEL: Record<AiStateKind, string> = {
  not_set_up: "AI is not set up",
  off: "AI is off",
  starting: "AI is starting",
  on: "AI is on",
  stopped: "AI has stopped",
};

/** Desktop AI setup: the size of the AI models. */
export const AI_TIER_LABEL: Record<AiTierId, string> = {
  small: "Small",
  standard: "Standard",
  large: "Large",
  // No longer offered (2026-11-18); kept so a setup saved under it is named.
  extra_large: "Extra large",
};
/**
 * What each size is like, said the same way for each: speed first, then
 * answers. From the real-page trials in docs/internal/model-trials-2026-11.md
 * on this project's 16 GB test computer, without a graphics card: Small
 * (Bonsai 2 4B) took 26 to 95 s an answer, Standard (Bonsai 2 9B) 40 to 163 s,
 * and Standard wrote more usable fixes (5 of 10 against 3). Large (27B) was
 * not timed, so its line says only what is certain: it is the biggest model
 * (three times Standard) and the slowest. Update these with the trials.
 */
export const AI_TIER_DESCRIPTION: Record<AiTierId, string> = {
  small: "Fastest, but fewer usable answers than Standard.",
  standard: "Better answers than Small in our tests. Takes about 1.5 times as long to answer.",
  large: "The biggest model, three times the size of Standard, and the slowest.",
  extra_large: "",
};
/** Desktop AI setup: a GGUF file the person chose instead of a size. */
export const AI_MY_MODEL_LABEL = "Your own model";

/** Why a suggestion failed, in words that say what to do next. */
export const SUGGESTION_ERROR_LABEL: Record<SuggestionErrorCode, string> = {
  model_unavailable: "The AI service on this computer was not running. Start it, then try again.",
  model_missing: "The AI model was not installed. Install it, then try again.",
  // A cloud model, or one Ollama's model list cannot confirm is on this
  // computer. Says nothing was sent, because that is the privacy fact.
  model_not_local:
    "The AI model may run off this computer, so Axcess sent nothing. Choose a model installed on this computer in Settings.",
  timeout: "The AI model took too long to answer. Try again when the computer is less busy.",
  no_change: "The AI did not suggest a real change to the code, even when asked twice, so nothing is shown. A bigger AI model in Settings may do better. You can also fix it by hand with the rule guidance.",
  bad_answer: "The AI wrote an answer Axcess could not show safely, even when asked twice, so nothing is shown. A bigger AI model in Settings may do better. You can also fix it by hand with the rule guidance.",
  restarted: "Axcess restarted before the suggestion was finished. Try again.",
  occurrence_gone: "This occurrence is no longer in the report.",
  internal: "Something went wrong in Axcess. Try again.",
};

export const AI_RUNTIME_START_LABEL: Record<import("../api/types").AiRuntimeStartState, string> = {
  started: "AI service started. It is isolated and stays on this computer.",
  already_running: "AI service is running. It is isolated and stays on this computer.",
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
  not_enough_memory: "The AI models would not fit in the memory that is free now, so AI was not started. Close other programs and try again, or choose a smaller size.",
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
