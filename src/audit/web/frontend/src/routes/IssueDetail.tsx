import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink } from "lucide-react";
import { api } from "../api/client";
import {
  Card,
  DownloadLink,
  EmptyState,
  LinkButton,
  PageHeader,
  PageLink,
  StatCard,
} from "../components/ui";
import type { AbilityLabel, ConformanceLabel } from "../api/types";

const STATUS_LABELS_ORDER = [
  "new",
  "reviewing",
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
] as const;

/**
 * Per-issue detail view — the Siteimprove "page 2".
 *
 * Lands here from the Issues list (one row click = one detail page).
 * Lays out the same visual primitives the Issues table uses
 * (conformance badge, ability tags, stat cards) so the design
 * language is continuous between list and detail.
 *
 * Pages-with-this-issue table uses the shared `<PageLink>` primitive,
 * which means every page URL on this view is a clickable external
 * link to the actual page — with a secondary "view in audit" link
 * for our in-app per-page view.
 */
export default function IssueDetailRoute() {
  const { scanId, issueKey } = useParams<{
    scanId: string;
    issueKey: string;
  }>();
  const id = Number(scanId);
  const key = decodeURIComponent(issueKey ?? "");
  const [params, setParams] = useSearchParams();
  const sort = params.get("sort") ?? "occurrences_desc";

  const { data: scan, error: scanError } = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
  });
  const { data, isLoading, error } = useQuery({
    queryKey: ["issue-detail", id, key, sort],
    queryFn: () => api.getIssueDetail(id, key, sort),
    enabled: Number.isFinite(id) && !!key,
  });

  const setSort = (value: string) => {
    const next = new URLSearchParams(params);
    next.set("sort", value);
    setParams(next);
  };

  if (scanError) {
    return (
      <Card className="p-4 text-sm text-sev-critical">
        {scanError instanceof Error ? scanError.message : String(scanError)}
      </Card>
    );
  }
  if (error) {
    return (
      <EmptyState
        title="Issue not found"
        message={
          "This issue isn't part of the current scan. It may have been " +
          "resolved or the URL may be stale. Try the Issues list."
        }
        action={
          <LinkButton to={`/scans/${id}/issues`} variant="primary">
            Back to Issues
          </LinkButton>
        }
      />
    );
  }
  if (!scan || !data || isLoading) {
    return <div className="text-fg-muted">Loading…</div>;
  }

  const { row, pages, description, why_matters, fix_steps, verify_manual,
    verify_automated, acceptance, help_url } = data;

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Scans", to: "/scans" },
          { label: `Scan #${scan.id}`, to: `/scans/${scan.id}` },
          { label: "Issues", to: `/scans/${scan.id}/issues` },
          { label: row.title },
        ]}
        title={
          <span className="flex flex-wrap items-center gap-2">
            <ConformanceBadge level={row.conformance} />
            <span>{row.title}</span>
          </span>
        }
        subtitle={
          row.wcag_sc
            ? `WCAG SC ${row.wcag_sc}${row.wcag_name ? `: ${row.wcag_name}` : ""}`
            : "Best-practice — no WCAG SC mapping"
        }
        actions={
          <>
            {help_url && (
              <LinkButton
                to={help_url}
                variant="secondary"
                reloadDocument
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink className="h-4 w-4" aria-hidden />
                Rule docs
              </LinkButton>
            )}
            {/* DownloadLink (plain <a>), not LinkButton — see the
                comment on the Issues view's export buttons: React
                Router's basename rewrites `/api/...` to `/app/api/...`
                under our mount, which hits the SPA 404 page. */}
            <DownloadLink
              href={`/api/scans/${scan.id}/export/audit`}
              variant="primary"
            >
              <Download className="h-4 w-4" aria-hidden />
              Audit report
            </DownloadLink>
          </>
        }
      />

      {/* Stat tiles — same visual primitives as the Issues list, so
          the design language stays continuous between list and detail. */}
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <StatCard label="Conformance" value={row.conformance} />
        <StatCard
          label="Priority"
          value={row.priority.toFixed(2)}
          hint="severity x log(1+pages)"
        />
        <StatCard label="Pages affected" value={row.page_count} />
        <StatCard label="Occurrences" value={row.occurrence_count} />
        {row.difficulty !== "Unknown" && (
          <StatCard label="Difficulty" value={row.difficulty} />
        )}
        <StatCard
          label="Responsibility"
          value={
            row.responsibility.charAt(0).toUpperCase() +
            row.responsibility.slice(1)
          }
        />
      </div>

      {row.abilities_affected.length > 0 && (
        <p className="mb-3 text-sm">
          <strong className="text-fg">Abilities affected:</strong>{" "}
          {row.abilities_affected.map((a: AbilityLabel) => (
            <span
              key={a}
              className="ml-1 inline-block rounded-full border border-border bg-surface-muted px-2 py-0.5 text-2xs"
              title={`Affects users with ${a} impairments`}
            >
              {a.charAt(0).toUpperCase() + a.slice(1)}
            </span>
          ))}
        </p>
      )}

      <Card className="mb-4 p-4">
        <h2 className="mb-2 text-base font-semibold">Description</h2>
        {description ? (
          <p className="text-sm text-fg">{description}</p>
        ) : (
          <p className="text-sm text-fg-muted">
            No templated description for this issue type yet. See the
            sample pages below for raw data; consider adding a card to{" "}
            <code>rules/audit_report.yaml</code> for future reports.
          </p>
        )}
        {why_matters && (
          <>
            <h3 className="mt-3 text-sm font-semibold">Why it matters</h3>
            <p className="text-sm text-fg">{why_matters}</p>
          </>
        )}
        {fix_steps.length > 0 && (
          <>
            <h3 className="mt-3 text-sm font-semibold">Fix (do this)</h3>
            <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm text-fg">
              {fix_steps.map((step, i) => (
                <li
                  key={i}
                  // Steps include inline <code> / <em> from the YAML.
                  // We trust YAML authors (it's our own rule book).
                  dangerouslySetInnerHTML={{ __html: step }}
                />
              ))}
            </ol>
          </>
        )}
        {(verify_manual || verify_automated || acceptance) && (
          <>
            <h3 className="mt-3 text-sm font-semibold">Verify it is fixed</h3>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-fg">
              {verify_manual && (
                <li>
                  <strong>Manual:</strong> {verify_manual}
                </li>
              )}
              {verify_automated && (
                <li>
                  <strong>Automated:</strong> {verify_automated}
                </li>
              )}
              {acceptance && (
                <li>
                  <strong>Acceptance:</strong> {acceptance}
                </li>
              )}
            </ul>
          </>
        )}
      </Card>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-border bg-surface-muted px-4 py-3">
          <h2 className="text-base font-semibold">
            Pages with this issue
            <span className="ml-2 text-sm font-normal text-fg-muted">
              {pages.length} page{pages.length !== 1 ? "s" : ""}
            </span>
          </h2>
          <label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
            Sort by
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="min-h-target rounded-xs border border-border bg-surface px-2 py-1 text-sm font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
            >
              <option value="occurrences_desc">
                Occurrences (most first)
              </option>
              <option value="occurrences_asc">
                Occurrences (least first)
              </option>
              <option value="url">Page URL (A–Z)</option>
              <option value="status">Status (un-triaged first)</option>
            </select>
          </label>
        </div>
        {pages.length === 0 ? (
          <div className="p-4 text-sm text-fg-muted">
            No pages currently associated with this issue.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">
                Pages with the issue {row.title}
              </caption>
              <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
                <tr>
                  <th
                    scope="col"
                    className="px-3 py-2 text-left font-semibold"
                  >
                    Page
                  </th>
                  <th
                    scope="col"
                    className="px-3 py-2 text-right font-semibold"
                  >
                    Occurrences
                  </th>
                  <th
                    scope="col"
                    className="px-3 py-2 text-left font-semibold"
                  >
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {pages.map((p) => (
                  <tr key={p.page_id}>
                    <td className="px-3 py-2 align-top">
                      <PageLink
                        pageId={p.page_id}
                        pageUrl={p.page_url}
                        pageTitle={p.page_title}
                      />
                    </td>
                    <td className="px-3 py-2 text-right align-top tabular-nums">
                      {p.occurrence_count}
                    </td>
                    <td className="px-3 py-2 align-top">
                      <div className="flex flex-wrap gap-1">
                        {STATUS_LABELS_ORDER.map((s) => {
                          const n = p.status_summary[s] ?? 0;
                          if (!n) return null;
                          const isOpen =
                            s === "new" ||
                            s === "reviewing" ||
                            s === "in_progress";
                          return (
                            <span
                              key={s}
                              className={
                                isOpen
                                  ? "inline-block rounded-xs bg-sev-major-bg/15 px-1.5 py-0.5 text-2xs text-fg"
                                  : "inline-block rounded-xs bg-surface-muted px-1.5 py-0.5 text-2xs text-fg-subtle"
                              }
                            >
                              {n} {s.replace(/_/g, " ")}
                            </span>
                          );
                        })}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
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
      className={`${bg} inline-block rounded-xs px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-white`}
      title="WCAG conformance level"
    >
      {level}
    </span>
  );
}
