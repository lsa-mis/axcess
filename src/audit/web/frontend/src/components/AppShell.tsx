import { Link, useLocation } from "react-router";
import {
  LayoutDashboard,
  ListChecks,
  LockKeyhole,
  Menu,
  Plus,
  Radar,
  X,
} from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "../lib/cn";
import { LinkButton } from "./ui";

/**
 * One sidebar entry. ``isActive`` decides whether the item should render
 * as the highlighted current section — we compute it ourselves rather
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
 * Nav lists DESTINATIONS only. "New scan" is an action, not a place —
 * it lives in the topbar as the single global CTA, never in the nav.
 * (Earlier versions had it in both places plus per-page header buttons:
 * three simultaneous "New scan" affordances per screen.)
 */
const NAV: NavItem[] = [
  {
    to: "/",
    label: "Dashboard",
    icon: LayoutDashboard,
    isActive: (p) => p === "/",
  },
  {
    // ``Scans`` highlights for any /scans/* route INCLUDING the new-scan
    // form (it's contextually part of the scans section now that it has
    // no nav item of its own) and /findings/* (a finding always belongs
    // to a scan) — the user never loses context for which section
    // they're in.
    to: "/scans",
    label: "Reports",
    icon: Radar,
    isActive: (p) =>
      p === "/scans" || p.startsWith("/scans/") || p.startsWith("/findings/"),
  },
  {
    to: "/tracking",
    label: "Tracking",
    icon: ListChecks,
    isActive: (p) => p === "/tracking",
  },
];

/**
 * Brand mark: maize rounded square with blue "Ax" — the product wordmark
 * (Axcess = access + the axe-core engine at its centre). Inverted relative
 * to the favicon (blue square, maize letters) because the sidebar is
 * already UMich blue.
 */
function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 select-none items-center justify-center rounded-[10px] bg-umich-maize font-black tracking-tighter text-umich-blue shadow-[0_5px_16px_rgba(255,203,5,0.18)]",
        className,
      )}
    >
      Ax
    </span>
  );
}

/**
 * App shell: UMich-Blue sidebar with Maize accent for the active item,
 * topbar with the product name + the single global "New scan" CTA,
 * skip-link for a11y, main content area.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const previousPath = useRef(pathname);
  const routeLabel = routeTitle(pathname);

  useEffect(() => {
    document.title = `${routeLabel} · Axcess`;
    setMobileNavOpen(false);
    if (previousPath.current !== pathname) {
      window.requestAnimationFrame(() =>
        document.getElementById("main")?.focus(),
      );
      previousPath.current = pathname;
    }
  }, [pathname, routeLabel]);

  return (
    <div className="min-h-screen bg-surface-subtle">
      <a
        href="#main"
        className="sr-only-focusable fixed left-2 top-2 z-50 rounded-xs bg-umich-blue px-3 py-1.5 text-fg-inverse"
      >
        Skip to main content
      </a>

      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-h-screen min-w-0 flex-1 flex-col">
          <TopBar
            routeLabel={routeLabel}
            mobileNavOpen={mobileNavOpen}
            onToggleMobileNav={() => setMobileNavOpen((open) => !open)}
          />
          {mobileNavOpen && <MobileNav pathname={pathname} />}
          <div className="sr-only" aria-live="polite">
            {routeLabel} page loaded
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
    </div>
  );
}

function Sidebar() {
  const { pathname } = useLocation();
  return (
    <aside
      className="hidden w-64 shrink-0 flex-col bg-[linear-gradient(180deg,#001E3C_0%,#00274C_52%,#00315F_100%)] text-fg-inverse shadow-[8px_0_30px_rgba(0,39,76,0.08)] md:flex"
      aria-label="Primary"
    >
      <div className="flex h-[72px] items-center gap-3 border-b border-white/10 px-5">
        <BrandMark className="h-9 w-9 text-sm" />
        <div className="min-w-0">
          <span className="block text-lg font-semibold leading-tight tracking-[-0.025em]">
            Axcess
          </span>
          <span className="block text-2xs font-medium tracking-wide text-surface-inverse-fg-subtle">
            Accessibility workbench
          </span>
        </div>
      </div>
      <nav className="flex-1 px-3 py-5">
        <p className="mb-2 px-3 text-2xs font-semibold uppercase tracking-[0.16em] text-surface-inverse-fg-subtle">
          Workspace
        </p>
        <ul className="space-y-1">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = item.isActive(pathname);
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  aria-current={active ? "page" : undefined}
                  // min-h-target keeps every nav row at 44px for SC 2.5.5,
                  // and the slightly larger icon (h-5) plus base text reads
                  // as a primary surface, not a sub-list of links.
                  className={cn(
                    "group relative flex min-h-target items-center gap-3 rounded-xs px-3 py-2.5 text-sm font-semibold no-underline transition-[background-color,color,box-shadow]",
                    active
                      ? "bg-white text-umich-blue shadow-[0_6px_18px_rgba(0,0,0,0.13)]"
                      : "text-surface-inverse-fg-subtle hover:bg-white/10 hover:text-white",
                  )}
                >
                  <Icon className="h-5 w-5 shrink-0" aria-hidden />
                  <span>{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {/* Footer caption uses the `inverse-fg-subtle` token (#C9D4E0) — at
          10:1 against UMich Blue it clears AAA. Plain `text-white/60`
          rendered as ~#99A9B7, which axe flagged at 6.24:1 (fails AAA). */}
      <div className="border-t border-white/10 px-5 py-4 text-2xs text-surface-inverse-fg-subtle">
        <p className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-umich-maize" aria-hidden />
          Local-first evidence workspace
        </p>
      </div>
    </aside>
  );
}

