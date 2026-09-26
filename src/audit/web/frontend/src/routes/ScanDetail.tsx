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
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { RETRY } from "../components/newScan/copy";
import { PUBLIC_DEFAULTS, quickRetrySettings } from "../components/newScan/scanPolicy";
import { BlockedScanNotice } from "../components/ReportSummary";
import {
  Button,
  Card,
  LinkButton,
  PageHeader,
} from "../components/ui";
import { httpStatusLabel, renderModeLabel } from "../lib/pageLabels";
import { formatScanEta } from "../lib/scanProgress";
import { SCAN_STATUS_LABEL } from "../lib/terms";
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
  // Two ways back from a scan that failed or was stopped, each saying what
  // it does ("Retry with balanced settings" left readers asking whether
  // their settings were kept; they were not):
  //
  // - "Change settings first" opens New scan with this scan's own
  //   settings filled in (`from=`), the path that keeps what they chose.
  // - "Scan again with faster settings" re-submits the same address at
  //   once with the default profile and Click-Through off
  //   (`quickRetrySettings`), which finishes
  //   quickly enough to show whether the site can be scanned at all. It
  //   keeps the WCAG version the report was audited against. A login scan
  //   has no quick retry: it cannot run without someone signing in.
  //
  // The settings query also says which tab the scan belongs to. A report it
  // cannot describe (a protected report, an older row) still gets an edit
  // link, prefilled with the address only.
  const previousSettings = useQuery({
    queryKey: ["scan-settings", id],
    queryFn: () => api.getScanSettings(id),
    enabled: Boolean(data) && data?.status !== "running" && data?.status !== "completed",
    retry: false,
    staleTime: Infinity,
  });
  const loginScan = previousSettings.data?.mode === "login";
  // A retry may produce a new scan id. When it does, navigate to it,
  // replacing history so Back does not return to a report that is now
  // superseded.
  const quickRetry = useMutation({
    mutationFn: () =>
      api.createScan(
        // A report loaded without a version falls back to the new-scan default.
        quickRetrySettings(data?.seed_url ?? "", data?.wcag_version ?? PUBLIC_DEFAULTS.wcag_version),
      ),
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
  if (isLoading || !data) return <div className="text-fg-muted">Loading the scan…</div>;

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
      <PageHeader title={`Report #${data.id}`} subtitle={data.seed_url} />

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
              This scan ended with the status{" "}
              <strong>{SCAN_STATUS_LABEL[data.status]}</strong> after{" "}
              {data.page_count.toLocaleString()} page
              {data.page_count === 1 ? "" : "s"}. Axcess saved everything it
              reached, and you can review it. The scan did not visit the rest
              of the site, so this report does not cover the whole site.
            </>
          ) : (
            <>
              This scan ended with the status{" "}
              <strong>{SCAN_STATUS_LABEL[data.status]}</strong> before any page
              finished. Axcess did not create a report.
            </>
          )}
        </p>
        {data.failure_reason && (
          <p className="mt-3 rounded-xs border border-sev-critical/30 bg-sev-critical-bg p-3 text-sm text-sev-critical">
            <strong>Why it failed:</strong> {data.failure_reason}
          </p>
        )}
        {quickRetry.error && (
          <p className="mt-3 text-sm text-sev-critical" role="alert">
            Axcess could not start this scan again: {quickRetry.error.message}
          </p>
        )}
        {/* Each retry says in its own description what it keeps, so the
            choice is made on the words and not on a guess at "balanced". */}
        <ul className="mt-4 flex flex-col gap-4">
          <li className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:gap-4">
            <LinkButton
              to={
                previousSettings.data
                  ? `/scans/new?${loginScan ? "mode=login&" : ""}from=${data.id}`
                  : `/scans/new?url=${encodeURIComponent(data.seed_url)}`
              }
              variant="primary"
              aria-describedby="retry-edit-hint"
              className="shrink-0 sm:w-56"
            >
              {RETRY.edit}
            </LinkButton>
            <p id="retry-edit-hint" className="text-sm text-fg-muted sm:pt-2">
              {RETRY.editHint}
            </p>
          </li>
          {!loginScan && (
            <li className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:gap-4">
              <Button
                type="button"
                onClick={() => quickRetry.mutate()}
                disabled={quickRetry.isPending}
                aria-describedby="retry-quick-hint"
                className="shrink-0 sm:w-56"
              >
                {quickRetry.isPending ? RETRY.quickPending : RETRY.quick}
              </Button>
              <p id="retry-quick-hint" className="text-sm text-fg-muted sm:pt-2">
                {RETRY.quickHint}
              </p>
            </li>
          )}
          {/* Without this the page said evidence "remains available" and
              then offered no way to reach it, so the only route onward was
              to run the scan again. */}
          {data.page_count > 0 && (
            <li>
              <LinkButton to={`/scans/${data.id}/issues`} variant="secondary">
                Review what the scan found
              </LinkButton>
            </li>
          )}
        </ul>
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
                : "Finding and checking pages"}
            </h2>
          </div>
          <p className="mt-1 text-sm text-fg-muted">
            This panel updates by itself. It does not reload the page or move
            your place on it.
          </p>
          <p className="mt-1 text-xs text-fg-muted">
            Axcess can find more links as it scans, so the estimated time is a
            range, not a promise.
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
              if (confirm("Stop this scan? Axcess will not check the pages that are still waiting."))
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
          ? "Page checks finished. Preparing the report."
          : `${progress?.discovered ?? 0} pages found, ${progress?.completed ?? 0} checked, ${progress?.leased ?? 0} being checked now.`}
      </div>

      <div
        className="grid gap-px bg-border md:grid-cols-4"
        aria-labelledby="scan-progress-title"
      >
        <ProgressStage
          icon={<Search className="h-5 w-5" aria-hidden />}
          title="Find pages"
          status={isPreparing ? "complete" : "active"}
          detail={`${progress?.discovered ?? 0} found · ${progress?.pending ?? 0} waiting`}
        />
        <ProgressStage
          icon={<ShieldCheck className="h-5 w-5" aria-hidden />}
          title="Open and check pages"
          status={
            stage === "starting"
              ? "waiting"
              : isPreparing
                ? "complete"
                : "active"
          }
          detail={`${progress?.completed ?? 0} checked · ${progress?.leased ?? 0} in progress`}
        />
        <ProgressStage
          icon={<FileOutput className="h-5 w-5" aria-hidden />}
          title="Prepare report"
          status={isPreparing ? "active" : "waiting"}
          detail={
            isPreparing
              ? "Grouping occurrences into issues and adding fixes"
              : "Starts after all pages are checked"
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
            What Axcess is scanning now
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
                          Loading the page and running the checks you chose ·{" "}
                          {page.depth} click{page.depth === 1 ? "" : "s"} from
                          the start page
                          {page.attempts > 1
                            ? ` · try ${page.attempts}`
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
                  ? "All pages are checked. Axcess is putting the report together."
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
                Recently checked pages
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
            Checks you chose
          </h3>
          <p className="mt-1 text-xs text-fg-muted">
            Each row says what the check does and how much work it has
            finished.
          </p>
          <MethodCoverageList
            methods={enabledMethods}
            className="mt-3"
            compact
          />
          <p className="mt-2 text-xs text-fg-muted">
            Totals count only finished checks. A page in progress is counted
            after Axcess saves its results.
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
  not_selected: "Not chosen",
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
