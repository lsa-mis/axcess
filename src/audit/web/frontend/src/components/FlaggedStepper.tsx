import { ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "./ui";
import { cn } from "../lib/cn";

/**
 * Previous / Next through the flagged elements of one page, in page order,
 * with the count between them saying where the reader is. One control for
 * both views of a page, the saved copy (Inspector) and its page code
 * (DomSource), so they cannot drift apart. One element gets a single "Jump".
 *
 * The buttons say what they do in words, with an arrow beside the word,
 * not an arrow alone. Up and down chevrons on their own read as "scroll" or
 * "collapse" as easily as "previous" and "next" (W3C COGA, "Making Content
 * Usable", https://www.w3.org/TR/coga-usable/: use words people know, and
 * label controls clearly), and a voice control user can only say what they
 * see: with an icon, they must guess the hidden name. Each accessible name
 * starts with its visible word ("Next flagged element"; WCAG 2.2 SC 2.5.3
 * Label in Name, Level A, "the name contains the text that is presented
 * visually"). The arrows stay: the box does move up or down the page. The
 * buttons are a full target tall (SC 2.5.5), and the group wraps on a
 * narrow screen rather than squeezing them.
 *
 * Laid out as a count and two separate buttons, not one framed pill. The
 * first version framed the count and two borderless (ghost) buttons in one
 * box, so the three read as a single control, and the disabled "Previous"
 * looked like grey text rather than a button. Each button now has its own
 * edge (the secondary button, as elsewhere) and space around it, so each is
 * found and aimed at on its own (W3C COGA: make controls look like
 * controls; easier for low vision and for anyone with an unsteady hand),
 * and the count stands outside them as plain text, the status it is.
 *
 * "Previous" and "Next", not "issue": the steps are flagged elements (each
 * an occurrence's place on this page), and "issue" is the grouped rule
 * (docs/plain-language.md).
 */
export default function FlaggedStepper({
  count,
  index,
  onGo,
  className,
}: {
  /** How many flagged elements the page has. */
  count: number;
  /** Which one the reader is on, from 0. */
  index: number;
  /** Go to element ``next`` (0-based). */
  onGo: (next: number) => void;
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
      </span>
      <span className="inline-flex items-center gap-2">
        {many && (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="min-h-target"
            aria-label="Previous flagged element"
            disabled={index === 0}
            onClick={() => onGo(index - 1)}
          >
            <ChevronUp className="h-4 w-4" aria-hidden />
            Previous
          </Button>
        )}
        <Button
          type="button"
          variant="secondary"
          size="sm"
          className="min-h-target"
          aria-label={many ? "Next flagged element" : "Jump to flagged element"}
          disabled={many && index === count - 1}
          onClick={() => onGo(many ? index + 1 : 0)}
        >
          {many ? "Next" : "Jump"}
          <ChevronDown className="h-4 w-4" aria-hidden />
        </Button>
      </span>
    </span>
  );
}
