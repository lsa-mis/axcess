import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Check, Download, FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { api, exportUrl } from "../api/client";
import ReportWorkspaceNav from "../components/ReportWorkspaceNav";
import { Card, DownloadLink, PageHeader } from "../components/ui";

export default function HandoffRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [draftAcknowledged, setDraftAcknowledged] = useState(false);
  const scanQuery = useQuery({ queryKey: ["scan", id], queryFn: () => api.getScan(id), enabled: Number.isFinite(id) });
  const evaluationQuery = useQuery({ queryKey: ["evaluation", id], queryFn: () => api.getEvaluation(id), enabled: Number.isFinite(id) });
  const checksQuery = useQuery({ queryKey: ["manual-checks", id], queryFn: () => api.getManualChecks(id), enabled: Number.isFinite(id) });
  const issuesQuery = useQuery({ queryKey: ["issues", id, "handoff"], queryFn: () => api.listIssues(id), enabled: Number.isFinite(id) });
  const error = scanQuery.error || evaluationQuery.error || checksQuery.error || issuesQuery.error;
  if (error) return <Card className="p-4 text-sm text-sev-critical" role="alert">Couldn&rsquo;t prepare the handoff. The stored report evidence is unchanged.</Card>;
  if (!scanQuery.data || !evaluationQuery.data || !checksQuery.data || !issuesQuery.data) return <div className="text-fg-muted">Checking handoff readiness…</div>;

  const scan = scanQuery.data;
  const evaluation = evaluationQuery.data;
  const checks = checksQuery.data.checks;
  const notStarted = checks.filter((check) => check.outcome === "not_started").length;
  const needsFollowUp = checks.filter((check) => check.outcome === "needs_follow_up").length;
  const notTested = checks.filter((check) => check.outcome === "not_tested").length;
  const missingRationale = checks.filter(
    (check) => check.outcome !== "not_started" && !check.rationale.trim(),
  ).length;
  const unreviewedActionableGroups = issuesQuery.data.rows.filter((issue) => {
    if (issue.review_lane === "informational") return false;
    const dispositioned =
      (issue.status_summary.in_progress ?? 0) +
      (issue.status_summary.remediated ?? 0) +
      (issue.status_summary.accepted_risk ?? 0) +
      (issue.status_summary.false_positive ?? 0);
    return dispositioned < issue.finding_ids.length;
  }).length;
  const preflight = [
    { label: "Reviewer identified", ready: !!evaluation.reviewer.trim(), to: `/scans/${id}/manual-checks` },
    { label: "Purpose and included scope documented", ready: !!evaluation.purpose.trim() && !!evaluation.scope_included.trim(), to: `/scans/${id}/manual-checks` },
    { label: "Methods documented", ready: !!evaluation.methods_note.trim(), to: `/scans/${id}/manual-checks` },
    { label: "Limitations documented", ready: !!evaluation.limitations.trim(), to: `/scans/${id}/manual-checks` },
    {
      label: "Every manual criterion has a final decision",
      ready: notStarted === 0 && needsFollowUp === 0,
      detail: notStarted || needsFollowUp ? `${notStarted} not started · ${needsFollowUp} follow-up` : undefined,
      to: `/scans/${id}/manual-checks`,
    },
    {
      label: "Every recorded decision has a rationale",
      ready: missingRationale === 0,
      detail: missingRationale ? `${missingRationale} missing rationale` : undefined,
      to: `/scans/${id}/manual-checks`,
    },
    {
      label: "Not-tested outcomes are documented as limitations",
      ready: notTested === 0 || (!!evaluation.limitations.trim() && missingRationale === 0),
      detail: notTested ? `${notTested} criterion${notTested === 1 ? "" : "s"} not tested` : "No not-tested outcomes",
      to: `/scans/${id}/manual-checks`,
    },
    {
      label: "Every actionable evidence group has an expert disposition",
      ready: unreviewedActionableGroups === 0,
      detail: unreviewedActionableGroups ? `${unreviewedActionableGroups} group${unreviewedActionableGroups === 1 ? "" : "s"} unreviewed` : undefined,
      to: `/scans/${id}/review`,
    },
    { label: "Evaluation marked completed", ready: evaluation.status === "completed", to: `/scans/${id}/manual-checks` },
  ];
  const ready = preflight.every((item) => item.ready);
  const downloadsEnabled = ready || draftAcknowledged;
  const downloadHref = (format: string) =>
    exportUrl(id, format, !ready && draftAcknowledged);

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Reports", to: "/scans" }, { label: `Report #${id}`, to: `/scans/${id}` }, { label: "Handoff" }]}
        title="Handoff"
        subtitle="Prepare an evidence-grounded remediation package for a U-M unit or vendor."
      />
      <ReportWorkspaceNav scanId={id} previousScanId={scan.previous_scan_id} />

      <Card className={`mb-5 overflow-hidden ${ready ? "border-umich-blue/30" : "border-sev-major/40"}`}>
        <div className={`flex items-start gap-3 p-4 ${ready ? "bg-umich-blue/5" : "bg-sev-major-bg"}`}>
          {ready ? <Check className="mt-0.5 h-5 w-5 text-umich-blue" aria-hidden /> : <AlertTriangle className="mt-0.5 h-5 w-5 text-sev-major" aria-hidden />}
          <div>
            <h2 className="font-semibold">{ready ? "Report is ready for handoff" : "Draft report — finish the expert record before sharing"}</h2>
            <p className="mt-1 text-sm text-fg-muted">Exports describe evidence and recommendations; they do not certify conformance.</p>
          </div>
        </div>
        <ul className="grid gap-px bg-border sm:grid-cols-2 lg:grid-cols-3">
          {preflight.map((item) => (
            <li key={item.label} className="flex items-start gap-2 bg-surface p-3 text-sm">
              <span aria-hidden className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${item.ready ? "border-umich-blue bg-umich-blue text-white" : "border-sev-major text-sev-major"}`}>{item.ready ? "✓" : "!"}</span>
              <span>
                <span className={`block text-xs font-semibold uppercase tracking-wide ${item.ready ? "text-umich-blue" : "text-sev-major"}`}>
                  {item.ready ? "Complete" : "Missing"}
                </span>
                <strong className="block">{item.label}</strong>
                {item.detail && <span className="block text-xs text-fg-muted">{item.detail}</span>}
                {!item.ready && <Link className="mt-1 inline-block text-xs" to={item.to}>Resolve this item</Link>}
              </span>
            </li>
          ))}
        </ul>
        {!ready && (
          <div className="flex min-h-target items-start gap-3 border-t border-border p-4 text-sm">
            <input id="draft-export-acknowledgement" type="checkbox" checked={draftAcknowledged} onChange={(event) => setDraftAcknowledged(event.target.checked)} aria-describedby="draft-export-description" className="mt-1 h-5 w-5" />
            <div>
              <label htmlFor="draft-export-acknowledgement" className="cursor-pointer font-semibold">Download an incomplete draft anyway</label>
              <p id="draft-export-description" className="text-fg-muted">I understand the evaluation status and missing context will be visible, and this draft is not ready for stakeholder reliance.</p>
            </div>
          </div>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <ExportCard
          title="Operational workbook"
          description={`Owner worklists, page hotspots, source layers, clickable evidence links, and Test Tracking. ${issuesQuery.data.review_lane_counts.expert_review} expert-review groups remain clearly separated.`}
          href={downloadHref("xlsx")}
          enabled={downloadsEnabled}
          icon={<FileSpreadsheet className="h-5 w-5" aria-hidden />}
          label="Download Excel workbook"
        />
        <ExportCard
          title="Stakeholder audit report"
          description="Executive summary, evaluation context, scope, process, results, recommended actions, limitations, and appendices."
          href={downloadHref("audit")}
          enabled={downloadsEnabled}
          icon={<FileText className="h-5 w-5" aria-hidden />}
          label="Download audit report"
        />
        <Card className="p-4 lg:col-span-2">
          <h2 className="mb-2 font-semibold">Evaluation record</h2>
          <dl className="grid gap-3 text-sm md:grid-cols-3">
            <div><dt className="font-semibold text-fg-muted">Target</dt><dd>{evaluation.target_standard} {evaluation.target_level}</dd></div>
            <div><dt className="font-semibold text-fg-muted">Review status</dt><dd className="capitalize">{evaluation.status.replace("_", " ")}</dd></div>
            <div><dt className="font-semibold text-fg-muted">Evidence lanes</dt><dd>{issuesQuery.data.review_lane_counts.likely_barrier} likely barriers · {issuesQuery.data.review_lane_counts.expert_review} leads</dd></div>
            <div className="md:col-span-3"><dt className="font-semibold text-fg-muted">Limitations</dt><dd>{evaluation.limitations || "No expert limitations recorded yet."}</dd></div>
          </dl>
          <details className="mt-4 border-t border-border pt-3">
            <summary className="cursor-pointer text-sm font-semibold text-umich-blue">Additional structured formats</summary>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {["csv", "json", "jira", "markdown"].map((format) => downloadsEnabled ? (
                <DownloadLink key={format} href={downloadHref(format)} variant="secondary"><Download className="h-4 w-4" aria-hidden /> {format.toUpperCase()}</DownloadLink>
              ) : (
                <button key={format} type="button" disabled className="inline-flex min-h-target cursor-not-allowed items-center justify-center rounded-xs border border-border bg-surface-muted px-4 py-2.5 text-sm font-semibold text-fg-subtle">{format.toUpperCase()} draft locked</button>
              ))}
            </div>
          </details>
        </Card>
      </div>
    </>
  );
}

function ExportCard({ title, description, href, enabled, icon, label }: { title: string; description: string; href: string; enabled: boolean; icon: React.ReactNode; label: string }) {
  return (
    <Card className="p-4">
      <h2 className="mb-2 flex items-center gap-2 font-semibold">{icon}{title}</h2>
      <p className="mb-3 text-sm text-fg-muted">{description}</p>
      {enabled ? (
        <DownloadLink href={href} variant="primary"><Download className="h-4 w-4" aria-hidden /> {label}</DownloadLink>
      ) : (
        <button type="button" disabled className="inline-flex min-h-target cursor-not-allowed items-center rounded-xs bg-surface-muted px-4 py-2.5 text-sm font-semibold text-fg-subtle">Complete preflight or acknowledge draft</button>
      )}
    </Card>
  );
}
