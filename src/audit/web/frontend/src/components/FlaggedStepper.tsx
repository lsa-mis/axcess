import { ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "./ui";
import { cn } from "../lib/cn";

/**
 * Every control for finding the flagged elements of one page, in one group:
 * the count saying where the reader is, and "Previous element" and "Next
 * element" through them in page order. One control for both views of a
 * page, the saved copy (Inspector) and its page code (DomSource), so they
 * cannot drift apart. One element gets "Show element" in place of Previous
 * and Next.
 *
 * The buttons move the highlight and keep focus on the button, so the
 * reader can press again and again; a screen reader hears each element in
 * the status.
 *
 * Getting keyboard focus onto the element itself, in the saved copy, is not
 * a button here. Tab into the copy starts on the element the reader is on
 * (``tabStartAt`` in lib/highlightTargets), where a screen reader reads it
 * in its place on the page, and Escape goes back (see the Inspector). This
 * replaced a "Go to element" button and a line explaining it, which the
 * developer removed on 2026-11-14 to make the toolbar shorter.
 * - Done by tab order (``tabindex="1"`` on the element), not by moving focus
 *   when it enters the copy. That alternative was rejected: a click into the
 *   copy would have focus pulled away from where it landed, and a change
 *   caused by focus is what SC 3.2.1 On Focus (Level A) rules out.
 * - Lost with the button, and accepted: a screen reader reading with the
 *   arrow keys moves no focus, so it meets the copy from its top, as it did
 *   before without the button; Tab after the element goes to the top of the
 *   copy, not on from it (SC 2.4.3 Focus Order, Level A, is kept: the rest
 *   of the copy keeps the page's own order); and there is no visible line
 *   that says Tab starts there. The frame's name says it, for the screen
 *   reader users it matters most to.
 * - Also rejected: Next moving focus into the copy. Every step would take
 *   two keys (Next, then Escape back), and focus would leave the toolbar
 *   each time.
 *
 * The buttons say what they do in their own words, verb or place and
 * object: "Previous element", "Next element", "Show element" (repo rule:
 * Interface language rule 8). Those words are the whole
 * accessible name, with no aria-label: the first version showed "Previous"
 * and named it "Previous flagged element" in an aria-label, which the rule
 * forbids and which a sighted reader never saw. The group's name, "Flagged
 * elements", says which elements. Arrows stay beside Previous and Next, not
 * instead of words: the box does move up or down the page, but chevrons
 * alone read as "scroll" or "collapse", and a voice control user can only
 * say what they see. Each button is a full target tall (SC 2.5.5 Target
 * Size (Enhanced), Level AAA), and the group wraps on a narrow screen rather
 * than squeezing them.
 *
 * Laid out as a count and separate buttons, not one framed pill. The first
 * version framed the count and two borderless (ghost) buttons in one box,
 * so the three read as a single control, and the disabled "Previous" looked
 * like grey text rather than a button. Each button has its own edge (the
 * secondary button, as elsewhere) and space around it (W3C COGA: make
 * controls look like controls), and the count stands outside them as plain
 * text, the status it is.
 *
 * The count is a status, so a screen reader hears where the reader is after
 * each step without moving. With ``detail`` it also hears what the element
 * is ("Flagged element 2 of 5: Heading level 5, “Status messages”"), as
 * screen-reader-only text: on screen the facts table under the toolbar
 * already shows it (SC 4.1.3 Status Messages, Level AA).
 *
 * "Element", not "occurrence": the steps are flagged elements, and one
 * element can hold several occurrences (the inspector's "Occurrences: 3 on
 * this element"), so a count of elements is not a count of occurrences. An
 * occurrence is one place a problem appears and a grouped rule is a "issue type" (docs/plain-language.md, "Why "occurrence" and "issue type"").
 *
 * ``noun`` names the steps when they are not flagged elements: opened from
 * the Documents tab, the inspector marks the links to one document, which
 * flag nothing ("Link to this document 1 of 2"). Same control, other words,
 * rather than a second stepper (SC 3.2.4 Consistent Identification, Level
 * AA). The buttons keep "element", which is still what they move between.
 */
export default function FlaggedStepper({
  count,
  index,
  onGo,
  detail,
  className,
  noun = { one: "Flagged element", many: "Flagged elements", count: "flagged element" },
}: {
  /** What the steps are: "Flagged element 2 of 5", the group "Flagged elements", "1 flagged element". */
  noun?: { one: string; many: string; count: string };
  /** How many flagged elements the page has. */
  count: number;
  /** Which one the reader is on, from 0. */
  index: number;
  /** Show element ``next`` (0-based). */
  onGo: (next: number) => void;
  /** What the current element is, heard after the count; not shown. */
  detail?: string;
  className?: string;
}) {
  const many = count > 1;
  return (
    <span
      role="group"
      aria-label={noun.many}
      className={cn("inline-flex flex-wrap items-center gap-x-3 gap-y-2", className)}
    >
      <span role="status" aria-atomic="true" className="text-2xs font-semibold text-fg-muted">
        {many ? `${noun.one} ${index + 1} of ${count}` : `1 ${noun.count}`}
        {detail && <span className="sr-only">: {detail}</span>}
      </span>
      <span className="inline-flex flex-wrap items-center gap-2">
        {many ? (
          <>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="min-h-target"
              disabled={index === 0}
              onClick={() => onGo(index - 1)}
            >
              <ChevronUp className="h-4 w-4" aria-hidden />
              Previous element
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="min-h-target"
              disabled={index === count - 1}
              onClick={() => onGo(index + 1)}
            >
              Next element
              <ChevronDown className="h-4 w-4" aria-hidden />
            </Button>
          </>
        ) : (
          <Button type="button" variant="secondary" size="sm" className="min-h-target" onClick={() => onGo(0)}>
            Show element
          </Button>
        )}
      </span>
    </span>
  );
}
