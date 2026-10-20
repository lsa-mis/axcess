import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { ChevronDown, FileText } from "lucide-react";
import { Button, LinkButton } from "./ui";
import ScanAgainLink from "./ScanAgainLink";
import { cn } from "../lib/cn";

/** The panel's links, in order. */
function panelLinks(panel: HTMLElement | null): HTMLAnchorElement[] {
  return Array.from(panel?.querySelectorAll("a") ?? []);
}

/**
 * Arrow keys, Home and End move between the panel's links. On the document
 * rather than the panel, so the panel stays a plain container and the links
 * keep their own native keyboard handling.
 */
function moveBetweenLinks(event: KeyboardEvent, panel: HTMLElement | null) {
  const links = panelLinks(panel);
  const current = links.indexOf(document.activeElement as HTMLAnchorElement);
  const target =
    event.key === "ArrowDown"
      ? Math.min(current + 1, links.length - 1)
      : event.key === "ArrowUp"
        ? Math.max(current - 1, 0)
        : event.key === "Home"
          ? 0
          : event.key === "End"
            ? links.length - 1
            : null;
  if (target === null || current === -1) return;
  event.preventDefault();
  links[target]?.focus();
}

/**
 * A site row's actions on Reports, behind one "Actions" button: "Open latest
 * scan" (when the site has a completed scan) and "Scan again".
 *
 * - The developer asked for a dropdown (Oct 2026). Two links shown in the
 *   cell were offered instead, because a dropdown hides the row's main
 *   action, opening the report, behind one more click and makes it harder
 *   to find (W3C COGA, "Making Content Usable",
 *   https://www.w3.org/TR/coga-usable/, paraphrased: keep the things people
 *   need visible). The developer chose the dropdown. The Issues count earlier
 *   in the row still opens the same report in one click.
 * - The APG disclosure pattern
 *   (https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/), not the menu
 *   pattern, for the same reasons as ExportMenu: the contents are ordinary
 *   links, so Tab, Enter and a screen reader's link list work as people
 *   expect, and `role="menu"` would take them out of the tab order. Arrow
 *   keys, Home and End also move between the links, as in ExportMenu, so
 *   the two dropdowns behave alike (SC 3.2.4 Consistent Identification,
 *   Level AA).
 * - The button reads "Actions" and, for screen readers only, which site
 *   (technique C7), so each row's button has its own name out of context
 *   (SC 2.4.6 Headings and Labels, Level AA) and its name starts with the
 *   visible word (SC 2.5.3 Label in Name, Level A). No `aria-label`.
 * - The panel is `position: fixed`, placed from the button. The table sits
 *   in a sideways-scrolling region, and a panel placed inside it was cut off
 *   at the region's edge on the last rows. It opens upward when there is not
 *   room below, and it closes when the page or table scrolls rather than
 *   drifting away from its button.
 * - A new component rather than ExportMenu: that one carries one download's
 *   state (sizes, progress, the DRAFT notice) and its own heading. FilterMenu
 *   holds form controls, not links. Neither could take a list of links
 *   without changing what it does.
 */
export default function RowActionsMenu({
  site,
  openScanId,
  scanAgainFromId,
}: {
  /** The site as it is shown, for the screen-reader-only words. */
  site: string;
  /** The latest completed scan to open; leave out when there is none. */
  openScanId?: number;
  /** The scan whose settings "Scan again" starts from. */
  scanAgainFromId: number;
}) {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<CSSProperties>({});
  const panelId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const focusFirstOnOpen = useRef(false);

  useLayoutEffect(() => {
    if (!open) return;
    const button = buttonRef.current?.getBoundingClientRect();
    const panelHeight = panelRef.current?.offsetHeight ?? 0;
    if (!button) return;
    const gap = 6;
    const below = window.innerHeight - button.bottom;
    const upward = below < panelHeight + gap && button.top > below;
    setPlace({
      right: Math.max(window.innerWidth - button.right, 8),
      ...(upward
        ? { bottom: window.innerHeight - button.top + gap }
        : { top: button.bottom + gap }),
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (focusFirstOnOpen.current) {
      focusFirstOnOpen.current = false;
      panelRef.current?.querySelector("a")?.focus();
    }
    const close = () => setOpen(false);
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) close();
    };
    const closeOnOutsideFocus = (event: FocusEvent) => {
      // Coming back to the window refocuses <body>; that is not leaving.
      if (event.target === document.body) return;
      if (!containerRef.current?.contains(event.target as Node)) close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Escape returns focus to the button, never to the top of the page.
        close();
        buttonRef.current?.focus();
        return;
      }
      moveBetweenLinks(event, panelRef.current);
    };
    document.addEventListener("mousedown", closeOnOutsidePointer);
    document.addEventListener("focusin", closeOnOutsideFocus);
    document.addEventListener("keydown", onKeyDown);
    // Scrolling or resizing closes the panel. If focus was on one of its
    // links, it goes back to the button, as Escape does, so a keyboard user
    // who scrolled with Page Down is not left focused on a hidden link
    // (SC 2.4.7 Focus Visible, Level AA). `preventScroll`, so returning
    // focus does not scroll the page back. Focus elsewhere is left alone.
    const closeOnMove = () => {
      if (panelRef.current?.contains(document.activeElement)) {
        buttonRef.current?.focus({ preventScroll: true });
      }
      close();
    };
    // Capture, so scrolling the table's own region closes it too.
    window.addEventListener("scroll", closeOnMove, true);
    window.addEventListener("resize", closeOnMove);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsidePointer);
      document.removeEventListener("focusin", closeOnOutsideFocus);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", closeOnMove, true);
      window.removeEventListener("resize", closeOnMove);
    };
  }, [open]);

  function onTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    // Opening adds the document listener before this key press reaches the
    // document; without this it would move on to the second link.
    event.stopPropagation();
    if (open) {
      panelLinks(panelRef.current)[0]?.focus();
    } else {
      focusFirstOnOpen.current = true;
      setOpen(true);
    }
  }

  return (
    <div ref={containerRef} className="inline-block">
      <Button
        ref={buttonRef}
        type="button"
        variant="ghost"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
        onKeyDown={onTriggerKeyDown}
        className="whitespace-nowrap px-3"
      >
        Actions
        <span className="sr-only"> for {site}</span>
        <ChevronDown
          className={cn("h-3.5 w-3.5 motion-safe:transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </Button>
      <div
        ref={panelRef}
        id={panelId}
        hidden={!open}
        style={place}
        className="fixed z-30 min-w-[13rem] rounded-xs border border-border bg-surface p-1.5 text-left shadow-raised"
      >
        <ul>
          {openScanId !== undefined && (
            <li>
              <LinkButton
                to={`/scans/${openScanId}`}
                variant="ghost"
                className="w-full justify-start whitespace-nowrap"
              >
                <FileText className="h-4 w-4" aria-hidden />
                Open latest scan
                <span className="sr-only"> of {site}, the most recent completed scan</span>
              </LinkButton>
            </li>
          )}
          <li>
            <ScanAgainLink
              scanId={scanAgainFromId}
              site={site}
              variant="ghost"
              className="w-full justify-start"
            />
          </li>
        </ul>
      </div>
    </div>
  );
}
