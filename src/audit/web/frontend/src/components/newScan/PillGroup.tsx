import { useId } from "react";
import { cn } from "../../lib/cn";

export type PillOption<T extends string> = {
  value: T;
  label: string;
  hint?: string;
  disabled?: boolean;
};

/**
 * A short, exclusive choice as a segmented control.
 *
 * Native radios, so it is a real radio group: arrow keys move between the
 * options, the group is named by its label, and each segment's hint is its
 * own description. The segment *is* the label, so the 44 px target is the
 * whole thing. Replaces a `<select>` and a column of radio cards for
 * choices with two or three options that fit on one line. It is drawn like
 * the scan-type tabs above the form, but it is not a tab list: choosing a
 * segment changes a setting, not the panel.
 *
 * `layout="list"` draws the same radio group as a column of classic radio
 * buttons, each with its own hint under its label. It is for options whose
 * labels are a phrase each and do not fit on one line, where segments
 * would wrap into an uneven block (first used by the inspector's
 * "Checked by a person" choice). Same native radios, legend and keys, so
 * the two layouts behave the same; only the drawing differs. As in the
 * segments, the real radio covers its whole row, invisible, so the row is
 * the target (SC 2.5.5 Target Size (Enhanced), Level AAA), and a 22 px
 * circle like the shared Checkbox is drawn for it, its dot kept in forced
 * colors. The option's words are its label and so its name; its hint sits
 * outside the label and is its description (aria-describedby), read with
 * it, not a live region.
 */
export default function PillGroup<T extends string>({
  label,
  hint,
  value,
  onChange,
  options,
  name,
  layout = "pills",
}: {
  label: string;
  hint?: string;
  value: T;
  onChange: (value: T) => void;
  options: ReadonlyArray<PillOption<T>>;
  name: string;
  /** Segments on one line (the default), or a column of classic radios. */
  layout?: "pills" | "list";
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const chosen = options.find((option) => option.value === value);
  if (layout === "list") {
    return (
      <fieldset className="m-0 min-w-0 border-0 p-0" aria-describedby={hint ? hintId : undefined}>
        <legend className="p-0 text-sm font-semibold text-fg">{label}</legend>
        {hint && (
          <p id={hintId} className="mt-0.5 text-xs text-fg-muted">
            {hint}
          </p>
        )}
        <div className="mt-1 flex flex-col">
          {options.map((option) => {
            const optionId = `${id}-${option.value}`;
            const optionHintId = `${optionId}-hint`;
            const selected = option.value === value;
            return (
              <div
                key={option.value}
                className={cn(
                  "relative flex min-h-target items-start gap-3 rounded-xs px-2 py-2 text-sm",
                  option.disabled ? "opacity-60" : "hover:bg-surface-muted",
                  "has-[:focus-visible]:outline has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-umich-blue",
                )}
              >
                {/* The drawn radio. Its ring is a border, which forced colors
                    keep; the dot opts out of forced colors and uses the
                    system text colour, so the checked state still shows. */}
                <span
                  aria-hidden
                  className={cn(
                    "mt-0.5 grid h-[22px] w-[22px] shrink-0 place-items-center rounded-full border-2 bg-surface",
                    selected ? "border-umich-blue" : "border-border-strong",
                  )}
                >
                  {selected && (
                    <span className="h-2.5 w-2.5 rounded-full bg-umich-blue forced-color-adjust-none forced-colors:bg-[CanvasText]" />
                  )}
                </span>
                <span className="min-w-0">
                  <label htmlFor={optionId} className="block font-medium text-fg">
                    {option.label}
                  </label>
                  {option.hint && (
                    <span id={optionHintId} className="mt-0.5 block text-xs text-fg-muted">
                      {option.hint}
                    </span>
                  )}
                </span>
                {/* The real radio covers the whole row, invisible, as in the
                    segmented layout: the row is its 44 px target. It is not
                    inside the label, so the label (the option's words) is its
                    name and the hint is only its description. */}
                <input
                  id={optionId}
                  type="radio"
                  name={name}
                  value={option.value}
                  checked={selected}
                  disabled={option.disabled}
                  aria-describedby={option.hint ? optionHintId : undefined}
                  onChange={() => onChange(option.value)}
                  className={cn(
                    "absolute inset-0 m-0 h-full w-full appearance-none rounded-xs opacity-0",
                    option.disabled ? "cursor-not-allowed" : "cursor-pointer",
                  )}
                />
              </div>
            );
          })}
        </div>
      </fieldset>
    );
  }
  return (
    <fieldset
      className="m-0 min-w-0 border-0 p-0"
      aria-describedby={hint ? hintId : undefined}
    >
      <legend className="p-0 text-sm font-semibold text-fg">{label}</legend>
      {hint && (
        <p id={hintId} className="mt-0.5 text-xs text-fg-muted">
          {hint}
        </p>
      )}
      <div className="mt-2 inline-flex max-w-full flex-wrap gap-1 rounded-md border border-border bg-surface-muted p-1">
        {options.map((option) => {
          const optionId = `${id}-${option.value}`;
          const selected = option.value === value;
          return (
            <label
              key={option.value}
              htmlFor={optionId}
              className={cn(
                "relative inline-flex min-h-target min-w-target items-center gap-2 rounded-xs px-4 text-sm font-semibold transition-colors duration-200 motion-reduce:transition-none",
                // The fill is dropped in forced colors and the radio is
                // invisible, so the chosen segment also gets an outline there.
                selected
                  ? "bg-umich-blue text-fg-inverse forced-colors:outline forced-colors:outline-2 forced-colors:-outline-offset-2"
                  : "text-fg hover:bg-surface",
                option.disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
                "has-[:focus-visible]:outline has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-umich-blue",
              )}
            >
              <input
                id={optionId}
                type="radio"
                name={name}
                value={option.value}
                checked={selected}
                disabled={option.disabled}
                onChange={() => onChange(option.value)}
                // The radio covers the whole segment, invisible: it is
                // the control's own hit area and what a tool measures, not
                // a painted stand-in for a 1 px input hidden elsewhere.
                className="absolute inset-0 m-0 h-full w-full cursor-[inherit] appearance-none rounded-xs opacity-0"
              />
              {option.label}
            </label>
          );
        })}
      </div>
      {chosen?.hint && (
        <p className="mt-2 text-xs text-fg-muted" aria-live="polite">
          {chosen.hint}
        </p>
      )}
    </fieldset>
  );
}
