import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useHref, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleAlert } from "lucide-react";
import { api } from "../api/client";
import type { SiteHistoryPoint } from "../api/types";
import { Button, Card, LinkButton, Select, type SelectOption } from "../components/ui";
import ReportHeader from "../components/ReportHeader";
import { scanQueryKey, useScanQuery } from "../hooks/useScanQuery";
import { useProtectedIdentityPartition } from "../hooks/useProtectedIdentityContext";
import { cn } from "../lib/cn";
import { FRAMED, isPaneMessage, PANE_MESSAGE_SOURCE, type PaneLocation, type PaneMessage } from "../lib/framed";
import { serverDate } from "../lib/serverTime";

/**
 * Compare reports: two reports of one site side by side, each a real page of
 * the app in its own frame, working like two browser tabs.
 *
 * The address names the pair: `/scans/:scanId/compare?compare_to=N` shows
 * report :scanId in the first panel and report N in the second. Without
 * `compare_to` the second panel shows the report before this one (the scan
 * detail's `previous_scan_id`), as the report's "Compare reports" tab does.
 *
 * Why it is built this way (keep these when you change it):
 *
 * - **Each panel is the app itself, in an `<iframe>`.** A reader can open an
 *   issue, filter, search and go back in one panel while the other stays as
 *   it is, which is what comparing two reports needs: the same issue, or the
 *   same filter, in each. The developer chose this on 2026-10-29. Rejected:
 *   two copies of the Issues page drawn inline on one page, where a panel
 *   could not navigate like a tab and the Issues page would need a risky
 *   rework to draw twice; and a split view in the desktop app only, which the
 *   browser build would not get. The diff of the two reports (new, still
 *   found, no longer found) is its own page, What changed
 *   (routes/Compare.tsx), one link away.
 * - **Inside a frame the app knows it is a panel** (lib/framed.ts): no
 *   sidebar or top bar, no Compare reports tab, its own history. If this
 *   route itself is opened inside a panel, it offers a link to open it in the
 *   whole window instead of nesting panels in panels.
 * - **Each frame has a title naming its report and page**, "Report #24,
 *   Accessibility issues", so a screen reader user knows which frame is which
 *   before entering it (WCAG technique H64, using the title attribute of the
 *   iframe element; SC 4.1.2 Name, Role, Value, Level A). It follows the
 *   panel as the reader moves through it.
 * - **No `sandbox` on these frames.** They load Axcess's own pages from its
 *   own origin, the app the reader is already running. The saved copies of
 *   scanned pages are a different case: the Page inspector sandboxes those.
 * - **Side by side from 1024 pixels wide, one above the other below.** At
 *   1280 pixels with the sidebar open each panel is about 460 pixels wide,
 *   and the page inside lays itself out for that width, as it would in a
 *   narrow window. Below 1024 pixels two panels would each be too narrow to
 *   read, so they stack, the first panel first, as in the reading order. A
 *   frame fills the window's height below the top bar when side by side, and
 *   80% of it when stacked, so both panels can be reached by scrolling the
 *   page. Nothing scrolls sideways at 320 pixels: each frame scrolls its own
 *   page up and down (SC 1.4.10 Reflow, Level AA), and keyboard focus moves
 *   into a frame with Tab, so its content is reachable without a pointer
 *   (SC 2.1.1 Keyboard, Level A).
 * - **The address holds the two reports, and only they change it.** Choosing
 *   a report with "Show this report" adds a history entry, so the browser's
 *   Back undoes it. Moving inside a panel does not: see "Go back" in
 *   ReportPane.
 */
export default function CompareReportsRoute() {
  // Fixed for the document's life, so the choice of component never changes
  // between renders.
  return FRAMED ? <OpenInWholeWindow /> : <CompareReports />;
}

/** One way to name a report everywhere on this page. */
const reportName = (id: number) => `Report #${id}`;

