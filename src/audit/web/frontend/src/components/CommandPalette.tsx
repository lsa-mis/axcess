import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Check, CornerDownLeft, Search } from "lucide-react";
import { api } from "../api/client";
import { siteLabel } from "./ReportCrumb";
import { cn } from "../lib/cn";
import { CHECK_LABEL, SCAN_STATUS_LABEL } from "../lib/terms";
import { ALL_SETTINGS } from "../lib/settingsCatalog";
import type { Preferences } from "../lib/preferences";
import { setPreference, usePreferences } from "../hooks/usePreferences";

type Item = {
  id: string;
  group: string;
  label: string;
  sublabel?: string;
} & (
  | { to: string; setting?: undefined }
  /** A choice for one setting: Enter applies it here, and Search stays open. */
  | { to?: undefined; setting: { key: keyof Preferences; value: string; current: boolean; name: string; option: string } }
);

/**
 * How many settings a query may list the choices of. A short query such as
 * "t" matches most of them, and a list of sixty choices is not a result; the
 * Settings page, which the same query also finds, has them all.
 */
const MAX_SETTINGS = 4;

/**
 * Every place the sidebar links to, plus the New scan action. Keep in step
 * with NAV and FOOT_PLACES in AppShell: a page missing here cannot be found
 * by search at all.
 *
 * ``terms`` are what a reader might type instead of the page name. For
 * Settings they are its setting labels (from lib/settingsCatalog, which the
 * lazy Settings route shares, so the entry bundle does not pull the route
 * in), so "dark" or "font" finds the page that holds them.
 */
const PLACES: ReadonlyArray<{ id: string; label: string; to: string; terms?: readonly string[] }> = [
  { id: "nav-reports", label: "Reports", to: "/scans" },
  { id: "nav-new", label: "New scan", to: "/scans/new" },
  {
    id: "nav-about",
    label: "About Axcess",
    to: "/about",
    terms: ["Help", "Version", "Documentation", "Privacy and data", "FAQ", "Download desktop builds"],
  },
  {
    id: "nav-settings",
    label: "Settings",
    to: "/settings",
    terms: ["Preferences", "Dark mode", ...ALL_SETTINGS.map((row) => row.label)],
  },
];

