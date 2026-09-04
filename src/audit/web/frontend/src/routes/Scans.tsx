import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListChecks, PlusCircle, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import {
  protectedQueryKey,
  useProtectedIdentityContext,
} from "../hooks/useProtectedIdentityContext";
import {
  Button,
  Card,
  EmptyState,
  LinkButton,
  PageHeader,
  ScanStatusBadge,
  relativeTime,
} from "../components/ui";
import type { ProtectedScanSummary, ScanSummary } from "../api/types";

/**
 * Scans list — the SPA's home page. Each row tells the operator three
 * things at a glance: where the crawl is pointed, what state it's in
 * (color-coded badge), and how recently it ran. Per-row actions live at
 * the right edge so the row body stays scannable.
 *
 * Running scans get a tinted background so they're impossible to miss
 * (and a pulsing badge from ScanStatusBadge as the secondary signal).
 * The Delete affordance is disabled for running scans — the backend
 * would 409 anyway, but disabling client-side avoids the round-trip.
 */
const REPORTS_PER_PAGE = 10;

export default function ScansRoute() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [requestedPage, setPage] = useState(1);
  const [requestedProtectedPage, setProtectedPage] = useState(1);
  const { data: scans = [], isLoading, isError } = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
  });
  const protectedIdentity = useProtectedIdentityContext();
  const protectedReports = useQuery({
    queryKey: protectedQueryKey("reports", protectedIdentity.fingerprint),
    queryFn: api.listProtectedScans,
    enabled: protectedIdentity.isReady,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: "always",
    // A 403/404 simply means this browser is not in a protected deployment;
    // public report browsing remains fully usable and does not surface a
    // misleading error card.
    retry: false,
  });
  const protectedScans =
    protectedIdentity.isReady && !protectedReports.isFetching
      ? protectedReports.data?.reports ?? []
      : [];

  const query = search.trim().toLowerCase();
  const filteredScans = scans.filter((scan) => !query || scan.seed_url.toLowerCase().includes(query) || `#${scan.id}`.includes(query));
  const filteredProtectedScans = protectedScans.filter((report) => !query || `#${report.scan_id}`.includes(query));

  const page = Math.min(requestedPage, Math.max(1, Math.ceil(filteredScans.length / REPORTS_PER_PAGE)));
  const protectedPage = Math.min(requestedProtectedPage, Math.max(1, Math.ceil(filteredProtectedScans.length / REPORTS_PER_PAGE)));
  const visibleScans = filteredScans.slice((page - 1) * REPORTS_PER_PAGE, page * REPORTS_PER_PAGE);
  const visibleProtectedScans = filteredProtectedScans.slice((protectedPage - 1) * REPORTS_PER_PAGE, protectedPage * REPORTS_PER_PAGE);

  return (
    <>
      {/* No header "New scan" action — the topbar carries the single
          global CTA. The empty state below keeps its contextual one. */}
      <PageHeader
        title="Reports"
        subtitle={isLoading ? "Loading…" : isError ? "Reports unavailable" : `${scans.length} public reports`}
      />

      <form role="search" aria-label="Search reports" className="mb-4 flex flex-wrap items-end gap-2" onSubmit={(event) => {
        event.preventDefault();
        setSearch(searchInput);
        setPage(1);
        setProtectedPage(1);
      }}>
        <div className="w-full sm:max-w-sm">
          <label htmlFor="report-search" className="mb-1 block text-sm font-medium text-fg">Search reports</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-fg-muted" aria-hidden />
            <input id="report-search" type="search" className="field rounded-lg pl-9" placeholder="Site URL or report #" value={searchInput} onChange={(event) => setSearchInput(event.target.value)} />
          </div>
        </div>
        <Button type="submit" variant="primary" className="rounded-lg">
          <Search className="h-4 w-4" aria-hidden /> Search
        </Button>
        {search && <Button type="button" variant="ghost" onClick={() => {
          setSearchInput(""); setSearch(""); setPage(1); setProtectedPage(1);
        }}>Clear search</Button>}
      </form>
      {query && <p role="status" className="mb-4 text-sm text-fg-muted">
        {filteredScans.length} public reports{protectedIdentity.isReady ? ` and ${filteredProtectedScans.length} protected reports` : ""} match “{search.trim()}”. Protected reports are searched by report number only.
      </p>}

      <p id="reports-help" className="mb-4 text-sm text-fg-muted">
        Findings are observations recorded during a scan. Related findings are grouped
        into issues. Open All issues to review every detection method, affected pages,
        and suggested fixes. The Image findings column counts only image-of-text evidence; zero
        does not mean there are no other issues. DOM states are page states reached
        by operating controls. Some findings need manual confirmation.
      </p>

      {isError ? (
        <p role="alert" className="mb-4 text-sm text-sev-critical">
          Could not load reports. Refresh the page to try again.
        </p>
      ) : isLoading ? (
        <p role="status">Loading reports…</p>
      ) : scans.length === 0 && protectedScans.length === 0 ? (
        <EmptyState
          title="No scans yet"
          message="Point the crawler at a URL to start auditing."
          action={
            <LinkButton to="/scans/new" variant="primary">
              <PlusCircle className="h-4 w-4" aria-hidden /> Create New Scan
            </LinkButton>
          }
        />
      ) : (
        <Card>
          {/* Keyboard users need focus on the overflow region to scroll the table. */}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
          <div className="overflow-x-auto focus-visible:shadow-focus" role="region" aria-label="Public reports table" aria-describedby="reports-help" tabIndex={0}>
            <table className="min-w-[58rem] w-full text-sm">
              <caption className="sr-only">Public reports, newest first</caption>
              <thead className="bg-surface-muted text-xs uppercase tracking-wide text-fg-muted">
                <tr>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">
                    Report
                  </th>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">
                    Site URL
                  </th>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-semibold">
                    Pages
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-semibold">
                    DOM states
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-semibold">
                    Image findings
                  </th>
                  <th scope="col" className="px-4 py-2 text-left font-semibold">
                    Started
                  </th>
                  <th scope="col" className="px-4 py-2 text-right font-semibold">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredScans.length === 0 && <tr><td colSpan={8} className="p-6 text-center text-fg-muted">No public reports match your search.</td></tr>}
                {visibleScans.map((s) => (
                  <ScanRow key={s.id} scan={s} />
                ))}
              </tbody>
            </table>
          </div>
          <ReportPagination label="Public reports" page={page} total={filteredScans.length} onPageChange={setPage} />
        </Card>
      )}

      {protectedIdentity.isChecking && (
        <p className="mt-4 text-sm text-fg-muted" aria-live="polite">
          Checking protected-report access…
        </p>
      )}

      {protectedIdentity.isReady && (
        <section className="mt-6" aria-labelledby="protected-reports-heading">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h2 id="protected-reports-heading" className="text-lg font-semibold text-fg">
                Protected reports
              </h2>
              <p className="mt-1 text-sm text-fg-muted">
                Your authorized reports only. Target locations and detailed evidence are not listed here.
              </p>
            </div>
            <LinkButton to="/scans/new?mode=login" variant="secondary">
              <PlusCircle className="h-4 w-4" aria-hidden /> New login scan
            </LinkButton>
          </div>
          {protectedReports.isFetching ? (
            <p className="text-sm text-fg-muted" aria-live="polite">
              Loading your protected reports…
            </p>
          ) : protectedScans.length === 0 ? (
            <Card className="p-5 text-sm text-fg-muted">
              No protected reports yet. Start one only after the target owner has authorized
              the scope and a least-privilege audit account is ready.
            </Card>
          ) : (
            <Card>
              {/* Keyboard users need focus on the overflow region to scroll the table. */}
              {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
              <div className="overflow-x-auto focus-visible:shadow-focus" role="region" aria-label="Protected reports table" tabIndex={0}>
                <table className="min-w-[58rem] w-full text-sm">
                  <caption className="sr-only">Your protected reports, newest activity first</caption>
                  <thead className="bg-surface-muted text-xs uppercase tracking-wide text-fg-muted">
                    <tr>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Report</th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Status</th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Handling</th>
                      <th scope="col" className="px-4 py-2 text-right font-semibold">Pages</th>
                      <th scope="col" className="px-4 py-2 text-right font-semibold">Issue leads</th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">Updated</th>
                      <th scope="col" className="px-4 py-2 text-right font-semibold">Open</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {filteredProtectedScans.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-fg-muted">No protected reports match your search.</td></tr>}
                    {visibleProtectedScans.map((report) => <ProtectedReportRow key={report.scan_id} report={report} />)}
                  </tbody>
                </table>
              </div>
              <ReportPagination label="Protected reports" page={protectedPage} total={filteredProtectedScans.length} onPageChange={setProtectedPage} />
            </Card>
          )}
        </section>
      )}
    </>
  );
}

