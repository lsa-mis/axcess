/*
 * Sorting shared by every table: one vocabulary for directions, the words a
 * sorted header and a status line use for them, and one text comparison.
 */

export type SortDirection = "asc" | "desc";

/**
 * What a column holds, which decides the direction it sorts first and the
 * words for each direction. Text reads A to Z first; numbers and dates
 * read biggest and newest first, the order a reviewer usually wants.
 */
export type SortKind = "text" | "number" | "date";

export type Sort<K extends string> = { column: K; direction: SortDirection };

export const FIRST_DIRECTION: Record<SortKind, SortDirection> = {
  text: "asc",
  number: "desc",
  date: "desc",
};

/**
 * A sort as it is kept in the URL (`?sort=completed_desc`), the form the
 * Issues table uses too, so Back and a shared link bring the order back.
 */
export function sortParam<K extends string>(sort: Sort<K>): string {
  return `${sort.column}_${sort.direction}`;
}

/** ``sortParam`` read back; null for a missing value or a column the table does not have. */
export function parseSortParam<K extends string>(raw: string | null, columns: readonly K[]): Sort<K> | null {
  const match = raw?.match(/^(.+)_(asc|desc)$/);
  if (!match || !(columns as readonly string[]).includes(match[1])) return null;
  return { column: match[1] as K, direction: match[2] as SortDirection };
}

/** Pressing the sorted column flips it; any other column starts at its first direction. */
export function nextSort<K extends string>(current: Sort<K> | null, column: K, kind: SortKind): Sort<K> {
  if (current?.column === column) {
    return { column, direction: current.direction === "asc" ? "desc" : "asc" };
  }
  return { column, direction: FIRST_DIRECTION[kind] };
}

const CHIP: Record<SortKind, Record<SortDirection, string>> = {
  text: { asc: "A → Z", desc: "Z → A" },
  number: { asc: "low → high", desc: "high → low" },
  date: { asc: "old → new", desc: "new → old" },
};

const WORDS: Record<SortKind, Record<SortDirection, string>> = {
  text: { asc: "A to Z", desc: "Z to A" },
  number: { asc: "lowest first", desc: "highest first" },
  date: { asc: "oldest first", desc: "newest first" },
};

/** The direction as the sorted header's chip shows it: "high → low", "A → Z". */
export function sortChip(kind: SortKind, direction: SortDirection): string {
  return CHIP[kind][direction];
}

/** The direction in words, for a status line or a caption: "highest first". */
export function sortWords(kind: SortKind, direction: SortDirection): string {
  return WORDS[kind][direction];
}

export function ariaSort(active: boolean, direction: SortDirection): "ascending" | "descending" | "none" {
  if (!active) return "none";
  return direction === "asc" ? "ascending" : "descending";
}

/**
 * Case- and accent-insensitive text order. One collator for every sort:
 * `localeCompare` with options builds a new one on every call, which made
 * a 2,000-row text sort about 40 times slower for the same order.
 */
const collator = new Intl.Collator(undefined, { sensitivity: "base" });
export const compareText = (a: string, b: string): number => collator.compare(a, b);
