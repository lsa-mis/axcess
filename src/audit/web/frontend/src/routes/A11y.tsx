import AlfaEvidenceNote from "../components/AlfaEvidenceNote";
import { Link, useParams, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronRight, ExternalLink, Info } from "lucide-react";
import { api } from "../api/client";
import {
  Card,
  EmptyState,
  LinkButton,
  PageHeader,
  PageLink,
  pageEvidencePath,
  Select,
  StatCard,
} from "../components/ui";
import { withoutUserinfo } from "../components/ReportCrumb";
import type {
  A11ySCGroup,
  AxeImpact,
  FindingStatus,
  Severity,
} from "../api/types";
import { TablePagination, usePagedRows } from "../components/TablePagination";
import {
  Cell,
  ColumnHeader,
  Row,
  Table,
  TableBar,
  TableEmpty,
  TableHead,
  TableRegion,
  TableStatus,
} from "../components/table/Table";
import { ActiveFilters, FilterMenu, activeFilterItems, type FilterGroup } from "../components/table/FilterMenu";
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
 * Per-scan WCAG DOM-engine view, segregated by success criterion.
 *
 * This is the second product surface, distinct from the original
 * `Findings` route which only covers WCAG 1.4.5 (Images of Text).
 * Different lifecycle (DOM-time, not image-time), different audience
 * (a developer fixing CSS / templates), different dedupe key
 * (page+rule+target, not content_hash).
 *
 * Two modes, controlled by the `wcag_sc` URL param:
 *   • Roll-up: counts by SC, level, and impact, with per-rule nesting.
 *   • Drill-down: a list of every individual DOM-engine finding for one SC,
 *     each row carrying the page URL and the failing element's
 *     selector and HTML snippet.
 *
 * Evidence stays attributable to the engine that produced it. Neither an
 * automated pass nor an Alfa `cantTell` outcome is a conformance verdict.
 */
