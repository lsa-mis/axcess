import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, PlusCircle, ServerCrash } from "lucide-react";
import { api } from "../api/client";
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

  return (
    <>
      {/* No "New scan" action here — the topbar carries the single
          global CTA. (The empty state below keeps its contextual one
          for the zero-scans first run.) */}
      <PageHeader
        title="Dashboard"
        subtitle="Local, offline accessibility review."
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

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Completed scans"
          value={isLoading ? "—" : completed.length}
        />
        <StatCard
          label="Pages crawled"
          value={isLoading ? "—" : totalPages.toLocaleString()}
        />
        <StatCard
          label="Findings"
          value={isLoading ? "—" : totalFindings.toLocaleString()}
          hint="across all scans"
        />
        <StatCard
          label="Most recent"
          value={scans[0] ? `#${scans[0].id}` : "—"}
          hint={scans[0]?.status}
          tone={scans[0]?.status === "completed" ? "default" : "info"}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-fg-subtle">
            Recent scans
          </h2>
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
                <li key={s.id} className="py-2.5">
                  <Link
                    to={`/scans/${s.id}`}
                    className="flex items-center justify-between gap-3 no-underline"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-fg">
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
        </Card>

        <Card className="p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-fg-subtle">
            About this tool
          </h2>
          <p className="text-sm leading-relaxed text-fg-muted">
            A local auditor that crawls a site, runs OCR + VLM against every
            image it finds, and compares the image&rsquo;s text to the authored{" "}
            <code className="rounded bg-surface-muted px-1 py-0.5 font-mono text-xs">
              alt
            </code>{" "}
            attribute. Findings are prioritized by severity and exportable
            to CSV, JSON, Jira, or a Markdown report. Fully offline after
            the one-time model pull.
          </p>
          <ul className="mt-3 space-y-1 text-sm text-fg-muted">
            <li className="flex gap-2">
              <AlertTriangle
                className="mt-0.5 h-4 w-4 shrink-0 text-umich-blue"
                aria-hidden
              />
              WCAG 2.2 AAA — this UI itself passes axe-core on every view.
            </li>
          </ul>
        </Card>
      </div>
    </>
  );
}
