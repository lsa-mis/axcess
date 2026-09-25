import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { createElement, forwardRef, useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, ChevronRight, ScanEye } from "lucide-react";
import { Link } from "react-router";
import { cn } from "../lib/cn";
import type { Severity, FindingStatus, ScanStatus } from "../api/types";

/** Severity chip, pairs color + text, so the signal isn't color-only. */
export function SeverityChip({ value }: { value: Severity }) {
  return <span className={cn("sev-chip", `sev-chip--${value}`)}>{value}</span>;
}

/** Status chip that uses neutral surfaces, we DON'T color-code status,
 * because status is intentionally user-workflow, not severity. */
export function StatusChip({ value }: { value: FindingStatus }) {
  return (
    <span className="inline-flex items-center rounded-xs border border-border bg-surface-muted px-2 py-0.5 text-2xs font-medium text-fg-muted">
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

/** Compact metric readout with strong numeric hierarchy.
 *
 * Deliberately chrome-free: no card fill, border, shadow or accent rule. Four
 * of these sit in a row, so a box around each one draws four rectangles the
 * reader has to look past to reach the numbers -- the chrome competes with the
 * data it frames. Spacing and type hierarchy do the grouping instead. */
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
    <div className="px-1 py-2">
      <div className="text-xs font-semibold text-fg-subtle">
        {label}
      </div>
      <div
        className={cn(
          "mt-2 text-[2rem] font-semibold leading-none tracking-tight",
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
    </div>
  );
}

/** Page header, breadcrumb + title + trailing actions. */
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
                  // breadcrumb target, always Link, never <a>.
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
 * one place is the single source of truth for action affordances, if a
 * designer changes "primary" to a different blue, both elements update.
 *
 * **Sizing.** Three sizes, all of which clear the WCAG 2.2 SC 2.5.5
 * (AAA, 44×44) floor. The `size` prop is therefore *visual emphasis*,
 * not a way to drop below the floor:
 *
 * - `lg`, primary page-level CTA. Use when there is exactly one
 *   "the thing the user came here to do" on a route ("Start crawl",
 *   "Start a new scan", "Save"). Larger type, more padding, stands out
 *   in the visual hierarchy.
 * - `md`, every other action. The default. Buttons in cards, table
 *   row actions, modal confirms, secondary affordances. Still 44×44.
 * - `sm`, *only* dense table cells where a 44px button would crowd
 *   the row layout. Pairs with `min-h-target` on the parent `<td>` so
 *   the *click target* is still 44×44 even though the chip is shorter.
 *   Use sparingly; if you reach for `sm`, double-check the layout
 *   actually needs it.
 *
 * **Why a baseline of `md` = 44px.** The Phase 1 baseline scan flagged
 * `py-1.5 text-sm` row buttons as ~30px tall, a SC 2.5.5 fail. The
 * earlier Phase 2 fix only addressed the checkbox; this sweep finishes
 * the job for the entire button surface.
 */
type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md" | "lg";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-xs font-semibold shadow-sm transition-[background-color,border-color,box-shadow,transform] duration-150 no-underline disabled:cursor-not-allowed disabled:opacity-60 active:translate-y-px";

const SIZE_CLASSES: Record<Size, string> = {
  // `sm` is sub-44px on its own, callers must wrap in a min-h-target cell
  // when used in tables. Documented above; not the default.
  sm: "px-2.5 py-1 text-xs",
  // `md` is the baseline, 44×44 hit target via min-h-target.
  md: "min-h-target px-4 py-2.5 text-sm",
  // `lg` is the primary-CTA size, 52px tall, larger type for visual weight.
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
// forwardRef so callers that must move focus back to the trigger, a
// disclosure closing on Escape, for one, can hold the element itself
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
 *, never a raw ``<a href>`` (which under ``basename="/app"`` would
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
 * ``/app/api/scans/.../export/csv``, a path React Router doesn't
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
 * widths, and say "opens in a new tab" in it, the new window is a
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
 * us was missing, nothing on the row said "this can be clicked" or
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
  meta,
  className,
  children,
}: {
  id: string;
  title: string;
  headingLevel?: 2 | 3;
  defaultOpen?: boolean;
  icon?: ReactNode;
  /**
   * A short status shown at the right end of the header row ("3 of 4 on").
   * It sits beside the button, not inside it, so the button's accessible
   * name stays the title alone; give it its own text for a screen reader.
   */
  meta?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const buttonId = `${id}-button`;
  const panelId = `${id}-panel`;

  return (
    <div className={cn("rounded-xs border border-border bg-surface", className)}>
      <div className={cn("flex items-center rounded-xs", open ? "bg-surface-muted" : "hover:bg-surface-muted/60")}>
      {createElement(
        `h${headingLevel}`,
        { className: "m-0 min-w-0 flex-1" },
        <button
          type="button"
          id={buttonId}
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((v) => !v)}
          className="flex min-h-target w-full items-center gap-2 rounded-xs px-4 py-3 text-left text-sm font-semibold text-fg"
        >
          {/* One caret, rotated when open: the turn is the only motion and
              the state is also in aria-expanded and the panel itself. */}
          <ChevronRight
            className={cn(
              "h-4 w-4 shrink-0 text-fg-subtle transition-transform duration-200 motion-reduce:transition-none",
              open && "rotate-90",
            )}
            aria-hidden
          />
          {icon}
          {/* The title must be this button's only text node: the UI tests
              address it both by exact text and by accessible name. */}
          <span>{title}</span>
        </button>,
      )}
      {meta && <div className="shrink-0 pr-4 text-xs font-semibold text-fg-subtle">{meta}</div>}
      </div>
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

/** Alt-attribute pill (missing / empty / authored), Siteimprove-style tag. */
export function AltTag({ value }: { value: string | null }) {
  if (value === null) {
    return (
      <span className="inline-flex items-center rounded-xs border border-sev-critical/40 bg-sev-critical-bg px-2 py-0.5 text-2xs font-semibold text-sev-critical">
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
 * stay neutral), scan status is operational state, running scans want a
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
        "inline-flex items-center rounded-xs border px-2 py-0.5 text-2xs font-semibold",
        SCAN_STATUS_CLASS[value],
      )}
    >
      {value}
    </span>
  );
}

/**
 * Accessible checkbox, promoted out of NewScan for reuse.
 *
 * **Why a custom component over a styled native input.**
 * The audit baseline scan flagged the New-Scan form's native checkboxes
 * as 13×13 px, failing WCAG 2.2 SC 2.5.8 (AA, 24×24) and the AAA
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
 *   "Ignore robots.txt"). Color is reinforcement, never the only signal,
 *   the label text and the optional `hint` carry the actual meaning.
 *
 * **Focus.** Uses the global `focus-visible:` outline (solid UMich Blue,
 * 3 px). Don't add a per-component ring, single source of truth keeps
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
  error,
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
   * Id of an element that explains the consequence of ticking this box,
   * for the authorization checkbox, the note describing what the visible
   * browser does during sign-in. Joined with the `hint`'s own id: both are
   * descriptions, read on request, never part of the name.
   */
  describedBy?: string;
  /** A problem with this choice, shown under the row and announced. */
  error?: string;
}) {
  const showWarning = tone === "warning" && checked;
  // The hint used to sit inside the label and so inside the accessible
  // name, which made every row's name a paragraph. It is a description now,
  // the same relationship `describedBy` always had.
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const description = [hint ? hintId : null, error ? errorId : null, describedBy]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="min-w-0">
    <label
      htmlFor={inputId}
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
        id={inputId}
        name={name}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={description || undefined}
        // 22×22 visual control. Padding on the parent label provides the
        // 44×44 hit zone. Border-strong (#D1D5DB) gives ≥3:1 against the
        // surface for the unchecked state, SC 1.4.11.
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
          <span id={hintId} className="text-xs leading-snug text-fg-muted">
            {hint}
          </span>
        )}
      </span>
    </label>
    {error && (
      <p id={errorId} role="alert" className="ml-[42px] mt-0.5 text-xs font-semibold text-sev-major">
        {error}
      </p>
    )}
    </div>
  );
}

