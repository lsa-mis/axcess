import { useQuery } from "@tanstack/react-query";
import { Download, FileSpreadsheet, FileText } from "lucide-react";
import { useParams } from "react-router-dom";
import { api, exportUrl } from "../api/client";
import ReportWorkspaceNav from "../components/ReportWorkspaceNav";
import { Card, DownloadLink, PageHeader } from "../components/ui";

export default function HandoffRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const { data: scan } = useQuery({ queryKey: ["scan", id], queryFn: () => api.getScan(id), enabled: Number.isFinite(id) });
  const { data: evaluation } = useQuery({ queryKey: ["evaluation", id], queryFn: () => api.getEvaluation(id), enabled: Number.isFinite(id) });
  if (!scan || !evaluation) return <div className="text-fg-muted">Loading…</div>;
  return (
    <>
      <PageHeader crumbs={[{ label: "Reports", to: "/scans" }, { label: `Report #${id}`, to: `/scans/${id}` }, { label: "Handoff" }]} title="Handoff" subtitle="Prepare an evidence-grounded remediation package for a unit or vendor." />
      <ReportWorkspaceNav scanId={id} previousScanId={scan.previous_scan_id} />
      <Card className="mb-5 border-umich-blue/20 bg-umich-blue/5 p-4">
        <h2 className="text-sm font-semibold">Before sharing</h2>
        <p className="mt-1 text-sm text-fg-muted">Confirm the report scope, methods, limitations, and manual outcomes. Exports describe evidence and recommendations; they do not certify conformance.</p>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-4"><h2 className="mb-2 flex items-center gap-2 font-semibold"><FileSpreadsheet className="h-5 w-5" aria-hidden /> Operational workbook</h2><p className="mb-3 text-sm text-fg-muted">Use the Excel workbook for owner worklists, page hotspots, coverage, and Test Tracking.</p><DownloadLink href={exportUrl(id, "xlsx")} variant="primary"><Download className="h-4 w-4" aria-hidden /> Download Excel workbook</DownloadLink></Card>
        <Card className="p-4"><h2 className="mb-2 flex items-center gap-2 font-semibold"><FileText className="h-5 w-5" aria-hidden /> Stakeholder report</h2><p className="mb-3 text-sm text-fg-muted">Use the audit report for executive summary, scope, methods, limitations, recommendations, and evidence references.</p><DownloadLink href={exportUrl(id, "audit")} variant="primary"><Download className="h-4 w-4" aria-hidden /> Download audit report</DownloadLink></Card>
        <Card className="p-4 lg:col-span-2"><h2 className="mb-2 font-semibold">Evaluation record</h2><dl className="grid gap-3 text-sm md:grid-cols-2"><div><dt className="font-semibold text-fg-muted">Target</dt><dd>{evaluation.target_standard} {evaluation.target_level}</dd></div><div><dt className="font-semibold text-fg-muted">Review status</dt><dd className="capitalize">{evaluation.status.replace("_", " ")}</dd></div><div className="md:col-span-2"><dt className="font-semibold text-fg-muted">Limitations</dt><dd>{evaluation.limitations || "No expert limitations recorded yet."}</dd></div></dl></Card>
      </div>
    </>
  );
}
