import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { createElement, forwardRef, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Link } from "react-router";
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

/** Shared workspace surface with a quiet border and evidence-friendly depth. */
export function Card({
  children,
  className,
  ...rest
}: {
  children: ReactNode;
  className?: string;
} & React.HTMLAttributes<HTMLDivElement>) {
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

/** Compact metric surface with strong numeric hierarchy. */
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
    <Card className="relative overflow-hidden p-5 before:absolute before:inset-x-0 before:top-0 before:h-1 before:bg-umich-blue">
      <div className="text-xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
        {label}
      </div>
      <div
        className={cn(
          "mt-2 text-[2rem] font-semibold leading-none tracking-tight tabular-nums",
          tone === "critical" && "text-sev-critical",
          tone === "major" && "text-sev-major",
          tone === "minor" && "text-sev-minor",
          tone === "info" && "text-fg",
          tone === "default" && "text-umich-blue",
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-2 text-xs text-fg-muted">{hint}</div>}
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
    <header className="mb-5">
      {crumbs && (
        // The trail is the page's orientation line, so it stays quiet until
        // you reach for it: ancestors are muted and only underline on hover,
        // and the current page is the one weighted item. Underlining every
        // crumb by default made the row compete with the <h1> beneath it.
        <nav
          aria-label="Breadcrumb"
          className="mb-2.5 text-xs font-medium text-fg-subtle"
        >
          <ol className="flex flex-wrap items-center gap-1.5">
            {crumbs.map((c, i) => (
              <li key={i} className="flex items-center gap-1.5">
                {c.to ? (
                  // Must be a Router <Link>, not a raw <a href>: the SPA is
                  // mounted under basename="/app", and a raw anchor would
                  // navigate to ``/scans`` (legacy Jinja UI) instead of the
                  // SPA's ``/app/scans`` route. Same goes for any internal
                  // breadcrumb target — always Link, never <a>.
                  <Link
                    className="rounded-2xs text-fg-muted no-underline hover:text-fg hover:underline hover:underline-offset-2"
                    to={c.to}
                  >
                    {c.label}
                  </Link>
                ) : (
                  <span
                    aria-current="page"
                    className="font-semibold text-fg"
                  >
                    {c.label}
                  </span>
                )}
                {i < crumbs.length - 1 && (
                  <ChevronRight
                    className="h-3.5 w-3.5 shrink-0 text-border-strong"
                    aria-hidden
                  />
                )}
              </li>
            ))}
          </ol>
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold leading-tight tracking-[-0.025em] text-fg sm:text-[1.75rem]">
            {title}
          </h1>
          {subtitle && (
            <p className="mt-1 max-w-4xl text-sm leading-6 text-fg-muted">
              {subtitle}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        )}
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
      {message && <p className="max-w-md text-sm text-fg-muted">{message}</p>}
      {action && <div className="mt-2">{action}</div>}
    </Card>
  );
}

/**
 * Shared chrome for ``Button`` and ``LinkButton`` so a primary <button>
 * and a primary <Link>-styled-as-button look identical. Keeping this in
 * one place is the single source of truth for action affordances — if a
 * designer changes "primary" to a different blue, both elements update.
 *
 * **Sizing.** Three sizes, all of which clear the WCAG 2.2 SC 2.5.5
 * (AAA, 44×44) floor. The `size` prop is therefore *visual emphasis*,
 * not a way to drop below the floor:
 *
 * - `lg` — primary page-level CTA. Use when there is exactly one
 *   "the thing the user came here to do" on a route ("Start crawl",
 *   "Start a new scan", "Save"). Larger type, more padding, stands out
 *   in the visual hierarchy.
 * - `md` — every other action. The default. Buttons in cards, table
 *   row actions, modal confirms, secondary affordances. Still 44×44.
 * - `sm` — *only* dense table cells where a 44px button would crowd
 *   the row layout. Pairs with `min-h-target` on the parent `<td>` so
 *   the *click target* is still 44×44 even though the chip is shorter.
 *   Use sparingly; if you reach for `sm`, double-check the layout
 *   actually needs it.
 *
 * **Why a baseline of `md` = 44px.** The Phase 1 baseline scan flagged
 * `py-1.5 text-sm` row buttons as ~30px tall — a SC 2.5.5 fail. The
 * earlier Phase 2 fix only addressed the checkbox; this sweep finishes
 * the job for the entire button surface.
 */
type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md" | "lg";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-xs font-semibold shadow-sm transition-[background-color,border-color,box-shadow,transform] duration-150 no-underline disabled:cursor-not-allowed disabled:opacity-60 active:translate-y-px";

const SIZE_CLASSES: Record<Size, string> = {
  // `sm` is sub-44px on its own — callers must wrap in a min-h-target cell
  // when used in tables. Documented above; not the default.
  sm: "px-2.5 py-1 text-xs",
  // `md` is the baseline — 44×44 hit target via min-h-target.
  md: "min-h-target px-4 py-2.5 text-sm",
  // `lg` is the primary-CTA size — 52px tall, larger type for visual weight.
  lg: "min-h-[52px] px-6 py-3 text-base",
};

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "border border-umich-blue bg-umich-blue text-fg-inverse hover:bg-umich-blue-600 hover:shadow-card",
  secondary:
    "border border-border-strong bg-surface text-fg hover:border-umich-blue hover:bg-surface-muted",
  danger:
    "border border-sev-critical bg-sev-critical text-fg-inverse hover:brightness-110",
  ghost:
    "border border-transparent bg-transparent text-fg shadow-none hover:bg-surface-muted",
};

/** Flat button variants. */
type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
};
// forwardRef so callers that must move focus back to the trigger — a
// disclosure closing on Escape, for one — can hold the element itself
// instead of re-querying the DOM for it.
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button({ variant = "secondary", size = "md", className, ...rest }, ref) {
    return (
      <button
        ref={ref}
        className={cn(
          BUTTON_BASE,
          SIZE_CLASSES[size],
          VARIANT_CLASSES[variant],
          className,
        )}
        {...rest}
      />
    );
  },
);

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
  size?: Size;
};
export function LinkButton({
  variant = "secondary",
  size = "md",
  className,
  ...rest
}: LinkButtonProps) {
  return (
    <Link
      className={cn(
        BUTTON_BASE,
        SIZE_CLASSES[size],
        VARIANT_CLASSES[variant],
        className,
      )}
      {...rest}
    />
  );
}

