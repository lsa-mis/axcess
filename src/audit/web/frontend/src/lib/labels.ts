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

/** Which family of checks produced a kind of issue's evidence. Table order. */
export const FINDING_TYPES = ["wcag", "click_through", "alt_text"] as const satisfies readonly FindingType[];

/**
 * Where a kind of issue shows up, as the Issues table's "Where it shows" column
 * names it: "At page load", "After clicking", "In an image". The header is a
 * plain question every value answers, like "How sure" beside it. Rejected
 * headers: "Found" (a lone verb, read as "found: yes or no" or a count),
 * "Where found" and "When found" (a time and a place do not both fit).
 *
 * Rejected: "WCAG", "Click-Through" and "Alt Text" under "Found by". WCAG
 * finds nothing, so "Found by WCAG" was wrong; "WCAG" is an abbreviation and
 * also the name of the next column (one word, two meanings); "Click-Through"
 * and "Alt Text" are feature and technical names. Also rejected as too
 * long: "When the page loads", "After opening something". "At page load"
 * and "After clicking" are the words page states already use ("At page
 * load", "After clicking Menu"), so one thing keeps one name. The
 * Click-Through feature keeps its name elsewhere; only this badge changed.
 * SC 3.1.4 Abbreviations and SC 3.1.5 Reading Level (both Level AAA); W3C
 * COGA "Making Content Usable", https://www.w3.org/TR/coga-usable/ (the
 * same word for the same thing); docs/plain-language.md.
 */
export const FINDING_TYPE_LABELS: Record<FindingType, string> = {
  wcag: "At page load",
  click_through: "After clicking",
  alt_text: "In an image",
};

export const FINDING_TYPE_HELP: Record<FindingType, string> = {
  wcag:
    "Found when the page first loads. It can come from a rule check, a browser check (such as the keyboard check), or the AI review.",
  click_through:
    "Found only after Axcess clicked something that opens more of the page, such as a menu, a tab, or a pop-up window (dialog). To see the problem yourself, click the same thing. Axcess never clicks links.",
  alt_text:
    "Found by the image text check. It looks at words inside an image and compares them to the image's text description (alt text), which a screen reader reads aloud.",
};

export const isFindingType = (value: string): value is FindingType =>
  (FINDING_TYPES as readonly string[]).includes(value);

/** How much confidence a kind of issue's evidence carries. Table order. */
export const REVIEW_LANES = ["likely_barrier", "expert_review", "informational"] as const satisfies readonly ReviewLane[];

/** The "How sure" values' names: `REVIEW_TYPE_LABEL` from terms.ts, under the name this module used. */
export const REVIEW_LANE_LABELS: Record<ReviewLane, string> = REVIEW_TYPE_LABEL;

export const REVIEW_LANE_HELP: Record<ReviewLane, string> = {
  likely_barrier:
    "A rule check (axe or Alfa) failed. These checks follow fixed rules, so they give the same result every time. Look at each issue on the page, fix it, test the fix, then scan again to see if it is still found.",
  expert_review:
    "Axcess found a possible problem, but it cannot be certain. This happens with checks such as the AI review, the browser checks, or a rule check that cannot decide. A person must decide whether it is a real problem before you report it.",
  informational:
    "Recorded for context. This is not a problem to fix. For example, an image whose text description (alt text) already matches the words in the image.",
};

/**
 * Hover hints for the Issues table's column headers. On each header's sort
 * button, not the cells: the button takes focus, so a keyboard user reaches
 * the hint too (in the "Always" hints setting) and a screen reader reads it
 * as the button's description.
 *
 * Keyed by the header's visible text (``columnHint`` in routes/Issues.tsx
 * looks hints up by it), so "Issues" is the count column that was
 * "Occurrences" until 2026-10-26 (docs/plain-language.md, "Why "issue" and
 * "kind of issue"").
 */
export const ISSUE_COLUMN_HELP = {
  "How sure": "How sure Axcess is that this kind of issue is a real problem: Mostly sure, Not sure, or For information.",
  "Where it shows": "Where this kind of issue shows up: at page load, after clicking, or in an image.",
  Priority:
    "High, Medium, or Low, from the impact rating of this kind of issue and how many pages it is on. Kinds of issue from the rule check (Alfa) have no rating, so they count as the lowest. A serious kind of issue on one page can still be Low. Kinds of issue marked For information show Does not apply.",
  Pages:
    "Pages with at least one issue of this kind. An element repeated on many pages, such as a shared menu, counts only on the first page it was found on. An image counts on every page it appears on.",
  Issues:
    "How many issues of this kind were found: one for each place. An element repeated on many pages, such as a shared menu, counts once. An image counts every time it appears.",
} as const;

/**
 * What each priority band means. Priority is the impact rating's weight
 * (critical 4 to minor 1; none, as for Rule check (Alfa), counts as 1) times
 * ln(1 + pages), pages where a shared element repeats included, with High at
 * 6 and Medium at 3 (``_priority`` in src/audit/web/issues.py). The table's
 * recommended order groups by "How sure" first, so a band ranks the kinds of
 * issue in one "How sure" group. The hints said "issues of the same type"
 * until 2026-10-26; "type" was the old name of "How sure", and a row is now
 * a kind of issue (docs/plain-language.md, "Why "issue" and "kind of issue"").
 */
export const PRIORITY_HELP = {
  High: "Look at these first among kinds of issue with the same How sure value: a high impact rating on many pages, such as a critical problem on 4 or more pages or a moderate one on 20 or more (pages a shared element repeats on count too).",
  Medium:
    "Look at these after the High ones with the same How sure value. Priority combines the impact rating with how many pages have it.",
  Low: "Look at these last among kinds of issue with the same How sure value. Low can still be serious: a critical problem on 1 page is Low, so open it before you skip it.",
} as const;

export const isReviewLane = (value: string): value is ReviewLane =>
  (REVIEW_LANES as readonly string[]).includes(value);

// ---------------------------------------------------------------------------
// Click-Through, additional forms. Mirrors `CLICK_THROUGH_STATE` in
// `src/audit/labels.py`.
// ---------------------------------------------------------------------------

/** One page state reached by operating a control (singular). */
export const CLICK_THROUGH_STATE = "page state opened by clicking";