/**
 * PageLink, standardized rendering for "open this page's in-app inspector."
 * Used everywhere a page URL surfaces.
 *
 * Visual contract:
 *   • Primary affordance: page title (or URL when title is missing) is the
 *     link, and it opens the IN-APP page/DOM inspector, it no longer sends
 *     the reviewer to the live site in a new tab. The inspector re-renders
 *     the page and (when ``selector``/``issue`` is supplied) circles the
 *     flagged element, and it shows the loaded DOM.
 *   • Secondary affordances (small, muted): "open live page ↗" for the rare
 *     case the reviewer wants the real site, and "stored evidence" for the
 *     in-app /pages/{id} view (findings + image thumbnails).
 *   • ``origin`` / ``context`` / ``backTo`` travel to the inspector so the
 *     reviewer always knows which view they came from and how to return.
 *
 * Centralizing this is what makes the link-sweep durable, every route that
 * shows a page URL uses <PageLink> and inherits the contract.
 */
/** One option in a {@link Select}. */
export type SelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
  /**
   * Shown before the label, in the list and in the closed box while chosen,
   * such as a status chip. It is read as part of the option's name, so its
   * meaning must be in its words, never in its color alone.
   */
  badge?: ReactNode;
};

/** How long a pause ends a type-to-find run, matching platform selects. */
const TYPEAHEAD_RESET_MS = 500;

