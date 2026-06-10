/**
 * Shared primitives. Everything interactive here is keyboard operable,
 * shows the global focus ring, and exposes correct name, role, value.
 */

import type { ReactNode } from "react";
import { TIER_LABEL } from "../data/types";
import type { Severity, Tier } from "../data/types";

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

const TIER_BG: Record<Tier, string> = {
  automated: "bg-tier-automated",
  ai_assisted: "bg-tier-ai",
  agentic: "bg-tier-agentic",
  manual: "bg-tier-manual",
  local_vlm: "bg-tier-vlm",
};

/** Badge naming the tier that owns or found a check. White on dark, 7:1. */
export function TierBadge({ tier }: { tier: Tier }) {
  return (
    <span
      className={cn(
        "inline-block rounded px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-white",
        TIER_BG[tier],
      )}
    >
      {TIER_LABEL[tier]}
    </span>
  );
}

const SEV_BG: Record<Severity, string> = {
  critical: "bg-sev-critical",
  serious: "bg-sev-serious",
  moderate: "bg-sev-moderate",
  minor: "bg-sev-minor",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={cn(
        "inline-block rounded px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-white",
        SEV_BG[severity],
      )}
    >
      {severity}
    </span>
  );
}

export function SampleTag() {
  return (
    <span className="inline-block rounded border border-line bg-paper-muted px-1.5 py-0.5 text-xs font-semibold text-ink-muted">
      Sample
    </span>
  );
}

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("rounded border border-line bg-paper", className)}>
      {children}
    </div>
  );
}

export function PageTitle({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold text-ink">{title}</h1>
        {subtitle ? <p className="mt-1 text-ink-muted">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "danger";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary: "bg-brand text-white hover:bg-[#003a70]",
  secondary: "border border-line bg-paper text-ink hover:bg-paper-muted",
  danger: "bg-sev-critical text-white hover:bg-[#8f1a1a]",
};

export function Button({
  variant = "secondary",
  className,
  type = "button",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
}) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex min-h-target items-center justify-center gap-2 rounded px-4 py-2 font-semibold",
        "disabled:cursor-not-allowed disabled:opacity-60",
        BUTTON_VARIANT[variant],
        className,
      )}
      {...rest}
    />
  );
}

export function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="font-semibold text-ink">
        {label}
      </label>
      {hint ? (
        <p id={`${htmlFor}-hint`} className="text-sm text-ink-muted">
          {hint}
        </p>
      ) : null}
      {children}
    </div>
  );
}

export const inputClass =
  "min-h-target rounded border border-line bg-paper px-3 py-2 text-base text-ink";
