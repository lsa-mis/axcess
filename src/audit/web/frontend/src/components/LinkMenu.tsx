import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";
import { Link } from "react-router";
import { ChevronDown } from "lucide-react";
import { cn } from "../lib/cn";
import { Button } from "./ui";

/** One place the menu goes. */
export type LinkMenuItem = {
  key: string;
  to: string;
  /** The visible words: "Report #20". */
  label: string;
  /** Screen-reader-only words after them: " (compare with report #24)". */
  context?: string;
};

/**
 * A button that shows a short list of links under it: "Compare with" on a
 * scan row of Reports, whose links each open Compare reports for that row
 * and the report chosen.
 *
 * Why it is built this way (keep these when you change it):
 *
 * - **Links, not a select that goes somewhere when you choose.** A select
 *   that opens another page as soon as a value is chosen changes the page
 *   on input. WCAG 2.2 SC 3.2.2 On Input (Level A): "Changing the setting
 *   of any user interface component does not automatically cause a change
 *   of context unless the user has been advised of the behavior before
 *   using the component." A list of links changes nothing until one is
 *   followed, and a link is what goes to a page.
 * - **The WAI-ARIA APG disclosure pattern**, not the menu pattern
 *   (https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/): a button with
 *   `aria-expanded` and `aria-controls`, and the links right after it in
 *   the tab order, so Tab, Enter and a screen reader's links list behave as
 *   they do for every other link. `role="menu"` would take the links out of
 *   the tab order and needs menu keys screen readers handle unevenly. The
 *   arrow keys, Home and End also move between the links, as in Export
 *   report, because the panel looks like the app's dropdowns.
 * - **How it closes**: Escape (focus goes back to the button, so it is
 *   never dropped at the top of the page; SC 2.4.3 Focus Order, Level A),
 *   pressing the button again, a press outside it, focus moving out of it,
 *   and following a link. **Never on scroll.** An earlier row dropdown on
 *   Reports closed when the page scrolled, which caught screen-magnifier
 *   users, who pan by scrolling (routes/Scans.tsx, "Actions"). The panel
 *   follows its button as the page or the table scrolls instead.
 * - **It floats in place, fixed to the window.** The rows sit in a table
 *   region that scrolls sideways, and a panel positioned inside it was cut
 *   off at the region's edge. A fixed panel is not clipped by the region,
 *   and it stays in the DOM right after its button, so the tab order still
 *   follows the reading order. It opens under the button, or over it when
 *   there is more room above, and never under the 72px top bar, so a
 *   focused link is never hidden (SC 2.4.11 Focus Not Obscured (Minimum),
 *   Level AA). A long list scrolls inside the panel. `data-menu-open` on
 *   the wrapper lets the cell around it rise above the rows after it while
 *   it is open (see ScanRow).
 * - **Words**: the button's name starts with its visible words, then adds
 *   screen-reader-only words that say which row it is for; each link reads
 *   its visible words, then what it does (technique C7; SC 2.5.3 Label in
 *   Name, Level A; SC 2.4.4 Link Purpose (In Context), Level AA). No
 *   `aria-label`, so the words are real text (docs/plain-language.md
 *   rule 8). Every target is 44px tall (SC 2.5.5 Target Size (Enhanced),
 *   Level AAA).
 *
 * Considered and not extended: Export report (ExportMenu), whose panel is
 * the export's own (file sizes, download states, announcements) and hangs
 * inside its parent, which a table region clips; the Filter menu
 * (table/FilterMenu), a panel of form controls that apply at once; and
 * `Disclosure` (ui.tsx), a heading-level section that opens in the flow of
 * the page, where a heading inside a table cell would break the outline.
 * This component keeps their keys and their closing rules.
 */
