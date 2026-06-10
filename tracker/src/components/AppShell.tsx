/**
 * App shell: skip link, header with the seven top-level destinations,
 * and the main landmark. Navigation is a nav landmark with aria-current
 * on the active item. Search is one of the seven and lives at /search.
 */

import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";
import { cn } from "./ui";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/sites", label: "Sites", end: false },
  { to: "/runner", label: "Test Runner", end: false },
  { to: "/issues", label: "Issues", end: false },
  { to: "/reports", label: "Reports", end: false },
  { to: "/settings", label: "Settings", end: false },
  { to: "/search", label: "Search", end: false },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-paper-muted text-ink">
      <a href="#main" className="skip-link">
        Skip to main content
      </a>
      <header className="bg-brand text-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-3">
          <span className="text-lg font-bold">
            <span className="text-brand-accent">A11y</span> Testing Tracker
          </span>
          <nav aria-label="Main">
            <ul className="flex flex-wrap gap-1">
              {NAV_ITEMS.map((item) => (
                <li key={item.to}>
                  {/* NavLink sets aria-current="page" on the active
                      anchor automatically. */}
                  <NavLink
                    to={item.to}
                    end={item.end}
                    className={({ isActive }) =>
                      cn(
                        "inline-flex min-h-target items-center rounded px-3 py-2 font-semibold no-underline",
                        isActive
                          ? "bg-white text-brand"
                          : "text-white hover:bg-white/15",
                      )
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-6xl px-4 py-6" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