/**
 * Button-styled <a> that escapes the React-Router basename trap.
 *
 * The SPA is mounted at ``basename="/app"``, which means
 * ``<Link to="/api/scans/.../export/csv">`` rewrites to
 * ``/app/api/scans/.../export/csv`` — a path React Router doesn't
 * recognize, so the user sees a 404 page instead of the file. Even
 * ``reloadDocument`` doesn't help because the URL prefix has already
 * been applied by the time the browser navigates.
 *
 * For *server* paths that aren't part of the SPA's route tree
 * (everything under ``/api/*`` and the legacy ``/scans/*`` Jinja
 * routes), use this component, not :func:`LinkButton`. The plain
 * ``<a>`` makes a real browser request to the absolute URL, which
 * hits FastAPI's export route directly and triggers the download.
 */
type DownloadLinkProps = ComponentPropsWithoutRef<"a"> & {
  variant?: Variant;
  size?: Size;
};
export function DownloadLink({
  variant = "secondary",
  size = "md",
  className,
  download = true,
  children,
  ...rest
}: DownloadLinkProps) {
  return (
    <a
      className={cn(
        BUTTON_BASE,
        SIZE_CLASSES[size],
        VARIANT_CLASSES[variant],
        className,
      )}
      // `download` defaults to true because every current call site is
      // an export endpoint that returns Content-Disposition:
      // attachment. Pass ``download={false}`` if you need a styled link
      // that opens the response in the tab instead of downloading.
      {...(download ? { download: "" } : {})}
      {...rest}
    >
      {children}
    </a>
  );
}

/**
 * Button-styled <a> to a genuinely external destination.
 *
 * Distinct from :func:`DownloadLink` (same-origin server paths) and
 * :func:`LinkButton` (SPA routes): this one always opens a new tab and
 * always carries ``rel="noopener noreferrer"``, so the destination can
 * never reach back into this window. In the packaged desktop app the
 * Electron shell intercepts these and hands the URL to the system
 * browser, which is why the href must be http(s).
 *
 * Pass ``aria-label`` whenever the visible text is hidden at small
 * widths, and say "opens in a new tab" in it — the new window is a
 * change of context the user should hear about before they activate it
 * (WCAG 3.2.5).
 */
