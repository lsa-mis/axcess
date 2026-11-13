import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { api } from "../../api/client";
import type { CoverageFound } from "../../api/types";
import { cn } from "../../lib/cn";
import { AXE_CATEGORY_LABEL, FOUND_LAYER_LABEL } from "../../lib/terms";
import Loading from "../Loading";
import { Button, Card, EmptyState, LinkButton, Select } from "../ui";
import { Cell, ColumnHeader, Row, RowHeader, Table, TableHead, TableRegion } from "../table/Table";
import { ExternalTextLink, compareSc, formatCount, percent } from "./coverageParts";

type GroupBy = "kind" | "criterion" | "rule";
type AxeRule = CoverageFound["axe_rules"][number];

/**
 * What Axcess found in this computer's completed reports (the second part of
 * Coverage). Counted by the server on each request (audit/web/issue_share.py),
 * and the query is fetched again when the window regains focus, so the
 * numbers change as soon as a scan completes without a reload. Nothing leaves
 * this computer.
 *
 * Three figures, each named for what it is: an exact count, an estimate, and a
 * criterion-level comparison. Each carries its tag in words, never colour
 * alone (SC 1.4.1 Use of Color, Level A), and none claims conformance.
 */
export default function FoundView() {
  const [params, setParams] = useSearchParams();
  const report = Number(params.get("report") ?? "") || undefined;
  const { data, isLoading, error } = useQuery({
    queryKey: ["coverage-found", report ?? "all"],
    queryFn: () => api.getCoverageFound(report),
    refetchOnWindowFocus: "always",
  });
  const set = (updates: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(updates)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
  };

  if (error) {
    return (
      <Card className="p-4">
        <p role="alert" className="text-sm text-sev-critical">
          Axcess could not count your reports: {error instanceof Error ? error.message : String(error)}
        </p>
        <p className="mt-2 text-sm">
          <Link to="/coverage/found" className="text-umich-blue underline underline-offset-2">
            Count all completed reports
          </Link>
        </p>
      </Card>
    );
  }
  if (isLoading || !data) return <Loading label="Counting your reports" />;
  if (data.scans_completed === 0) {
    return (
      <EmptyState
        title="No completed reports yet"
        message="These numbers appear after your first scan finishes. Axcess counts them on this computer."
        action={
          <LinkButton to="/scans/new" variant="primary">
            Start a new scan
          </LinkButton>
        }
      />
    );
  }

  const host = (url: string) => {
    try {
      return new URL(url).host;
    } catch {
      return url;
    }
  };
  const total = data.layers.total;

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="found-h">
        <h2 id="found-h" className="text-lg font-semibold text-fg">
          What Axcess found in your reports
        </h2>
        <p className="mt-1 max-w-measure text-base leading-7 text-fg-muted">
          Counted from the reports on this computer, after each scan. No report data leaves this computer.
          Occurrences marked “Not a problem” are left out.
        </p>
      </section>

      {/* The status line sits under the picker, on the same left edge, so the
          choice and what it counts read top to bottom as one block. */}
      <Card className="flex flex-col items-start gap-3 p-5">
        <Select
          label="Reports to count"
          stacked
          className="w-full max-w-md"
          value={report ? String(report) : ""}
          onChange={(value) => set({ report: value })}
          options={[
            {
              value: "",
              label:
                data.scans_completed > data.scans.length
                  ? `All completed reports (the ${data.scans.length} most recent)`
                  : `All completed reports (${data.scans.length})`,
            },
            ...data.scans.map((scan) => ({
              value: String(scan.id),
              label: `Report #${scan.id} · ${host(scan.seed_url)}${scan.finished_at ? ` · ${scan.finished_at.slice(0, 10)}` : ""}`,
            })),
          ]}
        />
        <p role="status" className="max-w-measure text-sm leading-6 text-fg-muted">
          Counting {data.scans_included === 1 ? "1 report" : `${data.scans_included} completed reports`}:{" "}
          {formatCount(total)} occurrences. Left out: {formatCount(data.layers.excluded_not_a_problem)} marked “Not a
          problem” and {formatCount(data.layers.excluded_records)} kept only as records.
        </p>
      </Card>

      <ByCheck data={data} />
      <Estimate data={data} report={report} />
      <ManualReview data={data} />
    </div>
  );
}

function Tag({ tone, children }: { tone: "exact" | "estimate" | "criterion"; children: string }) {
  return (
    <span
      className={cn(
        "rounded-2xs px-2 py-0.5 text-xs font-bold",
        tone === "exact" && "bg-ok-bg text-ok",
        tone === "estimate" && "bg-sev-major-bg text-sev-major",
        tone === "criterion" && "bg-surface-muted text-fg-muted",
      )}
    >
      {children}
    </span>
  );
}