/**
 * The app's dropdown for choosing a value.
 *
 * Built as the WAI-ARIA APG *select-only combobox*, drawn like the Export
 * panel so every dropdown in the app reads as one family.
 *
 * This replaced a native `<select>`. The native control was kept for as long
 * as it could be, because the platform gets keyboard, typeahead, and focus
 * right for free and custom listboxes are a routine source of the defects
 * this tool exists to find. It could not stay: its open list is drawn by the
 * OS, so it can neither match Export nor carry a status chip on an option
 * (the inspector marks page states whose element is gone). Everything the
 * native control did is therefore owned here and pinned by browser tests:
 *
 * - Focus never leaves the trigger; the highlighted option is conveyed with
 *   `aria-activedescendant`, and the trigger's text is the chosen value.
 * - Closed: Down, Up, Enter, and Space open the list on the chosen option;
 *   Home and End open it on the first or last; typing opens it on a match.
 * - Open: Up and Down move, Home, End, Page Up, and Page Down jump, Enter and
 *   Space choose, Escape closes without choosing, and Tab chooses the
 *   highlighted option and moves on, as the APG pattern specifies. Typing
 *   jumps to the next option starting with what was typed.
 * - Pointer: clicking an option chooses it; clicking away or focus leaving
 *   the trigger closes the list.
 *
 * `label` is always rendered and always associated. Pass `hideLabel` for a
 * control whose meaning is already obvious from its surroundings; the name
 * stays available to a screen reader rather than being dropped.
 *
 * `stacked` puts the label above rather than beside it, for a filter bar of
 * several controls where inline captions would eat the width the values need.
 *
 * `hint` sits between the label and the control and is wired to
 * `aria-describedby`, so the explanation a sighted user reads before choosing
 * is announced to everyone else as part of the same control.
 *
 * `data-value` on the trigger and on each option carries the raw value, so
 * tests and tooling can pick an option without depending on its wording.
 */
