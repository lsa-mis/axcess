import { Link, useLocation, useNavigate } from "react-router";
import {
  Info,
  LayoutDashboard,
  Menu,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Radar,
  Search,
  Settings,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "../lib/cn";
import { FEEDBACK_FORM_URL } from "../lib/scanCopy";
import { Button, LinkButton } from "./ui";
import BrandMark from "./BrandMark";
import CommandPalette from "./CommandPalette";
import ReportCrumb, { reportRouteMatch, useReportTrail } from "./ReportCrumb";
import { useScrollRestoration } from "../hooks/useScrollRestoration";
import { useSwipeNavigation } from "../hooks/useSwipeNavigation";
import { setPreference, usePreferences } from "../hooks/usePreferences";
import PreferenceEffects from "./PreferenceEffects";
import ShortcutsDialog from "./ShortcutsDialog";

/**
 * One sidebar entry. ``isActive`` decides whether the item should render
 * as the highlighted current section, we compute it ourselves rather
 * than relying on ``NavLink``'s built-in matching because the routes
 * overlap (``/scans/new`` is a child of ``/scans``) and the default
 * matcher can't disambiguate "you're inside a scan" from "you're on
 * the new-scan form" cleanly.
 */
interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  isActive: (pathname: string) => boolean;
}

/**
 * Nav lists DESTINATIONS only. "New scan" is an action, not a place: it is
 * the single global CTA at the top of the sidebar (the top bar on a phone,
 * where the sidebar is hidden), never in the nav. (Earlier versions had it
 * in several places plus per-page header buttons: three simultaneous
 * "New scan" affordances per screen.) Search and feedback are actions too:
 * they sit in the sidebar beside the nav, not inside it, so the landmark
 * still lists only places.
 */
const NAV: NavItem[] = [
  // The Dashboard is hidden for now; "/" redirects to Reports.
  {
    // ``Scans`` highlights for any /scans/* route INCLUDING the new-scan
    // form (it's contextually part of the scans section now that it has
    // no nav item of its own) and /findings/* (a finding always belongs
    // to a scan), the user never loses context for which section
    // they're in.
    to: "/scans",
    label: "Reports",
    icon: Radar,
    isActive: (p) =>
      p === "/scans" || p.startsWith("/scans/") || p.startsWith("/findings/"),
  },
  // The Product roadmap (/tracking) is hidden from the nav for now; the
  // route still resolves for anyone with the direct link.
];

/** Alt+1..3, in this order (Settings > Keyboard lists the same). */
const PLACE_SHORTCUTS: Record<string, string> = {
  Digit1: "/scans",
  Digit2: "/about",
  Digit3: "/settings",
};

