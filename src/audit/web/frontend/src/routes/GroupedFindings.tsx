import { Link, useParams, useSearchParams } from "react-router";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Info, Lightbulb } from "lucide-react";
import { useMemo, useState } from "react";
import { api, blobUrl } from "../api/client";
import {
  Button,
  Card,
  EmptyState,
  LinkButton,
  PageHeader,
  Select,
  SeverityChip,
  StatCard,
  StatusChip,
} from "../components/ui";
import { withoutUserinfo } from "../components/ReportCrumb";
import type {
  FindingStatus,
  FindingsGroup,
  GroupedFinding,
} from "../api/types";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import {
  Cell,
  ColumnHeader,
  Row,
  Table,
  TableBar,
  TableHead,
  TableRegion,
  TableStatus,
} from "../components/table/Table";
import { ActiveFilters, FilterMenu, activeFilterItems, type FilterGroup } from "../components/table/FilterMenu";
import { requestStatusRationale } from "../statusDecision";
import { useScanQuery } from "../hooks/useScanQuery";
import { STATUS_LABEL, STATUS_OPTION_LABEL } from "../lib/terms";

const STATUS_OPTIONS: FindingStatus[] = [
  "new",
  "reviewing",
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
];

/**
 * Image-of-text findings, grouped by remediation key.
 *
 * The parallel to the WCAG axe rollup at `/scans/:id/a11y`, instead of
 * grouping by `wcag_sc`, we group by `(classification, alt_adequacy)`
 * because that pair is the natural identity of an issue type: every
 * finding in the same group inherits the same row from
 * `rules/remediation.yaml`, so the *fix* is the same for every row.
 *
 * Surfacing the hint at the group level (not per-finding) keeps the
 * recommendation visible without repeating it, and avoids implying that
 * different findings might have different fixes when in fact they don't.
 */
export default function GroupedFindingsRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const rawStatus = params.get("status") ?? "";
  const status = (
    STATUS_OPTIONS.includes(rawStatus as FindingStatus) ? rawStatus : ""
  ) as FindingStatus | "";

  const { data: scan, error: scanError } = useScanQuery(id);
  const { data, isLoading } = useQuery({
    queryKey: ["grouped-findings", id, status],
    queryFn: () => api.getGroupedFindings(id, status || undefined),
    // A new status keeps this scan's groups on screen while it loads, so
    // the Filter menu, and the focus in it, stay where they were.
    placeholderData: (previous, query) => query?.queryKey[1] === id ? keepPreviousData(previous) : undefined,
    enabled: Number.isFinite(id),
  });

  const setStatusParam = (value: FindingStatus | "") => {
    const next = new URLSearchParams(params);
    if (value) next.set("status", value);
    else next.delete("status");
    setParams(next);
  };

  if (scanError) {
    return (
      <Card className="p-4 text-sm text-sev-critical">
        {scanError instanceof Error ? scanError.message : String(scanError)}
      </Card>
    );
  }
  if (!scan || !data || isLoading) {
    return <div className="text-fg-muted">Loading…</div>;
  }

  const { coverage, groups } = data;
  const filters: FilterGroup[] = [
    {
      key: "status",
      label: "Status",
      value: status,
      options: [
        { value: "", label: "All" },
        ...STATUS_OPTIONS.map((s) => ({ value: s, label: STATUS_OPTION_LABEL[s] })),
      ],
    },
  ];

  return (
    <>
      <PageHeader
        title="Images, grouped by issue"
        subtitle={withoutUserinfo(scan.seed_url)}
        actions={
          <LinkButton to={`/scans/${scan.id}/findings`} variant="secondary">
            Show all images in one table
            <ChevronRight className="h-4 w-4" aria-hidden />
          </LinkButton>
        }
      />

      {/* Up-front explainer, analogue of the WCAG view's scope-honesty
          banner. The story here is different: every group has one fix,
          so the operator decides once per group instead of per row. */}
      <Card
        className="mb-4 border-umich-blue/30 bg-umich-blue/5 p-4"
        role="note"
      >
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
          <p className="text-sm text-fg">
            <strong>How this page groups images.</strong> Each group is one
            issue. Axcess groups images by two things: the kind of image
            (classification), and whether its alt text is good enough. Alt
            text is the text a screen reader reads for an image. Every image
            in a group has the <em>same suggested fix</em>, so you can decide
            once for the whole group. Open a group to see its images and the
            pages where each one appears.
          </p>
        </div>
      </Card>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Images" value={coverage.finding_count} />
        <StatCard label="Issues" value={groups.length} />
        <StatCard label="Occurrences" value={coverage.occurrence_total} />
        <StatCard label="Pages scanned" value={coverage.page_count} />
      </div>

      {/* Status filter, URL-persistent, auto-applies on change. Same
          UX shape as the WCAG drill-down filter. One Filter menu for
          every group's table below: the status narrows them all. */}
      <Card className="mb-4">
        <TableBar
          footer={<ActiveFilters items={activeFilterItems(filters)} onClear={() => setStatusParam("")} />}
        >
          <FilterMenu
            groups={filters}
            onChange={(_key, value) => setStatusParam(value as FindingStatus | "")}
            onReset={() => setStatusParam("")}
          />
        </TableBar>
        <TableStatus className="border-b-0">
          {groups.length.toLocaleString()} {groups.length === 1 ? "issue" : "issues"}.
        </TableStatus>
      </Card>

      {groups.length === 0 ? (
        <EmptyState
          title={
            status
              ? "No images have this status"
              : "No images with text to review"
          }
          message={
            status
              ? "Clear the filters to see images with other statuses."
              : "The image text check found none in this scan, or Axcess has not finished grouping them yet."
          }
        />
      ) : (
        <div className="space-y-3">
          {groups.map((g, i) => (
            <GroupCard
              key={`${g.classification ?? "unclassified"}-${g.alt_adequacy}`}
              group={g}
              defaultOpen={i < 2}
              scanId={id}
            />
          ))}
        </div>
      )}
    </>
  );
}

