/**
 * Issue fields left out of the Issues table and the issue page for now.
 *
 * Each name is both a column of the Issues table and a fact on the issue
 * page, and hiding it here hides it in both. The API still returns the
 * field and the exports still carry it; only these two screens skip it. A
 * saved ``?sort=`` link naming a hidden column opens the recommended order.
 * Take a name out of the set to bring the field back.
 */
export const HIDDEN_ISSUE_FIELDS: ReadonlySet<string> = new Set(["Difficulty", "Responsibility"]);
