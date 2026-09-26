import { useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { api, blobUrl } from "../api/client";
import {
  AltTag,
  Button,
  Card,
  LinkButton,
  PageHeader,
  PageLink,
  Select,
  SeverityChip,
} from "../components/ui";
import type { FindingStatus } from "../api/types";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import { requestStatusRationale } from "../statusDecision";
import { STATUS_LABEL, STATUS_OPTION_LABEL } from "../lib/terms";

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
    mutationFn: ({ next, rationale }: { next: FindingStatus; rationale: string }) =>
      api.setStatus(id, next, rationale || undefined),
    onSuccess: (_, { next }) => {
      qc.invalidateQueries({ queryKey: ["finding", id] });
      qc.invalidateQueries({ queryKey: ["findings"] });
      setToast(`Status changed to ${STATUS_LABEL[next]}`);
      window.setTimeout(() => setToast(null), 1800);
    },
    onError: () => {
      setStatus(data?.status ?? null);
      setToast("Status not saved. Try again.");
      window.setTimeout(() => setToast(null), 1800);
    },
  });

  const attemptSave = useCallback((next: FindingStatus) => {
    const rationale = requestStatusRationale(next, `image #${id}`);
    if (rationale === null) {
      setStatus(data?.status ?? null);
      setToast("Status not changed");
      window.setTimeout(() => setToast(null), 1800);
      return;
    }
    setStatus(next);
    save.mutate({ next, rationale });
  }, [data?.status, id, save]);

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
        attemptSave(mapped);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [attemptSave]);
  const occurrences = data?.occurrences ?? [];
  const paged = usePagedRows(occurrences, {
    resetKey: occurrences.map((o) => `${o.page_id}:${o.page_url}`).join(","),
  });

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
          { label: "Reports", to: "/scans" },
          { label: `Report #${data.scan_id}`, to: `/scans/${data.scan_id}` },
          { label: "Images", to: `/scans/${data.scan_id}/findings` },
          { label: `Image #${data.id}` },
        ]}
        title={
          <div className="flex items-center gap-3">
            <SeverityChip value={data.severity} />
            <span>Image #{data.id}</span>
          </div>
        }
        subtitle={
          <span className="text-sm">
            WCAG {data.wcag_criterion}
          </span>
        }
        actions={
          <LinkButton
            to={`/scans/${data.scan_id}/findings`}
            variant="secondary"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Back to images
          </LinkButton>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(280px,45%)_1fr]">
        <Card className="flex items-center justify-center overflow-hidden bg-[repeating-conic-gradient(theme(colors.border.DEFAULT)_0_25%,transparent_0_50%)] [background-size:24px_24px]">
          {data.has_svg_text ? (
            <div className="p-8 text-center">
              <strong className="text-fg">Graphic in the page code (inline SVG)</strong>
              <p className="mt-1 text-sm text-fg-muted">
                It is part of the page itself, so Axcess has no image file to
                show.
              </p>
            </div>
          ) : data.content_hash ? (
            <img
              src={blobUrl(data.content_hash)}
              // The audited graphic itself. Avoid the literal word "image"
              // here, screen readers already announce <img> as an image,
              // so saying "Image under audit" doubles up
              // (jsx-a11y/img-redundant-alt). The wider page chrome makes
              // it clear *why* the graphic is on screen; the alt only needs
              // to convey what it is.
              alt="Graphic under review"
              className="max-h-[480px] w-full bg-white object-contain"
              {...(data.width ? { width: data.width } : {})}
              {...(data.height ? { height: data.height } : {})}
            />
          ) : (
            <div className="p-8 text-sm text-fg-muted">
              No saved image file
            </div>
          )}
        </Card>

        <div className="flex flex-col gap-4">
          <Card className="p-4">
            <h2 className="mb-3 text-sm font-semibold text-fg-subtle">
              What Axcess found
            </h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <VerdictCell label="Text read from image (OCR)">
                {data.ocr_text ? (
                  <div className="whitespace-pre-wrap font-mono text-sm text-fg">
                    {data.ocr_text}
                    <div className="mt-1 text-xs text-fg-muted">
                      Confidence: {Math.round(data.ocr_confidence ?? 0)}%
                    </div>
                  </div>
                ) : (
                  <em className="text-sm text-fg-subtle">No text found</em>
                )}
              </VerdictCell>
              <VerdictCell label="Alt text">
                <AltTag value={firstAlt} />
              </VerdictCell>
            </div>
            {(data.vlm_classification || data.vlm_rationale) && (
              <div className="mt-3">
                <VerdictCell label="Image type, suggested by AI (vision model)">
                  <strong className="text-fg">
                    {data.vlm_classification
                      ? sentenceCase(data.vlm_classification)
                      : "Not classified"}
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
                <div className="mb-1 text-2xs font-semibold text-umich-blue">
                  Suggested fix
                </div>
                {data.remediation_hint}
              </div>
            )}
          </Card>

          <Card className="p-4">
            <h2 className="mb-2 flex items-center justify-between gap-2 text-sm font-semibold text-fg-subtle">
              <span>Status</span>
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
            {/* The triage row is the page's primary affordance, the
                whole reason the user is on FindingDetail. Each control
                clears 44px (label gets a min-h-target so click-the-label
                still works for the dropdown), the dropdown is base
                font-size for legibility, and Save uses `size="lg"` to
                read as the page's primary CTA. */}
            <div className="flex flex-wrap items-center gap-3">
              <Select
                id="status-select"
                label="Change status to:"
                value={status ?? data.status}
                onChange={(next) => setStatus(next as FindingStatus)}
                options={STATUSES.map((s) => ({ value: s, label: STATUS_OPTION_LABEL[s] }))}
              />
              <Button
                variant="primary"
                size="lg"
                onClick={() => status && attemptSave(status)}
                disabled={save.isPending || status === data.status}
              >
                Save status
              </Button>
            </div>
            <p className="mt-2 text-2xs text-fg-muted">
              Or press a number key:{" "}
              {Object.entries(STATUS_KEY_MAP).map(([key, value], index) => (
                <span key={key}>
                  {index > 0 && ", "}
                  <kbd>{key}</kbd> {STATUS_OPTION_LABEL[value]}
                </span>
              ))}
              .
            </p>
          </Card>
        </div>
      </div>

      {data.occurrences.length > 0 && (
        <Card className="mt-6 overflow-hidden">
          <div className="border-b border-border bg-surface-muted px-4 py-2 text-2xs font-semibold text-fg-subtle">
            Appears on {data.occurrences.length} page
            {data.occurrences.length === 1 ? "" : "s"}
          </div>
          {/* Holds the tallest page's height, so paging never moves the pager. */}
          <div {...paged.hold}>
          <table className="w-full text-sm">
            <thead className="text-2xs font-semibold text-fg-subtle">
              <tr>
                <th scope="col" className="px-4 py-2 text-left">
                  Page
                </th>
                <th scope="col" className="px-4 py-2 text-left">
                  Alt text on that page
                </th>
                <th scope="col" className="px-4 py-2 text-left">
                  Visible without scrolling
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {paged.pageRows.map((o, i) => (
                <tr key={i} className="hover:bg-surface-muted/60">
                  <td className="px-4 py-2">
                    <PageLink
                      pageId={o.page_id}
                      scanId={data.scan_id}
                      pageUrl={o.page_url}
                      pageTitle={null}
                      origin={`Image #${id}`}
                      context={`Image ${id}`}
                      contextTo={`/findings/${id}`}
                      backTo={`/findings/${id}`}
                    />
                  </td>
                  <td className="px-4 py-2">
                    <AltTag value={o.alt_text} />
                  </td>
                  <td className="px-4 py-2 text-fg-muted">
                    {o.above_fold ? "Yes" : "No"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <TablePagination label="Occurrences" noun="occurrences" {...paged} />
        </Card>
      )}
    </>
  );
}

/** A stored value as sentence-case words: "no_meaningful_text" -> "No meaningful text". */
function sentenceCase(value: string): string {
  const words = value.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
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
      <div className="text-2xs font-semibold text-fg-subtle">
        {label}
      </div>
      <div className="mt-1">{children}</div>
    </div>
  );
}
