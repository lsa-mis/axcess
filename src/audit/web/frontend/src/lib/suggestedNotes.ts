/**
 * Issue notes suggested from the scan, for the inspector's review dialog.
 *
 * The ITS Accessibility Team writes each note as where it is, then what is
 * wrong, then the specifics: "After clicking “View Issues”, all the x and ✓
 * images lacking alt tag", or, copied from the rule check, "… has
 * insufficient color contrast of 3.9 (foreground color: #7d7d7d, …).
 * Expected contrast ratio of 4.5:1". The suggestion is built the same way
 * from what the scan stored:
 *
 *   [After clicking “A” → “B”, ]“text” what-it-is problem. detail.
 *
 * - The page state comes first, and only for an element found after a
 *   click (the click chain the inspector's Page state list shows).
 * - The element is its text or label and what it is, as the element facts
 *   say them; with no text, "The <div> element".
 * - The problem is the issue's plain-language title. When the check's own
 *   sentence starts "Element has …", that sentence is used with the element
 *   as its subject, which is exactly the team's contrast wording; a title
 *   that starts "Element …" is joined the same way.
 * - The check's detail follows only when it adds something the title does
 *   not: an attribute, a number, a colour, quoted text. "Heading order
 *   invalid" only repeats "Heading levels skip a step", so it is left out.
 *   An axe summary is lists of failed checks under "Fix all of the
 *   following" (each one a real failure, kept when it is specific) and
 *   "Fix any of the following" (other ways to fix it, such as every way a
 *   link could get a name, which describe no problem and are left out,
 *   except a specific "Element has …" sentence such as the contrast one,
 *   with its numbers). Any
 *   other check's summary is one detail, as written.
 *
 * Pure text in, text out, so it can be read and tested on its own.
 */

/** The heading axe puts before each list of failed checks. */
const FIX_HEADING = /^fix (any|all) of the following:?$/i;
const ELEMENT_HAS = /^element has /i;
const ELEMENT = /^element /i;
const MAX_TEXT = 60;
const MAX_DETAIL = 400;

export type NoteParts = {
  /** The click chain to the page state, "“Menu” → “Help”"; null at page load. */
  clickChain: string | null;
  /** What the element is, as the facts say it: "Button", "<div> element". */
  kind: string;
  /** The element's text or label; null when it has none. */
  text: string | null;
  /** The issue's plain-language title. */
  title: string;
  /** The check's own sentences for the occurrences on this element. */
  details: string[];
};

function shorten(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  const cut = flat.slice(0, max);
  const space = cut.lastIndexOf(" ");
  return `${(space > max / 2 ? cut.slice(0, space) : cut).replace(/[\s·,.;:–-]+$/, "")}…`;
}

type Detail = { text: string; alternative: boolean };

/**
 * A check's summary as separate sentences. An axe summary is lists of failed
 * checks, each under "Fix all …" (all are failures) or "Fix any …" (other
 * ways to fix it); any other summary is one sentence, as written.
 */
function splitDetail(summary: string): Detail[] {
  const lines = summary.split("\n").map((line) => line.trim()).filter(Boolean);
  if (!lines.some((line) => FIX_HEADING.test(line))) {
    const text = shorten(lines.join(" "), MAX_DETAIL);
    return text ? [{ text, alternative: false }] : [];
  }
  const out: Detail[] = [];
  let alternative = false;
  for (const line of lines) {
    const heading = FIX_HEADING.exec(line);
    if (heading) alternative = heading[1].toLowerCase() === "any";
    else out.push({ text: shorten(line, MAX_DETAIL), alternative });
  }
  return out;
}

/** Whether a detail says something the title does not. */
function informative(detail: string, title: string): boolean {
  if (!detail || detail.toLowerCase() === title.toLowerCase()) return false;
  return /[0-9:#="“”'"]/.test(detail);
}

function sentence(text: string): string {
  const trimmed = text.trim();
  return /[.!?…]$/.test(trimmed) ? trimmed : `${trimmed}.`;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function suggestIssueNotes({ clickChain, kind, text, title, details }: NoteParts): string {
  if (!title.trim()) return "";
  // "<div> element" stays as written; "Heading level 5" reads mid-sentence.
  const what = kind.startsWith("<") ? kind : kind.charAt(0).toLowerCase() + kind.slice(1);
  const label = text ? shorten(text, MAX_TEXT) : "";
  const subject = label ? `“${label}” ${what}` : `the ${what}`;

  const parts = details.flatMap(splitDetail);
  // Only a specific "Element has …" leads, such as the contrast sentence with
  // its numbers. "Element has no title attribute" is one of axe's other ways
  // to name an element, not the problem.
  const leading = parts.find(
    (detail) => ELEMENT_HAS.test(detail.text) && informative(detail.text, title),
  )?.text;
  const rest = [
    ...new Set(
      parts
        .filter((detail) => !detail.alternative && detail.text !== leading)
        .map((detail) => detail.text)
        .filter((text) => informative(text, title)),
    ),
  ];

  let main: string;
  if (leading) main = `${subject} ${leading.replace(ELEMENT, "")}`;
  else if (ELEMENT.test(title)) main = `${subject} ${title.replace(ELEMENT, "")}`;
  else main = `${subject}: ${title}`;
  const where = clickChain ? `After clicking ${clickChain}, ` : "";

  return [capitalize(sentence(where + main)), ...rest.map(sentence)].join(" ");
}
