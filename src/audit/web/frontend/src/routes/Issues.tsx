import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ChevronDown, Download, ExternalLink, X } from "lucide-react";
import { api } from "../api/client";
import {
  Card,
  DownloadLink,
  EmptyState,
  PageHeader,
} from "../components/ui";
import type {
  AbilityLabel,
  ConformanceLabel,
  FindingStatus,
  IssueRow,
} from "../api/types";

/**
 * Unified Issues view — card list, both pipelines.
 *
 * Earlier iterations rendered a Siteimprove-style dense table; the
 * tradeoff was that "why does this matter / how do I fix it" was
 * always one click away (the detail page). The card layout surfaces
 * what/why/how *inline* via a per-card disclosure, so an operator
 * triaging 13 issues doesn't make 13 round-trips through the detail
 * page.
 *
 * Filter + sort still work the same; the cards just replace the
 * tabular row. Per-card state lives in the URL as `?expand=key1,key2`
 * so an expanded view is bookmarkable + sharable.
 */
export default function IssuesRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();

  const conformance =
    (params.get("conformance") as ConformanceLabel | null) ?? "";
  const responsibility = params.get("responsibility") ?? "";
  const abilities = (params.get("abilities") as AbilityLabel | null) ?? "";
  const status = (params.get("status") as FindingStatus | null) ?? "";
  const q = params.get("q") ?? "";
  const sort = params.get("sort") ?? "priority_desc";

  // Comma-separated set of expanded issue keys. URL-backed so a
  // bookmark preserves the operator's reading position.
  const expandedFromUrl = new Set(
    (params.get("expand") ?? "").split(",").filter(Boolean),
  );
  const [expanded, setExpanded] = useState<Set<string>>(expandedFromUrl);

  const { data: scan, error: scanError } = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
  });
  const { data, isLoading } = useQuery({
    queryKey: ["issues", id, conformance, responsibility, abilities, status, q, sort],
    queryFn: () =>
      api.listIssues(id, {
        conformance,
        responsibility,
        abilities,
        status,
        q,
        sort,
      }),
    enabled: Number.isFinite(id),
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };

  const toggleCard = (key: string) => {
    const next = new Set(expanded);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setExpanded(next);
    // Mirror to URL so a refresh preserves the expanded set.
    const nextParams = new URLSearchParams(params);
    if (next.size > 0) nextParams.set("expand", [...next].join(","));
    else nextParams.delete("expand");
    setParams(nextParams, { replace: true });
  };

  const expandAll = (rows: IssueRow[]) => {
    const next = new Set(rows.map((r) => r.issue_key));
    setExpanded(next);
    const nextParams = new URLSearchParams(params);
    nextParams.set("expand", [...next].join(","));
    setParams(nextParams, { replace: true });
  };

  const collapseAll = () => {
    setExpanded(new Set());
    const nextParams = new URLSearchParams(params);
    nextParams.delete("expand");
    setParams(nextParams, { replace: true });
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

  const { rows, conformance_counts, responsibility_counts, abilities_counts } =
    data;

  const hasFilter = !!(
    conformance ||
    responsibility ||
    abilities ||
    status ||
    q
  );

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Scans", to: "/scans" },
          { label: `Scan #${scan.id}`, to: `/scans/${scan.id}` },
          { label: "Issues" },
        ]}
        title="Issues"
        subtitle={`${scan.seed_url} · ${rows.length} of ${data.total_unfiltered} issues`}
        actions={
          <>
            {/* Plain <a> via DownloadLink — `LinkButton` here would
                run the URL through React Router's basename ("/app")
                and the user would see a 404 SPA page instead of the
                file download. */}
            <DownloadLink
              href={`/api/scans/${scan.id}/export/audit`}
              variant="primary"
            >
              <Download className="h-4 w-4" aria-hidden />
              Audit report
            </DownloadLink>
            <DownloadLink
              href={`/api/scans/${scan.id}/export/csv`}
              variant="secondary"
            >
              <Download className="h-4 w-4" aria-hidden />
              CSV
            </DownloadLink>
          </>
        }
      />

      {hasFilter && (
        <div
          className="mb-3 flex flex-wrap items-center gap-2"
          aria-label="Active filters"
        >
          {conformance && (
            <FilterChip
              label={`Conformance: ${conformance}`}
              onRemove={() => setParam("conformance", "")}
            />
          )}
          {responsibility && (
            <FilterChip
              label={`Responsibility: ${responsibility}`}
              onRemove={() => setParam("responsibility", "")}
            />
          )}
          {abilities && (
            <FilterChip
              label={`Abilities: ${abilities}`}
              onRemove={() => setParam("abilities", "")}
            />
          )}
          {status && (
            <FilterChip
              label={`Status: ${status}`}
              onRemove={() => setParam("status", "")}
            />
          )}
          {q && (
            <FilterChip
              label={`Search: "${q}"`}
              onRemove={() => setParam("q", "")}
            />
          )}
          <button
            type="button"
            onClick={() => setParams(new URLSearchParams())}
            className="rounded-full border border-border bg-surface px-3 py-1 text-sm text-sev-critical hover:bg-sev-critical-bg"
          >
            Clear all
          </button>
        </div>
      )}

      <Card className="mb-4 p-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <FilterSelect
            label="Conformance"
            value={conformance}
            options={[
              { value: "", label: `all (${data.total_unfiltered})` },
              { value: "A", label: `Level A (${conformance_counts.A ?? 0})` },
              { value: "AA", label: `Level AA (${conformance_counts.AA ?? 0})` },
              { value: "AAA", label: `Level AAA (${conformance_counts.AAA ?? 0})` },
              { value: "BP", label: `Best-practice (${conformance_counts.BP ?? 0})` },
            ]}
            onChange={(v) => setParam("conformance", v)}
          />
          <FilterSelect
            label="Responsibility"
            value={responsibility}
            options={[
              { value: "", label: "all responsibilities" },
              ...Object.entries(responsibility_counts)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([k, n]) => ({
                  value: k,
                  label: `${k.charAt(0).toUpperCase()}${k.slice(1)} (${n})`,
                })),
            ]}
            onChange={(v) => setParam("responsibility", v)}
          />
          <FilterSelect
            label="Abilities affected"
            value={abilities}
            options={[
              { value: "", label: "all abilities" },
              ...Object.entries(abilities_counts)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([k, n]) => ({
                  value: k,
                  label: `${k.charAt(0).toUpperCase()}${k.slice(1)} (${n})`,
                })),
            ]}
            onChange={(v) => setParam("abilities", v)}
          />
          <FilterSelect
            label="Status (any finding)"
            value={status}
            options={[
              { value: "", label: "all statuses" },
              ...(
                [
                  "new",
                  "reviewing",
                  "in_progress",
                  "remediated",
                  "accepted_risk",
                  "false_positive",
                ] as const
              ).map((s) => ({ value: s, label: s.replace(/_/g, " ") })),
            ]}
            onChange={(v) => setParam("status", v)}
          />
          <label className="flex flex-col text-xs font-semibold uppercase tracking-wide text-fg-subtle">
            Search
            <input
              type="search"
              value={q}
              placeholder="title or SC…"
              onChange={(e) => setParam("q", e.target.value)}
              className="mt-1 min-h-target rounded-xs border border-border bg-surface px-2 py-2 text-base font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
            />
          </label>
        </div>
      </Card>

      {rows.length === 0 ? (
        <EmptyState
          title={hasFilter ? "No issues match these filters" : "No issues found"}
          message={
            hasFilter
              ? "Try clearing a filter to broaden the view."
              : "The scan didn't surface any issues. Either the site is clean, or no analyses have run yet."
          }
        />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-fg-muted">
              Each card answers <strong className="text-fg">what</strong>{" "}
              the issue is, <strong className="text-fg">why</strong> it
              matters, and <strong className="text-fg">how</strong> to fix
              it. Click any card to expand.
            </p>
            <div className="flex gap-2" role="group" aria-label="Expand all or collapse all cards">
              <button
                type="button"
                onClick={() => expandAll(rows)}
                className="rounded-xs border border-border bg-surface px-3 py-1 text-sm hover:bg-surface-muted"
              >
                Expand all
              </button>
              <button
                type="button"
                onClick={collapseAll}
                className="rounded-xs border border-border bg-surface px-3 py-1 text-sm hover:bg-surface-muted"
              >
                Collapse all
              </button>
            </div>
          </div>

          <ol className="m-0 grid list-none gap-3 p-0" aria-label="Issues">
            {rows.map((row) => (
              <IssueCard
                key={row.issue_key}
                row={row}
                expanded={expanded.has(row.issue_key)}
                onToggle={() => toggleCard(row.issue_key)}
              />
            ))}
          </ol>
        </>
      )}

      <p className="mt-4 text-xs text-fg-subtle">
        <strong>What &ldquo;Priority&rdquo; means here.</strong> Severity
        weight × log(1 + pages affected). A higher number means &ldquo;fix
        this first.&rdquo;
      </p>
    </>
  );
}

