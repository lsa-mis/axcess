import type {
  AiInstallState,
  AiInstallStep,
  AiTierId,
  DetectionPipeline,
  FindingStatus,
  ReviewLane,
  ScanStatus,
  SuggestionAudience,
  SuggestionCheckOutcome,
  SuggestionErrorCode,
  SuggestionStatus,
} from "../api/types";

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
  bad_answer: "The AI model gave an answer Axcess could not use safely, so it is not shown. Try again.",
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
