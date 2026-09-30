import { useEffect, useRef } from "react";
import { AlertOctagon } from "lucide-react";
import { ERRORS } from "./copy";
import type { FieldError, FieldKey } from "./scanPolicy";

/**
 * The one place a failed submit is reported.
 *
 * It is an alert, it takes focus the moment it appears, and each line is a
 * link that moves focus to the control at fault, so a keyboard or
 * screen-reader user who pressed Start at the bottom of a long form is told
 * what happened and taken there. The public form used to render a card with
 * neither, and to *disable* the button instead, which explains nothing.
 */
export default function FormErrorAlert({
  errors,
  fieldIds,
  title = ERRORS.title,
}: {
  errors: FieldError[];
  /** The DOM id of each field an error can name, for the alert's links. */
  fieldIds: Partial<Record<FieldKey, string>>;
  title?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // Re-focus whenever the set of errors changes, not only when it first
  // appears: a second failed submit with a different message is a new
  // event the reader has to hear.
  const signature = errors.map((error) => `${error.field}:${error.message}`).join("|");
  useEffect(() => {
    if (signature) ref.current?.focus();
  }, [signature]);

  if (errors.length === 0) return null;

  const focusField = (field: FieldKey) => {
    const id = fieldIds[field];
    const element = id ? document.getElementById(id) : null;
    element?.focus();
    element?.scrollIntoView({ block: "center" });
  };

  return (
    <div
      ref={ref}
      role="alert"
      tabIndex={-1}
      className="flex items-start gap-3 rounded-xs border border-sev-critical/50 bg-sev-critical-bg p-4 text-sm text-fg focus:outline-none focus-visible:shadow-focus"
    >
      <AlertOctagon className="mt-0.5 h-5 w-5 shrink-0 text-sev-critical" aria-hidden />
      <div className="min-w-0">
        <p className="font-semibold text-sev-critical">{title}</p>
        <p className="mt-1 text-fg-muted">{ERRORS.lead}</p>
        <ul className="mt-2 flex flex-col gap-1">
          {errors.map((error) => (
            <li key={`${error.field}:${error.message}`}>
              {fieldIds[error.field] ? (
                <a
                  href={`#${fieldIds[error.field]}`}
                  onClick={(event) => {
                    event.preventDefault();
                    focusField(error.field);
                  }}
                  className="report-link inline-flex min-h-target items-center font-semibold"
                >
                  {error.message}
                </a>
              ) : (
                <span className="inline-flex min-h-target items-center">{error.message}</span>
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
