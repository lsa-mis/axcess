/**
 * A running scan's page: how far it has got, and where each page stands.
 *
 * It wears the report pages' header, so a scan in progress reads as the
 * report it will become. The progress card leads with one bar, the three
 * steps a scan goes through, the time left and Stop scan, and keeps the
 * rest (live updates, each check's totals) behind "Show details": the page
 * used to open on six panels of equal weight, and the one question most
 * readers bring, "how far along is it?", had no single answer on screen.
 *
 * Under it, one table: a row per page and a column per check, each cell
 * done, checking, waiting or not run. The cells come from the crawl's own
 * process (see ``audit.crawler.live_progress``). A page it has no record of
 * says only what the queue knows, and never claims a check ran.
 */
import { useId, useState, type ReactNode } from "react";
import { Check, CircleDot, Clock3, Minus, Pause, Play, Square } from "lucide-react";
import type {
  PageCheckState,
  ScanDetail,
  ScanMethodCoverage,
  ScanMethodState,
  ScanPageChecks,
  ScanProgress,
} from "../api/types";
import ReportHeader from "./ReportHeader";
import { siteLabel, withoutUserinfo } from "./ReportCrumb";
import { Cell, ColumnHeader, Row, RowHeader, Table, TableHead, TableRegion } from "./table/Table";
import { Button, Card, relativeTime } from "./ui";
import { cn } from "../lib/cn";
import { CLICK_THROUGH } from "../lib/labels";
import { checkedPercent, formatScanEta } from "../lib/scanProgress";
import { CHECK_LABEL } from "../lib/terms";

/** Each check a page goes through, by its interface name, keyed as the API keys methods. */
const CHECK_NAME: Record<string, string> = {
  axe: CHECK_LABEL.axe,
  alfa: CHECK_LABEL.alfa,
  keyboard: CHECK_LABEL.keyboard,
  responsive: CHECK_LABEL.responsive,
  interaction: CLICK_THROUGH,
  image: CHECK_LABEL.image,
  semantic: CHECK_LABEL.semantic,
};

type StepStatus = "done" | "active" | "waiting";

export default function ScanProgressView({
  scan,
  cancel,
  liveUpdates,
  isFetching,
  onToggleLiveUpdates,
}: {
  scan: ScanDetail;
  cancel: { mutate: () => void; isPending: boolean };
  liveUpdates: boolean;
  isFetching: boolean;
  onToggleLiveUpdates: () => void;
}) {
  const progress = scan.progress;
  const stage = progress?.stage ?? "starting";
  const preparing = stage === "preparing_report";
  const discovered = progress?.discovered ?? 0;
  const completed = progress?.completed ?? 0;
  const percent = checkedPercent(progress);
  const checks = scan.methods_used.filter((method) => method.enabled && method.key in CHECK_NAME);
  const site = siteLabel(scan.seed_url);

  return (
    <>
      <ReportHeader
        scanId={scan.id}
        previousScanId={null}
        title="Scan in progress"
        meta={
          <>
            <span className="font-semibold text-fg">{site}</span>
            <span aria-hidden className="px-1.5 text-border-strong">·</span>
            Report #{scan.id}
            <span aria-hidden className="px-1.5 text-border-strong">·</span>
            <span title={scan.started_at ?? undefined}>Started {relativeTime(scan.started_at)}</span>
          </>
        }
      />

      {/* Said once per refresh, politely, in the words the bar and the
          steps show. */}
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {preparing
          ? "All pages are checked. Preparing the report."
          : `${percent}% checked: ${completed} of ${discovered} pages found so far. ${progress?.leased ?? 0} being checked now.`}
      </p>

      <ProgressCard
        progress={progress}
        preparing={preparing}
        stage={stage}
        discovered={discovered}
        completed={completed}
        percent={percent}
        cancel={cancel}
        details={
          <ProgressDetails
            checks={checks}
            liveUpdates={liveUpdates}
            isFetching={isFetching}
            onToggleLiveUpdates={onToggleLiveUpdates}
          />
        }
      />

      <PagesTable
        rows={pageRows(progress)}
        checks={checks}
        preparing={preparing}
        seedUrl={scan.seed_url}
      />
    </>
  );
}