/** A single-character shortcut must never fire while someone is typing. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
}

/**
 * App shell: UMich-Blue sidebar with Maize accent for the active item, the
 * single global "New scan" CTA, search and feedback; topbar with the
 * breadcrumb; skip-link for a11y, main content area.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);
  const prefs = usePreferences();
  const sidebarCollapsed = prefs.sidebar === "collapsed";
  const shortcutsOn = prefs.shortcuts === "on";
  const navigate = useNavigate();
  const [commandOpen, setCommandOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [sidebarNote, setSidebarNote] = useState("");
  const previousPath = useRef(pathname);
  const routeLabel = routeTitle(pathname);
  const reportMatch = reportRouteMatch(pathname);

  // Two-finger swipe back/forward in the desktop app, which has no browser
  // gesture of its own; a no-op in a browser tab, which does.
  useSwipeNavigation();

  // The rail's state is the Settings > Sidebar preference, so the toggle here
  // and the setting there are one value.
  const toggleSidebar = useCallback(
    () => setPreference("sidebar", sidebarCollapsed ? "open" : "collapsed"),
    [sidebarCollapsed],
  );

  // Cmd/Ctrl+K opens the search-everything palette anywhere in the app;
  // Cmd/Ctrl+B shows or hides the sidebar; Alt+1..3 go to the three places
  // and "?" lists them. All of it can be turned off in Settings, for readers
  // whose assistive tech wants the keys.
  useEffect(() => {
    if (!shortcutsOn) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && (event.key === "k" || event.key === "K")) {
        event.preventDefault();
        setCommandOpen((was) => !was);
        return;
      }
      if (
        (event.metaKey || event.ctrlKey) &&
        !event.altKey &&
        !event.shiftKey &&
        (event.key === "b" || event.key === "B")
      ) {
        // Below `md` the sidebar is not drawn at all (the top bar's menu
        // stands in for it), so the key would flip an invisible setting.
        if (!window.matchMedia("(min-width: 768px)").matches) return;
        event.preventDefault();
        toggleSidebar();
        // The button says its state through aria-expanded, but a shortcut
        // leaves focus where it was, so nothing else would tell a screen
        // reader user the key did anything.
        setSidebarNote(sidebarCollapsed ? "Sidebar shown" : "Sidebar hidden");
        return;
      }
      if (event.altKey && !event.metaKey && !event.ctrlKey && !event.shiftKey) {
        // `code`, not `key`: on a Mac, Alt+1 types "¡".
        const to = PLACE_SHORTCUTS[event.code];
        if (to) {
          event.preventDefault();
          navigate(to);
        }
        return;
      }
      if (event.key === "?" && !event.metaKey && !event.ctrlKey && !isTyping(event.target)) {
        event.preventDefault();
        setShortcutsOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, shortcutsOn, sidebarCollapsed, toggleSidebar]);

  useEffect(() => {
    document.title = `${routeLabel} · Axcess`;
    setMobileNavOpen(false);
    if (previousPath.current !== pathname) {
      // `preventScroll` is the whole point: <main> starts below the topbar,
      // so a plain focus() scrolled it flush to the top of the viewport and
      // took the sidebar brand and the topbar with it. Every navigation
      // nudged the page down by the height of the chrome. Focus still moves
      // for screen-reader and keyboard users; the viewport just stays put.
      window.requestAnimationFrame(() =>
        document.getElementById("main")?.focus({ preventScroll: true }),
      );
      previousPath.current = pathname;
    }
  }, [pathname, routeLabel]);

  // A new page starts at the top; Back and Forward return to where the
  // reader was (see the hook). Deliberately not inside the focus effect
  // above: that one runs in a requestAnimationFrame, which never fires while
  // the tab is in the background, and where the page starts should not
  // depend on whether anyone was watching it load.
  useScrollRestoration();

  // While Search is open, everything behind it is `inert`: it cannot take
  // focus, be clicked or be read, as behind a native modal <dialog>. Search
  // only said it was modal (aria-modal), so the page behind could still take
  // focus. A page whose code loaded late, after Search was open again, moved
  // focus to <main> or to its own first field; Enter then did nothing, or
  // submitted New scan's form. Checking for an open dialog before each focus
  // move was rejected: every page that sets focus would need the check, and
  // `inert` is the HTML that means "not now". WAI-ARIA APG Dialog (Modal)
  // pattern, https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/ (content
  // outside the dialog is inert); SC 2.4.3 Focus Order, Level A.
  return (
    <div className="min-h-screen bg-surface-subtle">
      <a
        inert={commandOpen}
        href="#main"
        className="sr-only-focusable fixed left-2 top-2 z-50 rounded-xs bg-umich-blue px-3 py-1.5 text-fg-inverse"
      >
        Skip to main content
      </a>

      <div inert={commandOpen} className="flex min-h-screen items-start">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={toggleSidebar}
          toggleShortcut={shortcutsOn}
          onSearch={() => setCommandOpen(true)}
        />
        <div className="flex min-h-screen min-w-0 flex-1 flex-col">
          <TopBar
            mobileNavOpen={mobileNavOpen}
            onToggleMobileNav={() => setMobileNavOpen((open) => !open)}
            onCloseMobileNav={closeMobileNav}
          >
            {mobileNavOpen && <MobileNav pathname={pathname} onSearch={() => setCommandOpen(true)} />}
          </TopBar>
          <div className="sr-only" aria-live="polite">
            {routeLabel} page loaded
          </div>
          <div className="sr-only" role="status">
            {sidebarNote}
          </div>
          <main
            id="main"
            tabIndex={-1}
            className="min-w-0 flex-1 overflow-auto bg-[radial-gradient(circle_at_top_right,rgba(0,39,76,0.045),transparent_30rem)] px-4 py-6 sm:px-6 sm:py-8 lg:px-10"
          >
            <div className="mx-auto min-w-0 max-w-[1440px]">{children}</div>
          </main>
        </div>
      </div>

      {/* Mounted only while open, so each opening starts with an empty search
          and the first result selected (CommandPalette.tsx). */}
      {commandOpen && (
        <CommandPalette open onClose={() => setCommandOpen(false)} scanId={reportMatch?.scanId ?? null} />
      )}
      <ShortcutsDialog open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
      <PreferenceEffects />
    </div>
  );
}

