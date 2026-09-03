import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  Accessibility,
  AlertOctagon,
  CheckCircle2,
  Clock3,
  FileOutput,
  GitCompare,
  ListFilter,
  Loader2,
  Pause,
  Play,
  Search,
  ShieldCheck,
  Square,
  Trash2,
} from "lucide-react";
import { api } from "../api/client";
import type {
  ScanDetail,
  ScanMethodCoverage,
  ScanMethodState,
  ScanProgress,
} from "../api/types";
import ReportWorkspaceNav from "../components/ReportWorkspaceNav";
import {
  Button,
  Card,
  LinkButton,
  PageHeader,
  StatCard,
} from "../components/ui";
import { httpStatusLabel, renderModeLabel } from "../lib/pageLabels";
import { formatScanEta } from "../lib/scanProgress";

export default function ScanDetailRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [liveUpdates, setLiveUpdates] = useState(true);

  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
    refetchInterval: (query) =>
      liveUpdates && query.state.data?.status === "running" ? 2000 : false,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
  });
  const cancel = useMutation({
    mutationFn: () => api.cancelScan(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scan", id] }),
  });
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
      }),
    onSuccess: async ({ scan_id }) => {
      setLiveUpdates(true);
      qc.removeQueries({ queryKey: ["issues", id] });
      await qc.invalidateQueries({ queryKey: ["scan", id] });
      await qc.invalidateQueries({ queryKey: ["scans"] });
      if (scan_id !== id) navigate(`/scans/${scan_id}`, { replace: true });
    },
  });
  const { data: issueSummary } = useQuery({
    queryKey: ["issues", id, "workspace-summary"],
    queryFn: () => api.listIssues(id),
    enabled: Number.isFinite(id) && data?.status === "completed",
  });
  const deleteScan = useMutation({
    mutationFn: () => api.deleteScan(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["scans"] });
      qc.removeQueries({ queryKey: ["scan", id] });
      navigate("/scans", { replace: true });
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
        <PageHeader
          crumbs={[
            { label: "Scans", to: "/scans" },
            { label: `Scan #${data.id}` },
          ]}
          title="Scan in progress"
          subtitle={data.seed_url}
        />
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

  const isComplete = data.status === "completed";
  const issueOccurrences = issueSummary?.occurrence_counts.all_evidence ?? 0;
  const issueGroups = issueSummary?.rows.length ?? 0;
  const likelyBarrierGroups =
    issueSummary?.review_lane_counts.likely_barrier ?? 0;
  const expertReviewGroups =
    issueSummary?.review_lane_counts.expert_review ?? 0;
  const reviewedBackingFindings =
    issueSummary?.rows
      .filter((issue) => issue.review_lane !== "informational")
      .reduce(
        (total, issue) =>
          total +
          (issue.status_summary.in_progress ?? 0) +
          (issue.status_summary.remediated ?? 0) +
          (issue.status_summary.accepted_risk ?? 0) +
          (issue.status_summary.false_positive ?? 0),
        0,
      ) ?? 0;
  const rejectedBackingFindings =
    issueSummary?.rows
      .filter((issue) => issue.review_lane !== "informational")
      .reduce(
        (total, issue) => total + (issue.status_summary.false_positive ?? 0),
        0,
      ) ?? 0;
  const observedRejectionRate = reviewedBackingFindings
    ? (rejectedBackingFindings / reviewedBackingFindings) * 100
    : null;

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Reports", to: "/scans" },
          { label: `Report #${data.id}` },
        ]}
        title={isComplete ? `Report #${data.id}` : `Scan #${data.id}`}
        subtitle={data.seed_url}
        actions={
          isComplete ? (
            <>
              <LinkButton
                to={`/scans/${data.id}/issues`}
                variant="primary"
                size="lg"
              >
                <ListFilter className="h-5 w-5" aria-hidden />
                Open issue table
              </LinkButton>
              {data.previous_scan_id != null && (
                <LinkButton
                  to={`/scans/${data.id}/diff?compare_to=${data.previous_scan_id}`}
                  variant="secondary"
                >
                  <GitCompare className="h-4 w-4" aria-hidden />
                  Compare
                </LinkButton>
              )}
            </>
          ) : undefined
        }
      />

      {deleteScan.error && (
        <Card
          className="mb-4 border-sev-critical/40 bg-sev-critical-bg p-3 text-sm text-sev-critical"
          role="alert"
        >
          Couldn&rsquo;t delete scan:{" "}
          {deleteScan.error instanceof Error
            ? deleteScan.error.message
            : String(deleteScan.error)}
        </Card>
      )}

      {data.blocked && (
        <BlockedScanNotice scanId={data.id} blocked={data.blocked} />
      )}

      {!isComplete ? (
        <Card className="p-5">
          <h2 className="font-semibold text-fg">No report was produced</h2>
          <p className="mt-1 text-sm text-fg-muted">
            {data.page_count > 0 ? (
              <>
                This scan ended as <strong>{data.status}</strong> after completing{" "}
                {data.page_count.toLocaleString()} page
                {data.page_count === 1 ? "" : "s"}. Partial evidence remains
                available, but it is not a completed report.
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
          </div>
        </Card>
      ) : (
        <>
          <Card className="mb-5 overflow-hidden border-umich-blue/30">
            <div className="flex flex-col gap-4 bg-umich-blue/5 p-5 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex gap-3">
                <CheckCircle2
                  className="mt-0.5 h-6 w-6 shrink-0 text-umich-blue"
                  aria-hidden
                />
                <div>
                  <h2 className="text-lg font-semibold text-fg">
                    Automated evidence is ready
                  </h2>
                  <p className="mt-1 text-sm text-fg-muted">
                    {issueSummary
                      ? `${issueGroups.toLocaleString()} issue groups / ${issueOccurrences.toLocaleString()} detected occurrences.`
                      : "Organizing issue groups and report evidence…"}
                  </p>
                  <p className="mt-1 text-xs text-fg-muted">
                    This is evidence for expert review, not an automated
                    conformance verdict.
                  </p>
                </div>
              </div>
              <LinkButton to={`/scans/${data.id}/issues`} variant="primary">
                <ListFilter className="h-4 w-4" aria-hidden />
                View all issues
              </LinkButton>
            </div>
            <dl className="grid gap-px bg-border sm:grid-cols-3">
              <ReportMetric
                label="Likely barriers"
                value={
                  issueSummary ? likelyBarrierGroups.toLocaleString() : "—"
                }
                note="High-confidence issue groups"
              />
              <ReportMetric
                label="Review leads"
                value={issueSummary ? expertReviewGroups.toLocaleString() : "—"}
                note="Expert decision required"
              />
              <ReportMetric
                label="Pages tested"
                value={data.page_count.toLocaleString()}
                note={`${data.error_count.toLocaleString()} crawl errors`}
              />
            </dl>
          </Card>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <StatCard label="Pages crawled" value={data.page_count} />
            {/* Pages alone understate an application whose content mostly
                does not exist until a control is used. This counts the
                states reached by opening menus, dialogs, and tabs. */}
            <StatCard
              label="DOM states discovered"
              value={(data.dom_state_count ?? 0).toLocaleString()}
              hint="reached by operating controls"
            />
            <StatCard
              label="Crawl errors"
              value={data.error_count}
              tone={data.error_count ? "major" : "default"}
            />
            <StatCard
              label="Likely barriers"
              value={likelyBarrierGroups}
              hint="issue groups"
            />
            <StatCard
              label="Review leads"
              value={expertReviewGroups}
              hint="expert decision needed"
            />
            <StatCard
              label="Occurrences"
              value={issueSummary ? issueOccurrences.toLocaleString() : "—"}
              hint="not a conformance score"
            />
          </div>

          <Card className="mt-5 p-5">
            <h2 className="flex items-center gap-2 font-semibold text-fg">
              <ShieldCheck className="h-5 w-5 text-umich-blue" aria-hidden />
              What Axcess checked
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-fg-muted">
              “Selected” only means a method was requested. The status and count
              below show whether it actually completed work for this report.
            </p>
            <MethodCoverageList methods={data.methods_used} className="mt-4" />
          </Card>

          <Card className="mt-5 p-5">
            <h2 className="flex items-center gap-2 font-semibold text-fg">
              <ListFilter className="h-5 w-5 text-umich-blue" aria-hidden />
              Issue table
            </h2>
            <p className="mt-1 text-sm text-fg-muted">
              See what the issue is, why it matters, the expected fix, and exact
              page locations in one table.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <LinkButton to={`/scans/${data.id}/issues`} variant="primary">
                Open accessibility issue table
              </LinkButton>
            </div>
          </Card>

          <details className="mt-5 rounded-xs border border-border bg-surface p-4 shadow-card">
            <summary className="min-h-target cursor-pointer py-2 font-semibold text-fg">
              Expert tools and scan details
            </summary>
            <div className="border-t border-border pt-4">
              <ReportWorkspaceNav
                scanId={data.id}
                previousScanId={data.previous_scan_id}
              />
              <div className="flex flex-wrap gap-2">
                <LinkButton to={`/scans/${data.id}/a11y`} variant="secondary">
                  <Accessibility className="h-4 w-4" aria-hidden /> DOM engines
                </LinkButton>
                <LinkButton
                  to={`/scans/${data.id}/findings`}
                  variant="secondary"
                >
                  Image evidence ({data.finding_count})
                </LinkButton>
              </div>
              <p className="mt-4 text-sm text-fg-muted">
                Observed reviewer rejection rate:{" "}
                <strong>
                  {observedRejectionRate == null
                    ? "not measured yet"
                    : `${observedRejectionRate.toFixed(1)}%`}
                </strong>
                {observedRejectionRate != null &&
                  ` (${rejectedBackingFindings} of ${reviewedBackingFindings} reviewed findings marked false positive)`}
                . This is a result from this report, not a general
                detector-accuracy claim.
              </p>
              <details className="mt-4 border-t border-border pt-3">
                <summary className="min-h-target cursor-pointer py-2 text-sm font-semibold text-sev-critical">
                  Danger zone
                </summary>
                <p className="text-sm text-fg-muted">
                  Deleting removes this scan and its report evidence. Shared
                  image blobs may remain.
                </p>
                <Button
                  variant="ghost"
                  disabled={deleteScan.isPending}
                  className="mt-2 text-sev-critical hover:bg-sev-critical-bg"
                  onClick={() => {
                    const ok = window.confirm(
                      `Delete scan #${data.id} (${data.seed_url})?\n\nThis permanently removes the scan, its pages, findings, and history. This cannot be undone.`,
                    );
                    if (ok) deleteScan.mutate();
                  }}
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                  {deleteScan.isPending ? "Deleting…" : "Delete report"}
                </Button>
              </details>
            </div>
          </details>
        </>
      )}
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
            range—not a fixed deadline.
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
            Each row explains the method and reports completed work—not merely
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
        <span className="ml-auto text-2xs font-semibold uppercase tracking-wide text-fg-muted">
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

function ReportMetric({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="bg-surface p-4">
      <dt className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">
        {label}
      </dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums text-umich-blue">
        {value}
      </dd>
      <dd className="text-xs text-fg-muted">{note}</dd>
    </div>
  );
}

function BlockedScanNotice({
  scanId,
  blocked,
}: {
  scanId: number;
  blocked: NonNullable<ScanDetail["blocked"]>;
}) {
  return (
    <Card className="mb-4 border-sev-critical/40 bg-sev-critical-bg p-4">
      <div className="flex items-start gap-3">
        <AlertOctagon
          className="mt-0.5 h-5 w-5 text-sev-critical"
          aria-hidden
        />
        <div className="text-sm">
          <strong className="text-sev-critical">
            Seed URL returned HTTP {blocked.status_code}
          </strong>
          {blocked.title && <> — &ldquo;{blocked.title}&rdquo;</>}. The crawler
          could not read past the entry page. Try a{" "}
          <Link to="/scans/new">new public scan</Link>, or use an authorized
          sign-in scan when the site requires authentication.
          <span className="sr-only"> Report {scanId} is incomplete.</span>
        </div>
      </div>
    </Card>
  );
}
