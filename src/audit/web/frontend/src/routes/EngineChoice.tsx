import type { NewScanPayload } from "../api/types";

/** One full-row, keyboard-native choice in the scan-engine radio group. */
export default function EngineChoice({
  value,
  selected,
  onChange,
  label,
  hint,
  disabled = false,
}: {
  value: NewScanPayload["scan_engine"];
  selected: NewScanPayload["scan_engine"];
  onChange: (value: NewScanPayload["scan_engine"]) => void;
  label: string;
  hint: string;
  disabled?: boolean;
}) {
  const id = `scan-engine-${value}`;
  return (
    // The native radio is nested inside this label and is also explicitly
    // connected through htmlFor/id. The lint rule cannot statically follow
    // the runtime-generated id, but browsers and assistive tech can.
    // eslint-disable-next-line jsx-a11y/label-has-associated-control
    <label
      htmlFor={id}
      className={`flex min-h-target cursor-pointer items-start gap-3 rounded-xs border p-3 text-sm ${
        selected === value ? "border-umich-blue bg-umich-blue/5" : "border-border"
      } ${disabled ? "cursor-not-allowed opacity-60" : "hover:bg-surface-muted"}`}
    >
      <input
        id={id}
        type="radio"
        name="scan-engine"
        value={value}
        checked={selected === value}
        disabled={disabled}
        onChange={() => onChange(value)}
        className="mt-0.5 h-[22px] w-[22px] shrink-0 border-2 border-border-strong text-umich-blue focus:outline-none"
      />
      <span>
        <span className="block font-semibold text-fg">{label}</span>
        <span className="block text-xs text-fg-muted">{hint}</span>
      </span>
    </label>
  );
}