/**
 * The sidebar's two kinds of control look different on purpose, the way Zen's
 * sidebar sets its button tiles apart from its tab list. New scan and Search
 * are actions: two button tiles side by side at the top, in the app's own
 * button styles. The places below them are flat full-width rows, one of
 * which is lit as where you are.
 */
const SIDEBAR_TILE = "h-12 w-full px-2";

/** One sidebar row, shared by the nav links and the feedback link. */
const SIDEBAR_ROW =
  "group relative flex min-h-target w-full items-center gap-3 rounded-xs py-2.5 text-sm font-semibold no-underline transition-[background-color,color,box-shadow]";
const SIDEBAR_ROW_IDLE = "text-fg-muted hover:bg-umich-blue/10 hover:text-umich-blue";
/**
 * The current place is a white card, the way Zen marks its selected tab:
 * lighter than the sidebar, no outline. It was filled blue, which is the New
 * scan button's colour, so the place you were in read as another button. No
 * border keeps it apart from the bordered Search button, and the bar on its
 * edge marks it by shape as well as by colour.
 *
 * Dark theme: the "white card" is the dark surface there, the same as the
 * sidebar, so the card vanished and its shadow could not show; and the blue
 * text (light blue in this theme) was dimmer than the idle rows' grey, so the
 * current place looked quieter than the rest. In dark it is a light-blue tint,
 * clearly lighter than the sidebar, with the brightest text (16:1 on the
 * sidebar, about 10:1 on the tint) and the same bar. SC 1.4.11 Non-text
 * Contrast and SC 1.4.6 Contrast (Enhanced); the current place is also
 * aria-current="page", so it never rests on colour alone.
 */
const SIDEBAR_ROW_ACTIVE =
  "bg-surface text-umich-blue shadow-[0_2px_10px_rgba(0,39,76,0.10)] before:absolute before:inset-y-2.5 before:left-0 before:w-1 before:rounded-r-full before:bg-umich-blue dark:bg-umich-blue/20 dark:text-fg dark:shadow-none";

/**
 * Search and feedback: reachable from every screen, so they live in the
 * shell. Search leads the sidebar, above the places it can take you;
 * feedback closes it, out of the way of the work. Collapsed, both keep
 * their full name on the control and in the tooltip.
 *
 * Feedback carries no scan context: Asana forms have no documented
 * URL-prefill contract, so there is no supported way to attach the current
 * page, and guessing at one could put a scanned URL into a third-party form.
 */
/**
 * The one "Create New Scan" action. Scan type is chosen on the new-scan page,
 * so this stays mode-neutral: the shell never makes users pick a workflow
 * before they have seen the explanation for each option.
 *
 * It looks and works the same on every screen, the New scan form included.
 * There it is marked aria-current="page", a link to where the reader already
 * is ("Start a new scan, current page, link"), and following it replaces the
 * history entry, so it adds no extra step to Back. It used to turn grey and
 * inert on the form (ghost, 50% opacity, aria-disabled, out of the tab
 * order): that read as broken or unavailable rather than "you are here", and
 * the shell's controls then differed from screen to screen. Changed at the
 * developer's request. Rests on SC 3.2.4 Consistent Identification (Level
 * AA): the same function is identified the same way wherever it appears;
 * and W3C COGA, "Making Content Usable" (https://www.w3.org/TR/coga-usable/):
 * the same control for the same job, everywhere.
 */