export default function LinkMenu({
  label,
  labelContext,
  intro,
  items,
}: {
  /** The button's visible words: "Compare with". */
  label: string;
  /** Screen-reader-only words after them: " another report, for report #24". */
  labelContext?: string;
  /** A short visible line at the top of the panel. */
  intro?: ReactNode;
  items: readonly LinkMenuItem[];
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const container = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const focusFirstOnOpen = useRef(false);
  const [place, setPlace] = useState<{ top: number; left: number; maxHeight: number } | null>(null);

  // Where the panel goes, measured before it is painted, and again whenever
  // anything scrolls (the page, or the table region sideways) or the window
  // changes size, so it stays with its button.
  useLayoutEffect(() => {
    if (!open) {
      setPlace(null);
      return;
    }
    const update = () => {
      const anchor = button.current?.getBoundingClientRect();
      const node = panel.current;
      if (!anchor || !node) return;
      const gap = 6;
      const edge = 8;
      // The sticky top bar is 72px tall; 16px more, as the page's scroll
      // padding leaves (styles.css).
      const topLimit = 88;
      const width = node.offsetWidth;
      // Its whole height, borders too, even while a smaller window caps it.
      const height = node.scrollHeight + (node.offsetHeight - node.clientHeight);
      const below = window.innerHeight - anchor.bottom - gap - edge;
      const above = anchor.top - gap - topLimit;
      const up = height > below && above > below;
      const maxHeight = Math.max(132, up ? above : below);
      const shown = Math.min(height, maxHeight);
      setPlace({
        top: up ? anchor.top - gap - shown : anchor.bottom + gap,
        // Hung from the button's right edge, as Export report is, and kept
        // inside the window.
        left: Math.max(edge, Math.min(anchor.right - width, window.innerWidth - width - edge)),
        maxHeight,
      });
    };
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [open]);

  // Down arrow on the button opens the list on its first link, once the
  // list has its place: until then it is hidden, and cannot take focus.
  useEffect(() => {
    if (!open || !place || !focusFirstOnOpen.current) return;
    focusFirstOnOpen.current = false;
    panel.current?.querySelector("a")?.focus();
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const outside = (target: EventTarget | null) => !container.current?.contains(target as Node | null);
    const onPointer = (event: PointerEvent) => {
      if (outside(event.target)) setOpen(false);
    };
    const onFocus = (event: FocusEvent) => {
      // Coming back to the window focuses <body>; that is not focus leaving.
      if (event.target === document.body) return;
      if (outside(event.target)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("focusin", onFocus);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("focusin", onFocus);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const links = () => Array.from(panel.current?.querySelectorAll("a") ?? []);

  const onButtonKey = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    if (open) links()[0]?.focus();
    else {
      focusFirstOnOpen.current = true;
      setOpen(true);
    }
  };

  const onLinkKey = (event: ReactKeyboardEvent<HTMLAnchorElement>) => {
    const all = links();
    const at = all.indexOf(event.currentTarget);
    const next =
      event.key === "ArrowDown"
        ? Math.min(at + 1, all.length - 1)
        : event.key === "ArrowUp"
          ? Math.max(at - 1, 0)
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? all.length - 1
              : null;
    if (next === null || at === -1) return;
    event.preventDefault();
    all[next]?.focus();
  };

  return (
    <div ref={container} data-menu-open={open || undefined}>
      <Button
        ref={button}
        type="button"
        variant="ghost"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={onButtonKey}
        className="report-link whitespace-nowrap"
      >
        {label}
        {labelContext && <span className="sr-only">{labelContext}</span>}
        <ChevronDown
          className={cn("h-4 w-4 shrink-0 motion-safe:transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </Button>
      {/* Always in the DOM, so `aria-controls` names a real element. Hidden
          until it has a place, so it never flashes at the window's corner. */}
      <div
        ref={panel}
        id={panelId}
        hidden={!open}
        style={
          place
            ? { top: place.top, left: place.left, maxHeight: place.maxHeight }
            : { top: 0, left: 0, visibility: "hidden" }
        }
        className="fixed z-30 min-w-[12rem] max-w-[calc(100vw-1rem)] overflow-y-auto rounded-xs border border-border bg-surface-raised p-1.5 text-left shadow-raised"
      >
        {intro && <p className="whitespace-normal px-2.5 pb-1 pt-1.5 text-xs font-semibold text-fg-muted">{intro}</p>}
        <ul>
          {items.map((item) => (
            <li key={item.key}>
              <Link
                to={item.to}
                onClick={() => setOpen(false)}
                onKeyDown={onLinkKey}
                className="report-link flex min-h-target items-center rounded-2xs px-2.5 py-2 text-sm font-semibold hover:bg-surface-muted"
              >
                {item.label}
                {item.context && <span className="sr-only">{item.context}</span>}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