function ReportPagination({ label, page, total, onPageChange }: {
  label: string;
  page: number;
  total: number;
  onPageChange: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / REPORTS_PER_PAGE));
  return (
    <nav aria-label={`${label} pagination`} className="flex flex-wrap items-center justify-between gap-3 border-t border-border p-4">
      <p role="status" aria-atomic="true" className="text-sm text-fg-muted">
        Showing {total === 0 ? 0 : (page - 1) * REPORTS_PER_PAGE + 1}–{Math.min(page * REPORTS_PER_PAGE, total)} of {total} reports · Page {page} of {pages}
      </p>
      <div className="flex gap-2">
        <Button variant="secondary" aria-label={`Previous page of ${label.toLowerCase()}`} aria-disabled={page === 1} onClick={() => { if (page > 1) onPageChange(page - 1); }}>
          Previous
        </Button>
        <Button variant="secondary" aria-label={`Next page of ${label.toLowerCase()}`} aria-disabled={page === pages} onClick={() => { if (page < pages) onPageChange(page + 1); }}>
          Next
        </Button>
      </div>
    </nav>
  );
}

function ProtectedReportRow({ report }: { report: ProtectedScanSummary }) {
  return (
    <tr className="transition-colors hover:bg-surface-muted/60">
      <th scope="row" className="whitespace-nowrap px-4 py-2 text-left font-mono text-xs text-fg-muted">#{report.scan_id}</th>
      <td className="px-4 py-2"><span className="font-medium text-fg">{report.protection_status.replaceAll("_", " ")}</span></td>
      <td className="px-4 py-2 text-fg-muted">{report.environment} · {report.data_classification}</td>
      <td className="px-4 py-2 text-right tabular-nums text-fg">{report.page_count.toLocaleString()}</td>
      <td className="px-4 py-2 text-right tabular-nums text-fg">{report.issue_occurrences.toLocaleString()}</td>
      <td className="px-4 py-2 text-xs text-fg-subtle" title={report.updated_at}>{relativeTime(report.updated_at)}</td>
      <td className="px-4 py-2 text-right">
        <LinkButton to={`/scans/${report.scan_id}/protected`} variant="ghost" aria-label={`Open protected report ${report.scan_id}`}>
          Open protected report
        </LinkButton>
      </td>
    </tr>
  );
}