function NewScanAction({
  iconOnly,
  className,
  labelClassName,
}: {
  iconOnly: boolean;
  className?: string;
  /** Classes for the "New scan" word, e.g. to show it only from a width up. */
  labelClassName?: string;
}) {
  const { pathname } = useLocation();
  const onNewScanForm = pathname === "/scans/new";
  return (
    <LinkButton
      to="/scans/new"
      variant="primary"
      size="md"
      className={className}
      aria-current={onNewScanForm ? "page" : undefined}
      replace={onNewScanForm}
      aria-label="Start a new scan"
      title="Start a new accessibility scan"
    >
      <Plus className="h-5 w-5 shrink-0" aria-hidden />
      {/* "New scan" fits half the sidebar; the accessible name and tooltip
          keep the full phrase, which contains these words (SC 2.5.3). */}
      {!iconOnly && <span className={labelClassName}>New scan</span>}
    </LinkButton>
  );
}

function SearchAction({
  collapsed,
  onSearch,
  className,
}: {
  collapsed: boolean;
  onSearch: () => void;
  className?: string;
}) {
  return (
    <Button
      type="button"
      variant="secondary"
      onClick={onSearch}
      title="Search everything (Cmd/Ctrl+K)"
      className={cn(SIDEBAR_TILE, className)}
    >
      <Search className="h-5 w-5 shrink-0" aria-hidden />
      {/* The name is real text, the visible word and the rest in
          screen-reader-only text (WCAG technique C7), not an aria-label
          (repo rule: Interface language rule 8). Collapsed, all of it is
          screen-reader-only. */}
      {collapsed ? (
        <span className="sr-only">Search everything (Cmd+K)</span>
      ) : (
        <span>
          Search<span className="sr-only"> everything (Cmd+K)</span>
        </span>
      )}
    </Button>
  );
}

function FeedbackAction({ collapsed }: { collapsed: boolean }) {
  return (
    <a
      href={FEEDBACK_FORM_URL}
      target="_blank"
      rel="noopener noreferrer"
      title="Give feedback (opens in a new tab)"
      className={cn(SIDEBAR_ROW, SIDEBAR_ROW_IDLE, collapsed ? "justify-center px-2" : "px-3")}
    >
      <MessageSquarePlus className="h-5 w-5 shrink-0" aria-hidden />
      {/* Real text, as Search's (see there). */}
      {collapsed ? (
        <span className="sr-only">Give feedback (opens in a new tab)</span>
      ) : (
        <span>
          Give feedback<span className="sr-only"> (opens in a new tab)</span>
        </span>
      )}
    </a>
  );
}

/**
 * About and Settings are places, but reference ones: they sit at the foot of
 * the sidebar with feedback rather than among the working sections, so the
 * nav above stays the places the work happens.
 *
 * Settings was considered right under Reports, where it would be found at
 * a glance. It stays here: moving it would mix the app's own utilities into
 * the places a reader works, and the foot group does not scroll away, so it
 * is always in view anyway. What WCAG asks is that the order never changes
 * from page to page (SC 3.2.3 Consistent Navigation, Level AA), which one
 * fixed foot group gives.
 */
const FOOT_PLACES = [
  { to: "/about", label: "About", name: "About Axcess", icon: Info },
  { to: "/settings", label: "Settings", name: "Settings", icon: Settings },
] as const;

function FootLink({
  place,
  collapsed,
  active,
}: {
  place: (typeof FOOT_PLACES)[number];
  collapsed: boolean;
  active: boolean;
}) {
  const Icon = place.icon;
  return (
    <Link
      to={place.to}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? place.name : undefined}
      title={collapsed ? place.name : undefined}
      className={cn(
        SIDEBAR_ROW,
        collapsed ? "justify-center px-2" : "px-3",
        active ? SIDEBAR_ROW_ACTIVE : SIDEBAR_ROW_IDLE,
      )}
    >
      <Icon className="h-5 w-5 shrink-0" aria-hidden />
      {!collapsed && <span>{place.label}</span>}
    </Link>
  );
}

