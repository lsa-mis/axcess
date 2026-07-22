import { Link, useParams, useSearchParams } from "react-router-dom";
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
  StatCard,
} from "../components/ui";
import type {
  A11yRuleGroup,
  A11yRuleGroupFinding,
  AxeImpact,
  FindingStatus,
  Severity,
} from "../api/types";

const STATUS_OPTIONS: FindingStatus[] = [
  "new",
  "reviewing",
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
];

/**
 * WCAG axe findings, grouped by rule — the actionable cut.
 *
 * The existing /a11y route groups by WCAG SC (the *reporting* axis: "we
 * fail 1.4.3 on 47 pages"). This one groups by axe `rule_id` (the
 * *fixing* axis: "color-contrast fails 800 times — one CSS class").
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

  const { data: scan, error: scanError } = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
  });
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
        crumbs={[
          { label: "Scans", to: "/scans" },
          { label: `Scan #${scan.id}`, to: `/scans/${scan.id}` },
          { label: "WCAG findings", to: `/scans/${scan.id}/a11y` },
          { label: "by rule" },
        ]}
        title="WCAG findings — grouped by rule"
        subtitle={scan.seed_url}
        actions={
          <LinkButton to={`/scans/${scan.id}/a11y`} variant="secondary">
            Group by WCAG SC
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
            <strong>How this view groups findings.</strong> Findings are
            grouped by axe <code>rule_id</code> — the <em>fixing</em>{" "}
            axis. A rule like <code>color-contrast</code> failing 800
            times is usually one CSS class on one template; seeing one
            group of 800 tells you where one fix has the biggest payoff.{" "}
            <Link
              to={`/scans/${scan.id}/a11y`}
              className="text-umich-blue underline underline-offset-2"
            >
              Group-by-SC
            </Link>{" "}
            is the reporting axis — useful when stakeholders ask
            &ldquo;which WCAG SCs are we failing?&rdquo;
          </p>
        </div>
      </Card>

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard label="Rules with failures" value={groups.length} />
        <StatCard label="Total violations" value={coverage.axe_violations_total} />
        <StatCard
          label="Pages scanned"
          value={coverage.axe_pages_scanned}
          hint={`of ${coverage.pages_total}`}
        />
      </div>

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
              ? "No axe violations match this filter"
              : "No axe violations to triage"
          }
          message={
            status
              ? "Clear the filter to see violations in other statuses."
              : coverage.axe_pages_scanned === 0
                ? "Axe didn't run on this scan — re-run with “Use real browser” enabled."
                : "Axe ran cleanly. Remember the scope caveat: axe checks ~30-40% of WCAG SCs."
          }
        />
      ) : (
        <div className="space-y-3">
          {groups.map((g, i) => (
            <RuleGroupCard
              key={g.rule_id}
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
          <code className="font-mono text-base font-semibold text-fg">
            {group.rule_id}
          </code>
          {group.wcag_sc && (
            <span className="text-sm text-fg-muted">
              SC {group.wcag_sc}
              {group.wcag_level && ` · Level ${group.wcag_level}`}
            </span>
          )}
        </span>
        <span className="text-sm text-fg-muted">
          <strong className="text-fg">{group.violation_count}</strong>{" "}
          violation{group.violation_count !== 1 ? "s" : ""} on{" "}
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
                  <strong>What axe says:</strong> {group.help}
                  {group.help_url && (
                    <>
                      {" "}
                      <a
                        href={group.help_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-umich-blue underline underline-offset-2"
                      >
                        rule docs <ExternalLink className="h-3 w-3" aria-hidden />
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
              .map(([k, v]) => `${k} (${v})`)
              .join(" · ") || "—"}
          </div>

          <RuleBulkBar
            scanId={scanId}
            findingIds={group.findings.map((f) => f.id)}
            ruleId={group.rule_id}
          />

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
                <tr>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">
                    Page
                  </th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">
                    Target
                  </th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {group.findings.map((f) => (
                  <FindingRow key={f.id} finding={f} scanId={scanId} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

function FindingRow({ finding, scanId }: { finding: A11yRuleGroupFinding; scanId: number }) {
  return (
    <tr className="align-top">
      <td className="max-w-xs px-3 py-2">
        <PageLink
          pageId={finding.page_id}
          scanId={scanId}
          pageUrl={finding.page_url}
          pageTitle={finding.page_title}
        />
      </td>
      <td className="px-3 py-2">
        <code className="block break-all font-mono text-2xs text-fg">
          {finding.target_selector.length > 90
            ? `${finding.target_selector.slice(0, 90)}…`
            : finding.target_selector}
        </code>
        {finding.html_snippet && (
          <details className="mt-1">
            <summary className="cursor-pointer text-2xs text-fg-subtle">
              show HTML
            </summary>
            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-xs bg-surface-muted p-2 text-2xs">
              {finding.html_snippet}
            </pre>
          </details>
        )}
        {finding.failure_summary && (
          <div className="mt-1 text-2xs text-fg-muted">
            {finding.failure_summary}
          </div>
        )}
      </td>
      <td className="px-3 py-2 text-xs">{finding.status}</td>
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
    mutationFn: (next: FindingStatus) =>
      api.bulkSetA11yStatus(findingIds, next),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["a11y-by-rule", scanId] });
      void qc.invalidateQueries({ queryKey: ["a11y-rollup", scanId] });
      void qc.invalidateQueries({ queryKey: ["a11y-drill", scanId] });
    },
  });
  const destructive: FindingStatus[] = [
    "remediated",
    "accepted_risk",
    "false_positive",
  ];

  const onApply = () => {
    if (destructive.includes(target)) {
      const ok = window.confirm(
        `Mark all ${findingIds.length} violations of "${ruleId}" as ${target}? ` +
          "This is reversible.",
      );
      if (!ok) return;
    }
    mutation.mutate(target);
  };

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xs border border-border bg-surface-muted/40 px-3 py-2 text-sm">
      <label
        htmlFor={`rule-bulk-${ruleId}`}
        className="font-semibold text-fg"
      >
        Bulk status:
      </label>
      <select
        id={`rule-bulk-${ruleId}`}
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

/** Mirror of the chip used in the by-SC view — keep both in sync. */
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
      className={`inline-flex items-center rounded-xs px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide text-white bg-sev-${tone}-bg`}
    >
      {value}
    </span>
  );
}