/**
 * One group card, header summarizes the bucket, the body shows the
 * shared remediation hint and a table of the individual findings.
 *
 * We use a controlled `useState` toggle rather than the browser-native
 * `<details>` element here because the surrounding components are
 * already React; mixing imperative DOM state with React state is a
 * footgun (closing the details element doesn't unmount its children).
 * Native keyboard handling is mirrored by making the `<button>` the
 * focusable target, Enter/Space toggle naturally.
 */
function GroupCard({
  group,
  defaultOpen,
  scanId,
}: {
  group: FindingsGroup;
  defaultOpen: boolean;
  scanId: number;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Card className="overflow-hidden">
      {/* eslint-disable-next-line react/forbid-elements -- Convert: a card-header disclosure, the job of Disclosure in ui.tsx */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex min-h-target w-full flex-wrap items-center justify-between gap-3 px-4 py-3 text-left hover:bg-surface-muted/60"
      >
        <span className="flex items-center gap-3">
          {open ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-fg-subtle" aria-hidden />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-fg-subtle" aria-hidden />
          )}
          <SeverityChip value={group.worst_severity} />
          <span className="text-base font-semibold text-fg">{group.label}</span>
        </span>
        <span className="text-sm text-fg-muted">
          <strong className="text-fg">{group.finding_count}</strong>{" "}
          image{group.finding_count !== 1 ? "s" : ""}
          {" · "}
          <strong className="text-fg">{group.occurrence_count}</strong>{" "}
          occurrence{group.occurrence_count !== 1 ? "s" : ""}
        </span>
      </button>

      {open && (
        <div className="border-t border-border px-4 py-3">
          {group.remediation_hint && (
            <div className="mb-3 border-l-4 border-umich-blue bg-umich-blue/5 px-3 py-2">
              <div className="flex items-start gap-2">
                <Lightbulb
                  className="mt-0.5 h-4 w-4 shrink-0 text-umich-blue"
                  aria-hidden
                />
                <p className="text-sm text-fg">
                  <strong>Suggested fix:</strong> {group.remediation_hint}
                </p>
              </div>
            </div>
          )}

          <div className="mb-2 flex flex-wrap gap-4 text-xs text-fg-muted">
            <span>
              <strong className="text-fg">Severity:</strong>{" "}
              {(["critical", "major", "minor", "info"] as const)
                .filter((s) => group.severity_breakdown[s])
                .map((s) => `${s} (${group.severity_breakdown[s]})`)
                .join(" · ") || "None"}
            </span>
            <span>
              <strong className="text-fg">Status:</strong>{" "}
              {Object.entries(group.status_breakdown)
                .map(([k, v]) => `${STATUS_LABEL[k as FindingStatus] ?? k} (${v})`)
                .join(" · ") || "None"}
            </span>
          </div>

          {/* Bulk-status, the whole point of this view. Apply one
              decision to every finding in the group in one POST. */}
          <BulkStatusBar
            scanId={scanId}
            findingIds={group.findings.map((f) => f.id)}
            groupLabel={group.label}
            kind="image"
          />

          <FindingsInGroup findings={group.findings} label={group.label} />
        </div>
      )}
    </Card>
  );
}

