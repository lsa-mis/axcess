import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  MapPin,
  PlusCircle,
  ServerCrash,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { api } from "../api/client";
import { siteLabel } from "../components/ReportCrumb";
import {
  Card,
  EmptyState,
  LinkButton,
  PageHeader,
  StatCard,
} from "../components/ui";

/** Home landing: counts across all scans + link to kick off a new one. */
export default function DashboardRoute() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
  });

  const scans = data ?? [];
  const completed = scans.filter((s) => s.status === "completed");
  const totalPages = completed.reduce((acc, s) => acc + s.page_count, 0);
  const totalFindings = completed.reduce((acc, s) => acc + s.finding_count, 0);
  const running = scans.find((s) => s.status === "running");
  const latest = completed[0];
  const { data: latestIssues } = useQuery({
    queryKey: ["issues", latest?.id, "dashboard"],
    queryFn: () => api.listIssues(latest!.id),
    enabled: !!latest,
  });

  return (
    <>
      {/* No "New scan" action here — the topbar carries the single
          global CTA. (The empty state below keeps its contextual one
          for the zero-scans first run.) */}
      <PageHeader
        title="Accessibility workbench"
        subtitle="Scan a site, inspect the evidence, and produce a clear remediation report."
      />

      {error && (
        <Card className="mb-4 flex items-start gap-2 border-sev-critical/30 bg-sev-critical-bg p-4 text-sev-critical">
          <ServerCrash className="mt-0.5 h-5 w-5" aria-hidden />
          <div className="text-sm">
            <strong>Couldn&rsquo;t load scans.</strong>{" "}
            {error instanceof Error ? error.message : String(error)}
          </div>
        </Card>
      )}

      {running && (
        <Card className="mb-4 flex items-center justify-between gap-3 border-umich-blue/30 bg-umich-blue/5 p-4">
          <div className="flex items-center gap-2 text-sm">
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-umich-maize" />
            <strong className="text-fg">Scan #{running.id}</strong>
            <span className="text-fg-muted">
              is crawling {running.seed_url}
            </span>
          </div>
          <Link
            to={`/scans/${running.id}`}
            className="text-sm font-semibold text-umich-blue underline underline-offset-2"
          >
            View progress →
          </Link>
          {/* Plain inline Link is correct here — this is a body text link, not
              a button-shaped affordance. The variant API on LinkButton is for
              chrome elements (page-header CTAs, table action cells, etc). */}
        </Card>
      )}

      {!error && latest && latestIssues && (
        <Card className="mb-6 overflow-hidden border-umich-blue bg-[linear-gradient(118deg,#001E3C_0%,#002F5D_58%,#00417B_100%)] shadow-raised">
          <div className="grid gap-5 p-6 sm:p-7 md:grid-cols-[1fr_auto] md:items-center">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-surface-inverse-fg-subtle">
                Latest completed report ·{" "}
                <span className="break-all normal-case tracking-normal">
                  {siteLabel(latest.seed_url)}
                </span>
              </p>
              <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">
                {latestIssues.total_unfiltered > 0
                  ? `View ${latestIssues.total_unfiltered} accessibility issue groups`
                  : "View the completed scan report"}
              </h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-surface-inverse-fg-subtle">
                {latestIssues.occurrence_counts.high_confidence.toLocaleString()}{" "}
                high-confidence occurrences are separated from{" "}
                {latestIssues.review_lane_counts.expert_review} groups that
                still need expert confirmation.
              </p>
            </div>
            <LinkButton
              to={`/scans/${latest.id}/issues`}
              variant="secondary"
              size="lg"
              className="border-white bg-white text-umich-blue hover:bg-surface-muted"
            >
              Open issue table <ArrowRight className="h-5 w-5" aria-hidden />
            </LinkButton>
          </div>
        </Card>
      )}

      {!error && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Completed scans"
            value={isLoading ? "—" : completed.length}
          />
          <StatCard
            label="Pages crawled"
            value={isLoading ? "—" : totalPages.toLocaleString()}
          />
          <StatCard
            label="Image evidence"
            value={isLoading ? "—" : totalFindings.toLocaleString()}
            hint="raw image records"
          />
          <StatCard
            label="Most recent"
            value={scans[0] ? `#${scans[0].id}` : "—"}
            hint={scans[0]?.status}
            tone={scans[0]?.status === "completed" ? "default" : "info"}
          />
        </div>
      )}

      {!error && (
        <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-[1.15fr_0.85fr]">
          <Card className="overflow-hidden">
            <div className="border-b border-border bg-surface-subtle px-5 py-4">
              <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-fg-subtle">
                Recent scans
              </h2>
            </div>
            <div className="px-5 py-2">
              {scans.length === 0 ? (
                <EmptyState
                  title="No scans yet"
                  message="Run a crawl to see findings here."
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
                        className="report-link -mx-2 flex min-h-target items-center justify-between gap-4 rounded-xs px-2 py-3 transition-colors"
                      >
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-umich-blue">
                            #{s.id} · {s.seed_url}
                          </div>
                          <div className="text-xs text-fg-subtle">
                            {s.status} · {s.page_count} pages ·{" "}
                            {s.finding_count} findings
                          </div>
                        </div>
                        <span className="shrink-0 text-xs text-fg-subtle">
                          {s.started_at?.slice(0, 16)}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>

          <Card className="p-5 sm:p-6">
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-umich-blue">
              How Axcess works
            </p>
            <h2 className="mb-2 text-xl font-semibold tracking-tight text-fg">
              One clear report
            </h2>
            <p className="text-sm leading-6 text-fg-muted">
              Each report explains what was detected, why it matters, the
              expected fix, and the exact stored locations. Axcess provides
              evidence for expert review; it does not certify conformance.
            </p>
            <ul className="mt-5 space-y-4 text-sm text-fg-muted">
              <li className="flex gap-3">
                <ShieldCheck
                  className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue"
                  aria-hidden
                />
                <span>
                  <strong className="block text-fg">
                    Understand the issue
                  </strong>
                  See the source engine, WCAG criterion, user impact, and
                  confidence.
                </span>
              </li>
              <li className="flex gap-3">
                <Wrench
                  className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue"
                  aria-hidden
                />
                <span>
                  <strong className="block text-fg">
                    Apply the expected fix
                  </strong>
                  Use concise remediation and acceptance guidance in the same
                  row.
                </span>
              </li>
              <li className="flex gap-3">
                <MapPin
                  className="mt-0.5 h-5 w-5 shrink-0 text-umich-blue"
                  aria-hidden
                />
                <span>
                  <strong className="block text-fg">
                    Open the exact location
                  </strong>
                  Follow the page, selector, and stored evidence links directly.
                </span>
              </li>
            </ul>
          </Card>
        </div>
      )}
    </>
  );
}
