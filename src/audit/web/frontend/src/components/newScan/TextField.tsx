import { useId } from "react";
import { cn } from "../../lib/cn";

/**
 * A labelled one-line text input with an optional hint and error, wired the
 * way `NumberField` is: the label is the input's name (H44, a `<label for>`),
 * and the hint and the error are its description (`aria-describedby`), so a
 * screen reader hears what to type and what went wrong with the field itself
 * (SC 3.3.1 Error Identification and SC 3.3.2 Labels or Instructions, both
 * Level A).
 *
 * New because nothing fitted. `NumberField` turns what is typed into a
 * number (an empty box is NaN), so text would need a second mode through
 * all of it; `UrlHero` is the page's address card, with its scope preview.
 * First used for the typed browser name (user agent) on New scan.
 *
 * The hint sits between the label and the box, as in the shared `Select`,
 * so the instruction is read before typing. Prefer no `maxLength` for a
 * limit the form checks: the browser cuts a long paste short without a
 * word, where the form's check says what the limit is (SC 3.3.1).
 *
 * `spellCheck`, `autoCapitalize` and `autoCorrect` are off: the text is
 * machine-read, and a corrected word would be sent as typed by the browser,
 * not by the person. `font-mono` keeps look-alike characters apart.
 */
export default function TextField({
  id,
  label,
  value,
  onChange,
  hint,
  error,
  maxLength,
  className,
}: {
  id?: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  error?: string;
  maxLength?: number;
  className?: string;
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
      {hint && (
        <p id={hintId} className="text-xs text-fg-muted">
          {hint}
        </p>
      )}
      <input
        id={inputId}
        type="text"
        value={value}
        maxLength={maxLength}
        spellCheck={false}
        autoCapitalize="off"
        autoCorrect="off"
        autoComplete="off"
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy || undefined}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "min-h-target w-full min-w-0 rounded-xs border bg-surface px-3 py-2 font-mono text-sm text-fg focus:border-umich-blue focus:outline-none",
          error ? "border-sev-critical" : "border-border",
        )}
      />
      {error && (
        <p id={errorId} className="text-xs font-semibold text-sev-critical">
          {error}
        </p>
      )}
    </div>
  );
}