/** A share in words, with a bar that only repeats it (aria-hidden). */
function ShareBar({ value }: { value: number | null }) {
  return (
    <span className="flex items-center gap-3">
      <span className="min-w-16 text-right font-semibold">{percent(value ?? 0)}</span>
      <span aria-hidden className="h-2.5 flex-1 rounded-full bg-surface-muted">
        <span className="block h-2.5 rounded-full bg-umich-blue" style={{ width: `${Math.max((value ?? 0) * 100, value ? 1 : 0)}%` }} />
      </span>
    </span>
  );
}

function ByCheck({ data }: { data: CoverageFound }) {
  const found = data.layers.layers.filter((row) => row.count > 0);
  const none = data.layers.layers.filter((row) => row.count === 0);
  return (
    <Card>
      <section aria-labelledby="by-check-h">
        <div className="flex flex-col gap-2 p-5 pb-2">
          <div className="flex flex-wrap items-center gap-3">
            <h3 id="by-check-h" className="text-base font-semibold text-fg">
              1. Which check found each occurrence
            </h3>
            <Tag tone="exact">Exact count</Tag>
          </div>
          <p className="max-w-measure text-sm leading-6 text-fg-muted">Counted as on the Issues page.</p>
        </div>
        <TableRegion label="Occurrences by check">
          <Table caption="Occurrences found, by check">
            <TableHead>
              <tr>
                <ColumnHeader>Check</ColumnHeader>
                <ColumnHeader>Occurrences</ColumnHeader>
                <ColumnHeader className="w-[38%]">Share of all found</ColumnHeader>
              </tr>
            </TableHead>
            <tbody>
              {found.map((row, index) => (
                <Row key={row.layer} index={index}>
                  <RowHeader className="font-medium">{FOUND_LAYER_LABEL[row.layer]}</RowHeader>
                  <Cell numeric>{formatCount(row.count)}</Cell>
                  <Cell>
                    <ShareBar value={row.share} />
                  </Cell>
                </Row>
              ))}
              <Row index={found.length}>
                <RowHeader>Total</RowHeader>
                <Cell numeric className="font-semibold">
                  {formatCount(data.layers.total)}
                </Cell>
                <Cell className="font-semibold">{data.layers.total ? "100%" : "—"}</Cell>
              </Row>
            </tbody>
          </Table>
        </TableRegion>
        {/* A check that found nothing is a fact about the scan settings or
            the site, not a row worth reading across: it sits under the
            table in muted text, so the table holds only what was found. */}
        {none.length > 0 && (
          <p className="max-w-measure px-5 pt-3 text-sm leading-6 text-fg-muted">
            Found nothing: {none.map((row) => FOUND_LAYER_LABEL[row.layer]).join(", ")}. A check that is off in
            the scan settings finds nothing.
          </p>
        )}
        <AxeBreakdown rules={data.axe_rules} />
      </section>
    </Card>
  );
}

/**
 * The rule check's occurrences split up, grouped by axe-core's own kind of
 * problem, by WCAG criterion, or not at all. A group opens to show its rules;
 * the open/close control is a button in the row header with aria-expanded,
 * the WAI-ARIA APG Disclosure pattern, so the table keeps its row and column
 * headers for a screen reader. Rejected: a tree grid, which needs its own
 * keyboard model for one optional level of detail.
 */
