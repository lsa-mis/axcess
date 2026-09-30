import { Check } from "lucide-react";

export type ProtectedScanStage =
  | "scope"
  | "pair"
  | "sign_in"
  | "scan"
  | "report";

const STEPS: Array<{
  key: ProtectedScanStage;
  label: string;
  detail: string;
}> = [
  {
    key: "scope",
    label: "Choose what to scan",
    detail: "Confirm you have permission, and give the exact website and sign-in addresses (origins).",
  },
  {
    key: "pair",
    label: "Open browser",
    detail: "Axcess opens a separate, protected Chromium browser window on your computer.",
  },
  {
    key: "sign_in",
    label: "Sign in yourself",
    detail: "Enter your password, passkey, or two-step sign-in (2FA) in that browser window.",
  },
  {
    key: "scan",
    label: "Scan",
    detail: "Axcess confirms it reached the approved page. Then it checks the pages you chose, without changing anything (read-only).",
  },
  {
    key: "report",
    label: "Review report",
    detail: "Open the Issues table, and download the report if you need it.",
  },
];

/**
 * A concise, screen-reader-friendly explanation of the authenticated scan.
 * It describes product states rather than deployment internals and never
 * implies that the web UI receives a credential or controls the login form.
 */
export default function ProtectedScanSteps({
  current,
  className = "",
}: {
  current: ProtectedScanStage;
  className?: string;
}) {
  const currentIndex = STEPS.findIndex((step) => step.key === current);

  return (
    <section
      className={`rounded-xs border border-border bg-surface p-5 shadow-card ${className}`}
      aria-labelledby="protected-scan-steps-title"
    >
      <div className="max-w-3xl">
        <p className="text-xs font-semibold text-umich-blue">
          Sign in before scanning
        </p>
        <h2 id="protected-scan-steps-title" className="mt-1 text-lg font-semibold text-fg">
          How a sign-in scan works
        </h2>
        <p className="mt-1 text-sm text-fg-muted">
          Only you and the website see your password and two-step sign-in (2FA).
          Axcess starts checking only after it confirms you reached an approved
          page after sign-in.
        </p>
      </div>

      <ol className="mt-5 grid gap-3 lg:grid-cols-5">
        {STEPS.map((step, index) => {
          const complete = index < currentIndex;
          const active = index === currentIndex;
          return (
            <li
              key={step.key}
              aria-current={active ? "step" : undefined}
              className={`rounded-xs border p-3 ${
                active
                  ? "border-umich-blue bg-umich-blue/5"
                  : "border-border bg-surface-muted/60"
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${
                    complete
                      ? "border-umich-blue bg-umich-blue text-fg-inverse"
                      : active
                        ? "border-umich-blue bg-surface text-umich-blue"
                        : "border-border bg-surface text-fg-muted"
                  }`}
                  aria-hidden="true"
                >
                  {complete ? <Check className="h-4 w-4" /> : index + 1}
                </span>
                <span className="font-semibold text-fg">{step.label}</span>
              </div>
              <p className="mt-2 text-xs leading-relaxed text-fg-muted">{step.detail}</p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