/**
 * Bulk-status action row.
 *
 * Reused by both the image-of-text grouped view and the WCAG axe
 * grouped view (once that lands), switch by `kind`. The destructive
 * transitions (`accepted_risk`, `false_positive`, `remediated`) get a
 * rationale prompt naming exactly how many findings the action will touch and
 * which group. `in_progress` also requires rationale because it now means the
 * expert confirmed an open barrier. UD #5 (Tolerance for Error) applies more
 * here than for single-finding edits because the blast radius is bigger.
 */
function BulkStatusBar({
  scanId,
  findingIds,
  groupLabel,
  kind,
}: {
  scanId: number;
  findingIds: number[];
  groupLabel: string;
  kind: "image" | "axe";
}) {
  const qc = useQueryClient();
  const [target, setTarget] = useState<FindingStatus>("reviewing");
  const mutation = useMutation({
    mutationFn: ({ next, rationale }: { next: FindingStatus; rationale: string }) =>
      kind === "image"
        ? api.bulkSetStatus(findingIds, next, rationale || undefined)
        : api.bulkSetA11yStatus(findingIds, next, rationale || undefined),
    onSuccess: () => {
      // Refresh the grouped view so counts + status breakdowns update.
      // Also bust the scan/finding caches because the per-finding
      // detail page and the flat table share state with this view.
      void qc.invalidateQueries({ queryKey: ["grouped-findings", scanId] });
      void qc.invalidateQueries({ queryKey: ["a11y-rollup", scanId] });
      void qc.invalidateQueries({ queryKey: ["a11y-drill", scanId] });
      void qc.invalidateQueries({ queryKey: ["findings", scanId] });
      void qc.invalidateQueries({ queryKey: ["scan", scanId] });
    },
  });
  const onApply = () => {
    const rationale = requestStatusRationale(
      target,
      `all ${findingIds.length} images in "${groupLabel}"`,
    );
    if (rationale === null) return;
    mutation.mutate({ next: target, rationale });
  };

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xs border border-border bg-surface-muted/40 px-3 py-2 text-sm">
      <Select
        id={`bulk-status-${findingIds[0] ?? "empty"}`}
        label="New status for all:"
        value={target}
        onChange={(next) => setTarget(next as FindingStatus)}
        disabled={mutation.isPending || findingIds.length === 0}
        options={STATUS_OPTIONS.map((s) => ({ value: s, label: STATUS_OPTION_LABEL[s] }))}
      />
      <Button
        type="button"
        variant="primary"
        onClick={onApply}
        disabled={mutation.isPending || findingIds.length === 0}
      >
        {mutation.isPending
          ? "Changing…"
          : `Change status of all ${findingIds.length}`}
      </Button>
      {mutation.isSuccess && (
        <span className="text-xs text-fg-subtle" role="status">
          Status changed for {mutation.data?.updated ?? 0}
        </span>
      )}
      {mutation.isError && (
        <span className="text-xs text-sev-critical" role="alert">
          {mutation.error instanceof Error
            ? mutation.error.message
            : "Status not changed. Try again."}
        </span>
      )}
    </div>
  );
}

function FindingsInGroup({ findings, label }: { findings: GroupedFinding[]; label: string }) {
  // One table per group, so the page is kept per group rather than in the URL.
  // A new row set (a status filter, a bulk update) starts it over.
  const resetKey = useMemo(() => findings.map((f) => f.id).join(","), [findings]);
  const paged = usePagedRows(findings, { local: true, resetKey });
  return (
    <>
      {paged.pages > 1 && (
        <TableBar pager={<TablePagination label="Images in this group" noun="images" {...paged} />} />
      )}
      <TableRegion label={`${label} images table`} paged={paged}>
        <Table caption={`Images in ${label}`}>
          <TableHead>
            <tr>
              <ColumnHeader>Image</ColumnHeader>
              <ColumnHeader>Text read from image (OCR)</ColumnHeader>
              <ColumnHeader>Severity</ColumnHeader>
              <ColumnHeader>Status</ColumnHeader>
              <ColumnHeader>Pages</ColumnHeader>
            </tr>
          </TableHead>
          <tbody>
            {paged.pageRows.map((f, index) => (
              <FindingRow key={f.id} finding={f} index={(paged.page - 1) * paged.pageSize + index} />
            ))}
          </tbody>
        </Table>
      </TableRegion>
    </>
  );
}

