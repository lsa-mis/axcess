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
import type { FindingType, ReviewLane, WcagRef } from "../api/types";
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

/** Which family of checks produced an issue type's evidence. Table order. */
export const FINDING_TYPES = ["wcag", "click_through", "alt_text"] as const satisfies readonly FindingType[];

/**
 * Where an issue type shows up, as the Issues table's "Where it shows" column
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

/** How much confidence an issue type's evidence carries. Table order. */
export const REVIEW_LANES = ["likely_barrier", "measured", "expert_review", "informational"] as const satisfies readonly ReviewLane[];

/**
 * The "How sure" values the Issues table shows when it opens: all four, since
 * 2026-11-13 (the developer's request). Mirrors `DEFAULT_REVIEW_LANES` in
 * `src/audit/labels.py`, which the server counts by (`default_view_counts`),
 * so the numbers above the table are the rows under them.
 */
export const DEFAULT_REVIEW_LANES = [
  "likely_barrier",
  "measured",
  "expert_review",
  "informational",
] as const satisfies readonly ReviewLane[];

/** The surest "How sure" values: what "Show only the surest" narrows the Issues table to. */
export const SUREST_REVIEW_LANES = ["likely_barrier", "measured"] as const satisfies readonly ReviewLane[];

/** The "How sure" values' names: `REVIEW_TYPE_LABEL` from terms.ts, under the name this module used. */
export const REVIEW_LANE_LABELS: Record<ReviewLane, string> = REVIEW_TYPE_LABEL;

export const REVIEW_LANE_HELP: Record<ReviewLane, string> = {
  likely_barrier:
    "A rule check (axe or Alfa) failed. These checks follow fixed rules, so they give the same result every time. Look at each occurrence on the page, fix it, test the fix, then scan again to see if it is still found.",
  measured:
    "The browser measured this on the page. No AI was used. A measurement can still miss how a person uses the page, so check each occurrence before you report it.",
  expert_review:
    "Axcess found a possible problem, but it cannot be certain. This happens with checks such as the AI review, the image text check, or a rule check that cannot decide. A person must decide whether it is a real problem before you report it.",
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
 * looks hints up by it). The count column is "Issue occurrences": it read
 * "Issues" from 2026-10-26 to 2026-10-28, "Occurrences" after user testing
 * with Siteimprove users, and "Issue occurrences" from 2026-10-30
 * (docs/plain-language.md, "Why "occurrence" and "issue type""). Its hint
 * says what an occurrence is,
 * because the column is where a reader first meets the word, and
 * "occurrence" is an advanced word (SC 3.1.3 Unusual Words, Level AAA).
 */
export const ISSUE_COLUMN_HELP = {
  "How sure": "How sure Axcess is that this issue type is a real problem: Mostly sure, Measured, Not sure, or For information.",
  "Where it shows": "Where this issue type shows up: at page load, after clicking, or in an image.",
  Priority:
    "High, Medium, or Low, from the impact rating of this issue type. More pages and more occurrences raise it. Not sure lowers it, because a person must confirm it first. Issue types from the rule check (Alfa) have no rating, so they start at the lowest. Issue types marked For information show Does not apply.",
  "Affected pages":
    "Pages with at least one occurrence of this issue type. An element repeated on many pages, such as a shared menu, counts only on the first page it was found on. An image counts on every page it appears on.",
  "Issue occurrences":
    "How many occurrences of this issue type were found. An occurrence is one place a problem appears: one element on one page, or in one page state. An element repeated on many pages, such as a shared menu, counts once. An image counts every time it appears.",
  Check:
    "Which check found this issue type. Rule check (axe) uses axe-core, made by Deque. Rule check (Alfa) uses Alfa, made by Siteimprove.",
} as const;

/**
 * What the Reports list's "Rule check" column holds. It names who makes each
 * tool, because testers who use Siteimprove asked whether a report came from
 * axe or from Siteimprove (user testing, 2026-10-28), and "Alfa" alone did
 * not tell them.
 */
export const RULE_CHECK_HELP =
  "Which rule checks tested pages in this scan: axe (axe-core, made by Deque), Alfa (made by Siteimprove), or both.";