type ExternalLinkButtonProps = ComponentPropsWithoutRef<"a"> & {
  variant?: Variant;
  size?: Size;
};
export function ExternalLinkButton({
  variant = "secondary",
  size = "md",
  className,
  children,
  ...rest
}: ExternalLinkButtonProps) {
  return (
    <a
      className={cn(
        BUTTON_BASE,
        SIZE_CLASSES[size],
        VARIANT_CLASSES[variant],
        className,
      )}
      target="_blank"
      rel="noopener noreferrer"
      {...rest}
    >
      {children}
    </a>
  );
}

/**
 * Collapsible section with a caret, a heading-level toggle, and an
 * expanded-state background.
 *
 * We use a controlled ``useState`` toggle rather than the browser-native
 * ``<details>`` element for the same reason ``GroupedFindings`` does:
 * the surrounding components are already React, and mixing imperative
 * DOM state with React state is a footgun. Native ``<details>`` also
 * gives no way to style the open state of the summary row or to swap the
 * marker for our own caret, which is exactly the affordance users told
 * us was missing — nothing on the row said "this can be clicked" or
 * "this is now open".
 *
 * **The panel is always mounted and hidden with the ``hidden``
 * attribute, never conditionally rendered.** ``aria-controls`` must point
 * at an element that exists, or axe fails ``aria-valid-attr-value`` on
 * every page that ships a closed disclosure.
 */