function ProgressCard({
  progress,
  preparing,
  stage,
  discovered,
  completed,
  percent,
  cancel,
  details,
}: {
  progress: ScanProgress | null;
  preparing: boolean;
  stage: ScanProgress["stage"];
  discovered: number;
  completed: number;
  percent: number;
  cancel: { mutate: () => void; isPending: boolean };
  details: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const steps: { title: string; status: StepStatus; detail: string }[] = [
    {
      title: "Find pages",
      status: preparing ? "done" : "active",
      detail: `${discovered.toLocaleString()} found · ${(progress?.pending ?? 0).toLocaleString()} waiting`,
    },
    {
      title: "Check pages",
      status: preparing ? "done" : stage === "starting" ? "waiting" : "active",
      detail: `${completed.toLocaleString()} checked · ${(progress?.leased ?? 0).toLocaleString()} now`,
    },
    {
      title: "Prepare report",
      status: preparing ? "active" : "waiting",
      detail: preparing ? "Grouping occurrences into issues" : "After every page is checked",
    },
  ];
  // Finding and checking run together, so two steps can be in progress at
  // once; the later one is the step the scan is on.
  const currentStep = steps.map((step) => step.status).lastIndexOf("active");

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold text-fg">
            {preparing ? "Preparing your report" : "Finding and checking pages"}
          </h2>
          {/* The percent leads; the counts it comes from follow, since the
              total grows as the scan finds links. */}
          <p className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="text-4xl font-semibold leading-none tabular-nums text-umich-blue">{percent}%</span>
            <span className="text-sm text-fg-muted">
              <span className="font-semibold text-fg">checked</span> · {completed.toLocaleString()} of{" "}
              {discovered.toLocaleString()} pages found so far
            </span>
          </p>
        </div>
        <Button
          variant="danger"
          onClick={() => {
            if (confirm("Stop this scan? Axcess will not check the pages that are still waiting."))
              cancel.mutate();
          }}
          disabled={cancel.isPending}
        >
          <Square className="h-4 w-4 fill-current" aria-hidden />
          {cancel.isPending ? "Stopping…" : "Stop scan"}
        </Button>
      </div>

      {/* The count above is the accessible version of this bar. */}
      <div aria-hidden className="mt-4 h-3 overflow-hidden rounded-full bg-surface-muted ring-1 ring-inset ring-border">
        <div
          className="h-full rounded-full bg-umich-blue transition-[width] duration-500 motion-reduce:transition-none"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="mt-2 flex items-center gap-1.5 text-sm text-fg-muted">
        <Clock3 className="h-4 w-4 shrink-0" aria-hidden />
        <span>
          <span className="font-semibold text-fg">Time left:</span> {formatScanEta(progress?.eta)}
        </span>
      </p>

      <ol className="mt-5 grid gap-3 sm:grid-cols-3" aria-label="Scan steps">
        {steps.map((step, index) => (
          <ScanStep key={step.title} number={index + 1} current={index === currentStep} {...step} />
        ))}
      </ol>

      <div className="mt-5 border-t border-border pt-3">
        {/* eslint-disable-next-line react/forbid-elements -- Convert: a text disclosure button, Button variant="ghost" */}
        <button
          type="button"
          aria-expanded={open}
          aria-controls={detailsId}
          onClick={() => setOpen((value) => !value)}
          className="inline-flex min-h-target items-center gap-1.5 rounded-xs px-1 text-sm font-semibold text-umich-blue underline underline-offset-2 hover:bg-surface-muted focus-visible:outline-none focus-visible:shadow-focus"
        >
          {open ? "Hide details" : "Show details"}
        </button>
        <div id={detailsId} hidden={!open} className="mt-3">
          {open && details}
        </div>
      </div>
    </Card>
  );
}

const STEP_WORD: Record<StepStatus, string> = { done: "Done", active: "In progress", waiting: "Waiting" };