function AxeBreakdown({ rules }: { rules: AxeRule[] }) {
  const [groupBy, setGroupBy] = useState<GroupBy>("kind");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const total = rules.reduce((sum, r) => sum + r.loaded + r.click_through, 0);
  if (!rules.length) return null;
  const sum = (rs: AxeRule[], key: "loaded" | "click_through") => rs.reduce((n, r) => n + r[key], 0);
  const groups: { id: string; label: string; rules: AxeRule[] }[] = [];
  if (groupBy !== "rule") {
    const byKey = new Map<string, AxeRule[]>();
    for (const rule of rules) {
      const key = groupBy === "kind" ? rule.category : (rule.criteria[0] ?? "best-practice");
      byKey.set(key, [...(byKey.get(key) ?? []), rule]);
    }
    for (const [key, rs] of byKey) {
      groups.push({
        id: key,
        label:
          groupBy === "kind"
            ? (AXE_CATEGORY_LABEL[key] ?? AXE_CATEGORY_LABEL.other)
            : key === "best-practice"
              ? "Best practice, not a WCAG criterion"
              : `WCAG ${key}`,
        rules: rs,
      });
    }
    groups.sort((a, b) =>
      groupBy === "criterion" && a.id !== "best-practice" && b.id !== "best-practice"
        ? compareSc(a.id, b.id)
        : sum(b.rules, "loaded") + sum(b.rules, "click_through") - sum(a.rules, "loaded") - sum(a.rules, "click_through"),
    );
  }
  const allOpen = groups.length > 0 && groups.every((g) => open[g.id]);
  let index = 0;
  const ruleRow = (rule: AxeRule, indent: boolean) => (
    <Row key={rule.rule_id} index={index++} className={cn(indent && "bg-surface-subtle")}>
      <RowHeader className={cn("font-normal", indent && "pl-11")}>
        {rule.help} <code className="rounded-2xs bg-surface-muted px-1 text-xs text-fg-muted">{rule.rule_id}</code>
      </RowHeader>
      <Cell numeric>{formatCount(rule.loaded)}</Cell>
      <Cell numeric>{formatCount(rule.click_through)}</Cell>
      <Cell numeric>{formatCount(rule.loaded + rule.click_through)}</Cell>
      <Cell>{percent(total ? (rule.loaded + rule.click_through) / total : 0)}</Cell>
    </Row>
  );

  return (
    <div className="border-t border-border">
      <div className="flex flex-col gap-3 p-5 pb-3">
        <h4 className="text-sm font-semibold text-fg">Rule check (axe): {formatCount(total)} occurrences by type</h4>
        <div className="flex flex-wrap items-end gap-3">
          <Select
            label="Group by"
            stacked
            value={groupBy}
            onChange={(value) => setGroupBy(value as GroupBy)}
            options={[
              { value: "kind", label: "Kind of problem, then rule" },
              { value: "criterion", label: "WCAG criterion, then rule" },
              { value: "rule", label: "Rule only" },
            ]}
          />
          {groupBy !== "rule" && (
            <Button
              type="button"
              onClick={() => setOpen(Object.fromEntries(groups.map((g) => [g.id, !allOpen])))}
            >
              {allOpen ? "Close every group" : "Open every group"}
            </Button>
          )}
        </div>
      </div>
      <TableRegion label="Rule check occurrences by type">
        <Table caption={groupBy === "rule" ? "Rule check occurrences by rule" : `Rule check occurrences by ${groupBy === "kind" ? "kind of problem" : "WCAG criterion"} and rule`}>
          <TableHead>
            <tr>
              <ColumnHeader>{groupBy === "kind" ? "Kind of problem (rule)" : groupBy === "criterion" ? "WCAG criterion (rule)" : "Rule"}</ColumnHeader>
              <ColumnHeader>Page as loaded</ColumnHeader>
              <ColumnHeader>After Click-Through</ColumnHeader>
              <ColumnHeader>Total</ColumnHeader>
              <ColumnHeader className="w-[22%]">Share of rule check</ColumnHeader>
            </tr>
          </TableHead>
          <tbody>
            {groupBy === "rule"
              ? rules.map((rule) => ruleRow(rule, false))
              : groups.flatMap((group) => {
                  const loaded = sum(group.rules, "loaded");
                  const after = sum(group.rules, "click_through");
                  const expanded = Boolean(open[group.id]);
                  return [
                    <Row key={`g-${group.id}`} index={index++}>
                      <RowHeader className="py-0">
                        <Button
                          type="button"
                          variant="ghost"
                          aria-expanded={expanded}
                          onClick={() => setOpen({ ...open, [group.id]: !expanded })}
                          className="-ml-2 justify-start px-2 shadow-none"
                        >
                          <ChevronRight
                            aria-hidden
                            className={cn("h-4 w-4 transition-transform motion-reduce:transition-none", expanded && "rotate-90")}
                          />
                          {group.label}
                          <span className="sr-only">
                            , {group.rules.length} {group.rules.length === 1 ? "rule" : "rules"}
                          </span>
                        </Button>
                      </RowHeader>
                      <Cell numeric>{formatCount(loaded)}</Cell>
                      <Cell numeric>{formatCount(after)}</Cell>
                      <Cell numeric className="font-semibold">
                        {formatCount(loaded + after)}
                      </Cell>
                      <Cell>
                        <ShareBar value={total ? (loaded + after) / total : 0} />
                      </Cell>
                    </Row>,
                    ...(expanded ? group.rules.map((rule) => ruleRow(rule, true)) : []),
                  ];
                })}
          </tbody>
        </Table>
      </TableRegion>
      <p className="px-5 py-3 text-xs text-fg-subtle">
        {groupBy === "criterion"
          ? "Each occurrence counts once, under its rule's first criterion."
          : "Each occurrence counts once, so the rows add up to the total."}
      </p>
    </div>
  );
}

