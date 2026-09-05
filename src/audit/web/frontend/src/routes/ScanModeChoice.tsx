import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export type ScanMode = "public" | "login";

/**
 * One scan-type card. The whole box is the control.
 *
 * Earlier this was a Card with a "Select …" button inside it, which gave
 * the page two competing targets, the box looked clickable but wasn't,
 * and the button repeated the card's own title. A native radio fixes
 * both: click anywhere on the card, arrow between the options, and the
 * selected state is real form state rather than a styled div.
 *
 * ``footer`` renders as a sibling of the label, never inside it, because
 * it can contain a link, a link nested in a label would also toggle the
 * radio when activated.
 */
export default function ScanModeChoice({
  value,
  selected,
  onSelect,
  icon,
  title,
  help,
  disabled = false,
  footer,
}: {
  value: ScanMode;
  selected: ScanMode;
  onSelect: (value: ScanMode) => void;
  icon: ReactNode;
  title: string;
  help: string;
  disabled?: boolean;
  footer?: ReactNode;
}) {
  const id = `scan-mode-${value}`;
  const isSelected = selected === value;
  return (
    <div
      className={cn(
        // border-2 in both states: a 1px→2px swap on selection would
        // shift the card's contents by a pixel every time you arrow
        // between the two options.
        "flex h-full flex-col rounded-xs border-2 bg-surface shadow-card",
        isSelected ? "border-umich-blue bg-umich-blue/5" : "border-border",
      )}
    >
      {/* The native radio is nested in this label and also joined by
          htmlFor/id, so the association holds for browsers and assistive
          tech either way. */}
      <label
        htmlFor={id}
        className={cn(
          "flex flex-1 flex-col gap-2 p-5",
          disabled
            ? "cursor-not-allowed opacity-60"
            : "cursor-pointer hover:bg-surface-muted/40",
        )}
      >
        <span className="flex items-start gap-3">
          <input
            id={id}
            type="radio"
            name="scan-mode"
            value={value}
            checked={isSelected}
            disabled={disabled}
            onChange={() => onSelect(value)}
            aria-labelledby={`${id}-title`}
            aria-describedby={`${id}-help`}
            className="mt-0.5 h-[22px] w-[22px] shrink-0 border-2 border-border-strong text-umich-blue focus:outline-none"
          />
          {icon}
          <span id={`${id}-title`} className="font-semibold text-fg">
            {title}
          </span>
        </span>
        <span id={`${id}-help`} className="text-sm text-fg-muted">
          {help}
        </span>
        {isSelected && (
          // mt-auto pins the pill to the bottom of the card, so it sits
          // in the same place on both cards however long the help text
          // above it runs.
          <span className="mt-auto inline-flex self-start rounded-full bg-umich-blue px-2.5 py-1 text-xs font-semibold text-fg-inverse">
            Selected
          </span>
        )}
      </label>
      {footer && <div className="px-5 pb-5 text-sm text-fg-muted">{footer}</div>}
    </div>
  );
}
