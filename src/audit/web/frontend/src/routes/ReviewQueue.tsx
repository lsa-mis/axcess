import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import ReportWorkspaceNav from "../components/ReportWorkspaceNav";
import { Card, EmptyState, PageHeader, StatusChip } from "../components/ui";

/** Dense, grouped queue for expert triage. Issue detail remains the evidence view. */
export default function ReviewQueueRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
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

  if (scanError || error) {
    return <Card className="p-4 text-sm text-sev-critical" role="alert">Couldn’t load this review queue.</Card>;
  }
  if (!scan || !data || isLoading) return <div className="text-fg-muted">Loading…</div>;

  return (
    <>
      <PageHeader
        crumbs={[{ label: "Reports", to: "/scans" }, { label: `Report #${id}`, to: `/scans/${id}` }, { label: "Review queue" }]}
        title="Review queue"
        subtitle={`${data.total_unfiltered} issue groups, ordered by priority and reach.`}
      />
      <ReportWorkspaceNav scanId={id} previousScanId={scan.previous_scan_id} />
      <Card className="mb-4 border-umich-blue/20 bg-umich-blue/5 p-4 text-sm text-fg-muted">
        Review grouped issues first, then open the evidence page to make a human decision. AI-assisted findings are leads that need confirmation before broad remediation.
      </Card>
      {data.rows.length === 0 ? (
        <EmptyState title="No issue groups" message="This completed report has no grouped findings." />
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Prioritized accessibility issue groups</caption>
            <thead className="bg-surface-muted text-left text-2xs uppercase tracking-wide text-fg-subtle">
              <tr>
                <th scope="col" className="px-4 py-2">Issue</th>
                <th scope="col" className="px-4 py-2">Evidence</th>
                <th scope="col" className="px-4 py-2 text-right">Pages</th>
                <th scope="col" className="px-4 py-2 text-right">Occurrences</th>
                <th scope="col" className="px-4 py-2">Owner</th>
                <th scope="col" className="px-4 py-2">Triage</th>
                <th scope="col" className="px-4 py-2 text-right">Priority</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.rows.map((issue) => {
                const status = Object.entries(issue.status_summary).find(([, count]) => count > 0)?.[0] ?? "new";
                return (
                  <tr key={issue.issue_key} className="align-top hover:bg-surface-muted/60">
                    <th scope="row" className="min-w-72 px-4 py-3 text-left font-semibold">
                      <Link className="text-umich-blue underline underline-offset-2" to={`/scans/${id}/issues/${encodeURIComponent(issue.issue_key)}`}>
                        {issue.title}
                      </Link>
                      <span className="mt-1 block text-xs font-normal text-fg-muted">
                        {issue.wcag_sc ? `WCAG ${issue.wcag_sc} · ${issue.conformance}` : "Best practice"}
                      </span>
                    </th>
                    <td className="px-4 py-3 text-xs text-fg-muted">
                      <strong className="font-semibold text-fg">{issue.pipeline}</strong>
                      <span className="block">{issue.pipeline === "image" ? "AI-assisted — confirm" : "Observed by audit"}</span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{issue.page_count.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{issue.occurrence_count.toLocaleString()}</td>
                    <td className="px-4 py-3 capitalize">{issue.responsibility}</td>
                    <td className="px-4 py-3"><StatusChip value={status as "new"} /></td>
                    <td className="px-4 py-3 text-right font-semibold tabular-nums">{issue.priority.toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
