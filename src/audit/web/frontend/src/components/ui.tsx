import type { ReactNode } from "react";
import { cn } from "../lib/cn";
import type { Severity, FindingStatus } from "../api/types";

/** Severity chip — pairs color + text, so the signal isn't color-only. */
export function SeverityChip({ value }: { value: Severity }) {
  return <span className={cn("sev-chip", `sev-chip--${value}`)}>{value}</span>;
}

/** Status chip that uses neutral surfaces — we DON'T color-code status,
 * because status is intentionally user-workflow, not severity. */
export function StatusChip({ value }: { value: FindingStatus }) {
  return (
    <span className="inline-flex items-center rounded-xs border border-border bg-surface-muted px-2 py-0.5 text-2xs font-medium uppercase tracking-wide text-fg-muted">
      {value.replace(/_/g, " ")}
    </span>
  );
}

/** Card container with a subtle shadow; Siteimprove-inspired. */
export function Card({
  children,
  className,
  ...rest
}: { children: ReactNode; className?: string } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xs border border-border bg-surface shadow-card",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

/** Stat "pill" — big number, small label. Dashboard grid's bread + butter. */
export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: number | string;
  hint?: string;
  tone?: "default" | "critical" | "major" | "minor" | "info";
}) {
  return (
    <Card className="p-4">
      <div className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">
        {label}
      </div>
      <div
        className={cn(
          "mt-1 text-3xl font-semibold tabular-nums",
          tone === "critical" && "text-sev-critical",
          tone === "major" && "text-sev-major",
          tone === "minor" && "text-sev-minor",
          tone === "info" && "text-fg",
          tone === "default" && "text-umich-blue",
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-fg-muted">{hint}</div>}
    </Card>
  );
}

/** Page header — breadcrumb + title + trailing actions. */
export function PageHeader({
  title,
  subtitle,
  crumbs,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  crumbs?: { label: string; to?: string }[];
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6">
      {crumbs && (
        <nav aria-label="Breadcrumb" className="mb-1 text-xs text-fg-subtle">
          <ol className="flex items-center gap-1">
            {crumbs.map((c, i) => (
              <li key={i} className="flex items-center gap-1">
                {c.to ? (
                  <a
                    className="text-fg-muted no-underline hover:underline"
                    href={c.to}
                  >
                    {c.label}
                  </a>
                ) : (
                  <span aria-current="page" className="text-fg">
                    {c.label}
                  </span>
                )}
                {i < crumbs.length - 1 && <span aria-hidden>›</span>}
              </li>
            ))}
          </ol>
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-fg">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-0.5 text-sm text-fg-muted">{subtitle}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

/** Empty-state block, used when lists come back empty. */
export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <Card className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <h2 className="text-base font-semibold text-fg">{title}</h2>
      {message && (
        <p className="max-w-md text-sm text-fg-muted">{message}</p>
      )}
      {action && <div className="mt-2">{action}</div>}
    </Card>
  );
}

/** Flat button variants — kept tiny; use `<a>` + cn() for links. */
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
};
export function Button({
  variant = "secondary",
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center gap-1.5 rounded-xs px-3 py-1.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-60",
        variant === "primary" &&
          "bg-umich-blue text-fg-inverse hover:bg-umich-blue-600",
        variant === "secondary" &&
          "border border-border bg-surface text-fg hover:bg-surface-muted",
        variant === "danger" &&
          "bg-sev-critical text-fg-inverse hover:brightness-110",
        variant === "ghost" && "bg-transparent text-fg hover:bg-surface-muted",
        className,
      )}
      {...rest}
    />
  );
}

/** Alt-attribute pill (missing / empty / authored) — Siteimprove-style tag. */
export function AltTag({ value }: { value: string | null }) {
  if (value === null) {
    return (
      <span className="inline-flex items-center rounded-xs border border-sev-critical/40 bg-sev-critical-bg px-2 py-0.5 text-2xs font-semibold uppercase tracking-wide text-sev-critical">
        missing
      </span>
    );
  }
  if (value === "") {
    return (
      <span className="inline-flex items-center rounded-xs border border-border bg-surface-muted px-2 py-0.5 font-mono text-2xs text-fg-muted">
        alt=""
      </span>
    );
  }
  return (
    <span
      className="block max-w-full truncate text-xs text-fg"
      title={value}
    >
      &ldquo;{value}&rdquo;
    </span>
  );
}
