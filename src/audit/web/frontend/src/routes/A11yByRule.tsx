import AlfaEvidenceNote from "../components/AlfaEvidenceNote";
import { Link, useParams, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Info,
  Lightbulb,
} from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import {
  Button,
  Card,
  EmptyState,
  LinkButton,
  PageHeader,
  PageLink,
  pageEvidencePath,
  Select,
  StatCard,
} from "../components/ui";
import type {
  A11yRuleGroup,
  A11yRuleGroupFinding,
  AxeImpact,
  FindingStatus,
  Severity,
} from "../api/types";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import { requestStatusRationale } from "../statusDecision";
import { useScanQuery } from "../hooks/useScanQuery";
import { CHECK_LABEL, STATUS_LABEL, STATUS_OPTION_LABEL } from "../lib/terms";

const STATUS_OPTIONS: FindingStatus[] = [
  "new",
  "reviewing",
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
];

/**
 * WCAG DOM-engine findings, grouped by rule, the actionable cut.
 *
 * The existing /a11y route groups by WCAG SC (the *reporting* axis: "we
 * fail 1.4.3 on 47 pages"). This one groups by axe `rule_id` (the
 * *fixing* axis: "color-contrast fails 800 times, one CSS class").
 * Bulk-status lives per group: one decision touches every violation
 * of one rule.
 */