/**
 * What each priority band means. Priority starts from the impact rating
 * (critical 6, serious 4, moderate 2.5, minor 1; none, as for Rule check
 * (Alfa), counts as minor), adds ln(pages) up to 3 (pages where a shared
 * element repeats included) and 0.25 x ln(occurrences) up to 1, then scales
 * by how sure Axcess is (Mostly sure x1, Not sure x0.55, For information
 * x0.25). High is 6 or more and Medium 3 or more (``_priority`` in
 * src/audit/web/issues.py). So a critical problem is High on 1 page, a
 * serious one is High from 8 pages, and Not sure is never High.
 *
 * Until 2026-11-06 the score was the weight times ln(1 + pages): a critical
 * problem on 1 page was Low while a Not sure zoom lead on 10 pages was High,
 * so Priority contradicted the Impact column and the "How sure" value.
 * Rejected: keeping spread first and warning in the Low hint ("Low can still
 * be serious"). A label that needs a warning to be read correctly is the
 * wrong label (W3C COGA "Making Content Usable",
 * https://www.w3.org/TR/coga-usable/, paraphrased: make content clear and
 * do not make people work out what it means).
 *
 * The table's recommended order groups by "How sure" first, so a band ranks
 * the kinds of issue in one "How sure" group. The examples are exact for the
 * formula; keep them in step with ``test_priority_bands``.
 */
export const PRIORITY_HELP = {
  High: "Look at these first among issue types with the same How sure value. For example: a critical problem, even on 1 page, or a serious one on 8 or more pages. Not sure issue types are never High, because a person must confirm them first.",
  Medium:
    "Look at these after the High ones with the same How sure value. For example: a serious problem on 1 page, or a moderate one on 2 or more pages. More pages and more occurrences raise the priority, and pages a shared element repeats on count too.",
  Low: "Look at these last among issue types with the same How sure value. For example: a minor problem, or a moderate one on 1 page. Low can still matter, so open it before you skip it.",
} as const;

/**
 * "1 at page load, 7 after clicking": where an issue type's occurrences were
 * found, for the issue page's Issue occurrences tile. Empty when none needed
 * a click, since then every one was there at page load and the Where it
 * shows tag already says so.
 *
 * The developer chose this (2026-11-10) over a count inside the Issues
 * table's "At page load" and "After clicking" tags: the table keeps its
 * narrow stacked tags (see FindingTypeCell in routes/Issues.tsx), and the
 * split is on the page a reader opens to compare Axcess with a tool such as
 * WAVE, which checks the page with its menus closed and so finds fewer. The
 * words are the tags' own, lower-cased, so one thing keeps one name (W3C
 * COGA "Making Content Usable", https://www.w3.org/TR/coga-usable/; WCAG 2.2
 * SC 3.2.4 Consistent Identification, Level AA).
 */
export function whereFoundText(occurrences: number, afterClicking: number): string {
  if (afterClicking <= 0) return "";
  const atLoad = Math.max(0, occurrences - afterClicking);
  return `${atLoad.toLocaleString()} ${FINDING_TYPE_LABELS.wcag.toLowerCase()}, ${afterClicking.toLocaleString()} ${FINDING_TYPE_LABELS.click_through.toLowerCase()}`;
}

/**
 * The other criteria an issue type maps to, as "also 4.1.2 Name, Role,
 * Value": one axe rule can fail more than one criterion (link-name fails
 * 2.4.4 and 4.1.2), and naming only the first under-reports what a fix must
 * meet. The first criterion keeps its place and its level badge, so sorting
 * and the badge mean what they did; "also" says the rest are extra, not a
 * replacement. Rejected: one badge per criterion (a row of badges reads as a
 * list of separate issue types) and a joined "2.4.4, 4.1.2" (it hides which
 * one the level badge belongs to). Names show when Axcess knows them.
 */
export function alsoWcagText(refs: readonly WcagRef[], withNames: boolean): string {
  if (refs.length === 0) return "";
  const parts = refs.map((ref) => (withNames && ref.name ? `${ref.sc} ${ref.name}` : ref.sc));
  return `also ${parts.join(", ")}`;
}

export const isReviewLane = (value: string): value is ReviewLane =>
  (REVIEW_LANES as readonly string[]).includes(value);

// ---------------------------------------------------------------------------
// Click-Through, additional forms. Mirrors `CLICK_THROUGH_STATE` in
// `src/audit/labels.py`.
// ---------------------------------------------------------------------------

/** One page state reached by operating a control (singular). */
export const CLICK_THROUGH_STATE = "page state opened by clicking";