export function Disclosure({
  id,
  title,
  headingLevel = 2,
  defaultOpen = false,
  icon,
  className,
  children,
}: {
  id: string;
  title: string;
  headingLevel?: 2 | 3;
  defaultOpen?: boolean;
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const buttonId = `${id}-button`;
  const panelId = `${id}-panel`;
  const Caret = open ? ChevronDown : ChevronRight;

  return (
    <div className={cn("rounded-xs border border-border bg-surface", className)}>
      {createElement(
        `h${headingLevel}`,
        { className: "m-0" },
        <button
          type="button"
          id={buttonId}
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className={cn(
            "flex min-h-target w-full items-center gap-2 rounded-xs px-4 py-3 text-left text-sm font-semibold text-fg",
            open ? "bg-surface-muted" : "hover:bg-surface-muted/60",
          )}
        >
          <Caret className="h-4 w-4 shrink-0 text-fg-subtle" aria-hidden />
          {icon}
          {/* The title must be this button's only text node: the UI tests
              address it both by exact text and by accessible name. */}
          <span>{title}</span>
        </button>,
      )}
      <div
        id={panelId}
        role="region"
        aria-labelledby={buttonId}
        hidden={!open}
        className="border-t border-border p-4"
      >
        {children}
      </div>
    </div>
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
        alt=&quot;&quot;
      </span>
    );
  }
  return (
    <span className="block max-w-full truncate text-xs text-fg" title={value}>
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
 * Accessible checkbox — promoted out of NewScan for reuse.
 *
 * **Why a custom component over a styled native input.**
 * The audit baseline scan flagged the New-Scan form's native checkboxes
 * as 13×13 px — failing WCAG 2.2 SC 2.5.8 (AA, 24×24) and the AAA
 * SC 2.5.5 (44×44). This component keeps the *visual* control at 22 px
 * (recognisable as a checkbox; respects platform conventions) but makes
 * the *whole label row* a 44 px hit target by wrapping the input in a
 * tall `<label>` with sufficient padding. Click-the-label semantics are
 * native browser behavior, so screen-reader and keyboard users get the
 * same affordance as pointer users.
 *
 * **Variants.**
 * - `tone="warning"`: when checked, renders a soft amber surface to
 *   reinforce that the option has a real consequence (used for
 *   "Ignore robots.txt"). Color is reinforcement, never the only signal —
 *   the label text and the optional `hint` carry the actual meaning.
 *
 * **Focus.** Uses the global `focus-visible:` outline (solid UMich Blue,
 * 3 px). Don't add a per-component ring — single source of truth keeps
 * focus consistent across every interactive element.
 */
export function Checkbox({
  checked,
  onChange,
  label,
  hint,
  tone = "neutral",
  id,
  name,
  disabled = false,
  describedBy,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  hint?: ReactNode;
  tone?: "neutral" | "warning";
  id?: string;
  name?: string;
  disabled?: boolean;
  /**
   * Id of an element that explains the consequence of ticking this box —
   * for the authorization checkbox, the note describing what the visible
   * browser does during sign-in. The `hint` prop is part of the label
   * (and so of the accessible name); this is a description instead,
   * which is the right relationship for a longer standing explanation.
   */
  describedBy?: string;
}) {
  const showWarning = tone === "warning" && checked;
  return (
    <label
      className={cn(
        // Full-row hit target: SC 2.5.5 AAA (44×44).
        "group flex min-h-target items-start gap-3 rounded-xs border border-transparent px-2 py-2 text-sm",
        disabled
          ? "cursor-not-allowed opacity-60"
          : "cursor-pointer hover:bg-surface-muted",
        showWarning && "border-sev-major/60 bg-sev-major-bg/40",
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        id={id}
        name={name}
        disabled={disabled}
        aria-describedby={describedBy}
        // 22×22 visual control. Padding on the parent label provides the
        // 44×44 hit zone. Border-strong (#D1D5DB) gives ≥3:1 against the
        // surface for the unchecked state — SC 1.4.11.
        className={cn(
          "mt-0.5 h-[22px] w-[22px] shrink-0 rounded-2xs",
          disabled ? "cursor-not-allowed" : "cursor-pointer",
          "border-2 border-border-strong bg-surface",
          "checked:border-umich-blue checked:bg-umich-blue",
          "focus:outline-none",
          // Focus ring is the global one; we just need to suppress the
          // double-ring that Tailwind's default `focus:ring` would draw.
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-umich-blue focus-visible:ring-offset-2",
        )}
      />
      <span className="flex flex-col gap-0.5 text-fg">
        <span className="leading-snug">{label}</span>
        {hint && (
          <span className="text-xs leading-snug text-fg-muted">{hint}</span>
        )}
      </span>
    </label>
  );
}

/**
 * PageLink — standardized rendering for "click to see the actual page
 * that has the issue." Used everywhere a page URL surfaces.
 *
 * Visual contract (mirrors Siteimprove's pattern):
 *   • Primary affordance: page title (or URL when title is missing) is
 *     the link, opens the actual page in a new tab. Visible "↗" icon
 *     plus an sr-only "opens in a new tab" announce makes the affordance
 *     unambiguous to both sighted and screen-reader users.
 *   • Secondary affordance: a smaller "view in audit" link goes to our
 *     in-app /pages/{id} view where image thumbnails + filtered axe
 *     findings live. Smaller treatment so the external link reads as
 *     primary.
 *
 * Centralizing this is what makes the link-sweep durable — future
 * routes that show a page URL use <PageLink> and inherit the contract.
 */
export function PageLink({
  pageId,
  scanId,
  pageUrl,
  pageTitle,
  showUrlBelow = true,
}: {
  pageId: number;
  /** Report scope required for the in-app evidence route. */
  scanId?: number;
  pageUrl: string;
  pageTitle?: string | null;
  /** Show the raw URL as a microcopy line below the title. */
  showUrlBelow?: boolean;
}) {
  const display = pageTitle?.trim() || pageUrl;
  return (
    <div className="min-w-0">
      <a
        href={pageUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-baseline gap-1 break-words text-umich-blue underline underline-offset-2"
      >
        <span className="break-words">{display}</span>
        <span aria-hidden className="text-2xs">
          ↗
        </span>
        <span className="sr-only">opens in a new tab</span>
      </a>
      {showUrlBelow && pageTitle && (
        <div className="break-all text-2xs text-fg-subtle" title={pageUrl}>
          {pageUrl}
        </div>
      )}
      {scanId != null && (
        <Link
          to={`/scans/${scanId}/pages/${pageId}`}
          className="mt-1 inline-block text-2xs text-fg-muted underline underline-offset-2 hover:text-fg"
        >
          view evidence →
        </Link>
      )}
    </div>
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