function TopBar({
  routeLabel,
  mobileNavOpen,
  onToggleMobileNav,
}: {
  routeLabel: string;
  mobileNavOpen: boolean;
  onToggleMobileNav: () => void;
}) {
  const { pathname, search } = useLocation();
  const loginMode = new URLSearchParams(search).get("mode") === "login";
  const onNewScanForm = pathname === "/scans/new" && !loginMode;
  const onProtectedScanForm =
    (pathname === "/scans/new" && loginMode) ||
    pathname === "/scans/protected/new";
  return (
    <header
      className="flex h-[72px] items-center justify-between border-b border-border bg-white/95 px-4 shadow-[0_1px_0_rgba(0,39,76,0.03)] backdrop-blur sm:px-6 lg:px-8"
      role="banner"
    >
      {/* Mobile brand — the sidebar (which carries the brand on desktop)
          is hidden below md, so the topbar shows it instead. */}
      <div className="flex min-w-0 items-center gap-2 text-sm text-fg-muted md:hidden">
        <button
          type="button"
          aria-label={
            mobileNavOpen
              ? "Close primary navigation"
              : "Open primary navigation"
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
        <BrandMark className="h-8 w-8 text-xs" />
        <span className="hidden font-semibold leading-tight text-fg sm:inline">
          Axcess
        </span>
      </div>
      <div className="hidden min-w-0 md:block">
        <p className="text-2xs font-semibold uppercase tracking-[0.16em] text-fg-subtle">
          Accessibility audit
        </p>
        <p className="truncate text-sm font-semibold text-fg">{routeLabel}</p>
      </div>
      {/* Public and authenticated scans are different security workflows, so
          keep both choices visible at the app level. At narrow widths the
          icons retain explicit accessible names and titles without forcing
          the header wider than the viewport. */}
      <div className="ml-auto flex items-center gap-2">
        <LinkButton
          to="/scans/new?mode=login"
          variant={onProtectedScanForm ? "ghost" : "secondary"}
          size="md"
          className={cn(
            onProtectedScanForm && "pointer-events-none opacity-50",
          )}
          aria-disabled={onProtectedScanForm || undefined}
          tabIndex={onProtectedScanForm ? -1 : undefined}
          aria-label="2FA or login scan"
          title="Scan a site that requires login or 2FA"
        >
          <LockKeyhole className="h-5 w-5" aria-hidden />
          <span className="hidden sm:inline">2FA / login scan</span>
        </LinkButton>
        <LinkButton
          to="/scans/new"
          variant={onNewScanForm ? "ghost" : "primary"}
          size="md"
          className={cn(onNewScanForm && "pointer-events-none opacity-50")}
          aria-disabled={onNewScanForm || undefined}
          tabIndex={onNewScanForm ? -1 : undefined}
          aria-label="New public scan"
          title="Scan a public site"
        >
          <Plus className="h-5 w-5" aria-hidden />
          <span className="hidden sm:inline">Public scan</span>
        </LinkButton>
      </div>
    </header>
  );
}

function MobileNav({ pathname }: { pathname: string }) {
  return (
    <nav
      id="mobile-primary-nav"
      aria-label="Primary"
      className="border-b border-border bg-umich-blue p-2 text-white shadow-card md:hidden"
    >
      <ul className="grid grid-cols-3 gap-1">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = item.isActive(pathname);
          return (
            <li key={item.to}>
              <Link
                to={item.to}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex min-h-target items-center justify-center gap-2 rounded-xs px-2 py-2 text-sm font-semibold no-underline",
                  active
                    ? "bg-white text-umich-blue"
                    : "text-white hover:bg-white/10",
                )}
              >
                <Icon className="h-4 w-4" aria-hidden />
                <span>{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function routeTitle(pathname: string): string {
  const routes: Array<[RegExp, string]> = [
    [/^\/$/, "Dashboard"],
    [/^\/scans\/?$/, "Reports"],
    [/^\/scans\/new\/?$/, "New scan"],
    [/^\/scans\/protected\/new\/?$/, "2FA / login scan"],
    [/^\/scans\/\d+\/protected\/manual-checks\/?$/, "Protected manual checks"],
    [/^\/scans\/\d+\/protected\/issues\/?$/, "Protected issue index"],
    [/^\/scans\/\d+\/protected\/?$/, "Protected companion"],
    [
      /^\/scans\/\d+\/(?:review|manual-checks|handoff)\/?$/,
      "Accessibility issues",
    ],
    [/^\/scans\/\d+\/pages\/\d+\/?$/, "Page evidence"],
    [/^\/scans\/\d+\/issues\/[^/]+\/?$/, "Issue evidence"],
    [/^\/scans\/\d+\/issues\/?$/, "Accessibility issues"],
    [/^\/scans\/\d+\/findings\/grouped\/?$/, "Grouped image evidence"],
    [/^\/scans\/\d+\/findings\/?$/, "Image evidence"],
    [/^\/scans\/\d+\/a11y\/by-rule\/?$/, "DOM-engine rules"],
    [/^\/scans\/\d+\/a11y\/?$/, "DOM-engine evidence"],
    [/^\/scans\/\d+\/diff\/?$/, "Verify changes"],
    [/^\/scans\/\d+\/?$/, "Report overview"],
    [/^\/findings\/\d+\/?$/, "Finding evidence"],
    [/^\/tracking\/?$/, "Coverage tracking"],
  ];
  for (const [pattern, title] of routes) {
    if (pattern.test(pathname)) return title;
  }
  return "Page not found";
}
