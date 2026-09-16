import type { ReactNode } from "react";
import { Link } from "react-router";
import { cn } from "../lib/cn";

/**
 * The one segmented switcher: a row of chips on a recessed track, the current
 * one filled UMich Blue.
 *
 * Three of these rows used to exist as three unrelated implementations — the
 * report's underline tabs, the inspector's white-chip tablist, and the
 * tracker's navy-chip button group — so the same control looked like three
 * different controls depending on which page you were on.
 *
 * **One keyboard model: Tab moves, Enter/Space activates.** Every chip here is
 * separately Tab-reachable, whichever mode it is in. The inspector's row used
 * to be a real ARIA `tablist`, which meant arrow keys moved between its chips
 * and Tab skipped past the row entirely — correct for that pattern, but once
 * all three rows looked identical, two of them answered the arrow keys and one
 * did not. Identical controls that take different keys are worse than either
 * convention on its own (WCAG 3.2.4, Consistent Identification), so the
 * tablist went and its two views became links like the rest.
 *
 * Losing `tablist` cost nothing: it buys arrow-key roving and a tab/panel
 * relationship, and the inspector's views are better off as URLs anyway —
 * they can be linked to and bookmarked, which a `useState` tab never could.
 * If a future row genuinely needs the APG tab pattern, give it its own
 * component and its own look; do not add a third keyboard model to this one.
 *
 * `mode` picks the semantics, never the styling:
 *
 * - `nav` — each chip is a URL, so they are real links marked with
 *   `aria-current="page"`.
 * - `filter` — toggle buttons that narrow a list in place. No panel per chip,
 *   so these are `aria-pressed`, not tabs.
 *
 * The active chip is never signalled by colour alone: it also gains a filled
 * shape and the matching ARIA state.
 */
type Mode = "nav" | "filter";

export type TabItem = {
  /** Identity of the chip, and the value reported to `onChange`. */
  key: string;
  label: ReactNode;
  /** `nav` mode only — the route this chip navigates to. */
  to?: string;
};

/** Recessed track. Chips wrap rather than scroll: a scroll container here
 *  would clip the chips' own focus ring against the track's border. */
const TRACK =
  "flex flex-wrap items-center gap-1 rounded-xs border border-border bg-surface-muted p-1";

const CHIP =
  "inline-flex min-h-target items-center justify-center whitespace-nowrap rounded-2xs px-3.5 py-1.5 text-sm font-semibold no-underline transition-colors";

const CHIP_ACTIVE = "bg-umich-blue text-fg-inverse hover:bg-umich-blue-600";
const CHIP_IDLE = "text-fg-muted hover:bg-surface hover:text-fg";

const chipClass = (active: boolean) =>
  cn(CHIP, active ? CHIP_ACTIVE : CHIP_IDLE);

export default function Tabs({
  mode,
  label,
  items,
  value,
  onChange,
  controls,
  replace = false,
  className,
}: {
  mode: Mode;
  /** Names the row for assistive tech; never rendered. */
  label: string;
  items: TabItem[];
  /** `key` of the active chip. */
  value: string;
  /** Required for `filter`; ignored in `nav`. */
  onChange?: (key: string) => void;
  /** `filter` mode — the region these chips narrow. */
  controls?: string;
  /** `nav` mode — swap the history entry instead of pushing one. For a row
   *  that switches views of the page you are already on, so that Back still
   *  leaves the page rather than stepping through every chip you tried. */
  replace?: boolean;
  className?: string;
}) {
  if (mode === "nav") {
    return (
      <nav aria-label={label} className={className}>
        <ul className={TRACK}>
          {items.map((item) => (
            <li key={item.key}>
              <Link
                to={item.to ?? "#"}
                replace={replace}
                aria-current={item.key === value ? "page" : undefined}
                className={chipClass(item.key === value)}
              >
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    );
  }

  return (
    <div role="group" aria-label={label} className={cn(TRACK, className)}>
      {items.map((item) => {
        const active = item.key === value;
        return (
          <button
            key={item.key}
            type="button"
            aria-pressed={active}
            aria-controls={controls}
            onClick={() => onChange?.(item.key)}
            className={chipClass(active)}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
