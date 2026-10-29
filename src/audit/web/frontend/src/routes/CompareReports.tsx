import { useEffect, useId, useRef, useState, type FormEvent, type MutableRefObject } from "react";
import { Link, useHref, useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleAlert, X } from "lucide-react";
import { api } from "../api/client";
import type { SiteHistoryPoint } from "../api/types";
import { Button, Card, LinkButton, Select, type SelectOption } from "../components/ui";
import ReportHeader from "../components/ReportHeader";
import { count, countKinds } from "../components/compare/format";
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
 * `compare_to` the second panel is empty and lists the site's other reports
 * to choose from (EmptyPane): that is where the report's "Compare reports"
 * tab opens. "Compare with" on Reports opens a pair.
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
 * - **Opened from a report, the second panel starts empty.** The developer
 *   asked for this (2026-10-29): coming from one report, the reader has not
 *   said which report to compare it with yet, so the page asks rather than
 *   guess. Until then the second panel showed the report before this one,
 *   which loaded a whole second report the reader may not have wanted and
 *   made the choice look already made. The empty panel is a dashed box that
 *   lists the site's other reports; see EmptyPane.
 * - **The second panel can be closed** ("Close report #20", ReportPane),
 *   which empties it again, as closing a browser tab leaves a new-tab page.
 *   The first panel has no Close: it is the report the page belongs to.
 * - **Focus follows the panel that changed.** Choosing a report in the empty
 *   panel, or closing the second panel, removes the control that was
 *   pressed. Focus then moves to the heading of what replaced it, so it is
 *   not dropped to the top of the page (SC 2.4.3 Focus Order, Level A).
 * - **The address holds the two reports, and only they change it.** Choosing
 *   a report with "Show this report", choosing one in the empty panel, and
 *   closing the second panel each add a history entry, so the browser's Back
 *   undoes them. Moving inside a panel does not: see "Go back" in
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

  // A pair of one report is no pair: the second panel is then empty, as with
  // no `compare_to`.
  const askedId = positiveId(params.get("compare_to"));
  const second = askedId === first ? null : askedId;
  const previous = scanQuery.data?.previous_scan_id ?? null;
  const points = historyQuery.data?.scans;
  const history = { points, failed: Boolean(historyQuery.error) };
  // Which heading takes focus once the address has changed: see "Focus
  // follows the panel that changed" above. Read once, by the panel it names.
  const focusNext = useRef<"second" | "empty" | null>(null);

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
    navigate(pairPath(firstId, secondId));
  };
  const close = () => {
    focusNext.current = "empty";
    navigate(pairPath(first, null));
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
        <ReportPane reportId={first} otherId={second} history={history} onShow={(id) => void show("first", id)} />
        {second === null ? (
          <EmptyPane reportId={first} history={history} focusNext={focusNext} />
        ) : (
          <ReportPane
            reportId={second}
            otherId={first}
            history={history}
            onShow={(id) => void show("second", id)}
            onClose={close}
            focusNext={focusNext}
          />
        )}
      </div>
    </>
  );
}

type History = { points: SiteHistoryPoint[] | undefined; failed: boolean };
type FocusNext = MutableRefObject<"second" | "empty" | null>;

/** The page's address for a pair, or for one report and an empty panel. */
const pairPath = (first: number, second: number | null) =>
  `/scans/${first}/compare${second != null ? `?compare_to=${second}` : ""}`;