/** One step: a numbered circle, a green tick once done; the word says it too. */
function ScanStep({
  number,
  title,
  status,
  detail,
  current,
}: {
  number: number;
  title: string;
  status: StepStatus;
  detail: string;
  current: boolean;
}) {
  return (
    <li
      aria-current={current ? "step" : undefined}
      className={cn(
        "flex items-start gap-3 rounded-xs border p-3",
        status === "active" ? "border-umich-blue/40 bg-umich-blue/5" : "border-border bg-surface",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold",
          status === "done"
            ? "bg-ok-bg text-ok ring-1 ring-inset ring-ok/30"
            : status === "active"
              ? "bg-umich-blue text-fg-inverse"
              : "bg-surface-muted text-fg-muted ring-1 ring-inset ring-border",
        )}
      >
        {status === "done" ? <Check className="h-4 w-4" strokeWidth={3} /> : number}
      </span>
      <div className="min-w-0">
        <p className="text-sm font-semibold text-fg">
          {title}
          <span className="sr-only">: </span>
          <span className="ml-2 text-xs font-semibold text-fg-muted">{STEP_WORD[status]}</span>
        </p>
        <p className="mt-0.5 text-xs text-fg-muted">{detail}</p>
      </div>
    </li>
  );
}

function ProgressDetails({
  checks,
  liveUpdates,
  isFetching,
  onToggleLiveUpdates,
}: {
  checks: ScanMethodCoverage[];
  liveUpdates: boolean;
  isFetching: boolean;
  onToggleLiveUpdates: () => void;
}) {
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)]">
      <section aria-labelledby="progress-checks-title">
        <h3 id="progress-checks-title" className="text-sm font-semibold text-fg">
          Checks you chose
        </h3>
        <ul className="mt-2 divide-y divide-border rounded-xs border border-border">
          {checks.map((method) => (
            <li key={method.key} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-3">
              <span className="text-sm font-semibold text-fg">{CHECK_NAME[method.key] ?? method.label}</span>
              <span className="flex items-center gap-3 text-sm text-fg-muted">
                <span className="tabular-nums">{method.result}</span>
                <MethodChip state={method.state} />
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-fg-muted">Totals count a page once Axcess saves its results.</p>
      </section>
      <section aria-labelledby="progress-live-title">
        <h3 id="progress-live-title" className="text-sm font-semibold text-fg">
          Live updates
        </h3>
        <p className="mt-1 text-sm text-fg-muted" role="status" aria-live="polite">
          {!liveUpdates
            ? "Live updates paused. The scan continues in the background."
            : isFetching
              ? "Checking for new scan activity…"
              : "On. This page checks every 2 seconds."}
        </p>
        <Button variant="secondary" className="mt-2" onClick={onToggleLiveUpdates}>
          {liveUpdates ? <Pause className="h-4 w-4" aria-hidden /> : <Play className="h-4 w-4" aria-hidden />}
          {liveUpdates ? "Pause live updates" : "Resume live updates"}
        </Button>
      </section>
    </div>
  );
}

const METHOD_WORD: Record<ScanMethodState, string> = {
  not_selected: "Not chosen",
  waiting: "Waiting",
  running: "Checking",
  checked: "Done",
  partial: "Partly done",
  not_run: "Did not run",
  coverage_unknown: "Not recorded",
};

function MethodChip({ state }: { state: ScanMethodState }) {
  const tone: PageCheckState =
    state === "checked" || state === "partial"
      ? "done"
      : state === "running"
        ? "running"
        : state === "waiting"
          ? "waiting"
          : "not_run";
  return <Chip tone={tone}>{METHOD_WORD[state]}</Chip>;
}

const CELL_WORD: Record<PageCheckState, string> = {
  done: "Done",
  running: "Checking",
  waiting: "Waiting",
  not_run: "Not run",
};

/**
 * A state in words with an icon as its second signal, colour the third: a
 * tick on green for done, a dot on yellow for checking, a clock for
 * waiting, a dash for not run.
 */
function Chip({ tone, children }: { tone: PageCheckState; children: ReactNode }) {
  const Icon = tone === "done" ? Check : tone === "running" ? CircleDot : tone === "waiting" ? Clock3 : Minus;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-2xs font-semibold",
        tone === "done"
          ? "border-ok/30 bg-ok-bg text-ok"
          : tone === "running"
            ? "border-umich-maize/60 bg-umich-maize/15 text-fg"
            : "border-border bg-surface text-fg-muted",
      )}
    >
      <Icon className="h-3 w-3 shrink-0" strokeWidth={3} aria-hidden />
      {children}
    </span>
  );
}

const PAGE_WORD: Record<ScanPageChecks["state"], string> = {
  checking: "Being checked",
  checked: "Checked",
  waiting: "Waiting",
};

