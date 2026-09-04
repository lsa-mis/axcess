import { Link, useParams, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Info, Lightbulb } from "lucide-react";
import { useState } from "react";
import { api, blobUrl } from "../api/client";
import {
  Button,
  Card,
  EmptyState,
  LinkButton,
  PageHeader,
  SeverityChip,
  StatCard,
  StatusChip,
} from "../components/ui";
import type {
  FindingStatus,
  FindingsGroup,
  GroupedFinding,
} from "../api/types";
import { requestStatusRationale } from "../statusDecision";

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
 * The parallel to the WCAG axe rollup at `/scans/:id/a11y` — instead of
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

  const { data: scan, error: scanError } = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
  });
  const { data, isLoading } = useQuery({
    queryKey: ["grouped-findings", id, status],
    queryFn: () => api.getGroupedFindings(id, status || undefined),
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

  return (
    <>
      <PageHeader
        title="Image-of-text findings — grouped by issue"
        subtitle={scan.seed_url}
        actions={
          <LinkButton to={`/scans/${scan.id}/findings`} variant="secondary">
            Show flat table
            <ChevronRight className="h-4 w-4" aria-hidden />
          </LinkButton>
        }
      />

      {/* Up-front explainer — analogue of the WCAG view's scope-honesty
          banner. The story here is different: every group has one fix,
          so the operator decides once per group instead of per row. */}
      <Card
        className="mb-4 border-umich-blue/30 bg-umich-blue/5 p-4"
        role="note"
      >
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
          <p className="text-sm text-fg">
            <strong>How this view groups findings.</strong> Findings are
            bucketed by <code>(classification, alt&nbsp;adequacy)</code> —
            the same pair our remediation rule book is keyed on. Everything
            in one group has the <em>same recommended fix</em>, so you can
            decide once per group instead of once per row. Expand a group
            to see the individual images and the pages where each appears.
          </p>
        </div>
      </Card>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Findings" value={coverage.finding_count} />
        <StatCard label="Issue groups" value={groups.length} />
        <StatCard label="Occurrences" value={coverage.occurrence_total} />
        <StatCard label="Pages crawled" value={coverage.page_count} />
      </div>

      {/* Status filter — URL-persistent, auto-applies on change. Same
          UX shape as the WCAG drill-down filter. */}
      <Card className="mb-4 p-3">
        <label className="flex flex-col text-xs font-semibold uppercase tracking-wide text-fg-subtle">
          Status filter
          <select
            value={status}
            onChange={(e) =>
              setStatusParam(e.target.value as FindingStatus | "")
            }
            className="mt-1 min-h-target rounded-xs border border-border bg-surface px-2 py-2 text-base font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
          >
            <option value="">all statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </label>
      </Card>

      {groups.length === 0 ? (
        <EmptyState
          title={
            status
              ? "No findings match this status filter"
              : "No image-of-text findings"
          }
          message={
            status
              ? "Clear the filter to see findings in other statuses."
              : "Either none were detected on this scan, or synthesis didn't run yet."
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
 * One group card — header summarizes the bucket, the body shows the
 * shared remediation hint and a table of the individual findings.
 *
 * We use a controlled `useState` toggle rather than the browser-native
 * `<details>` element here because the surrounding components are
 * already React; mixing imperative DOM state with React state is a
 * footgun (closing the details element doesn't unmount its children).
 * Native keyboard handling is mirrored by making the `<button>` the
 * focusable target — Enter/Space toggle naturally.
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
          finding{group.finding_count !== 1 ? "s" : ""}
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
                .join(" · ") || "—"}
            </span>
            <span>
              <strong className="text-fg">Status:</strong>{" "}
              {Object.entries(group.status_breakdown)
                .map(([k, v]) => `${k} (${v})`)
                .join(" · ") || "—"}
            </span>
          </div>

          {/* Bulk-status — the whole point of this view. Apply one
              decision to every finding in the group in one POST. */}
          <BulkStatusBar
            scanId={scanId}
            findingIds={group.findings.map((f) => f.id)}
            groupLabel={group.label}
            kind="image"
          />

          <FindingsInGroup findings={group.findings} />
        </div>
      )}
    </Card>
  );
}

/**
 * Bulk-status action row.
 *
 * Reused by both the image-of-text grouped view and the WCAG axe
 * grouped view (once that lands) — switch by `kind`. The destructive
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
      `all ${findingIds.length} findings in "${groupLabel}"`,
    );
    if (rationale === null) return;
    mutation.mutate({ next: target, rationale });
  };

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xs border border-border bg-surface-muted/40 px-3 py-2 text-sm">
      <label
        htmlFor={`bulk-status-${findingIds[0] ?? "empty"}`}
        className="font-semibold text-fg"
      >
        Bulk status:
      </label>
      <select
        id={`bulk-status-${findingIds[0] ?? "empty"}`}
        value={target}
        onChange={(e) => setTarget(e.target.value as FindingStatus)}
        disabled={mutation.isPending || findingIds.length === 0}
        className="min-h-target rounded-xs border border-border bg-surface px-2 py-1 text-base text-fg focus:border-umich-blue focus:outline-none disabled:opacity-60"
      >
        {STATUS_OPTIONS.map((s) => (
          <option key={s} value={s}>
            {s.replace(/_/g, " ")}
          </option>
        ))}
      </select>
      <Button
        type="button"
        variant="primary"
        onClick={onApply}
        disabled={mutation.isPending || findingIds.length === 0}
      >
        {mutation.isPending
          ? "Updating…"
          : `Apply to all ${findingIds.length}`}
      </Button>
      {mutation.isSuccess && (
        <span className="text-xs text-fg-subtle" role="status">
          Updated {mutation.data?.updated ?? 0}
        </span>
      )}
      {mutation.isError && (
        <span className="text-xs text-sev-critical" role="alert">
          {mutation.error instanceof Error
            ? mutation.error.message
            : "Bulk update failed"}
        </span>
      )}
    </div>
  );
}

function FindingsInGroup({ findings }: { findings: GroupedFinding[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
          <tr>
            <th scope="col" className="px-3 py-2 text-left font-semibold">
              Image
            </th>
            <th scope="col" className="px-3 py-2 text-left font-semibold">
              OCR text
            </th>
            <th scope="col" className="px-3 py-2 text-left font-semibold">
              Severity
            </th>
            <th scope="col" className="px-3 py-2 text-left font-semibold">
              Status
            </th>
            <th scope="col" className="px-3 py-2 text-left font-semibold">
              Pages
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {findings.map((f) => (
            <FindingRow key={f.id} finding={f} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FindingRow({ finding }: { finding: GroupedFinding }) {
  const [showPages, setShowPages] = useState(false);
  return (
    <tr className="align-top">
      <td className="px-3 py-2">
        {finding.has_svg_text ? (
          <span className="inline-flex h-12 w-[72px] items-center justify-center rounded-xs border border-dashed border-umich-blue/40 bg-umich-blue/5 font-mono text-2xs font-semibold text-umich-blue">
            SVG text
          </span>
        ) : finding.content_hash ? (
          <Link to={`/findings/${finding.id}`} className="inline-block">
            <img
              src={blobUrl(finding.content_hash)}
              alt=""
              loading="lazy"
              decoding="async"
              className="h-12 w-[72px] rounded-xs border border-border bg-white object-contain"
            />
          </Link>
        ) : (
          <span className="text-fg-subtle">—</span>
        )}
      </td>
      <td className="px-3 py-2">
        {finding.ocr_text ? (
          <>
            <code className="block max-w-md break-words font-mono text-xs text-fg">
              {finding.ocr_text.length > 120
                ? `${finding.ocr_text.slice(0, 120)}…`
                : finding.ocr_text}
            </code>
            {finding.ocr_confidence !== null && (
              <div className="mt-1 text-2xs text-fg-subtle">
                confidence {Math.round(finding.ocr_confidence)}%
              </div>
            )}
          </>
        ) : (
          <span className="text-fg-subtle">—</span>
        )}
      </td>
      <td className="px-3 py-2">
        <SeverityChip value={finding.severity} />
        <div className="mt-1 text-2xs text-fg-subtle">
          priority {finding.priority_score.toFixed(2)}
        </div>
      </td>
      <td className="px-3 py-2">
        <StatusChip value={finding.status} />
      </td>
      <td className="px-3 py-2">
        {/* Per-finding occurrence drawer — keyed off a local toggle so
            opening row 3 doesn't change row 4. Collapsed by default
            because most findings appear on 1-3 pages and the row stays
            scannable; expanded reveals every page + alt + above-fold. */}
        <button
          type="button"
          onClick={() => setShowPages((v) => !v)}
          aria-expanded={showPages}
          className="text-xs text-umich-blue underline underline-offset-2"
        >
          {showPages ? "▾" : "▸"} {finding.occurrences.length} page
          {finding.occurrences.length !== 1 ? "s" : ""}
        </button>
        {showPages && (
          <ul className="mt-2 space-y-1 text-xs">
            {finding.occurrences.map((occ) => (
              <li key={`${occ.page_id}-${occ.position}`}>
                {/* Compact inline page link — opens the actual page in
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
                  className="ml-2 text-2xs text-fg-subtle underline underline-offset-2"
                >
                  view in audit
                </Link>
                <span className="ml-2 text-fg-subtle">
                  alt=
                  {occ.alt_text === null ? (
                    <em className="text-sev-critical">missing</em>
                  ) : occ.alt_text === "" ? (
                    <em>&quot;&quot;</em>
                  ) : (
                    <>&ldquo;{occ.alt_text}&rdquo;</>
                  )}
                </span>
                {occ.above_fold && (
                  <span className="ml-1 text-fg-subtle">(above fold)</span>
                )}
              </li>
            ))}
          </ul>
        )}
        <Link
          to={`/findings/${finding.id}`}
          className="mt-1 block text-2xs text-umich-blue underline underline-offset-2"
        >
          triage finding →
        </Link>
      </td>
    </tr>
  );
}
