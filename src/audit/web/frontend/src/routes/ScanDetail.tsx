/**
 * A report's own URL: progress while it runs, why it stopped if it failed,
 * and the report itself once it finishes.
 *
 * This route has three faces, chosen by scan status. Running shows the
 * progress panel and a cancel control. Failed or interrupted shows why and
 * offers a retry. Completed redirects to the Issues table, which is where a
 * report opens: it used to have an Overview tab of its own here, and its
 * numbers and coverage now sit above the table (see ``ReportSummary``). The
 * redirect keeps every existing ``/scans/:id`` link working, and a scan that
 * finishes while the reader watches lands them on its report.
 *
 * The mutations here are the scan's lifecycle actions -- cancel, retry --
 * and each has to reconcile the cache by hand afterwards, since they change
 * records other screens are already showing.
 */
import { Navigate, useNavigate, useParams } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Clock3,
  FileOutput,
  Loader2,
  Pause,
  Play,
  Search,
  ShieldCheck,
  Square,
} from "lucide-react";
import { api } from "../api/client";
import type {
  ScanDetail,
  ScanMethodCoverage,
  ScanMethodState,
  ScanProgress,
} from "../api/types";
import { BlockedScanNotice } from "../components/ReportSummary";
import {
  Button,
  Card,
  LinkButton,
  PageHeader,
} from "../components/ui";
import { httpStatusLabel, renderModeLabel } from "../lib/pageLabels";
import { formatScanEta } from "../lib/scanProgress";
import { useScanQuery } from "../hooks/useScanQuery";

