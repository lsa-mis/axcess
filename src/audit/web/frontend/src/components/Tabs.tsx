import type { KeyboardEvent, ReactNode } from "react";
import { useRef } from "react";
import { Link } from "react-router";
import { cn } from "../lib/cn";

/**
 * The one segmented switcher: a row of chips on a recessed track, the current
 * one filled UMich Blue.
 *
 * Three of these rows used to exist as three unrelated implementations — the
 * report's underline tabs, the inspector's white-chip tablist, and the
 * tracker's navy-chip button group — so the same control looked like three
 * different controls depending on which page you were on. They share this
 * file now; `mode` picks the semantics, never the styling.
 *
 * **Why `mode` exists at all.** These rows look alike but are not the same
 * widget, and giving them identical markup would break them:
 *
 * - `nav` — each chip is a different URL. They stay real links, marked with
 *   `aria-current="page"`. Links must not carry `role="tab"`: that role takes
 *   over the arrow keys and promises a panel in this document, neither of
 *   which is true of a link that navigates away.
 * - `tabs` — a genuine ARIA tablist over panels in the same document. Follows
 *   the APG: arrow keys move selection, and only the selected tab is in the
 *   tab sequence, so Tab steps out of the row into the panel rather than
 *   through every chip.
 * - `filter` — toggle buttons that narrow a list. There is no panel per chip,
 *   so these are `aria-pressed`, not tabs.
 *
 * The active chip is never signalled by colour alone: it also gains a filled
 * shape and the appropriate ARIA state.
 */
type Mode = "nav" | "tabs" | "filter";

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
  idPrefix,
  className,
}: {
  mode: Mode;
  /** Names the row for assistive tech; never rendered. */
  label: string;
  items: TabItem[];
  /** `key` of the active chip. */
  value: string;
  /** Required for `tabs` and `filter`; ignored in `nav`. */
  onChange?: (key: string) => void;
  /** `filter` mode — the region these chips narrow. */
  controls?: string;
  /** `tabs` mode — chip i gets `${idPrefix}-tab-${key}` and points at
   *  `${idPrefix}-panel-${key}`, so panels can name their tab back. */
  idPrefix?: string;
  className?: string;
}) {
  const chipRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  if (mode === "nav") {
    return (
      <nav aria-label={label} className={className}>
        <ul className={TRACK}>
          {items.map((item) => (
            <li key={item.key}>
              <Link
                to={item.to ?? "#"}
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

  const isTabs = mode === "tabs";

  // APG roving tabindex: arrows move selection and focus together, wrapping at
  // both ends. Only wired for `tabs` — `filter` chips are independent toggles,
  // so each one stays in the tab sequence and the arrows keep their default.
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = items[(index + step + items.length) % items.length];
    onChange?.(next.key);
    chipRefs.current[next.key]?.focus();
  };

  return (
    <div
      role={isTabs ? "tablist" : "group"}
      aria-label={label}
      className={cn(TRACK, className)}
    >
      {items.map((item, index) => {
        const active = item.key === value;
        return (
          <button
            key={item.key}
            type="button"
            ref={(el) => {
              chipRefs.current[item.key] = el;
            }}
            id={isTabs && idPrefix ? `${idPrefix}-tab-${item.key}` : undefined}
            role={isTabs ? "tab" : undefined}
            aria-selected={isTabs ? active : undefined}
            aria-pressed={isTabs ? undefined : active}
            aria-controls={
              isTabs
                ? idPrefix && `${idPrefix}-panel-${item.key}`
                : controls
            }
            tabIndex={isTabs ? (active ? 0 : -1) : undefined}
            onClick={() => onChange?.(item.key)}
            onKeyDown={isTabs ? (e) => onKeyDown(e, index) : undefined}
            className={chipClass(active)}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
