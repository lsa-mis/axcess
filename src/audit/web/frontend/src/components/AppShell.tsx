import { Link, useLocation } from "react-router-dom";
import {
  BarChart3,
  FilePlus2,
  LayoutDashboard,
  ListChecks,
  Radar,
} from "lucide-react";
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

const NAV: NavItem[] = [
  {
    to: "/",
    label: "Dashboard",
    icon: LayoutDashboard,
    isActive: (p) => p === "/",
  },
  {
    // ``Scans`` highlights for any /scans/* route EXCEPT the new-scan
    // form, which has its own item. So /scans, /scans/5, /scans/5/findings,
    // /scans/5/diff, and /findings/123 (a finding always belongs to a scan)
    // all keep the Scans tab lit — the user never loses context for which
    // section they're in.
    to: "/scans",
    label: "Scans",
    icon: Radar,
    isActive: (p) =>
      (p === "/scans" ||
        (p.startsWith("/scans/") && p !== "/scans/new") ||
        p.startsWith("/findings/")),
  },
  {
    to: "/scans/new",
    label: "New scan",
    icon: FilePlus2,
    isActive: (p) => p === "/scans/new",
  },
];

/**
 * App shell: UMich-Blue sidebar with Maize accent for the active item,
 * topbar with the product name + skip-link for a11y, main content area.
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
      <div className="flex h-14 items-center gap-2 border-b border-white/10 px-4">
        <BarChart3 className="h-5 w-5 text-umich-maize" aria-hidden />
        <span className="text-sm font-semibold tracking-tight">
          Image Text Audit
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
        <p>Local · offline · WCAG 1.4.5 review</p>
      </div>
    </aside>
  );
}

function TopBar() {
  return (
    <header
      className="flex h-14 items-center justify-between border-b border-border bg-surface px-6"
      role="banner"
    >
      <div className="flex items-center gap-2 text-sm text-fg-muted md:hidden">
        <BarChart3 className="h-5 w-5 text-umich-blue" aria-hidden />
        <span className="font-semibold text-fg">Image Text Audit</span>
      </div>
      {/* Topbar primary CTA. Hidden on mobile because the sidebar already
          shows "New scan" — it'd just be redundant in a narrow viewport. */}
      <LinkButton
        to="/scans/new"
        variant="primary"
        className="hidden md:inline-flex"
      >
        <ListChecks className="h-4 w-4" aria-hidden />
        Start a new scan
      </LinkButton>
    </header>
  );
}
