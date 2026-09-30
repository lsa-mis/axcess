import { useId, type Ref } from "react";
import { cn } from "../../lib/cn";

/**
 * A labelled number input with an optional hint, both wired for a screen
 * reader: the label is the name, the hint and any error are the description.
 *
 * min-h-target keeps the input at the SC 2.5.5 floor; px-3 leaves room for
 * the spinner controls browsers add.
 *
 * An empty box is `NaN`, not 0: `Number("")` is 0, which snapped a cleared
 * field back to "0" before the next digit could be typed and then posted a
 * scan of zero pages. The caller validates `NaN` like any other bad value.
 */
export default function NumberField({
  id,
  label,
  value,
  onChange,
  min,
  max,
  step,
  hint,
  error,
  disabled = false,
  inputRef,
  className,
  inputClassName,
}: {
  id?: string;
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
  error?: string;
  disabled?: boolean;
  inputRef?: Ref<HTMLInputElement>;
  className?: string;
  /** Width for the box alone, so a long hint can still use the column. */
  inputClassName?: string;
}) {
  const generated = useId();
  const inputId = id ?? generated;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <label htmlFor={inputId} className="text-sm font-semibold text-fg">
        {label}
      </label>
      <input
        ref={inputRef}
        id={inputId}
        type="number"
        inputMode="decimal"
        value={Number.isFinite(value) ? value : ""}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        onChange={(event) => {
          const raw = event.target.value.trim();
          onChange(raw === "" ? Number.NaN : Number(raw));
        }}
        className={cn(
          "min-h-target rounded-xs border bg-surface px-3 py-2 text-base font-normal text-fg focus:border-umich-blue focus:outline-none disabled:cursor-not-allowed disabled:opacity-60",
          error ? "border-sev-critical" : "border-border",
          inputClassName,
        )}
      />
      {hint && (
        <p id={hintId} className="text-xs text-fg-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs font-semibold text-sev-critical">
          {error}
        </p>
      )}
    </div>
  );
}
