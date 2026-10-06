import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, PlusCircle, ServerCrash } from "lucide-react";
import { api } from "../api/client";
import { siteLabel } from "../components/ReportCrumb";
import { REVIEW_TYPE_LABEL } from "../lib/terms";
import {
  Card,
  EmptyState,
  LinkButton,
  PageHeader,
  ScanStatusBadge,
  ScanTag,
  StatCard,
  relativeTime,
} from "../components/ui";

/**
 * The workbench landing screen, written for the person who has to make the
 * decisions rather than for someone being sold the tool.
 *
 * It used to open with four counts about the software, completed scans, pages
 * crawled, "image evidence · raw image records", most recent scan id, under a
 * dark marketing panel and a permanent three-bullet "How Axcess works"
 * explainer. None of that answers the only question an accessibility expert
 * arrives with: *what is waiting for my judgement?* So the page leads with the
 * review queue, states the counts in the report's own vocabulary, and keeps
 * the product explanation off a screen its reader sees every day.
 */
export default function DashboardRoute() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
  });

  const scans = data ?? [];
  const completed = scans.filter((s) => s.status === "completed");
  const running = scans.find((s) => s.status === "running");
  const latest = completed[0];

  // Lane counts are per report, so this is deliberately the newest report only
  //, and the copy says so. Summing them across every scan would invent a
  // site-wide backlog the data does not support.
  const { data: latestIssues } = useQuery({
    queryKey: ["issues", latest?.id, "dashboard"],
    queryFn: () => api.listIssues(latest!.id),
    enabled: !!latest,
  });

  const reviewLeads = latestIssues?.review_lane_counts.expert_review ?? 0;
  const likelyBarriers = latestIssues?.review_lane_counts.likely_barrier ?? 0;

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={
          completed.length === 0
            ? "Scan a site, look at what the scan found, and make a report of what to fix."
            : `${completed.length} completed report${completed.length === 1 ? "" : "s"} · results for an expert to review, not proof that a site meets accessibility rules.`
        }
      />

      {error && (
        <Card className="mb-4 flex items-start gap-2 border-sev-critical/30 bg-sev-critical-bg p-4 text-sev-critical" role="alert">
          <ServerCrash className="mt-0.5 h-5 w-5" aria-hidden />
          <div className="text-sm">
            <strong>Axcess could not load the reports.</strong>{" "}
            {error instanceof Error ? error.message : String(error)}
          </div>
        </Card>
      )}

      {running && (
        <Card className="mb-4 flex flex-wrap items-center justify-between gap-3 border-umich-blue/30 bg-umich-blue/5 p-4">
          <div className="flex items-center gap-2 text-sm">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-umich-maize" aria-hidden />
            <strong className="text-fg">Scan {running.id}</strong>
            <span className="break-all text-fg-muted">
              is scanning {siteLabel(running.seed_url)}
            </span>
          </div>
          {/* Plain inline Link is correct here, this is a body text link, not
              a button-shaped affordance. The variant API on LinkButton is for
              chrome elements (page-header CTAs, table action cells, etc). */}
          <Link
            to={`/scans/${running.id}`}
            className="text-sm font-semibold text-umich-blue underline underline-offset-2"
          >
            View progress →
          </Link>
        </Card>
      )}

      {!error && latest && latestIssues && (
        <Card className="mb-5 p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-2xs font-semibold text-fg-subtle">
                Waiting for you · Report #{latest.id} ·{" "}
                <span className="break-all normal-case tracking-normal text-fg-muted">
                  {siteLabel(latest.seed_url)}
                </span>
              </p>
              {/* The headline is the decision, not the total. A count of
                  "issues" flatters the tool; a count of judgements owed is the
                  thing the reader actually has to clear. */}
              <h2 className="mt-1.5 text-xl font-semibold tracking-tight text-fg sm:text-2xl">
                {reviewLeads > 0
                  ? `${reviewLeads} issue${reviewLeads === 1 ? "" : "s"} need${reviewLeads === 1 ? "s" : ""} a person to decide`
                  : latestIssues.total_unfiltered > 0
                    ? "No issues need a person to decide"
                    : "The checks found no issues"}
              </h2>
              <p className="mt-1.5 max-w-2xl text-sm leading-6 text-fg-muted">
                {/* "Check it on the page, then fix it", not "sure enough to fix
                    without checking first" (as this said before): a fixed rule
                    can still be wrong about a page, and the glossary says to
                    confirm each one (docs/glossary.md, "Zero false positive
                    goal"). */}
                {likelyBarriers > 0
                  ? `${likelyBarriers} issue${likelyBarriers === 1 ? " is" : "s are"} marked ${REVIEW_TYPE_LABEL.likely_barrier}: a fixed rule failed. Check ${likelyBarriers === 1 ? "it" : "each one"} on the page, then fix ${likelyBarriers === 1 ? "it" : "them"}. `
                  : `No issues are marked ${REVIEW_TYPE_LABEL.likely_barrier}. `}
                {latestIssues.occurrence_counts.all_evidence.toLocaleString()} occurrences across{" "}
                {latest.page_count.toLocaleString()} page
                {latest.page_count === 1 ? "" : "s"}.
              </p>
            </div>
            <LinkButton to={`/scans/${latest.id}/issues`} variant="primary" size="lg">
              Open the issues
              <ArrowRight className="h-5 w-5" aria-hidden />
            </LinkButton>
          </div>
        </Card>
      )}

      {!error && latest && (
        // Counts in the report's own vocabulary. "Pages crawled" and "image
        // evidence · raw image records" measured the crawler, not the audit.
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label={REVIEW_TYPE_LABEL.likely_barrier}
            value={latestIssues ? likelyBarriers : "Not available"}
            hint="Newest report · check on the page, then fix"
          />
          <StatCard
            label={REVIEW_TYPE_LABEL.expert_review}
            value={latestIssues ? reviewLeads : "Not available"}
            hint="Newest report · a person must decide"
          />
          <StatCard
            label="Occurrences"
            value={
              latestIssues
                ? latestIssues.occurrence_counts.all_evidence.toLocaleString()
                : "Not available"
            }
            hint="Newest report · not an accessibility score"
          />
          <StatCard
            label="Completed reports"
            value={isLoading ? "Loading" : completed.length}
            hint="All time"
          />
        </div>
      )}

      {!error && (
        <Card className="mt-5 overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-border bg-surface-subtle px-5 py-3.5">
            <h2 className="text-sm font-semibold text-fg">Recent reports</h2>
            {scans.length > 6 && (
              <Link
                to="/scans"
                className="text-xs font-semibold text-umich-blue underline underline-offset-2"
              >
                All {scans.length} reports
              </Link>
            )}
          </div>
          {scans.length === 0 ? (
            <EmptyState
              title="No reports yet"
              message="Start a scan to see reports here."
              action={
                <LinkButton to="/scans/new" variant="primary" size="lg">
                  <PlusCircle className="h-5 w-5" aria-hidden /> New scan
                </LinkButton>
              }
            />
          ) : (
            <ul className="divide-y divide-border">
              {scans.slice(0, 6).map((s) => (
                <li key={s.id}>
                  <Link
                    to={`/scans/${s.id}`}
                    className="flex min-h-target flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 no-underline transition-colors hover:bg-surface-muted/60 hover:no-underline"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold text-umich-blue">
                        {siteLabel(s.seed_url)}
                      </span>
                      <span className="block text-xs text-fg-subtle">
                        <ScanTag id={s.id} /> · {s.page_count.toLocaleString()} page
                        {s.page_count === 1 ? "" : "s"} · {s.finding_count.toLocaleString()}{" "}
                        image{s.finding_count === 1 ? "" : "s"} with text
                      </span>
                    </span>
                    <ScanStatusBadge value={s.status} />
                    <span className="shrink-0 text-xs tabular-nums text-fg-subtle">
                      {relativeTime(s.started_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {/* The scope caveat stays, it is what keeps a report from being read as
          a certificate, but as one line of standing context rather than the
          three-bullet product tour that used to hold a third of this page. */}
      {!error && scans.length > 0 && (
        <p className="mt-4 max-w-3xl text-xs leading-relaxed text-fg-subtle">
          Axcess reports what its checks found, and where. Automated results
          are for an expert to review. They never prove that a site meets
          accessibility rules. A check that did not run is not a pass. Each
          report lists what was and was not checked, above its Issues table.
        </p>
      )}
    </>
  );
}