/** One of the places in NAV, as a sidebar row; the narrow-screen menu uses the same row. */
function NavRow({ item, collapsed, active }: { item: NavItem; collapsed: boolean; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      aria-current={active ? "page" : undefined}
      title={collapsed ? item.label : undefined}
      aria-label={collapsed ? item.label : undefined}
      // min-h-target keeps every nav row at 44px for SC 2.5.5,
      // and the slightly larger icon (h-5) plus base text reads
      // as a primary surface, not a sub-list of links.
      className={cn(
        SIDEBAR_ROW,
        collapsed ? "justify-center px-2" : "px-3",
        active ? SIDEBAR_ROW_ACTIVE : SIDEBAR_ROW_IDLE,
      )}
    >
      <Icon className="h-5 w-5 shrink-0" aria-hidden />
      {!collapsed && <span>{item.label}</span>}
    </Link>
  );
}

/** The sidebar's fill, a light neutral ramp; the narrow-screen menu wears it too. */
const SIDEBAR_FILL =
  "bg-[linear-gradient(180deg,rgb(var(--c-sidebar-1))_0%,rgb(var(--c-sidebar-2))_52%,rgb(var(--c-sidebar-3))_100%)]";

function Sidebar({
  collapsed,
  onToggle,
  toggleShortcut,
  onSearch,
}: {
  collapsed: boolean;
  onToggle: () => void;
  /** Whether Cmd/Ctrl+B toggles it (keyboard shortcuts are on). */
  toggleShortcut: boolean;
  onSearch: () => void;
}) {
  const { pathname } = useLocation();
  return (
    <aside
      className={cn(
        // Light neutral ramp drawn from the surface tokens. Everything on it
        // uses the standard foreground ramp rather than the inverse one: at the
        // darkest stop (#E6EBF2) `fg` is 14.8:1 and `fg-muted` 8.6:1, both AAA.
        // `fg-subtle` would fall to 6.6:1 here, so it is deliberately not used.
        "sticky top-0 hidden h-screen shrink-0 flex-col overflow-y-auto border-r border-border text-fg shadow-[8px_0_30px_rgba(0,39,76,0.05)] transition-[width] duration-150 md:flex",
        SIDEBAR_FILL,
        collapsed ? "w-16" : "w-64",
      )}
      aria-label="Primary"
    >
      <div
        className={cn(
          "flex h-[72px] items-center border-b border-border",
          collapsed ? "justify-center px-2" : "gap-1.5 px-5",
        )}
      >
        {/* Collapsed, the rail is 64px: a 44px target and the wordmark cannot
            both sit here, and the toggle has to win because it is the only way
            back. Expanded, the brand leads and the toggle sits at the far end. */}
        {!collapsed && (
          <>
            <BrandMark className="h-8 w-8 text-umich-blue" />
            {/* The logo: "axcess" in lowercase Comfortaa Bold (font-brand),
                the developer's choice. Comfortaa's round, one-storey "a"
                matches the mark's inner "a", so mark and word read as one
                logo. It is the only lowercase "axcess" and the only
                Comfortaa in the app: page titles, About and every sentence
                keep "Axcess", a name with its capital
                (docs/plain-language.md rule 11), in Atkinson Hyperlegible,
                because round letters look alike when small. Real text, not a
                picture of it: a screen reader says it the same either way,
                and it keeps the theme's colour. No negative letter spacing:
                that was tuned for Atkinson, and Comfortaa's own spacing is
                drawn for it. */}
            <span className="min-w-0 flex-1 truncate font-brand text-xl font-bold leading-tight">
              axcess
            </span>
          </>
        )}
        {/* eslint-disable-next-line react/forbid-elements -- Keep: the sidebar's own control on its dark background */}
        <button
          type="button"
          aria-label={
            collapsed ? "Expand navigation sidebar" : "Collapse navigation sidebar"
          }
          aria-expanded={!collapsed}
          aria-keyshortcuts={toggleShortcut ? "Meta+B Control+B" : undefined}
          title={
            (collapsed ? "Expand sidebar" : "Collapse sidebar") +
            (toggleShortcut ? " (⌘/Ctrl+B)" : "")
          }
          onClick={onToggle}
          className="inline-flex min-h-target min-w-target shrink-0 items-center justify-center rounded-xs text-fg-muted transition-colors hover:bg-umich-blue/10 hover:text-umich-blue"
        >
          {collapsed ? (
            <PanelLeftOpen className="h-5 w-5" aria-hidden />
          ) : (
            <PanelLeftClose className="h-5 w-5" aria-hidden />
          )}
        </button>
      </div>
      {/* Actions first, as one row of button tiles: New scan (filled, the
          primary action) beside Search. Collapsed, the rail is too narrow for
          two, so they stack as icon-only tiles. */}
      <div
        className={cn(
          "grid gap-2 pt-5",
          collapsed ? "grid-cols-1 px-2" : "grid-cols-2 px-3",
        )}
      >
        <NewScanAction iconOnly={collapsed} className={SIDEBAR_TILE} />
        <SearchAction collapsed={collapsed} onSearch={onSearch} />
      </div>
      <nav className={cn("flex-1 pb-5 pt-4", collapsed ? "px-2" : "px-3")}>
        <ul className="space-y-1">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavRow item={item} collapsed={collapsed} active={item.isActive(pathname)} />
            </li>
          ))}
        </ul>
      </nav>
      <div className={cn("space-y-1 border-t border-border py-3", collapsed ? "px-2" : "px-3")}>
        <FeedbackAction collapsed={collapsed} />
        {FOOT_PLACES.map((place) => (
          <FootLink key={place.to} place={place} collapsed={collapsed} active={pathname === place.to} />
        ))}
      </div>
    </aside>
  );
}

