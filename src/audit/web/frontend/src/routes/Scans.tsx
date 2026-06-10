import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListChecks, PlusCircle, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import {
  Button,
  Card,
  EmptyState,
  LinkButton,
  PageHeader,
  ScanStatusBadge,
  relativeTime,
} from "../components/ui";
import type { ScanSummary } from "../api/types";

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
export default function ScansRoute() {
  const { data: scans = [], isLoading } = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
  });

  return (
    <>
      {/* No header "New scan" action — the topbar carries the single
          global CTA. The empty state below keeps its contextual one. */}
      <PageHeader
        title="Scans"
        subtitle={isLoading ? "Loading…" : `${scans.length} total`}
      />

      {scans.length === 0 && !isLoading ? (
        <EmptyState
          title="No scans yet"
          message="Point the crawler at a URL to start auditing."
          action={
            <LinkButton to="/scans/new" variant="primary">
              <PlusCircle className="h-4 w-4" aria-hidden /> New scan
            </LinkButton>
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <caption className="sr-only">Scans, newest first</caption>
            <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  #
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Seed URL
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Status
                </th>
                <th scope="col" className="px-4 py-2 text-right font-semibold">
                  Pages
                </th>
                <th scope="col" className="px-4 py-2 text-right font-semibold">
                  Findings
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
              {scans.map((s) => (
                <ScanRow key={s.id} scan={s} />
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
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
      <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-fg-muted">
        <Link
          to={`/scans/${scan.id}`}
          className="text-umich-blue no-underline hover:underline"
        >
          #{scan.id}
        </Link>
      </td>
      <td className="max-w-md truncate px-4 py-2 text-fg">
        <Link
          to={`/scans/${scan.id}`}
          className="text-umich-blue no-underline hover:underline"
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
      <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums">
        {scan.finding_count > 0 ? (
          <Link
            to={`/scans/${scan.id}/findings`}
            className="font-semibold text-umich-blue no-underline hover:underline"
          >
            {scan.finding_count.toLocaleString()}
          </Link>
        ) : (
          <span className="text-fg-subtle">0</span>
        )}
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
        <div className="flex items-center justify-end gap-1">
          {scan.finding_count > 0 && (
            <LinkButton
              to={`/scans/${scan.id}/findings`}
              variant="ghost"
              className="px-2 py-1 text-xs"
              aria-label={`View ${scan.finding_count} findings for scan ${scan.id}`}
            >
              <ListChecks className="h-3.5 w-3.5" aria-hidden />
              Findings
            </LinkButton>
          )}
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
        className="px-2 py-1 text-xs text-fg-subtle"
        aria-label={`Delete scan ${scan.id} (disabled — scan is running)`}
      >
        <Trash2 className="h-3.5 w-3.5" aria-hidden />
        Delete
      </Button>
    );
  }

  return (
    <>
      <Button
        variant="ghost"
        disabled={mutation.isPending}
        className="px-2 py-1 text-xs text-sev-critical hover:bg-sev-critical-bg"
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
        <Trash2 className="h-3.5 w-3.5" aria-hidden />
        {mutation.isPending ? "Deleting…" : "Delete"}
      </Button>
      {error && (
        <span className="ml-2 text-2xs text-sev-critical" role="alert">
          {error}
        </span>
      )}
    </>
  );
}
