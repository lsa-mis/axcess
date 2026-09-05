import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { CornerDownLeft, Search } from "lucide-react";
import { api } from "../api/client";
import { siteLabel } from "./ReportCrumb";
import { cn } from "../lib/cn";

type Item = {
  id: string;
  group: string;
  label: string;
  sublabel?: string;
  to: string;
};

/**
 * Cmd/Ctrl+K command palette, search everything across the app.
 *
 * Quick actions (Dashboard, New scan, Reports, Tracking), every report (by site
 * URL), and, when you're inside a report, every issue in it. Fully keyboard
 * driven: type to filter, ↑/↓ to move, ↵ to open, Esc to close. Screen-reader
 * friendly: a modal dialog with a labelled dialog/listbox.
 */
export default function CommandPalette({
  open,
  onClose,
  scanId,
}: {
  open: boolean;
  onClose: () => void;
  scanId?: number | null;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const scansQuery = useQuery({
    queryKey: ["scans"],
    queryFn: () => api.listScans(),
    enabled: open,
  });
  const issuesQuery = useQuery({
    queryKey: ["issues", scanId],
    queryFn: () => api.listIssues(scanId as number),
    enabled: open && !!scanId,
  });

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);
  useEffect(() => setActive(0), [query]);

  const act = (item: Item | undefined) => {
    if (!item) return;
    navigate(item.to);
    onClose();
  };

  const items = useMemo<Item[]>(() => {
    const q = query.trim().toLowerCase();
    const out: Item[] = [];

    const actions: Item[] = [
      { id: "nav-dashboard", group: "Go to", label: "Dashboard", to: "/" },
      { id: "nav-reports", group: "Go to", label: "Reports", to: "/scans" },
      { id: "nav-new", group: "Go to", label: "New scan", to: "/scans/new" },
      { id: "nav-tracking", group: "Go to", label: "Coverage & tracking", to: "/tracking" },
    ];
    for (const a of actions) if (!q || a.label.toLowerCase().includes(q)) out.push(a);

    for (const s of scansQuery.data ?? []) {
      const label = siteLabel(s.seed_url);
      if (!q || label.toLowerCase().includes(q) || `#${s.id}`.includes(q) || String(s.id).includes(q)) {
        out.push({
          id: `scan-${s.id}`,
          group: "Reports",
          label,
          sublabel: `#${s.id} · ${s.status}`,
          to: `/scans/${s.id}`,
        });
      }
    }

    if (scanId) {
      for (const i of issuesQuery.data?.rows ?? []) {
        const hay = `${i.title} ${i.issue_key} ${i.wcag_sc ?? ""} ${i.wcag_name ?? ""}`.toLowerCase();
        if (!q || hay.includes(q)) {
          out.push({
            id: `issue-${scanId}-${i.issue_key}`,
            group: "Issues",
            label: i.title,
            sublabel: `${i.issue_key} · ${i.pipeline}`,
            to: i.detail_url,
          });
        }
      }
    }
    return out;
  }, [query, scansQuery.data, issuesQuery.data, scanId]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((a) => Math.min(a + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      act(items[active]);
    } else if (event.key === "Escape") {
      onClose();
    }
  };

  useEffect(() => {
    if (listRef.current) {
      const el = listRef.current.children[active] as HTMLElement | undefined;
      el?.scrollIntoView({ block: "nearest" });
    }
  }, [active]);

  if (!open) return null;

  let lastGroup = "";
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]">
      {/* Backdrop is a real <button> so click-to-close is keyboard- and
          screen-reader-friendly and the a11y interaction rules are satisfied. */}
      <button
        type="button"
        aria-label="Close search"
        onClick={onClose}
        className="absolute inset-0 h-full w-full cursor-default bg-black/40"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search everything"
        className="relative z-10 w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface shadow-2xl"
      >
        <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
          <Search className="h-4 w-4 shrink-0 text-fg-subtle" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search reports, issues, and actions…"
            aria-label="Search"
            className="min-w-0 flex-1 bg-transparent text-base text-fg outline-none placeholder:text-fg-subtle"
          />
          <kbd className="hidden shrink-0 rounded-2xs border border-border bg-surface-muted px-1.5 py-0.5 text-2xs text-fg-subtle sm:inline">
            esc
          </kbd>
        </div>

        <ul ref={listRef} role="listbox" aria-label="Results" className="max-h-[50vh] overflow-y-auto py-1">
          {items.length === 0 ? (
            <li className="px-4 py-8 text-center text-sm text-fg-muted">No matches for “{query}”.</li>
          ) : (
            items.map((item, index) => {
              const showHeader = item.group !== lastGroup;
              lastGroup = item.group;
              return (
                <Fragment key={item.id}>
                  {showHeader && (
                    <li className="px-4 pb-1 pt-3 text-2xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
                      {item.group}
                    </li>
                  )}
                  <li>
                    <button
                      type="button"
                      role="option"
                      aria-selected={index === active}
                      onClick={() => act(item)}
                      onMouseEnter={() => setActive(index)}
                      className={cn(
                        "block w-full px-4 py-2 text-left",
                        index === active ? "bg-umich-blue/10" : "hover:bg-surface-muted",
                      )}
                    >
                      <span className="block text-sm font-medium text-fg">{item.label}</span>
                      {item.sublabel && (
                        <span className="block text-2xs text-fg-muted">{item.sublabel}</span>
                      )}
                    </button>
                  </li>
                </Fragment>
              );
            })
          )}
        </ul>

        <div className="flex items-center gap-3 border-t border-border px-3 py-2 text-2xs text-fg-subtle">
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded-2xs border border-border bg-surface-muted px-1 py-0.5">↑↓</kbd> navigate
          </span>
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded-2xs border border-border bg-surface-muted px-1 py-0.5">↵</kbd> open
          </span>
          <span className="ml-auto inline-flex items-center gap-1">
            <CornerDownLeft className="h-3 w-3" aria-hidden /> ⌘K anytime
          </span>
        </div>
      </div>
    </div>
  );
}
