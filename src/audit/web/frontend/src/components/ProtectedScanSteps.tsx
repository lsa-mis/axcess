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
    label: "Set scope",
    detail: "Record authorization and the exact application and sign-in origins.",
  },
  {
    key: "pair",
    label: "Connect browser",
    detail: "Open the protected Chromium window on your computer.",
  },
  {
    key: "sign_in",
    label: "Sign in yourself",
    detail: "Complete password, passkey, or 2FA in the visible browser window.",
  },
  {
    key: "scan",
    label: "Scan",
    detail: "Axcess verifies the approved page, then checks the read-only scope.",
  },
  {
    key: "report",
    label: "Review report",
    detail: "Open the issue table and download the available report.",
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
      className={`rounded-md border border-border bg-surface p-5 shadow-card ${className}`}
      aria-labelledby="protected-scan-steps-title"
    >
      <div className="max-w-3xl">
        <p className="text-xs font-semibold uppercase tracking-wide text-umich-blue">
          Login before scanning
        </p>
        <h2 id="protected-scan-steps-title" className="mt-1 text-lg font-semibold text-fg">
          How the secure browser flow works
        </h2>
        <p className="mt-1 text-sm text-fg-muted">
          Your password and 2FA stay between you and the website. Checking starts
          only after Axcess confirms an approved post-login page.
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
                      ? "border-umich-blue bg-umich-blue text-white"
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
