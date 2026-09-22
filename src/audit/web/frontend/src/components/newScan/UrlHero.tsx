import type { Ref } from "react";
import type { ScopePreview } from "../../api/types";
import { cn } from "../../lib/cn";
import ScopeLine from "./ScopeLine";
import type { ScopePreviewState } from "./useScopePreview";

/**
 * The one field every scan needs, treated as the page's hero input.
 *
 * The label is the name and nothing else. The help text, the live scope
 * line and any error are *descriptions*, wired with `aria-describedby`, and
 * an error also sets `aria-invalid` so the field itself reports its state.
 * The previous markup nested help and preview inside the `<label>`, which
 * made the accessible name a whole paragraph.
 *
 * No `required`: the browser's own bubble would fight the form's alert,
 * which is announced, focused and links back here.
 */
export default function UrlHero({
  id,
  label,
  help,
  placeholder,
  value,
  onChange,
  preview,
  error,
  afterSignIn = false,
  autoFocus = false,
  inputRef,
}: {
  id: string;
  label: string;
  help: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  preview: { state: ScopePreviewState; data: ScopePreview | null };
  error?: string;
  afterSignIn?: boolean;
  autoFocus?: boolean;
  inputRef?: Ref<HTMLInputElement>;
}) {
  const helpId = `${id}-help`;
  const scopeId = `${id}-scope`;
  const errorId = `${id}-error`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-base font-semibold text-fg">
        {label}
      </label>
      <p id={helpId} className="text-sm text-fg-muted">
        {help}
      </p>
      <input
        ref={inputRef}
        id={id}
        type="url"
        inputMode="url"
        autoComplete="url"
        spellCheck={false}
        autoFocus={autoFocus}
        placeholder={placeholder}
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={[helpId, error ? errorId : scopeId].join(" ")}
        onChange={(event) => onChange(event.target.value)}
        className={cn(
          "min-h-[52px] rounded-xs border-2 bg-surface px-4 py-3 text-base text-fg focus:border-umich-blue focus:outline-none",
          error ? "border-sev-critical" : "border-border",
        )}
      />
      {error ? (
        <p id={errorId} className="mt-1 text-sm font-semibold text-sev-critical">
          {error}
        </p>
      ) : (
        <ScopeLine id={scopeId} state={preview.state} data={preview.data} afterSignIn={afterSignIn} />
      )}
    </div>
  );
}
