import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useParams } from "react-router";
import { api, blobUrl } from "../api/client";
import ReportWorkspaceNav from "../components/ReportWorkspaceNav";
import { Card, PageHeader, StatusChip } from "../components/ui";
import { httpStatusLabel, renderModeLabel } from "../lib/pageLabels";

export default function PageEvidenceRoute() {
  const { scanId, pageId } = useParams<{ scanId: string; pageId: string }>();
  const scan = Number(scanId);
  const page = Number(pageId);
  const { data: scanData } = useQuery({ queryKey: ["scan", scan], queryFn: () => api.getScan(scan), enabled: Number.isFinite(scan) });
  const { data, error } = useQuery({ queryKey: ["page-evidence", scan, page], queryFn: () => api.getPageEvidence(scan, page), enabled: Number.isFinite(scan) && Number.isFinite(page) });
  if (error) return <Card className="p-4 text-sm text-sev-critical" role="alert">This page is not part of the requested report.</Card>;
  if (!scanData || !data) return <div className="text-fg-muted">Loading…</div>;
  return (
    <>
      <PageHeader crumbs={[{ label: "Reports", to: "/scans" }, { label: `Report #${scan}`, to: `/scans/${scan}` }, { label: "Page evidence" }]} title={data.page.title || "Page evidence"} subtitle={data.page.url_normalized} />
      <ReportWorkspaceNav scanId={scan} previousScanId={scanData.previous_scan_id} />
      <Card className="mb-4 p-4 text-sm"><dl className="grid gap-3 sm:grid-cols-3"><div><dt className="font-semibold text-fg-muted">Page load result</dt><dd>{httpStatusLabel(data.page.status_code)}</dd></div><div><dt className="font-semibold text-fg-muted">How Axcess loaded it</dt><dd>{renderModeLabel(data.page.render_mode)}</dd></div><div><dt className="font-semibold text-fg-muted">Fetched</dt><dd>{data.page.fetched_at ?? "—"}</dd></div></dl></Card>
      <section className="mb-6"><h2 className="mb-2 text-base font-semibold">Observed accessibility findings</h2><div className="space-y-3">{data.a11y_findings.map((finding) => <Card key={finding.id} className="p-4"><div className="flex flex-wrap justify-between gap-2"><div><strong>{finding.help}</strong><p className="mt-1 text-sm text-fg-muted">{finding.wcag_sc ? `WCAG ${finding.wcag_sc}` : "Best practice"} · {finding.pipeline}{finding.pipeline === "alfa" && ` · ${finding.engine_outcome === "cant_tell" ? "Needs expert review (cannot tell)" : "Standardized ACT test failed"}`}</p></div><StatusChip value={finding.status} /></div>{finding.failure_summary && <p className="mt-2 text-sm">{finding.failure_summary}</p>}<code className="mt-2 block overflow-x-auto rounded-xs bg-surface-muted p-2 text-xs">{finding.target_selector}</code>{finding.screenshot_hash && <figure className="mt-3"><img className="max-h-72 rounded-xs border border-border" src={blobUrl(finding.screenshot_hash)} alt="Circled issue evidence. The circular marker identifies the detected location." loading="lazy" /><figcaption className="mt-1 text-xs text-fg-muted">The circle marks the detected location.</figcaption></figure>}</Card>)}</div></section>
      <section><h2 className="mb-2 text-base font-semibold">Image evidence</h2><div className="grid gap-3 lg:grid-cols-2">{data.image_occurrences.map((image) => <Card key={image.occurrence_id} className="p-4"><a href={image.src_url_canonical} target="_blank" rel="noreferrer" className="font-semibold">Source image <ExternalLink className="inline h-4 w-4" aria-hidden /></a><p className="mt-2 text-sm"><strong>Alt:</strong> {image.alt_text === null ? "Missing" : image.alt_text || "Decorative"}</p>{image.ocr_text && <p className="mt-2 text-sm"><strong>OCR:</strong> {image.ocr_text}</p>}{image.vlm_rationale && <p className="mt-2 text-sm text-fg-muted"><strong>AI rationale:</strong> {image.vlm_rationale}</p>}</Card>)}</div></section>
    </>
  );
}
