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
import { AlertCircle, Check, ChevronDown, Copy, Download, Loader2 } from "lucide-react";
import { ApiError, api, exportUrl } from "../api/client";
import type { ExportFormat } from "../api/types";
import { cn } from "../lib/cn";
import {
  COPY_FIX_BRIEF_DONE,
  COPY_FIX_BRIEF_HINT,
  COPY_FIX_BRIEF_LABEL,
  EXPORT_FORMAT_HINT,
  EXPORT_FORMAT_LABEL,
  FIX_BRIEF_REDACTION_LIMITS,
  FIX_BRIEF_SCOPE_NOTE,
  REDACTION_LIMITS,
} from "../lib/terms";
import { Button, Checkbox } from "./ui";

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
 * The fix brief is the one file that does not cover the whole report: it
 * lists open issue types only, up to a limit, with a few places for each.
 * So the footer's note says "every file except the fix brief", and a second
 * sentence says what the brief is. Before, "includes every issue type and
 * every status" read as true of all five files, and someone could take the
 * brief for the complete report (PR #58 review; AGENTS.md, Interface
 * language rule 5: text accurate to the code). Rejected: a separate note
 * under the brief's own row, which would put two scope notes in one panel
 * for people to reconcile (W3C COGA "Making Content Usable",
 * https://www.w3.org/TR/coga-usable/, paraphrased: keep related information
 * together). The footer's three facts (what the files cover, what the brief
 * covers, what automated results cannot prove) are three short paragraphs,
 * one idea each, rather than one block (same COGA document, paraphrased: use
 * short blocks of text, one topic each).
 * Each download then says what happened. A plain `<a download>` could not:
 * a refused or failed export saved the error as the file, or nothing, with
 * no word on the page. The link's `href` stays the real export URL, so a
 * modified click (a new tab, copying the link) still does what it asks.
 *
 * **Remove private details (redact).** A report of a site behind a sign-in
 * can hold a person's own data (a filled-in field, an email address in a
 * greeting). One checkbox, above the files, asks for redacted copies:
 * the server replaces likely private details with "[redacted]" in the file
 * and names it `_REDACTED`. The fix brief for a coding agent is redacted
 * either way, because it is made to be handed over. It changes the
 * downloads only; the report in Axcess keeps everything, as decided for
 * this feature (export only).
 * - A checkbox, the native `<input type="checkbox">` in the shared
 *   `Checkbox`, because this is an on/off setting for the files below it
 *   (W3C "Using ARIA" rule 1, https://www.w3.org/TR/using-aria/#rule1).
 *   Rejected: a second "redacted" link for each file. Ten links for five
 *   files is two ways to do one thing (W3C COGA "Making Content Usable",
 *   https://www.w3.org/TR/coga-usable/, paraphrased: keep one way to do a
 *   task), and the list would no longer fit at 320 px.
 * - Above the files, not below: the choice comes before the action, in
 *   reading and focus order (SC 2.4.3 Focus Order, Level A). It is also the
 *   first stop for the arrow keys, so opening the panel with Down arrow
 *   lands on it rather than skipping past it to the first file.
 * - Off by default. Turning it on by default would change what every
 *   existing download contains (AGENTS.md, Implementation rule 5), and the
 *   reviewer's own copy should keep the full evidence. The label says what
 *   it does in plain words first, with "redact" in parentheses for people
 *   who know the term (docs/plain-language.md).
 * - Its limits are never shortened away: when it is on, the footer says it
 *   is best effort, what it can miss, and to check the file before sharing
 *   (AGENTS.md, Interface language rule 4). Each file carries the same
 *   notice inside it. One limit is a choice, not a miss: the files keep
 *   element locators (CSS selectors) whole, because a changed locator no
 *   longer finds its element, so a locator that quotes a value from the
 *   page still shows it. The footer says that too (PR #58 review).
 * - The fix brief is redacted whether or not the box is ticked, so its
 *   limits are shown whether or not it is ticked too: with the box off, the
 *   footer says the brief is a redacted copy, that this is best effort, what
 *   it can miss, and to check the brief before sharing or pasting it. The
 *   brief's download link and "Copy fix brief" both point to that text with
 *   `aria-describedby`, so a screen reader user hears the limits before
 *   acting, as a sighted user sees them in the open panel. The brief's own
 *   hint says "best effort" too. Rejected: the earlier "Private details are
 *   always removed", which promised more than a pattern-matching redactor
 *   can do (it cannot recognize a name), and hiding the limits until the box
 *   was ticked, when the brief is redacted either way (PR #60 review).
 *
 * **Copy fix brief.** The fix brief is made to be pasted into Claude Code or
 * another coding agent, so it has a one-click copy beside its download
 * (asked for on Asana 1220313732698508): a native `<button>` under the
 * brief's row, because it acts rather than goes somewhere, with a verb and
 * an object as its words ("Copy fix brief"). It fetches the same URL as the
 * download, so a refused or failed export says why in words, and its result
 * ("Copied", or why not) is said in the row and in the live region. The
 * button's words never change to "Copied": a voice-control user says the
 * words they see, and they must still work a second time.
 * - It writes a `ClipboardItem` whose text is still being fetched, so the
 *   copy counts as part of the click; Safari refuses a clipboard write that
 *   starts after a network wait. Browsers without `ClipboardItem` fall back
 *   to `writeText` once the text has arrived.
 * - The download stays: the button is a second way to the same file for
 *   people who paste rather than attach.
 */
const FORMAT_BADGES: {
  format: ExportFormat;
  badge: string;
  /** The badge's tint. The badge is decorative (the label names the format),
   *  but its text still clears 7:1 on its tint in every theme. */
  tone: string;
}[] = [
  { format: "xlsx", badge: "XLSX", tone: "bg-umich-blue/10 text-umich-blue" },
  { format: "audit", badge: "MD", tone: "bg-sev-info-bg text-sev-info" },
  // The fix brief sits beside the written report, the other Markdown file,
  // so the two are compared where they are chosen. Its badge says what it is
  // for ("FIX"), not "MD" again, so the two rows do not look alike. It is
  // always redacted, whatever the checkbox says: the server builds it for
  // hand-off to a coding agent, and its hint says so in words.
  { format: "brief", badge: "FIX", tone: "bg-sev-critical-bg text-sev-critical" },
  { format: "csv", badge: "CSV", tone: "bg-sev-minor-bg text-sev-minor" },
  { format: "json", badge: "JSON", tone: "bg-sev-major-bg text-sev-major" },
];
// Names and hints live in lib/terms.ts, so every surface that names an
// export uses the same words (AGENTS.md, Interface language rule 2).
const FORMATS = FORMAT_BADGES.map((entry) => ({
  ...entry,
  label: EXPORT_FORMAT_LABEL[entry.format],
  hint: EXPORT_FORMAT_HINT[entry.format],
}));

type CopyState =
  | { kind: "copying" }
  | { kind: "done" }
  | { kind: "failed"; message: string };

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
  /** The report's site, pages and issue types, under the panel's heading,
   *  so the reader can see which report they are taking away. */
  site?: string;
  pageCount?: number;
  issueGroups?: number;
  /** Issue types (rows) the table shows now; pass it only while a filter or a
   *  search narrows the table. */
  shownIssueGroups?: number;
}) {
  const [open, setOpen] = useState(false);
  const [downloads, setDownloads] = useState<Partial<Record<ExportFormat, DownloadState>>>({});
  const [announcement, setAnnouncement] = useState("");
  const [redact, setRedact] = useState(false);
  const [copyState, setCopyState] = useState<CopyState | null>(null);
  const idBase = useId();
  const panelId = `${idBase}-panel`;
  const limitsId = `${idBase}-redaction-limits`;
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
    queryKey: ["export-options", scanId, redact],
    queryFn: () => api.getExportOptions(scanId, redact),
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
      panelStops()[0]?.focus();
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

  /** The panel's arrow-key stops, in order: the redaction choice, then the
   *  five downloads, with "Copy fix brief" right after the fix brief. */
  function panelStops(): HTMLElement[] {
    return Array.from(
      panelRef.current?.querySelectorAll<HTMLElement>("input, a, button") ?? [],
    );
  }

  function onTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    if (open) {
      panelStops()[0]?.focus();
    } else {
      focusFirstOnOpen.current = true;
      setOpen(true);
    }
  }

  function onStopKeyDown(event: ReactKeyboardEvent<HTMLElement>) {
    const links = panelStops();
    const current = links.indexOf(event.target as HTMLElement);
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
      const result = await api.downloadExport(scanId, entry.format, redact);
      setDownloads((previous) => ({
        ...previous,
        [entry.format]: { kind: "done", filename: result.filename },
      }));
      setAnnouncement(
        `Downloading ${result.filename}${result.redacted ? ", a redacted copy" : ""}, ` +
          `${formatFileSize(result.sizeBytes)}.`,
      );
    } catch (error) {
      const message =
        error instanceof ApiError
          ? error.message
          : "The Axcess server did not respond. Check that it is still running.";
      setDownloads((previous) => ({ ...previous, [entry.format]: { kind: "failed", message } }));
      setAnnouncement(`Axcess could not download “${entry.label}”. ${message}`);
    }
  }

  async function copyBrief() {
    if (copyState?.kind === "copying") return;
    setCopyState({ kind: "copying" });
    setAnnouncement("Copying the fix brief…");
    // Started at once, inside the click, so the clipboard write below still
    // counts as the click's own action (see the component's comment).
    const text = api.fetchExportText(scanId, "brief", redact);
    const fetchFailure = text.then(
      () => null,
      (error: unknown) => error,
    );
    try {
      if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
        const blob = text.then((markdown) => new Blob([markdown], { type: "text/plain" }));
        await navigator.clipboard.write([new ClipboardItem({ "text/plain": blob })]);
      } else {
        await navigator.clipboard.writeText(await text);
      }
      setCopyState({ kind: "done" });
      setAnnouncement(COPY_FIX_BRIEF_DONE);
    } catch {
      const failure = await fetchFailure;
      const message =
        failure instanceof ApiError
          ? failure.message
          : failure
            ? "The Axcess server did not respond. Check that it is still running."
            : "Your browser did not let Axcess use the clipboard. Download the file instead.";
      setCopyState({ kind: "failed", message });
      setAnnouncement(`Axcess could not copy the fix brief. ${message}`);
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

  const preparing =
    Object.values(downloads).some((state) => state?.kind === "preparing") ||
    copyState?.kind === "copying";
  const facts = [
    site,
    pageCount === undefined ? "" : plural(pageCount, "page", "pages"),
    issueGroups === undefined ? "" : plural(issueGroups, "issue type", "issue types"),
  ]
    .filter(Boolean)
    .join(" · ");
  const scopeNote =
    shownIssueGroups !== undefined && issueGroups !== undefined && shownIssueGroups < issueGroups
    ? `Every file except the fix brief includes all ${plural(issueGroups, "issue type", "issue types")} ` +
      `and every status, not only the ${shownIssueGroups.toLocaleString()} your filters show.`
    : "Every file except the fix brief includes every issue type and every status in this report, even if the table has filters on.";

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
          "absolute z-30 mt-1.5 w-[23rem] max-w-[calc(100vw-2rem)] overflow-hidden rounded-xs border border-border bg-surface-raised shadow-raised",
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

        {/* The wrapper takes the arrow keys for the checkbox inside it; the
            shared Checkbox has no key handler of its own to pass one to. */}
        {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions -- Keep: forwards the panel's arrow keys from the native checkbox inside; it is not itself a control. */}
        <div className="border-b border-border px-2 py-1.5" onKeyDown={onStopKeyDown}>
          <Checkbox
            checked={redact}
            onChange={setRedact}
            label="Remove private details (redact)"
            hint="Replaces form field values, email addresses, phone numbers, card and ID numbers, and secret codes with [redacted] in the files. The report in Axcess keeps everything."
          />
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
            const describedBy = [
              ids.hint,
              entry.format === "brief" && limitsId,
              option && ids.size,
              state && ids.state,
            ]
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
                  href={exportUrl(scanId, entry.format, true, redact)}
                  download={option?.filename ?? ""}
                  aria-labelledby={ids.label}
                  aria-describedby={describedBy}
                  aria-disabled={state?.kind === "preparing" || undefined}
                  onClick={(event) => onChoose(event, entry)}
                  onKeyDown={onStopKeyDown}
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
                {entry.format === "brief" && (
                  <CopyBriefRow
                    idBase={idBase}
                    limitsId={limitsId}
                    state={copyState}
                    onCopy={() => void copyBrief()}
                    onKeyDown={onStopKeyDown}
                  />
                )}
              </li>
            );
          })}
        </ul>

        <div className="space-y-1.5 border-t border-border bg-surface-subtle px-4 py-3 text-xs text-fg-muted">
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
          {/* One limits note, always shown: for every file when the box is
              ticked, for the always-redacted fix brief when it is not. */}
          <p id={limitsId} className="font-semibold text-fg">
            {redact ? REDACTION_LIMITS : FIX_BRIEF_REDACTION_LIMITS}
          </p>
          {options.data?.draft && (
            <p className="font-semibold text-fg">
              An expert has not finished reviewing this report, so each file is marked DRAFT.
            </p>
          )}
          <p>{scopeNote}</p>
          <p>{FIX_BRIEF_SCOPE_NOTE}</p>
          <p>
            Automated results are for an expert to review. They never prove that a site meets
            accessibility rules.
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * "Copy fix brief", under the fix brief's row and lined up with its words,
 * so it reads as part of that file and not as a sixth one.
 */