/**
 * The table's rows. A server that predates ``page_checks`` still sends the
 * pages in progress and the latest checked, so those make rows with the
 * page's own state and no per-check detail.
 */
function pageRows(progress: ScanProgress | null): ScanPageChecks[] {
  if (!progress) return [];
  if (progress.page_checks) return progress.page_checks;
  return [
    ...progress.in_flight_pages.map((page) => ({ url: page.url, state: "checking" as const, checks: {} })),
    ...progress.recent_pages.map((page) => ({ url: page.url_normalized, state: "checked" as const, checks: {} })),
  ];
}

/**
 * The address without the site, which the header already names. The part
 * after "#" stays: a single-page app's pages differ only there
 * ("/#/about", "/#/projects"), and without it every row read "/". A page
 * on another host (a subdomain) keeps its host.
 */
function pagePath(url: string, seedUrl: string): string {
  try {
    const parsed = new URL(url);
    const path = `${parsed.pathname}${parsed.search}${parsed.hash}` || "/";
    return parsed.host === new URL(seedUrl).host ? path : `${parsed.host}${path}`;
  } catch {
    return url;
  }
}

function PagesTable({
  rows,
  checks: chosen,
  preparing,
  seedUrl,
}: {
  rows: ScanPageChecks[];
  checks: ScanMethodCoverage[];
  preparing: boolean;
  seedUrl: string;
}) {
  // Per-check states exist only while the scan runs in the process serving
  // this page (see audit.crawler.live_progress). A scan run from the command
  // line, one that was running when Axcess restarted, or a server older than
  // this table has none; then the check columns would only repeat "no
  // record" on every row, so the table drops them and says why once.
  const tracked = rows.some((row) => Object.keys(row.checks).length > 0);
  const checks = tracked ? chosen : [];
  return (
    <Card className="mt-5 overflow-hidden">
      <div className="px-5 pb-3 pt-4">
        <h2 id="progress-pages-title" className="text-base font-semibold text-fg">
          {tracked ? "Pages and checks" : "Pages"}
        </h2>
        <p className="mt-1 text-sm text-fg-muted">
          The pages being checked now, the latest finished, and the next few waiting.
          {!tracked && rows.length > 0 && (
            <> Each check&rsquo;s progress on a page is not available for this scan, so each page shows its status only.</>
          )}
        </p>
      </div>
      {rows.length === 0 ? (
        <p className="border-t border-border px-5 py-6 text-sm text-fg-muted">
          {preparing ? "All pages are checked. Axcess is putting the report together." : "Starting the first page…"}
        </p>
      ) : (
        <TableRegion label="Pages and checks">
          <Table
            caption={tracked ? "Each page and where each check stands on it" : "Each page and its status"}
            className={cn("border-t border-border", checks.length > 3 ? "min-w-[56rem]" : "min-w-[28rem]")}
          >
            <TableHead>
              <tr>
                <ColumnHeader>Page</ColumnHeader>
                <ColumnHeader>Status</ColumnHeader>
                {checks.map((method) => (
                  <ColumnHeader key={method.key}>{CHECK_NAME[method.key]}</ColumnHeader>
                ))}
              </tr>
            </TableHead>
            <tbody>
              {rows.map((row, index) => (
                <Row key={`${row.state}-${row.url}`} index={index}>
                  <RowHeader className="max-w-[22rem] font-normal">
                    <span className="block break-all font-mono text-xs text-fg" title={withoutUserinfo(row.url)}>
                      {pagePath(row.url, seedUrl)}
                    </span>
                  </RowHeader>
                  <Cell className="whitespace-nowrap text-center text-sm font-semibold text-fg">{PAGE_WORD[row.state]}</Cell>
                  {checks.map((method) => {
                      // A waiting page has started no check; any other page
                      // without a state for a check was not tracked for it
                      // (checked before a restart, say), which says so.
                      const state = row.checks[method.key] ?? (row.state === "waiting" ? "waiting" : undefined);
                      return (
                        <Cell key={method.key} className="text-center">
                          {state ? (
                            <Chip tone={state}>{CELL_WORD[state]}</Chip>
                          ) : (
                            <span className="text-xs text-fg-muted">Not recorded</span>
                          )}
                        </Cell>
                      );
                    })}
                </Row>
              ))}
            </tbody>
          </Table>
        </TableRegion>
      )}
    </Card>
  );
}
