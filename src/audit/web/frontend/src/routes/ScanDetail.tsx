import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertOctagon,
  Accessibility,
  Download,
  GitCompare,
  ListFilter,
  Loader2,
  Square,
  Trash2,
} from "lucide-react";
import { api, exportUrl } from "../api/client";
import {
  Button,
  Card,
  LinkButton,
  PageHeader,
  StatCard,
} from "../components/ui";
import type { Severity } from "../api/types";

export default function ScanDetailRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ["scan", id],
    queryFn: () => api.getScan(id),
    enabled: Number.isFinite(id),
    // Poll while running so the page updates in near-real-time.
    refetchInterval: (q) =>
      q.state.data?.status === "running" ? 2000 : false,
  });

  const cancel = useMutation({
    mutationFn: () => api.cancelScan(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scan", id] }),
  });

  // Delete sends the user back to the scans list. We invalidate the list
  // query first (so the navigation lands on a fresh, deleted-row-free
  // page) and replace the history entry — pressing Back from /scans
  // shouldn't try to load the now-404 detail page.
  const deleteScan = useMutation({
    mutationFn: () => api.deleteScan(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["scans"] });
      qc.removeQueries({ queryKey: ["scan", id] });
      navigate("/scans", { replace: true });
    },
  });

  if (error) {
    return (
      <Card className="p-4 text-sm text-sev-critical">
        {error instanceof Error ? error.message : String(error)}
      </Card>
    );
  }
  if (isLoading || !data) {
    return <div className="text-fg-muted">Loading…</div>;
  }

  const severities: Severity[] = ["critical", "major", "minor", "info"];
  // Findings + exports are meaningless mid-crawl: synthesis only runs at
  // end-of-crawl, so the count is always 0 and an export would be empty.
  // Disable the contextual buttons (with a tooltip) until the scan settles.
  const isRunning = data.status === "running";
  const lockedTip =
    "Available once the crawl completes — findings are synthesized at end of scan.";

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Scans", to: "/scans" },
          { label: `Scan #${data.id}` },
        ]}
        title={<>Scan #{data.id}</>}
        subtitle={data.seed_url}
        actions={
          <>
            {isRunning ? (
              // Disabled "pending" placeholder — sized to match the
              // Findings CTA below (size="lg") so the layout doesn't jump
              // when the scan completes and the live link replaces it.
              <span
                className="inline-flex min-h-[52px] cursor-not-allowed items-center gap-2 rounded-xs border border-border bg-surface-muted px-6 py-3 text-base font-semibold text-fg-subtle"
                aria-disabled="true"
                title={lockedTip}
              >
                <Loader2
                  className="h-5 w-5 animate-spin"
                  aria-hidden
                />
                Findings — pending
              </span>
            ) : (
              // **The** primary CTA on a completed scan: the unified
              // Issues table. This replaced the old per-pipeline CTAs
              // because one operator entry point beats two — they
              // had to remember which surface had which slice.
              // The pipeline-specific views remain reachable as
              // secondary actions below for operators who already know
              // which slice they want.
              <LinkButton
                to={`/scans/${data.id}/issues`}
                variant="primary"
                size="lg"
              >
                <ListFilter className="h-5 w-5" aria-hidden />
                Issues ({data.finding_count + data.axe_violations_total})
              </LinkButton>
            )}
            {!isRunning && (
              <LinkButton
                to={`/scans/${data.id}/findings`}
                variant="secondary"
              >
                Image-of-text ({data.finding_count})
              </LinkButton>
            )}
            {!isRunning && (
              <LinkButton
                to={`/scans/${data.id}/a11y`}
                variant="secondary"
              >
                <Accessibility className="h-4 w-4" aria-hidden />
                WCAG axe ({data.axe_violations_total})
              </LinkButton>
            )}
            {data.previous_scan_id != null && !isRunning && (
              <LinkButton
                to={`/scans/${data.id}/diff?compare_to=${data.previous_scan_id}`}
                variant="secondary"
              >
                <GitCompare className="h-4 w-4" aria-hidden />
                Diff vs #{data.previous_scan_id}
              </LinkButton>
            )}
            {/* Delete is only offered when the scan isn't running — the
                backend rejects DELETE on a live scan with 409, so we hide
                the button rather than letting the user click into an
                error. The Stop crawl affordance below covers the running
                case; once stopped, the page re-renders with Delete shown. */}
            {!isRunning && (
              <Button
                variant="ghost"
                disabled={deleteScan.isPending}
                className="text-sev-critical hover:bg-sev-critical-bg"
                onClick={() => {
                  const ok = window.confirm(
                    `Delete scan #${data.id} (${data.seed_url})?\n\n` +
                      "This permanently removes the scan, its pages, " +
                      "findings, and history. Image blobs are kept (they " +
                      "may be referenced by other scans). This cannot be " +
                      "undone.",
                  );
                  if (ok) deleteScan.mutate();
                }}
              >
                <Trash2 className="h-4 w-4" aria-hidden />
                {deleteScan.isPending ? "Deleting…" : "Delete scan"}
              </Button>
            )}
          </>
        }
      />

      {deleteScan.error && (
        <Card
          className="mb-4 border-sev-critical/40 bg-sev-critical-bg p-3 text-sm text-sev-critical"
          role="alert"
        >
          Couldn&rsquo;t delete scan:{" "}
          {deleteScan.error instanceof Error
            ? deleteScan.error.message
            : String(deleteScan.error)}
        </Card>
      )}

      {/* Coverage truth — which detection methods this scan ran. A
          static-only or partial run is visible at a glance instead of
          being discovered after someone trusts an incomplete report.
          Skipped methods render struck-through with an sr-only note. */}
      {data.methods_used && data.methods_used.length > 0 && (
        <p
          className="mb-4 flex flex-wrap items-center gap-1.5 text-sm"
          aria-label="Detection methods used on this scan"
        >
          <span className="font-semibold text-fg-muted">Methods:</span>
          {data.methods_used.map((m) => (
            <span
              key={m.key}
              title={`${m.label} ${m.enabled ? "ran on this scan" : "was skipped on this scan"}`}
              className={
                "inline-block rounded-full border border-border bg-surface-muted px-2 py-0.5 text-2xs " +
                (m.enabled ? "text-fg" : "text-fg-subtle line-through opacity-60")
              }
            >
              {m.label}
              {!m.enabled && <span className="sr-only"> (skipped)</span>}
            </span>
          ))}
        </p>
      )}

      {data.status === "running" && (
        <Card className="mb-4 border-umich-blue/30 bg-umich-blue/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-umich-maize" />
              <strong className="text-fg">Crawl in progress</strong>
              <span className="text-sm text-fg-muted">
                refreshing every 2s
              </span>
            </div>
            {/* The only place a `danger` `lg` button is appropriate:
                stopping a live crawl is destructive and the user needs to
                see the affordance clearly. The confirm() wrapper provides
                Tolerance for Error (UD #5). */}
            <Button
              variant="danger"
              size="lg"
              onClick={() => {
                if (confirm("Stop this crawl? Pending pages will be dropped.")) {
                  cancel.mutate();
                }
              }}
              disabled={cancel.isPending}
            >
              <Square className="h-4 w-4 fill-current" aria-hidden />
              Stop crawl
            </Button>
          </div>
          {data.progress && (
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <StatCard label="Pages" value={data.page_count} />
              <StatCard label="Queued" value={data.progress.pending} />
              <StatCard label="In flight" value={data.progress.leased} />
              <StatCard label="Images" value={data.progress.images_seen} />
            </div>
          )}
          {data.progress && data.progress.in_flight_pages.length > 0 && (
            <details className="mt-3" open>
              <summary className="cursor-pointer text-sm font-semibold text-fg">
                Fetching now ({data.progress.in_flight_pages.length})
              </summary>
              <ul className="mt-2 space-y-0.5 font-mono text-2xs text-fg-muted">
                {data.progress.in_flight_pages.map((p) => (
                  <li
                    key={p.url}
                    className="flex items-center gap-2"
                    aria-live="polite"
                  >
                    <Loader2
                      className="h-3 w-3 shrink-0 animate-spin text-umich-blue"
                      aria-hidden
                    />
                    <span
                      className="inline-block rounded bg-surface-muted px-1.5 font-sans uppercase text-fg-subtle"
                      title={`Depth ${p.depth}`}
                    >
                      d{p.depth}
                    </span>
                    {p.attempts > 0 && (
                      <span
                        className="inline-block rounded bg-sev-major-bg px-1.5 font-sans text-sev-major"
                        title={`Retry ${p.attempts}`}
                      >
                        ↻{p.attempts}
                      </span>
                    )}
                    <span className="truncate">{p.url}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {data.progress && data.progress.recent_pages.length > 0 && (
            <details className="mt-3" open>
              <summary className="cursor-pointer text-sm font-semibold text-fg">
                Last {data.progress.recent_pages.length} fetched
              </summary>
              <ul className="mt-2 space-y-0.5 font-mono text-2xs text-fg-muted">
                {data.progress.recent_pages.map((p) => (
                  <li key={p.url_normalized} className="flex gap-2">
                    <span
                      className={
                        p.status_code && p.status_code >= 200 && p.status_code < 300
                          ? "text-fg"
                          : "text-sev-critical"
                      }
                    >
                      {p.status_code ?? "—"}
                    </span>
                    <span className="inline-block rounded bg-surface-muted px-1.5 font-sans uppercase text-fg-subtle">
                      {p.render_mode}
                    </span>
                    <span className="truncate">{p.url_normalized}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </Card>
      )}

      {data.blocked && (
        <Card className="mb-4 border-sev-critical/40 bg-sev-critical-bg p-4">
          <div className="flex items-start gap-3">
            <AlertOctagon className="mt-0.5 h-5 w-5 text-sev-critical" aria-hidden />
            <div className="text-sm">
              <strong className="text-sev-critical">
                Seed URL returned HTTP {data.blocked.status_code}
              </strong>
              {data.blocked.title && (
                <> — &ldquo;{data.blocked.title}&rdquo;</>
              )}
              . The crawler couldn&rsquo;t read past the entry page. Try{" "}
              <Link to="/scans/new">New scan</Link> with &ldquo;Use real
              browser (Playwright) for every page&rdquo; checked.
            </div>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <StatCard label="Pages" value={data.page_count} />
        <StatCard label="Findings" value={data.finding_count} />
        {severities.map((sev) => (
          <StatCard
            key={sev}
            label={sev}
            value={data.by_severity[sev] ?? 0}
            tone={sev}
          />
        ))}
      </div>

      <Card className="mt-6 p-4">
        <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-fg-subtle">
          <Download className="h-4 w-4" aria-hidden />
          Export this scan
        </h2>
        {isRunning && (
          <p className="mb-3 text-sm text-fg-muted">
            Exports become available when the crawl finishes — until then
            the report would be empty.
          </p>
        )}
        <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
          {(
            [
              // Audit report leads — it's the deliverable-shaped output:
              // issue cards with fix steps, owner type, effort, and a
              // verification plan. The other formats are data dumps for
              // import into other tools (Jira, spreadsheets) or feeds
              // (JSON for downstream pipelines).
              ["audit", "Audit report (cards, fixes, verify steps)"],
              ["xlsx", "Excel workbook (full report — every section as a table)"],
              ["csv", "CSV (one row per occurrence)"],
              ["json", "JSON (nested per finding)"],
              ["jira", "Jira CSV (import template)"],
              ["markdown", "Markdown report (data-dense)"],
            ] as const
          ).map(([fmt, label]) =>
            isRunning ? (
              <li key={fmt}>
                {/* Using a styled <span aria-disabled> instead of a disabled
                    <a> because anchors don't honor `disabled`. The visual
                    treatment + tooltip + aria-disabled cover keyboard,
                    screen-reader, and pointer users. */}
                <span
                  role="link"
                  aria-disabled="true"
                  tabIndex={-1}
                  title={lockedTip}
                  className="block cursor-not-allowed rounded-xs border border-border bg-surface-muted px-3 py-2 text-sm text-fg-subtle"
                >
                  {label}
                </span>
              </li>
            ) : (
              <li key={fmt}>
                <a
                  href={exportUrl(data.id, fmt)}
                  download
                  className="block rounded-xs border border-border px-3 py-2 text-sm no-underline hover:bg-surface-muted"
                >
                  {label}
                </a>
              </li>
            ),
          )}
        </ul>
      </Card>
    </>
  );
}