/** "27 October 2026": the day a report's scan started, in the reader's locale. */
function scanDay(point: SiteHistoryPoint | undefined): string | null {
  if (!point) return null;
  const at = serverDate(point.started_at);
  if (Number.isNaN(at.getTime())) return null;
  return at.toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

function positiveId(value: string | null): number | null {
  const id = Number(value);
  return value !== null && Number.isSafeInteger(id) && id > 0 ? id : null;
}

function CompareReports() {
  const { scanId } = useParams<{ scanId: string }>();
  const first = Number(scanId);
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const identityPartition = useProtectedIdentityPartition();
  const scanQuery = useScanQuery(first);
  const historyQuery = useQuery({
    queryKey: ["site-history", first],
    queryFn: () => api.getSiteHistory(first),
    enabled: Number.isSafeInteger(first) && first > 0,
  });

  // A pair of one report is no pair: the second panel then falls back to the
  // report before, as with no `compare_to`.
  const askedId = positiveId(params.get("compare_to"));
  const asked = askedId === first ? null : askedId;
  const previous = scanQuery.data?.previous_scan_id ?? null;
  // Undefined while the report is still loading and no pair was asked for.
  const second: number | null | undefined = asked ?? (scanQuery.data ? previous : undefined);
  const points = historyQuery.data?.scans;
  const history = { points, failed: Boolean(historyQuery.error) };

  // Choosing a report changes only its own panel, and records the pair in
  // the address: the first panel is the path, the second is `compare_to`.
  // A push, so the browser's Back undoes the choice.
  //
  // The first panel's report is the route's own report, behind
  // ProtectedReportGate, which draws "Loading report…" in place of the page
  // until it knows the report. That would remove both panels and reload the
  // second one too. So the new report's summary is fetched first, into the
  // cache the gate reads (the same key as useScanQuery), and the page moves
  // only then: only the first panel changes. If the fetch fails, the page
  // moves anyway and the gate shows why.
  const show = async (panel: "first" | "second", id: number) => {
    const firstId = panel === "first" ? id : first;
    const secondId = panel === "second" ? id : second;
    if (panel === "first") {
      await queryClient
        .fetchQuery({ queryKey: scanQueryKey(id, identityPartition), queryFn: () => api.getScan(id) })
        .catch(() => undefined);
    }
    navigate(`/scans/${firstId}/compare${secondId != null ? `?compare_to=${secondId}` : ""}`);
  };

  // What changed compares a later report with an earlier one of the same
  // site, both completed (src/audit/web/comparison.py). The site's history
  // lists exactly those, oldest first, in the order the server uses for
  // "earlier", so the link shows only when both reports are in it.
  const at = (id: number | null | undefined) => (id == null || !points ? -1 : points.findIndex((p) => p.id === id));
  const firstAt = at(first);
  const secondAt = at(second);
  const changes =
    firstAt >= 0 && secondAt >= 0 && firstAt !== secondAt && points
      ? firstAt > secondAt
        ? { newer: points[firstAt].id, older: points[secondAt].id }
        : { newer: points[secondAt].id, older: points[firstAt].id }
      : null;

  return (
    <>
      <ReportHeader
        tabs
        scanId={first}
        previousScanId={previous}
        title="Compare reports"
        meta="Two reports of the same site, side by side. Each panel works on its own: open an issue, filter the table or go back, and the other panel stays as it is."
        actions={
          changes && (
            <LinkButton to={`/scans/${changes.newer}/compare/changes?compare_to=${changes.older}`}>
              See what changed between these reports
            </LinkButton>
          )
        }
      />
      {/* Side by side from `lg` (1024 px), stacked below it, first panel first. */}
      <div className="grid gap-6 lg:grid-cols-2">
        <ReportPane panel="first" reportId={first} otherId={second ?? null} history={history} onShow={(id) => void show("first", id)} />
        {second === undefined ? (
          <p role="status" className="text-sm text-fg-muted">Loading report…</p>
        ) : (
          <ReportPane
            panel="second"
            reportId={second}
            otherId={first}
            history={history}
            onShow={(id) => void show("second", id)}
          />
        )}
      </div>
    </>
  );
}

type History = { points: SiteHistoryPoint[] | undefined; failed: boolean };

/**
 * One panel: its report's name, a "Go back" for the panel's own history, a
 * report picker, and the report's pages in a frame.
 *
 * Why (keep these when you change it):
 *
 * - **"Go back" belongs to this panel.** The browser's Back cannot do this
 *   job: frames share their window's history, so Back steps back in
 *   whichever frame changed last, which may be the other panel. So a panel
 *   keeps its own history (lib/framed.ts), and this button asks it to step
 *   back once, returning to where the reader was on that page. It comes
 *   first in the bar, where a browser puts Back. When the panel has nowhere
 *   to go back to, it is `aria-disabled` and looks unavailable, as the
 *   table pager's arrows do (TablePagination): a native `disabled` would
 *   drop keyboard focus to the page the moment the last step back is taken,
 *   and hiding it would move the controls after it. WAI-ARIA Authoring
 *   Practices, "Focusability of disabled controls"
 *   (https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/#focusabilityofdisabledcontrols).
 * - **Choosing a report waits for "Show this report".** The picker alone
 *   changes nothing, so moving through its options never reloads a panel.
 *   SC 3.2.2 On Input (Level A): "Changing the setting of any user interface
 *   component does not automatically cause a change of context unless the
 *   user has been advised of the behavior before using the component." The
 *   picker and the button are one form, with the button as its submit.
 * - **The report the other panel shows cannot be chosen.** It is still in
 *   the list, so the list is the same in both panels, but showing it says
 *   why not in a message under the picker, tied to it by
 *   `aria-describedby`, and puts focus back on the picker (SC 3.3.1 Error
 *   Identification, Level A; SC 3.3.3 Error Suggestion, Level AA). Showing
 *   the report already in this panel takes the panel back to its Issues
 *   page, a way to start the panel over.
 * - **Words.** Two panels have the same controls, so each control's name
 *   ends with screen-reader-only words naming its report ("Go back in the
 *   report #24 panel"), after the visible words (technique C7; SC 2.5.3
 *   Label in Name, Level A), "report" in lower case inside a sentence, as
 *   the other controls write it (docs/plain-language.md rule 11). They say "panel", never "left" or "right":
 *   below 1024 pixels the panels are one above the other (SC 1.3.3 Sensory
 *   Characteristics, Level A).
 * - **A new report is a new frame** (keyed by report): changing an
 *   existing frame's address would add an entry to the window's history,
 *   and the new report's panel would start with a step back into the old
 *   one.
 */
function ReportPane({
  panel,
  reportId,
  otherId,
  history,
  onShow,
}: {
  panel: "first" | "second";
  /** The report shown, or null when there is none to show yet. */
  reportId: number | null;
  /** The report in the other panel, which this one may not show too. */
  otherId: number | null;
  history: History;
  onShow: (id: number) => void;
}) {
  const ids = useId();
  const headingId = `${ids}-heading`;
  const selectId = `${ids}-report`;
  const errorId = `${ids}-error`;
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [generation, setGeneration] = useState(0);
  const [place, setPlace] = useState<PaneLocation | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Newest first, as Reports lists them. A report outside the site's list
  // (another site, or older than the list keeps) is still named.
  const listed = [...(history.points ?? [])].reverse();
  const options: SelectOption[] = listed.map((point) => ({
    value: String(point.id),
    label: [reportName(point.id), scanDay(point)].filter(Boolean).join(", "),
  }));
  if (reportId !== null && !listed.some((point) => point.id === reportId)) {
    options.unshift({ value: String(reportId), label: reportName(reportId) });
  }
  const fallback = options.find((option) => option.value !== String(otherId))?.value ?? "";
  const [choice, setChoice] = useState(reportId !== null ? String(reportId) : fallback);
  // A new report from the address (Back, or the other panel's choice) resets
  // the picker and what the panel last said about itself.
  useEffect(() => {
    setChoice(reportId !== null ? String(reportId) : "");
    setError(null);
    setPlace(null);
  }, [reportId]);
  useEffect(() => {
    if (choice === "" && fallback !== "") setChoice(fallback);
  }, [choice, fallback]);

  // The panel says where it is after every move (lib/framed.ts). Only this
  // panel's own frame, from this origin, is listened to.
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (!frameRef.current || event.source !== frameRef.current.contentWindow) return;
      if (!isPaneMessage(event.data) || event.data.type !== "location") return;
      const { path, title, canGoBack } = event.data;
      setPlace({ path, title, canGoBack });
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  const send = (message: PaneMessage) =>
    frameRef.current?.contentWindow?.postMessage(message, window.location.origin);

  const src = useHref(reportId !== null ? `/scans/${reportId}/issues` : "/scans");
  const name = reportId !== null ? reportName(reportId) : null;
  const point = history.points?.find((p) => p.id === reportId);
  const day = scanDay(point);
  const canGoBack = place?.canGoBack ?? false;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const id = positiveId(choice);
    if (id === null) return;
    if (id === otherId) {
      setError(`${reportName(id)} is already in the other panel. Choose a different report.`);
      document.getElementById(selectId)?.focus();
      return;
    }
    setError(null);
    if (id === reportId) {
      // The same report: start this panel over, on its Issues page.
      setPlace(null);
      setGeneration((n) => n + 1);
      return;
    }
    onShow(id);
  };

  return (
    <section aria-labelledby={headingId} className="min-w-0">
      <Card className="flex min-w-0 flex-col">
        <div className="border-b border-border p-3">
          <h2 id={headingId} className="text-base font-semibold text-fg">
            {name ?? "Nothing earlier to compare with"}
            {day && (
              <>
                <span className="sr-only">,</span>{" "}
                <span className="text-sm font-normal text-fg-muted">scanned {day}</span>
              </>
            )}
          </h2>
          {/* One row when it fits, Go back first; the picker's label sits
              above it (`stacked`), so at 320 px the box keeps the whole
              width for the report's name instead of sharing it with the
              label. */}
          <div className="mt-2 flex flex-wrap items-end gap-2">
            {name && (
              <Button
                type="button"
                aria-disabled={!canGoBack || undefined}
                onClick={() => canGoBack && send({ source: PANE_MESSAGE_SOURCE, type: "back" })}
                className="aria-disabled:cursor-not-allowed aria-disabled:border-border aria-disabled:bg-surface-muted aria-disabled:text-fg-subtle aria-disabled:opacity-60 aria-disabled:shadow-none aria-disabled:hover:border-border aria-disabled:hover:bg-surface-muted aria-disabled:active:translate-y-0"
              >
                <ArrowLeft className="h-4 w-4" aria-hidden />
                <span>
                  Go back<span className="sr-only"> in the {name.toLowerCase()} panel</span>
                </span>
              </Button>
            )}
            {history.failed ? (
              <p className="text-sm text-fg-muted">The list of reports could not load. Try again later.</p>
            ) : !history.points ? (
              <p role="status" className="text-sm text-fg-muted">Loading the list of reports…</p>
            ) : options.length > (name ? 1 : 0) ? (
              <form onSubmit={submit} className="flex min-w-0 flex-wrap items-end gap-2">
                <Select
                  id={selectId}
                  stacked
                  label="Report"
                  value={choice}
                  onChange={(value) => {
                    setChoice(value);
                    setError(null);
                  }}
                  options={options}
                  aria-describedby={error ? errorId : undefined}
                />
                <Button type="submit">
                  <span>
                    Show this report<span className="sr-only">{name ? ` in place of ${name.toLowerCase()}` : ` in the ${panel} panel`}</span>
                  </span>
                </Button>
              </form>
            ) : null}
          </div>
          {error && (
            <p id={errorId} className="mt-2 flex items-start gap-2 text-sm font-semibold text-sev-critical">
              <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{error}</span>
            </p>
          )}
        </div>
        {name ? (
          // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- the frame's load event, not a reader's action
          <iframe
            key={`${reportId}-${generation}`}
            ref={frameRef}
            src={src}
            title={`${name}, ${place?.title || "Accessibility issues"}`}
            loading="eager"
            // Ask the panel where it is once it has loaded, in case its first
            // word came before this page was listening.
            onLoad={() => send({ source: PANE_MESSAGE_SOURCE, type: "report" })}
            className={cn(
              "block w-full rounded-b-xs border-0 bg-surface-subtle",
              "h-[80vh] min-h-[28rem] lg:h-[calc(100vh-7rem)] lg:min-h-[32rem]",
            )}
          />
        ) : (
          <p className="p-4 text-sm leading-relaxed text-fg-muted">
            {otherId !== null && listed.length > 1
              ? `${reportName(otherId)} is the first completed report of this site. Choose a later report to show here.`
              : "This site has one completed report so far. Scan the site again after you fix issues, then compare the two reports here."}
          </p>
        )}
      </Card>
    </section>
  );
}

/**
 * This route inside one of its own panels: a link to open it in the whole
 * window, never panels inside a panel (see lib/framed.ts). The link targets
 * the top window (`target="_top"`), a plain link to the same address.
 */
function OpenInWholeWindow() {
  const { pathname, search } = useLocation();
  const href = useHref(pathname + search);
  return (
    <>
      <h1 className="text-2xl font-semibold leading-tight tracking-[-0.025em] text-fg">Compare reports</h1>
      <Card className="mt-4 p-4 text-sm leading-relaxed">
        <p>Compare reports shows two reports side by side, so it cannot open inside one of its own panels.</p>
        <a href={href} target="_top" className="report-link mt-1 inline-flex min-h-target items-center font-semibold">
          Open Compare reports in the whole window
        </a>
      </Card>
    </>
  );
}
