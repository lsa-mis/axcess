import { cn } from "../lib/cn";

/**
 * A "How sure" value as a small filled tag: "Mostly sure", "Not sure", and
 * the quiet outlined look for a value that is not a problem found ("For
 * information" on Issues, "Could not check" on Documents).
 *
 * Moved here from the Issues table (routes/Issues.tsx, ``LaneTag``) when the
 * Documents tab needed the same value shown the same way: one look for one
 * kind of thing on every screen (SC 3.2.4 Consistent Identification, Level
 * AA). Rejected: a second, restyled copy in the Documents route, which would
 * drift from this one. The markup and classes are exactly the old LaneTag's.
 *
 * The words carry the meaning; the colour only repeats it (SC 1.4.1 Use of
 * Color, Level A). ``help`` is a hover hint only, so the screen that shows a
 * tag must also say what each value means in its own text.
 */
export default function HowSureTag({
  label,
  help,
  quiet = false,
}: {
  label: string;
  /** What the value means, shown on hover. Omit where the meaning is printed beside it. */
  help?: string;
  /** The outlined, muted look, for a value that is not a problem found. */
  quiet?: boolean;
}) {
  return (
    <span
      title={help}
      className={cn(
        "inline-flex items-center rounded-2xs px-2 py-0.5 text-2xs font-semibold",
        quiet ? "border border-border bg-surface-muted text-fg-muted" : "bg-sev-major-bg text-sev-major",
      )}
    >
      {label}
    </span>
  );
}
