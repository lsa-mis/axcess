import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
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
  attached = false,
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
  /**
   * `nav` mode — the row heads a content area. The active chip's fill
   * slides between chips instead of jumping, and a rail under the track
   * carries a small pointer beneath the active chip, so the content below
   * reads as belonging to that tab. Motion is 250 ms and off under
   * reduced motion; the state is still the fill, the pointer and
   * `aria-current`, never the movement.
   */
  attached?: boolean;
  className?: string;
}) {
  if (mode === "nav") {
    return (
      <NavTabs
        label={label}
        items={items}
        value={value}
        replace={replace}
        attached={attached}
        className={className}
      />
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

type Slot = { left: number; width: number };
/** The last measured active slot per row, so a re-mounted row can slide from it. */
const lastSlot = new Map<string, Slot>();

const pointerTransform = (s: Slot) => `translateX(${s.left + s.width / 2}px) translateX(-50%) rotate(45deg)`;

/** Slide the fill and the pointer from the previous slot to the current one. */
function slideFrom(fill: HTMLElement | null, pointer: HTMLElement | null, from: Slot, to: Slot) {
  if (typeof fill?.animate !== "function") return;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  const timing: KeyframeAnimationOptions = { duration: 300, easing: "cubic-bezier(0.2, 0, 0, 1)" };
  fill.animate(
    [
      { transform: `translateX(${from.left}px)`, width: `${from.width}px` },
      { transform: `translateX(${to.left}px)`, width: `${to.width}px` },
    ],
    timing,
  );
  pointer?.animate([{ transform: pointerTransform(from) }, { transform: pointerTransform(to) }], timing);
}

function NavTabs({
  label,
  items,
  value,
  replace,
  attached = false,
  className,
}: {
  label: string;
  items: TabItem[];
  value: string;
  replace: boolean;
  attached: boolean;
  className?: string;
}) {
  const trackRef = useRef<HTMLUListElement>(null);
  const chipRefs = useRef<Record<string, HTMLAnchorElement | null>>({});
  const fillRef = useRef<HTMLLIElement>(null);
  const pointerRef = useRef<HTMLSpanElement>(null);
  // Where the active chip is, measured, so the fill and the pointer can sit
  // under it. Measured again on resize and whenever the labels wrap.
  //
  // Each report route mounts its own copy of this row, so a tab change
  // re-mounts it and React state cannot carry the old position across. The
  // module-level `lastSlot` (keyed by the row's label) remembers where the
  // previous copy left the fill, and the slide from there to the new chip is
  // a Web Animations API animation on the two elements: it starts from the
  // old position in the same frame the new one is committed, and no later
  // re-render can cancel it. Off under reduced motion.
  // Start from the remembered slot so the fill and pointer exist on the
  // first render and can be animated in the layout effect below.
  const [slot, setSlot] = useState<Slot | null>(() => (attached ? lastSlot.get(label) ?? null : null));
  useLayoutEffect(() => {
    if (!attached) return;
    const measure = () => {
      const track = trackRef.current;
      const chip = chipRefs.current[value];
      if (!track || !chip) {
        setSlot(null);
        return;
      }
      const t = track.getBoundingClientRect();
      const c = chip.getBoundingClientRect();
      const next = { left: c.left - t.left, width: c.width };
      const from = lastSlot.get(label);
      lastSlot.set(label, next);
      setSlot(next);
      if (from && (from.left !== next.left || from.width !== next.width)) {
        slideFrom(fillRef.current, pointerRef.current, from, next);
      }
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (trackRef.current) observer.observe(trackRef.current);
    return () => observer.disconnect();
  }, [attached, value, items, label]);

  return (
    <nav aria-label={label} className={className}>
      <ul ref={trackRef} className={cn(TRACK, attached && "relative")}>
        {attached && slot && (
          // The sliding fill. Chips above it keep their own colours, so the
          // one it sits under reads as filled; the transition is the only
          // thing this element adds.
          <li
            ref={fillRef}
            aria-hidden
            className="pointer-events-none absolute top-1 bottom-1 left-0 rounded-2xs bg-umich-blue"
            style={{ width: slot.width, transform: `translateX(${slot.left}px)` }}
          />
        )}
        {items.map((item) => {
          const active = item.key === value;
          return (
            <li key={item.key} className="relative">
              <Link
                ref={(element) => {
                  chipRefs.current[item.key] = element;
                }}
                to={item.to ?? "#"}
                replace={replace}
                aria-current={active ? "page" : undefined}
                className={cn(
                  chipClass(active),
                  // With the sliding fill behind, the active chip's own fill
                  // is transparent so the two never double up mid-slide.
                  attached && active && "bg-transparent hover:bg-transparent",
                )}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
      {attached && (
        // The rail: a hairline the content hangs from, with a pointer under
        // the active chip. It says "everything below is this tab's".
        <div aria-hidden className="relative mt-3 h-px bg-border-strong">
          {slot && (
            <span
              ref={pointerRef}
              className="absolute -top-[6px] h-3 w-3 border-2 border-border-strong bg-surface"
              style={{ transform: pointerTransform(slot) }}
            />
          )}
        </div>
      )}
    </nav>
  );
}