/**
 * One scans-table row. Pulled out so the delete mutation's loading state
 * is local to the row that owns it — clicking delete on row 7 doesn't
 * grey out the buttons in row 8.
 */
function ScanRow({ scan }: { scan: ScanSummary }) {
  const isRunning = scan.status === "running";
  return (
    <tr
      className={
        isRunning
          ? "bg-umich-blue/5 transition-colors hover:bg-umich-blue/10"
          : "transition-colors hover:bg-surface-muted/60"
      }
    >
      <th scope="row" className="whitespace-nowrap px-4 py-2 text-left font-mono text-xs text-fg-muted">
        <Link
          to={`/scans/${scan.id}`}
          className="report-link inline-flex min-h-target items-center px-1 font-semibold"
        >
          <span className="sr-only">Open report </span>#{scan.id}
        </Link>
      </th>
      <td className="min-w-48 max-w-md break-all px-4 py-2 text-fg">
        <Link
          to={`/scans/${scan.id}`}
          className="report-link inline-flex min-h-target items-center px-1 font-semibold"
          title={scan.seed_url}
        >
          {scan.seed_url}
        </Link>
      </td>
      <td className="px-4 py-2">
        <ScanStatusBadge value={scan.status} />
      </td>
      <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums text-fg">
        {scan.page_count.toLocaleString()}
      </td>
      {/* States reached by operating controls, alongside pages: a scan of an
          application is not described by its URL count alone. */}
      <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums text-fg">
        {(scan.dom_state_count ?? 0).toLocaleString()}
      </td>
      <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums">
        <span className="text-fg">{scan.finding_count.toLocaleString()}</span>
      </td>
      <td
        className="whitespace-nowrap px-4 py-2 text-xs text-fg-subtle"
        // Full ISO on hover gives precision when "2h ago" isn't enough —
        // e.g. comparing two scans that both say "yesterday".
        title={scan.started_at ?? undefined}
      >
        {relativeTime(scan.started_at)}
      </td>
      <td className="whitespace-nowrap px-4 py-2">
        {/* Per-row actions kept at default `md` size (44px tall). The
            earlier compressed `px-2 py-1 text-xs` style was the exact
            SC 2.5.5 fail flagged by the discovery audit — destructive
            controls in particular must be a real target. The action
            cluster gets `gap-2` so the two controls don't visually
            merge into one wide button. */}
        <div className="flex items-center justify-end gap-2">
          <LinkButton
            to={`/scans/${scan.id}/issues`}
            variant="ghost"
            className="report-link"
            aria-label={`All issues for report ${scan.id}`}
          >
            <ListChecks className="h-4 w-4" aria-hidden />
            All issues
          </LinkButton>
          <DeleteScanButton scan={scan} />
        </div>
      </td>
    </tr>
  );
}