function FindingRow({ finding, index }: { finding: GroupedFinding; index: number }) {
  const [showPages, setShowPages] = useState(false);
  return (
    <Row index={index}>
      <Cell>
        {finding.has_svg_text ? (
          <span className="inline-flex h-12 w-[72px] items-center justify-center rounded-xs border border-dashed border-umich-blue/40 bg-umich-blue/5 font-mono text-2xs font-semibold text-umich-blue">
            SVG text
          </span>
        ) : finding.content_hash ? (
          // The thumbnail is the row's only link to the image's page, so its
          // alt names where it goes ("Open image #12", the terms table's
          // "Image #12"): with alt="" the link had no name at all (SC 2.4.4
          // Link Purpose (In Context) and SC 4.1.2 Name, Role, Value, both
          // Level A; technique H30). A description of the picture was
          // rejected: it is the scanned site's image, and the link's job is
          // to say where it leads.
          <Link to={`/findings/${finding.id}`} className="inline-block">
            {/* eslint-disable-next-line jsx-a11y/img-redundant-alt -- "image" names the record the link opens ("Image #12", docs/plain-language.md), not the picture */}
            <img
              src={blobUrl(finding.content_hash)}
              alt={`Open image #${finding.id}`}
              loading="lazy"
              decoding="async"
              className="h-12 w-[72px] rounded-xs border border-border bg-white object-contain"
            />
          </Link>
        ) : (
          <span className="text-fg-muted">No image</span>
        )}
      </Cell>
      <Cell>
        {finding.ocr_text ? (
          <>
            <code className="block max-w-md break-words font-mono text-xs text-fg">
              {finding.ocr_text.length > 120
                ? `${finding.ocr_text.slice(0, 120)}…`
                : finding.ocr_text}
            </code>
            {finding.ocr_confidence !== null && (
              <div className="mt-1 text-2xs text-fg-muted">
                Confidence: {Math.round(finding.ocr_confidence)}%
              </div>
            )}
          </>
        ) : (
          <span className="text-fg-muted">No text found</span>
        )}
      </Cell>
      <Cell>
        <SeverityChip value={finding.severity} />
      </Cell>
      <Cell>
        <StatusChip value={finding.status} />
      </Cell>
      <Cell>
        {/* Per-finding occurrence drawer, keyed off a local toggle so
            opening row 3 doesn't change row 4. Collapsed by default
            because most findings appear on 1-3 pages and the row stays
            scannable; expanded reveals every page + alt + above-fold. */}
        {/* eslint-disable-next-line react/forbid-elements -- Convert: a text-link styled disclosure; needs a link variant on Button */}
        <button
          type="button"
          onClick={() => setShowPages((v) => !v)}
          aria-expanded={showPages}
          className="text-xs text-umich-blue underline underline-offset-2"
        >
          <span aria-hidden>{showPages ? "▾" : "▸"}</span> {finding.occurrences.length} page
          {finding.occurrences.length !== 1 ? "s" : ""}
        </button>
        {showPages && (
          <ul className="mt-2 space-y-1 text-xs">
            {finding.occurrences.map((occ) => (
              <li key={`${occ.page_id}-${occ.position}`}>
                {/* Compact inline page link, opens the actual page in
                    a new tab so the operator can spot-check the
                    occurrence. The previous stub (preventDefault) was
                    a stub from an earlier phase; users could see a
                    URL but not click it. Fixed under the visible-
                    links rule (accessibility.md §4.5). */}
                <a
                  href={occ.page_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-mono text-fg-muted underline underline-offset-2"
                  title={occ.page_url}
                >
                  {occ.page_url.length > 60
                    ? `…${occ.page_url.slice(-60)}`
                    : occ.page_url}
                  <span aria-hidden> ↗</span>
                  <span className="sr-only">opens in a new tab</span>
                </a>
                <Link
                  to={`/pages/${occ.page_id}`}
                  className="ml-2 text-2xs text-fg-muted underline underline-offset-2"
                >
                  Page details
                </Link>
                <span className="ml-2 text-fg-muted">
                  Alt text:{" "}
                  {occ.alt_text === null ? (
                    <em className="text-sev-critical">missing</em>
                  ) : occ.alt_text === "" ? (
                    <em>empty (&quot;&quot;)</em>
                  ) : (
                    <>&ldquo;{occ.alt_text}&rdquo;</>
                  )}
                </span>
                {occ.above_fold && (
                  <span className="ml-1 text-fg-muted">(visible without scrolling)</span>
                )}
              </li>
            ))}
          </ul>
        )}
        <Link
          to={`/findings/${finding.id}`}
          className="mt-1 block text-2xs text-umich-blue underline underline-offset-2"
        >
          Review this image →
        </Link>
      </Cell>
    </Row>
  );
}
