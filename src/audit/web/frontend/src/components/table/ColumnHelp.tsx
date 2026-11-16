import type { ReactNode } from "react";
import { HelpTip } from "../ui";

/**
 * The "?" beside an explained column's header: the question the column
 * answers and what each of its values means, in the glossary's own words,
 * so the two never disagree (W3C COGA, "Making Content Usable": the same
 * words for the same thing). Shared by the Issues table (How sure, Where it
 * shows, Priority) and the Documents table (Accessibility problems?), so the
 * same kind of help looks and works the same on both (SC 3.2.4 Consistent
 * Identification, Level AA). Moved here from routes/Issues.tsx when the
 * Documents tab got its "?" (the developer's request, 2026-11-16), rather
 * than copied.
 *
 * Which headers have one (the developer's choice, 2026-11-16, option 1 of
 * three): those whose values need explaining, not every header. One rule,
 * one look, one behaviour: a "?" is wherever a word needs explaining, as on
 * the big numbers over the table and the Images heading. Rejected: a "?" on
 * every header, which added about 224px on Issues (the table then scrolled
 * sideways at 1280px), more Tab stops, and a question in every column's
 * name for words that need no explaining; and a "?" on each row's tag, one
 * Tab stop per row for the same sentences. "What the labels mean" under the
 * table stays as the one place all the meanings can be read, searched and
 * printed together.
 *
 * The icon sits on the label's line, as the sort button's words sit at the
 * foot of their target (SortHeader, wrap="words"); centred in its target it
 * floated above the words (the developer's screenshots, 2026-11-16). 28px
 * wide, so the header reads as one centred group: allowed because "What
 * the labels mean" (``report-labels-button``, a 44px control on the same
 * page) gives the same explanation (HelpTip, ``equivalent``; SC 2.5.5
 * Target Size (Enhanced), Level AAA, "Equivalent" exception).
 *
 * Known cost: the button's words sit inside the header cell, so a screen
 * reader that names the column for each cell may read "How sure, What does
 * How sure mean?" there. Kept short for that reason, and only on the
 * headers that need it.
 */
export default function ColumnHelp({
  question,
  answers,
  items,
}: {
  /** The button's name without its "?": "What does “How sure” mean". */
  question: string;
  /** The question the column answers, as a sentence: "How sure Axcess is …". */
  answers: string;
  items: { key: string; term: ReactNode; help: string }[];
}) {
  return (
    <HelpTip
      question={question}
      equivalent="report-labels-button"
      small
      // Centred on the label's line: 18px icon, 20px line, 6px under it.
      className="items-end pb-1.5"
    >
      <p className="mb-2 font-semibold">
        {answers.charAt(0).toUpperCase()}
        {answers.slice(1)}.
      </p>
      <dl className="space-y-2">
        {items.map((item) => (
          <div key={item.key}>
            <dt>{item.term}</dt>
            <dd className="mt-0.5 text-fg-muted">{item.help}</dd>
          </div>
        ))}
      </dl>
    </HelpTip>
  );
}
