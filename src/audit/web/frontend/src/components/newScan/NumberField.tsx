import { useId, type Ref } from "react";
import { cn } from "../../lib/cn";

/**
 * A labelled number input with an optional hint, both wired for a screen
 * reader: the label is the name, the hint and any error are the description.
 *
 * min-h-target keeps the input at the SC 2.5.5 floor; px-3 leaves room for
 * the spinner controls browsers add.
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
}) {
  const generated = useId();
  const inputId = id ?? generated;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ");
  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <label htmlFor={inputId} className="text-xs font-semibold text-fg-subtle">
        {label}
      </label>
      <input
        ref={inputRef}
        id={inputId}
        type="number"
        inputMode="decimal"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        onChange={(event) => onChange(Number(event.target.value))}
        className={cn(
          "min-h-target rounded-xs border bg-surface px-3 py-2 text-base font-normal text-fg focus:border-umich-blue focus:outline-none disabled:cursor-not-allowed disabled:opacity-60",
          error ? "border-sev-critical" : "border-border",
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
