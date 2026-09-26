/**
 * User-facing names for features and issue categories, in one place.
 *
 * The API, the stored data and the code keep their stable internal keys
 * (`likely_barrier`, `click_through`, `dom_state_count`, …). What a reader
 * sees is looked up here, so the table, its filters, its help text and every
 * other screen use one word for one thing. The server mirrors these in
 * `src/audit/labels.py` for the exports and the method ledger; keep the two
 * in step.
 *
 * "Click-Through" is the one name for the feature that operates a page's
 * controls (menus, tabs, dialogs, disclosures) and re-checks what they
 * reveal. What it reaches is a "view opened by clicking": plain words anyone
 * can follow. Earlier copy said "DOM states", "interaction states" and
 * "Click-Through states"; those should not reach a reader.
 */
import type { FindingType, ReviewLane } from "../api/types";

export const CLICK_THROUGH = "Click-Through";
/** Page states reached by operating a control. Lower case, for use
 *  mid-sentence; headings and table columns use the `_LABEL` form. */
export const CLICK_THROUGH_STATES = "views opened by clicking";
export const CLICK_THROUGH_STATES_LABEL = "Views opened by clicking";

export function clickThroughStates(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? CLICK_THROUGH_STATE : CLICK_THROUGH_STATES}`;
}

/** Which family of checks produced an issue's evidence. Table order. */
export const FINDING_TYPES = ["wcag", "click_through", "alt_text"] as const satisfies readonly FindingType[];

export const FINDING_TYPE_LABELS: Record<FindingType, string> = {
  wcag: "WCAG",
  click_through: CLICK_THROUGH,
  alt_text: "Alt Text",
};

export const FINDING_TYPE_HELP: Record<FindingType, string> = {
  wcag:
    "Checked against WCAG rules in the page as it loaded: axe-core, Alfa, the browser probes, and the semantic checks.",
  click_through:
    "Found only after operating a control (a menu, tab, dialog, or disclosure). Reproduce it by using the control first.",
  alt_text:
    "Image evidence: text found in images and whether the alternative text says the same thing.",
};

export const isFindingType = (value: string): value is FindingType =>
  (FINDING_TYPES as readonly string[]).includes(value);

/** How much confidence an issue's evidence carries. Table order. */
export const REVIEW_LANES = ["likely_barrier", "expert_review", "informational"] as const satisfies readonly ReviewLane[];

export const REVIEW_LANE_LABELS: Record<ReviewLane, string> = {
  likely_barrier: "Barrier",
  expert_review: "Needs review",
  informational: "Informational",
};

export const REVIEW_LANE_HELP: Record<ReviewLane, string> = {
  likely_barrier:
    "A rule failed deterministically, so this is likely to block someone. Fix it, then rescan to confirm.",
  expert_review:
    "A lead from a browser probe, image analysis, or AI-assisted check. A person must confirm it before it is reported as a barrier.",
  informational:
    "Recorded for context, not a problem to fix, such as an image whose alternative text already matches.",
};

export const isReviewLane = (value: string): value is ReviewLane =>
  (REVIEW_LANES as readonly string[]).includes(value);

// ---------------------------------------------------------------------------
// Click-Through, additional forms. Mirrors `CLICK_THROUGH_STATE` in
// `src/audit/labels.py`.
// ---------------------------------------------------------------------------

/** One page state reached by operating a control (singular). */
export const CLICK_THROUGH_STATE = "view opened by clicking";
