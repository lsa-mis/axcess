import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, blobUrl } from "../api/client";
import { Card, PageLink, StatCard } from "./ui";
import ConformanceBadge from "./ConformanceBadge";
import type { AbilityLabel } from "../api/types";

const STATUS_LABELS_ORDER = [
  "new",
  "reviewing",
  "in_progress",
  "remediated",
  "accepted_risk",
  "false_positive",
] as const;

/**
 * The full evidence for one issue group: what it is, why it matters, the fix,
 * the verification steps, and every affected page with its occurrences and
 * instance screenshots. This is the "issue evidence page" content, rendered
 * inline, both on the per-issue route (under a ReportHeader) and expanded
 * inside the Issues list, so a reviewer never has to leave the table to see
 * all occurrences.
 */
export default function IssueEvidence({
  scanId,
  issueKey,
}: {
  scanId: number;
  issueKey: string;
}) {
  const [sort, setSort] = useState("occurrences_desc");
  const { data, isLoading, error } = useQuery({
    queryKey: ["issue-detail", scanId, issueKey, sort],
    queryFn: () => api.getIssueDetail(scanId, issueKey, sort),
    enabled: Number.isFinite(scanId) && !!issueKey,
  });

  if (error) {
    return (
      <Card className="p-4 text-sm text-sev-critical" role="alert">
        Couldn&rsquo;t load this issue&rsquo;s evidence. The stored scan data is unchanged.
      </Card>
    );
  }
  if (!data || isLoading) {
    return <p className="px-4 py-6 text-sm text-fg-muted" role="status">Loading issue evidence…</p>;
  }

  const { row, pages, description, why_matters, fix_steps, verify_manual,
    verify_automated, acceptance, help_url } = data;
  const isInformational = row.review_lane === "informational";
  const laneLabel = row.review_lane === "likely_barrier"
    ? "Barrier"
    : row.review_lane === "expert_review"
      ? "Needs confirmation"
      : "Informational evidence";
  const laneClass = row.review_lane === "likely_barrier"
    ? "border-umich-blue/30 bg-umich-blue/5"
    : row.review_lane === "expert_review"
      ? "border-sev-major/40 bg-sev-major-bg"
      : "border-border bg-surface-muted";

  return (
    <div className="p-4">
      <Card className={`mb-4 p-4 ${laneClass}`}>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
            {!isInformational && <ConformanceBadge level={row.conformance} />}
            <span>{laneLabel}</span>
          </h2>
          <span className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-surface px-2 py-1 text-xs font-semibold capitalize">
              {row.evidence_confidence} evidence confidence
            </span>
            {help_url && (
              <a
                href={help_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs font-semibold text-umich-blue underline underline-offset-2"
              >
                Rule docs
                <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                <span className="sr-only">opens in a new tab</span>
              </a>
            )}
          </span>
        </div>
        <p className="mt-1 text-sm text-fg-muted">{row.evidence_summary}</p>
        {row.review_lane === "expert_review" && (
          <p className="mt-2 text-sm font-semibold">
            Do not describe this as a confirmed barrier until the expert decision is documented.
          </p>
        )}
        {isInformational && (
          <p className="mt-2 text-sm font-semibold">
            No barrier was detected by this check. This record is read-only evidence retained for transparency.
          </p>
        )}
      </Card>

      {/* Stat tiles, same visual primitives as the Issues list, so the
          design language stays continuous between list and detail. */}
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <StatCard label="Criterion level" value={row.wcag_sc ? row.conformance : "n/a"} />
        {!isInformational && (
          <StatCard
            label="Priority"
            value={`${row.priority.toFixed(2)} · ${priorityTier(row.priority)}`}
            hint="Fix sooner when it's both severe and affects many pages."
          />
        )}
        <StatCard label="Pages affected" value={row.page_count} />
        <StatCard label="Occurrences" value={row.occurrence_count} />
        {!isInformational && row.difficulty !== "Unknown" && (
          <StatCard label="Difficulty" value={row.difficulty} />
        )}
        {!isInformational && (
          <StatCard
            label="Responsibility"
            value={
              row.responsibility.charAt(0).toUpperCase() +
              row.responsibility.slice(1)
            }
          />
        )}
      </div>

      {!isInformational && row.abilities_affected.length > 0 && (
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
        <h3 className="mb-2 text-base font-semibold">
          {isInformational ? "Evidence summary" : "About this issue"}
        </h3>

        <h4 className="text-2xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
          What it is
        </h4>
        <p className="mt-1 text-sm text-fg">
          {description ||
            row.evidence_summary ||
            "This is an automated evidence record. Review the affected pages below for the captured detail."}
        </p>
        {!isInformational && why_matters && (
          <p className="mt-2 text-sm text-fg-muted">
            <span className="font-semibold text-fg">Why it matters:</span> {why_matters}
          </p>
        )}

        {!isInformational && fix_steps.length > 0 && (
          <>
            <h4 className="mt-4 text-2xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
              Expected behavior
            </h4>
            <ol className="mt-1 list-decimal space-y-1.5 pl-5 text-sm text-fg">
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
        {!isInformational && acceptance && (
          <p className="mt-2 text-sm text-fg-muted">
            <span className="font-semibold text-fg">Done when:</span> {acceptance}
          </p>
        )}

        {!isInformational && (verify_manual || verify_automated) && (
          <>
            <h4 className="mt-4 text-2xs font-semibold uppercase tracking-[0.12em] text-fg-subtle">
              {row.review_lane === "expert_review"
                ? "What to check to confirm"
                : "How to verify"}
            </h4>
            <ul className="mt-1 list-disc space-y-1.5 pl-5 text-sm text-fg">
              {verify_manual && <li>{verify_manual}</li>}
              {verify_automated && <li>{verify_automated}</li>}
              {row.review_lane === "expert_review" && (
                <li className="font-semibold text-umich-blue">
                  Confirm the finding in page context before reporting it as a barrier.
                </li>
              )}
            </ul>
          </>
        )}
      </Card>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-border bg-surface-muted px-4 py-3">
          <h3 className="text-base font-semibold">
            {isInformational ? "Pages with this evidence" : "Pages with this issue"}
            <span className="ml-2 text-sm font-normal text-fg-muted">
              {pages.length} page{pages.length !== 1 ? "s" : ""}
            </span>
          </h3>
          <label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">
            Sort by
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="min-h-target rounded-xs border border-border bg-surface px-2 py-1 text-sm font-normal normal-case tracking-normal text-fg focus:border-umich-blue focus:outline-none"
            >
              <option value="occurrences_desc">Occurrences (most first)</option>
              <option value="occurrences_asc">Occurrences (least first)</option>
              <option value="url">Page URL (A–Z)</option>
              {!isInformational && <option value="status">Status (un-triaged first)</option>}
            </select>
          </label>
        </div>
        {pages.length === 0 ? (
          <div className="p-4 text-sm text-fg-muted">
            No pages are currently associated with this evidence group.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">
                Pages with the evidence group {row.title}
              </caption>
              <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
                <tr>
                  <th scope="col" className="w-10 px-3 py-2 text-right font-semibold">
                    <span aria-hidden="true">#</span>
                    <span className="sr-only">Row number</span>
                  </th>
                  <th scope="col" className="px-3 py-2 text-left font-semibold">
                    Page
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-semibold">
                    Occurrences
                  </th>
                  {!isInformational && (
                    <th scope="col" className="px-3 py-2 text-left font-semibold">
                      Status
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {pages.map((p, pageIndex) => {
                  const missingScreenshots = Math.max(
                    0,
                    p.occurrence_count - p.screenshot_hashes.length,
                  );
                  const pageLabel = p.page_title || p.page_url;
                  return (
                    <Fragment key={p.page_id}>
                      <tr>
                        <th
                          scope="row"
                          className="px-3 py-2 text-right align-top font-normal tabular-nums text-fg-subtle"
                        >
                          {pageIndex + 1}
                        </th>
                        <td className="px-3 py-2 align-top">
                          <PageLink
                            pageId={p.page_id}
                            scanId={scanId}
                            pageUrl={p.page_url}
                            pageTitle={p.page_title}
                            issue={issueKey}
                            origin="Issues"
                            context={issueKey}
                            contextTo={`/scans/${scanId}/issues/${encodeURIComponent(issueKey)}`}
                            backTo={`/scans/${scanId}/issues`}
                          />
                        </td>
                        <td className="px-3 py-2 text-right align-top tabular-nums">
                          {p.occurrence_count}
                        </td>
                        {!isInformational && (
                          <td className="px-3 py-2 align-top">
                            <div className="flex flex-wrap gap-1">
                              {STATUS_LABELS_ORDER.map((s) => {
                                const n = p.status_summary[s] ?? 0;
                                if (!n) return null;
                                const isOpen =
                                  s === "new" || s === "reviewing" || s === "in_progress";
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
                        )}
                      </tr>
                      {p.screenshot_hashes.length > 0 && (
                        <tr className="bg-surface-muted/40">
                          <td colSpan={isInformational ? 3 : 4} className="px-3 pb-4 pt-2">
                            <h4 className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                              Instance screenshots
                            </h4>
                            <div className="mt-2 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                              {p.screenshot_hashes.map((hash, index) => (
                                <figure
                                  key={`${hash}-${index}`}
                                  className="rounded-xs border border-border bg-surface p-2"
                                >
                                  <img
                                    src={blobUrl(hash)}
                                    alt={`Issue instance ${index + 1} on ${pageLabel}. A circular marker identifies the detected location.`}
                                    className="max-h-80 w-full rounded-xs object-contain"
                                    loading="lazy"
                                  />
                                  <figcaption className="mt-2 text-xs text-fg-muted">
                                    Instance {index + 1} of {p.occurrence_count}. The circle marks the detected location.
                                  </figcaption>
                                </figure>
                              ))}
                            </div>
                            {missingScreenshots > 0 && (
                              <p className="mt-2 text-xs text-fg-muted">
                                {missingScreenshots} additional instance{missingScreenshots === 1 ? "" : "s"} had no locatable screenshot or exceeded the per-page safety limit.
                              </p>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {row.locations.length > 0 && (
        <Card className="mb-4 p-4">
          <h3 className="mb-2 text-base font-semibold">Flagged element</h3>
          <ul className="space-y-3">
            {row.locations.map((loc) => (
              <li
                key={`${loc.page_id}:${loc.target}`}
                className="rounded-xs border border-border bg-surface-subtle p-3"
              >
                <p className="text-xs font-semibold text-fg">
                  {loc.page_title || loc.page_url}
                  {loc.page_title && (
                    <span className="ml-1 break-all font-normal text-fg-muted">
                      {loc.page_url}
                    </span>
                  )}
                </p>
                {loc.revealed_by && (
                  <p className="mt-1 text-xs text-fg">
                    After clicking &ldquo;{loc.revealed_by}&rdquo;
                  </p>
                )}
                <code className="mt-1.5 block overflow-x-auto rounded-2xs border border-border bg-surface px-2 py-1 text-2xs text-fg">
                  {loc.target}
                </code>
                {loc.html_snippet && (
                  <pre className="mt-1.5 max-h-40 overflow-auto rounded-2xs border border-sev-major/20 bg-surface p-2 text-2xs leading-relaxed text-fg">
                    <code>
                      <mark className="rounded-[2px] bg-umich-maize/40 text-fg">
                        {loc.html_snippet}
                      </mark>
                    </code>
                  </pre>
                )}
                {loc.context && (
                  <p className="mt-1.5 text-xs leading-relaxed text-fg-muted">{loc.context}</p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

/** A plain-English band for the priority score (severity × log1p(pages)). */
function priorityTier(priority: number): "High" | "Medium" | "Low" {
  if (priority >= 6) return "High";
  if (priority >= 3) return "Medium";
  return "Low";
}

