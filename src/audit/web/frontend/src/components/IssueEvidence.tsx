import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, AlertTriangle, ClipboardCheck, ExternalLink, Info, type LucideIcon } from "lucide-react";
import { api } from "../api/client";
import { Card, Disclosure } from "./ui";
import IssuePagesTable from "./IssuePagesTable";
import type { AbilityLabel, IssueRow } from "../api/types";
import { HIDDEN_ISSUE_FIELDS } from "../lib/hiddenIssueFields";

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
  const lane = LANES[row.review_lane] ?? LANES.informational;
  const isInformational = row.review_lane === "informational";
  const isLead = row.review_lane === "expert_review";
  const LaneIcon = lane.icon;

  // What it is, the next step and the background each sit in their own
  // disclosure, all closed on arrival, so the page opens on the issue's
  // title and its pages and a reviewer opens only what they need. A lead is
  // confirmed before anyone fixes it, so its checks are the next step and
  // the fix goes in the background; a barrier is the other way round.
  const verifySteps = [verify_manual, verify_automated].filter(Boolean) as string[];
  const nextSteps = isInformational ? [] : isLead ? verifySteps : fix_steps;
  const nextTitle = isLead ? "How to confirm it" : "How to fix it";
  const hasBackground =
    !!why_matters ||
    (isLead ? fix_steps.length > 0 : verifySteps.length > 0) ||
    (isLead && !!acceptance);

  return (
    <div className="space-y-4 p-4">
      <div className="space-y-3">
        <Disclosure
          id="issue-what"
          title={isInformational ? "Evidence summary" : "What it is"}
          headingLevel={2}
        >
          {/* The verdict leads the section and reads as a sentence, not a
              badge: what this record is, what that means for how it may be
              reported, and why the tool raised it. The icon and the words
              carry the lane, so the tint is never the only signal. */}
          <div className={`rounded-xs border border-l-4 p-3 ${lane.className}`}>
            <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
              <div className="flex min-w-0 items-start gap-3">
                <LaneIcon className={`mt-0.5 h-5 w-5 shrink-0 ${lane.iconClass}`} aria-hidden />
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-fg">{lane.label}</h3>
                  <p className="mt-0.5 text-sm text-fg">{lane.meaning}</p>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pl-8 text-xs sm:pl-0">
                <span className="text-fg-muted">
                  Evidence confidence:{" "}
                  <span className="font-semibold text-fg">{capitalize(row.evidence_confidence)}</span>
                </span>
                {help_url && (
                  <a
                    href={help_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-semibold text-umich-blue underline underline-offset-2"
                  >
                    Rule docs
                    <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
                    <span className="sr-only">opens in a new tab</span>
                  </a>
                )}
              </div>
            </div>
            {row.evidence_summary && (
              <p className="mt-3 pl-8 text-sm text-fg-muted">
                <span className="font-semibold text-fg">Why it was flagged: </span>
                {row.evidence_summary}
              </p>
            )}
          </div>

          {/* One strip of facts, read left to right: criterion, urgency,
              spread, who fixes it. */}
          <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-2 rounded-xs border border-border px-3 py-2">
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

          <p className="mt-3 max-w-[75ch] text-sm leading-relaxed text-fg">
            {description ? (
              <RuleText text={description} />
            ) : (
              row.evidence_summary ||
              "This is an automated evidence record. Review the affected pages below for the captured detail."
            )}
          </p>
        </Disclosure>

        {nextSteps.length > 0 && (
          <Disclosure
            id="issue-next"
            title={nextTitle}
            headingLevel={2}
            icon={<ClipboardCheck className="h-4 w-4 shrink-0 text-umich-blue" aria-hidden />}
          >
            <ol className="max-w-[75ch] list-decimal space-y-1.5 pl-6 text-sm leading-relaxed text-fg">
              {isLead
                ? nextSteps.map((step, i) => <li key={i}>{step}</li>)
                : nextSteps.map((step, i) => (
                    <li
                      key={i}
                      // Steps include inline <code> / <em> from the YAML.
                      // We trust YAML authors (it's our own rule book).
                      dangerouslySetInnerHTML={{ __html: step }}
                    />
                  ))}
              {isLead && (
                <li className="font-semibold">
                  Confirm the finding in page context before reporting it as a barrier.
                </li>
              )}
            </ol>
            {!isLead && acceptance && (
              <p className="mt-2 max-w-[75ch] text-sm text-fg-muted">
                <span className="font-semibold text-fg">Done when:</span> {acceptance}
              </p>
            )}
          </Disclosure>
        )}

        {!isInformational && hasBackground && (
          <Disclosure
            id="issue-fix"
            title={isLead ? "Why it matters, and how to fix it if confirmed" : "Why it matters, and how to verify the fix"}
            headingLevel={2}
          >
            {why_matters && <p className="max-w-[75ch] text-sm text-fg-muted">{why_matters}</p>}
            {isLead && fix_steps.length > 0 && (
              <>
                <h3 className="mt-3 text-2xs font-semibold text-fg-subtle">Expected behavior</h3>
                <ol className="mt-1 max-w-[75ch] list-decimal space-y-1.5 pl-5 text-sm text-fg">
                  {fix_steps.map((step, i) => (
                    <li key={i} dangerouslySetInnerHTML={{ __html: step }} />
                  ))}
                </ol>
              </>
            )}
            {isLead && acceptance && (
              <p className="mt-2 max-w-[75ch] text-sm text-fg-muted">
                <span className="font-semibold text-fg">Done when:</span> {acceptance}
              </p>
            )}
            {!isLead && verifySteps.length > 0 && (
              <>
                <h3 className="mt-3 text-2xs font-semibold text-fg-subtle">How to verify</h3>
                <ul className="mt-1 max-w-[75ch] list-disc space-y-1.5 pl-5 text-sm text-fg">
                  {verifySteps.map((step, i) => <li key={i}>{step}</li>)}
                </ul>
              </>
            )}
          </Disclosure>
        )}
      </div>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-border bg-surface-muted px-4 py-3">
          <h2 className="text-base font-semibold">
            Pages with this issue
            <span className="ml-2 text-sm font-normal text-fg-muted">
              {pages.length} page{pages.length !== 1 ? "s" : ""}
            </span>
          </h2>
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
    </div>
  );
}

