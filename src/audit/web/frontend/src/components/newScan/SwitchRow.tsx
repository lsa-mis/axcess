import { useId } from "react";
import { cn } from "../../lib/cn";

/**
 * An on/off setting drawn as a switch.
 *
 * The switch *is* the checkbox: a native `<input type="checkbox">` with
 * `role="switch"`, `appearance: none`, and the knob drawn as its `::before`.
 * So the thing you see is the thing you click, focus, and measure — no
 * hidden input behind a painted track — and it toggles with Space, reads as
 * "switch, on/off", and needs no script to be a control. The label is the
 * name and the hint is the description, never part of the name. The whole
 * row is the 52 px hit target.
 *
 * Motion: the knob slides 200 ms; `motion-reduce:` stops it. State is
 * carried by position, track colour, and the checkbox itself, never by the
 * animation alone.
 */
export default function SwitchRow({
  id,
  checked,
  onChange,
  label,
  hint,
  tone = "neutral",
  disabled = false,
  error,
  describedBy,
}: {
  id?: string;
  checked: boolean;
  onChange: (on: boolean) => void;
  label: string;
  hint?: string;
  tone?: "neutral" | "warning";
  disabled?: boolean;
  /** An inline problem with this setting, announced and shown beside it. */
  error?: string;
  describedBy?: string;
}) {
  const generated = useId();
  const inputId = id ?? generated;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const description = [hint ? hintId : null, error ? errorId : null, describedBy]
    .filter(Boolean)
    .join(" ");
  const warn = tone === "warning" && checked;

  return (
    <div className="min-w-0">
      <label
        htmlFor={inputId}
        className={cn(
          "group flex min-h-[52px] items-start gap-3.5 rounded-xs border border-transparent px-2.5 py-2 text-sm transition-colors duration-150 motion-reduce:transition-none",
          disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer hover:bg-surface-muted",
          warn && "border-sev-major/60 bg-sev-major-bg/40",
        )}
      >
        <input
          id={inputId}
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={description || undefined}
          onChange={(event) => onChange(event.target.checked)}
          className={cn(
            "relative mt-0.5 h-[26px] w-[46px] shrink-0 cursor-[inherit] appearance-none rounded-full border-0 bg-border-strong transition-colors duration-200 motion-reduce:transition-none",
            "checked:bg-umich-blue",
            "before:absolute before:left-[3px] before:top-[3px] before:h-5 before:w-5 before:rounded-full before:bg-surface before:shadow-[0_1px_2px_rgba(0,0,0,0.3)] before:transition-transform before:duration-200 before:ease-out before:content-[''] motion-reduce:before:transition-none",
            "checked:before:translate-x-5",
            "focus:outline-none focus-visible:outline focus-visible:outline-[3px] focus-visible:outline-offset-2 focus-visible:outline-umich-blue",
          )}
        />
        <span className="flex min-w-0 flex-col gap-0.5 text-fg">
          <span className="font-semibold leading-snug">{label}</span>
          {hint && (
            <span id={hintId} className="text-xs leading-snug text-fg-muted">
              {hint}
            </span>
          )}
        </span>
      </label>
      {error && (
        <p id={errorId} role="alert" className="ml-[66px] mt-0.5 text-xs font-semibold text-sev-major">
          {error}
        </p>
      )}
    </div>
  );
}
