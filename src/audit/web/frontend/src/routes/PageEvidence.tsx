import AlfaEvidenceNote from "../components/AlfaEvidenceNote";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useLocation, useParams } from "react-router";
import { api, blobUrl } from "../api/client";
import ReportHeader from "../components/ReportHeader";
import { Card, StatusChip } from "../components/ui";
import { httpStatusLabel, renderModeLabel } from "../lib/pageLabels";
import type { PageEvidence } from "../api/types";

/** One row of a page's accessibility evidence. */
type PageEvidenceFinding = PageEvidence["a11y_findings"][number];

/** One finding's evidence card. Extracted unchanged so the flat list and the
 *  grouped-by-state list render identically. */
function FindingCard({ finding }: { finding: PageEvidenceFinding }) {
  return <Card id={`finding-${finding.id}`} tabIndex={-1} className="scroll-mt-24 p-4" aria-label={`Finding ${finding.id}: ${finding.help}`}>
    <div className="flex flex-wrap justify-between gap-2">
      <div><h3 className="font-semibold">{finding.help}</h3>
        <p className="mt-1 text-sm text-fg-muted">{finding.wcag_sc ? `WCAG ${finding.wcag_sc}` : "Best practice"} · {finding.pipeline}{finding.pipeline === "alfa" && ` · ${finding.engine_outcome === "cant_tell" ? "Needs manual review (cannot tell)" : "Standardized ACT test failed"}`}</p>
      </div><StatusChip value={finding.status} />
    </div>
    {finding.failure_summary && <p className="mt-2 text-sm">{finding.failure_summary}</p>}
    <AlfaEvidenceNote evidence={finding} />
    <p className="mt-3 text-xs font-semibold">Location</p>
    <code className="mt-1 block overflow-x-auto rounded-xs bg-surface-muted p-2 text-xs">{finding.target_display || finding.target_selector}</code>
    {finding.screenshot_hash && <figure className="mt-3"><img className="max-h-72 rounded-xs border border-border" src={blobUrl(finding.screenshot_hash)} alt="Circled issue evidence. The circular marker identifies the detected location." loading="lazy" /><figcaption className="mt-1 text-xs text-fg-muted">The circle marks the detected location.</figcaption></figure>}
  </Card>;
}

/** Findings split by the control that revealed them.
 *
 *  A finding that only exists after a click cannot be told apart from one
 *  present at load when both sit in a flat list — an auditor reading this
 *  page was being sent to look for a dialog that is not there until
 *  something is operated. Load-state findings come first, then each control
 *  in the order the probe reached it, which is also the order an auditor
 *  reproduces them in.
 */
function groupByRevealingControl(findings: PageEvidenceFinding[]) {
  const atLoad = findings.filter((f) => !f.revealed_by);
  const order: string[] = [];
  const byControl = new Map<string, PageEvidenceFinding[]>();
  for (const finding of findings) {
    const control = finding.revealed_by;
    if (!control) continue;
    if (!byControl.has(control)) {
      byControl.set(control, []);
      order.push(control);
    }
    byControl.get(control)!.push(finding);
  }
  const groups: { key: string; label: string; findings: PageEvidenceFinding[] }[] = [];
  if (atLoad.length > 0) groups.push({ key: "__load__", label: "At page load", findings: atLoad });
  for (const control of order) {
    groups.push({ key: control, label: `After clicking \u201C${control}\u201D`, findings: byControl.get(control)! });
  }
  return groups;
}

export default function PageEvidenceRoute() {
  const { scanId, pageId } = useParams<{ scanId: string; pageId: string }>();
  const { hash } = useLocation();
  const scan = Number(scanId);
  const page = Number(pageId);
  const { data: scanData } = useQuery({ queryKey: ["scan", scan], queryFn: () => api.getScan(scan), enabled: Number.isFinite(scan) });
  const { data, error } = useQuery({ queryKey: ["page-evidence", scan, page], queryFn: () => api.getPageEvidence(scan, page), enabled: Number.isFinite(scan) && Number.isFinite(page) });
  useEffect(() => {
    if (!data || !scanData || !/^#finding-\d+$/.test(hash)) return;
    const frame = window.requestAnimationFrame(() => {
      const finding = document.getElementById(hash.slice(1));
      finding?.scrollIntoView({ block: "center" });
      finding?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [hash, data, scanData]);
  if (error) return <Card className="p-4 text-sm text-sev-critical" role="alert">This page is not part of the requested report.</Card>;
  if (!scanData || !data) return <div className="text-fg-muted">Loading…</div>;
  // Only group when a click actually revealed something: on a page where
  // nothing was, a lone "At page load" heading would divide nothing.
  const a11yGroups = data.a11y_findings.some((f) => f.revealed_by)
    ? groupByRevealingControl(data.a11y_findings)
    : null;
  return (
    <>
      <ReportHeader
        scanId={scan}
        previousScanId={scanData.previous_scan_id}
        title={data.page.title || "Page evidence"}
        meta={data.page.url_normalized}
      />
      <Card className="mb-4 p-4 text-sm"><dl className="grid gap-3 sm:grid-cols-3"><div><dt className="font-semibold text-fg-muted">Page load result</dt><dd>{httpStatusLabel(data.page.status_code)}</dd></div><div><dt className="font-semibold text-fg-muted">How Axcess loaded it</dt><dd>{renderModeLabel(data.page.render_mode)}</dd></div><div><dt className="font-semibold text-fg-muted">Fetched</dt><dd>{data.page.fetched_at ?? "—"}</dd></div></dl></Card>
      <section className="mb-6"><h2 className="mb-2 text-base font-semibold">Observed accessibility findings</h2>{a11yGroups === null ? (<div className="space-y-3">{data.a11y_findings.map((finding) => <FindingCard key={finding.id} finding={finding} />)}</div>) : (<div className="space-y-6">{a11yGroups.map((group) => (<section key={group.key}><h3 className="mb-2 text-sm font-semibold text-fg">{group.label} <span className="font-normal text-fg-muted">({group.findings.length} {group.findings.length === 1 ? "finding" : "findings"})</span></h3><div className="space-y-3">{group.findings.map((finding) => <FindingCard key={finding.id} finding={finding} />)}</div></section>))}</div>)}</section>
      <section><h2 className="mb-2 text-base font-semibold">Image evidence</h2><div className="grid gap-3 lg:grid-cols-2">{data.image_occurrences.map((image) => <Card key={image.occurrence_id} className="p-4"><a href={image.src_url_canonical} target="_blank" rel="noreferrer" className="font-semibold">Source image <ExternalLink className="inline h-4 w-4" aria-hidden /></a><p className="mt-2 text-sm"><strong>Alt:</strong> {image.alt_text === null ? "Missing" : image.alt_text || "Decorative"}</p>{image.ocr_text && <p className="mt-2 text-sm"><strong>OCR:</strong> {image.ocr_text}</p>}{image.vlm_rationale && <p className="mt-2 text-sm text-fg-muted"><strong>AI rationale:</strong> {image.vlm_rationale}</p>}</Card>)}</div></section>
    </>
  );
}