/**
 * Delete button with a window.confirm gate. We use the native confirm()
 * intentionally — it's keyboard-accessible by default, screen-reader
 * friendly, and adds zero UI surface. The cost is a slightly utilitarian
 * dialog, which is appropriate for an internal a11y tool and avoids the
 * trap of building a custom modal that itself fails axe.
 *
 * Running scans show a disabled button with a tooltip explaining why —
 * the user shouldn't have to discover the constraint by clicking.
 */
function DeleteScanButton({ scan }: { scan: ScanSummary }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const isRunning = scan.status === "running";

  const mutation = useMutation({
    mutationFn: () => api.deleteScan(scan.id),
    onSuccess: () => {
      // Refresh the scans list. The deleted row vanishes on next render.
      void queryClient.invalidateQueries({ queryKey: ["scans"] });
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
    },
  });

  if (isRunning) {
    return (
      <Button
        variant="ghost"
        disabled
        title="Cancel the running scan before deleting it."
        className="text-fg-subtle"
        aria-label={`Delete scan ${scan.id} (disabled — scan is running)`}
      >
        <Trash2 className="h-4 w-4" aria-hidden />
        Delete
      </Button>
    );
  }

  return (
    <>
      <Button
        variant="ghost"
        disabled={mutation.isPending}
        className="text-sev-critical hover:bg-sev-critical-bg"
        aria-label={`Delete scan ${scan.id}`}
        onClick={() => {
          // confirm() blocks; it's the right primitive for "are you sure".
          // Message includes the scan ID and seed URL so the user knows
          // exactly which scan they're about to remove.
          const ok = window.confirm(
            `Delete scan #${scan.id} (${scan.seed_url})?\n\n` +
              "This permanently removes the scan, its pages, findings, and " +
              "history. Image blobs are kept (they may be referenced by " +
              "other scans). This cannot be undone.",
          );
          if (ok) mutation.mutate();
        }}
      >
        <Trash2 className="h-4 w-4" aria-hidden />
        {mutation.isPending ? "Deleting…" : "Delete"}
      </Button>
      {error && (
        // role="alert" + text-xs (12px). Bumped from text-2xs (10px)
        // because errors are critical to read on first glance — AAA
        // reading-comfort doesn't mandate a font size, but tiny error
        // text fights the user.
        <span className="ml-2 text-xs text-sev-critical" role="alert">
          {error}
        </span>
      )}
    </>
  );
}