/**
 * A pure action bar. It used to also print "Accessibility audit /
 * <route name>", which restated the <h1> sitting a few pixels below it,
 * two orientation lines saying the same thing, neither of which said
 * *which report* you were in. The breadcrumb above each page title is now
 * the single answer to "where am I", and on a desktop that is all this bar
 * carries: "Create New Scan", search and feedback live in the sidebar. On a
 * phone the sidebar is hidden, so the bar keeps the brand, the menu button
 * and the new-scan action.
 */
function TopBar({
  mobileNavOpen,
  onToggleMobileNav,
  onCloseMobileNav,
  children,
}: {
  mobileNavOpen: boolean;
  onToggleMobileNav: () => void;
  onCloseMobileNav: () => void;
  /** The narrow-screen menu, while it is open (see `MobileNav`). */
  children?: ReactNode;
}) {
  const { match: inReport } = useReportTrail();
  const headerRef = useRef<HTMLElement | null>(null);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);

  // The open menu lies over the page (see `MobileNav`), so it closes the way
  // an overlay does: Escape, which puts focus back on the menu button; a
  // click or tap outside the bar and the menu; and focus leaving them, so
  // Tab past the last row cannot land on a link the menu is covering (SC
  // 2.4.11 Focus Not Obscured (Minimum), Level AA). The WAI-ARIA APG
  // Disclosure (Show/Hide) pattern, which the button follows
  // (https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/), asks only for
  // Enter and Space; these are what an overlay adds. Rejected: making the
  // page behind it inert, as for Search. The menu is not a dialog, it is the
  // page's own navigation shown in another place, and a reader may still
  // scroll the page to compare before choosing.
  useEffect(() => {
    if (!mobileNavOpen) return;
    const header = headerRef.current;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      onCloseMobileNav();
      menuButtonRef.current?.focus();
    };
    const onPointerDown = (event: PointerEvent) => {
      if (header && !header.contains(event.target as Node)) onCloseMobileNav();
    };
    const onFocusOut = (event: FocusEvent) => {
      const next = event.relatedTarget as Node | null;
      if (next && header && !header.contains(next)) onCloseMobileNav();
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    header?.addEventListener("focusout", onFocusOut);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
      header?.removeEventListener("focusout", onFocusOut);
    };
  }, [mobileNavOpen, onCloseMobileNav]);

  return (
    <header
      ref={headerRef}
      className="sticky top-0 z-20 flex h-[72px] items-center gap-4 border-b border-border bg-surface/95 px-4 shadow-[0_1px_0_rgba(0,39,76,0.03)] backdrop-blur sm:px-6 lg:px-8"
      role="banner"
    >
      {/* Below md, one line: the menu button, then where you are, then New
          scan. Inside a report "where you are" is the trail, as on a
          desktop, where the trail is in this bar too; elsewhere it is the
          logo, which the hidden sidebar carries on a desktop. The trail
          used to be a second sticky bar under this one, 53 px more of a
          phone's height held over the page on every report screen, and on
          other screens an empty 9 px strip; one bar keeps the page's room
          for the page (W3C COGA, "Making Content Usable",
          https://www.w3.org/TR/coga-usable/: keep the layout simple and the
          same; SC 1.4.10 Reflow, Level AA, asks that content not need two
          scroll directions at 320 px, and a tall sticky header eats the
          one direction left). Rejected: the logo and the trail together,
          which left the trail too little width at 320 px to name the
          report. The trail fits itself to the room it has (ReportCrumb
          cuts the longest crumb first). The trail is the same component
          as the desktop's, so it reads the same. */}
      <div className="flex min-w-0 flex-1 items-center gap-1.5 text-xl text-fg-muted md:hidden">
        {/* eslint-disable-next-line react/forbid-elements -- Keep: the top bar's menu control, styled with the shell */}
        <button
          ref={menuButtonRef}
          type="button"
          aria-label={
            mobileNavOpen
              ? "Close menu"
              : "Open menu"
          }
          aria-expanded={mobileNavOpen}
          aria-controls="mobile-primary-nav"
          onClick={onToggleMobileNav}
          className="inline-flex min-h-target min-w-target items-center justify-center rounded-xs text-fg hover:bg-surface-muted"
        >
          {mobileNavOpen ? (
            <X className="h-5 w-5" aria-hidden />
          ) : (
            <Menu className="h-5 w-5" aria-hidden />
          )}
        </button>
        {inReport ? (
          <div className="min-w-0 flex-1">
            {/* Below 640 px only the step up fits (ReportCrumb says why). */}
            <div className="sm:hidden">
              <ReportCrumb compact />
            </div>
            <div className="hidden sm:block">
              <ReportCrumb />
            </div>
          </div>
        ) : (
          <>
            <BrandMark className="h-8 w-8 text-xs" />
            {/* The same logo as the sidebar's (see there). */}
            <span className="font-brand font-bold leading-tight text-fg">axcess</span>
          </>
        )}
      </div>
      {/* flex-1: the trail's room is the bar's, not its own content's. The
          crumbs are cut to fit this width, so a width that followed them
          would shrink with every cut. */}
      <div className="hidden min-w-0 flex-1 md:block">
        <ReportCrumb />
      </div>
      {/* The same New scan button as the sidebar's, word and all, at every
          width: a plus sign alone said less than the button everywhere
          else, and words are what people know (W3C COGA, "Making Content
          Usable"; repo rule: Interface language rule 8). The trail and the
          logo give up the width it takes. */}
      <div className="ml-auto flex shrink-0 items-center gap-2 md:hidden">
        <NewScanAction iconOnly={false} />
      </div>
      {children}
    </header>
  );
}

