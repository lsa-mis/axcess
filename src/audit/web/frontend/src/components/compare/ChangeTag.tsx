import type { ComparisonChange } from "../../api/types";
import { cn } from "../../lib/cn";

export const CHANGES: ComparisonChange[] = ["new", "resolved", "remaining"];

export const CHANGE_LABEL: Record<ComparisonChange, string> = {
  new: "New",
  resolved: "Resolved",
  remaining: "Remaining",
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

export default function ChangeTag({ change, className }: { change: ComparisonChange; className?: string }) {
  return (
    <span
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
