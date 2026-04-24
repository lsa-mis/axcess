import { NavLink } from "react-router-dom";
import {
  BarChart3,
  FilePlus2,
  LayoutDashboard,
  ListChecks,
  Radar,
} from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/scans", label: "Scans", icon: Radar, end: true },
  { to: "/scans/new", label: "New scan", icon: FilePlus2 },
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
            return (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    cn(
                      "group flex items-center gap-2.5 rounded-xs px-3 py-2 text-sm font-medium no-underline transition-colors",
                      isActive
                        ? "bg-umich-maize text-umich-blue"
                        : "text-white/85 hover:bg-white/10 hover:text-white",
                    )
                  }
                >
                  <Icon className="h-4 w-4 shrink-0" aria-hidden />
                  <span>{item.label}</span>
                </NavLink>
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
      <NavLink
        to="/scans/new"
        className="hidden items-center gap-1.5 rounded-xs bg-umich-blue px-3 py-1.5 text-sm font-semibold text-fg-inverse no-underline hover:bg-umich-blue-600 md:inline-flex"
      >
        <ListChecks className="h-4 w-4" aria-hidden />
        Start a new scan
      </NavLink>
    </header>
  );
}