/**
 * The sidebar's stand-in below md, built from the sidebar's own parts in the
 * sidebar's order and look: Search, then the places (Reports), then, after a
 * line, Give feedback, About and Settings. One column, each row the full
 * width and 44 px tall, the label after its icon at the left edge, the
 * current place the same white card with a bar as in the sidebar.
 *
 * It was a navy panel of its own: Reports alone in a three-column grid,
 * then Search, About, Settings and Give feedback in a two-column grid with
 * centred labels. The same navigation looked different on a phone and on a
 * desktop, in a different order (SC 3.2.3 Consistent Navigation and SC
 * 3.2.4 Consistent Identification, both Level AA; W3C COGA, "Making Content
 * Usable", https://www.w3.org/TR/coga-usable/: the same control for the
 * same job, everywhere), centred labels in a grid were harder to scan than
 * a list down one edge, and Search and Give feedback took their names from
 * an aria-label. Built from the same parts (SearchAction, NavRow,
 * FeedbackAction, FootLink), the two cannot drift apart again. New scan is
 * not repeated here: it is the New scan button in the top bar, always in
 * view.
 *
 * It lies over the page, inside the sticky top bar and just under it, not
 * in the page's flow. In the flow it opened at the very top of the page, so
 * after scrolling down, the menu button in the sticky bar seemed to do
 * nothing until the reader scrolled back up (found on hardware by the
 * developer). Under the bar it opens where the reader is, and it scrolls
 * inside itself when it is taller than the screen, so its last row is always
 * reachable (SC 1.4.10 Reflow, Level AA). How it closes is with the bar
 * (`TopBar`).
 */