export default function ScanDetailRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [liveUpdates, setLiveUpdates] = useState(true);

  // Polls only while the scan is actually running, and only in a visible
  // tab. Shares the report summary cache entry with the gate and every
  // other report route; see useScanQuery.
  const { data, isLoading, error, isFetching } = useScanQuery(id, {
    refetchInterval: (query) =>
      liveUpdates && query.state.data?.status === "running" ? 2000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  });
  // Invalidating on the `["scan", id]` prefix reaches the identity-
  // partitioned key the shared hook actually uses. Do not narrow it to an
  // exact key here without reading useScanQuery first.
  const cancel = useMutation({
    mutationFn: () => api.cancelScan(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scan", id] }),
  });
  // "Retry" re-submits the same seed with a fixed balanced profile rather
  // than the settings the original scan used: this button exists for a scan
  // that failed, and repeating a configuration that just failed is rarely
  // what the operator wants. The expensive optional passes (VLM, semantic,
  // interaction, visual) are off so the retry finishes quickly enough to
  // tell them whether the site is reachable at all.
  //
  // A retry may produce a new scan id. When it does, navigate to it,
  // replacing history so Back does not return to a report that is now
  // superseded.
  const retryBalanced = useMutation({
    mutationFn: () =>
      api.createScan({
        url: data?.seed_url ?? "",
        max_pages: 2500,
        max_depth: 10,
        rps: 2,
        workers: 8,
        include_subdomain: false,
        whole_host: false,
        ignore_robots: false,
        skip_ocr: false,
        skip_vlm: true,
        static_only: false,
        show_browser: false,
        scan_engine: "axe",
        skip_interaction: true,
        skip_keyboard: false,
        skip_responsive: false,
        skip_semantic: true,
        skip_focus: false,
        skip_visual: true,
        axe_level: "AA",
        skip_rendered_storage: false,
      }),
    onSuccess: async ({ scan_id }) => {
      setLiveUpdates(true);
      qc.removeQueries({ queryKey: ["issues", id] });
      await qc.invalidateQueries({ queryKey: ["scan", id] });
      await qc.invalidateQueries({ queryKey: ["scans"] });
      if (scan_id !== id) navigate(`/scans/${scan_id}`, { replace: true });
    },
  });

  if (error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        {error instanceof Error ? error.message : String(error)}
      </Card>
    );
  }
  if (isLoading || !data) return <div className="text-fg-muted">Loading…</div>;

  if (data.status === "running") {
    return (
      <>
        <PageHeader title="Scan in progress" subtitle={data.seed_url} />
        <ScanProgressPanel
          scan={data}
          progress={data.progress}
          cancel={cancel}
          liveUpdates={liveUpdates}
          isFetching={isFetching}
          onToggleLiveUpdates={() => setLiveUpdates((current) => !current)}
        />
      </>
    );
  }

  if (data.status === "completed") {
    return <Navigate replace to={`/scans/${data.id}/issues`} />;
  }

  return (
    <>
      <PageHeader title={`Scan #${data.id}`} subtitle={data.seed_url} />

      {data.blocked && (
        <BlockedScanNotice scanId={data.id} blocked={data.blocked} />
      )}

      <Card className="p-5">
        {/* "No report was produced" was told to scans that had produced
            thousands of findings across hundreds of pages, because it keyed
            on the status rather than on whether anything was collected. A
            stopped scan keeps everything it reached; what it cannot claim is
            that the site was covered. Say that, and leave the evidence
            reachable. */}
        <h2 className="font-semibold text-fg">
          {data.page_count > 0 ? "Partial report" : "No report was produced"}
        </h2>
        <p className="mt-1 text-sm text-fg-muted">
          {data.page_count > 0 ? (
            <>
              This scan ended as <strong>{data.status}</strong> after{" "}
              {data.page_count.toLocaleString()} page
              {data.page_count === 1 ? "" : "s"}. Everything it reached is
              saved and can be reviewed below; the rest of the site was not
              visited, so this is not evidence of full coverage.
            </>
          ) : (
            <>
              This scan ended as <strong>{data.status}</strong> before any page
              finished. No report evidence was created.
            </>
          )}
        </p>
        {data.failure_reason && (
          <p className="mt-3 rounded-xs border border-sev-critical/30 bg-sev-critical-bg p-3 text-sm text-sev-critical">
            <strong>Why it failed:</strong> {data.failure_reason}
          </p>
        )}
        {retryBalanced.error && (
          <p className="mt-3 text-sm text-sev-critical" role="alert">
            Couldn&rsquo;t restart this scan: {retryBalanced.error.message}
          </p>
        )}
        <div className="mt-4 flex flex-wrap gap-3">
          <Button
            type="button"
            variant="primary"
            onClick={() => retryBalanced.mutate()}
            disabled={retryBalanced.isPending}
          >
            {retryBalanced.isPending
              ? "Restarting scan…"
              : "Retry with balanced settings"}
          </Button>
          <LinkButton
            to={`/scans/new?url=${encodeURIComponent(data.seed_url)}`}
            variant="secondary"
          >
            Review settings first
          </LinkButton>
          {/* Without this the page said evidence "remains available" and
              then offered no way to reach it, so the only route onward was
              to run the scan again. */}
          {data.page_count > 0 && (
            <LinkButton to={`/scans/${data.id}/issues`} variant="secondary">
              Review what was collected
            </LinkButton>
          )}
        </div>
      </Card>
    </>
  );
}

