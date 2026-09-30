import {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Check, ChevronDown, Download, Loader2 } from "lucide-react";
import { ApiError, api, exportUrl } from "../api/client";
import type { ExportFormat } from "../api/types";
import { cn } from "../lib/cn";
import { Button } from "./ui";

/**
 * The report's downloads, behind one control.
 *
 * The header used to carry two side-by-side download buttons ("Download
 * workbook", "Download report") competing with the page's own actions, while
 * the CSV and JSON renderers the server already exposes had no UI at all.
 * They are all the same job, take this report elsewhere, so they share one
 * button.
 *
 * This is the APG *disclosure* pattern, deliberately not the menu pattern:
 * the contents are ordinary links, so Tab, Enter, and a screen reader's link
 * list all behave the way users already expect. A `role="menu"` here would
 * take the links out of the tab order and buy nothing. The arrow keys, Home
 * and End also move between the links, because the panel looks like the
 * app's dropdowns and people will reach for them.
 *
 * The panel says what it is about to hand over before anyone chooses: which
 * report, how large each file is, that the files cover the whole report
 * rather than the table's filters, and whether they will be marked DRAFT.
 * Each download then says what happened. A plain `<a download>` could not:
 * a refused or failed export saved the error as the file, or nothing, with
 * no word on the page. The link's `href` stays the real export URL, so a
 * modified click (a new tab, copying the link) still does what it asks.
 */
const FORMATS: {
  format: ExportFormat;
  badge: string;
  /** The badge's tint. The badge is decorative (the label names the format),
   *  but its text still clears 7:1 on its tint in every theme. */
  tone: string;
  label: string;
  hint: string;
}[] = [
  {
    format: "xlsx",
    badge: "XLSX",
    tone: "bg-umich-blue/10 text-umich-blue",
    label: "Issue list with fixes (Excel)",
    hint: "One row per issue, with how to fix it",
  },
  {
    format: "audit",
    badge: "MD",
    tone: "bg-sev-info-bg text-sev-info",
    label: "Written report (Markdown)",
    hint: "The whole report as readable text",
  },
  {
    format: "csv",
    badge: "CSV",
    tone: "bg-sev-minor-bg text-sev-minor",
    label: "Occurrence list (CSV)",
    hint: "One row for each place an issue appears",
  },
  {
    format: "json",
    badge: "JSON",
    tone: "bg-sev-major-bg text-sev-major",
    label: "All report data (JSON)",
    hint: "Every detail the scan saved, for developers",
  },
];

type DownloadState =
  | { kind: "preparing" }
  | { kind: "done"; filename: string }
  | { kind: "failed"; message: string };

/** Decimal units, as the Finder reports a file's size. */
function formatFileSize(bytes: number): string {
  if (bytes < 1000) return `${bytes} B`;
  if (bytes < 999_500) return `${Math.round(bytes / 1000)} KB`;
  const megabytes = bytes / 1_000_000;
  return `${megabytes < 99.95 ? megabytes.toFixed(1) : Math.round(megabytes)} MB`;
}

const plural = (count: number, one: string, many: string) =>
  `${count.toLocaleString()} ${count === 1 ? one : many}`;