function MobileNav({ pathname, onSearch }: { pathname: string; onSearch: () => void }) {
  return (
    <div
      id="mobile-primary-nav"
      className={cn(
        "absolute inset-x-0 top-full max-h-[calc(100dvh-72px)] overflow-y-auto overscroll-contain",
        "border-b border-border px-3 py-3 text-fg shadow-card md:hidden",
        SIDEBAR_FILL,
      )}
    >
      {/* Full width here, so its icon and word start where the rows' do,
          not centred: one edge to read down (the sidebar centres them in
          its half-width tile). */}
      <SearchAction collapsed={false} onSearch={onSearch} className="justify-start gap-3 px-3" />
      <nav aria-label="Primary" className="pt-3">
        <ul className="space-y-1">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavRow item={item} collapsed={false} active={item.isActive(pathname)} />
            </li>
          ))}
        </ul>
      </nav>
      <div className="mt-3 space-y-1 border-t border-border pt-3">
        <FeedbackAction collapsed={false} />
        {FOOT_PLACES.map((place) => (
          <FootLink key={place.to} place={place} collapsed={false} active={pathname === place.to} />
        ))}
      </div>
    </div>
  );
}

function routeTitle(pathname: string): string {
  const routes: Array<[RegExp, string]> = [
    [/^\/$/, "Reports"],
    [/^\/scans\/?$/, "Reports"],
    [/^\/scans\/new\/?$/, "New scan"],
    [/^\/scans\/protected\/new\/?$/, "New scan"],
    [/^\/scans\/\d+\/protected\/manual-checks\/?$/, "Manual checks for the sign-in scan"],
    [/^\/scans\/\d+\/protected\/issues\/?$/, "Sign-in scan issues"],
    [/^\/scans\/\d+\/protected\/?$/, "Sign-in scan"],
    [
      /^\/scans\/\d+\/(?:review|manual-checks|handoff)\/?$/,
      "Accessibility issues",
    ],
    [/^\/scans\/\d+\/pages\/\d+\/inspect\/?$/, "Page inspector"],
    [/^\/scans\/\d+\/pages\/\d+\/?$/, "Page details"],
    [/^\/scans\/\d+\/issues\/[^/]+\/pages\/\d+\/screenshots\/?$/, "Issue screenshots"],
    [/^\/scans\/\d+\/issues\/[^/]+\/pages\/?$/, "Pages with this kind of issue"],
    [/^\/scans\/\d+\/issues\/[^/]+\/?$/, "Issue evidence"],
    [/^\/scans\/\d+\/issues\/?$/, "Accessibility issues"],
    [/^\/scans\/\d+\/findings\/grouped\/?$/, "Images, grouped by kind of issue"],
    [/^\/scans\/\d+\/findings\/?$/, "Images"],
    [/^\/scans\/\d+\/a11y\/by-rule\/?$/, "Rule check issues by rule"],
    [/^\/scans\/\d+\/a11y\/?$/, "Rule check issues by WCAG criterion"],
    [/^\/scans\/\d+\/compare\/?$/, "Compare reports"],
    // Only running and failed scans render here; a completed report
    // redirects to its issue table.
    [/^\/scans\/\d+\/?$/, "Scan status"],
    [/^\/findings\/\d+\/?$/, "Image details"],
    [/^\/tracking\/?$/, "Product roadmap"],
    [/^\/about\/?$/, "About"],
    [/^\/settings\/?$/, "Settings"],
  ];
  for (const [pattern, title] of routes) {
    if (pattern.test(pathname)) return title;
  }
  return "Page not found";
}
