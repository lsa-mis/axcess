import { useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
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
import {
  Cell,
  ColumnHeader,
  Row,
  Table,
  TableBar,
  TableHead,
  TableRegion,
} from "../components/table/Table";
import { requestStatusRationale } from "../statusDecision";
import { usePreferences } from "../hooks/usePreferences";
import { messageDuration } from "../lib/preferences";
import { STATUS_HELP, STATUS_LABEL, STATUS_OPTION_LABEL } from "../lib/terms";

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
  // Settings > Session and message timing: 1.8s, five times that, or until
  // the reader dismisses it.
  const toastMs = messageDuration(usePreferences().messageTiming, 1800);
  const showToast = useCallback(
    (message: string) => {
      setToast(message);
      if (toastMs !== null) window.setTimeout(() => setToast(null), toastMs);
    },
    [toastMs],
  );

  useEffect(() => {
    if (data) setStatus(data.status);
  }, [data]);

  const save = useMutation({
    mutationFn: ({ next, rationale }: { next: FindingStatus; rationale: string }) =>
      api.setStatus(id, next, rationale || undefined),
    onSuccess: (_, { next }) => {
      qc.invalidateQueries({ queryKey: ["finding", id] });
      qc.invalidateQueries({ queryKey: ["findings"] });
      showToast(`Status changed to ${STATUS_LABEL[next]}`);
    },
    onError: () => {
      setStatus(data?.status ?? null);
      showToast("Status not saved. Try again.");
    },
  });

  const attemptSave = useCallback((next: FindingStatus) => {
    const rationale = requestStatusRationale(next, `image #${id}`);
    if (rationale === null) {
      setStatus(data?.status ?? null);
      showToast("Status not changed");
      return;
    }
    setStatus(next);
    save.mutate({ next, rationale });
  }, [data?.status, id, save, showToast]);

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
  const occurrences = useMemo(() => data?.occurrences ?? [], [data]);
  const resetKey = useMemo(
    () => occurrences.map((o) => `${o.page_id}:${o.page_url}`).join(","),
    [occurrences],
  );
  const paged = usePagedRows(occurrences, { resetKey });

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
                <span className="flex items-center gap-1">
                  <span
                    role="status"
                    aria-live="polite"
                    className="rounded-xs bg-umich-maize/60 px-2 py-0.5 text-2xs font-semibold text-[#00274C] dark:bg-umich-maize"
                  >
                    {toast}
                  </span>
                  {toastMs === null && (
                    // eslint-disable-next-line react/forbid-elements -- Convert: a small ghost button, Button variant="ghost" size="sm"
                    <button
                      type="button"
                      onClick={() => setToast(null)}
                      className="inline-flex min-h-target items-center rounded-xs px-2 text-2xs font-semibold text-fg-muted hover:bg-surface-muted hover:text-fg"
                    >
                      Dismiss message
                    </button>
                  )}
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
            {/* What the chosen status means, in words: a status is a person's
                decision, and "Fixed" is not something Axcess checks. */}
            <p className="mt-2 text-sm text-fg-muted">
              <span className="font-semibold text-fg">{STATUS_OPTION_LABEL[status ?? data.status]}:</span>{" "}
              {STATUS_HELP[status ?? data.status]}
            </p>
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
        <Card className="mt-6">
          <div className="border-b border-border bg-surface-muted px-4 py-2 text-2xs font-semibold text-fg-muted">
            Appears on {data.occurrences.length} page
            {data.occurrences.length === 1 ? "" : "s"}
          </div>
          {paged.pages > 1 && (
            <TableBar pager={<TablePagination label="Occurrences" noun="occurrences" {...paged} />} />
          )}
          <TableRegion label="Occurrences table" paged={paged}>
            <Table caption={`Occurrences of image #${data.id}`}>
              <TableHead>
                <tr>
                  <ColumnHeader>Page</ColumnHeader>
                  <ColumnHeader>Alt text on that page</ColumnHeader>
                  <ColumnHeader>Visible without scrolling</ColumnHeader>
                </tr>
              </TableHead>
              <tbody>
                {paged.pageRows.map((o, i) => (
                  <Row key={i} index={(paged.page - 1) * paged.pageSize + i}>
                    <Cell>
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
                    </Cell>
                    <Cell>
                      <AltTag value={o.alt_text} />
                    </Cell>
                    <Cell className="text-fg-muted">
                      {o.above_fold ? "Yes" : "No"}
                    </Cell>
                  </Row>
                ))}
              </tbody>
            </Table>
          </TableRegion>
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