/**
 * The estimate: one text column on the card's left edge, in reading order:
 * the answer (or why there is none), what an estimate is, and its source.
 * Every paragraph shares one measure, so the lines start and end together.
 */
function Estimate({ data, report }: { data: CoverageFound; report: number | undefined }) {
  const est = data.estimate;
  return (
    <Card className="p-5">
      <section aria-labelledby="estimate-h" className="flex max-w-measure flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h3 id="estimate-h" className="text-base font-semibold text-fg">
            2. Estimated share of all issues
          </h3>
          <Tag tone="estimate">Estimate</Tag>
        </div>
        {est.available && est.share !== null && est.estimated_total !== null ? (
          <div className="flex flex-col gap-1">
            <p className="text-4xl font-semibold text-umich-blue">{percent(est.share)}</p>
            <p className="text-base leading-7">
              Of an estimated {formatCount(Math.round(est.estimated_total))} issues on{" "}
              {data.scans_included === 1 ? "this site" : "these sites"}, Axcess found about{" "}
              {formatCount(Math.round(est.share * est.estimated_total))}.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            <p className="text-base font-semibold text-fg">Not enough data for an estimate yet</p>
            <p className="text-base leading-7 text-fg-muted">
              It needs at least {est.min_sample} rule check (axe) occurrences.{" "}
              {data.scans_included === 1 ? "This report has" : "These reports have"} {formatCount(est.axe_sample)}.{" "}
              {report ? "Choose all completed reports, or run more scans." : "Run more scans to reach it."}
            </p>
          </div>
        )}
        <div className="flex flex-col gap-2 border-l-4 border-sev-major py-1 pl-4 text-base leading-7 text-fg">
          <p>
            <strong>An estimate, not a result.</strong> A scan counts only what Axcess finds. Missed issues are
            estimated from how often the rule check (axe) catches each kind in Deque&apos;s audit study.
          </p>
          <p>It doesn&apos;t show a site meets WCAG. Deque makes axe and studied its own clients&apos; sites. 4.1.1 Parsing is left out.</p>
        </div>
        <p className="text-sm text-fg-muted">
          Source:{" "}
          <ExternalTextLink standalone href={est.source_url}>
            {est.source_title}
          </ExternalTextLink>
        </p>
      </section>
    </Card>
  );
}

function ManualReview({ data }: { data: CoverageFound }) {
  const mr = data.manual_review;
  return (
    <Card>
      <section aria-labelledby="manual-h">
        <div className="flex flex-col gap-2 p-5 pb-3">
          <div className="flex flex-wrap items-center gap-3">
            <h3 id="manual-h" className="text-base font-semibold text-fg">
              3. Criteria that failed a manual review
            </h3>
            <Tag tone="criterion">By criterion</Tag>
          </div>
          {mr.failed === 0 ? (
            <>
              <p className="font-semibold text-fg">No criteria marked as failed yet</p>
              <p className="text-sm text-fg-muted">Appears once a manual review on a report marks a criterion as failed.</p>
            </>
          ) : (
            <>
              <p className="max-w-measure text-base">
                In {mr.scans.length} manual {mr.scans.length === 1 ? "review" : "reviews"}, people marked {mr.failed}{" "}
                WCAG criteria as failed. Axcess had found at least one occurrence for {mr.found} of them (
                {percent(mr.share)}) in the same report.
              </p>
              <p className="max-w-measure text-sm text-fg-muted">
                Counts criteria, not occurrences. One occurrence doesn&apos;t mean Axcess found every problem for that
                criterion.
              </p>
            </>
          )}
        </div>
        {mr.failed > 0 && (
          <TableRegion label="Failed criteria by report">
            <Table caption="Failed criteria by report">
              <TableHead>
                <tr>
                  <ColumnHeader>Report</ColumnHeader>
                  <ColumnHeader>Criteria failed</ColumnHeader>
                  <ColumnHeader>Axcess found an occurrence</ColumnHeader>
                  <ColumnHeader>Share</ColumnHeader>
                </tr>
              </TableHead>
              <tbody>
                {mr.scans.map((scan, index) => (
                  <Row key={scan.scan_id} index={index}>
                    <RowHeader className="font-medium">
                      <Link to={`/scans/${scan.scan_id}/issues`} className="text-umich-blue underline underline-offset-2">
                        Report #{scan.scan_id}, {scan.seed_url}
                      </Link>
                    </RowHeader>
                    <Cell numeric>{scan.failed}</Cell>
                    <Cell numeric>{scan.found}</Cell>
                    <Cell numeric>{percent(scan.failed ? scan.found / scan.failed : 0)}</Cell>
                  </Row>
                ))}
              </tbody>
            </Table>
          </TableRegion>
        )}
      </section>
    </Card>
  );
}