/** Moves focus to `heading` once, when `focusNext` names `which`. */
function useTakeFocus(focusNext: FocusNext | undefined, which: "second" | "empty") {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focusNext?.current !== which) return;
    focusNext.current = null;
    heading.current?.focus();
  }, [focusNext, which]);
  return heading;
}

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
 * - **"Close" empties the second panel** (CompareReports, "The second panel
 *   can be closed"). It sits at the panel's top edge, after the heading,
 *   where a browser tab has its close button, and is the X icon with the
 *   word "Close" beside it: an icon alone asks the reader to know what an X
 *   means (W3C COGA, "Making Content Usable", objective 3, use clear and
 *   understandable content; paraphrased). Screen-reader-only words name the
 *   report, "Close report #20" (technique C7). A quiet (`ghost`) button, so
 *   it does not compete with "Go back" and the picker, the panel's main
 *   controls; still 44 pixels (SC 2.5.5 Target Size (Enhanced), Level AAA).
 * - **A new report is a new frame** (keyed by report): changing an
 *   existing frame's address would add an entry to the window's history,
 *   and the new report's panel would start with a step back into the old
 *   one.
 */
function ReportPane({
  reportId,
  otherId,
  history,
  onShow,
  onClose,
  focusNext,
}: {
  reportId: number;
  /** The report in the other panel, which this one may not show too; null when that panel is empty. */
  otherId: number | null;
  history: History;
  onShow: (id: number) => void;
  /** Empties this panel. Only the second panel has it. */
  onClose?: () => void;
  focusNext?: FocusNext;
}) {
  const ids = useId();
  const headingId = `${ids}-heading`;
  const selectId = `${ids}-report`;
  const errorId = `${ids}-error`;
  const frameRef = useRef<HTMLIFrameElement>(null);
  const [generation, setGeneration] = useState(0);
  const [place, setPlace] = useState<PaneLocation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const heading = useTakeFocus(focusNext, "second");

  // Newest first, as Reports lists them. A report outside the site's list
  // (another site, or older than the list keeps) is still named.
  const listed = [...(history.points ?? [])].reverse();
  const options: SelectOption[] = listed.map((point) => ({
    value: String(point.id),
    label: [reportName(point.id), scanDay(point)].filter(Boolean).join(", "),
  }));
  if (!listed.some((point) => point.id === reportId)) {
    options.unshift({ value: String(reportId), label: reportName(reportId) });
  }
  const [choice, setChoice] = useState(String(reportId));
  // A new report from the address (Back, or the other panel's choice) resets
  // the picker and what the panel last said about itself.
  useEffect(() => {
    setChoice(String(reportId));
    setError(null);
    setPlace(null);
  }, [reportId]);

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

  const src = useHref(`/scans/${reportId}/issues`);
  const name = reportName(reportId);
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
          {/* As tall as the Close button in both panels (`min-h-target`), so
              the two frames start at the same height side by side. */}
          <div className="flex min-h-target items-center justify-between gap-2">
            {/* `tabIndex={-1}`: a target for focus after a choice, not a stop in the tab order. */}
            <h2 ref={heading} id={headingId} tabIndex={-1} className="min-w-0 text-base font-semibold text-fg">
              {name}
              {day && (
                <>
                  <span className="sr-only">,</span>{" "}
                  <span className="text-sm font-normal text-fg-muted">scanned {day}</span>
                </>
              )}
            </h2>
            {onClose && (
              <Button type="button" variant="ghost" onClick={onClose} className="shrink-0 px-3">
                <X className="h-4 w-4" aria-hidden />
                <span>
                  Close<span className="sr-only"> {name.toLowerCase()}</span>
                </span>
              </Button>
            )}
          </div>
          {/* One row when it fits, Go back first. The picker's label
              "Report" sits beside its box when there is room and above it
              when there is not (`stacked="when-narrow"`, see Select): the
              developer asked for it beside the box (2026-10-29), to save a
              line. It stays a visible label either way, never only an
              `aria-label`: a visible label is what SC 3.3.2 Labels or
              Instructions (Level A) asks for, voice control users say the
              word they see, and without it the box reads as a fact about
              the panel rather than a choice. Above, in a narrow panel (320
              px, or side by side at 1024 px), the box keeps the whole width
              for the report's name instead of sharing it with the label. */}
          <div className="mt-2 flex flex-wrap items-end gap-2">
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
            {history.failed ? (
              <p className="text-sm text-fg-muted">The list of reports could not load. Try again later.</p>
            ) : !history.points ? (
              <p role="status" className="text-sm text-fg-muted">Loading the list of reports…</p>
            ) : options.length > 1 ? (
              <form onSubmit={submit} className="flex min-w-0 flex-wrap items-end gap-2">
                <Select
                  id={selectId}
                  stacked="when-narrow"
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
                    Show this report<span className="sr-only"> in place of {name.toLowerCase()}</span>
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
        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- the frame's load event, not a reader's action */}
        <iframe
          key={`${reportId}-${generation}`}
          ref={frameRef}
          src={src}
          title={`${name}, ${place?.title || "Accessibility issues"}`}
          loading="eager"
          // Ask the panel where it is once it has loaded, in case its first
          // word came before this page was listening.
          onLoad={() => send({ source: PANE_MESSAGE_SOURCE, type: "report" })}
          className={cn("block w-full rounded-b-xs border-0 bg-surface-subtle", PANEL_HEIGHT)}
        />
      </Card>
    </section>
  );
}

/** A report frame's height: the window below the top bar side by side, 80% of it stacked. */
const PANEL_HEIGHT = "h-[80vh] min-h-[28rem] lg:h-[calc(100vh-7rem)] lg:min-h-[32rem]";

/**
 * The second panel before a report is chosen for it: a dashed box listing the
 * site's other completed reports, each a link that shows it here.
 *
 * Why (keep these when you change it):
 *
 * - **A dashed edge, not a card.** The developer asked for "a dashed blank"
 *   (2026-10-29). Dashed reads as a place to put something, the way an empty
 *   slot or a drop zone does, and sets this panel apart from the solid card
 *   of a report. The words say the same thing, so the edge is not the only
 *   cue (SC 1.4.1 Use of Color, Level A, in spirit: no meaning by look
 *   alone). It is as tall as a report's frame, so the two panels line up
 *   side by side.
 * - **The choices are in the box, one click each.** The request was to click
 *   the box to choose a report. One big button that then opened a list was
 *   considered and rejected: it adds a step, and hides the choices until it
 *   is pressed (W3C COGA, "Making Content Usable", objective 4, help users
 *   focus, and objective 5, help users avoid mistakes; paraphrased: fewer
 *   steps, nothing hidden). So the box lists the reports itself, each a whole
 *   row to press, at least 44 pixels tall (SC 2.5.5 Target Size (Enhanced),
 *   Level AAA). They are links, because each opens an address
 *   (`?compare_to=N`) that can be bookmarked or opened in a new tab; a
 *   button would do neither. A picker with "Show this report", as above a
 *   report's panel, was the other option; a list shows every report's date
 *   and size at once, which is what picking one needs.
 * - **Newest first, without the first panel's report**, as Reports and the
 *   panels' pickers list them. Each row names the report, the day it was
 *   scanned, and how many kinds of issues and occurrences it found, in the
 *   words the rest of the app uses (docs/plain-language.md, Terms).
 *   Screen-reader-only words end each link's name, "(compare with Report
 *   #24)", as the "Compare with" list on Reports ends its links (technique
 *   C7; SC 2.4.4 Link Purpose (In Context), Level A).
 * - **A site with one report** gets the box with a sentence saying how to
 *   get a second report, not an empty list.
 */
function EmptyPane({
  reportId,
  history,
  focusNext,
}: {
  /** The first panel's report. */
  reportId: number;
  history: History;
  focusNext: FocusNext;
}) {
  const ids = useId();
  const headingId = `${ids}-heading`;
  const heading = useTakeFocus(focusNext, "empty");
  const others = [...(history.points ?? [])].reverse().filter((point) => point.id !== reportId);
  const title = history.points && others.length === 0 ? "Nothing to compare with yet" : "Choose a report to compare with";

  return (
    // Side by side, the grid row is as tall as the report's panel; the box
    // fills it (`flex-1`), so the two panels end together. Stacked, it is
    // at least as tall as a frame's minimum, and grows with a long list.
    <section aria-labelledby={headingId} className="flex min-w-0 flex-col">
      <div className="flex min-h-[28rem] flex-1 flex-col rounded-xs border-2 border-dashed border-border-strong bg-surface-subtle p-4">
        {/* `tabIndex={-1}`: a target for focus after Close, not a stop in the tab order. */}
        <h2 ref={heading} id={headingId} tabIndex={-1} className="text-base font-semibold text-fg">
          {title}
        </h2>
        {history.failed ? (
          <p className="mt-1 text-sm text-fg-muted">The list of reports could not load. Try again later.</p>
        ) : !history.points ? (
          <p role="status" className="mt-1 text-sm text-fg-muted">Loading the list of reports…</p>
        ) : others.length === 0 ? (
          <p className="mt-1 text-sm leading-relaxed text-fg-muted">
            This site has one completed report so far. Scan the site again after you fix issues, then compare the two
            reports here.
          </p>
        ) : (
          <>
            {/* No sentence between the heading and the list: the heading says
                what to do, and the developer removed a line repeating it
                (2026-10-29). */}
            <ul className="mt-3 flex flex-col gap-2">
              {others.map((point) => {
                const day = scanDay(point);
                return (
                  <li key={point.id}>
                    <Link
                      to={pairPath(reportId, point.id)}
                      onClick={() => {
                        focusNext.current = "second";
                      }}
                      className="flex min-h-target flex-col justify-center rounded-xs border border-border bg-surface px-3 py-2 text-sm text-fg no-underline shadow-sm hover:border-umich-blue hover:bg-surface-muted"
                    >
                      <span className="font-semibold text-umich-blue underline underline-offset-2">
                        {reportName(point.id)}
                      </span>
                      <span className="text-fg-muted">
                        {day && <>Scanned {day}. </>}
                        {countKinds(point.groups)}, {count(point.occurrences, "occurrence")}
                      </span>
                      <span className="sr-only"> (compare with {reportName(reportId)})</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
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
