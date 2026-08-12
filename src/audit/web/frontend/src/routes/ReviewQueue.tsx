import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, CheckCircle2, Filter, Search, ShieldCheck, Sparkles } from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type RefObject,
} from "react";
import { useParams, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { FindingStatus, IssueRow, ReviewLane } from "../api/types";
import ReportWorkspaceNav from "../components/ReportWorkspaceNav";
import { Button, Card, EmptyState, LinkButton, PageHeader } from "../components/ui";

const PIPELINE_LABEL: Record<string, string> = {
  axe: "axe-core",
  alfa: "Siteimprove Alfa",
  image: "Image analysis",
  semantic: "Semantic analysis",
  keyboard: "Keyboard probe",
  responsive: "Reflow & zoom probe",
  focus: "Focus probe",
  visual: "Visual review probe",
  protected_image: "Protected image analysis",
};

const LANE_META: Record<ReviewLane, { label: string; description: string }> = {
  likely_barrier: {
    label: "Likely barriers",
    description: "Deterministic failed outcomes ready for expert triage.",
  },
  expert_review: {
    label: "Needs confirmation",
    description: "Behavioral or AI-assisted evidence that needs an expert decision.",
  },
  informational: {
    label: "Informational",
    description: "Non-actionable evidence retained for transparency.",
  },
};

const STATUS_OPTIONS: FindingStatus[] = [
  "new",
  "reviewing",
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
];

const DECISIVE_STATUSES = new Set<FindingStatus>([
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
]);

/** Keyboard-first master/detail queue. The result lane prevents ambiguous
 * evidence from being reported as a barrier before an expert confirms it. */
export default function ReviewQueueRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const { data: scan, error: scanError } = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
  });
  const { data, isLoading, error } = useQuery({
    queryKey: ["issues", id, "review"],
    queryFn: () => api.listIssues(id),
    enabled: Number.isFinite(id),
  });

  const requestedLane = params.get("lane") as ReviewLane | null;
  const lane: ReviewLane =
    requestedLane && Object.hasOwn(LANE_META, requestedLane)
      ? requestedLane
      : (data?.review_lane_counts.likely_barrier ?? 0) > 0
        ? "likely_barrier"
        : (data?.review_lane_counts.expert_review ?? 0) > 0
          ? "expert_review"
          : "informational";
  const source = params.get("source") ?? "";
  const query = params.get("q") ?? "";
  const selectedKey = params.get("issue") ?? "";

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (data?.rows ?? []).filter(
      (row) =>
        row.review_lane === lane &&
        (!source || row.pipeline === source) &&
        (!needle ||
          row.title.toLowerCase().includes(needle) ||
          row.issue_key.toLowerCase().includes(needle) ||
          (row.wcag_sc ?? "").includes(needle)),
    );
  }, [data?.rows, lane, query, source]);
  const selected = rows.find((row) => row.issue_key === selectedKey) ?? rows[0] ?? null;
  const selectedIssueKey = selected?.issue_key ?? null;
  const sources = [...new Set((data?.rows ?? []).map((row) => row.pipeline))].sort();
  const optionRefs = useRef(new Map<string, HTMLButtonElement>());
  const previewHeadingRef = useRef<HTMLHeadingElement>(null);
  const previewFocusKey = useRef<string | null>(null);
  const [previewFocusRequest, setPreviewFocusRequest] = useState(0);
  const [selectionAnnouncement, setSelectionAnnouncement] = useState("");

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "issue") next.delete("issue");
    setParams(next, { replace: true });
  };

  const selectIssue = (row: IssueRow, focusPreview: boolean) => {
    setParam("issue", row.issue_key);
    setSelectionAnnouncement(`${row.title} selected. Details updated.`);
    if (focusPreview && window.matchMedia("(max-width: 1023px)").matches) {
      previewFocusKey.current = row.issue_key;
      setPreviewFocusRequest((request) => request + 1);
    }
  };

  const moveSelection = (
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    let nextIndex: number | null = null;
    if (event.key === "ArrowDown") nextIndex = (index + 1) % rows.length;
    if (event.key === "ArrowUp") nextIndex = (index - 1 + rows.length) % rows.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = rows.length - 1;
    if (nextIndex === null) return;

    event.preventDefault();
    const nextRow = rows[nextIndex];
    selectIssue(nextRow, false);
    window.requestAnimationFrame(() => optionRefs.current.get(nextRow.issue_key)?.focus());
  };

  useEffect(() => {
    if (
      previewFocusRequest === 0 ||
      !selectedIssueKey ||
      previewFocusKey.current !== selectedIssueKey
    ) {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      const heading = previewHeadingRef.current;
      previewFocusKey.current = null;
      if (!heading) return;
      heading.focus({ preventScroll: true });
      heading.scrollIntoView({ block: "start" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [previewFocusRequest, selectedIssueKey]);

  if (scanError || error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        Couldn&rsquo;t load this review queue. Existing report evidence is unchanged.
      </Card>
    );
  }
  if (!scan || !data || isLoading) return <div className="text-fg-muted">Loading review evidence…</div>;

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Reports", to: "/scans" },
          { label: `Report #${id}`, to: `/scans/${id}` },
          { label: "Review queue" },
        ]}
        title="Review queue"
        subtitle={`${data.review_lane_counts.likely_barrier} likely barrier groups · ${data.review_lane_counts.expert_review} expert-review leads · ${data.occurrence_counts.all_evidence.toLocaleString()} evidence occurrences`}
      />
      <ReportWorkspaceNav scanId={id} previousScanId={scan.previous_scan_id} />
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {selectionAnnouncement}
      </p>

      <section aria-labelledby="evidence-lanes-heading" className="mb-5">
        <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 id="evidence-lanes-heading" className="text-base font-semibold">Evidence decision lanes</h2>
            <p className="text-sm text-fg-muted">Only deterministic failed outcomes enter the likely-barrier lane. Every result still needs remediation verification.</p>
          </div>
          <p className="rounded-full bg-surface-muted px-3 py-1 text-xs font-semibold text-fg-muted">
            {data.occurrence_counts.high_confidence.toLocaleString()} high-confidence occurrences
          </p>
        </div>
        <div className="grid gap-2 sm:grid-cols-3" role="group" aria-label="Filter by evidence decision lane">
          {(Object.keys(LANE_META) as ReviewLane[]).map((key) => {
            const active = key === lane;
            return (
              <button
                key={key}
                type="button"
                aria-pressed={active}
                onClick={() => setParam("lane", key)}
                className={`min-h-target rounded-xs border p-3 text-left ${
                  active
                    ? "border-umich-blue bg-umich-blue text-white shadow-card"
                    : "border-border bg-surface text-fg hover:bg-surface-muted"
                }`}
              >
                <span className="flex items-baseline justify-between gap-2">
                  <strong>{LANE_META[key].label}</strong>
                  <span className="text-xl font-semibold tabular-nums">{data.review_lane_counts[key]}</span>
                </span>
                <span className={`mt-1 block text-xs ${active ? "text-white" : "text-fg-muted"}`}>
                  {LANE_META[key].description}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <Card className="mb-4 p-3">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem]">
          <label>
            <span className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
              <Search className="h-3.5 w-3.5" aria-hidden /> Search evidence
            </span>
            <input
              type="search"
              value={query}
              onChange={(event) => setParam("q", event.target.value)}
              placeholder="Issue, rule ID, or WCAG criterion"
              className="field"
            />
          </label>
          <label>
            <span className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
              <Filter className="h-3.5 w-3.5" aria-hidden /> Evidence source
            </span>
            <select value={source} onChange={(event) => setParam("source", event.target.value)} className="field">
              <option value="">All sources</option>
              {sources.map((item) => (
                <option key={item} value={item}>{PIPELINE_LABEL[item] ?? item}</option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      {rows.length === 0 ? (
        <EmptyState
          title={`No ${LANE_META[lane].label.toLowerCase()} match`}
          message="Clear the search or source filter, or choose another evidence lane."
        />
      ) : (
        <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(18rem,0.85fr)_minmax(24rem,1.35fr)]">
          <section aria-label={`${LANE_META[lane].label} list`} className="min-w-0">
            <p className="mb-2 text-sm text-fg-muted">{rows.length} group{rows.length === 1 ? "" : "s"} in this view</p>
            <ol
              className="space-y-2"
              role="listbox"
              aria-label={`${LANE_META[lane].label} groups`}
            >
              {rows.map((row, index) => (
                <li key={row.issue_key} role="none">
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected?.issue_key === row.issue_key}
                    tabIndex={selected?.issue_key === row.issue_key ? 0 : -1}
                    ref={(node) => {
                      if (node) optionRefs.current.set(row.issue_key, node);
                      else optionRefs.current.delete(row.issue_key);
                    }}
                    onClick={() => selectIssue(row, true)}
                    onKeyDown={(event) => moveSelection(event, index)}
                    className={`w-full min-w-0 rounded-xs border p-3 text-left transition-colors ${
                      selected?.issue_key === row.issue_key
                        ? "border-umich-blue bg-umich-blue/5 shadow-card"
                        : "border-border bg-surface hover:bg-surface-muted"
                    }`}
                  >
                    <span className="flex min-w-0 items-start justify-between gap-3">
                      <span className="min-w-0">
                        <strong className="block break-words text-sm text-fg">{row.title}</strong>
                        <span className="mt-1 block text-xs text-fg-muted">
                          {PIPELINE_LABEL[row.pipeline] ?? row.pipeline}
                          {row.wcag_sc ? ` · WCAG ${row.wcag_sc} ${row.conformance}` : " · no criterion claim"}
                        </span>
                      </span>
                      <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-umich-blue" aria-hidden />
                    </span>
                    <span className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-fg-muted">
                      <span><strong className="text-fg">{row.page_count}</strong> pages</span>
                      <span><strong className="text-fg">{row.occurrence_count}</strong> occurrences</span>
                      <span className="capitalize"><strong className="text-fg">{row.evidence_confidence}</strong> confidence</span>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </section>
          {selected && (
            <IssuePreview
              scanId={id}
              issue={selected}
              headingRef={previewHeadingRef}
            />
          )}
        </div>
      )}
    </>
  );
}

function IssuePreview({
  scanId,
  issue,
  headingRef,
}: {
  scanId: number;
  issue: IssueRow;
  headingRef: RefObject<HTMLHeadingElement | null>;
}) {
  const qc = useQueryClient();
  const isInformational = issue.review_lane === "informational";
  const statuses = Object.entries(issue.status_summary).filter(([, count]) => count > 0);
  const singleStatus = statuses.length === 1 ? (statuses[0][0] as FindingStatus) : "";
  const [nextStatus, setNextStatus] = useState<FindingStatus | "">(singleStatus);
  const [rationale, setRationale] = useState("");
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    setNextStatus(singleStatus);
    setRationale("");
  }, [issue.issue_key, singleStatus]);

  const rationaleRequired = !!nextStatus && DECISIVE_STATUSES.has(nextStatus);

  const update = useMutation({
    mutationFn: async ({ status, reason }: { status: FindingStatus; reason: string }) => {
      if (DECISIVE_STATUSES.has(status) &&
          !window.confirm(`Apply the documented ${status.replace(/_/g, " ")} decision to all ${issue.finding_ids.length} findings in this group?`)) {
        throw new Error("Update cancelled");
      }
      return issue.pipeline === "image"
        ? api.bulkSetStatus(issue.finding_ids, status, reason || undefined)
        : api.bulkSetA11yStatus(issue.finding_ids, status, reason || undefined);
    },
    onSuccess: (result) => {
      setAnnouncement(`${result.updated} findings updated.`);
      setRationale("");
      void qc.invalidateQueries({ queryKey: ["issues", scanId] });
    },
    onError: (mutationError) => {
      if (mutationError instanceof Error && mutationError.message === "Update cancelled") return;
      setAnnouncement("Status was not updated. Review the error and try again.");
    },
  });

  const Icon = issue.review_lane === "likely_barrier" ? ShieldCheck : issue.review_lane === "expert_review" ? Sparkles : CheckCircle2;

  return (
    <section aria-labelledby="selected-issue-heading" className="min-w-0 self-start scroll-mt-4 lg:sticky lg:top-4">
      <Card className="overflow-hidden">
        <div className="border-b border-border bg-surface-muted p-4">
          <div className="flex items-start gap-3">
            <span className="rounded-full bg-umich-blue/10 p-2 text-umich-blue"><Icon className="h-5 w-5" aria-hidden /></span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">{LANE_META[issue.review_lane].label}</p>
              <h2
                ref={headingRef}
                id="selected-issue-heading"
                tabIndex={-1}
                className="mt-1 scroll-mt-4 break-words text-lg font-semibold text-fg"
              >
                {issue.title}
              </h2>
              <p className="mt-1 text-sm text-fg-muted">{issue.evidence_summary}</p>
            </div>
          </div>
        </div>
        <div className="space-y-4 p-4">
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <Metric label="Source" value={PIPELINE_LABEL[issue.pipeline] ?? issue.pipeline} />
            <Metric label="Confidence" value={issue.evidence_confidence} />
            <Metric label="Pages" value={String(issue.page_count)} />
            <Metric label="Occurrences" value={String(issue.occurrence_count)} />
          </dl>

          {isInformational ? (
            <div className="rounded-xs border border-umich-blue/20 bg-umich-blue/5 p-3" role="note">
              <h3 className="text-sm font-semibold">No barrier detected by this check</h3>
              <p className="mt-1 text-sm text-fg-muted">
                This read-only evidence is retained for transparency. It does not need a
                remediation status unless a separate expert review finds contradictory context.
              </p>
              {issue.description && (
                <p className="mt-2 text-sm text-fg-muted">{issue.description}</p>
              )}
            </div>
          ) : (
            <>
              {issue.description && (
                <div>
                  <h3 className="text-sm font-semibold">What was detected</h3>
                  <p className="mt-1 text-sm leading-relaxed text-fg-muted">{issue.description}</p>
                </div>
              )}
              {issue.why_matters && (
                <div>
                  <h3 className="text-sm font-semibold">Why it matters</h3>
                  <p className="mt-1 text-sm leading-relaxed text-fg-muted">{issue.why_matters}</p>
                </div>
              )}
              {issue.fix_steps.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold">Recommended next step</h3>
                  <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm text-fg-muted">
                    {issue.fix_steps.slice(0, 3).map((step, index) => <li key={index}>{stripMarkup(step)}</li>)}
                  </ol>
                </div>
              )}

              <div className="rounded-xs border border-border bg-surface-subtle p-3">
                <h3 className="text-sm font-semibold">{issue.review_lane === "expert_review" ? "Record the expert decision" : "Triage this group"}</h3>
                <p className="mt-1 text-xs text-fg-muted">
                  {statuses.map(([status, count]) => `${count} ${status.replace(/_/g, " ")}`).join(" · ") || "No status recorded"}
                </p>
                {issue.finding_ids.length <= 500 ? (
                  <div className="mt-2 space-y-2">
                    <div className="flex flex-wrap gap-2">
                      <label className="min-w-52 flex-1">
                        <span className="sr-only">New status for {issue.title}</span>
                        <select value={nextStatus} onChange={(event) => setNextStatus(event.target.value as FindingStatus)} className="field">
                          <option value="">Choose a group decision…</option>
                          {STATUS_OPTIONS.map((status) => <option key={status} value={status}>{statusLabel(issue.review_lane, status)}</option>)}
                        </select>
                      </label>
                      <Button
                        type="button"
                        disabled={!nextStatus || nextStatus === singleStatus || (rationaleRequired && !rationale.trim()) || update.isPending}
                        onClick={() => nextStatus && update.mutate({ status: nextStatus, reason: rationale.trim() })}
                      >
                        {update.isPending ? "Saving…" : "Apply decision"}
                      </Button>
                    </div>
                    {rationaleRequired && (
                      <label className="block">
                        <span className="mb-1 block text-xs font-semibold text-fg">Decision rationale (required)</span>
                        <textarea
                          value={rationale}
                          onChange={(event) => setRationale(event.target.value)}
                          className="field min-h-20"
                          placeholder="What evidence did you review, what did you conclude, and why?"
                        />
                        <span className="mt-1 block text-xs text-fg-muted">Stored with the reviewer, timestamp, prior status, and new status for auditability.</span>
                      </label>
                    )}
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-fg-muted">This group has more than 500 findings. Open the evidence view to triage a bounded selection.</p>
                )}
                <p className="mt-2 text-xs text-fg-muted" aria-live="polite">{announcement}</p>
              </div>
            </>
          )}

          <LinkButton to={`/scans/${scanId}/issues/${encodeURIComponent(issue.issue_key)}`} variant="primary" className="w-full sm:w-auto">
            {isInformational ? "View supporting evidence" : "Review pages and evidence"} <ArrowRight className="h-4 w-4" aria-hidden />
          </LinkButton>
        </div>
      </Card>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">{label}</dt>
      <dd className="mt-0.5 break-words font-semibold capitalize text-fg">{value}</dd>
    </div>
  );
}

function statusLabel(lane: ReviewLane, status: FindingStatus): string {
  if (lane !== "expert_review") return status.replace(/_/g, " ");
  const labels: Record<FindingStatus, string> = {
    new: "Not reviewed",
    reviewing: "Needs follow-up",
    in_progress: "Barrier confirmed — remediation planned",
    remediated: "Barrier confirmed — remediated",
    accepted_risk: "Barrier confirmed — risk accepted",
    false_positive: "Reviewed — not a barrier",
  };
  return labels[status];
}

function stripMarkup(value: string): string {
  return value.replace(/<[^>]+>/g, "");
}
