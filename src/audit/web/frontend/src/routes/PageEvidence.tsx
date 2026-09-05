import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Crosshair, ExternalLink, ImageOff, ScanEye } from "lucide-react";
import { useLocation, useParams } from "react-router";
import { api, blobUrl } from "../api/client";
import AlfaEvidenceNote from "../components/AlfaEvidenceNote";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
import { Card, StatusChip } from "../components/ui";
import { httpStatusLabel, renderModeLabel } from "../lib/pageLabels";
import { findingLocation } from "../lib/findingLocation";
import type { PageEvidence } from "../api/types";

/** One row of a page's accessibility evidence. */
type PageEvidenceFinding = PageEvidence["a11y_findings"][number];

/**
 * Everything one scanned page produced.
 *
 * The page used to open with three facts about the fetch, load result, render
 * mode, timestamp, and only then reach "Observed accessibility findings".
 * That is backwards: how the page was retrieved is provenance, and provenance
 * is what you check *after* you know what was found. So the answer comes
 * first, in counts and then in cards, and the fetch details sit at the bottom
 * where a reader goes to audit the audit.
 */
export default function PageEvidenceRoute() {
  const { scanId, pageId } = useParams<{ scanId: string; pageId: string }>();
  const { hash } = useLocation();
  const scan = Number(scanId);
  const page = Number(pageId);
  const { data: scanData } = useQuery({
    queryKey: ["scan", scan],
    queryFn: () => api.getScan(scan),
    enabled: Number.isFinite(scan),
  });
  const { data, error } = useQuery({
    queryKey: ["page-evidence", scan, page],
    queryFn: () => api.getPageEvidence(scan, page),
    enabled: Number.isFinite(scan) && Number.isFinite(page),
  });

  useEffect(() => {
    if (!data || !scanData || !/^#finding-\d+$/.test(hash)) return;
    const frame = window.requestAnimationFrame(() => {
      const finding = document.getElementById(hash.slice(1));
      finding?.scrollIntoView({ block: "center" });
      finding?.focus({ preventScroll: true });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [hash, data, scanData]);

  if (error)
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        This page is not part of the requested report.
      </Card>
    );
  if (!scanData || !data) return <div className="text-fg-muted">Loading…</div>;

  const findings = data.a11y_findings;
  const needsDecision = findings.filter((f) => f.engine_outcome === "cant_tell").length;
  const failed = findings.length - needsDecision;
  const withoutAlt = data.image_occurrences.filter((i) => i.alt_text === null).length;

  // Only group when a click actually revealed something: on a page where
  // nothing was, a lone "At page load" heading would divide nothing.
  const groups = findings.some((f) => f.revealed_by) ? groupByRevealingControl(findings) : null;

  return (
    <>
      <ReportHeader
        scanId={scan}
        previousScanId={scanData.previous_scan_id}
        title={data.page.title || "Page evidence"}
        meta={
          <ReportMeta
            counts={
              findings.length === 0
                ? "No accessibility findings on this page"
                : `${findings.length} finding${findings.length === 1 ? "" : "s"}` +
                  ` · ${data.image_occurrences.length} image${data.image_occurrences.length === 1 ? "" : "s"} checked`
            }
            note={data.page.url_normalized}
          />
        }
      />

      {findings.length > 0 && (
        <Card className="mb-5 p-4">
          <h2 className="text-sm font-semibold text-fg">What we found on this page</h2>
          <ul className="mt-2 flex flex-wrap gap-x-6 gap-y-1.5 text-sm text-fg-muted">
            {failed > 0 && (
              <li>
                <strong className="font-semibold tabular-nums text-fg">{failed}</strong> check
                {failed === 1 ? "" : "s"} the page did not pass
              </li>
            )}
            {needsDecision > 0 && (
              <li>
                <strong className="font-semibold tabular-nums text-fg">{needsDecision}</strong>{" "}
                the engine could not decide, a person has to judge {needsDecision === 1 ? "it" : "them"}
              </li>
            )}
            {withoutAlt > 0 && (
              <li>
                <strong className="font-semibold tabular-nums text-fg">{withoutAlt}</strong> image
                {withoutAlt === 1 ? "" : "s"} with no alt text
              </li>
            )}
          </ul>
        </Card>
      )}

      <section className="mb-6">
        <h2 className="mb-2.5 text-base font-semibold text-fg">
          {findings.length === 0 ? "Accessibility checks" : "Findings"}
        </h2>
        {findings.length === 0 ? (
          <Card className="p-4 text-sm text-fg-muted">
            No check reported a problem on this page. That is not the same as a pass, the
            report overview lists which methods ran and which did not.
          </Card>
        ) : groups === null ? (
          <div className="space-y-3">
            {findings.map((finding) => (
              <FindingCard key={finding.id} finding={finding} pageUrl={data.page.url_normalized} />
            ))}
          </div>
        ) : (
          <div className="space-y-6">
            {groups.map((group) => (
              <section key={group.key}>
                <h3 className="mb-2 text-sm font-semibold text-fg">
                  {group.label}{" "}
                  <span className="font-normal text-fg-muted">
                    ({group.findings.length} {group.findings.length === 1 ? "finding" : "findings"})
                  </span>
                </h3>
                <div className="space-y-3">
                  {group.findings.map((finding) => (
                    <FindingCard
                      key={finding.id}
                      finding={finding}
                      pageUrl={data.page.url_normalized}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </section>

      {data.image_occurrences.length > 0 && (
        <section className="mb-6">
          <h2 className="mb-2.5 text-base font-semibold text-fg">Images on this page</h2>
          <div className="grid gap-3 lg:grid-cols-2">
            {data.image_occurrences.map((image) => (
              <Card key={image.occurrence_id} className="p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <a
                    href={image.src_url_canonical}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm font-semibold text-umich-blue underline underline-offset-2"
                  >
                    Open the image
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                    <span className="sr-only"> in a new tab</span>
                  </a>
                  <AltChip alt={image.alt_text} />
                </div>
                {image.alt_text ? (
                  <p className="mt-2 text-sm text-fg">
                    <span className="font-semibold">Alt text:</span> “{image.alt_text}”
                  </p>
                ) : (
                  <p className="mt-2 text-sm text-fg-muted">
                    {image.alt_text === null
                      ? "This image has no alt attribute, so a screen reader announces nothing in its place."
                      : "Marked decorative (empty alt), so screen readers skip it."}
                  </p>
                )}
                {image.ocr_text && (
                  <p className="mt-2 text-sm text-fg-muted">
                    <span className="font-semibold text-fg">Text read from the image:</span>{" "}
                    {image.ocr_text}
                  </p>
                )}
                {image.vlm_rationale && (
                  <p className="mt-2 text-sm text-fg-muted">
                    <span className="font-semibold text-fg">What the local model saw:</span>{" "}
                    {image.vlm_rationale}
                  </p>
                )}
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* Provenance, not findings. It answers "can I trust the above" and
          belongs after it, this was the first thing on the page before. */}
      <details className="rounded-xs border border-border bg-surface p-4 shadow-card">
        <summary className="min-h-target cursor-pointer content-center text-sm font-semibold text-fg">
          How Axcess loaded this page
        </summary>
        <dl className="mt-2 grid gap-3 border-t border-border pt-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="font-semibold text-fg-muted">Page load result</dt>
            <dd className="text-fg">{httpStatusLabel(data.page.status_code)}</dd>
          </div>
          <div>
            <dt className="font-semibold text-fg-muted">How it was loaded</dt>
            <dd className="text-fg">{renderModeLabel(data.page.render_mode)}</dd>
          </div>
          <div>
            <dt className="font-semibold text-fg-muted">Fetched</dt>
            <dd className="text-fg">{data.page.fetched_at ?? "n/a"}</dd>
          </div>
        </dl>
      </details>
    </>
  );
}

function FindingCard({
  finding,
  pageUrl,
}: {
  finding: PageEvidenceFinding;
  pageUrl: string;
}) {
  const location = findingLocation(pageUrl, finding.target_selector, finding.target_display);
  const cantTell = finding.engine_outcome === "cant_tell";

  return (
    <Card
      id={`finding-${finding.id}`}
      tabIndex={-1}
      className="scroll-mt-24 p-4"
      aria-label={`Finding ${finding.id}: ${finding.help}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold leading-snug text-fg">{finding.help}</h3>
          <p className="mt-1 text-xs text-fg-muted">
            {finding.wcag_sc ? `WCAG ${finding.wcag_sc}` : "Best practice"} ·{" "}
            {sourceLabel(finding.pipeline)}
            {finding.pipeline === "alfa" &&
              ` · ${cantTell ? "could not be decided automatically" : "a standardized ACT test did not pass"}`}
          </p>
        </div>
        <StatusChip value={finding.status} />
      </div>

      {finding.failure_summary && (
        <p className="mt-2.5 text-sm leading-relaxed text-fg">{finding.failure_summary}</p>
      )}
      <AlfaEvidenceNote evidence={finding} />

      <p className="mt-3 text-2xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
        Where on the page
      </p>
      <p className="mt-1 break-words text-sm text-fg">{location.label}</p>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {/* A text fragment scrolls the live page to this exact wording and
            highlights it, the only "show me" available for findings that
            have no screenshot, which is every Alfa result. */}
        {location.deepLink && (
          <a
            href={location.deepLink}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-semibold text-umich-blue underline underline-offset-2"
          >
            <Crosshair className="h-4 w-4" aria-hidden />
            Show me on the live page
            <span className="sr-only">, opens in a new tab and scrolls to this text</span>
          </a>
        )}
        <details className="text-xs">
          <summary className="min-h-target cursor-pointer content-center text-fg-muted">
            Selector for developers
          </summary>
          <code className="mt-1 block max-w-full overflow-x-auto rounded-2xs border border-border bg-surface-muted px-2 py-1 text-xs text-fg">
            {location.raw}
          </code>
        </details>
      </div>

      {finding.screenshot_hash ? (
        <figure className="mt-3">
          <img
            className="max-h-72 rounded-xs border border-border"
            src={blobUrl(finding.screenshot_hash)}
            alt="Circled issue evidence. The circular marker identifies the detected location."
            loading="lazy"
          />
          <figcaption className="mt-1 flex items-center gap-1.5 text-xs text-fg-muted">
            <ScanEye className="h-3.5 w-3.5" aria-hidden />
            Captured during the scan. The circle marks the detected location.
          </figcaption>
        </figure>
      ) : (
        // Saying why there is no picture is the difference between "the tool
        // is broken" and "this check cannot produce one".
        <p className="mt-3 flex items-center gap-1.5 text-xs text-fg-subtle">
          <ImageOff className="h-3.5 w-3.5 shrink-0" aria-hidden />
          {finding.pipeline === "alfa"
            ? "No screenshot: ACT rules are evaluated in a separate browser session, which the scan cannot photograph."
            : "No screenshot was captured for this finding."}
        </p>
      )}
    </Card>
  );
}

function AltChip({ alt }: { alt: string | null }) {
  const [label, tone] =
    alt === null
      ? ["No alt text", "bg-sev-major-bg text-sev-major"]
      : alt === ""
        ? ["Decorative", "border border-border bg-surface-muted text-fg-muted"]
        : ["Has alt text", "border border-border bg-surface-muted text-fg-muted"];
  return (
    <span className={`inline-flex shrink-0 items-center rounded-2xs px-2 py-0.5 text-2xs font-semibold ${tone}`}>
      {label}
    </span>
  );
}

function sourceLabel(pipeline: string): string {
  return (
    {
      axe: "axe-core",
      alfa: "Siteimprove Alfa",
      keyboard: "keyboard probe",
      responsive: "responsive & zoom probe",
      focus: "focus probe",
      visual: "visual probe",
    }[pipeline] ?? pipeline
  );
}

/** Findings split by the control that revealed them.
 *
 *  A finding that only exists after a click cannot be told apart from one
 *  present at load when both sit in a flat list, an auditor reading this
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
    groups.push({
      key: control,
      label: `After clicking “${control}”`,
      findings: byControl.get(control)!,
    });
  }
  return groups;
}
