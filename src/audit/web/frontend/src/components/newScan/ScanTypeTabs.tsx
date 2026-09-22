import { useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { Globe2, LockKeyhole } from "lucide-react";
import { cn } from "../../lib/cn";
import { TAB_LOGIN, TAB_PUBLIC } from "./copy";
import type { ScanMode } from "./scanPolicy";

export const SCAN_PANEL_ID = "scan-panel";
export const scanTabId = (mode: ScanMode) => `scan-tab-${mode}`;

const TABS: Array<{ mode: ScanMode; label: string; Icon: typeof Globe2 }> = [
  { mode: "public", label: TAB_PUBLIC, Icon: Globe2 },
  { mode: "login", label: TAB_LOGIN, Icon: LockKeyhole },
];

/**
 * The two kinds of scan as a real tab list.
 *
 * Arrow keys move between the tabs and select as they go (the WAI-ARIA
 * automatic-activation pattern), Home/End jump, and only the selected tab
 * is in the Tab order. The panel below is keyed on the mode by the route,
 * so a change re-mounts it and it drops in; the tab strip itself never
 * animates anything but its background.
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
  // The active tab's slot, measured, so the fill and the pointer under the
  // rail slide to it — the same treatment as the report tabs, so the two
  // rows read as one control across the app.
  const [slot, setSlot] = useState<{ left: number; width: number } | null>(null);
  useLayoutEffect(() => {
    const measure = () => {
      const track = trackRef.current;
      const chip = refs.current[mode];
      if (!track || !chip) return setSlot(null);
      const t = track.getBoundingClientRect();
      const c = chip.getBoundingClientRect();
      setSlot({ left: c.left - t.left, width: c.width });
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
        className="relative inline-flex flex-wrap gap-1 rounded-md border border-border bg-surface p-1"
      >
        {slot && (
          <span
            aria-hidden
            className="pointer-events-none absolute bottom-1 left-0 top-1 rounded-xs bg-umich-blue transition-[transform,width] duration-300 ease-out motion-reduce:transition-none"
            style={{ width: slot.width, transform: `translateX(${slot.left}px)` }}
          />
        )}
        {TABS.map(({ mode: tabMode, label, Icon }) => {
          const selected = tabMode === mode;
          const disabled = tabMode === "login" && Boolean(disabledReason);
          return (
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
                selected ? "text-fg-inverse" : "text-fg hover:bg-surface-muted",
                disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
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
      {/* The rail the panel hangs from, with a pointer under the chosen tab:
          everything below — the form and the summary beside it — is that
          tab's. */}
      <div aria-hidden className="relative mt-3 h-px bg-border-strong">
        {slot && (
          <span
            className="absolute -top-[6px] h-3 w-3 border-2 border-border-strong bg-surface transition-transform duration-300 ease-out motion-reduce:transition-none"
            style={{ transform: `translateX(${slot.left + slot.width / 2}px) translateX(-50%) rotate(45deg)` }}
          />
        )}
      </div>
    </div>
  );
}