/**
 * Cmd/Ctrl+K command palette, search everything across the app.
 *
 * Every place (Reports, New scan, About, Settings), every report (by site
 * URL), and, when you're inside a report, every issue in it. A query that
 * names a setting ("dark", "text size", "motion") also lists that setting's
 * choices, so it can be changed right here: Enter applies the choice, Search
 * stays open, and a status message says what changed. Fully keyboard
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
  const [message, setMessage] = useState("");
  const prefs = usePreferences();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

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
    setMessage("");
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);
  useEffect(() => {
    setActive(0);
    setMessage("");
  }, [query]);

  const act = (item: Item | undefined) => {
    if (!item) return;
    if (item.setting) {
      // Applied at once, as on the Settings page. The list keeps its place,
      // so the next choice is one arrow key away.
      const { key, value, name, option } = item.setting;
      setPreference(key, value as Preferences[typeof key]);
      setMessage(`${name} is now ${option}.`);
      return;
    }
    navigate(item.to);
    onClose();
  };

  const items = useMemo<Item[]>(() => {
    const q = query.trim().toLowerCase();
    const out: Item[] = [];

    for (const place of PLACES) {
      const item = { id: place.id, group: "Go to", label: place.label, to: place.to };
      if (!q || place.label.toLowerCase().includes(q)) {
        out.push(item);
        continue;
      }
      // Matched on a term, not the name: say which, so "dark" landing on
      // "Settings" is not a mystery.
      const hits = (place.terms ?? []).filter((term) => term.toLowerCase().includes(q));
      if (hits.length) out.push({ ...item, sublabel: hits.slice(0, 3).join(", ") });
    }

    for (const s of scansQuery.data ?? []) {
      const label = siteLabel(s.seed_url);
      if (!q || label.toLowerCase().includes(q) || `#${s.id}`.includes(q) || `report #${s.id}`.includes(q) || `scan ${s.id}`.includes(q) || String(s.id).includes(q)) {
        out.push({
          id: `scan-${s.id}`,
          group: "Reports",
          label,
          sublabel: `Report #${s.id} · ${SCAN_STATUS_LABEL[s.status] ?? s.status}`,
          to: `/scans/${s.id}`,
        });
      }
    }

    // A setting's choices, when the query names the setting, its section or
    // one of its choices. Only for a real query: with nothing typed the list
    // is places and reports, as before.
    if (q) {
      const matched = ALL_SETTINGS.filter((row) =>
        `${row.section} ${row.label} ${row.options.map((option) => option.label).join(" ")}`
          .toLowerCase()
          .includes(q),
      );
      for (const row of matched.slice(0, MAX_SETTINGS)) {
        for (const option of row.options) {
          const current = prefs[row.key] === option.value;
          out.push({
            id: `setting-${row.key}-${option.value}`,
            group: "Change a setting",
            label: `${row.label}: ${option.label}`,
            sublabel: current ? "Current setting" : row.section,
            setting: { key: row.key, value: option.value, current, name: row.label, option: option.label },
          });
        }
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
            sublabel: `${i.issue_key} · ${CHECK_LABEL[i.pipeline] ?? i.pipeline}`,
            to: i.detail_url,
          });
        }
      }
    }
    return out;
  }, [query, scansQuery.data, issuesQuery.data, scanId, prefs]);

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
    // By option, not by child: the options sit inside their groups.
    const el = listRef.current?.querySelectorAll<HTMLElement>('[role="option"]')[active];
    el?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  // Consecutive results of one kind, in list order; `index` is the
  // result's place in the whole list, which the arrow keys move through.
  const groups: { name: string; items: { item: Item; index: number }[] }[] = [];
  items.forEach((item, index) => {
    const last = groups[groups.length - 1];
    if (last && last.name === item.group) last.items.push({ item, index });
    else groups.push({ name: item.group, items: [{ item, index }] });
  });

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

        {/* Says what a setting result changed; Search stays open after it. */}
        <p role="status" className={cn("text-sm font-semibold text-fg", message ? "border-b border-border bg-ok-bg px-4 py-2" : "sr-only")}>
          {message}
        </p>

        {/* A listbox of groups, one per kind of result, each named by its
            heading. The options are the group's only other children, so the
            structure is the one a listbox allows (the headings used to sit
            among the options as list items of their own). */}
        {items.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-fg-muted">
            Nothing matches “{query}”. Try a site name, a report number, an issue name, or a setting.
          </p>
        ) : (
          <div ref={listRef} role="listbox" aria-label="Results" className="max-h-[50vh] overflow-y-auto py-1">
            {groups.map((group, groupIndex) => (
              <div key={group.name} role="group" aria-labelledby={`palette-group-${groupIndex}`}>
                <div id={`palette-group-${groupIndex}`} className="px-4 pb-1 pt-3 text-2xs font-semibold text-fg-subtle">
                  {group.name}
                </div>
                {group.items.map(({ item, index }) => (
                  <button
                    key={item.id}
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
                    <span className="flex items-center gap-2 text-sm font-medium text-fg">
                      {item.label}
                      {/* The current choice: a tick and the words below, not colour alone. */}
                      {item.setting?.current && <Check className="h-4 w-4 shrink-0 text-ok" strokeWidth={3} aria-hidden />}
                    </span>
                    {item.sublabel && (
                      <span className="block text-2xs text-fg-muted">{item.sublabel}</span>
                    )}
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-3 border-t border-border px-3 py-2 text-2xs text-fg-subtle">
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded-2xs border border-border bg-surface-muted px-1 py-0.5">↑↓</kbd> move
          </span>
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded-2xs border border-border bg-surface-muted px-1 py-0.5">↵</kbd> open or change
          </span>
          <span className="ml-auto inline-flex items-center gap-1">
            <CornerDownLeft className="h-3 w-3" aria-hidden /> ⌘K or Ctrl+K opens search anytime
          </span>
        </div>
      </div>
    </div>
  );
}
