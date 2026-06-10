import { Link, useLocation } from "react-router-dom";
import { LayoutDashboard, Plus, Radar } from "lucide-react";
import type { ReactNode } from "react";
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
    label: "Scans",
    icon: Radar,
    isActive: (p) =>
      p === "/scans" || p.startsWith("/scans/") || p.startsWith("/findings/"),
  },
];

/**
 * Brand mark: maize rounded square with blue "AA". The doubled A is the
 * product initials (AccessibleAccessibility) and a deliberate nod to the
 * WCAG AA conformance badge. Inverted relative to the favicon (blue
 * square, maize letters) because the sidebar is already UMich blue.
 */
function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex shrink-0 select-none items-center justify-center rounded-md bg-umich-maize font-black tracking-tighter text-umich-blue",
        className,
      )}
    >
      AA
    </span>
  );
}

/**
 * App shell: UMich-Blue sidebar with Maize accent for the active item,
 * topbar with the product name + the single global "New scan" CTA,
 * skip-link for a11y, main content area.
 */
export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only-focusable fixed left-2 top-2 z-50 rounded-xs bg-umich-blue px-3 py-1.5 text-fg-inverse"
      >
        Skip to main content
      </a>

      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-h-screen flex-1 flex-col">
          <TopBar />
          <main
            id="main"
            className="flex-1 overflow-auto bg-surface-subtle px-6 py-6 lg:px-8"
          >
            <div className="mx-auto max-w-[1400px]">{children}</div>
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
      className="hidden w-60 flex-col bg-umich-blue text-fg-inverse md:flex"
      aria-label="Primary"
    >
      <div className="flex h-14 items-center gap-2.5 border-b border-white/10 px-4">
        <BrandMark className="h-7 w-7 text-xs" />
        {/* Two-line lockup — the 23-char name fits the w-60 rail cleanly
            stacked; one line would force a font size too small to read. */}
        <span className="text-sm font-semibold leading-tight tracking-tight">
          Accessible
          <br />
          Accessibility
        </span>
      </div>
      <nav className="flex-1 px-2 py-3">
        <ul className="space-y-0.5">
          {NAV.map((item) => {
            const Icon = item.icon;
            const active = item.isActive(pathname);
            return (
              <li key={item.to}>
                <Link
                  to={item.to}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group flex items-center gap-2.5 rounded-xs px-3 py-2 text-sm font-medium no-underline transition-colors",
                    active
                      ? "bg-umich-maize text-umich-blue"
                      : "text-white/85 hover:bg-white/10 hover:text-white",
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden />
                  <span>{item.label}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="border-t border-white/10 px-4 py-3 text-2xs text-white/60">
        <p>Local · offline · accessibility review</p>
      </div>
    </aside>
  );
}

function TopBar() {
  const { pathname } = useLocation();
  const onNewScanForm = pathname === "/scans/new";
  return (
    <header
      className="flex h-14 items-center justify-between border-b border-border bg-surface px-4 sm:px-6"
      role="banner"
    >
      {/* Mobile brand — the sidebar (which carries the brand on desktop)
          is hidden below md, so the topbar shows it instead. */}
      <div className="flex items-center gap-2 text-sm text-fg-muted md:hidden">
        <BrandMark className="h-7 w-7 text-xs" />
        <span className="font-semibold leading-tight text-fg">
          AccessibleAccessibility
        </span>
      </div>

      {/* The ONE global scan CTA. Always visible, every breakpoint —
          icon-only below sm to stay sleek on small screens. On the
          new-scan form itself it renders inert (ghost + aria-disabled):
          a self-link would be noise, but vanishing entirely would make
          users wonder where the button went. */}
      <LinkButton
        to="/scans/new"
        variant={onNewScanForm ? "ghost" : "primary"}
        className={cn("ml-auto", onNewScanForm && "pointer-events-none opacity-50")}
        aria-disabled={onNewScanForm || undefined}
        tabIndex={onNewScanForm ? -1 : undefined}
        aria-label="New scan"
        title="New scan"
      >
        <Plus className="h-4 w-4" aria-hidden />
        <span className="hidden sm:inline">New scan</span>
      </LinkButton>
    </header>
  );
}
