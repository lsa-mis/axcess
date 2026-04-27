import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { Link } from "react-router-dom";
import { cn } from "../lib/cn";
import type { Severity, FindingStatus, ScanStatus } from "../api/types";

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
                  // Must be a Router <Link>, not a raw <a href>: the SPA is
                  // mounted under basename="/app", and a raw anchor would
                  // navigate to ``/scans`` (legacy Jinja UI) instead of the
                  // SPA's ``/app/scans`` route. Same goes for any internal
                  // breadcrumb target — always Link, never <a>.
                  <Link
                    className="text-fg-muted no-underline hover:underline"
                    to={c.to}
                  >
                    {c.label}
                  </Link>
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

/**
 * Shared chrome for ``Button`` and ``LinkButton`` so a primary <button>
 * and a primary <Link>-styled-as-button look identical. Keeping this in
 * one place is the single source of truth for action affordances — if a
 * designer changes "primary" to a different blue, both elements update.
 */
type Variant = "primary" | "secondary" | "danger" | "ghost";

const BUTTON_BASE =
  "inline-flex items-center gap-1.5 rounded-xs px-3 py-1.5 text-sm font-semibold transition-colors no-underline disabled:cursor-not-allowed disabled:opacity-60";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-umich-blue text-fg-inverse hover:bg-umich-blue-600",
  secondary:
    "border border-border bg-surface text-fg hover:bg-surface-muted",
  danger: "bg-sev-critical text-fg-inverse hover:brightness-110",
  ghost: "bg-transparent text-fg hover:bg-surface-muted",
};

/** Flat button variants. */
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
};
export function Button({
  variant = "secondary",
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cn(BUTTON_BASE, VARIANT_CLASSES[variant], className)}
      {...rest}
    />
  );
}

/**
 * Internal styled link that LOOKS like a button. Always renders a Router
 * ``<Link>`` so the SPA basename is honored and the click is intercepted
 * — never a raw ``<a href>`` (which under ``basename="/app"`` would
 * silently navigate to the legacy Jinja UI).
 *
 * Use this anywhere a styled "go to another SPA route" affordance is
 * needed; reach for plain ``<Link>`` only when you need link styling
 * (an inline body link), and for ``<a target="_blank">`` only when the
 * destination is genuinely external.
 */
type LinkButtonProps = ComponentPropsWithoutRef<typeof Link> & {
  variant?: Variant;
};
export function LinkButton({
  variant = "secondary",
  className,
  ...rest
}: LinkButtonProps) {
  return (
    <Link
      className={cn(BUTTON_BASE, VARIANT_CLASSES[variant], className)}
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

/**
 * Color-coded scan status. Unlike findings (where status is workflow and we
 * stay neutral), scan status is operational state — running scans want a
 * "live" pulse, failures want red, interrupted wants amber. This is the
 * only place in the SPA we color-code status.
 *
 * Color is paired with text and an aria-label so screen readers and
 * deuteranopes get the same signal.
 */
const SCAN_STATUS_CLASS: Record<ScanStatus, string> = {
  running:
    "border-umich-blue/50 bg-umich-blue/10 text-umich-blue animate-pulse",
  completed: "border-border bg-surface-muted text-fg-muted",
  failed: "border-sev-critical/40 bg-sev-critical-bg text-sev-critical",
  interrupted: "border-sev-major/40 bg-sev-major-bg text-sev-major",
};
export function ScanStatusBadge({ value }: { value: ScanStatus }) {
  return (
    <span
      aria-label={`Scan status: ${value}`}
      className={cn(
        "inline-flex items-center rounded-xs border px-2 py-0.5 text-2xs font-semibold uppercase tracking-wide",
        SCAN_STATUS_CLASS[value],
      )}
    >
      {value}
    </span>
  );
}

/**
 * Render an ISO-8601 timestamp as a short, human-friendly relative string
 * (``"2h ago"``, ``"3d ago"``). Returns ``"—"`` for null/empty input so
 * callers don't have to guard.
 *
 * We round down — "59 minutes" reads as "59m ago", not "1h ago" — because
 * scan timing matters for the user ("did this finish recently?") and
 * over-rounding hides recency. The full ISO timestamp should be passed
 * via a ``title`` attribute on the wrapping element so hovering reveals
 * the exact moment; this helper only formats, it doesn't render.
 */
export function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "—";
  const seconds = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  const years = Math.floor(days / 365);
  return `${years}y ago`;
}
