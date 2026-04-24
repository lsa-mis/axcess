import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PlusCircle } from "lucide-react";
import { api } from "../api/client";
import { Card, EmptyState, PageHeader, StatusChip } from "../components/ui";

export default function ScansRoute() {
  const { data: scans = [], isLoading } = useQuery({
    queryKey: ["scans"],
    queryFn: api.listScans,
  });

  return (
    <>
      <PageHeader
        title="Scans"
        subtitle={isLoading ? "Loading…" : `${scans.length} total`}
        actions={
          <Link
            to="/scans/new"
            className="inline-flex items-center gap-1.5 rounded-xs bg-umich-blue px-3 py-1.5 text-sm font-semibold text-fg-inverse no-underline hover:bg-umich-blue-600"
          >
            <PlusCircle className="h-4 w-4" aria-hidden />
            New scan
          </Link>
        }
      />

      {scans.length === 0 && !isLoading ? (
        <EmptyState
          title="No scans yet"
          message="Point the crawler at a URL to start auditing."
          action={
            <Link
              to="/scans/new"
              className="inline-flex items-center gap-1 rounded-xs bg-umich-blue px-3 py-1.5 text-sm font-semibold text-fg-inverse no-underline"
            >
              <PlusCircle className="h-4 w-4" aria-hidden /> Start a scan
            </Link>
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
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {scans.map((s) => (
                <tr
                  key={s.id}
                  className="transition-colors hover:bg-surface-muted/60"
                >
                  <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-fg-muted">
                    <Link to={`/scans/${s.id}`} className="no-underline">
                      #{s.id}
                    </Link>
                  </td>
                  <td className="max-w-md truncate px-4 py-2 text-fg">
                    <Link
                      to={`/scans/${s.id}`}
                      className="text-umich-blue no-underline hover:underline"
                      title={s.seed_url}
                    >
                      {s.seed_url}
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <StatusChip value={s.status as never} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums text-fg">
                    {s.page_count.toLocaleString()}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums">
                    {s.finding_count > 0 ? (
                      <Link
                        to={`/scans/${s.id}/findings`}
                        className="font-semibold text-umich-blue no-underline hover:underline"
                      >
                        {s.finding_count.toLocaleString()}
                      </Link>
                    ) : (
                      <span className="text-fg-subtle">0</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-fg-subtle">
                    {s.started_at?.slice(0, 16) ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