export function Select({
  label,
  hideLabel = false,
  stacked = false,
  hint,
  value,
  onChange,
  options,
  id,
  className,
  disabled = false,
  "aria-describedby": extraDescribedBy,
}: {
  label: string;
  hideLabel?: boolean;
  stacked?: boolean;
  hint?: ReactNode;
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  id?: string;
  className?: string;
  disabled?: boolean;
  "aria-describedby"?: string;
}) {
  const generated = useId();
  const triggerId = id ?? generated;
  const hintId = `${triggerId}-hint`;
  const listId = `${triggerId}-list`;
  const labelId = `${triggerId}-label`;
  const optionId = (index: number) => `${triggerId}-option-${index}`;
  const describedBy = [hint ? hintId : null, extraDescribedBy].filter(Boolean).join(" ");

  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const typeahead = useRef({ text: "", at: 0 });

  const selectedIndex = options.findIndex((option) => option.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined;
  const enabled = (index: number) =>
    index >= 0 && index < options.length && !options[index].disabled;
  /** The nearest enabled option ``distance`` steps from ``from``, clamped. */
  const move = (from: number, distance: number) => {
    const direction = distance < 0 ? -1 : 1;
    let target = from;
    let remaining = Math.abs(distance);
    for (let i = from + direction; i >= 0 && i < options.length && remaining > 0; i += direction) {
      if (enabled(i)) {
        target = i;
        remaining -= 1;
      }
    }
    return target;
  };
  const first = () => move(-1, 1);
  const last = () => move(options.length, -1);

  const openAt = (index: number) => {
    setActive(enabled(index) ? index : first());
    setOpen(true);
  };
  const choose = (index: number) => {
    setOpen(false);
    if (enabled(index) && options[index].value !== value) onChange(options[index].value);
  };

  /** The next option whose label starts with what has been typed. */
  const findTyped = (key: string, from: number) => {
    const now = Date.now();
    const run = typeahead.current;
    run.text = now - run.at > TYPEAHEAD_RESET_MS ? key : run.text + key;
    run.at = now;
    // Repeating one letter cycles through the options that start with it.
    const repeated = [...run.text].every((char) => char === run.text[0]);
    const needle = (repeated ? run.text[0] : run.text).toLowerCase();
    const start = repeated || run.text.length === 1 ? from + 1 : from;
    for (let offset = 0; offset < options.length; offset += 1) {
      const index = (start + offset + options.length) % options.length;
      if (enabled(index) && options[index].label.toLowerCase().startsWith(needle)) return index;
    }
    return -1;
  };

  useEffect(() => {
    if (!open || active < 0) return;
    document.getElementById(`${triggerId}-option-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [open, active, triggerId]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    const { key } = event;
    const printable = key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;
    // Any other key ends a type-to-find run, so "n", Home, "i" finds "i".
    if (!printable && !["Shift", "Control", "Alt", "Meta"].includes(key)) {
      typeahead.current = { text: "", at: 0 };
    }
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(key)) {
        event.preventDefault();
        openAt(selectedIndex);
      } else if (key === "Home") {
        event.preventDefault();
        openAt(first());
      } else if (key === "End") {
        event.preventDefault();
        openAt(last());
      } else if (printable) {
        const match = findTyped(key, selectedIndex);
        if (match >= 0) openAt(match);
      }
      return;
    }
    // A space inside a type-to-find run is part of the text, not a choice.
    const typing = Date.now() - typeahead.current.at <= TYPEAHEAD_RESET_MS;
    if (key === "ArrowDown") {
      event.preventDefault();
      setActive(move(active, 1));
    } else if (key === "ArrowUp") {
      event.preventDefault();
      if (event.altKey) choose(active);
      else setActive(move(active, -1));
    } else if (key === "Home") {
      event.preventDefault();
      setActive(first());
    } else if (key === "End") {
      event.preventDefault();
      setActive(last());
    } else if (key === "PageDown") {
      event.preventDefault();
      setActive(move(active, 10));
    } else if (key === "PageUp") {
      event.preventDefault();
      setActive(move(active, -10));
    } else if (key === "Enter" || (key === " " && !typing)) {
      event.preventDefault();
      choose(active);
    } else if (key === "Escape") {
      // Handled here, so a page-level Escape handler does not also fire.
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
    } else if (key === "Tab") {
      choose(active);
    } else if (printable) {
      const match = findTyped(key, active);
      if (match >= 0) setActive(match);
    }
  };

  return (
    <div
      className={cn(
        "min-w-0",
        stacked ? "flex flex-col gap-1" : "inline-flex items-center gap-2",
        className,
      )}
    >
      <label
        id={labelId}
        htmlFor={triggerId}
        className={cn(
          "shrink-0 font-semibold text-fg",
          stacked ? "text-xs text-fg-subtle" : "text-sm",
          hideLabel && "sr-only",
        )}
      >
        {label}
      </label>
      {hint && (
        <p id={hintId} className="text-xs text-fg-muted">
          {hint}
        </p>
      )}
      <div className="relative min-w-0">
        <button
          id={triggerId}
          type="button"
          role="combobox"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listId}
          aria-activedescendant={open && active >= 0 ? optionId(active) : undefined}
          aria-describedby={describedBy || undefined}
          data-value={value}
          disabled={disabled}
          onClick={() => (open ? setOpen(false) : openAt(selectedIndex))}
          onKeyDown={onKeyDown}
          // Clicks in the list keep focus here (see its onMouseDown), so a
          // blur means focus really went elsewhere.
          onBlur={() => setOpen(false)}
          className="min-h-target w-full rounded-xs border border-border-strong bg-surface py-2.5 pl-3 pr-9 text-left text-sm font-semibold text-fg shadow-sm transition-colors hover:border-umich-blue hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
        >
          {/* Every option is laid out invisibly in the same cell, so the box
              is as wide as its longest option, as a native select is, and
              does not change width with each choice. */}
          <span className="grid">
            {options.map((option) => (
              <span
                key={option.value}
                aria-hidden
                className="invisible col-start-1 row-start-1 flex items-center gap-2 whitespace-nowrap"
              >
                {option.badge}
                {option.label}
              </span>
            ))}
            <span className="col-start-1 row-start-1 flex min-w-0 items-center gap-2">
              {selected?.badge}
              <span className="truncate">{selected?.label ?? ""}</span>
            </span>
          </span>
        </button>
        <ChevronDown
          className="pointer-events-none absolute right-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-muted"
          aria-hidden
        />
        {/* The Export panel's surface. Not focusable: focus stays on the
            trigger, and mousedown is cancelled so clicking an option or the
            scrollbar does not blur it. */}
        <ul
          id={listId}
          role="listbox"
          aria-labelledby={labelId}
          hidden={!open}
          onMouseDown={(event) => event.preventDefault()}
          className="absolute left-0 z-30 mt-1.5 max-h-80 w-max min-w-full max-w-[calc(100vw-2rem)] overflow-auto rounded-xs border border-border bg-surface p-1.5 shadow-raised"
        >
          {options.map((option, index) => (
            // Keyboard selection lives on the trigger, which keeps focus and
            // points here with aria-activedescendant; options are never focused.
            // eslint-disable-next-line jsx-a11y/click-events-have-key-events
            <li
              key={option.value}
              id={optionId(index)}
              role="option"
              aria-selected={index === selectedIndex}
              aria-disabled={option.disabled || undefined}
              data-value={option.value}
              onClick={() => enabled(index) && choose(index)}
              onMouseMove={() => enabled(index) && index !== active && setActive(index)}
              className={cn(
                "flex min-h-target cursor-pointer items-center gap-2 rounded-2xs px-3 py-2 text-sm text-fg",
                index === active && "bg-surface-muted outline outline-2 -outline-offset-2 outline-umich-blue",
                index === selectedIndex && "font-semibold",
                option.disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <Check
                className={cn(
                  "h-3.5 w-3.5 shrink-0",
                  index === selectedIndex ? "text-umich-blue" : "invisible",
                )}
                aria-hidden
              />
              {option.badge}
              <span>{option.label}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/**
 * Add the "you came from here" pair to an in-app path.
 *
 * ``origin``/``back`` are what the topbar breadcrumb turns into a parent crumb
 * (see ReportCrumb), and that crumb is the only way back in the desktop app,
 * which has no browser back button. Existing query and hash are preserved, and
 * an off-app target is returned untouched: `back` is only honoured for
 * absolute in-app paths, so there is nothing to gain by decorating one.
 */
export function withReturnTrail(to: string, origin?: string, backTo?: string): string {
  if (!origin || !backTo || !to.startsWith("/") || to.startsWith("//")) return to;
  const [beforeHash, ...hashParts] = to.split("#");
  const hash = hashParts.length ? `#${hashParts.join("#")}` : "";
  const [path, query = ""] = beforeHash.split("?");
  const params = new URLSearchParams(query);
  params.set("origin", origin);
  params.set("back", backTo);
  return `${path}?${params.toString()}${hash}`;
}

/**
 * Path to a page's stored evidence, carrying the view it was opened from.
 *
 * ``origin``/``back`` are what the topbar breadcrumb reads to draw the parent
 * crumb (see ReportCrumb). Without them the trail on Page evidence stops at
 * ``Reports › site › Page evidence``, and in the desktop app — which has no
 * browser back button — there is then no way back to Issues at all. So every
 * link into stored evidence carries its origin, the same contract the
 * inspector links already follow.
 */
export function pageEvidencePath({
  scanId,
  pageId,
  origin,
  backTo,
  hash,
}: {
  scanId: number;
  pageId: number;
  origin?: string;
  backTo?: string;
  /** Fragment to append, e.g. ``"#finding-12"``; query comes first. */
  hash?: string;
}): string {
  const params = new URLSearchParams();
  if (origin) params.set("origin", origin);
  if (backTo) params.set("back", backTo);
  const qs = params.toString();
  return `/scans/${scanId}/pages/${pageId}${qs ? `?${qs}` : ""}${hash ?? ""}`;
}

export function PageLink({
  pageId,
  scanId,
  pageUrl,
  pageTitle,
  showUrlBelow = true,
  selector = null,
  snippet = null,
  issue = null,
  origin,
  context,
  contextTo,
  backTo,
}: {
  pageId: number;
  /** Report scope required for the in-app inspector route. */
  scanId?: number;
  pageUrl: string;
  pageTitle?: string | null;
  /** Show the raw URL as a microcopy line below the title. */
  showUrlBelow?: boolean;
  /** Target selector to circle on the inspected page (when known directly). */
  selector?: string | null;
  /** Exact element markup (html_snippet), the most reliable locator. */
  snippet?: string | null;
  /** Issue key to resolve the selector for (used when ``selector`` is absent). */
  issue?: string | null;
  /** Label of the view this link lives in (orientation breadcrumb). */
  origin?: string;
  /** Short context label (rule/issue/finding) shown on the inspector. */
  context?: string;
  /** In-app path the context label links to (issue detail, finding, …). */
  contextTo?: string;
  /** In-app path the inspector's "Back" link returns to. */
  backTo?: string;
}) {
  const display = pageTitle?.trim() || pageUrl;

  // Build the inspector URL with whatever orientation/selector context the
  // caller can offer. The params are kept sparse so the route stays legible.
  const inspectTo = (() => {
    if (scanId == null) return null;
    const params = new URLSearchParams();
    if (selector) params.set("selector", selector);
    // The snippet (exact element markup) is the reliable locator; the DB caps
    // it at 4000 chars, so mirror that, no point truncating below the source.
    if (snippet) params.set("snippet", snippet.slice(0, 4000));
    if (issue) params.set("issue", issue);
    if (origin) params.set("origin", origin);
    if (context) params.set("context", context);
    if (contextTo) params.set("contextTo", contextTo);
    if (backTo) params.set("back", backTo);
    const qs = params.toString();
    return `/scans/${scanId}/pages/${pageId}/inspect${qs ? `?${qs}` : ""}`;
  })();

  return (
    <div className="min-w-0">
      {inspectTo ? (
        <Link
          to={inspectTo}
          className="inline-flex items-baseline gap-1 break-words text-umich-blue underline underline-offset-2"
        >
          {/* self-start, not self-center: the flex line is as tall as the wrapped
              title, so centring drops the icon into the gap between lines on
              any title that wraps. Top-aligned it stays beside the first line. */}
          <ScanEye className="h-5 w-5 shrink-0 self-start pt-0.5 text-fg-subtle" aria-hidden />
          <span className="break-words">{display}</span>
          <span className="sr-only">, opens the in-app page inspector</span>
        </Link>
      ) : (
        // Without a scan scope there is no in-app inspector to link to; keep
        // the external affordance as the fallback.
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
      )}
      {showUrlBelow && pageTitle && (
        <div className="break-all text-2xs text-fg-subtle" title={pageUrl}>
          {pageUrl}
        </div>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-2xs text-fg-muted">
        <a
          href={pageUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-2 hover:text-fg"
        >
          open live page ↗
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
        {scanId != null && (
          <>
            <span aria-hidden className="text-fg-subtle">
              ·
            </span>
            <Link
              to={pageEvidencePath({ scanId, pageId, origin, backTo })}
              className="underline underline-offset-2 hover:text-fg"
            >
              stored evidence
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

/**
 * Render an ISO-8601 timestamp as a short, human-friendly relative string
 * (``"2h ago"``, ``"3d ago"``). Returns ``"n/a"`` for null/empty input so
 * callers don't have to guard.
 *
 * We round down, "59 minutes" reads as "59m ago", not "1h ago", because
 * scan timing matters for the user ("did this finish recently?") and
 * over-rounding hides recency. The full ISO timestamp should be passed
 * via a ``title`` attribute on the wrapping element so hovering reveals
 * the exact moment; this helper only formats, it doesn't render.
 */
export function relativeTime(iso: string | null): string {
  if (!iso) return "n/a";
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "n/a";
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
