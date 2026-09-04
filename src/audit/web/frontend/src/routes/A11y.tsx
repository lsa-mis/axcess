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
  StatCard,
} from "../components/ui";
import type {
  A11ySCGroup,
  AxeImpact,
  FindingStatus,
  Severity,
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
 * Per-scan WCAG DOM-engine view, segregated by success criterion.
 *
 * This is the second product surface — distinct from the original
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

  const { data: scan, error: scanError } = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
  });
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
        title="WCAG DOM-engine findings"
        subtitle={scan.seed_url}
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
              Image-of-text findings
              <ChevronRight className="h-4 w-4" aria-hidden />
            </LinkButton>
          </>
        }
      />

      <ScopeBanner />

      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7">
        <StatCard
          label="Axe pages"
          value={coverage.axe_pages_scanned}
          hint={`of ${coverage.pages_total}`}
        />
        <StatCard
          label="Alfa pages"
          value={coverage.alfa_pages_scanned}
          hint={`of ${coverage.pages_total}`}
        />
        <StatCard label="Axe violations" value={coverage.axe_violations_total} />
        <StatCard label="Alfa failed" value={coverage.alfa_failed_total} />
        <StatCard label="Alfa review leads" value={coverage.alfa_cant_tell_total} />
        <StatCard label="Level A" value={rollup.by_level.A} tone="critical" />
        <StatCard label="Level AA" value={rollup.by_level.AA} tone="major" />
        <StatCard label="Level AAA" value={rollup.by_level.AAA} tone="minor" />
        <StatCard
          label="Best-practice"
          value={rollup.by_level.best_practice}
          tone="info"
        />
      </div>

      {noDomPagesScanned ? (
        <EmptyState
          title="No pages were evaluated by a DOM engine"
          message="Start a new scan and select axe-core, Siteimprove Alfa, or both. Axe requires Axcess browser rendering; Alfa can also run when static-only crawl mode is selected."
          action={
            <LinkButton to="/scans/new" variant="primary">
              New scan
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
          title="No retained WCAG DOM-engine findings"
          message="The selected engine(s) returned no failed or expert-review outcomes. Manual review is still required before making a conformance claim."
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
      aria-label="What this view shows"
    >
      <div className="flex items-start gap-3">
        <Info
          className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue"
          aria-hidden
        />
        <p className="text-sm text-fg">
          <strong>What this view shows.</strong> Each finding retains its source:
          <strong> axe-core</strong> or <strong> Siteimprove Alfa</strong>. Axe
          evaluates deterministic browser rules. Alfa evaluates independent
          <strong> ACT (Accessibility Conformance Testing) rules</strong> on its
          own local browser capture. Each standardized ACT rule checks one
          specific condition and can return pass, fail, or <code>cantTell</code>.
          A failed rule is evidence about that condition—not proof that the whole
          page or site fails WCAG. A <code>cantTell</code> result needs an expert
          decision.
        </p>
      </div>
    </Card>
  );
}

function RollupView({ scanId, groups }: { scanId: number; groups: A11ySCGroup[] }) {
  return (
    <div className="space-y-3">
      <h2 className="text-base font-semibold uppercase tracking-wide text-fg-subtle">
        Failures by WCAG success criterion
      </h2>
      {groups.map((g) => (
        <SCGroupCard key={g.wcag_sc ?? "best-practice"} scanId={scanId} group={g} />
      ))}
    </div>
  );
}

function SCGroupCard({ scanId, group }: { scanId: number; group: A11ySCGroup }) {
  const linkParams = new URLSearchParams();
  // For best-practice (wcag_sc=null), pass an empty string — the server
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
              SC {group.wcag_sc}
            </Link>
          ) : (
            <span>Best-practice (no SC)</span>
          )}
          {group.wcag_level && (
            <span className="ml-2 text-sm font-normal text-fg-muted">
              · Level {group.wcag_level}
            </span>
          )}
        </h3>
        <span className="text-sm text-fg-muted">
          <strong className="text-fg">{group.violation_count}</strong>{" "}
          violation{group.violation_count !== 1 ? "s" : ""} on{" "}
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
                {r.pipeline === "alfa" ? "Siteimprove Alfa" : r.pipeline === "axe" ? "axe-core" : r.pipeline}
              </span>
              {r.impact && <ImpactChip value={r.impact} />}
              <span className="text-xs text-fg-muted">
                {r.violation_count} ×, on {r.page_count} page
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
                {r.pipeline === "alfa" ? "Alfa rule docs" : "rule docs"}{" "}
                <ExternalLink className="h-3 w-3" aria-hidden />
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
  return (
    <>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">
          SC {wcagSc}
          {group && (
            <span className="ml-2 text-sm font-normal text-fg-muted">
              · {group.violation_count} violation
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
          ← Back to all SCs
        </Link>
      </div>

      {/* Status filter — auto-applies on change, URL-persistent. The
          option labels carry the count so the triager can see at a
          glance how many findings sit in each bucket before clicking. */}
      <Card className="mb-3 p-3">
        <label className="flex flex-col text-xs font-semibold uppercase tracking-wide text-fg-subtle">
          Status filter
          <select
            value={status}
            onChange={(e) =>
              onStatusFilterChange(e.target.value as FindingStatus | "")
            }
            className="mt-1 min-h-target rounded-xs border border-border bg-surface px-2 py-2 text-base font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
          >
            <option value="">all statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")} ({statusCounts[s] ?? 0})
              </option>
            ))}
          </select>
        </label>
      </Card>

      {loading ? (
        <div className="text-fg-muted">Loading…</div>
      ) : drill.length === 0 ? (
        <Card className="p-4 text-sm text-fg-muted">
          No drill-down rows
          {status && (
            <>
              {" "}
              matching status <strong>{status}</strong>.{" "}
              <button
                type="button"
                onClick={() => onStatusFilterChange("")}
                className="text-umich-blue underline underline-offset-2"
              >
                Show all statuses
              </button>
            </>
          )}
          {!status && <> for this SC.</>}
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <caption className="sr-only">
              DOM-engine findings for SC {wcagSc}, sorted by impact
            </caption>
            <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-semibold">
                  Rule
                </th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">
                  Source
                </th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">
                  Impact
                </th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">
                  Page
                </th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">
                  Target selector
                </th>
                <th scope="col" className="px-3 py-2 text-left font-semibold">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {drill.map((f) => (
                <tr key={f.id} className="align-top">
                  <td className="px-3 py-2">
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
                  </td>
                  <td className="px-3 py-2 text-xs text-fg-muted">
                    {f.pipeline === "alfa" ? "Siteimprove Alfa" : f.pipeline === "axe" ? "axe-core" : f.pipeline}
                    {f.pipeline === "alfa" && f.engine_outcome === "cant_tell" && (
                      <span className="mt-1 block">Needs expert review</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {f.impact ? <ImpactChip value={f.impact} /> : (
                      <span className="text-fg-subtle">—</span>
                    )}
                  </td>
                  <td className="max-w-xs px-3 py-2">
                    <PageLink
                      pageId={f.page_id}
                      scanId={scanId}
                      pageUrl={f.page_url}
                      pageTitle={f.page_title}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <code className="block break-all font-mono text-2xs text-fg">
                      {(f.target_display || f.target_selector).length > 90
                        ? `${(f.target_display || f.target_selector).slice(0, 90)}…`
                        : (f.target_display || f.target_selector)}
                    </code>
                    {f.html_snippet && (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-2xs text-fg-subtle">
                          show HTML
                        </summary>
                        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all rounded-xs bg-surface-muted p-2 text-2xs">
                          {f.html_snippet}
                        </pre>
                      </details>
                    )}
                    <AlfaEvidenceNote evidence={f} />
                    <Link className="report-link inline-flex min-h-target items-center text-xs" to={`/scans/${scanId}/pages/${f.page_id}#finding-${f.id}`}>Open stored finding evidence</Link>
                    {f.failure_summary && (
                      <div className="mt-1 text-2xs text-fg-muted">
                        {f.failure_summary}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <StatusCell
                      scanId={scanId}
                      findingId={f.id}
                      current={f.status}
                    />
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

/**
 * Per-row status select with optimistic-ish save.
 *
 * Each row owns its own mutation so a save on row 3 doesn't grey out
 * row 4's controls. On success we invalidate both the drill-down query
 * (the row now shows its new status) and the rollup (the status-filter
 * counts in the header need to refresh).
 *
 * Auto-submits on change — no Save button, no extra keystrokes. The
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
      <label className="sr-only" htmlFor={`status-${findingId}`}>
        Triage status for finding {findingId}
      </label>
      <select
        id={`status-${findingId}`}
        value={current}
        onChange={(e) => {
          const next = e.target.value as FindingStatus;
          const rationale = requestStatusRationale(next, `finding #${findingId}`);
          if (rationale === null) {
            e.currentTarget.value = current;
            return;
          }
          mutation.mutate({ next, rationale });
        }}
        disabled={mutation.isPending}
        className="min-h-target rounded-xs border border-border bg-surface px-2 py-1 text-sm text-fg focus:border-umich-blue focus:outline-none disabled:opacity-60"
      >
        {STATUS_OPTIONS.map((s) => (
          <option key={s} value={s}>
            {s.replace(/_/g, " ")}
          </option>
        ))}
      </select>
      {mutation.isError ? (
        <span className="text-2xs text-sev-critical" role="alert">
          Save failed
        </span>
      ) : mutation.isSuccess ? (
        <span className="text-2xs text-fg-subtle" role="status">
          Saved
        </span>
      ) : null}
    </div>
  );
}

/**
 * Pill rendering an axe impact value. We map axe's four-level scale to
 * the existing severity tokens so this view inherits the color system
 * the rest of the SPA uses — no new colors to audit. critical → critical,
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
      className={`inline-flex items-center gap-1 rounded-xs px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide text-white bg-sev-${tone}-bg`}
    >
      {value === "critical" && (
        <AlertTriangle className="h-3 w-3" aria-hidden />
      )}
      {value}
    </span>
  );
}
