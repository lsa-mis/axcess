import { Link, useParams, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "../api/client";
import {
  Card,
  LinkButton,
  PageHeader,
  SeverityChip,
  StatCard,
} from "../components/ui";
import type { DiffEntry } from "../api/types";

export default function DiffRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params] = useSearchParams();
  const compareTo = Number(params.get("compare_to") ?? NaN);

  const { data, error, isLoading } = useQuery({
    queryKey: ["diff", id, compareTo],
    queryFn: () => api.getDiff(id, compareTo),
    enabled: Number.isFinite(id) && Number.isFinite(compareTo),
  });

  if (!Number.isFinite(compareTo)) {
    return (
      <Card className="p-4 text-sm text-sev-critical">
        Missing <code>compare_to</code> query parameter.
      </Card>
    );
  }
  if (error) {
    return (
      <Card className="p-4 text-sm text-sev-critical">
        {error instanceof Error ? error.message : String(error)}
      </Card>
    );
  }
  if (isLoading || !data) return <div className="text-fg-muted">Loading…</div>;

  return (
    <>
      <PageHeader
        crumbs={[
          { label: "Scans", to: "/scans" },
          { label: `Scan #${id}`, to: `/scans/${id}` },
          { label: "Diff" },
        ]}
        title={<>Diff — #{id} vs #{compareTo}</>}
        actions={
          <LinkButton to={`/scans/${id}`} variant="secondary">
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Back to Scan #{id}
          </LinkButton>
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="New" value={data.counts.new} tone="critical" />
        <StatCard label="Resolved" value={data.counts.resolved} tone="info" />
        <StatCard
          label="Still open"
          value={data.counts.still_open}
          tone="major"
        />
        <StatCard
          label="Status changed"
          value={data.counts.status_changed}
          tone="minor"
        />
      </div>

      <Section
        title={`New (${data.counts.new})`}
        emptyMessage="No new findings."
        rows={data.new}
        kind="current"
      />
      <Section
        title={`Resolved (${data.counts.resolved})`}
        emptyMessage="Nothing has been cleared."
        rows={data.resolved}
        kind="previous"
      />
      <Section
        title={`Status changed (${data.counts.status_changed})`}
        emptyMessage="No manual status updates."
        rows={data.status_changed}
        kind="changed"
      />
      <Section
        title={`Still open (${data.counts.still_open})`}
        emptyMessage="No remaining open findings."
        rows={data.still_open}
        kind="current"
      />
    </>
  );
}

function Section({
  title,
  emptyMessage,
  rows,
  kind,
}: {
  title: string;
  emptyMessage: string;
  rows: DiffEntry[];
  kind: "current" | "previous" | "changed";
}) {
  return (
    <section className="mt-6">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-fg-subtle">
        {title}
      </h2>
      {rows.length === 0 ? (
        <Card className="p-4 text-sm text-fg-muted">{emptyMessage}</Card>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-surface-muted text-2xs uppercase tracking-wide text-fg-subtle">
              <tr>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Severity
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Page
                </th>
                <th scope="col" className="px-4 py-2 text-left font-semibold">
                  Status
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((e, i) => (
                <tr key={i} className="hover:bg-surface-muted/60">
                  <td className="px-4 py-2">
                    {e.severity ? (
                      <SeverityChip value={e.severity} />
                    ) : e.previous_severity ? (
                      <SeverityChip value={e.previous_severity} />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="max-w-[480px] truncate px-4 py-2">
                    {kind === "previous" && e.previous_finding_id ? (
                      <Link
                        to={`/findings/${e.previous_finding_id}`}
                        className="text-umich-blue underline underline-offset-2"
                        title={e.url_normalized}
                      >
                        {e.url_normalized}
                      </Link>
                    ) : e.current_finding_id ? (
                      <Link
                        to={`/findings/${e.current_finding_id}`}
                        className="text-umich-blue underline underline-offset-2"
                        title={e.url_normalized}
                      >
                        {e.url_normalized}
                      </Link>
                    ) : (
                      e.url_normalized
                    )}
                  </td>
                  <td className="px-4 py-2 text-xs text-fg-muted">
                    {kind === "changed" ? (
                      <>
                        {e.previous_status} →{" "}
                        <strong>{e.current_status}</strong>
                      </>
                    ) : kind === "previous" ? (
                      <>was {e.previous_status}</>
                    ) : (
                      (e.current_status ?? "—")
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </section>
  );
}
