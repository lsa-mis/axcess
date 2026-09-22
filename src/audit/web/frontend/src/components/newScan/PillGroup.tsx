import { useId } from "react";
import { cn } from "../../lib/cn";

export type PillOption<T extends string> = {
  value: T;
  label: string;
  hint?: string;
  disabled?: boolean;
};

/**
 * A short, exclusive choice as a row of pills.
 *
 * Native radios, so it is a real radio group: arrow keys move between the
 * options, the group is named by its label, and each pill's hint is its own
 * description. The pill *is* the label, so the 44 px target is the whole
 * thing. Replaces a `<select>` and a column of radio cards for choices with
 * two or three options that fit on one line.
 */
export default function PillGroup<T extends string>({
  label,
  hint,
  value,
  onChange,
  options,
  name,
}: {
  label: string;
  hint?: string;
  value: T;
  onChange: (value: T) => void;
  options: ReadonlyArray<PillOption<T>>;
  name: string;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const chosen = options.find((option) => option.value === value);
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
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map((option) => {
          const optionId = `${id}-${option.value}`;
          const selected = option.value === value;
          return (
            <label
              key={option.value}
              htmlFor={optionId}
              className={cn(
                "relative inline-flex min-h-target items-center gap-2 rounded-full border-2 px-4 text-sm font-semibold transition-colors duration-200 motion-reduce:transition-none",
                selected
                  ? "border-umich-blue bg-umich-blue text-fg-inverse"
                  : "border-border-strong bg-surface text-fg hover:border-umich-blue",
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
                // The radio covers the whole pill, invisible: the pill is
                // the control's own hit area and what a tool measures, not
                // a painted stand-in for a 1 px input hidden elsewhere.
                className="absolute inset-0 m-0 h-full w-full cursor-[inherit] appearance-none rounded-full opacity-0"
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