/**
 * How each review lane reads at the top of the record. The meaning line says
 * what the lane permits a reviewer to do with the finding, in words, so the
 * tint and icon are never the only cue.
 */
const LANES: Record<
  IssueRow["review_lane"],
  { label: string; meaning: string; icon: LucideIcon; className: string; iconClass: string }
> = {
  likely_barrier: {
    label: "Barrier",
    meaning: "Automated checks found a likely accessibility barrier. Fix it, then verify.",
    icon: AlertOctagon,
    className: "border-umich-blue/30 border-l-umich-blue bg-umich-blue/5",
    iconClass: "text-umich-blue",
  },
  expert_review: {
    label: "Needs confirmation",
    meaning:
      "Not a confirmed barrier. Don\u2019t report it as one until the expert decision is documented.",
    icon: AlertTriangle,
    className: "border-sev-major/40 border-l-sev-major bg-sev-major-bg",
    iconClass: "text-sev-major",
  },
  informational: {
    label: "Informational evidence",
    meaning:
      "No barrier was detected by this check. This record is read-only evidence retained for transparency.",
    icon: Info,
    className: "border-border border-l-fg-subtle bg-surface-muted",
    iconClass: "text-fg-muted",
  },
};

/**
 * Rule-book prose with its inline ``<code>`` spans rendered as code. Only that
 * one tag is honoured and everything else stays text: a description can carry
 * a scanner diagnostic quoted from the crawled page, which must never become
 * markup.
 */
function RuleText({ text }: { text: string }) {
  const parts = text.split(/<code>([\s\S]*?)<\/code>/g);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <code key={i} className="rounded-2xs bg-surface-muted px-1 py-px text-[0.9em]">
            {decodeEntities(part)}
          </code>
        ) : (
          decodeEntities(part)
        ),
      )}
    </>
  );
}

function decodeEntities(value: string): string {
  return value
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&");
}

/** One label/value line in the issue's spec list. */
type IssueFact = { label: string; value: string | number; hint?: string };

/**
 * The issue's at-a-glance metadata, in reading order: what the criterion is,
 * how urgent it is, how far it spreads, and who fixes it. Entries that carry no
 * meaning for the record are dropped rather than shown empty, an informational
 * record has no priority, difficulty or owner because nothing is being asked of
 * anyone. Fields named in ``HIDDEN_ISSUE_FIELDS`` are left out for now.
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
  return facts.filter((fact) => !HIDDEN_ISSUE_FIELDS.has(fact.label));
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