export default function A11yRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const wcagSc = params.get("wcag_sc"); // null = roll-up, string = drill-down
  // Empty string = "all statuses", same convention the backend uses.
  // Cast through unknown because the param is free-form until validated.
  const rawStatus = params.get("status") ?? "";
  const status = (
    STATUS_OPTIONS.includes(rawStatus as FindingStatus) ? rawStatus : ""
  ) as FindingStatus | "";

  const { data: scan, error: scanError } = useScanQuery(id);
  const { data: rollup, isLoading: rollupLoading } = useQuery({
    queryKey: ["a11y-rollup", id],
    queryFn: () => api.getA11yRollup(id),
    enabled: Number.isFinite(id),
  });
  const { data: drill, isLoading: drillLoading } = useQuery({
    queryKey: ["a11y-drill", id, wcagSc, status],
    queryFn: () => api.getA11yFindings(id, wcagSc, status || undefined),
    enabled: Number.isFinite(id) && wcagSc !== null,
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
  if (!scan || !rollup || rollupLoading) {
    return <div className="text-fg-muted">Loading…</div>;
  }

  const coverage = rollup.coverage;
  const noDomPagesScanned =
    coverage.axe_pages_scanned === 0 && coverage.alfa_pages_scanned === 0;

  return (
    <>
      <PageHeader
        title="Rule check issues by WCAG criterion"
        subtitle={withoutUserinfo(scan.seed_url)}
        actions={
          <>
            {/* Group-by-rule is the actionable cut (one rule, one fix
                applied N places). Promote it as the primary action;
                this by-SC view stays useful as the reporting axis. */}
            <LinkButton
              to={`/scans/${scan.id}/a11y/by-rule`}
              variant="primary"
            >
              Group by rule
              <ChevronRight className="h-4 w-4" aria-hidden />
            </LinkButton>
            <LinkButton to={`/scans/${scan.id}/findings`} variant="secondary">
              Images (image text check)
              <ChevronRight className="h-4 w-4" aria-hidden />
            </LinkButton>
          </>
        }
      />

      <ScopeBanner />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
        <StatCard
          label="Pages checked (axe)"
          value={coverage.axe_pages_scanned}
          hint={`of ${coverage.pages_total}`}
        />
        <StatCard
          label="Pages checked (Alfa)"
          value={coverage.alfa_pages_scanned}
          hint={`of ${coverage.pages_total}`}
        />
        <StatCard label="Occurrences (axe)" value={coverage.axe_violations_total} />
        <StatCard label="Failed (Alfa)" value={coverage.alfa_failed_total} />
        <StatCard label="Needs review (Alfa)" value={coverage.alfa_cant_tell_total} />
        <StatCard label="Level A" value={rollup.by_level.A} tone="critical" />
        <StatCard label="Level AA" value={rollup.by_level.AA} tone="major" />
        <StatCard label="Level AAA" value={rollup.by_level.AAA} tone="minor" />
        <StatCard
          label="Best practice"
          value={rollup.by_level.best_practice}
          tone="info"
        />
      </div>

      {noDomPagesScanned ? (
        <EmptyState
          title="No rule check ran in this scan"
          message="Start a new scan and choose Rule check (axe), Rule check (Alfa), or both. The axe check needs Axcess to open pages in a browser. The Alfa check also works in static-only mode, where the scan reads page code without a browser."
          action={
            <LinkButton to="/scans/new" variant="primary">
              Start a new scan
            </LinkButton>
          }
        />
      ) : wcagSc ? (
        <DrillDownView
          scanId={id}
          wcagSc={wcagSc}
          drill={drill?.findings ?? []}
          loading={drillLoading}
          group={rollup.groups.find((g) => g.wcag_sc === wcagSc) ?? null}
          status={status}
          onStatusFilterChange={setStatusParam}
          statusCounts={rollup.by_status}
        />
      ) : rollup.groups.length === 0 ? (
        <EmptyState
          title="The rule checks found no issues"
          message="The rule checks you chose found nothing that failed or needs review. A person still needs to test the site by hand. Automated checks alone cannot show that a site meets WCAG."
        />
      ) : (
        <RollupView scanId={id} groups={rollup.groups} />
      )}
    </>
  );
}

function ScopeBanner() {
  return (
    <Card
      className="mb-4 border-umich-blue/30 bg-umich-blue/5 p-4"
      role="note"
      aria-label="What this page shows"
    >
      <div className="flex items-start gap-3">
        <Info
          className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue"
          aria-hidden
        />
        <p className="text-sm text-fg">
          <strong>What this page shows.</strong> Each occurrence names the check
          that found it: <strong>Rule check (axe)</strong> or{" "}
          <strong>Rule check (Alfa)</strong>. Both test pages against fixed
          rules. Alfa is a separate tool. It opens its own copy of each page in a
          browser on this computer and uses standard test rules
          (<strong>ACT, Accessibility Conformance Testing</strong>). Each rule
          tests one thing, for example that an image has alt text. A rule can
          pass, fail, or say it cannot tell (<code>cantTell</code>). A failed rule
          shows a problem with that one thing. It does not prove that the whole
          page or site fails the Web Content Accessibility Guidelines (WCAG).
          When a rule cannot tell, a person needs to review it.
        </p>
      </div>
    </Card>
  );
}

function RollupView({ scanId, groups }: { scanId: number; groups: A11ySCGroup[] }) {
  return (
    <div className="space-y-3">
      <h2 className="text-base font-semibold text-fg-subtle">
        Issues by WCAG criterion
      </h2>
      {groups.map((g) => (
        <SCGroupCard key={g.wcag_sc ?? "best-practice"} scanId={scanId} group={g} />
      ))}
    </div>
  );
}

function SCGroupCard({ scanId, group }: { scanId: number; group: A11ySCGroup }) {
  const linkParams = new URLSearchParams();
  // For best-practice (wcag_sc=null), pass an empty string, the server
  // treats "" as "no SC mapping" and `undefined` as "no filter."
  linkParams.set("wcag_sc", group.wcag_sc ?? "");
  return (
    <Card className="p-4">
      <header className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-lg font-semibold">
          {group.wcag_sc ? (
            <Link
              to={`/scans/${scanId}/a11y?${linkParams}`}
              className="text-umich-blue underline underline-offset-2"
            >
              WCAG {group.wcag_sc}
            </Link>
          ) : (
            <span>Best practice (no WCAG criterion)</span>
          )}
          {group.wcag_level && (
            <span className="ml-2 text-sm font-normal text-fg-muted">
              · Level {group.wcag_level}
            </span>
          )}
        </h3>
        <span className="text-sm text-fg-muted">
          <strong className="text-fg">{group.violation_count}</strong>{" "}
          occurrence{group.violation_count !== 1 ? "s" : ""} on{" "}
          <strong className="text-fg">{group.page_count}</strong> page
          {group.page_count !== 1 ? "s" : ""}
        </span>
      </header>
      <ul className="grid gap-2">
        {group.rules.map((r) => (
          <li
            key={`${r.pipeline}:${r.rule_id}`}
            className="rounded-xs border border-border bg-surface-muted/40 p-3"
          >
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <code className="font-mono text-sm text-fg">{r.rule_id}</code>
              <span className="rounded-full bg-surface px-2 py-0.5 text-2xs font-semibold text-fg-muted">
                {CHECK_LABEL[r.pipeline] ?? r.pipeline}
              </span>
              {r.impact && <ImpactChip value={r.impact} />}
              <span className="text-xs text-fg-muted">
                {r.violation_count} occurrence{r.violation_count !== 1 ? "s" : ""} on{" "}
                {r.page_count} page
                {r.page_count !== 1 ? "s" : ""}
              </span>
            </div>
            {r.help && <div className="text-sm text-fg">{r.help}</div>}
            {r.help_url && (
              <a
                href={r.help_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-xs text-umich-blue underline underline-offset-2"
              >
                {r.pipeline === "alfa" ? "About this rule (Alfa)" : "About this rule"}{" "}
                <ExternalLink className="h-3 w-3" aria-hidden />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function DrillDownView({
  scanId,
  wcagSc,
  drill,
  loading,
  group,
  status,
  onStatusFilterChange,
  statusCounts,
}: {
  scanId: number;
  wcagSc: string;
  drill: import("../api/types").A11yDrillFinding[];
  loading: boolean;
  group: A11ySCGroup | null;
  status: FindingStatus | "";
  onStatusFilterChange: (value: FindingStatus | "") => void;
  statusCounts: Record<FindingStatus, number>;
}) {
  // A new SC or status filter starts the table over at page 1.
  const paged = usePagedRows(drill, { resetKey: `${wcagSc}|${status}` });
  // The option labels carry the count so the triager can see at a glance
  // how many occurrences sit in each status before choosing.
  const filters: FilterGroup[] = [
    {
      key: "status",
      label: "Status",
      value: status,
      options: [
        { value: "", label: "All" },
        ...STATUS_OPTIONS.map((s) => ({
          value: s,
          label: STATUS_OPTION_LABEL[s],
          count: statusCounts[s] ?? 0,
        })),
      ],
    },
  ];
  return (
    <>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">
          {wcagSc ? `WCAG ${wcagSc}` : "Best practice (no WCAG criterion)"}
          {group && (
            <span className="ml-2 text-sm font-normal text-fg-muted">
              · {group.violation_count} occurrence
              {group.violation_count !== 1 ? "s" : ""} on {group.page_count}{" "}
              page{group.page_count !== 1 ? "s" : ""}
              {group.wcag_level && ` · Level ${group.wcag_level}`}
            </span>
          )}
        </h2>
        <Link
          to={`/scans/${scanId}/a11y`}
          className="text-sm text-umich-blue underline underline-offset-2"
        >
          ← Back to all WCAG criteria
        </Link>
      </div>

      {/* Status filter, auto-applies on change, URL-persistent. The card
          and its bar stay up when nothing matches, so the filter that
          emptied the table is still there to undo. */}
      <Card>
        <TableBar
          pager={<TablePagination label="Occurrences" noun="occurrences" {...paged} />}
          footer={<ActiveFilters items={activeFilterItems(filters)} onClear={() => onStatusFilterChange("")} />}
        >
          <FilterMenu
            groups={filters}
            onChange={(_key, value) => onStatusFilterChange(value as FindingStatus | "")}
            onReset={() => onStatusFilterChange("")}
          />
        </TableBar>
        <TableStatus>
          {loading
            ? "Loading…"
            : `${drill.length.toLocaleString()} ${drill.length === 1 ? "occurrence" : "occurrences"}, most serious impact first.`}
        </TableStatus>
        {loading ? null : drill.length === 0 ? (
          <TableEmpty>
            No occurrences
            {status && (
              <>
                {" "}
                have the status <strong>{STATUS_LABEL[status]}</strong>.{" "}
                <button
                  type="button"
                  onClick={() => onStatusFilterChange("")}
                  className="text-umich-blue underline underline-offset-2"
                >
                  Show all statuses
                </button>
              </>
            )}
            {!status && <> for this WCAG criterion.</>}
          </TableEmpty>
        ) : (
          <TableRegion label="Rule check occurrences table" paged={paged}>
            <Table
              caption={`Rule check occurrences for ${wcagSc ? `WCAG ${wcagSc}` : "best practice"}, most serious impact first`}
            >
              <TableHead>
                <tr>
                  <ColumnHeader>Rule</ColumnHeader>
                  <ColumnHeader>Check</ColumnHeader>
                  <ColumnHeader>Impact</ColumnHeader>
                  <ColumnHeader>Page</ColumnHeader>
                  <ColumnHeader>Element locator (CSS selector)</ColumnHeader>
                  <ColumnHeader>Status</ColumnHeader>
                </tr>
              </TableHead>
              <tbody>
                {paged.pageRows.map((f, index) => (
                  <Row key={f.id} index={(paged.page - 1) * paged.pageSize + index}>
                    <Cell>
                      <code className="font-mono text-xs text-fg">
                        {f.rule_id}
                      </code>
                      {f.help && (
                        <div className="mt-1 text-xs text-fg-muted">
                          {f.help.length > 140
                            ? `${f.help.slice(0, 140)}…`
                            : f.help}
                        </div>
                      )}
                    </Cell>
                    <Cell className="text-xs text-fg-muted">
                      {CHECK_LABEL[f.pipeline] ?? f.pipeline}
                      {f.pipeline === "alfa" && f.engine_outcome === "cant_tell" && (
                        <span className="mt-1 block">Needs review</span>
                      )}
                    </Cell>
                    <Cell>
                      {f.impact ? <ImpactChip value={f.impact} /> : (
                        <span className="text-fg-muted">Does not apply</span>
                      )}
                    </Cell>
                    <Cell className="max-w-xs">
                      <PageLink
                        pageId={f.page_id}
                        scanId={scanId}
                        pageUrl={f.page_url}
                        pageTitle={f.page_title}
                        selector={f.target_selector}
                        snippet={f.html_snippet}
                        origin="Rule check issues by WCAG criterion"
                        context={f.rule_id}
                        backTo={`/scans/${scanId}/a11y?wcag_sc=${wcagSc}`}
                      />
                    </Cell>
                    <Cell>
                      <code className="block break-all font-mono text-2xs text-fg">
                        {(f.target_display || f.target_selector).length > 90
                          ? `${(f.target_display || f.target_selector).slice(0, 90)}…`
                          : (f.target_display || f.target_selector)}
                      </code>
                      {f.html_snippet && (
                        <details className="mt-1">
                          <summary className="cursor-pointer text-2xs text-fg-muted">
                            Show element code (HTML)
                          </summary>
                          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-xs bg-surface-muted p-2 text-2xs">
                            {f.html_snippet}
                          </pre>
                        </details>
                      )}
                      <AlfaEvidenceNote evidence={f} />
                      <Link className="report-link inline-flex min-h-target items-center text-xs" to={pageEvidencePath({ scanId, pageId: f.page_id, origin: "Rule check issues by WCAG criterion", backTo: `/scans/${scanId}/a11y?wcag_sc=${wcagSc}`, hash: `#finding-${f.id}` })}>Open the evidence for this occurrence</Link>
                      {f.failure_summary && (
                        <div className="mt-1 text-2xs text-fg-muted">
                          {f.failure_summary}
                        </div>
                      )}
                    </Cell>
                    <Cell>
                      <StatusCell
                        scanId={scanId}
                        findingId={f.id}
                        current={f.status}
                      />
                    </Cell>
                  </Row>
                ))}
              </tbody>
            </Table>
          </TableRegion>
        )}
      </Card>
    </>
  );
}

/**
 * Per-row status select with optimistic-ish save.
 *
 * Each row owns its own mutation so a save on row 3 doesn't grey out
 * row 4's controls. On success we invalidate both the drill-down query
 * (the row now shows its new status) and the rollup (the status-filter
 * counts in the header need to refresh).
 *
 * Auto-submits on change, no Save button, no extra keystrokes. The
 * triager can fly through dozens of findings with Tab + arrow keys.
 */
function StatusCell({
  scanId,
  findingId,
  current,
}: {
  scanId: number;
  findingId: number;
  current: FindingStatus;
}) {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ next, rationale }: { next: FindingStatus; rationale: string }) =>
      api.setA11yStatus(findingId, next, rationale || undefined),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["a11y-rollup", scanId] });
      void qc.invalidateQueries({ queryKey: ["a11y-drill", scanId] });
    },
  });
  return (
    <div className="flex flex-col gap-1">
      <Select
        hideLabel
        id={`status-${findingId}`}
        label={`Status for occurrence ${findingId}`}
        value={current}
        onChange={(next) => {
          const rationale = requestStatusRationale(
            next as FindingStatus,
            `occurrence #${findingId}`,
          );
          // Declining the rationale leaves the value where it was. The select
          // is controlled, so React restores it on the next render without the
          // manual reset the uncontrolled version needed.
          if (rationale === null) return;
          mutation.mutate({ next: next as FindingStatus, rationale });
        }}
        disabled={mutation.isPending}
        options={STATUS_OPTIONS.map((s) => ({ value: s, label: STATUS_OPTION_LABEL[s] }))}
      />
      {mutation.isError ? (
        <span className="text-2xs text-sev-critical" role="alert">
          Status not saved. Try again.
        </span>
      ) : mutation.isSuccess ? (
        <span className="text-2xs text-fg-muted" role="status">
          Status saved
        </span>
      ) : null}
    </div>
  );
}

/**
 * Pill rendering an axe impact value. We map axe's four-level scale to
 * the existing severity tokens so this view inherits the color system
 * the rest of the SPA uses, no new colors to audit. critical → critical,
 * serious → major, moderate → minor, minor → info.
 */
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
      className={`inline-flex items-center gap-1 rounded-xs px-1.5 py-0.5 text-2xs font-semibold text-white bg-sev-${tone}-bg`}
    >
      {value === "critical" && (
        <AlertTriangle className="h-3 w-3" aria-hidden />
      )}
      {value}
    </span>
  );
}
