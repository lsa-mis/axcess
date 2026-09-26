/**
 * User-facing names for features and issue categories, in one place.
 *
 * The API, the stored data and the code keep their stable internal keys
 * (`likely_barrier`, `click_through`, `dom_state_count`, …). What a reader
 * sees is looked up here, so the table, its filters, its help text and every
 * other screen use one word for one thing. The words follow the terms table
 * in docs/plain-language.md; the issue types come from `terms.ts`, which is
 * the one source for them. The server mirrors these in `src/audit/labels.py`
 * for the exports and the method ledger; keep the two in step.
 *
 * "Click-Through" is the one name for the feature that operates a page's
 * controls (menus, tabs, dialogs, disclosures) and re-checks what they
 * reveal. What it reaches is a "page state opened by clicking": the plain
 * term for how a page looked at one moment ("page state"), and the same
 * "clicking" the page-state picker uses ("After clicking “Menu”"). Earlier
 * copy said "DOM states", "interaction states", "Click-Through states" and
 * "views opened by clicking"; those should not reach a reader.
 */
import type { FindingType, ReviewLane } from "../api/types";
import { REVIEW_TYPE_LABEL } from "./terms";

export const CLICK_THROUGH = "Click-Through";
/** Page states reached by operating a control. Lower case, for use
 *  mid-sentence; headings and table columns use the `_LABEL` form. */
export const CLICK_THROUGH_STATES = "page states opened by clicking";
/** The heading or column form, as the Reports table names the count. */
export const CLICK_THROUGH_STATES_LABEL = "Page states opened by clicking";

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
    "Found at page load, by a rule check (axe or Alfa), a browser check such as the keyboard check, or the AI review.",
  click_through:
    "Found only in a page state opened by clicking a control, such as a menu, tab, or dialog. Use that control first to see it.",
  alt_text:
    "Found by the image text check: text in an image, and whether its alt text (what a screen reader reads) says the same.",
};

export const isFindingType = (value: string): value is FindingType =>
  (FINDING_TYPES as readonly string[]).includes(value);

/** How much confidence an issue's evidence carries. Table order. */
export const REVIEW_LANES = ["likely_barrier", "expert_review", "informational"] as const satisfies readonly ReviewLane[];

/** The issue types' names: `REVIEW_TYPE_LABEL` from terms.ts, under the name this module used. */
export const REVIEW_LANE_LABELS: Record<ReviewLane, string> = REVIEW_TYPE_LABEL;

export const REVIEW_LANE_HELP: Record<ReviewLane, string> = {
  likely_barrier:
    "A check failed a fixed rule, so this is likely to block someone. Fix it, then scan again to confirm the fix.",
  expert_review:
    "A possible problem from a less certain check, such as the AI review or a rule check that cannot tell. A person must confirm it before you report it as a barrier.",
  informational:
    "Recorded for context, not a problem to fix, such as an image whose alt text already says the same words.",
};

export const isReviewLane = (value: string): value is ReviewLane =>
  (REVIEW_LANES as readonly string[]).includes(value);

// ---------------------------------------------------------------------------
// Click-Through, additional forms. Mirrors `CLICK_THROUGH_STATE` in
// `src/audit/labels.py`.
// ---------------------------------------------------------------------------

/** One page state reached by operating a control (singular). */
export const CLICK_THROUGH_STATE = "page state opened by clicking";
