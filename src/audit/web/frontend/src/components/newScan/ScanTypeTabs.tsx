import { useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { cn } from "../../lib/cn";
import { TAB_LOGIN, TAB_PUBLIC } from "./copy";
import type { ScanMode } from "./scanPolicy";

export const SCAN_PANEL_ID = "scan-panel";
export const scanTabId = (mode: ScanMode) => `scan-tab-${mode}`;

const TABS: Array<{ mode: ScanMode; label: string }> = [
  { mode: "public", label: TAB_PUBLIC },
  { mode: "login", label: TAB_LOGIN },
];

/**
 * The two kinds of scan as a real tab list.
 *
 * Arrow keys move between the tabs and select as they go (the WAI-ARIA
 * automatic-activation pattern), Home/End jump, and only the selected tab
 * is in the Tab order. The panel below is keyed on the mode by the route,
 * so a change re-mounts it and it drops in; the tab strip itself never
 * animates anything but its background. It is drawn as a segmented
 * control, the same shape as the choices inside the form.
 */
export default function ScanTypeTabs({
  mode,
  onChange,
  disabledReason,
}: {
  mode: ScanMode;
  onChange: (mode: ScanMode) => void;
  /** Why the login tab cannot be chosen yet, when it cannot. */
  disabledReason?: string | null;
}) {
  const refs = useRef<Partial<Record<ScanMode, HTMLButtonElement | null>>>({});
  const trackRef = useRef<HTMLDivElement>(null);
  // The active tab's slot, measured, so the fill slides to it — the same
  // treatment as the report tabs, so the two rows read as one control
  // across the app. Its top and height too: on a narrow screen the tabs
  // wrap onto two lines, and a fill the height of the whole row covered the
  // second tab's words.
  const [slot, setSlot] = useState<{ left: number; top: number; width: number; height: number } | null>(null);
  useLayoutEffect(() => {
    const measure = () => {
      const track = trackRef.current;
      const chip = refs.current[mode];
      if (!track || !chip) return setSlot(null);
      const t = track.getBoundingClientRect();
      const c = chip.getBoundingClientRect();
      setSlot({ left: c.left - t.left, top: c.top - t.top, width: c.width, height: c.height });
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (trackRef.current) observer.observe(trackRef.current);
    return () => observer.disconnect();
  }, [mode]);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const order = TABS.map((tab) => tab.mode);
    const index = order.indexOf(mode);
    let next: ScanMode | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = order[(index + 1) % order.length];
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = order[(index - 1 + order.length) % order.length];
    if (event.key === "Home") next = order[0];
    if (event.key === "End") next = order[order.length - 1];
    if (!next || next === mode) return;
    if (next === "login" && disabledReason) return;
    event.preventDefault();
    onChange(next);
    refs.current[next]?.focus();
  };

  return (
    <div>
      <div
        ref={trackRef}
        role="tablist"
        aria-label="Scan type"
        className="relative inline-flex flex-wrap gap-1 rounded-md border border-border bg-surface-muted p-1"
      >
        {slot && (
          <span
            aria-hidden
            className="pointer-events-none absolute left-0 top-0 rounded-xs bg-umich-blue transition-[transform,width,height] duration-300 ease-out motion-reduce:transition-none"
            style={{ width: slot.width, height: slot.height, transform: `translate(${slot.left}px, ${slot.top}px)` }}
          />
        )}
        {TABS.map(({ mode: tabMode, label }) => {
          const selected = tabMode === mode;
          const disabled = tabMode === "login" && Boolean(disabledReason);
          return (
            // eslint-disable-next-line react/forbid-elements -- Keep: a tab of the Scan type tabs (role=tab)
            <button
              key={tabMode}
              ref={(element) => {
                refs.current[tabMode] = element;
              }}
              type="button"
              role="tab"
              id={scanTabId(tabMode)}
              aria-selected={selected}
              aria-controls={SCAN_PANEL_ID}
              aria-disabled={disabled || undefined}
              tabIndex={selected ? 0 : -1}
              onClick={() => !disabled && onChange(tabMode)}
              onKeyDown={onKeyDown}
              className={cn(
                "relative inline-flex min-h-target items-center gap-2 rounded-xs px-4 text-sm font-semibold transition-colors duration-200 motion-reduce:transition-none",
                // The sliding fill is dropped in forced colors, so the
                // selected tab also gets an outline there.
                selected
                  ? "text-fg-inverse forced-colors:outline forced-colors:outline-2 forced-colors:-outline-offset-2"
                  : "text-fg hover:bg-surface",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              {label}
            </button>
          );
        })}
      </div>
      {disabledReason && (
        <p role="status" className="mt-2 text-xs text-fg-muted">
          {disabledReason}
        </p>
      )}
    </div>
  );
}