function CopyBriefRow({
  idBase,
  limitsId,
  state,
  onCopy,
  onKeyDown,
}: {
  idBase: string;
  /** The panel's redaction limits note, which also covers this copy. */
  limitsId: string;
  state: CopyState | null;
  onCopy: () => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => void;
}) {
  const hintId = `${idBase}-copy-brief-hint`;
  const stateId = `${idBase}-copy-brief-state`;
  return (
    <div className="pb-2 pl-[4.125rem] pr-2.5">
      <Button
        type="button"
        size="sm"
        className="min-h-target"
        aria-describedby={[hintId, limitsId, state && stateId].filter(Boolean).join(" ")}
        aria-disabled={state?.kind === "copying" || undefined}
        onClick={onCopy}
        onKeyDown={onKeyDown}
      >
        {state?.kind === "copying" ? (
          <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden />
        ) : (
          <Copy className="h-3.5 w-3.5" aria-hidden />
        )}
        {COPY_FIX_BRIEF_LABEL}
      </Button>
      <span id={hintId} className="mt-1 block text-xs text-fg-muted">
        {COPY_FIX_BRIEF_HINT}
      </span>
      {state?.kind === "copying" && (
        <span id={stateId} className="mt-0.5 flex items-center gap-1 text-xs text-fg-muted">
          <Loader2 className="h-3.5 w-3.5 shrink-0 motion-safe:animate-spin" aria-hidden />
          Copying…
        </span>
      )}
      {state?.kind === "done" && (
        <span id={stateId} className="mt-0.5 flex items-start gap-1 text-xs text-fg-muted">
          <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>{COPY_FIX_BRIEF_DONE}</span>
        </span>
      )}
      {state?.kind === "failed" && (
        <span id={stateId} className="mt-0.5 flex items-start gap-1 text-xs text-sev-critical">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>Axcess could not copy the fix brief. {state.message}</span>
        </span>
      )}
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
