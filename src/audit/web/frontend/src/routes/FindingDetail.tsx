import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { api, blobUrl } from "../api/client";
import {
  AltTag,
  Button,
  Card,
  LinkButton,
  PageHeader,
  PageLink,
  SeverityChip,
} from "../components/ui";
import type { FindingStatus } from "../api/types";

const STATUSES: FindingStatus[] = [
  "new",
  "reviewing",
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
];

// 0-5 shortcuts on the detail page for one-key status changes.
const STATUS_KEY_MAP: Record<string, FindingStatus> = {
  "0": "new",
  "1": "reviewing",
  "2": "in_progress",
  "3": "remediated",
  "4": "accepted_risk",
  "5": "false_positive",
};

export default function FindingDetailRoute() {
  const { findingId } = useParams<{ findingId: string }>();
  const id = Number(findingId);
  const qc = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["finding", id],
    queryFn: () => api.getFinding(id),
    enabled: Number.isFinite(id),
  });
  const [status, setStatus] = useState<FindingStatus | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (data) setStatus(data.status);
  }, [data]);

  const save = useMutation({
    mutationFn: (s: FindingStatus) => api.setStatus(id, s),
    onSuccess: (_, s) => {
      qc.invalidateQueries({ queryKey: ["finding", id] });
      qc.invalidateQueries({ queryKey: ["findings"] });
      setToast(`Status updated to ${s}`);
      window.setTimeout(() => setToast(null), 1800);
    },
  });

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      const target = ev.target as HTMLElement | null;
      if (
        target &&
        (/^(input|textarea|select)$/i.test(target.tagName) ||
          target.isContentEditable)
      ) {
        return;
      }
      const mapped = STATUS_KEY_MAP[ev.key];
      if (mapped) {
        ev.preventDefault();
        setStatus(mapped);
        save.mutate(mapped);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [save]);

  if (error) {
    return (
      <Card className="p-4 text-sm text-sev-critical">
        {error instanceof Error ? error.message : String(error)}
      </Card>
    );
  }
  if (isLoading || !data) {
    return <div className="text-fg-muted">Loading…</div>;
  }

  const firstAlt = data.occurrences[0]?.alt_text ?? null;

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Scans", to: "/scans" },
          { label: `Scan #${data.scan_id}`, to: `/scans/${data.scan_id}` },
          { label: "Findings", to: `/scans/${data.scan_id}/findings` },
          { label: `Finding #${data.id}` },
        ]}
        title={
          <div className="flex items-center gap-3">
            <SeverityChip value={data.severity} />
            <span>Finding #{data.id}</span>
          </div>
        }
        subtitle={
          <span className="text-sm">
            priority <strong>{data.priority_score.toFixed(2)}</strong> · WCAG{" "}
            {data.wcag_criterion}
          </span>
        }
        actions={
          <LinkButton
            to={`/scans/${data.scan_id}/findings`}
            variant="secondary"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Back to findings
          </LinkButton>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(280px,45%)_1fr]">
        <Card className="flex items-center justify-center overflow-hidden bg-[repeating-conic-gradient(theme(colors.border.DEFAULT)_0_25%,transparent_0_50%)] [background-size:24px_24px]">
          {data.has_svg_text ? (
            <div className="p-8 text-center">
              <strong className="text-fg">Inline SVG</strong>
              <p className="mt-1 text-sm text-fg-muted">
                Embedded directly in the page — no image file stored.
              </p>
            </div>
          ) : data.content_hash ? (
            <img
              src={blobUrl(data.content_hash)}
              // The audited graphic itself. Avoid the literal word "image"
              // here — screen readers already announce <img> as an image,
              // so saying "Image under audit" doubles up
              // (jsx-a11y/img-redundant-alt). The wider page chrome makes
              // it clear *why* the graphic is on screen; the alt only needs
              // to convey what it is.
              alt="Audited graphic"
              className="max-h-[480px] w-full bg-white object-contain"
              {...(data.width ? { width: data.width } : {})}
              {...(data.height ? { height: data.height } : {})}
            />
          ) : (
            <div className="p-8 text-sm text-fg-muted">
              No image blob available
            </div>
          )}
        </Card>

        <div className="flex flex-col gap-4">
          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-fg-subtle">
              Decision grid
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <VerdictCell label="Image text (OCR)">
                {data.ocr_text ? (
                  <div className="whitespace-pre-wrap font-mono text-sm text-fg">
                    {data.ocr_text}
                    <div className="mt-1 text-xs text-fg-muted">
                      confidence {Math.round(data.ocr_confidence ?? 0)}%
                    </div>
                  </div>
                ) : (
                  <em className="text-sm text-fg-subtle">no text detected</em>
                )}
              </VerdictCell>
              <VerdictCell label="Alt attribute">
                <AltTag value={firstAlt} />
              </VerdictCell>
            </div>
            {(data.vlm_classification || data.vlm_rationale) && (
              <div className="mt-3">
                <VerdictCell label="VLM classification">
                  <strong className="text-fg">
                    {data.vlm_classification ?? "—"}
                  </strong>
                  {data.vlm_rationale && (
                    <p className="mt-1 text-sm italic text-fg-muted">
                      &ldquo;{data.vlm_rationale}&rdquo;
                    </p>
                  )}
                </VerdictCell>
              </div>
            )}
            {data.remediation_hint && (
              <div className="mt-3 rounded-xs border-l-2 border-umich-blue bg-umich-blue/5 p-3 text-sm text-fg">
                <div className="mb-1 text-2xs font-semibold uppercase tracking-wide text-umich-blue">
                  Suggested fix
                </div>
                {data.remediation_hint}
              </div>
            )}
          </Card>

          <Card className="p-4">
            <h2 className="mb-2 flex items-center justify-between gap-2 text-sm font-semibold uppercase tracking-wide text-fg-subtle">
              <span>Triage status</span>
              {toast && (
                <span
                  role="status"
                  aria-live="polite"
                  className="rounded-xs bg-umich-maize/60 px-2 py-0.5 text-2xs font-semibold text-umich-blue"
                >
                  {toast}
                </span>
              )}
            </h2>
            {/* The triage row is the page's primary affordance — the
                whole reason the user is on FindingDetail. Each control
                clears 44px (label gets a min-h-target so click-the-label
                still works for the dropdown), the dropdown is base
                font-size for legibility, and Save uses `size="lg"` to
                read as the page's primary CTA. */}
            <div className="flex flex-wrap items-center gap-3">
              <label
                htmlFor="status-select"
                className="flex min-h-target items-center text-base font-semibold text-fg"
              >
                Status:
              </label>
              <select
                id="status-select"
                value={status ?? data.status}
                onChange={(e) => setStatus(e.target.value as FindingStatus)}
                className="min-h-target rounded-xs border border-border bg-surface px-3 py-2 text-base text-fg focus:border-umich-blue focus:outline-none"
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
              <Button
                variant="primary"
                size="lg"
                onClick={() => status && save.mutate(status)}
                disabled={save.isPending || status === data.status}
              >
                Save
              </Button>
            </div>
            <p className="mt-2 text-2xs text-fg-muted">
              Or press: <kbd>0</kbd>=new <kbd>1</kbd>=reviewing{" "}
              <kbd>2</kbd>=in_progress <kbd>3</kbd>=remediated{" "}
              <kbd>4</kbd>=accepted_risk <kbd>5</kbd>=false_positive
            </p>
          </Card>
        </div>
      </div>

      {data.occurrences.length > 0 && (
        <Card className="mt-6 overflow-hidden">
          <div className="border-b border-border bg-surface-muted px-4 py-2 text-2xs font-semibold uppercase tracking-wide text-fg-subtle">
            Appears on {data.occurrences.length} page
            {data.occurrences.length === 1 ? "" : "s"}
          </div>
          <table className="w-full text-sm">
            <thead className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">
              <tr>
                <th scope="col" className="px-4 py-2 text-left">
                  Page
                </th>
                <th scope="col" className="px-4 py-2 text-left">
                  Alt text on that page
                </th>
                <th scope="col" className="px-4 py-2 text-left">
                  Above fold
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.occurrences.map((o, i) => (
                <tr key={i} className="hover:bg-surface-muted/60">
                  <td className="px-4 py-2">
                    <PageLink
                      pageId={o.page_id}
                      scanId={data.scan_id}
                      pageUrl={o.page_url}
                      pageTitle={null}
                    />
                  </td>
                  <td className="px-4 py-2">
                    <AltTag value={o.alt_text} />
                  </td>
                  <td className="px-4 py-2 text-fg-muted">
                    {o.above_fold ? "yes" : "no"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}

function VerdictCell({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">
        {label}
      </div>
      <div className="mt-1">{children}</div>
    </div>
  );
}