export default function ExportMenu({
  scanId,
  site,
  pageCount,
  issueGroups,
  shownIssueGroups,
}: {
  scanId: number;
  /** The report's site, pages and issues, under the panel's heading,
   *  so the reader can see which report they are taking away. */
  site?: string;
  pageCount?: number;
  issueGroups?: number;
  /** Issues the table shows now; pass it only while a filter or a
   *  search narrows the table. */
  shownIssueGroups?: number;
}) {
  const [open, setOpen] = useState(false);
  const [downloads, setDownloads] = useState<Partial<Record<ExportFormat, DownloadState>>>({});
  const [announcement, setAnnouncement] = useState("");
  const idBase = useId();
  const panelId = `${idBase}-panel`;
  const headingId = `${idBase}-heading`;
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const focusFirstOnOpen = useRef(false);
  // Which edge of the button the panel hangs from. It hangs from the right
  // edge, as the header's last action; but when the header wraps, the button
  // starts a line of its own at the left, and a right-hung panel reached
  // back under the sidebar, where half of it could not be seen or clicked.
  const [hangLeft, setHangLeft] = useState(false);

  // Rendering every format to measure it takes a second or two on a large
  // scan, so it waits until someone opens the panel. The downloads never
  // wait for it: a link works before, and without, its size.
  const options = useQuery({
    queryKey: ["export-options", scanId],
    queryFn: () => api.getExportOptions(scanId),
    enabled: open,
    staleTime: 60_000,
    // One retry, not the default three: a server that lacks the endpoint
    // (one started before it existed) answers 404 every time, and three
    // backed-off retries kept a loading bar up for seconds before the size
    // column went quietly blank.
    retry: 1,
  });
  const optionFor = (format: ExportFormat) =>
    options.data?.formats.find((option) => option.format === format);

  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const button = buttonRef.current?.getBoundingClientRect();
      const panelWidth = panelRef.current?.offsetWidth ?? 0;
      const leftBound = containerRef.current?.closest("main")?.getBoundingClientRect().left ?? 0;
      if (button) setHangLeft(button.right - panelWidth < leftBound);
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (focusFirstOnOpen.current) {
      focusFirstOnOpen.current = false;
      panelRef.current?.querySelector("a")?.focus();
    }
    const closeOnOutsidePointer = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnOutsideFocus = (event: FocusEvent) => {
      // Re-entering the window refocuses <body> without the user having moved
      // anywhere; treating that as "focus left the menu" would snap the panel
      // shut whenever they alt-tabbed back to it.
      if (event.target === document.body) return;
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      // Escape returns focus to the trigger; closing a disclosure must never
      // drop the user at the top of the document.
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener("mousedown", closeOnOutsidePointer);
    // `focusin` is the keyboard half of the same rule: tabbing past the last
    // link dismisses the panel, so focus never lands behind something that is
    // still covering the page.
    document.addEventListener("focusin", closeOnOutsideFocus);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsidePointer);
      document.removeEventListener("focusin", closeOnOutsideFocus);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function panelLinks(): HTMLAnchorElement[] {
    return Array.from(panelRef.current?.querySelectorAll("a") ?? []);
  }

  function onTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    if (open) {
      panelLinks()[0]?.focus();
    } else {
      focusFirstOnOpen.current = true;
      setOpen(true);
    }
  }

  function onLinkKeyDown(event: ReactKeyboardEvent<HTMLAnchorElement>) {
    const links = panelLinks();
    const current = links.indexOf(event.currentTarget);
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

  async function download(entry: (typeof FORMATS)[number]) {
    setDownloads((previous) => ({ ...previous, [entry.format]: { kind: "preparing" } }));
    setAnnouncement(`Preparing “${entry.label}”…`);
    try {
      const result = await api.downloadExport(scanId, entry.format);
      setDownloads((previous) => ({
        ...previous,
        [entry.format]: { kind: "done", filename: result.filename },
      }));
      setAnnouncement(`Downloading ${result.filename}, ${formatFileSize(result.sizeBytes)}.`);
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "The Axcess server did not respond. Check that it is still running.";
      setDownloads((previous) => ({ ...previous, [entry.format]: { kind: "failed", message } }));
      setAnnouncement(`Axcess could not download “${entry.label}”. ${message}`);
    }
  }

  function onChoose(event: ReactMouseEvent<HTMLAnchorElement>, entry: (typeof FORMATS)[number]) {
    // A modified click asks the browser for something else (a new tab, a
    // saved link); the href is the real export URL, so let it do that.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    if (downloads[entry.format]?.kind === "preparing") return;
    void download(entry);
  }

  const preparing = Object.values(downloads).some((state) => state?.kind === "preparing");
  const facts = [
    site,
    pageCount === undefined ? "" : plural(pageCount, "page", "pages"),
    issueGroups === undefined ? "" : plural(issueGroups, "issue", "issues"),
  ]
    .filter(Boolean)
    .join(" · ");
  const scopeNote =
    shownIssueGroups !== undefined && issueGroups !== undefined && shownIssueGroups < issueGroups
    ? `Includes all ${plural(issueGroups, "issue", "issues")} and their statuses, ` +
      `not only the ${shownIssueGroups.toLocaleString()} your filters show.`
    : "Includes every issue and status in this report, even if the table has filters on.";

  return (
    <div ref={containerRef} className="relative">
      <Button
        ref={buttonRef}
        type="button"
        variant="secondary"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
        onKeyDown={onTriggerKeyDown}
      >
        {preparing ? (
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden />
        ) : (
          <Download className="h-4 w-4" aria-hidden />
        )}
        Export report
        <ChevronDown
          className={cn("h-3.5 w-3.5 motion-safe:transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </Button>

      {/* Outside the panel, so a download that finishes after the panel is
          closed is still announced; a live region inside a hidden element
          says nothing. */}
      <p role="status" className="sr-only">
        {announcement}
      </p>

      <div
        ref={panelRef}
        id={panelId}
        role="group"
        aria-labelledby={headingId}
        hidden={!open}
        className={cn(
          "absolute z-30 mt-1.5 w-[23rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-xs border border-border bg-surface shadow-raised",
          hangLeft ? "left-0" : "right-0",
        )}
      >
        <div className="border-b border-border px-4 pb-3 pt-3.5">
          <h2 id={headingId} className="text-base font-semibold leading-6 text-fg">
            Export Report #{scanId}
          </h2>
          {facts && (
            <p className="mt-0.5 text-xs text-fg-muted [overflow-wrap:anywhere]">{facts}</p>
          )}
        </div>

        <ul className="p-1.5">
          {FORMATS.map((entry) => {
            const option = optionFor(entry.format);
            const state = downloads[entry.format];
            const ids = {
              label: `${idBase}-${entry.format}-label`,
              hint: `${idBase}-${entry.format}-hint`,
              size: `${idBase}-${entry.format}-size`,
              state: `${idBase}-${entry.format}-state`,
            };
            const describedBy = [ids.hint, option && ids.size, state && ids.state]
              .filter(Boolean)
              .join(" ");
            return (
              <li key={entry.format}>
                {/* A plain <a>, not a Router <Link>: the SPA is mounted under
                    basename="/app" and a Link would rewrite the /api path.
                    `draft=acknowledged` keeps an incomplete report
                    downloadable as a visibly labeled draft, which is the
                    server's contract; the footer says when that applies. */}
                <a
                  href={exportUrl(scanId, entry.format, true)}
                  download={option?.filename ?? ""}
                  aria-labelledby={ids.label}
                  aria-describedby={describedBy}
                  aria-disabled={state?.kind === "preparing" || undefined}
                  onClick={(event) => onChoose(event, entry)}
                  onKeyDown={onLinkKeyDown}
                  // Drawn as a row, not a run of text: the global link hover
                  // underline (and the "always underline links" setting)
                  // would otherwise strike through every line inside it.
                  data-button
                  className={cn(
                    "flex min-h-target items-center gap-3 rounded-2xs px-2.5 py-2 no-underline hover:bg-surface-muted hover:no-underline",
                    state?.kind === "preparing" && "cursor-progress",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "grid h-9 w-11 shrink-0 place-items-center rounded-2xs font-mono text-2xs font-bold tracking-wide",
                      entry.tone,
                    )}
                  >
                    {entry.badge}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span id={ids.label} className="block text-sm font-semibold text-fg">
                      {entry.label}
                    </span>
                    <span id={ids.hint} className="block text-xs text-fg-muted">
                      {entry.hint}
                    </span>
                    {state && <DownloadLine id={ids.state} state={state} />}
                  </span>
                  <span className="shrink-0 self-start whitespace-nowrap pt-0.5 text-xs tabular-nums text-fg-muted">
                    {option ? (
                      <span id={ids.size}>
                        <span aria-hidden>≈ </span>
                        <span className="sr-only">about </span>
                        {formatFileSize(option.size_bytes)}
                      </span>
                    ) : options.isFetching ? (
                      <span
                        aria-hidden
                        className="inline-block h-3 w-12 rounded-2xs bg-surface-muted motion-safe:animate-pulse"
                      />
                    ) : null}
                  </span>
                </a>
              </li>
            );
          })}
        </ul>

        <div className="space-y-1.5 border-t border-border bg-surface-subtle px-4 py-3 text-xs leading-5 text-fg-muted">
          {/* An empty size column said nothing about why; this says what is
              missing and that nothing else is. */}
          {options.isError && (
            <p className="flex items-start gap-1 text-fg">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <span>
                Axcess could not check the file sizes, or whether the files are drafts. The
                downloads still work.
              </span>
            </p>
          )}
          {options.data?.draft && (
            <p className="font-semibold text-fg">
              An expert has not finished reviewing this report, so each file is marked DRAFT.
            </p>
          )}
          <p>
            {scopeNote} Automated results are for an expert to review. They never prove that a
            site meets accessibility rules.
          </p>
        </div>
      </div>
    </div>
  );
}

/** One download's progress, in words and an icon: never color alone. */
function DownloadLine({ id, state }: { id: string; state: DownloadState }) {
  if (state.kind === "preparing") {
    return (
      <span id={id} className="mt-0.5 flex items-center gap-1 text-xs text-fg-muted">
        <Loader2 className="h-3.5 w-3.5 shrink-0 motion-safe:animate-spin" aria-hidden />
        Preparing…
      </span>
    );
  }
  if (state.kind === "done") {
    return (
      <span id={id} className="mt-0.5 flex items-start gap-1 text-xs text-fg-muted">
        <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        <span className="[overflow-wrap:anywhere]">Downloaded {state.filename}</span>
      </span>
    );
  }
  return (
    <span id={id} className="mt-0.5 flex items-start gap-1 text-xs text-sev-critical">
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>
        Axcess could not download this file. {state.message} To try again, choose the file again.
      </span>
    </span>
  );
}