export default function A11yByRuleRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const rawStatus = params.get("status") ?? "";
  const status = (
    STATUS_OPTIONS.includes(rawStatus as FindingStatus) ? rawStatus : ""
  ) as FindingStatus | "";

  const { data: scan, error: scanError } = useScanQuery(id);
  const { data, isLoading } = useQuery({
    queryKey: ["a11y-by-rule", id, status],
    queryFn: () => api.getA11yByRule(id, status || undefined),
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
        title="Rule check issues by rule"
        subtitle={scan.seed_url}
        actions={
          <LinkButton to={`/scans/${scan.id}/a11y`} variant="secondary">
            Group by WCAG criterion
            <ChevronRight className="h-4 w-4" aria-hidden />
          </LinkButton>
        }
      />

      <Card
        className="mb-4 border-umich-blue/30 bg-umich-blue/5 p-4"
        role="note"
      >
        <div className="flex items-start gap-3">
          <Info className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue" aria-hidden />
          <p className="text-sm text-fg">
            <strong>How this page groups issues.</strong> Each issue is one
            rule from one check. This view helps you <em>plan fixes</em>. For
            example, the <code>color-contrast</code> rule may fail 800 times.
            Often one style (CSS class) in one page template causes all of
            them, so one fix solves all 800. To report by requirement,{" "}
            <Link
              to={`/scans/${scan.id}/a11y`}
              className="text-umich-blue underline underline-offset-2"
            >
              group by WCAG criterion
            </Link>{" "}
            instead. That view answers &ldquo;which WCAG criteria have
            problems?&rdquo;
          </p>
        </div>
      </Card>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard label="Issues" value={groups.length} />
        <StatCard label="Occurrences (axe)" value={coverage.axe_violations_total} />
        <StatCard label="Failed (Alfa)" value={coverage.alfa_failed_total} />
        <StatCard label="Needs review (Alfa)" value={coverage.alfa_cant_tell_total} />
        <StatCard
          label="Pages checked (axe)"
          value={coverage.axe_pages_scanned}
          hint={`of ${coverage.pages_total}`}
        />
      </div>

      <Card className="mb-4 p-3">
        <Select
          stacked
          label="Filter by status"
          value={status}
          onChange={(next) => setStatusParam(next as FindingStatus | "")}
          options={[
            { value: "", label: "All statuses" },
            ...STATUS_OPTIONS.map((s) => ({ value: s, label: STATUS_OPTION_LABEL[s] })),
          ]}
        />
      </Card>

      {groups.length === 0 ? (
        <EmptyState
          title={
            status
              ? "No issues have this status"
              : "The rule checks found no issues to review"
          }
          message={
            status
              ? "Choose All statuses to see the other issues."
              : coverage.axe_pages_scanned === 0 && coverage.alfa_pages_scanned === 0
                ? "No rule check ran in this scan. Start a new scan and choose Rule check (axe), Rule check (Alfa), or both."
                : "The rule checks you chose found nothing to keep. A person still needs to test the site by hand. Automated checks alone cannot show that a site meets WCAG."
          }
        />
      ) : (
        <div className="space-y-3">
          {groups.map((g, i) => (
            <RuleGroupCard
              key={`${g.pipeline}:${g.rule_id}:${g.outcome_group ?? "all"}`}
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

function RuleGroupCard({
  group,
  defaultOpen,
  scanId,
}: {
  group: A11yRuleGroup;
  defaultOpen: boolean;
  scanId: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  // One table per rule, so the page is kept per card rather than in the URL.
  const paged = usePagedRows(group.findings, {
    local: true,
    resetKey: group.findings.map((f) => f.id).join(","),
  });

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
          {group.impact && <ImpactChip value={group.impact} />}
          <span className="rounded-full bg-surface-muted px-2 py-0.5 text-xs font-semibold text-fg-muted">
            {CHECK_LABEL[group.pipeline] ?? group.pipeline}
          </span>
          {group.pipeline === "alfa" && group.outcome_group && (
            <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${group.outcome_group === "failed" ? "bg-sev-critical-bg text-sev-critical" : "bg-sev-minor-bg text-sev-minor"}`}>
              {group.outcome_group === "failed" ? "Failed a standard test (ACT)" : "Needs review (Alfa cannot tell)"}
            </span>
          )}
          <code className="font-mono text-base font-semibold text-fg">
            {group.rule_id}
          </code>
          {group.wcag_sc && (
            <span className="text-sm text-fg-muted">
              WCAG {group.wcag_sc}
              {group.wcag_level && ` · Level ${group.wcag_level}`}
            </span>
          )}
        </span>
        <span className="text-sm text-fg-muted">
          <strong className="text-fg">{group.violation_count}</strong>{" "}
          occurrence{group.violation_count !== 1 ? "s" : ""} on{" "}
          <strong className="text-fg">{group.page_count}</strong> page
          {group.page_count !== 1 ? "s" : ""}
        </span>
      </button>

      {open && (
        <div className="border-t border-border px-4 py-3">
          {group.help && (
            <div className="mb-3 border-l-4 border-umich-blue bg-umich-blue/5 px-3 py-2">
              <div className="flex items-start gap-2">
                <Lightbulb
                  className="mt-0.5 h-4 w-4 shrink-0 text-umich-blue"
                  aria-hidden
                />
                <p className="text-sm text-fg">
                  <strong>{group.pipeline === "alfa" ? "What the Alfa rule says:" : "What the rule says:"}</strong> {group.help}
                  {group.help_url && (
                    <>
                      {" "}
                      <a
                        href={group.help_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-umich-blue underline underline-offset-2"
                      >
                        About this rule <ExternalLink className="h-3 w-3" aria-hidden />
                        <span className="sr-only">(opens in a new tab)</span>
                      </a>
                    </>
                  )}
                </p>
              </div>
            </div>
          )}

          <div className="mb-2 text-xs text-fg-muted">
            <strong className="text-fg">Status:</strong>{" "}
            {Object.entries(group.status_breakdown)
              .filter(([, v]) => v > 0)
              .map(([k, v]) => `${STATUS_LABEL[k as FindingStatus] ?? k} (${v})`)
              .join(" · ") || "None"}
          </div>
          {group.pipeline === "alfa" && group.engine_outcomes.cant_tell > 0 && (
            <p className="mb-2 text-xs text-fg-muted">
              <strong className="text-fg">Needs review:</strong> For{" "}
              {group.engine_outcomes.cant_tell} occurrence
              {group.engine_outcomes.cant_tell === 1 ? "" : "s"}, Alfa could not
              tell (<code>cantTell</code>) if the rule passed. A person needs to
              check {group.engine_outcomes.cant_tell === 1 ? "it" : "them"}.{" "}
              {group.engine_outcomes.cant_tell === 1 ? "It does" : "They do"} not
              show that the page fails WCAG.
            </p>
          )}

          <RuleBulkBar
            scanId={scanId}
            findingIds={group.findings.map((f) => f.id)}
            ruleId={group.rule_id}
          />

          <div className="overflow-x-auto">
            {/* Holds the tallest page's height, so paging never moves the pager. */}
            <div {...paged.hold}>
            <table className="w-full text-sm">
              <thead className="bg-surface-muted text-2xs text-fg-subtle">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">
                    Page
                  </th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">
                    Element locator (CSS selector)
                  </th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {paged.pageRows.map((f) => (
                  <FindingRow key={f.id} finding={f} scanId={scanId} ruleId={group.rule_id} />
                ))}
              </tbody>
            </table>
            </div>
          </div>
          <TablePagination label={`${group.rule_id} occurrences`} noun="occurrences" {...paged} />
        </div>
      )}
    </Card>
  );
}

function FindingRow({
  finding,
  scanId,
  ruleId,
}: {
  finding: A11yRuleGroupFinding;
  scanId: number;
  ruleId: string;
}) {
  return (
    <tr className="align-top">
      <td className="max-w-xs px-3 py-2">
        <PageLink
          pageId={finding.page_id}
          scanId={scanId}
          pageUrl={finding.page_url}
          pageTitle={finding.page_title}
          selector={finding.target_selector}
          snippet={finding.html_snippet}
          origin="Rule check issues by rule"
          context={ruleId}
          backTo={`/scans/${scanId}/a11y/by-rule`}
        />
      </td>
      <td className="px-3 py-2">
        <code className="block break-all font-mono text-2xs text-fg">
          {(finding.target_display || finding.target_selector).length > 90
            ? `${(finding.target_display || finding.target_selector).slice(0, 90)}…`
            : (finding.target_display || finding.target_selector)}
        </code>
        {finding.html_snippet && (
          <details className="mt-1">
            <summary className="cursor-pointer text-2xs text-fg-subtle">
              Show element code (HTML)
            </summary>
            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-xs bg-surface-muted p-2 text-2xs">
              {finding.html_snippet}
            </pre>
          </details>
        )}
        <AlfaEvidenceNote evidence={finding} />
        <Link className="report-link inline-flex min-h-target items-center text-xs" to={pageEvidencePath({ scanId, pageId: finding.page_id, origin: "Rule check issues by rule", backTo: `/scans/${scanId}/a11y/by-rule`, hash: `#finding-${finding.id}` })}>Open the evidence for this occurrence</Link>
        {finding.failure_summary && (
          <div className="mt-1 text-2xs text-fg-muted">
            {finding.failure_summary}
          </div>
        )}
      </td>
      <td className="px-3 py-2 text-xs">{STATUS_LABEL[finding.status]}</td>
    </tr>
  );
}

function RuleBulkBar({
  scanId,
  findingIds,
  ruleId,
}: {
  scanId: number;
  findingIds: number[];
  ruleId: string;
}) {
  const qc = useQueryClient();
  const [target, setTarget] = useState<FindingStatus>("reviewing");
  const mutation = useMutation({
    mutationFn: ({ next, rationale }: { next: FindingStatus; rationale: string }) =>
      api.bulkSetA11yStatus(findingIds, next, rationale || undefined),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["a11y-by-rule", scanId] });
      void qc.invalidateQueries({ queryKey: ["a11y-rollup", scanId] });
      void qc.invalidateQueries({ queryKey: ["a11y-drill", scanId] });
    },
  });
  const onApply = () => {
    const rationale = requestStatusRationale(
      target,
      `all ${findingIds.length} occurrences of "${ruleId}"`,
    );
    if (rationale === null) return;
    mutation.mutate({ next: target, rationale });
  };

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xs border border-border bg-surface-muted/40 px-3 py-2 text-sm">
      <Select
        id={`rule-bulk-${ruleId}`}
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

/** Mirror of the chip used in the by-SC view, keep both in sync. */
function ImpactChip({ value }: { value: AxeImpact }) {
  const tone: Severity = (
    {
      critical: "critical",
      serious: "major",
      moderate: "minor",
      minor: "info",
    } as const
  )[value];
  return (
    <span
      className={`inline-flex items-center rounded-xs px-1.5 py-0.5 text-2xs font-semibold text-white bg-sev-${tone}-bg`}
    >
      {value}
    </span>
  );
}