function ScanProgressPanel({
  scan,
  progress,
  cancel,
  liveUpdates,
  isFetching,
  onToggleLiveUpdates,
}: {
  scan: ScanDetail;
  progress: ScanProgress | null;
  cancel: { mutate: () => void; isPending: boolean };
  liveUpdates: boolean;
  isFetching: boolean;
  onToggleLiveUpdates: () => void;
}) {
  const enabledMethods = scan.methods_used.filter((method) => method.enabled);
  const stage = progress?.stage ?? "starting";
  const isPreparing = stage === "preparing_report";

  return (
    <Card className="overflow-hidden border-umich-blue/30 [overflow-anchor:none]">
      <div className="flex flex-wrap items-start justify-between gap-3 bg-umich-blue/5 p-5">
        <div>
          <div className="flex items-center gap-2">
            <Loader2
              className="h-5 w-5 animate-spin text-umich-blue"
              aria-hidden
            />
            <h2 id="scan-progress-title" className="font-semibold text-fg">
              {isPreparing
                ? "Preparing your report"
                : "Discovering and testing pages"}
            </h2>
          </div>
          <p className="mt-1 text-sm text-fg-muted">
            Live data updates this panel without reloading the page or moving
            your scroll position.
          </p>
          <p className="mt-1 text-xs text-fg-muted">
            The site can reveal more links during the crawl, so the ETA is a
            range, not a fixed deadline.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={onToggleLiveUpdates}>
            {liveUpdates ? (
              <Pause className="h-4 w-4" aria-hidden />
            ) : (
              <Play className="h-4 w-4" aria-hidden />
            )}
            {liveUpdates ? "Pause live updates" : "Resume live updates"}
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              if (confirm("Stop this scan? Pending pages will be dropped."))
                cancel.mutate();
            }}
            disabled={cancel.isPending}
          >
            <Square className="h-4 w-4 fill-current" aria-hidden />
            {cancel.isPending ? "Stopping…" : "Stop scan"}
          </Button>
        </div>
      </div>

      <div
        className="sr-only"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {isPreparing
          ? "Page testing complete. Preparing report."
          : `${progress?.discovered ?? 0} pages discovered, ${progress?.completed ?? 0} completed, ${progress?.leased ?? 0} in progress.`}
      </div>

      <div
        className="grid gap-px bg-border md:grid-cols-4"
        aria-labelledby="scan-progress-title"
      >
        <ProgressStage
          icon={<Search className="h-5 w-5" aria-hidden />}
          title="Discover pages"
          status={isPreparing ? "complete" : "active"}
          detail={`${progress?.discovered ?? 0} discovered · ${progress?.pending ?? 0} queued`}
        />
        <ProgressStage
          icon={<ShieldCheck className="h-5 w-5" aria-hidden />}
          title="Render and test"
          status={
            stage === "starting"
              ? "waiting"
              : isPreparing
                ? "complete"
                : "active"
          }
          detail={`${progress?.completed ?? 0} completed · ${progress?.leased ?? 0} active`}
        />
        <ProgressStage
          icon={<FileOutput className="h-5 w-5" aria-hidden />}
          title="Prepare report"
          status={isPreparing ? "active" : "waiting"}
          detail={
            isPreparing
              ? "Grouping evidence and recommendations"
              : "Starts after the crawl settles"
          }
        />
        <ProgressStage
          icon={<Clock3 className="h-5 w-5" aria-hidden />}
          title="Estimated time"
          status={
            isPreparing
              ? "active"
              : progress?.eta.state === "range"
                ? "active"
                : "waiting"
          }
          detail={formatScanEta(progress?.eta)}
        />
      </div>

      <p
        className="border-b border-border bg-surface px-5 py-2 text-xs text-fg-muted"
        role="status"
        aria-live="polite"
      >
        {!liveUpdates
          ? "Live updates paused. The scan continues in the background."
          : isFetching
            ? "Checking for new scan activity…"
            : "Live updates on · next check in about 2 seconds"}
      </p>

      <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)]">
        <section aria-labelledby="current-work-title">
          <h3 id="current-work-title" className="font-semibold text-fg">
            What Axcess is scanning
          </h3>
          <div className="mt-3 min-h-[7.5rem]">
            {progress?.in_flight_pages.length ? (
              <ul className="max-h-64 space-y-2 overflow-y-auto overscroll-contain pr-1">
                {progress.in_flight_pages.map((page) => (
                  <li
                    key={page.url}
                    className="rounded-xs border border-border bg-surface-muted p-3"
                  >
                    <div className="flex items-start gap-2">
                      <Loader2
                        className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-umich-blue"
                        aria-hidden
                      />
                      <div className="min-w-0">
                        <div
                          className="truncate font-mono text-xs text-fg"
                          title={page.url}
                        >
                          {page.url}
                        </div>
                        <div className="mt-1 text-xs text-fg-muted">
                          Fetching, rendering, and running selected checks ·
                          depth {page.depth}
                          {page.attempts > 1
                            ? ` · attempt ${page.attempts}`
                            : ""}
                        </div>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-xs border border-border bg-surface-muted p-3 text-sm text-fg-muted">
                {isPreparing
                  ? "All queued pages are settled. Axcess is consolidating the report."
                  : "Starting the first page…"}
              </p>
            )}
          </div>

          {!!progress?.recent_pages.length && (
            <section className="mt-4" aria-labelledby="recent-pages-title">
              <h4
                id="recent-pages-title"
                className="py-2 text-sm font-semibold text-fg"
              >
                Recently completed pages
              </h4>
              <ul className="max-h-64 space-y-1 overflow-y-auto overscroll-contain pr-1 text-xs">
                {progress.recent_pages.map((page) => (
                  <li
                    key={page.url_normalized}
                    className="rounded-xs bg-surface-muted px-3 py-2"
                  >
                    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                      <span
                        className={
                          page.status_code &&
                          page.status_code >= 200 &&
                          page.status_code < 300
                            ? "font-medium text-fg"
                            : "font-medium text-sev-critical"
                        }
                      >
                        {httpStatusLabel(page.status_code)}
                      </span>
                      <span aria-hidden className="text-fg-subtle">
                        ·
                      </span>
                      <span className="text-fg-muted">
                        {renderModeLabel(page.render_mode)}
                      </span>
                    </div>
                    <div
                      className="mt-1 truncate font-mono text-fg-muted"
                      title={page.url_normalized}
                    >
                      {page.url_normalized}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </section>

        <section aria-labelledby="method-progress-title">
          <h3 id="method-progress-title" className="font-semibold text-fg">
            Selected checks
          </h3>
          <p className="mt-1 text-xs text-fg-muted">
            Each row explains the method and reports completed work, not merely
            configuration.
          </p>
          <MethodCoverageList
            methods={enabledMethods}
            className="mt-3"
            compact
          />
          <p className="mt-2 text-xs text-fg-muted">
            Engine totals show completed evaluations; active pages appear after
            their evidence is safely stored.
          </p>
        </section>
      </div>
    </Card>
  );
}

function MethodCoverageList({
  methods,
  className = "",
  compact = false,
}: {
  methods: ScanMethodCoverage[];
  className?: string;
  compact?: boolean;
}) {
  return (
    <ul
      className={`${className} grid gap-3 ${compact ? "" : "lg:grid-cols-2"}`}
    >
      {methods.map((method) => (
        <li
          key={method.key}
          className="rounded-xs border border-border bg-surface-muted p-3"
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <span className="font-semibold text-fg">{method.label}</span>
            <MethodStateBadge state={method.state} />
          </div>
          <p className="mt-1 text-sm text-fg-muted">{method.description}</p>
          <p className="mt-2 text-sm font-medium tabular-nums text-fg">
            {method.result}
          </p>
          {!compact && (
            <p className="mt-1 text-xs text-fg-subtle">{method.caveat}</p>
          )}
        </li>
      ))}
    </ul>
  );
}

const METHOD_STATE_LABEL: Record<ScanMethodState, string> = {
  not_selected: "Not selected",
  waiting: "Waiting",
  running: "Checking",
  checked: "Checked",
  partial: "Partially checked",
  not_run: "Did not run",
  coverage_unknown: "Not recorded",
};

function MethodStateBadge({ state }: { state: ScanMethodState }) {
  const tone =
    state === "checked"
      ? "border-umich-blue/30 bg-umich-blue/10 text-umich-blue"
      : state === "running"
        ? "border-umich-maize/60 bg-umich-maize/15 text-fg"
        : state === "partial" || state === "not_run"
          ? "border-sev-major/30 bg-sev-major-bg text-sev-major"
          : "border-border bg-surface text-fg-muted";
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-2xs font-semibold ${tone}`}
    >
      {METHOD_STATE_LABEL[state]}
    </span>
  );
}

function ProgressStage({
  icon,
  title,
  status,
  detail,
}: {
  icon: React.ReactNode;
  title: string;
  status: "waiting" | "active" | "complete";
  detail: string;
}) {
  return (
    <div className="bg-surface p-4">
      <div className="flex items-center gap-2">
        <span
          className={
            status === "waiting" ? "text-fg-subtle" : "text-umich-blue"
          }
        >
          {icon}
        </span>
        <strong className="text-sm text-fg">{title}</strong>
        <span className="ml-auto text-2xs font-semibold text-fg-muted">
          {status === "complete"
            ? "Complete"
            : status === "active"
              ? "In progress"
              : "Waiting"}
        </span>
      </div>
      <p className="mt-2 text-xs text-fg-muted">{detail}</p>
    </div>
  );
}