function IssueCard({
  row,
  expanded,
  onToggle,
}: {
  row: IssueRow;
  expanded: boolean;
  onToggle: () => void;
}) {
  // The deep-link the row's detail_url builds points at /scans/{id}/
  // issues/{key}, which is the canonical /scans/... path. The SPA's
  // route tree mounts at /app, so we keep the path the same and let
  // React Router resolve it (the basename is configured globally).
  const detailHref = row.detail_url;

  const open = row.status_summary.new > 0 ||
    row.status_summary.reviewing > 0 ||
    row.status_summary.in_progress > 0;

  return (
    <li className="m-0">
      <article
        className={
          "rounded-xs border bg-surface transition-colors " +
          (expanded
            ? "border-umich-blue/40 shadow-card"
            : "border-border")
        }
      >
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-controls={`issue-body-${row.issue_key}`}
          className="grid w-full min-h-target grid-cols-[1fr_auto] items-center gap-x-3 gap-y-2 px-4 py-3 text-left hover:bg-surface-muted/60"
        >
          <div className="flex flex-wrap items-center gap-2">
            <ConformanceBadge level={row.conformance} />
            <span className="text-base font-semibold text-fg">{row.title}</span>
          </div>
          <ChevronDown
            className={
              "h-5 w-5 shrink-0 text-fg-subtle transition-transform row-span-3 " +
              (expanded ? "rotate-180" : "")
            }
            aria-hidden
          />
          <div className="col-start-1 row-start-2 flex flex-wrap items-center gap-2 text-sm text-fg-muted">
            {row.wcag_sc ? (
              <span>
                <strong className="text-fg">SC {row.wcag_sc}</strong>
                {row.wcag_name ? `: ${row.wcag_name}` : ""}
              </span>
            ) : (
              <strong className="text-fg">Best-practice</strong>
            )}
            <span>·</span>
            <span>
              {row.responsibility.charAt(0).toUpperCase() +
                row.responsibility.slice(1)}
            </span>
            {row.difficulty !== "Unknown" && (
              <>
                <span>·</span>
                <span>{row.difficulty}</span>
              </>
            )}
            {row.abilities_affected.length > 0 && <span>·</span>}
            {row.abilities_affected.map((a) => (
              <span
                key={a}
                className="inline-block rounded-full border border-border bg-surface-muted px-2 py-0.5 text-2xs"
                title={`Affects users with ${a} impairments`}
              >
                {a.charAt(0).toUpperCase() + a.slice(1)}
              </span>
            ))}
          </div>
          <div className="col-start-1 row-start-3 flex flex-wrap items-center gap-3 text-sm">
            <span>
              <strong className="text-fg">{row.occurrence_count}</strong>{" "}
              occurrence{row.occurrence_count !== 1 ? "s" : ""}
            </span>
            <span>
              on <strong className="text-fg">{row.page_count}</strong> page
              {row.page_count !== 1 ? "s" : ""}
            </span>
            <span title="Severity weight × log(1 + pages)">
              Priority{" "}
              <strong className="text-fg">{row.priority.toFixed(2)}</strong>
            </span>
            {open ? (
              <>
                {row.status_summary.new > 0 && (
                  <span className="inline-block rounded-xs bg-sev-major-bg/15 px-1.5 py-0.5 text-2xs text-fg">
                    {row.status_summary.new} new
                  </span>
                )}
                {row.status_summary.reviewing > 0 && (
                  <span className="inline-block rounded-xs bg-umich-blue/15 px-1.5 py-0.5 text-2xs text-fg">
                    {row.status_summary.reviewing} reviewing
                  </span>
                )}
                {row.status_summary.in_progress > 0 && (
                  <span className="inline-block rounded-xs bg-umich-blue/25 px-1.5 py-0.5 text-2xs text-fg">
                    {row.status_summary.in_progress} in progress
                  </span>
                )}
              </>
            ) : (
              <span className="text-2xs text-fg-subtle">all triaged</span>
            )}
          </div>
        </button>

        {expanded && (
          <div
            id={`issue-body-${row.issue_key}`}
            className="border-t border-border px-4 py-3 text-sm text-fg"
          >
            {row.description && (
              <section className="my-2">
                <h3 className="mb-1 text-2xs font-bold uppercase tracking-wider text-fg-muted">
                  What is happening
                </h3>
                <p>{row.description}</p>
              </section>
            )}
            {row.why_matters && (
              <section className="my-2">
                <h3 className="mb-1 text-2xs font-bold uppercase tracking-wider text-fg-muted">
                  Why it matters
                </h3>
                <p>{row.why_matters}</p>
              </section>
            )}
            {row.fix_steps.length > 0 && (
              <section className="my-2">
                <h3 className="mb-1 text-2xs font-bold uppercase tracking-wider text-fg-muted">
                  How to fix
                </h3>
                <ol className="list-decimal space-y-1 pl-5">
                  {row.fix_steps.map((step, i) => (
                    <li
                      key={i}
                      // Steps include inline <code>/<em> from the YAML.
                      // Trust boundary is sound because we author the
                      // rule book; same justification as the audit
                      // report renderer.
                      dangerouslySetInnerHTML={{ __html: step }}
                    />
                  ))}
                </ol>
              </section>
            )}
            {!row.description && !row.why_matters && row.fix_steps.length === 0 && (
              <p className="text-fg-muted">
                No templated card for this issue yet — add one to{" "}
                <code>rules/audit_report.yaml</code> and the what / why /
                how will appear here.
              </p>
            )}
            {row.acceptance && (
              <p className="mt-3 text-sm">
                <strong>Done when:</strong> {row.acceptance}
              </p>
            )}

            <p className="mt-3 flex flex-wrap items-center gap-3 border-t border-dashed border-border pt-3 text-sm">
              <Link
                to={detailHref}
                className="rounded-xs bg-umich-blue px-3 py-1.5 font-semibold text-fg-inverse no-underline hover:bg-umich-blue/90"
              >
                Full detail · pages affected →
              </Link>
              {row.help_url && (
                <a
                  href={row.help_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-umich-blue underline underline-offset-2"
                >
                  Rule docs{" "}
                  <ExternalLink className="inline h-3 w-3" aria-hidden />
                  <span className="sr-only">opens in a new tab</span>
                </a>
              )}
            </p>
          </div>
        )}
      </article>
    </li>
  );
}

function ConformanceBadge({ level }: { level: ConformanceLabel }) {
  const bg = {
    A: "bg-[#b00060]",
    AA: "bg-[#4b1d8a]",
    AAA: "bg-[#2e6694]",
    BP: "bg-[#4a4a4a]",
  }[level];
  return (
    <span
      className={`${bg} inline-block rounded-xs px-2 py-0.5 text-2xs font-bold uppercase tracking-wider text-white`}
      title="WCAG conformance level"
    >
      {level}
    </span>
  );
}

function FilterChip({
  label,
  onRemove,
}: {
  label: string;
  onRemove: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onRemove}
      className="inline-flex min-h-target items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-sm text-fg hover:bg-surface-muted"
    >
      {label}
      <X className="h-3 w-3" aria-hidden />
      <span className="sr-only">Remove filter</span>
    </button>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col text-xs font-semibold uppercase tracking-wide text-fg-subtle">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 min-h-target rounded-xs border border-border bg-surface px-2 py-2 text-base font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
