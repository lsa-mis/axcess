import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api } from "../api/client";
import { Card, Disclosure } from "./ui";
import ConformanceBadge from "./ConformanceBadge";
import IssuePagesTable from "./IssuePagesTable";
import type { AbilityLabel, IssueRow } from "../api/types";

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
  origin = "Issues",
  backTo,
}: {
  scanId: number;
  issueKey: string;
  /**
   * The view this evidence is being read in, and the path back to it. They
   * travel with every page link below so the topbar trail on the page's own
   * views names the view the reviewer actually came from — the only way back
   * in the desktop app, which has no browser back button. Defaults to the
   * Issues list, where this is expanded inline.
   */
  origin?: string;
  backTo?: string;
}) {
  const parentTo = backTo ?? `/scans/${scanId}/issues`;
  const { data, isLoading, error } = useQuery({
    queryKey: ["issue-detail", scanId, issueKey],
    queryFn: () => api.getIssueDetail(scanId, issueKey),
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

      {/* One strip of facts, read left to right: criterion, urgency,
          spread, who fixes it. The earlier stacked list put each fact on its
          own row, which pushed the pages — the part a reviewer opens this
          record for — below the fold on every issue. */}
      <dl className="mb-4 flex flex-wrap gap-x-6 gap-y-2 rounded-xs border border-border bg-surface px-4 py-3">
        {issueFacts(row, isInformational).map((fact) => (
          <div key={fact.label} className="flex min-w-0 flex-col" title={fact.hint}>
            <dt className="text-2xs font-medium text-fg-subtle">{fact.label}</dt>
            <dd className="text-sm font-semibold tabular-nums text-fg">{fact.value}</dd>
          </div>
        ))}
        {!isInformational && row.abilities_affected.length > 0 && (
          <div className="flex min-w-0 flex-col">
            <dt className="text-2xs font-medium text-fg-subtle">Abilities affected</dt>
            <dd className="flex flex-wrap gap-1 pt-0.5">
              {row.abilities_affected.map((a: AbilityLabel) => (
                <span
                  key={a}
                  className="inline-block rounded-full border border-border bg-surface-muted px-2 py-0.5 text-2xs font-semibold"
                  title={`Affects users with ${a} impairments`}
                >
                  {capitalize(a)}
                </span>
              ))}
            </dd>
          </div>
        )}
      </dl>

      <Card className="mb-4 overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-border bg-surface-muted px-4 py-3">
          <h3 className="text-base font-semibold">
            Pages with this issue
            <span className="ml-2 text-sm font-normal text-fg-muted">
              {pages.length} page{pages.length !== 1 ? "s" : ""}
            </span>
          </h3>
        </div>
        <IssuePagesTable
          scanId={scanId}
          issueKey={issueKey}
          row={row}
          pages={pages}
          backTo={parentTo}
          origin={origin}
        />
      </Card>

      <Card className="mb-4 p-4">
        <h3 className="text-base font-semibold">
          {isInformational ? "Evidence summary" : "What it is"}
        </h3>
        <p className="mt-1 text-sm text-fg">
          {description ||
            row.evidence_summary ||
            "This is an automated evidence record. Review the affected pages above for the captured detail."}
        </p>
        {!isInformational && (why_matters || fix_steps.length > 0 || verify_manual || verify_automated) && (
          <Disclosure
            id="issue-fix"
            title={row.review_lane === "expert_review" ? "Why it matters, and what to check" : "Why it matters, and how to fix it"}
            headingLevel={3}
            className="mt-3"
          >
            {why_matters && <p className="text-sm text-fg-muted">{why_matters}</p>}
            {fix_steps.length > 0 && (
              <>
                <h4 className="mt-3 text-2xs font-semibold text-fg-subtle">Expected behavior</h4>
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
            {acceptance && (
              <p className="mt-2 text-sm text-fg-muted">
                <span className="font-semibold text-fg">Done when:</span> {acceptance}
              </p>
            )}
            {(verify_manual || verify_automated) && (
              <>
                <h4 className="mt-3 text-2xs font-semibold text-fg-subtle">
                  {row.review_lane === "expert_review" ? "What to check to confirm" : "How to verify"}
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
          </Disclosure>
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

/** One label/value line in the issue's spec list. */
type IssueFact = { label: string; value: string | number; hint?: string };

/**
 * The issue's at-a-glance metadata, in reading order: what the criterion is,
 * how urgent it is, how far it spreads, and who fixes it. Entries that carry no
 * meaning for the record are dropped rather than shown empty, an informational
 * record has no priority, difficulty or owner because nothing is being asked of
 * anyone.
 */
function issueFacts(row: IssueRow, isInformational: boolean): IssueFact[] {
  const facts: IssueFact[] = [
    { label: "Criterion level", value: row.wcag_sc ? row.conformance : "n/a" },
  ];
  if (!isInformational) {
    facts.push({
      label: "Priority",
      value: priorityTier(row.priority),
      hint: "Severity × how many pages it touches. Fix sooner when both are high.",
    });
  }
  facts.push(
    { label: "Pages affected", value: row.page_count },
    { label: "Occurrences", value: row.occurrence_count },
  );
  if (!isInformational && row.difficulty !== "Unknown") {
    facts.push({ label: "Difficulty", value: row.difficulty });
  }
  if (!isInformational) {
    facts.push({ label: "Responsibility", value: capitalize(row.responsibility) });
  }
  return facts;
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

/** A plain-English band for the priority score (severity × log1p(pages)). */
function priorityTier(priority: number): "High" | "Medium" | "Low" {
  if (priority >= 6) return "High";
  if (priority >= 3) return "Medium";
  return "Low";
}

