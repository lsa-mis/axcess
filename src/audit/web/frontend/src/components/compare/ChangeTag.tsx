import type { ComparisonChange } from "../../api/types";
import { cn } from "../../lib/cn";

export const CHANGES: ComparisonChange[] = ["new", "resolved", "remaining"];

/**
 * The words for each change. "No longer found", not "Resolved": the later
 * scan not finding an issue does not prove it was fixed, and "Fixed" is a
 * status (docs/plain-language.md).
 */
export const CHANGE_LABEL: Record<ComparisonChange, string> = {
  new: "New",
  resolved: "No longer found",
  remaining: "Still found",
};

/**
 * What each change means, for the hover hint. "No longer found" keeps its
 * limit: a later scan not finding an issue does not prove it was fixed, and
 * different pages or checks can explain New and No longer found.
 */
export const CHANGE_HELP: Record<ComparisonChange, string> = {
  new: "Found in the later scan but not in the earlier one. The site may have changed, or the scans used different pages or checks. Check the page.",
  resolved:
    "Found in the earlier scan but not in the later one. That is not proof of a fix, especially if the scans used different pages or checks. Check the page yourself before you mark it Fixed.",
  remaining: "Found in both scans. Its number of occurrences can still go up or down.",
};

/**
 * One tint per change, shared by the stat cards, the before/after bars and
 * the table, so a colour means the same thing everywhere on the page. The
 * word is always printed with it: the tint only helps the eye group them.
 */
export const CHANGE_TONE: Record<ComparisonChange, string> = {
  new: "bg-sev-critical-bg text-sev-critical",
  resolved: "bg-umich-blue/10 text-umich-blue",
  remaining: "bg-surface-muted text-fg-muted",
};

/** ``hint={false}`` where the meaning is printed beside it or a button around it says it. */
export default function ChangeTag({
  change,
  className,
  hint = true,
}: {
  change: ComparisonChange;
  className?: string;
  hint?: boolean;
}) {
  return (
    <span
      title={hint ? CHANGE_HELP[change] : undefined}
      className={cn(
        "inline-flex items-center rounded-2xs border border-transparent px-2 py-0.5 text-2xs font-semibold",
        CHANGE_TONE[change],
        change === "remaining" && "border-border",
        className,
      )}
    >
      {CHANGE_LABEL[change]}
    </span>
  );
}
