import type { RefObject } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "./ui";
import { cn } from "../lib/cn";

/**
 * Every control for finding the flagged elements of one page, in one group:
 * the count saying where the reader is, "Previous element" and "Next
 * element" through them in page order, and, in the saved copy, "Go to
 * element". One control for both views of a page, the saved copy
 * (Inspector) and its page code (DomSource), so they cannot drift apart.
 * One element gets "Show element" in place of Previous and Next.
 *
 * Two kinds of move, two kinds of button. Previous, Next and Show element
 * move the highlight and keep focus on the button, so the reader can press
 * again and again; a screen reader hears each element in the status. "Go to
 * element" moves keyboard focus onto the element itself, inside the copy,
 * where a screen reader reads it in its place on the page, and Escape comes
 * back to it (see the Inspector). They sit together because they answer one
 * question, where is the element; the Go to button used to sit under the
 * facts table, far from the stepper, and read as a second way to do the same
 * thing (W3C COGA, "Making Content Usable",
 * https://www.w3.org/TR/coga-usable/: group related controls).
 *
 * Rejected, at the developer's suggestion: (1) dropping Go to and landing on
 * the flagged element whenever focus enters the copy. A click into the copy
 * fires the same focus, so a mouse user would have focus pulled away from
 * where they clicked; a screen reader reading with the arrow keys moves no
 * focus, so it would not happen for the readers it is for; nothing on screen
 * would say it happens; and Tab would start part way down a page (SC 2.4.3
 * Focus Order, Level A; the idea behind SC 3.2.1 On Focus, Level A). (2)
 * Next moving focus into the copy: every step would take two keys (Next,
 * then Escape back), and focus would leave the toolbar each time.
 *
 * The buttons say what they do in their own words, verb or place and
 * object: "Previous element", "Next element", "Show element", "Go to
 * element" (repo rule: Interface language rule 8). Those words are the whole
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
 * "Element", not "issue": the steps are flagged elements (each an
 * occurrence's place on this page), and "issue" is the grouped rule
 * (docs/plain-language.md).
 */
export default function FlaggedStepper({
  count,
  index,
  onGo,
  detail,
  goTo,
  className,
}: {
  /** How many flagged elements the page has. */
  count: number;
  /** Which one the reader is on, from 0. */
  index: number;
  /** Show element ``next`` (0-based). */
  onGo: (next: number) => void;
  /** What the current element is, heard after the count; not shown. */
  detail?: string;
  /** "Go to element", where the view can move focus onto it (the saved copy). */
  goTo?: { onClick: () => void; ref: RefObject<HTMLButtonElement | null>; hintId: string };
  className?: string;
}) {
  const many = count > 1;
  return (
    <span
      role="group"
      aria-label="Flagged elements"
      className={cn("inline-flex flex-wrap items-center gap-x-3 gap-y-2", className)}
    >
      <span role="status" aria-atomic="true" className="text-2xs font-semibold text-fg-muted">
        {many ? `Flagged element ${index + 1} of ${count}` : "1 flagged element"}
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
        {goTo && (
          <Button
            ref={goTo.ref}
            type="button"
            variant="secondary"
            size="sm"
            className="min-h-target"
            aria-describedby={goTo.hintId}
            onClick={goTo.onClick}
          >
            Go to element
          </Button>
        )}
      </span>
    </span>
  );
}
